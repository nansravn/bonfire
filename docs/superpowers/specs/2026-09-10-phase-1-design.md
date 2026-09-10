# Phase 1 — Agent, Function, Discord commands, state and events: design

**Date:** 2026-09-10
**Status:** Approved in brainstorming; awaiting written review
**Inputs:** [prd.md](../../prd.md) section 14 (Phase 1), [architecture.md](../../architecture.md), the four contracts under [contracts/](../../contracts/adapter-interface.md), [ADR 0003](../../adr/0003-controller-azure-function-interactions-endpoint.md), [ADR 0004](../../adr/0004-watchdog-local-agent-primary-function-safety-net.md), [ADR 0005](../../adr/0005-storage-table-cosmos-keyvault-blob.md), [ADR 0007](../../adr/0007-test-runner-pytest-bdd.md), [testing.md](../../testing.md), the six unit feature files under `tests/features/`, and section 11 of the [Phase 0 spec](2026-09-09-phase-0-design.md).

## 1. Purpose and scope

Phase 1 makes Bonfire usable from Discord: any guild member ignites, checks, extinguishes and asks the cost; the on-VM agent marks readiness, drives the idle timer and warnings, backs up and deallocates; the Function's safety net enforces the ceiling and heartbeat and reconciles the state row. Both write to the state table and the events container. At the end of the phase the nightly auto-deallocate backstop is removed.

**In scope:** the `bonfire` Python package (core, agent, function); systemd units and cloud-init changes; Terraform modules `controller` and `data`, IAM and secrets additions, root variables and outputs; the Function deployment build script; the command registration script; the fake adapter and step definitions for the six unit feature files; direct tests for the Function's HTTP layer; CI for unit tests and the build; the `bonfire-update` boot unit; backup upload on extinguish; `/bonfire cost`; removal of the nightly shutdown schedule; ADR 0008; document amendments listed in section 9.

**Out of scope:** `/bonfire restart` and the keep-it-lit button (Phase 1.5); Terraform apply from CI with OIDC; agent logs shipped to Log Analytics (Phase 3); crossplay support; a second adapter; moving the data disk to its own resource group.

## 2. Decisions taken in brainstorming

| Topic | Decision | Cost if wrong |
|---|---|---|
| Language | Python 3.12 for the agent, the Function, the fakes and the tests, in one package. Node would not fix the cold-start risk, and one language shares the A2S helper, the fakes and the runner from ADR 0007. | Rewrite of about 1,500 lines of Function code; no data or infrastructure change. |
| Player counting | Steam-only. A2S on loopback is primary (proven in Phase 0); the log fallback stays as the safety layer; crossplay is documented as unsupported in v1. | A console player cannot join until a later adapter change. |
| Scope extras | In: safety-net timer, `cost`, backup upload on extinguish, removal of the nightly shutdown. Out: `restart`, CI apply, agent log shipping. | A crashed game during the pilot is restarted over SSH; Terraform keeps running from the owner's machine; agent debugging means `journalctl` on the VM. |
| Agent delivery | Pull on every boot: a `bonfire-update` unit checks out `bonfire_git_ref` (default `main`) and reinstalls the package before the game and agent units start. Pin to a tag with one apply when real players arrive. | A bad merge breaks ignite until the next merge; the safety net bounds the damage to 20 minutes of VM time. |
| Function work after the ack | The HTTP trigger verifies, answers PING, enqueues and defers; a queue-triggered worker does the work and edits the reply (ADR 0008). | One extra function and a queue, free at this volume. |
| Agent shape | A systemd timer runs a short-lived check every `idle_check_interval` minutes; all state lives in the row. While `igniting`, one run polls `is_ready` every 10 s for up to 50 s. | Wrapping `run_check` in a loop turns it into a daemon later. |
| Code sharing | One package `bonfire/` at the repository root; the VM installs it into the venv; a script stages a copy for the Function zip. | A 20-line build script; copy the package out if the Function must become independent. |
| Compute calls | Three REST calls (start, deallocate, instance view) with an `azure-identity` token; no `azure-mgmt-compute`. Table and Cosmos use their data-plane SDKs with managed identity. | Swap the module for the SDK. |
| Function plan | Classic Linux consumption (Y1). Flex Consumption is the fallback if cold starts show in the e2e run. | Change the plan resource. |
| Bot token | Stored in Key Vault now (the registration script reads it; Phase 1.5 needs it) but referenced by no Function setting in Phase 1. | None. |
| Manual VM start | The agent adopts a session when it finds the row `out`: it writes `igniting` with fresh session fields, actor `agent`. | A manual start is treated as an ignite; the alternative was the drift rule deallocating it after 20 minutes. |

