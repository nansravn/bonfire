# 0004. Watchdog: on-VM agent primary, Function safety net

**Status:** Accepted, amended 2026-09-12 (see Amendment)
**Date:** 2026-09-08

## Context

The VM must never stay allocated with zero players beyond the idle timeout, and must be extinguished even if the game or the whole VM hangs ([PRD](../prd.md) sections 3 and 6.4). Counting players needs the game's query protocol, which for Valheim is Steam A2S on UDP 2457. Querying it from outside the VM means opening the port to the internet and tolerating remote UDP flakiness.

## Decision

Two cooperating watchdogs:

- **The agent on the VM is primary.** A systemd timer runs every `idle_check_interval` minutes, asks the adapter for `player_count`, and drives the idle timer and warnings. After `idle_timeout_minutes` with zero players it stops the game cleanly and deallocates the VM through the VM's own managed identity.
- **The Function is the safety net.** A timer trigger every 15 minutes (the `WATCHDOG_INTERVAL_MINUTES` constant) deallocates the VM when it has been allocated longer than `max_session_hours` or the agent has not written a heartbeat for `heartbeat_stale_minutes`. It never reads the player count.

The state table is the contract between them: the agent writes a heartbeat and the last player count on every check; the Function acts only when the agent is silent or the ceiling is exceeded.

## Alternatives considered

### Function-only, polling A2S over the internet

Rejected. Requires opening the query port publicly and makes shutdown decisions on a lossy remote UDP query. A false zero would disconnect players.

### Agent-only

Rejected. A hung VM or a crashed agent would stay allocated indefinitely.

## Consequences

- Two code paths must be tested: the agent's idle logic and the Function's ceiling and heartbeat checks. Feature files `idle-shutdown.feature` and `watchdog.feature` cover them.
- The "unknown never extinguishes" rule applies to the agent only. The safety net's ceiling is absolute and can disconnect players, which is why it is announced one hour ahead; PRD section 11 counts any safety-net trigger as an agent bug to fix.
- The agent needs a managed identity with permission to deallocate its own VM, and the Function needs the same permission on that VM (Terraform `iam` module).
- The query port stays closed to the internet in v1; only the agent queries, on the loopback address.

## Amendment (2026-09-12): what the first real sessions showed

Both watchdogs ran end to end on the pilot on 2026-09-12; the numbers below come from the `events` container.

- **The agent's timer is exact.** With nobody connected, `idle_since` was set at 05:40:20 and the burn-out fired at 06:25:20, the 45-minute timeout to the second. The warnings arrived 12 and 40 seconds after their thresholds (the check runs once a minute), the backup uploaded 44 files, the adapter stopped the game cleanly, and the VM was deallocated by the agent itself. The Function's next 15-minute tick closed the session and added the hours.
- **The safety net's reaction time is `heartbeat_stale_minutes` plus up to one watchdog interval.** With the agent's timer stopped at 13:41 (last heartbeat 13:40:22), the 14:00 tick correctly did nothing (19 min 38 s stale, under 20) and the 14:15 tick deallocated the VM: 35 minutes after the last heartbeat. That is the bound the PRD's "zero shutdowns with a player connected" metric has to live with, since the ceiling and heartbeat rules ignore the player count by design.
- **A VM started outside Bonfire is adopted, not killed.** The design's drift rule would have deallocated a VM started with `az vm start` twenty minutes later. The agent now treats a row that says `out` while it is running as an ignite by actor `agent` (event detail `adopted manual start`), so debugging starts and portal starts behave like `/bonfire ignite`. This is the one transition the agent takes that the original table reserved for the Function; the table in architecture.md records it.
- **The agent's boot path is the fragile part, and the safety net covered it.** Two boot bugs were found the same day: a systemd drop-in that reset every monotonic timer including the boot trigger, so the agent never ran after boot; and the update script replacing itself mid-run, so a fix to that script only took effect one boot later. In the affected session the VM sat `igniting` with no heartbeat until a manual tick; had nobody intervened, the boot-failure rule would have deallocated it at 20 minutes and announced it. Consequence: every change to `agent/` needs the end-to-end check "first heartbeat within two minutes of boot", not only the unit level.
- **Open refinement.** Reconciliation marks an `igniting` row `lit` when the lock has expired and the agent has a fresh heartbeat (architecture rule 3). On a slow boot this pre-empts the agent's own `ready` message and metric. The rule only matters after five minutes of boot, and the warm boot takes about a minute, so it is left as a Phase 1.5 question rather than changed now.
