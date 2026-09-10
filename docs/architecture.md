# Bonfire architecture

Bonfire starts and stops one game VM on demand. This document is the system-level design; per-phase design lives in `superpowers/specs/`. Decisions are recorded in [adr/](adr/README.md).

## Components

Four parts run Bonfire. Each owns one concern.

- **Function** (Azure Functions, consumption plan). Owns: the Discord Interactions Endpoint (slash commands and button clicks), the safety-net timer, and every transition it is allowed to make in the state machine below. Depends on: the state table, the events container, the Azure Compute API for the VM, Key Vault for the bot token. Never talks to the adapter. See [ADR 0003](adr/0003-controller-azure-function-interactions-endpoint.md).
- **Agent** (a service on the VM, run by a systemd timer every `idle_check_interval` minutes; a boot-time unit pulls `bonfire_git_ref` and reinstalls it first). Owns: readiness detection, the idle timer and warnings, heartbeat, crash restarts, executing `pending_command`, clean stop and self-deallocation. Depends on: the adapter CLI, the state table, the events container, the Discord webhook URL, the VM's managed identity. See [ADR 0004](adr/0004-watchdog-local-agent-primary-function-safety-net.md).
- **Adapter** (a directory under `games/<name>/`: compose file, `adapter.sh`, `adapter.json`). Owns: everything game-specific. Depends on: Docker and the data disk. Contract in [contracts/adapter-interface.md](contracts/adapter-interface.md).
- **Terraform** (`infra/`). Owns: provisioning only. Never starts or stops the VM after apply. See [ADR 0006](adr/0006-infrastructure-as-code-terraform.md).

## Repository layout

```
.github/      CI workflows
agent/        systemd units and the boot-time update script for the VM
bonfire/      the Python package: core/ (shared), agent/, function/
function/     Azure Functions deployment root (function_app.py, host.json, requirements.txt)
infra/        Terraform: bootstrap/, envs/pilot/, modules/ (see ADR 0006)
games/        one adapter per game
docs/         this documentation
tests/        features/ (Gherkin), steps/ (pytest-bdd), fake-adapter/
scripts/      repository tooling: docs checker, Function build, command registration
```

## VM state machine

Four states. Table of every transition:

| From | To | Trigger | Actor | Lock |
|---|---|---|---|---|
| out | igniting | `/bonfire ignite` | Function | takes `lock_until = now + LOCK_TTL_MINUTES` (5 min); sets `session_id`, `session_started_at` |
| out | igniting | agent finds the VM running while the row says out (started outside Bonfire) | agent | takes lock; sets `session_id`, `session_started_at`; records `command/ignite` with actor `agent` |
| igniting | lit | adapter `is_ready` succeeds | agent | clears lock |
| igniting | lit (with `last_health = crashed`) | the adapter's `ready_timeout_minutes` elapsed without readiness | agent | clears lock |
| igniting | out | reconcile: lock expired and VM power state is deallocated | Function | none |
| igniting | extinguishing | boot failure: no heartbeat within `heartbeat_stale_minutes` of `state_since` | Function (safety-net timer) | takes lock; sets `session_ended_at`; deallocates directly; posts `watchdog_boot_failed` |
| lit | extinguishing | `/bonfire extinguish` (confirmed if players online) | Function | takes lock; sets `session_ended_at` |
| lit | extinguishing | idle timeout reached | agent | takes lock; sets `session_ended_at` |
| lit | extinguishing | safety net: session ceiling or missing heartbeat | Function | takes lock; sets `session_ended_at`; deallocates directly |
| extinguishing | (deallocating) | agent observes `extinguishing` on its check | agent | runs adapter `stop`, then deallocates the VM |
| extinguishing | out | VM power state observed deallocated | Function (handler after lock expiry, or safety-net timer) | clears lock; adds `session_ended_at - session_started_at` to `hours_this_month`; clears session fields |
| out | out | drift: VM power state running, no heartbeat for `heartbeat_stale_minutes` | Function timer deallocates | none |
| lit | lit | `/bonfire restart` (accepted only while `lit`; otherwise the status reply) | Function writes `pending_command = restart`; agent runs adapter `stop` then `start` and clears it | none |