## 3. Repository layout after Phase 1

```
pyproject.toml              package `bonfire`, extras: agent, function, test
bonfire/
  __init__.py
  core/
    config.py               reads BONFIRE_* and DISCORD_* env; validates configuration.md rules
    state.py                StateRow dataclass; Table client; conditional write (412 -> re-read)
    events.py               Cosmos events writer
    compute.py              start / deallocate / power_state via REST + azure-identity
    discord.py              Ed25519 verification, message catalog, webhook post, reply edit
    clock.py                injectable now()
  agent/
    __init__.py
    check.py                run_check(clients, now): the per-tick decision
    __main__.py             python -m bonfire.agent: load env, build real clients, run_check
  function/
    __init__.py
    interactions.py         HTTP trigger logic: verify, PING, enqueue, defer
    worker.py               queue worker: ignite, extinguish, check, cost, buttons
    watchdog.py             safety-net tick
    reconcile.py            reconcile(row, power_state, now) shared by worker and watchdog
function/                   deployment root: function_app.py, host.json, requirements.txt
agent/systemd/              bonfire-update.service, bonfire-agent.service, bonfire-agent.timer
scripts/
  build-function.sh         stages function/ + bonfire/ into dist/function
  register-commands.py      PUT the /bonfire command tree to the guild
tests/
  fake-adapter/adapter.sh, adapter.json
  steps/fakes.py            fake row, compute, webhook, reply editor, events, signer
  steps/common_steps.py     step phrases shared by the six unit modules
  steps/test_ignite.py, test_extinguish.py, test_check.py, test_idle_shutdown.py,
        test_concurrency.py, test_watchdog.py, test_interactions_http.py
infra/modules/controller/   function app, plan, storage account, table, queue, app insights
infra/modules/data/         cosmos serverless, database, container
docs/adr/0008-function-ack-then-queue.md
```

`dist/` is gitignored. `tests/steps/conftest.py` keeps the contract fixtures and gains nothing that unit tests need; unit fixtures live in `fakes.py`.

## 4. Delivery

### 4.1 To the VM

Cloud-init changes once for Phase 1, which replaces the VM (data disk and public IP survive). It writes:

- `/etc/bonfire/bonfire.env` (0600) with the Phase 0 adapter variables plus every tunable and derived value from [configuration.md](../../contracts/configuration.md), `BONFIRE_GIT_REF`, and `DISCORD_WEBHOOK_URL` fetched from Key Vault at boot with `bonfire-fetch-secret` the way the game password is. The contract's file name changes from `agent.env` to `bonfire.env`.
- `bonfire-update.service` itself, the one unit that must exist before the checkout is current. It copies all three units from `agent/systemd/` on every boot, so unit changes also arrive by pull.

Boot order: `bonfire-update.service` (oneshot, after network-online and `data.mount`): `git -C /opt/bonfire fetch`, `git checkout $BONFIRE_GIT_REF`, `git pull --ff-only` when the ref is a branch, `/opt/bonfire/venv/bin/pip install --quiet /opt/bonfire[agent]`, copy units to `/etc/systemd/system/`, `systemctl daemon-reload`. Then `bonfire-game.service` (unchanged: adapter `start` on boot, `stop` on shutdown). Then `bonfire-agent.timer`: `OnBootSec=30s`, `OnUnitActiveSec=<idle_check_interval>min`, `AccuracySec=5s`, driving `bonfire-agent.service` (oneshot, `EnvironmentFile=/etc/bonfire/bonfire.env`, `ExecStart=/opt/bonfire/venv/bin/python -m bonfire.agent`, `TimeoutStartSec=240`). If `bonfire-update` fails, the game and agent units still start from the previous checkout; the failure is visible in journald and, because the agent still heartbeats, does not trigger the safety net.

