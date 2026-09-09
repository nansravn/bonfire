# PRD — Bonfire: on-demand game server

**Version:** 0.3
**Owner:** Renan
**Status:** In discussion
**Pilot:** Valheim, Azure Brazil South, up to 5 concurrent players
**Changelog v0.2 → v0.3:** English throughout; final command names under `/bonfire`; configurable idle-shutdown warnings; "keep it lit" button as v1.5; check interval lowered to 1 min.

---

## 1. Summary

Bonfire is an orchestration layer that starts and stops a dedicated game server in the cloud based on real player demand. Anyone in the group lights the bonfire with a Discord command; the system posts warnings as the idle timer runs down, extinguishes the server after 45 minutes with nobody connected, and tells the group. The product is game-agnostic: each game is an *adapter* packaged as a container that declares how to start, health-check and count players. All infrastructure is provisioned with Terraform. Valheim is the first adapter.

## 2. Problem

Dedicated servers for small friend groups run 24/7 but are used a few hours a day. In Brazil South, a suitable VM (4 vCPU / 16 GB) costs ~US$0.28/h, or US$170–200/month on-demand [R1][R2]; running 5 h/day it would cost ~US$42. The current alternative is one person starting and stopping the VM from the portal, which creates a single point of dependency, forgotten VMs running all night, and social friction.

Open-source projects address this [R7–R11], but none combines Azure, game-agnosticism, a serverless bot and shutdown based on an actual player count (see section 13).

## 3. Goals

- Any group member can start the server without the admin.
- The VM never stays up more than the configured idle timeout with zero players, and the group is warned before it goes down.
- The group always knows the server state (up/down, players online, time left).
- Adding a game requires only an adapter (compose file + script), no core changes.
- The whole stack is `terraform apply` from scratch; the VM is disposable.
- Predictable monthly cost under US$120 for the pilot.

## 4. Non-goals (v1)

- Multiple servers or multiple groups per installation.
- VM size auto-scaling.
- Providers other than Azure (the abstraction should allow it; not implemented).
- Web UI. Discord is the only control surface.
- Mod management or save restore through the interface.
- Authentication beyond membership in the group's Discord server.

## 5. Personas

| Persona | Need |
|---|---|
| **Admin** (Renan) | Configure once via Terraform, watch cost, never be the bottleneck. |
| **Player** | Type one command and play within 2 minutes. |
| **Contributor** (future) | Add a game by writing a compose file and a player-count script. |

## 6. Architecture decisions

### 6.1 Compute: VM + Docker (decided)

Alternatives evaluated:

| Criterion | VM + Docker | AKS | ACI |
|---|---|---|---|
| Cost while stopped | Disk + IP (~US$14/mo) | System node pool 24/7 (~US$35–70) + LB | Zero |
| Cost while running (4 vCPU/16 GB, BR) | ~US$0.28/h [R1] | Node VM + overhead | ~US$0.25–0.30/h |
| Time to ready | ~2 min | 3–6 min if node pool scales from zero | 2–4 min (image pull on every start) |
| UDP + fixed address | Trivial | Standard LB with UDP | No fixed IP; stable DNS label |
| Save persistence | OS/data disk | PVC on Azure Disk | Azure Files (slow; corruption reports with Valheim) |
| Terraform complexity | Low | High | Medium |

- **AKS rejected:** the *system* node pool cannot scale to zero, so a VM would run 24/7 just to orchestrate the game VM. Fixed cost higher than the whole solution running.
- **ACI rejected for v1:** zero idle cost is attractive, but the image pull on every start and Azure Files for saves are real friction. Candidate for v2 if the image is small and the game tolerates Azure Files.
- **VM + Docker chosen:** the adapter is a container (portable to ACI/AKS later) but runs on a VM with fast local disk and a fixed IP. Simple Terraform.

### 6.2 VM size: D4as v5, not B4as v2

B-series VMs use burst credits: they bank credits below 40% usage and spend them above, and are throttled to baseline when credits run out [R3][R4]. The B4as v2 starts with only 60 credits, and credits are lost on deallocation — a VM that starts and stops daily would spend much of each session throttled. The D4as v5 has the same silicon (AMD EPYC 7763), same RAM and full CPU from the first second, for ~12% more [R1][R2].

### 6.3 Controller: Azure Function with Discord Interactions Endpoint

No persistent bot. Discord delivers slash commands over HTTP; the Function validates the signature and acts. Same pattern as `game-server-deploy` [R8], which uses Lambdas. Cost: cents.

### 6.4 Watchdog: on-VM agent is primary; Function is the safety net

