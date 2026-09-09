# Adapter interface

An adapter is everything Bonfire knows about one game. The core never inspects a game; it only calls this interface. Adapters live in `games/<name>/`.

## Files

| File | Purpose |
|---|---|
| `docker-compose.yml` | The game server image and its configuration. Must mount `${BONFIRE_DATA_DIR}` for saves. |
| `adapter.sh` | Executable implementing the subcommands below. Bash; may call other tools it installs. |
| `adapter.json` | Game metadata read by Terraform and the agent. Shape: `{"ports": [{"port": 2456, "proto": "udp"}], "stop_grace_seconds": 60, "ready_timeout_minutes": 10}`. `proto` is `udp` or `tcp`; the first port is the one players connect to. Query ports the adapter itself uses (Valheim's 2457) are not listed: they stay loopback-only. |
| `README.md` | Game-specific notes: image, known issues, how player count is obtained. |

## Environment

The agent sets these before every invocation and runs `adapter.sh` with `BONFIRE_ADAPTER_DIR` as the working directory.

| Variable | Meaning | Example |
|---|---|---|
| `BONFIRE_GAME` | Adapter name | `valheim` |
| `BONFIRE_ADAPTER_DIR` | Absolute path of `games/<name>/` | `/opt/bonfire/games/valheim` |
| `BONFIRE_DATA_DIR` | Persistent save directory on the data disk | `/data/valheim` |
| `BONFIRE_BACKUP_DIR` | Staging directory `backup` copies into | `/data/backup-staging/valheim` |
| `BONFIRE_STOP_GRACE_SECONDS` | Seconds `stop` may wait for a clean save; the agent copies it from `adapter.json` | `60` |
| `BONFIRE_PUBLIC_ADDRESS` | Address players connect to | `191.0.2.10:2456` |

Game secrets (server password and the like) are provided in `/etc/bonfire/<name>.env`, which the agent sources before invoking the adapter. Its variable names are the adapter's own; the file is written at boot from Key Vault.

## Subcommands

Every subcommand writes diagnostics to stderr only. Stdout carries only the values below. Any exit code not listed is a failure.

| Subcommand | Purpose | Stdout | Exit codes | Timeout | Idempotent |
|---|---|---|---|---|---|
| `install` | Pull the image; update server binaries | none | 0 done, 1 failed | 15 min | yes |
| `start` | Bring the server up (`docker compose up -d`). Returns when the container is running, not when the game is ready. | none | 0 started, 1 failed | 2 min | yes |
| `stop` | Stop with a clean save. Must wait up to `BONFIRE_STOP_GRACE_SECONDS` for the save before forcing. | none | 0 stopped, 1 failed | grace + 60 s | yes |
| `is_ready` | Report whether the game accepts connections | none | 0 ready, 1 not ready, 2 cannot tell | 10 s | yes |
| `player_count` | Report connected players | one line: a non-negative integer, or `unknown` | 0 printed a value, 1 failed | 10 s | yes |
| `health` | Report process health: `ok` when the container is running; `degraded` when Docker is restarting it or has restarted it since the previous call; `crashed` when it has exited and Docker no longer restarts it | one line: `ok`, `degraded` or `crashed` | 0 printed a value, 1 failed | 10 s | yes |
| `backup` | Copy saves into `BONFIRE_BACKUP_DIR` | none | 0 copied, 1 failed | 5 min | yes |

Timeouts are enforced by the caller. A timed-out `player_count` or `health` is treated as `unknown`; a timed-out anything else is a failure.

## Rules for callers

1. **`unknown` never extinguishes.** A caller that receives `unknown` from `player_count`, a non-zero exit, or a timeout must not start, advance or fire the idle timer.
2. `start` then `is_ready` in a loop is the readiness protocol. `start` alone proves nothing.
3. `stop` must be called before deallocating whenever the agent is alive. Deallocating without `stop` loses unsaved progress.
4. Callers pass no arguments beyond the subcommand. Configuration reaches the adapter only through the environment.
5. Docker owns crash restarts. The compose file sets `restart: on-failure:3` on the game service; the agent never calls `start` in response to `health`, only on ignite or `/bonfire restart`.

## Conformance

A new adapter conforms when `tests/features/adapter-<name>.feature` passes at the `@contract` level using the real image on a Docker host, and at the `@e2e` level on the pilot VM. The Valheim file is the reference:
[adapter-valheim.feature](../../tests/features/adapter-valheim.feature).