### 4.2 To Azure

`scripts/build-function.sh` creates `dist/function/` containing `function/function_app.py`, `function/host.json`, `function/requirements.txt` and a copy of `bonfire/`. Terraform's `archive_file` zips that directory and `azurerm_linux_function_app` deploys it through `zip_deploy_file` with `SCM_DO_BUILD_DURING_DEPLOYMENT=true` and `ENABLE_ORYX_BUILD=true`, so dependencies are built remotely. The build script runs before `terraform plan`; CI runs it to prove staging works. `requirements.txt` pins `azure-functions`, `azure-identity`, `azure-data-tables`, `azure-cosmos`, `cryptography`, `requests`.

`scripts/register-commands.py` reads `DISCORD_APPLICATION_ID`, `DISCORD_GUILD_ID` and the bot token (from `az keyvault secret show` or the environment) and PUTs the guild command tree with six subcommands: `ignite`, `start`, `extinguish`, `stop`, `check`, `cost`, with the description strings from [discord.md](../../contracts/discord.md). `restart` is registered in Phase 1.5.

## 5. Terraform

### 5.1 Module `controller`

- Storage account `stbonfirectl<suffix>` (Standard_LRS, TLS 1.2), table `state`, queue `interactions`. The host connection `AzureWebJobsStorage` is identity-based (`storage_uses_managed_identity`); shared-key access stays enabled because zip deployment uses it. If identity-based host storage proves unsupported for zip deploy on Y1 Linux, the host falls back to the account key and the application code keeps using identity; the plan records which.
- Log Analytics workspace `log-bonfire` (PerGB2018, 30-day retention) and Application Insights `appi-bonfire` (workspace-based, sampling 20%).
- Service plan `asp-bonfire` (Linux, `Y1`).
- Function app `func-bonfire-<suffix>`: Python 3.12, system-assigned identity, HTTPS only, `AzureWebJobsStorage__accountName` pointing at the account (identity-based host storage), `zip_deploy_file` from the archive, remote-build settings, `WEBSITE_TIME_ZONE` unset (all timestamps UTC).
- App settings: every `BONFIRE_*` tunable and derived value from configuration.md, `DISCORD_APPLICATION_ID`, `DISCORD_PUBLIC_KEY`, `DISCORD_WEBHOOK_URL` as a Key Vault reference.
- Outputs: `function_url` (`https://<host>/api/interactions`), `state_table_endpoint`, `storage_account_id`, `principal_id`.

### 5.2 Module `data`

Cosmos DB account `cosmos-bonfire-<suffix>` with `EnableServerless`, session consistency, local authentication disabled, one region. SQL database `bonfire`, container `events`, partition key `/month`, default TTL 7776000. Outputs: `endpoint`, `account_id`.

### 5.3 IAM additions (module `iam`)

| Principal | Role | Scope |
|---|---|---|
| Function identity | custom `Bonfire VM Control`: `virtualMachines/read`, `instanceView/read`, `start/action`, `deallocate/action` | the VM |
| Function identity | `Storage Blob Data Owner`, `Storage Queue Data Contributor`, `Storage Table Data Contributor` | controller storage account |
| Function identity | Cosmos DB Built-in Data Contributor (`azurerm_cosmosdb_sql_role_assignment`) | Cosmos account |
| Function identity | `Key Vault Secrets User` | Key Vault |
| VM identity | `Storage Table Data Contributor` | controller storage account |
| VM identity | Cosmos DB Built-in Data Contributor | Cosmos account |

The VM's existing self-deallocate role and blob role are unchanged. Role assignments propagate slowly; a `time_sleep` of 90 s follows them before the Function app resource, as in Phase 0.