- **Local agent (primary):** systemd timer every `idle_check_interval` calls the adapter's `player_count`. Zero players for `idle_timeout_minutes` → deallocate via the VM's own managed identity + Discord post.
- **Function (safety net):** timer every 15 min. If the VM has been allocated longer than `max_session_hours` (default 12) or the agent has not sent a heartbeat in 20 min, deallocate and notify. Covers a fully hung VM.
- **Contract:** the agent writes heartbeat and `player_count` to the state table on every check. The Function acts only when the agent is silent or the ceiling is exceeded.

### 6.5 Storage

| Data | Service | Why |
|---|---|---|
| Operational state (VM state, idle timer, warnings posted, heartbeat, hours this month) | Azure Table Storage | Comes with the Function's storage account; cents/month. |
| Events and interactions (who ran what, result, latency, player count over time) | Cosmos DB serverless, `events` container, 90-day TTL | Rich queries for pilot metrics; billed per RU, near zero at this volume. Alternative: Cosmos free tier (1,000 RU/s, 25 GB) if the subscription has none yet. |
| Secrets (Discord token, game password) | Key Vault | Never in code or plain env vars. |
| Save backups | Blob Storage, daily, 7-day retention | Outside the Discord surface. |

### 6.6 Infrastructure as code: Terraform

```
infra/
  modules/
    network/     vnet, subnet, nsg (rules from adapter), static public IP (Standard)
    vm/          D4as v5, Premium OS disk, separate data disk, managed identity, cloud-init
    controller/  function app (consumption), storage account, table, app settings
    data/        cosmos serverless, events container (ttl=90d)
    iam/         function → VM Contributor (scope: the VM); VM → may deallocate itself
    secrets/     key vault + access policies
  envs/
    pilot/       terraform.tfvars
games/
  valheim/
    docker-compose.yml   lloesche/valheim-server or equivalent
    adapter.sh           implements the interface in 7.6
    ports.tf             [{port=2456, proto=udp}, {port=2457, proto=udp}]
```

Terraform provisions; day-to-day start/stop is the Function and the agent. Cloud-init clones the repo, installs Docker and brings up the configured adapter's compose. Saves live on a dedicated data disk with `prevent_destroy = true`, so the VM can be destroyed and recreated without losing worlds.

### 6.7 Configuration

All timings are Terraform variables, pushed to Function app settings and the agent's environment file.

```hcl
idle_timeout_minutes = 45        # zero players for this long → extinguish
idle_warning_minutes = [15, 5]   # post a warning when this many minutes remain
idle_check_interval  = 1         # agent check frequency (minutes)
max_session_hours    = 12        # external watchdog ceiling
```

Validation: every value in `idle_warning_minutes` must be less than `idle_timeout_minutes` and greater than `idle_check_interval`. The A2S query is local and cheap, so a 1-minute check interval is the default; it keeps warnings accurate to within a minute.

## 7. Functional requirements

### 7.1 Commands

All commands are subcommands of `/bonfire`, so typing `/bonfire` shows every action in Discord's autocomplete. Discord has no native aliases; `start` and `stop` are registered as separate subcommands routed to the same handlers, with descriptions marking them as aliases.

| Command | Behavior |
|---|---|
| `/bonfire ignite` (alias `start`) | If deallocated, start the VM; reply "Lighting the bonfire, ~2 min" and post "Bonfire lit — server ready" when `is_ready` succeeds. If already up or starting, reply with current status. |
| `/bonfire extinguish` (alias `stop`) | Deallocate. If players are online, require confirmation (button). |
| `/bonfire check` | State (lit / out / igniting / extinguishing), players online/max, uptime this session, minutes until auto-extinguish. |
| `/bonfire cost` | Hours lit this month and estimated US$. |
| `/bonfire restart` | Restart the game process only (adapter `stop` + `start`), VM stays up. |

### 7.2 Concurrency

- A lock in the state table (`state = igniting|extinguishing`, 5-min TTL) prevents two simultaneous `ignite` calls or an `extinguish` during boot. The second command receives the current status.
- Actions are idempotent: `ignite` on a running VM only replies.

### 7.3 Idle shutdown with warnings

Agent logic, run every `idle_check_interval`:

```
count = adapter player_count
if count == unknown:
    do nothing; alert if unknown persists > 60 min
elif count > 0:
    if idle_since is set and any warning was posted:
        post "Someone joined — auto-extinguish cancelled."
    idle_since = null; warnings_posted = {}
else:
    idle_since ??= now
    remaining = idle_timeout_minutes - (now - idle_since)
    for w in idle_warning_minutes (descending):
        if remaining <= w and w not in warnings_posted:
            post "The bonfire will burn out in {w} min with nobody around."
            warnings_posted += w
    if remaining <= 0:
        extinguish
        post "The bonfire burned out after {idle_timeout_minutes} min with no one around. /bonfire ignite to bring it back."
```

`idle_since` and `warnings_posted` are persisted in the state table so an agent restart does not reset the timer.