Rules:

1. Only the actor in the table may make that transition. Anyone else that observes an inconsistent state reconciles as described in the two reconcile rows.
2. Every write to the state row is conditional on the ETag read moments before. A 412 means re-read and re-evaluate; never overwrite blindly.
3. Reconciliation. Whenever `vm_state` is `extinguishing`, and whenever it is `igniting` with `lock_until` in the past, a handler or the safety-net timer reads the VM power state before acting. Deallocated means `out` (adding the session hours). Running while `extinguishing` with an expired lock means the agent is presumed dead: the Function deallocates directly. Running while `igniting` with a heartbeat in the last `heartbeat_stale_minutes` means `lit`; running with no heartbeat at all for `heartbeat_stale_minutes` since `state_since` is a boot failure (row above). A member who runs `ignite` within a minute of a burn-out therefore either waits out the deallocation with `status_extinguishing` or, once the VM is off, proceeds normally.
4. Manual extinguish goes through the agent so the game saves cleanly. Only the safety net, which by definition has no working agent, deallocates without a clean stop.

## Sequences

**Ignite**

```mermaid
sequenceDiagram
    participant Player
    participant Discord
    participant Function
    participant Azure
    participant VM/agent
    participant Adapter
    participant State table

    Player->>Discord: /bonfire ignite
    Discord->>Function: POST interaction
    Function-->>Discord: deferred acknowledgement
    Function->>Function: enqueue interaction (worker continues)
    Function->>State table: read state row
    Function->>Function: reconcile (rule 3) if applicable
    alt vm_state is not out
        Function-->>Discord: edit reply with status message
    else vm_state is out
        Function->>State table: write igniting, state_since, session_id, session_started_at, lock_until (If-Match)
        Function->>Azure: start VM
        Function->>State table: record command/ignite event
        Function-->>Discord: edit reply to igniting message
        Azure->>VM/agent: boot; cloud-init starts Docker and agent timer
        VM/agent->>Adapter: install (if image missing), start
        loop each check
            VM/agent->>Adapter: is_ready
        end
        alt ready before ready_timeout_minutes
            VM/agent->>State table: write lit, clear lock, last_health = ok
            VM/agent->>Discord: post ready message (webhook)
            VM/agent->>State table: record vm/ready event (duration_ms)
        else ready_timeout_minutes elapses first
            VM/agent->>State table: write lit, last_health = crashed, clear lock
            VM/agent->>Discord: post ignite-failed message (webhook)
            VM/agent->>State table: record vm/ignite_failed event
        end
    end
```

1. Player runs `/bonfire ignite`; Discord POSTs the interaction to the Function.
2. Function validates the signature, puts the interaction on its queue and immediately responds with a deferred acknowledgement (in channel); a queue-triggered worker performs the following steps ([ADR 0008](adr/0008-function-ack-then-queue.md)).
3. Function reads the state row and reconciles when rule 3 applies. If `vm_state` is not `out`, it edits the reply with the status message and stops.
4. Function writes `vm_state = igniting`, `state_since`, `session_id`, `session_started_at`, `lock_until` with If-Match. On 412 it re-reads and returns to step 3.
5. Function calls Azure to start the VM, records a `command/ignite` event, and edits the reply to the igniting message.
6. The VM boots; cloud-init starts Docker and the agent timer. The agent runs adapter `install` (if the image is missing) and `start`.
7. Each check, the agent runs `is_ready`. On success it writes `vm_state = lit`, clears `lock_until`, writes `last_health = ok`, posts the ready message through the webhook, and records a `vm/ready` event with `duration_ms` since `session_started_at`.
8. If the adapter's `ready_timeout_minutes` (from `adapter.json`) pass first, the agent writes `vm_state = lit`, `last_health = crashed`, clears the lock, posts the ignite-failed message, and records `vm/ignite_failed`.