### 5.4 Module `secrets` additions

Secrets `discord-webhook-url` and `discord-bot-token` from sensitive root variables.

### 5.5 Root module

New variables, with the validation blocks from configuration.md: `idle_timeout_minutes` (45), `idle_warning_minutes` ([15, 5]), `idle_check_interval` (1), `max_session_hours` (12), `heartbeat_stale_minutes` (20), `vm_hourly_usd` (0.30, the D4as v6 rate), `fixed_monthly_usd` (18); `discord_application_id`, `discord_public_key`, `discord_guild_id`, `discord_bot_token` (sensitive), `discord_webhook_url` (sensitive). New outputs: `function_url`, `cosmos_endpoint`, `state_table_endpoint`. `vm_size` default becomes `Standard_D4as_v6`, matching the amendment to ADR 0002.

The nightly shutdown schedule (`azurerm_dev_test_global_vm_shutdown_schedule.nightly`) stays until the final task of the phase removes it, together with the `shutdown_*` variables.

Added monthly cost: under US$2 (Application Insights ingestion is the only meaningful line; Cosmos serverless, the queue, the table and Y1 executions are at or near zero for this volume).

## 6. The Function

Three functions in `function_app.py`, each a thin wrapper that builds real clients and calls a pure handler in `bonfire.function`.

### 6.1 `interactions` (HTTP trigger, anonymous auth, route `interactions`)

1. Read `X-Signature-Ed25519`, `X-Signature-Timestamp` and the raw body; verify with `cryptography` against `DISCORD_PUBLIC_KEY`; missing or invalid gives HTTP 401 with an empty body.
2. Type 1: respond `{"type": 1}`.
3. Types 2 and 3: put `{"received_at": <iso>, "interaction": <raw json>}` on the `interactions` queue through the output binding, then respond type 5 (commands) or type 6 (buttons).
4. Anything else: HTTP 400.

Imports are limited to `azure.functions`, `cryptography`, `json` and `bonfire.function.interactions` so a cold start stays well under the deadline.

### 6.2 `worker` (queue trigger on `interactions`)

Dispatch on the subcommand name (aliases map to the same handler) or on the `custom_id` prefix. Each handler:

1. Read the row; call `reconcile` (section 6.4) when rule 3 applies and persist its result.
2. Decide the transition from the state machine in architecture.md.
3. Write the row with If-Match. On 412: re-read and return to step 1, at most three times; after that reply with the current status and record the event with `ok` false and detail `etag conflict`.
4. Call compute when the transition requires it (ignite: start).
5. Record the `command/*` event: actor is the Discord user ID, `duration_ms` is now minus `received_at`, `player_count` from the row for extinguish, `ok`.
6. Edit the original reply through `PATCH /webhooks/{application_id}/{interaction_token}/messages/@original`. A failed edit (expired token, Discord error) is logged and recorded in the event detail; the state change stands because Azure has already acted.

Handlers:

- **ignite / start.** `out` to `igniting`: `state_since`, new `session_id`, `session_started_at`, `lock_until = now + 5 min`, `ceiling_warned = false`; start the VM; reply `igniting`. Any other state: the status reply, no compute call, event with detail `already <state>`.
- **extinguish / stop.** `lit` with `last_player_count` 0 or -1: `lit` to `extinguishing` with `session_ended_at` and the lock; reply `extinguished_manual`. An unknown count does not trigger confirmation because nobody can be shown to be online; the event's `player_count` is null. `lit` with `last_player_count` > 0: reply `confirm_extinguish` with the two buttons, row unchanged, no event yet. Other states: the status reply.
- **Buttons `extinguish:confirm:<user>:<ts>` and `extinguish:cancel:<user>:<ts>`.** Ownership, 120-second expiry and outcomes as in discord.md. Confirm re-reads the row and only transitions when still `lit`; otherwise it edits to the status message. The confirmed transition records `command/extinguish` with the confirming user as actor and the row's `player_count`.
- **check.** Reconcile, then the status selection order from discord.md; `{r}` is `idle_timeout_minutes − (now − idle_since)` rounded down to whole minutes, or `idle_timeout_minutes` when `idle_since` is null.
- **cost.** `hours_this_month` when `hours_month` is the current month, else 0; `{vm} = hours × vm_hourly_usd` to two decimals; `{fixed} = fixed_monthly_usd`.