**v1.5 — "Keep it lit" button:** warnings are sent by the Function (as the bot) instead of a webhook, carrying a button. Clicking it resets `idle_since` and posts who kept it lit. Lets someone on Discord hold the server for a few minutes before joining.

### 7.4 Notifications

The Discord channel receives: bonfire lit (ready), each idle warning, auto-extinguish cancelled, burned out (idle), extinguished manually (with author), failed to ignite, game crashed/restarted, external watchdog triggered.

### 7.5 Network

Static Standard public IP. NSG rules from the adapter's `ports.tf`. The query port (2457) is opened only if the external watchdog needs it; in v1 only the local agent queries, on `127.0.0.1`.

### 7.6 Adapter interface

The core knows no game. Each adapter is a directory in `games/<name>/` with:

- `docker-compose.yml` — image and server configuration.
- `ports.tf` — ports/protocols to open.
- `adapter.sh` with subcommands:

```
install         pull image / update server binaries
start           docker compose up -d
stop            docker compose down with clean save (configurable grace period)
is_ready        exit 0 when the game accepts connections
player_count    print an integer; print "unknown" if unavailable
health          print ok | degraded | crashed
backup          copy saves to the backup staging directory
```

**Safety rule:** if `player_count` returns `unknown`, the watchdog **never** extinguishes.

**Valheim adapter:**
- Image: `lloesche/valheim-server` (SteamCMD built in, auto-update).
- `player_count`: Steam A2S_INFO query on `127.0.0.1:2457` (`python-a2s`). Fallback: log parsing (`Got connection SteamID` / `Closing socket`).
- `is_ready`: A2S responds.
- Ports: 2456–2457/UDP.
- Known risk: with `-crossplay` (PlayFab) A2S may behave differently; test in phase 0.

## 8. Non-functional requirements

- `ignite` → ready: ≤ 3 min (target 2).
- Zero shutdowns with a player connected.
- Warnings posted within 1 minute of their configured threshold.
- Controller + storage: < US$3/month.
- Every command logged with author, timestamp and result (Cosmos `events`).
- Azure Cost Management alert at 80% of budget.
- Application Insights on the Function; agent logs shipped to Log Analytics (free tier, 5 GB/month).

## 9. Data model

**Table Storage — `state`** (single row)
`vm_state`, `state_since`, `idle_since`, `warnings_posted`, `last_heartbeat`, `last_player_count`, `hours_this_month`, `lock_until`.

**Cosmos — `events`** (TTL 90 days)
```json
{ "ts": "...", "type": "command|vm|watchdog|game",
  "action": "ignite|extinguish|check|cost|restart|ready|warning|idle_shutdown|crash|keep_lit",
  "actor": "discord_user_id|agent|function",
  "player_count": 3, "duration_ms": 1830, "ok": true, "detail": "..." }
```

## 10. Estimated costs (pilot, Brazil South)

| Item | Monthly estimate | Source |
|---|---|---|
| D4as v5 on-demand, ~5 h/day | ~US$42 | [R1] |
| Premium SSD OS disk + data disk | ~US$12 | — |
| Static Standard public IP | ~US$4 | — |
| Function + Table + Cosmos serverless + Blob | ~US$2 | — |
| **Total** | **~US$60** | |

Ceiling: US$120/month ≈ 13 h/day lit. 1-year reservations do not apply (billed 730 h/month even when deallocated).

## 11. Success metrics (4-week pilot)

- ≥ 90% of sessions ignited by someone other than the admin.
- Zero shutdowns with a player connected.
- Idle hours (lit with 0 players) < 15% of total lit hours.
- Actual cost ≤ US$80.
- `ignite` → ready ≤ 3 min in ≥ 95% of cases.
- External watchdog triggered 0 times (any trigger is an agent bug).
- ≥ 1 auto-extinguish cancelled by a player joining after a warning (evidence the warnings are useful).

## 12. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Player count fails (crossplay, game update) | Log fallback; `unknown` never extinguishes; alert if `unknown` > 1 h. |
| VM stays lit for days | External watchdog with hour ceiling; cost alert. |
| Conflicting commands | Lock with TTL in the state table. |
| `extinguish` abuse | Confirmation when players online; author logged. |
| Image update breaks the adapter | `install` validated at boot; on failure notify and keep the VM up for diagnosis (within ceiling). |
| Agent restarts mid-idle | `idle_since` persisted in the state table. |
| Warning spam if players flap around zero | Warnings reset only after a cancellation post; consider a 2-check debounce before starting the idle timer. |
| Cosmos cost surprise | Serverless with US$5/month alert; 90-day TTL. |

## 13. Prior art

