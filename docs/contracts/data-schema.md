# Data schema

Two stores: one Table Storage row for operational state, one Cosmos container for events. Timestamps are ISO 8601 in UTC with a trailing `Z`.

## Table Storage: `state`

Table `state`, one entity: `PartitionKey = "bonfire"`, `RowKey = "state"`. Every write replaces the whole entity (Replace, never Merge) and is conditional on the ETag from the preceding read (If-Match). On HTTP 412 the writer re-reads and re-evaluates; it never retries the same write. Table Storage has no null: a null field below is written by omitting the property, and readers treat an absent property as null.

| Field | Type | Meaning | Written by | Read by |
|---|---|---|---|---|
| `vm_state` | string: `out`, `igniting`, `lit`, `extinguishing` | Current state; transitions in [architecture.md](../architecture.md#vm-state-machine) | Function, agent (per the transition table) | everyone |
| `state_since` | datetime | When `vm_state` last changed | whoever changed it | Function (check reply, watchdog) |
| `session_id` | string (UUID) or null | Identifies the current session from ignite to out | Function on ignite; cleared on out | agent (events), Function |
| `session_started_at` | datetime or null | Set on ignite | Function | Function (ceiling, hours) |
| `session_ended_at` | datetime or null | Set when extinguishing begins | Function or agent | Function (hours) |
| `idle_since` | datetime or null | First check that saw zero players in the current idle streak | agent | agent, Function (check reply) |
| `warnings_posted` | string | Comma-separated warning thresholds already posted this streak, e.g. `""`, `"15"`, `"15,5"` | agent | agent |
| `unknown_since` | datetime or null | First check that got `unknown` in the current unknown streak | agent | agent |
| `unknown_alerted` | bool | Whether the unknown alert was posted this streak | agent | agent |
| `last_heartbeat` | datetime or null | Time of the agent's last check | agent | Function (watchdog) |
| `last_player_count` | int32 | Last count; `-1` when unknown | agent | Function (check, extinguish confirmation) |
| `last_health` | string: `ok`, `degraded`, `crashed`, `unknown` | Last adapter `health` | agent | Function (check reply) |
| `ceiling_warned` | bool | Whether `watchdog_ceiling_warning` was posted this session | Function; reset to false on ignite | Function |
| `pending_command` | string or null: `restart` | Command for the agent to run on its next check; set only while `vm_state` is `lit` | Function sets; agent clears | agent |
| `hours_this_month` | double | Lit hours accumulated in `hours_month` | whoever writes `out` | Function (cost reply) |
| `hours_month` | string `YYYY-MM` | Month `hours_this_month` belongs to; on mismatch with the current month, reset hours to 0 before adding | whoever writes `out` | Function |
| `lock_until` | datetime or null | Transition lock; see below | Function, agent | everyone |

### Lock semantics

- Taken by whoever moves to `igniting` or `extinguishing`, set to `now + LOCK_TTL_MINUTES` (5 minutes; see [configuration.md](configuration.md#constants)).
- While `lock_until` is in the future and `vm_state` is `igniting` or `extinguishing`, command handlers do not change state; they reply with the status message.
- Cleared by the transition out of those states.
- If `lock_until` is in the past, the state is suspect: the next handler or watchdog tick reconciles it against the VM power state (architecture rule 3).

### Values per state

| Field | out | igniting | lit | extinguishing |
|---|---|---|---|---|
| `session_*` | null | set | set | set, `session_ended_at` set |
| `idle_since`, `warnings_posted` | null / `""` | null / `""` | as observed | null / `""` |
| `lock_until` | null | set | null | set |
| `last_heartbeat` | stale | may be null until the agent starts | fresh | fresh until the VM dies |

## Cosmos DB: `events`

Database `bonfire`, container `events`, partition key `/month`, default TTL 7776000 seconds (90 days).

| Field | Type | Values |
|---|---|---|
| `id` | string | UUID |
| `month` | string | `YYYY-MM` of `ts`; the partition key |
| `ts` | datetime | When the event happened |
| `session_id` | string or null | From the state row; null for commands run while out |
| `type` | string | `command`, `vm`, `watchdog`, `game` |
| `action` | string | Per type, below |
| `actor` | string | Discord user ID for commands and button clicks; `agent`; `function` |
| `player_count` | int or null | Count at the time, null when unknown or not applicable |
| `duration_ms` | int or null | Handler latency for commands; ignite-to-ready for `vm/ready` |
| `ok` | bool | Whether the action succeeded |
| `detail` | string | Free text, at most 500 characters; never secrets |

| `type` | Allowed `action` values |
|---|---|
| `command` | `ignite`, `extinguish`, `check`, `cost`, `restart`, `keep_lit` |
| `vm` | `ready`, `ignite_failed`, `deallocated`, `backup` |
| `watchdog` | `warning`, `idle_cancelled`, `idle_shutdown`, `unknown_alert`, `ceiling_warning`, `ceiling`, `heartbeat_missing`, `boot_failed` |
| `game` | `crash`, `crash_gave_up` |

`command/ignite` with actor `agent` and detail `adopted manual start` records a VM started outside Bonfire that the agent adopted. `vm/backup` records the backup upload before an extinguish, with the file count or the failure in `detail`.

### Examples

A command event:

```json
{
  "id": "6f1c2a3e-...",
  "month": "2026-09",
  "ts": "2026-09-12T23:04:11Z",
  "session_id": "b7e0...",
  "type": "command",
  "action": "ignite",
  "actor": "123456789012345678",
  "player_count": null,
  "duration_ms": 1830,
  "ok": true,
  "detail": "vm start accepted"
}
```

An idle-shutdown event:

```json
{
  "id": "9a8b...",
  "month": "2026-09",
  "ts": "2026-09-13T02:31:00Z",
  "session_id": "b7e0...",
  "type": "watchdog",
  "action": "idle_shutdown",
  "actor": "agent",
  "player_count": 0,
  "duration_ms": null,
  "ok": true,
  "detail": "idle 45 min; warnings 15,5 posted"
}
```

## Metrics queries

The PRD section 11 metrics map to these queries, all filtered by `month`:

- Sessions ignited by non-admin: `command/ignite` with `ok = true`, grouped by `actor`.
- Ignite-to-ready: `vm/ready` `duration_ms`, 95th percentile.
- Idle hours: sum over sessions of (`idle_shutdown.ts` minus the `idle_since` recorded in `detail`), versus `hours_this_month`.
- Safety-net triggers: count of `watchdog/ceiling`, `watchdog/heartbeat_missing` and `watchdog/boot_failed`.
- Warnings that worked: count of `watchdog/idle_cancelled`.