### 6.3 `watchdog` (timer trigger, NCRONTAB `0 */15 * * * *`)

One tick, in order, each step writing the row with If-Match and abandoning the tick on 412 (the next tick retries):

1. Read the row. If `vm_state` is `extinguishing`, or `igniting` with `lock_until` in the past, or `out` with a `last_heartbeat`, read the VM power state and apply `reconcile`.
2. `lit` and `session_started_at` older than `max_session_hours − 1` hours and `ceiling_warned` false: post `watchdog_ceiling_warning`, set `ceiling_warned`, record `watchdog/ceiling_warning`.
3. `lit` and `session_started_at` older than `max_session_hours`: write `extinguishing` with `session_ended_at` and the lock, deallocate, post `watchdog_ceiling`, record `watchdog/ceiling` with the row's player count.
4. `lit` and `last_heartbeat` older than `heartbeat_stale_minutes`: same transition, post `watchdog_heartbeat`, record `watchdog/heartbeat_missing`. (`lit` is only ever written after a heartbeat, so the field is never null here.)
5. `igniting`, `last_heartbeat` null, `state_since` older than `heartbeat_stale_minutes`, VM running: same transition, post `watchdog_boot_failed`, record `watchdog/boot_failed`.
6. `out`, VM running, `last_heartbeat` older than `heartbeat_stale_minutes` (drift): deallocate, post `watchdog_heartbeat`, record `watchdog/heartbeat_missing`; the row is not changed.

The tick never reads the player count. The 15-minute cadence also keeps the Function app warm.

### 6.4 `reconcile(row, power_state, now)`

A pure function returning the corrected row, the events to record, and a `deallocate` flag the caller acts on; used by the worker (before deciding) and the watchdog (step 1):

- `extinguishing` and deallocated: `out`; `hours_this_month += (session_ended_at − session_started_at)` in hours, after resetting to 0 when `hours_month` is not the month of `now`; clear session fields, idle fields, `lock_until`; record `vm/deallocated` with actor `function`.
- `extinguishing`, running, lock expired: the agent is presumed dead; `deallocate` flag set, record `vm/deallocated` with `ok` false and detail `agent silent; function deallocated`; row unchanged (the next tick sees deallocated and writes `out`).
- `igniting`, lock expired, deallocated: `out`, session fields cleared, no hours added.
- `igniting`, lock expired, running, `last_heartbeat` within `heartbeat_stale_minutes`: `lit`, clear `lock_until`.
- Anything else: unchanged.

## 7. The agent

`python -m bonfire.agent` runs once per timer tick. It loads `/etc/bonfire/bonfire.env`, validates every rule in configuration.md and exits 2 naming the failed rule if any fails, builds the real clients (Table, Cosmos, compute, webhook, blob, the adapter runner with the contract timeouts), and calls `run_check(clients, now)`.

`run_check`, in order:

