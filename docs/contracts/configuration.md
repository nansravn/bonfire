# Configuration

Every tunable is a Terraform variable. Terraform writes it to the Function's app settings and to the agent's environment file `/etc/bonfire/bonfire.env` under the same uppercase name. Lists become comma-separated strings.

## Variables

| Terraform variable | Setting / env name | Type | Default | Validation |
|---|---|---|---|---|
| `game` | `BONFIRE_GAME` | string | `valheim` | `games/<game>/adapter.sh` and `adapter.json` exist |
| `idle_timeout_minutes` | `BONFIRE_IDLE_TIMEOUT_MINUTES` | number | 45 | > `idle_check_interval` |
| `idle_warning_minutes` | `BONFIRE_IDLE_WARNING_MINUTES` | list(number) → `15,5` | `[15, 5]` | strictly descending; each < `idle_timeout_minutes` and > `idle_check_interval` |
| `idle_check_interval` | `BONFIRE_IDLE_CHECK_INTERVAL` | number (minutes) | 1 | ≥ 1 |
| `max_session_hours` | `BONFIRE_MAX_SESSION_HOURS` | number | 12 | ≥ 2, so the ceiling warning at `max_session_hours − 1` is after ignite |
| `heartbeat_stale_minutes` | `BONFIRE_HEARTBEAT_STALE_MINUTES` | number | 20 | ≥ 3 × `idle_check_interval`; > 15 (the watchdog interval) |
| `vm_hourly_usd` | `BONFIRE_VM_HOURLY_USD` | number | 0.30 (D4as v6 rate) | > 0 |
| `fixed_monthly_usd` | `BONFIRE_FIXED_MONTHLY_USD` | number | 18 | ≥ 0 |
| `discord_guild_id` | `DISCORD_GUILD_ID` | string | none | used by `scripts/register-commands.py` only |

The first five are the timings PRD section 6.7 names plus the game selector. `heartbeat_stale_minutes` is the value PRD 6.4 states in prose. The two cost rates serve `/bonfire cost` (PRD section 10).

## Constants

Fixed in code and documented here; changing one is a code change, not a deploy setting.

| Constant | Value | Where it applies |
|---|---|---|
| `WATCHDOG_INTERVAL_MINUTES` | 15 | The safety-net timer trigger's schedule |
| `UNKNOWN_ALERT_MINUTES` | 60 | The agent posts `unknown_alert` after this long of `unknown` |
| `LOCK_TTL_MINUTES` | 5 | `lock_until = now + 5 min` on every transition into `igniting` or `extinguishing` |

## Per-adapter settings

Two values differ per game and live in the adapter's `adapter.json` (see [adapter-interface.md](adapter-interface.md)), not in Terraform. The agent reads them at startup and exports `BONFIRE_STOP_GRACE_SECONDS` to the adapter.

| Key in `adapter.json` | Valheim value | Meaning |
|---|---|---|
| `stop_grace_seconds` | 60 | How long `stop` may wait for a clean save |
| `ready_timeout_minutes` | 10 | How long the agent waits for `is_ready` after `start` before declaring ignite failed; Valheim's first world generation can take several minutes |

## Derived settings

Terraform computes these from resources it creates; they are not variables.

| Setting / env name | Value | Read by |
|---|---|---|
| `BONFIRE_PUBLIC_ADDRESS` | `<static ip>:<first port in adapter.json>` | agent, Function |
| `BONFIRE_VM_RESOURCE_ID` | Resource ID of the game VM | agent, Function |
| `BONFIRE_STATE_TABLE_ENDPOINT` | Table service endpoint of the controller storage account | agent, Function |
| `BONFIRE_EVENTS_ENDPOINT` | Cosmos account endpoint | agent, Function |
| `DISCORD_APPLICATION_ID` | Discord application ID (variable, not secret) | Function |
| `DISCORD_PUBLIC_KEY` | Discord interaction public key (variable, not secret) | Function |
| `BONFIRE_GIT_REF` | the `bonfire_git_ref` variable | agent (`bonfire-update`) |
| `BONFIRE_BACKUP_ACCOUNT_URL` | Blob endpoint of the backup storage account | agent |

## Secrets

Stored in Key Vault. The Function reads them as Key Vault references in app settings; the agent fetches them at boot with its managed identity and writes `/etc/bonfire/bonfire.env` and `/etc/bonfire/<game>.env` with mode 0600.

| Key Vault secret | Env name | Read by |
|---|---|---|
| `discord-bot-token` | `DISCORD_BOT_TOKEN` | Function. Stored in Phase 1 for `scripts/register-commands.py`; no Function setting references it until Phase 1.5. |
| `discord-webhook-url` | `DISCORD_WEBHOOK_URL` | agent |
| `<game>-server-password` | adapter-defined | adapter, via `/etc/bonfire/<game>.env` |

## Validation

Terraform enforces the Validation column with `validation` blocks. The agent re-validates on startup and refuses to run on an invalid file, logging which rule failed, so a bad deploy fails loudly rather than shutting a server down at the wrong time.