**Idle shutdown**

```mermaid
sequenceDiagram
    participant Player
    participant Discord
    participant Function
    participant Azure
    participant VM/agent
    participant Adapter
    participant State table

    loop every idle_check_interval minutes
        VM/agent->>Adapter: player_count, health
        VM/agent->>State table: write last_heartbeat, last_player_count, last_health
        VM/agent->>VM/agent: apply idle rules (PRD 7.3)
        VM/agent->>Discord: post warning/cancellation (webhook)
        VM/agent->>State table: record event
    end
    VM/agent->>State table: write extinguishing, session_ended_at, lock_until
    VM/agent->>Discord: post burned-out message (webhook)
    VM/agent->>State table: record watchdog/idle_shutdown event
    VM/agent->>Adapter: backup
    VM/agent->>Azure: upload backup (blob)
    VM/agent->>Adapter: stop (clean save within stop_grace_seconds)
    VM/agent->>Azure: deallocate VM (managed identity)
    Note over VM/agent: agent dies with the VM
    Function->>Azure: observe VM power state
    Function->>State table: write out; add session hours
```

1. Every `idle_check_interval` minutes the agent runs adapter `player_count` and `health`, then writes `last_heartbeat`, `last_player_count`, `last_health`.
2. It applies the idle rules from PRD 7.3 (warnings, cancellation, unknown handling). Each warning and cancellation is posted through the webhook and recorded as an event.
3. When the timeout is reached with a known zero count, the agent writes `vm_state = extinguishing`, `session_ended_at`, `lock_until`; posts the burned-out message; records `watchdog/idle_shutdown`.
4. The agent runs adapter `backup`, uploads the staging directory to the `backups` container, runs adapter `stop` (clean save within `stop_grace_seconds`), then calls Azure to deallocate the VM through its managed identity. The agent dies with the VM.
5. The next Function handler or safety-net tick observes the VM deallocated and writes `vm_state = out`, adding the session hours.

## Crash handling

Docker owns restarts: every adapter's compose file sets `restart: on-failure:3`, so a crashed game comes back without the agent's help, and a crash loop stops after three attempts. The agent only observes. On each check it compares the adapter's `health` with `last_health`: when it moves from `ok` to `degraded` or `crashed` it posts the `crash` message and records a `game/crash` event; when it reaches `crashed` (the container has exited and Docker has given up) it posts `crash_gave_up` and records `game/crash_gave_up`, once per streak. While the game is down `player_count` returns unknown, so the idle timer never fires; the session ends by `/bonfire extinguish`, `/bonfire restart`, or the session ceiling.

## Glossary

- **out**: VM deallocated.
- **igniting**: VM starting, game not yet ready.
- **lit**: game accepting connections, or VM up with the game crashed.
- **extinguishing**: clean stop and deallocation in progress.
- **ignite**: the command and act of starting.
- **extinguish**: the command and act of stopping.
- **burn out**: an idle-timeout extinguish.
- **keep it lit**: resetting the idle timer from Discord, v1.5.
- **adapter**: the per-game container plus CLI.
- **agent**: the on-VM service.
- **controller** (or **Function**): the Azure Function.
- **safety net**: the Function's timer that enforces the ceiling and heartbeat.
- **session**: from ignite to out, identified by `session_id`.

## Security notes

- Discord requests are accepted only with a valid Ed25519 signature over timestamp and body (details in [contracts/discord.md](contracts/discord.md)).
- The Function's identity holds Virtual Machine Contributor scoped to the one VM.
- The VM's managed identity may only deallocate itself.
- The bot token, webhook URL and game password live in Key Vault and reach code through references, never plain app settings.
- The NSG opens only the ports in the adapter's `adapter.json`, and the query port is never opened in v1.