1. **Read the row.** If `vm_state` is `out`, adopt the session: write `igniting`, `state_since = now`, new `session_id`, `session_started_at = now`, `lock_until = now + 5 min`, `ceiling_warned = false`; record `command/ignite` with actor `agent` and detail `adopted manual start`. Continue as `igniting`.
2. **`extinguishing`:** run adapter `backup`; upload every file under `BONFIRE_BACKUP_DIR` to the `backups` container under `<session_id>/<timestamp>/`, then delete the staging copy; record `vm/backup` with `ok` and the file count in detail. Run adapter `stop`. Deallocate through the VM identity. Backup or upload failure is recorded and logged but never blocks `stop`; a `stop` failure is recorded and the deallocate still proceeds, since the alternative is a VM that never goes out.
3. **`igniting`:** write `last_heartbeat`. Poll `is_ready` every 10 s until success or until 50 s have passed. On success: `lit`, `state_since`, clear `lock_until`, `last_health = ok`; post `ready`; record `vm/ready` with `duration_ms = now − session_started_at`; then perform step 4 in the same tick so the first count and heartbeat are in the row before anyone runs `check`. If `now − state_since ≥ ready_timeout_minutes` and still not ready: `lit`, `last_health = crashed`, clear the lock; post `ignite_failed`; record `vm/ignite_failed` with `ok` false. Otherwise exit; the next tick continues.
4. **`lit`:**
   1. If `pending_command` is set, ignore it in Phase 1 (log once); Phase 1.5 implements `restart`.
   2. Run `player_count` and `health` with the contract timeouts. Timeouts and non-zero exits count as `unknown`.
   3. Write `last_heartbeat = now`, `last_player_count` (-1 for unknown), `last_health` (`unknown` on failure).
   4. Crash detection against the previous `last_health`: `ok` to `degraded` or `crashed` posts `crash` and records `game/crash`; reaching `crashed` from `degraded` posts `crash_gave_up` and records `game/crash_gave_up`; each once per streak. The agent never calls `start` here.
   5. Idle rules from PRD 7.3 and `idle-shutdown.feature`: the unknown streak (`unknown_since`, one `unknown_alert` after `UNKNOWN_ALERT_MINUTES`, reset on a known count); the idle timer (`idle_since`, warnings in descending order once each, `idle_cancelled` when a player appears after any warning, silent reset otherwise); burn-out when `now − idle_since ≥ idle_timeout_minutes` with a known zero: write `extinguishing`, `session_ended_at`, the lock, clear idle fields; post `idle_shutdown`; record `watchdog/idle_shutdown` with detail `idle <n> min; warnings <list> posted`; then perform step 2 in the same tick.

`health` is consulted only in steps 3 and 4, where the game is expected to be running, so the adapter's `crashed` after a clean `stop` is never misread. Every write is If-Match; a 412 re-reads and restarts the tick, at most three times, then exits 0 and leaves it to the next tick. Table or Cosmos unreachable: log, exit 1 without touching the adapter. Webhook unreachable: log; the state change stands. Logging goes to stderr, captured by journald under `bonfire-agent`.

## 8. Tests

### 8.1 Unit level

`tests/steps/fakes.py` provides: `FakeStateTable` (one entity, ETag increments on write, stale ETag raises the same error type as `azure.data.tables`); `FakeCompute` (records `start` and `deallocate`, settable `power_state`); `FakeWebhook` and `FakeReplies` (record posted and edited messages by catalog ID and placeholders); `FakeEvents` (a list); `Signer` (a test Ed25519 key pair and a function that signs a payload the way Discord does); and `FakeClock`.

`tests/fake-adapter/adapter.sh` implements the seven subcommands: each reads `FAKE_<SUBCOMMAND>` (`FAKE_PLAYER_COUNT=unknown`, `FAKE_IS_READY=1`, `FAKE_HEALTH=degraded`, `FAKE_STOP_RC=1`) and appends `<subcommand>` to `$FAKE_LOG`. Its `adapter.json` declares `ready_timeout_minutes` 5 and `stop_grace_seconds` 1, as `ignite.feature` requires.

One step module per feature file; step phrases are shared through `tests/steps/common_steps.py` so "the bonfire is lit with 3 players online", "the reply is message X with n 3", "a VM deallocate is requested by the agent exactly once" and the rest are defined once. Time is driven by `FakeClock`, so "at 20:00" and "13 minutes ago" are exact. Every scenario in the six feature files is bound; `pytest -m unit tests/` runs them without Docker or Azure.

### 8.2 Function HTTP layer

`tests/steps/test_interactions_http.py`, plain pytest: missing signature gives 401; wrong signature gives 401; PING gives `{"type": 1}`; a command gives type 5 and exactly one queue message carrying the raw interaction; a button gives type 6; an unknown type gives 400.

### 8.3 CI