| Project | What it does | What we reuse | What differs |
|---|---|---|---|
| nichogx/game-servers-manager-bot [R7] | Discord bot starts EC2, waits for the game, posts IP; checks players every 15 min and stops when empty. Multi-game, multi-server. | "Start → wait ready → post address" flow; shutdown by player count. | AWS; persistent 24/7 bot; no IaC; unmaintained. |
| CoderCoco/game-server-deploy [R8] | Multi-game on AWS Fargate, serverless Discord bot (Lambdas), watchdog by network packets, Terraform, web dashboard. | Serverless Interactions Endpoint pattern; Terraform for everything. | AWS; shutdown by traffic (noisy); far heavier. |
| Azure + Discord voice article [R9] | Starts VM when someone joins a voice channel, stops when the last one leaves. | Anti-accident guards (10 s on join, 1 min on leave, re-check 3 min after stop). | Voice trigger instead of commands (backlog). |
| timvisee/lazymc [R10] | Proxy that sleeps an idle Minecraft server and wakes it when someone connects, transparently. | Per-game adapter mental model; wake-on-connect UX. | Minecraft only (TCP); stops the process, not the VM. |
| Assorted Minecraft bots [R11] | Start/stop by command, one game, one provider. | — | No abstraction. |

**What makes Bonfire different:** Azure; container-based game-agnostic adapter; serverless bot; shutdown by real player count with the "unknown never extinguishes" rule; configurable pre-shutdown warnings; full Terraform; queryable interaction history.

## 14. Roadmap

- **Phase 0 (1 week):** Terraform for VM + network; Valheim adapter in compose; A2S working; Blob backup. Test A2S with and without crossplay.
- **Phase 1 (2 weeks):** Local agent (idle timer + warnings + heartbeat + webhook). Function with `ignite`, `extinguish`, `check`. Table + Cosmos. Concurrency lock.
- **Phase 1.5:** Warnings sent by the bot with the "Keep it lit" button. `restart`.
- **Phase 2 (4-week pilot):** Real use. Collect section 11 metrics from Cosmos.
- **Phase 3:** `cost`; external watchdog; alerts. Second adapter (Minecraft, Palworld or Enshrouded) to validate the abstraction.
- **Phase 4 (exploratory):** voice-channel trigger; ACI benchmark as an alternative runner.

## 15. Open questions

- Is 45 min the right timeout? Revisit with pilot data.
- Are [15, 5] the right warning points, or is a single 10-min warning enough?
- Scheduled ignite ("every Friday 20:00") — worth it?
- Two games on one VM: one compose with two services, or two adapters?
- Backup: data-disk snapshot vs copying saves to Blob? (v1: copy; snapshots cost more.)
- Should `check` be a live-updating embed instead of a static reply?

## 16. References

Retrieved 2026-09-08.

- [R1] DevZero — Standard_B4as_v2 pricing by region (Brazil South US$0.242/h on-demand, US$0.131/h 1-yr reserved; East US US$0.150/h). https://www.devzero.io/instances/azure/Standard_B4as_v2
- [R2] Vantage — D4as v5 pricing and specs (4 vCPU, 16 GiB, US$0.172/h East US). https://instances.vantage.sh/azure/vm/d4as-v5
- [R3] Microsoft Learn — Basv2 sizes series (CPU credit model, AMD EPYC 7763). https://learn.microsoft.com/en-us/azure/virtual-machines/sizes/general-purpose/basv2-series
- [R4] Microsoft Learn — B-series CPU credit model (accrual/consumption formula). https://learn.microsoft.com/en-us/azure/virtual-machines/sizes/b-series-cpu-credit-model
- [R5] Valheim Wiki (Fandom) — Dedicated servers (RAM per world/area; world generation is CPU-bound). https://valheim.fandom.com/wiki/Dedicated_servers
- [R6] dedicatedgameservers.net — Valheim dedicated server requirements 2026 (4 GB for up to 5 vanilla players; per-core clock matters more than core count). https://dedicatedgameservers.net/articles/valheim-dedicated-server-requirements-2026/
- [R7] nichogx/game-servers-manager-bot. https://github.com/nichogx/game-servers-manager-bot
- [R8] CoderCoco/game-server-deploy. https://github.com/codercoco/game-server-deploy
- [R9] Hotaru Komajou — Triggering Azure VM Start/Stop via Discord Voice Channel Activity (Medium, Jan 2026). https://medium.com/@hotakoma/triggering-azure-vm-start-stop-via-discord-voice-channel-activity-414dadaa5929
- [R10] timvisee/lazymc. https://github.com/timvisee/lazymc
- [R11] Examples: coding-kiko/mc-server-control-dc-bot, ModzabazeR/simple-mc-bot, DeMislead/Discord-GS-Bot.
- [R12] ArchWiki — Valheim (minimum requirements; ~3 GB practical RAM use). https://wiki.archlinux.org/title/Valheim