`ci.yml` gains: `pip install -e .[test]`, `pytest -m unit tests/`, `scripts/build-function.sh` (proves staging), and `terraform validate` now covers the new modules. `shellcheck` covers `agent/systemd` helpers and `scripts/*.sh`. The `adapter-contract` workflow is unchanged.

### 8.4 End-to-end (manual, results recorded in section 11)

1. Ignite from Discord: `/bonfire ignite` to the `ready` message, with the time between them.
2. Check in every reachable state: out, igniting, lit with 0 and with 1 player, extinguishing.
3. Extinguish with nobody online; extinguish with one connected player to see the confirmation, then confirm.
4. Burn-out: with `idle_timeout_minutes` temporarily 5 and `idle_warning_minutes` `3,1`, both warnings arrive and the VM deallocates; then the defaults are restored.
5. Safety net: stop `bonfire-agent.timer` on the VM, wait 20 minutes, observe `watchdog_heartbeat` and the deallocation. This run justifies removing the nightly shutdown.

## 9. Amendments to existing documents

- **architecture.md**: the adopt-manual-start row in the transition table (out to igniting, actor agent, trigger "agent finds the VM running while the row says out"); the queue between the HTTP function and the worker in the ignite sequence; backup and upload before `stop` in the idle sequence; repository layout updated.
- **contracts/configuration.md**: `agent.env` becomes `bonfire.env`; `BONFIRE_GIT_REF` added as a derived setting; `discord_guild_id` added as a variable; `vm_hourly_usd` default 0.30; a note that `discord-bot-token` is stored but referenced by no Function setting until Phase 1.5.
- **contracts/discord.md**: `restart` marked Phase 1.5 in the command table; the unknown-count extinguish rule stated; `scripts/register-commands.py` named as the registration path.
- **contracts/adapter-interface.md**: rule 6: callers consult `health` only while the game is expected to be running.
- **contracts/data-schema.md**: `command/ignite` may carry actor `agent` with detail `adopted manual start`; `vm` gains action `backup`.
- **prd.md**: 7.6 Valheim bullet states crossplay is unsupported in v1; roadmap Phase 1 lists the safety net, `cost` and backup upload; `restart` stays in 1.5.
- **README.md**: Discord setup steps, `pytest -m unit`, status line "Phase 1 in progress" and then "complete".
- **ADR 0008** (new): the Function acknowledges over HTTP and does its work from a queue.
- **ADR 0002**: no change; the root `vm_size` default is aligned to the amendment.
- **Phase 0 spec section 11**: each follow-up annotated resolved (nightly shutdown, health, crossplay decision, warm-boot timing, data disk via backups, `vm_hourly_usd`), deferred (CI delivery, log shipping, review minors) or moved here.

## 10. Inputs from the owner, in order

1. Discord developer portal: create the application and its bot; record the application ID, public key and bot token; invite the bot to the guild with the `applications.commands` scope.
2. The guild ID (developer mode, copy ID) and a channel webhook URL created in the group's channel.
3. Values for the new Terraform variables in the gitignored `terraform.tfvars`; tunables may stay at their defaults.
4. Approval for the apply: it replaces the VM once (the data disk and IP survive) and adds under US$2 a month.
5. After the first apply: paste `function_url` as the Interactions Endpoint URL in the portal (Discord verifies it with a PING), then run `scripts/register-commands.py`.
6. Presence for the e2e session, including one real connection to the game.

## 11. Acceptance

- `pytest -m unit tests/` passes locally and in CI with every scenario in the six feature files bound; `test_interactions_http.py` passes.
- `python3 scripts/check_docs.py` prints `OK`; every amendment in section 9 is applied.
- `terraform apply` succeeds from the Phase 0 state; a second apply is a no-op; the Discord portal accepts the endpoint.
- The five e2e runs in 8.4 pass and their timings are recorded below.
- The nightly shutdown schedule and its variables are removed in the final PR of the phase.

## 12. Phase 1 results

Appended after execution: e2e outcomes and timings, and follow-ups carried into Phase 1.5.
