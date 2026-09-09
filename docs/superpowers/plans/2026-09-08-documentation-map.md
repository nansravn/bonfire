# Documentation Map Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce every document in the approved documentation map so that Phase 0 of Bonfire can be specified and coded against precise, non-duplicated docs.

**Architecture:** Documents are Markdown under `docs/`, Gherkin under `tests/features/`, and one Python script under `scripts/` that verifies links and feature-file structure. Each task writes one or two files, runs the checker, and commits. Later tasks link earlier ones, so order matters; the prior-art survey is independent and may run in parallel.

**Tech Stack:** Markdown (GitHub flavour, Mermaid for sequence diagrams), Gherkin, Python 3 standard library only.

**Spec:** `docs/superpowers/specs/2026-09-08-documentation-map-design.md`

## Global Constraints

- One home per fact: a fact lives in one file; every other file links to it with a relative Markdown link.
- Files stay under roughly 300 lines. Split before exceeding it.
- VM states are exactly `out`, `igniting`, `lit`, `extinguishing`. Use these spellings everywhere, including prose.
- Command vocabulary: ignite, extinguish, check, cost, restart, keep it lit. `start` and `stop` are aliases, never the primary name.
- Feature files live in `tests/features/`; every Scenario carries exactly one of `@unit`, `@contract`, `@e2e` on the line above it.
- ADR filenames are fixed: `0001-compute-vm-plus-docker.md`, `0002-vm-size-d4as-v5.md`, `0003-controller-azure-function-interactions-endpoint.md`, `0004-watchdog-local-agent-primary-function-safety-net.md`, `0005-storage-table-cosmos-keyvault-blob.md`, `0006-infrastructure-as-code-terraform.md`.
- User-facing message copy is defined once in `docs/contracts/discord.md`. Feature files quote it verbatim.
- `python3 scripts/check_docs.py` must print `OK` before every commit from Task 2 onward.
- Every commit message ends with these two lines:
  ```
  Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_019c6Rp3J5mVAC8oVoAceqPG
  ```

## Decisions made in this plan

The spec fixed the document set. Writing precise contracts required choices the PRD leaves open. Each is recorded here so the owner can veto before execution; each also lands in the document named.

| # | Decision | Lands in |
|---|---|---|
| D1 | Adapters declare game metadata in `adapter.json`: the ports Terraform opens plus two game-specific tunables, `stop_grace_seconds` and `ready_timeout_minutes`. Terraform cannot load a `.tf` file or module by variable name, but it can `jsondecode(file(...))` a JSON file selected by `var.game`. | ADR 0006, adapter-interface.md, configuration.md |
| D2 | The agent marks `igniting → lit` when `is_ready` succeeds and posts the ready message, because only the agent can reach the adapter. If no heartbeat arrives within `heartbeat_stale_minutes` of ignite, the safety net treats the boot as failed, deallocates, and posts `watchdog_boot_failed`. | architecture.md, watchdog.feature |
| D3 | Manual extinguish goes through the agent for a clean save: the Function sets `vm_state = extinguishing`, and the agent's next check runs adapter `stop`, then deallocates. Every handler and the safety-net timer reconcile against the VM power state whenever `vm_state` is `extinguishing`; if the lock has expired and the VM is still running, the Function deallocates directly. | architecture.md, extinguish.feature |
| D4 | Whoever observes deallocation complete writes `out` and adds `session_ended_at − session_started_at` to the month's hours. `igniting` is reconciled only after lock expiry. | architecture.md, data-schema.md |
| D5 | Every state-row write is a full-entity Replace with If-Match; a null field is written by omitting the property. The row gains `session_id`, `session_started_at`, `session_ended_at`, `unknown_since`, `unknown_alerted`, `last_health`, `ceiling_warned`, `hours_month`, `pending_command`. `last_player_count` is `-1` when unknown. | data-schema.md |
| D6 | Events partition key is `/month` (`YYYY-MM`). Action enum extended beyond the PRD list to cover every notification in PRD 7.4. | data-schema.md |
| D7 | Every reply is in channel, so "is it up?" is answered for everyone. The only ephemeral message is `confirm_not_yours`. Every handler responds with a deferred acknowledgement first. | discord.md |
| D8 | The extinguish confirmation is the deferred public reply itself, carrying Extinguish and Cancel buttons. Only the requester may click; the prompt expires after 2 minutes. | discord.md |
| D9 | The session ceiling extinguishes regardless of player count, as PRD 6.4 states, but announces itself one hour ahead with `watchdog_ceiling_warning`. PRD section 8 gains "except the announced session ceiling". | watchdog.feature, ADR 0004, prd.md |
| D10 | Docker owns crash restarts: adapter compose files set `restart: on-failure:3`. The agent only observes `health`, posting `crash` when it leaves `ok` and `crash_gave_up` when it reaches `crashed`; it never restarts the game itself. Recovery is `/bonfire restart`. | adapter-interface.md, architecture.md, discord.md |
| D11 | Eight Terraform variables: the PRD's four timings plus `game`, `heartbeat_stale_minutes`, `vm_hourly_usd`, `fixed_monthly_usd`. Three documented constants (watchdog interval 15 min, unknown alert 60 min, lock TTL 5 min). Two per-adapter values in `adapter.json`. No `max_players`: status messages say "{n} players online". | configuration.md, discord.md |
| D12 | `restart` is delivered through `pending_command` in the state row, which the agent reads every check, and is accepted only while `lit`. | architecture.md, data-schema.md, discord.md |
| D13 | A checker script `scripts/check_docs.py` enforces link resolution and feature-file structure. It is the only code this plan adds. | Task 1 |

---

### Task 1: Documentation checker script

**Files:**
- Create: `scripts/check_docs.py`

**Interfaces:**
- Produces: `python3 scripts/check_docs.py` exits 0 and prints `OK` when every relative Markdown link under `docs/` and `README.md` resolves and every `tests/features/*.feature` file is well-formed; otherwise prints one line per problem and exits 1. Environment variable `BONFIRE_DOCS_ROOT` overrides the repository root for testing.

- [ ] **Step 1: Write the negative fixture and confirm the script does not exist yet**

```bash
FIX=/tmp/claude-1000/-home-renanvn-GitHub-bonfire/80ab3bb9-d324-4fff-90b6-16c81fc7ace7/scratchpad/checkfix
mkdir -p "$FIX/docs" "$FIX/tests/features"
printf '# A\n\nSee [b](missing.md) and [c](../README.md).\n' > "$FIX/docs/a.md"
printf '# root\n' > "$FIX/README.md"
printf 'Feature: X\n\n  Scenario: no tag\n    Given a\n    When b\n    Then c\n\n  @unit\n  Scenario: no then\n    Given a\n    When b\n' > "$FIX/tests/features/x.feature"
BONFIRE_DOCS_ROOT="$FIX" python3 scripts/check_docs.py; echo "exit=$?"
```

Expected: `python3: can't open file ... scripts/check_docs.py` and `exit=2`.

- [ ] **Step 2: Write the script**

```python
#!/usr/bin/env python3
"""Verify Bonfire documentation.

Checks:
  1. Every relative Markdown link in docs/**/*.md and README.md points to an existing file.
  2. Every tests/features/*.feature file starts with a Feature line, and every
     Scenario has exactly one level tag (@unit, @contract, @e2e) and uses Given, When and Then.

Exit 0 and print OK when clean; otherwise print one problem per line and exit 1.
Set BONFIRE_DOCS_ROOT to check a different tree (used by the script's own test).
"""
import os
import pathlib
import re
import sys

ROOT = pathlib.Path(os.environ.get("BONFIRE_DOCS_ROOT", pathlib.Path(__file__).resolve().parent.parent))
LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
LEVELS = {"@unit", "@contract", "@e2e"}
STEP_WORDS = ("Given", "When", "Then")


def check_links() -> list[str]:
    problems = []
    files = sorted((ROOT / "docs").rglob("*.md")) if (ROOT / "docs").exists() else []
    if (ROOT / "README.md").exists():
        files.append(ROOT / "README.md")
    for md in files:
        text = md.read_text(encoding="utf-8")
        for match in LINK.finditer(text):
            target = match.group(1)
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            path = target.split("#", 1)[0]
            if not (md.parent / path).exists():
                problems.append(f"{md.relative_to(ROOT)}: broken link {target}")
    return problems


def check_features() -> list[str]:
    problems = []
    feature_dir = ROOT / "tests" / "features"
    if not feature_dir.exists():
        return problems
    for feature in sorted(feature_dir.glob("*.feature")):
        rel = feature.relative_to(ROOT)
        lines = feature.read_text(encoding="utf-8").splitlines()
        if not any(line.strip().startswith("Feature:") for line in lines[:5]):
            problems.append(f"{rel}: no 'Feature:' line within the first 5 lines")
        pending_tags: set[str] = set()
        scenario = None
        seen: set[str] = set()

        def close() -> None:
            if scenario is not None:
                missing = [w for w in STEP_WORDS if w not in seen]
                if missing:
                    problems.append(f"{rel}: '{scenario}' lacks {', '.join(missing)}")

        for line in lines:
            s = line.strip()
            if s.startswith("@"):
                pending_tags |= set(s.split())
            elif s.startswith(("Scenario:", "Scenario Outline:")):
                close()
                scenario = s
                seen = set()
                levels = pending_tags & LEVELS
                if len(levels) != 1:
                    problems.append(f"{rel}: '{scenario}' must have exactly one of @unit, @contract, @e2e")
                pending_tags = set()
            elif scenario is not None:
                word = s.split(" ", 1)[0]
                if word in STEP_WORDS:
                    seen.add(word)
        close()
    return problems


def main() -> int:
    problems = check_links() + check_features()
    if problems:
        print("\n".join(problems))
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Run the negative fixture and confirm all three problems are reported**

```bash
FIX=/tmp/claude-1000/-home-renanvn-GitHub-bonfire/80ab3bb9-d324-4fff-90b6-16c81fc7ace7/scratchpad/checkfix
BONFIRE_DOCS_ROOT="$FIX" python3 scripts/check_docs.py; echo "exit=$?"
```

Expected output, three lines then `exit=1`:

```
docs/a.md: broken link missing.md
tests/features/x.feature: 'Scenario: no tag' must have exactly one of @unit, @contract, @e2e
tests/features/x.feature: 'Scenario: no then' lacks Then
```

- [ ] **Step 4: Run against the real repository**

Run: `python3 scripts/check_docs.py; echo "exit=$?"`
Expected: `OK` then `exit=0` (the PRD has only external links, and `tests/features/` does not exist yet).

- [ ] **Step 5: Commit**

```bash
git add scripts/check_docs.py
git commit -m "$(cat <<'MSG'
Add documentation checker script

Verifies relative Markdown links under docs/ and README.md, and that every
Gherkin scenario carries one level tag and uses Given, When and Then.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_019c6Rp3J5mVAC8oVoAceqPG
MSG
)"
```

---

### Task 2: ADR index, template, and ADRs 0001 and 0002

**Files:**
- Create: `docs/adr/README.md`
- Create: `docs/adr/0001-compute-vm-plus-docker.md`
- Create: `docs/adr/0002-vm-size-d4as-v5.md`

**Interfaces:**
- Consumes: `docs/prd.md` sections 6.1 and 6.2 (source material) and section 16 (references R1 to R4).
- Produces: the ADR template every later ADR follows; ADR files that `docs/prd.md` v0.4 and `docs/architecture.md` link by the fixed filenames.

- [ ] **Step 1: Write the index and template**

`docs/adr/README.md`:

```markdown
# Architecture decision records

One file per decision that shapes Bonfire's structure. A decision is recorded once it is settled; proposals live in phase specs until then.

## Index

| ADR | Title | Status |
|---|---|---|
| [0001](0001-compute-vm-plus-docker.md) | Compute: a single VM running Docker | Accepted |
| [0002](0002-vm-size-d4as-v5.md) | VM size: D4as v5 instead of B4as v2 | Accepted |

## Template

Copy this block into `NNNN-short-title.md`, where `NNNN` is the next number in the index.

```markdown
# NNNN. Title

**Status:** Proposed | Accepted | Superseded by NNNN
**Date:** YYYY-MM-DD

## Context

What situation forces a choice. Facts and constraints, with references.

## Decision

What was chosen, in one or two sentences.

## Alternatives considered

One subsection per alternative: what it is, why it was rejected.

## Consequences

What becomes easier, what becomes harder, what must now be done.
```
```

The index lists only the two ADRs this task creates, so the checker stays green. Tasks 3 and 4 append their rows; the final index has six.

- [ ] **Step 2: Write ADR 0001**

`docs/adr/0001-compute-vm-plus-docker.md`, filled from PRD 6.1:

```markdown
# 0001. Compute: a single VM running Docker

**Status:** Accepted
**Date:** 2026-09-08

## Context

Bonfire runs one dedicated game server for a small group, a few hours a day, in Azure Brazil South. The server needs UDP on a fixed address, fast local disk for saves, and about 4 vCPU and 16 GB of RAM ([PRD](../prd.md) section 2). The run-time cost target is under US$120 a month with roughly 5 hours of play a day.

Three Azure compute shapes were compared:

| Criterion | VM + Docker | AKS | ACI |
|---|---|---|---|
| Cost while stopped | Disk + IP (~US$14/mo) | System node pool 24/7 (~US$35–70) + LB | Zero |
| Cost while running (4 vCPU/16 GB, BR) | ~US$0.28/h | Node VM + overhead | ~US$0.25–0.30/h |
| Time to ready | ~2 min | 3–6 min if node pool scales from zero | 2–4 min (image pull on every start) |
| UDP + fixed address | Trivial | Standard LB with UDP | No fixed IP; stable DNS label |
| Save persistence | OS/data disk | PVC on Azure Disk | Azure Files (slow; corruption reports with Valheim) |
| Terraform complexity | Low | High | Medium |

## Decision

Run the game in a Docker container on a single VM. The game adapter is a container so it stays portable; the VM gives it a fixed IP, local disk and simple provisioning.

## Alternatives considered

### AKS

Rejected. The system node pool cannot scale to zero, so a node would run 24/7 only to orchestrate the game. That fixed cost exceeds the whole solution's running cost.

### ACI

Rejected for v1. Zero idle cost is attractive, but every start pulls the image again, and saves would live on Azure Files, which is slow and has corruption reports with Valheim. Candidate for a later phase if the image is small and the game tolerates Azure Files.

## Consequences

- Terraform stays simple: one VM, one NIC, one public IP, one NSG, two disks.
- Idle cost is not zero: disks and the static IP cost about US$14 a month while the VM is deallocated.
- The VM's OS is Bonfire's responsibility to patch; cloud-init rebuilds it from scratch, so the VM is treated as disposable.
- Because the adapter is a container, moving to ACI or AKS later changes the runner, not the adapter.
```

- [ ] **Step 3: Write ADR 0002**

`docs/adr/0002-vm-size-d4as-v5.md`, filled from PRD 6.2:

```markdown
# 0002. VM size: D4as v5 instead of B4as v2

**Status:** Accepted
**Date:** 2026-09-08

## Context

Valheim for up to 5 players needs about 4 GB of RAM in practice and benefits from per-core clock speed more than core count ([PRD](../prd.md) references R5, R6, R12). Two 4 vCPU / 16 GB sizes fit: the burstable B4as v2 and the general-purpose D4as v5. Both use the AMD EPYC 7763.

B-series VMs run on CPU credits: they bank credits while below a 40% baseline and spend them above it, and are throttled to the baseline when credits run out (references R3, R4). A B4as v2 starts with 60 credits, and banked credits are lost on deallocation.

## Decision

Use Standard_D4as_v5.

## Alternatives considered

### Standard_B4as_v2

Rejected. A VM that starts and stops daily loses its credit bank on every deallocation and begins each session with 60 credits. A game server that idles near 40% and spikes during world generation would spend much of a session throttled. It is about 12% cheaper per hour (reference R1 versus R2), which does not cover that risk.

## Consequences

- Full CPU from the first second of every session; no throttling to reason about.
- About 12% higher hourly cost than the burstable size.
- If usage ever approaches 24/7, revisit with reserved instances, which do not help a VM that is deallocated most of the day.
```

- [ ] **Step 4: Verify links and file count**

Run: `python3 scripts/check_docs.py && ls docs/adr`
Expected: `OK` then `0001-compute-vm-plus-docker.md  0002-vm-size-d4as-v5.md  README.md`.

- [ ] **Step 5: Commit**

```bash
git add docs/adr
git commit -m "$(cat <<'MSG'
Add ADR index, template, and ADRs 0001 and 0002

Backfill the compute (VM + Docker) and VM size (D4as v5) decisions
from PRD section 6 as architecture decision records.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_019c6Rp3J5mVAC8oVoAceqPG
MSG
)"
```

---

### Task 3: ADRs 0003 and 0004

**Files:**
- Create: `docs/adr/0003-controller-azure-function-interactions-endpoint.md`
- Create: `docs/adr/0004-watchdog-local-agent-primary-function-safety-net.md`
- Modify: `docs/adr/README.md` (add two index rows)

**Interfaces:**
- Consumes: the ADR template from Task 2; PRD sections 6.3 and 6.4.
- Produces: two ADRs linked from `docs/architecture.md` (Task 5) and `docs/prd.md` v0.4 (Task 14).

- [ ] **Step 1: Write ADR 0003**

```markdown
# 0003. Controller: Azure Function with the Discord Interactions Endpoint

**Status:** Accepted
**Date:** 2026-09-08

## Context

Players control Bonfire through Discord slash commands. Discord offers two ways to receive them: a persistent gateway connection held open by a bot process, or an Interactions Endpoint URL that Discord calls over HTTPS for each command. The controller must be reachable when the game VM is deallocated, and its idle cost must be near zero ([PRD](../prd.md) section 6.3).

## Decision

An Azure Function on the consumption plan is registered as the Discord Interactions Endpoint. Discord delivers each command as an HTTPS request; the Function validates the Ed25519 signature and acts. No process stays running.

## Alternatives considered

### Gateway bot on the game VM

Rejected. The bot would be off whenever the VM is off, so nobody could ignite.

### Gateway bot on a small always-on host

Rejected. An always-on VM or container costs more per month than the whole controller and storage budget of US$3 (PRD section 8), and adds a host to patch.

### Azure Logic Apps

Rejected. Signature validation and the deferred-response flow need code; a Function is the cheaper and simpler home for it.

## Consequences

- Discord requires an acknowledgement within 3 seconds. Every handler responds with a deferred acknowledgement first, then edits the reply. The exact flow is in [contracts/discord.md](../contracts/discord.md).
- Cold starts on the consumption plan are usually under 3 seconds but not guaranteed; the deferred acknowledgement is sent before any I/O to protect the deadline.
- The Function has no gateway connection, so it cannot see voice-channel events. A voice trigger (PRD phase 4) would need a separate gateway process.
- The same pattern is used by CoderCoco/game-server-deploy on AWS Lambda (PRD reference R8).
```

- [ ] **Step 2: Write ADR 0004**

```markdown
# 0004. Watchdog: on-VM agent primary, Function safety net

**Status:** Accepted
**Date:** 2026-09-08

## Context

The VM must never stay allocated with zero players beyond the idle timeout, and must be extinguished even if the game or the whole VM hangs ([PRD](../prd.md) sections 3 and 6.4). Counting players needs the game's query protocol, which for Valheim is Steam A2S on UDP 2457. Querying it from outside the VM means opening the port to the internet and tolerating remote UDP flakiness.

## Decision

Two cooperating watchdogs:

- **The agent on the VM is primary.** A systemd timer runs every `idle_check_interval` minutes, asks the adapter for `player_count`, and drives the idle timer and warnings. After `idle_timeout_minutes` with zero players it stops the game cleanly and deallocates the VM through the VM's own managed identity.
- **The Function is the safety net.** A timer trigger every `watchdog_interval_minutes` deallocates the VM when it has been allocated longer than `max_session_hours` or the agent has not written a heartbeat for `heartbeat_stale_minutes`. It never reads the player count.

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
```

- [ ] **Step 3: Add the two index rows to `docs/adr/README.md`**

Insert after the 0002 row:

```markdown
| [0003](0003-controller-azure-function-interactions-endpoint.md) | Controller: Azure Function with the Discord Interactions Endpoint | Accepted |
| [0004](0004-watchdog-local-agent-primary-function-safety-net.md) | Watchdog: on-VM agent primary, Function safety net | Accepted |
```

- [ ] **Step 4: Verify**

Run: `python3 scripts/check_docs.py`
Expected: exactly one line reporting a broken link, from ADR 0003 to `../contracts/discord.md`, which Task 9 creates. Any other output is a defect in this task.

To keep the commit green, replace that one link in ADR 0003 with plain text `contracts/discord.md` (no Markdown link) and add a line `<!-- TODO-LINK: contracts/discord.md -->` directly above it. Task 9 restores the link. Re-run: expected `OK`.

- [ ] **Step 5: Commit**

```bash
git add docs/adr
git commit -m "$(cat <<'MSG'
Add ADRs 0003 (controller) and 0004 (watchdog)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_019c6Rp3J5mVAC8oVoAceqPG
MSG
)"
```

---

### Task 4: ADRs 0005 and 0006

**Files:**
- Create: `docs/adr/0005-storage-table-cosmos-keyvault-blob.md`
- Create: `docs/adr/0006-infrastructure-as-code-terraform.md`
- Modify: `docs/adr/README.md` (add two index rows)

**Interfaces:**
- Consumes: the ADR template; PRD sections 6.5 and 6.6; decision D1 (`adapter.json`).
- Produces: two ADRs; the repository layout tree that `docs/architecture.md` (Task 5) reproduces.

- [ ] **Step 1: Write ADR 0005**

```markdown
# 0005. Storage: Table for state, Cosmos for events, Key Vault, Blob

**Status:** Accepted
**Date:** 2026-09-08

## Context

Bonfire keeps four kinds of data with different shapes ([PRD](../prd.md) section 6.5): one small operational state record read and written every minute; an append-only log of commands and events queried for pilot metrics; a handful of secrets; and daily save backups. The whole controller-plus-storage budget is under US$3 a month.

## Decision

| Data | Service |
|---|---|
| Operational state (one row) | Azure Table Storage in the Function's storage account |
| Events and interactions | Cosmos DB serverless, container `events`, 90-day TTL |
| Secrets | Key Vault |
| Save backups | Blob Storage, daily, 7-day retention |

## Alternatives considered

### Cosmos DB for the state row too

Rejected. One row with optimistic concurrency is exactly what Table Storage does for cents; Cosmos adds nothing here.

### Table Storage for events

Rejected. Table Storage cannot run the range and aggregate queries needed for PRD section 11 metrics without scanning.

### SQLite on the VM

Rejected. The Function cannot read it while the VM is deallocated, and the state must survive the VM.

### PostgreSQL flexible server

Rejected. Its idle cost alone exceeds the storage budget.

## Consequences

- Two data stores with two SDKs in both the agent and the Function.
- Concurrency on the state row uses Table Storage ETags: every conditional write sends If-Match and retries on 412. Lock semantics are in [contracts/data-schema.md](../contracts/data-schema.md).
- Events expire after 90 days; long-term metrics must be exported before then.
- If the subscription has no Cosmos free-tier account yet, the free tier (1,000 RU/s, 25 GB) is an alternative to serverless with the same schema.
```

- [ ] **Step 2: Write ADR 0006**

```markdown
# 0006. Infrastructure as code: Terraform

**Status:** Accepted
**Date:** 2026-09-08

## Context

The whole stack must come up from `terraform apply` on an empty subscription, and the VM must be disposable without losing saves ([PRD](../prd.md) section 3). Day-to-day start and stop are not provisioning and stay out of Terraform.

## Decision

Terraform provisions every Azure resource. The repository is laid out so that each concern is one module:

```
infra/
  modules/
    network/     vnet, subnet, nsg (rules from the adapter's adapter.json), static public IP (Standard)
    vm/          D4as v5, Premium OS disk, separate data disk, managed identity, cloud-init
    controller/  function app (consumption), storage account, table, app settings
    data/        cosmos serverless, events container (ttl = 90 days)
    iam/         function -> VM Contributor scoped to the VM; VM -> may deallocate itself
    secrets/     key vault + access policies
  envs/
    pilot/       terraform.tfvars
games/
  <name>/
    docker-compose.yml
    adapter.sh
    adapter.json
```

Cloud-init clones the repository, installs Docker, and brings up the configured adapter. Saves live on the data disk, which carries `prevent_destroy = true`.

## Alternatives considered

### Bicep

Rejected. Azure-native and stateless, but the abstraction should allow another provider later (PRD section 4), and the owner's existing tooling is Terraform.

### Portal and CLI scripts

Rejected. Not reproducible from scratch; the PRD's "VM is disposable" goal depends on reproducibility.

## Consequences

- Adapters declare their ports in `adapter.json`, not a `.tf` file: Terraform cannot select a `.tf` file or module source by variable, but it can read `jsondecode(file("${path.root}/../../games/${var.game}/adapter.json")).ports`.
- Terraform needs a state backend. The pilot uses an `azurerm` backend in a small bootstrap storage account created once outside Terraform; the Phase 0 spec details the bootstrap.
- Configuration values flow from Terraform variables to Function app settings and the agent's environment file; the mapping is in [contracts/configuration.md](../contracts/configuration.md).
- Destroying and re-creating the VM keeps the data disk and its saves.
```

- [ ] **Step 3: Add the two index rows to `docs/adr/README.md`**

Insert after the 0004 row:

```markdown
| [0005](0005-storage-table-cosmos-keyvault-blob.md) | Storage: Table for state, Cosmos for events, Key Vault, Blob | Accepted |
| [0006](0006-infrastructure-as-code-terraform.md) | Infrastructure as code: Terraform | Accepted |
```

- [ ] **Step 4: Verify**

Run: `python3 scripts/check_docs.py`
Expected: two broken-link lines, for `../contracts/data-schema.md` (Task 8) and `../contracts/configuration.md` (Task 7). Apply the same holding pattern as Task 3: replace each with plain text and a `<!-- TODO-LINK: ... -->` line above it. Re-run: expected `OK`.

Then: `grep -c TODO-LINK docs/adr/*.md`
Expected: `0003...: 1`, `0005...: 1`, `0006...: 1`, others `0`.

- [ ] **Step 5: Commit**

```bash
git add docs/adr
git commit -m "$(cat <<'MSG'
Add ADRs 0005 (storage) and 0006 (Terraform)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_019c6Rp3J5mVAC8oVoAceqPG
MSG
)"
```

---

### Task 5: Architecture document

**Files:**
- Create: `docs/architecture.md`

**Interfaces:**
- Consumes: ADRs 0001 to 0006; PRD sections 6.4, 6.6, 7.2, 7.3; decisions D2, D3, D4, D10, D12.
- Produces: the state machine table and the glossary that every contract and feature file uses; component names `Function`, `agent`, `adapter`, `Terraform`.

- [ ] **Step 1: Write the document**

`docs/architecture.md`. Headings and the content each must contain:

```markdown
# Bonfire architecture

Bonfire starts and stops one game VM on demand. This document is the system-level design; per-phase design lives in `superpowers/specs/`. Decisions are recorded in [adr/](adr/README.md).

## Components

Four parts run Bonfire. Each owns one concern.
```

Then one subsection per component, each a single paragraph naming what it owns and what it depends on:

- **Function** (Azure Functions, consumption plan). Owns: the Discord Interactions Endpoint (slash commands and button clicks), the safety-net timer, and every transition it is allowed to make in the state machine below. Depends on: the state table, the events container, the Azure Compute API for the VM, Key Vault for the bot token. Never talks to the adapter. See [ADR 0003](adr/0003-controller-azure-function-interactions-endpoint.md).
- **Agent** (a service on the VM, run by a systemd timer every `idle_check_interval` minutes). Owns: readiness detection, the idle timer and warnings, heartbeat, crash restarts, executing `pending_command`, clean stop and self-deallocation. Depends on: the adapter CLI, the state table, the events container, the Discord webhook URL, the VM's managed identity. See [ADR 0004](adr/0004-watchdog-local-agent-primary-function-safety-net.md).
- **Adapter** (a directory under `games/<name>/`: compose file, `adapter.sh`, `adapter.json`). Owns: everything game-specific. Depends on: Docker and the data disk. Contract in [contracts/adapter-interface.md](contracts/adapter-interface.md).
- **Terraform** (`infra/`). Owns: provisioning only. Never starts or stops the VM after apply. See [ADR 0006](adr/0006-infrastructure-as-code-terraform.md).

```markdown
## Repository layout
```

Reproduce the tree from ADR 0006 and extend it with the two code directories:

```
agent/        the on-VM agent and its systemd units
function/     the Azure Function app
infra/        Terraform (see ADR 0006 for the module tree)
games/        one adapter per game
docs/         this documentation
tests/        feature files and, later, test code
scripts/      repository tooling
```

```markdown
## VM state machine
```

Four states. Table of every transition:

| From | To | Trigger | Actor | Lock |
|---|---|---|---|---|
| out | igniting | `/bonfire ignite` | Function | takes `lock_until = now + lock_ttl_minutes`; sets `session_id`, `session_started_at` |
| igniting | lit | adapter `is_ready` succeeds | agent | clears lock |
| igniting | lit (with `last_health = crashed`) | `ready_timeout_minutes` elapsed without readiness | agent | clears lock |
| igniting | out | reconcile: lock expired and VM power state is deallocated | Function | none |
| igniting | extinguishing | boot failure: no heartbeat within `heartbeat_stale_minutes` of `state_since` | Function (safety-net timer) | takes lock; sets `session_ended_at`; deallocates directly; posts `watchdog_boot_failed` |
| lit | extinguishing | `/bonfire extinguish` (confirmed if players online) | Function | takes lock; sets `session_ended_at` |
| lit | extinguishing | idle timeout reached | agent | takes lock; sets `session_ended_at` |
| lit | extinguishing | safety net: session ceiling or missing heartbeat | Function | takes lock; sets `session_ended_at`; deallocates directly |
| extinguishing | (deallocating) | agent observes `extinguishing` on its check | agent | runs adapter `stop`, then deallocates the VM |
| extinguishing | out | VM power state observed deallocated | Function (handler after lock expiry, or safety-net timer) | clears lock; adds `session_ended_at - session_started_at` to `hours_this_month`; clears session fields |
| out | out | drift: VM power state running, no heartbeat for `heartbeat_stale_minutes` | Function timer deallocates | none |
| lit | lit | `/bonfire restart` (accepted only while `lit`; otherwise the status reply) | Function writes `pending_command = restart`; agent runs adapter `stop` then `start` and clears it | none |

Rules stated after the table:

1. Only the actor in the table may make that transition. Anyone else that observes an inconsistent state reconciles as described in the two reconcile rows.
2. Every write to the state row is conditional on the ETag read moments before. A 412 means re-read and re-evaluate; never overwrite blindly.
3. Reconciliation. Whenever `vm_state` is `extinguishing`, and whenever it is `igniting` with `lock_until` in the past, a handler or the safety-net timer reads the VM power state before acting. Deallocated means `out` (adding the session hours). Running while `extinguishing` with an expired lock means the agent is presumed dead: the Function deallocates directly. Running while `igniting` with a heartbeat in the last `heartbeat_stale_minutes` means `lit`; running with no heartbeat at all for `heartbeat_stale_minutes` since `state_since` is a boot failure (row above). A member who runs `ignite` within a minute of a burn-out therefore either waits out the deallocation with `status_extinguishing` or, once the VM is off, proceeds normally.
4. Manual extinguish goes through the agent so the game saves cleanly. Only the safety net, which by definition has no working agent, deallocates without a clean stop.

```markdown
## Sequences
```

Two Mermaid sequence diagrams (`sequenceDiagram`), participants `Player`, `Discord`, `Function`, `Azure`, `VM/agent`, `Adapter`, `State table`.

**Ignite**, in this order:
1. Player runs `/bonfire ignite`; Discord POSTs the interaction to the Function.
2. Function validates the signature and immediately responds with a deferred acknowledgement (in channel).
3. Function reads the state row and reconciles when rule 3 applies. If `vm_state` is not `out`, it edits the reply with the status message and stops.
4. Function writes `vm_state = igniting`, `state_since`, `session_id`, `session_started_at`, `lock_until` with If-Match. On 412 it re-reads and returns to step 3.
5. Function calls Azure to start the VM, records a `command/ignite` event, and edits the reply to the igniting message.
6. The VM boots; cloud-init starts Docker and the agent timer. The agent runs adapter `install` (if the image is missing) and `start`.
7. Each check, the agent runs `is_ready`. On success it writes `vm_state = lit`, clears `lock_until`, writes `last_health = ok`, posts the ready message through the webhook, and records a `vm/ready` event with `duration_ms` since `session_started_at`.
8. If `ready_timeout_minutes` pass first, the agent writes `vm_state = lit`, `last_health = crashed`, clears the lock, posts the ignite-failed message, and records `vm/ignite_failed`.

**Idle shutdown**, in this order:
1. Every `idle_check_interval` minutes the agent runs adapter `player_count` and `health`, then writes `last_heartbeat`, `last_player_count`, `last_health`.
2. It applies the idle rules from PRD 7.3 (warnings, cancellation, unknown handling). Each warning and cancellation is posted through the webhook and recorded as an event.
3. When the timeout is reached with a known zero count, the agent writes `vm_state = extinguishing`, `session_ended_at`, `lock_until`; posts the burned-out message; records `watchdog/idle_shutdown`.
4. The agent runs adapter `stop` (clean save within `stop_grace_seconds`), then calls Azure to deallocate the VM through its managed identity. The agent dies with the VM.
5. The next Function handler or safety-net tick observes the VM deallocated and writes `vm_state = out`, adding the session hours.

```markdown
## Crash handling
```

Docker owns restarts: every adapter's compose file sets `restart: on-failure:3`, so a crashed game comes back without the agent's help, and a crash loop stops after three attempts. The agent only observes. On each check it compares the adapter's `health` with `last_health`: when it moves from `ok` to `degraded` or `crashed` it posts the `crash` message and records a `game/crash` event; when it reaches `crashed` (the container has exited and Docker has given up) it posts `crash_gave_up` and records `game/crash_gave_up`, once per streak. While the game is down `player_count` returns unknown, so the idle timer never fires; the session ends by `/bonfire extinguish`, `/bonfire restart`, or the session ceiling.

```markdown
## Glossary
```

Definitions, one line each: **out** (VM deallocated), **igniting** (VM starting, game not yet ready), **lit** (game accepting connections, or VM up with the game crashed), **extinguishing** (clean stop and deallocation in progress), **ignite** (the command and act of starting), **extinguish** (the command and act of stopping), **burn out** (an idle-timeout extinguish), **keep it lit** (resetting the idle timer from Discord, v1.5), **adapter** (the per-game container plus CLI), **agent** (the on-VM service), **controller** or **Function** (the Azure Function), **safety net** (the Function's timer that enforces the ceiling and heartbeat), **session** (from ignite to out, identified by `session_id`).

```markdown
## Security notes
```

Five bullets: Discord requests are accepted only with a valid Ed25519 signature over timestamp and body (details in [contracts/discord.md](contracts/discord.md)); the Function's identity holds Virtual Machine Contributor scoped to the one VM; the VM's managed identity may only deallocate itself; the bot token, webhook URL and game password live in Key Vault and reach code through references, never plain app settings; the NSG opens only the ports in the adapter's `adapter.json`, and the query port is never opened in v1.

- [ ] **Step 2: Verify structure and links**

Run:

```bash
python3 scripts/check_docs.py
grep -c '^## ' docs/architecture.md
grep -o '| [a-z]* | [a-z]* |' docs/architecture.md | sort -u | head -20
wc -l docs/architecture.md
```

Expected: `OK` after applying the TODO-LINK holding pattern to the link to `contracts/adapter-interface.md` (Task 6) and `contracts/discord.md` (Task 9); seven `## ` headings; the transition table's from/to pairs use only the four state names; under 300 lines.

- [ ] **Step 3: Commit**

```bash
git add docs/architecture.md
git commit -m "$(cat <<'MSG'
Add system architecture document

Components, repository layout, VM state machine with every transition
and its actor, ignite and idle-shutdown sequences, crash handling,
glossary, and security notes.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_019c6Rp3J5mVAC8oVoAceqPG
MSG
)"
```

---

### Task 6: Adapter interface contract

**Files:**
- Create: `docs/contracts/adapter-interface.md`
- Modify: `docs/architecture.md` (restore the TODO-LINK to this file)

**Interfaces:**
- Consumes: PRD 7.6; decision D1.
- Produces: subcommand names, exit codes, stdout formats, timeouts and environment variables that `adapter-valheim.feature` (Task 13) and `testing.md` (Task 10) rely on.

- [ ] **Step 1: Write the contract**

`docs/contracts/adapter-interface.md`:

```markdown
# Adapter interface

An adapter is everything Bonfire knows about one game. The core never inspects a game; it only calls this interface. Adapters live in `games/<name>/`.

## Files

| File | Purpose |
|---|---|
| `docker-compose.yml` | The game server image and its configuration. Must mount `${BONFIRE_DATA_DIR}` for saves. |
| `adapter.sh` | Executable implementing the subcommands below. Bash; may call other tools it installs. |
| `adapter.json` | Game metadata read by Terraform and the agent. Shape: `{"ports": [{"port": 2456, "proto": "udp"}, {"port": 2457, "proto": "udp"}], "stop_grace_seconds": 60, "ready_timeout_minutes": 10}`. `proto` is `udp` or `tcp`; the first port is the one players connect to. |
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

A new adapter conforms when `tests/features/adapter-<name>.feature` passes at the `@contract` level using the real image on a Docker host, and at the `@e2e` level on the pilot VM. The Valheim file is the reference: [adapter-valheim.feature](../../tests/features/adapter-valheim.feature).
```

- [ ] **Step 2: Restore the link in `docs/architecture.md`**

Remove the `<!-- TODO-LINK: contracts/adapter-interface.md -->` line and turn the plain-text mention back into `[contracts/adapter-interface.md](contracts/adapter-interface.md)`.

- [ ] **Step 3: Verify**

Run: `python3 scripts/check_docs.py; grep -n TODO-LINK docs/architecture.md`
Expected: one broken-link line for `../../tests/features/adapter-valheim.feature` (Task 13). Apply the holding pattern to it. Re-run: `OK`. The grep shows only the `contracts/discord.md` TODO-LINK remaining in architecture.md.

- [ ] **Step 4: Commit**

```bash
git add docs/contracts/adapter-interface.md docs/architecture.md
git commit -m "$(cat <<'MSG'
Add adapter interface contract

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_019c6Rp3J5mVAC8oVoAceqPG
MSG
)"
```

---

### Task 7: Configuration contract

**Files:**
- Create: `docs/contracts/configuration.md`
- Modify: `docs/adr/0006-infrastructure-as-code-terraform.md` (restore TODO-LINK)

**Interfaces:**
- Consumes: PRD 6.7; decision D11.
- Produces: variable names used by every feature file's Background and by `data-schema.md`.

- [ ] **Step 1: Write the contract**

`docs/contracts/configuration.md`:

```markdown
# Configuration

Every tunable is a Terraform variable. Terraform writes it to the Function's app settings and to the agent's environment file `/etc/bonfire/agent.env` under the same uppercase name. Lists become comma-separated strings.

## Variables

| Terraform variable | Setting / env name | Type | Default | Validation |
|---|---|---|---|---|
| `game` | `BONFIRE_GAME` | string | `valheim` | `games/<game>/adapter.sh` and `adapter.json` exist |
| `idle_timeout_minutes` | `BONFIRE_IDLE_TIMEOUT_MINUTES` | number | 45 | > `idle_check_interval` |
| `idle_warning_minutes` | `BONFIRE_IDLE_WARNING_MINUTES` | list(number) → `15,5` | `[15, 5]` | strictly descending; each < `idle_timeout_minutes` and > `idle_check_interval` |
| `idle_check_interval` | `BONFIRE_IDLE_CHECK_INTERVAL` | number (minutes) | 1 | ≥ 1 |
| `max_session_hours` | `BONFIRE_MAX_SESSION_HOURS` | number | 12 | ≥ 2, so the ceiling warning at `max_session_hours − 1` is after ignite |
| `heartbeat_stale_minutes` | `BONFIRE_HEARTBEAT_STALE_MINUTES` | number | 20 | ≥ 3 × `idle_check_interval`; > 15 (the watchdog interval) |
| `vm_hourly_usd` | `BONFIRE_VM_HOURLY_USD` | number | 0.28 | > 0 |
| `fixed_monthly_usd` | `BONFIRE_FIXED_MONTHLY_USD` | number | 18 | ≥ 0 |

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

## Secrets

Stored in Key Vault. The Function reads them as Key Vault references in app settings; the agent fetches them at boot with its managed identity and writes `/etc/bonfire/agent.env` and `/etc/bonfire/<game>.env` with mode 0600.

| Key Vault secret | Env name | Read by |
|---|---|---|
| `discord-bot-token` | `DISCORD_BOT_TOKEN` | Function |
| `discord-webhook-url` | `DISCORD_WEBHOOK_URL` | agent |
| `<game>-server-password` | adapter-defined | adapter, via `/etc/bonfire/<game>.env` |

## Validation

Terraform enforces the Validation column with `validation` blocks. The agent re-validates on startup and refuses to run on an invalid file, logging which rule failed, so a bad deploy fails loudly rather than shutting a server down at the wrong time.
```

- [ ] **Step 2: Restore the TODO-LINK in ADR 0006**

Turn the plain-text `contracts/configuration.md` back into `[contracts/configuration.md](../contracts/configuration.md)` and delete the TODO-LINK comment.

- [ ] **Step 3: Verify**

Run: `python3 scripts/check_docs.py && grep -c '^| `' docs/contracts/configuration.md`
Expected: `OK` and a count of 22 table rows (8 variables + 3 constants + 2 per-adapter + 6 derived + 3 secrets).

- [ ] **Step 4: Commit**

```bash
git add docs/contracts/configuration.md docs/adr/0006-infrastructure-as-code-terraform.md
git commit -m "$(cat <<'MSG'
Add configuration contract

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_019c6Rp3J5mVAC8oVoAceqPG
MSG
)"
```

---

### Task 8: Data schema contract

**Files:**
- Create: `docs/contracts/data-schema.md`
- Modify: `docs/adr/0005-storage-table-cosmos-keyvault-blob.md` (restore TODO-LINK)

**Interfaces:**
- Consumes: PRD section 9; decisions D4, D5, D6, D12; state machine from Task 5.
- Produces: field names and enums that every feature file asserts on.

- [ ] **Step 1: Write the contract**

`docs/contracts/data-schema.md`:

```markdown
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

- Taken by whoever moves to `igniting` or `extinguishing`, set to `now + lock_ttl_minutes`.
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
| `vm` | `ready`, `ignite_failed`, `deallocated` |
| `watchdog` | `warning`, `idle_cancelled`, `idle_shutdown`, `unknown_alert`, `ceiling_warning`, `ceiling`, `heartbeat_missing`, `boot_failed` |
| `game` | `crash`, `crash_gave_up` |

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
```

- [ ] **Step 2: Restore the TODO-LINK in ADR 0005**

- [ ] **Step 3: Verify**

Run: `python3 scripts/check_docs.py && grep -c '^| `' docs/contracts/data-schema.md`
Expected: `OK` and a count of 37: 17 state fields, 4 values-per-state rows, 11 event fields, the action table header, and 4 action rows.

- [ ] **Step 4: Commit**

```bash
git add docs/contracts/data-schema.md docs/adr/0005-storage-table-cosmos-keyvault-blob.md
git commit -m "$(cat <<'MSG'
Add data schema contract

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_019c6Rp3J5mVAC8oVoAceqPG
MSG
)"
```

---

### Task 9: Discord contract and message catalog

**Files:**
- Create: `docs/contracts/discord.md`
- Modify: `docs/adr/0003-controller-azure-function-interactions-endpoint.md`, `docs/architecture.md` (restore TODO-LINKs)

**Interfaces:**
- Consumes: PRD 7.1, 7.4; decisions D7, D8, D10.
- Produces: message IDs and exact copy that every feature file quotes.

- [ ] **Step 1: Write the contract**

`docs/contracts/discord.md`:

```markdown
# Discord contract

Discord is the only control surface. This file defines the command tree, the interaction flow, and every message Bonfire sends.

## Commands

One top-level command `/bonfire` with subcommands, registered per guild (instant propagation) with `PUT /applications/{application_id}/guilds/{guild_id}/commands`.

| Subcommand | Description string | Options | Handler |
|---|---|---|---|
| `ignite` | Light the bonfire (start the server) | none | ignite |
| `start` | Alias of ignite | none | ignite |
| `extinguish` | Put out the bonfire (stop the server) | none | extinguish |
| `stop` | Alias of extinguish | none | extinguish |
| `check` | Is the bonfire lit? Players, uptime, time left | none | check |
| `cost` | Hours lit this month and estimated cost | none | cost |
| `restart` | Restart the game only; the bonfire stays lit | none | restart |

## Interaction flow

1. Discord POSTs to the Function with headers `X-Signature-Ed25519` and `X-Signature-Timestamp`. The Function verifies the Ed25519 signature of `timestamp + raw body` against `DISCORD_PUBLIC_KEY`. Invalid or missing signature: HTTP 401, nothing else.
2. Interaction type 1 (PING): respond `{"type": 1}`.
3. Interaction type 2 (command) and type 3 (button): respond within 3 seconds with a deferred acknowledgement, before any I/O. Commands use response type 5 (`DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE`); buttons use type 6 (`DEFERRED_UPDATE_MESSAGE`).
4. Every reply is in channel, so a `check` answers "is it up?" for everyone. The only ephemeral message is `confirm_not_yours` (`flags: 64`).
5. The handler then does its work and edits the original reply with `PATCH /webhooks/{application_id}/{interaction_token}/messages/@original`. The token is valid for 15 minutes.
6. Messages that happen later (ready, warnings, burn-out) are posted by the agent to the channel webhook `DISCORD_WEBHOOK_URL`, not through an interaction token.

### Extinguish confirmation

When `last_player_count > 0`, the extinguish handler edits its reply to `confirm_extinguish` with two buttons: `Extinguish` (style danger, `custom_id = extinguish:confirm:<user_id>:<unix_ts>`) and `Cancel` (style secondary, `custom_id = extinguish:cancel:<user_id>:<unix_ts>`). Rules:

- Only the user whose ID is in `custom_id` may click. Anyone else gets an ephemeral `confirm_not_yours`.
- If `now - unix_ts > 120` seconds, either click edits the message to `confirm_expired`.
- `Extinguish` proceeds as a confirmed extinguish and edits the message to `extinguished_manual_with_players`.
- `Cancel` edits the message to `confirm_cancelled`.

## Message catalog

Placeholders in braces are substituted; everything else is verbatim. Feature files quote these strings.

| ID | Sent by | Where | Copy |
|---|---|---|---|
| `igniting` | Function | channel | Lighting the bonfire, ~2 min. |
| `status_out` | Function | channel | The bonfire is out. /bonfire ignite to light it. |
| `status_igniting` | Function | channel | The bonfire is igniting ({m} min so far, usually ready in ~2 min). |
| `status_lit` | Function | channel | The bonfire is lit: {n} players online, lit for {h}h {mm}m. |
| `status_lit_idle` | Function | channel | The bonfire is lit: 0 players online, lit for {h}h {mm}m. Burns out in {r} min unless someone joins. |
| `status_lit_unknown` | Function | channel | The bonfire is lit, but the player count is unknown (auto-extinguish paused). Lit for {h}h {mm}m. |
| `status_lit_crashed` | Function | channel | The bonfire is lit but the game is down. Try /bonfire restart. |
| `status_extinguishing` | Function | channel | The bonfire is being extinguished. |
| `ready` | agent | webhook | Bonfire lit — server ready. Connect to {address}. |
| `ignite_failed` | agent | webhook | Failed to ignite: the game did not become ready in {ready_timeout_minutes} min. The VM stays up for diagnosis until the session ceiling. |
| `warning` | agent | webhook | The bonfire will burn out in {w} min with nobody around. |
| `idle_cancelled` | agent | webhook | Someone joined — auto-extinguish cancelled. |
| `idle_shutdown` | agent | webhook | The bonfire burned out after {idle_timeout_minutes} min with no one around. /bonfire ignite to bring it back. |
| `unknown_alert` | agent | webhook | Player count has been unknown for {unknown_alert_minutes} min. Auto-extinguish is paused; check the server. |
| `extinguished_manual` | Function | channel | Bonfire extinguished by {user}. |
| `confirm_extinguish` | Function | channel, with buttons | {n} players are online. Extinguish anyway? |
| `extinguished_manual_with_players` | Function | channel | Bonfire extinguished by {user} with {n} players online. |
| `confirm_cancelled` | Function | channel (edited) | Kept lit. |
| `confirm_not_yours` | Function | ephemeral | Only the person who ran /bonfire extinguish can confirm. |
| `confirm_expired` | Function | channel (edited) | This prompt expired. Run /bonfire extinguish again. |
| `restarting` | Function | channel | Restarting the game; the bonfire stays lit. |
| `crash` | agent | webhook | The game crashed; Docker is restarting it. |
| `crash_gave_up` | agent | webhook | The game crashed repeatedly and stays down. Fix it and use /bonfire restart. |
| `watchdog_ceiling_warning` | Function | webhook | The bonfire has been lit for {h} h; the safety net puts it out at {max_session_hours} h. |
| `watchdog_ceiling` | Function | webhook | Safety net: the bonfire has been lit for {max_session_hours} h and was extinguished. /bonfire ignite to bring it back. |
| `watchdog_heartbeat` | Function | webhook | Safety net: no heartbeat from the server for {heartbeat_stale_minutes} min; the bonfire was extinguished. |
| `watchdog_boot_failed` | Function | webhook | Safety net: the server never reported in after {heartbeat_stale_minutes} min; the bonfire was extinguished. Check the VM boot logs. |
| `cost` | Function | channel | Lit {h} h this month: about US${vm} for the VM plus US${fixed} fixed (disks, IP, storage). |

`{user}` is a Discord mention (`<@user_id>`). `{address}` is `BONFIRE_PUBLIC_ADDRESS`. `{vm}` is `hours_this_month × vm_hourly_usd` with two decimals; `{fixed}` is `fixed_monthly_usd`. `{h}` in `status_*` and `cost` is whole hours; `{mm}` is zero-padded minutes.

In v1.5 the `warning`, `idle_cancelled` and `idle_shutdown` rows move from the agent's webhook to the Function so they can carry the keep-it-lit button; their copy does not change.

## Status reply selection

`check`, any redundant `ignite` or `extinguish`, and a `restart` issued while not `lit`, reply with the status message chosen by this order: `vm_state` is `out` → `status_out`; `igniting` → `status_igniting`; `extinguishing` → `status_extinguishing`; `lit` and `last_health = crashed` → `status_lit_crashed`; `lit` and `last_player_count = -1` → `status_lit_unknown`; `lit` and `last_player_count = 0` → `status_lit_idle` with `{r} = idle_timeout_minutes − (now − idle_since)`; otherwise `status_lit`.
```

- [ ] **Step 2: Restore the TODO-LINKs** in ADR 0003 and `docs/architecture.md` that point at this file.

- [ ] **Step 3: Verify**

Run: `python3 scripts/check_docs.py && grep -rn TODO-LINK docs/ | wc -l`
Expected: `OK` and `1` (the remaining TODO-LINK in adapter-interface.md to the Valheim feature file).

- [ ] **Step 4: Commit**

```bash
git add docs/contracts/discord.md docs/adr/0003-controller-azure-function-interactions-endpoint.md docs/architecture.md
git commit -m "$(cat <<'MSG'
Add Discord contract and message catalog

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_019c6Rp3J5mVAC8oVoAceqPG
MSG
)"
```

---

### Task 10: Testing document

**Files:**
- Create: `docs/testing.md`

**Interfaces:**
- Consumes: the adapter contract (Task 6); the feature-file list from the spec.
- Produces: the fake-adapter approach and the level-to-file map that Tasks 11 to 13 follow.

- [ ] **Step 1: Write the document**

`docs/testing.md`:

```markdown
# Testing

Three levels. Each feature file declares its level with a tag on every scenario, so one runner can select a level with a tag expression.

| Level | Tag | Runs where | Exercises | Needs Azure |
|---|---|---|---|---|
| Unit | `@unit` | Local, no Docker | Agent idle and heartbeat logic against a fake adapter and an in-memory state row; Function handlers against signed fake Discord payloads and a fake Azure client | No |
| Adapter contract | `@contract` | Local Docker host | `adapter.sh` conformance with the real game image | No |
| End-to-end | `@e2e` | The pilot VM and Function | Ignite to ready, idle to deallocate, safety net | Yes |

## Feature files

| File | Level(s) | What it pins |
|---|---|---|
| `tests/features/ignite.feature` | unit | Ignite from every state; readiness; ignite failure |
| `tests/features/extinguish.feature` | unit | Extinguish with and without players; confirmation; deallocation completion |
| `tests/features/check.feature` | unit | Status reply in every state |
| `tests/features/idle-shutdown.feature` | unit | Warnings, cancellation, unknown rule, timer persistence, heartbeat |
| `tests/features/concurrency.feature` | unit | Ignite race, lock expiry and reconciliation |
| `tests/features/watchdog.feature` | unit | Ceiling, missing heartbeat, drift, healthy no-op |
| `tests/features/adapter-valheim.feature` | contract, e2e | Valheim conformance and real-connection behaviour |

## Fakes

- **Fake adapter.** `tests/fake-adapter/adapter.sh` implements the [adapter interface](contracts/adapter-interface.md). Each subcommand reads its scripted result from an environment variable named `FAKE_<SUBCOMMAND>` (for example `FAKE_PLAYER_COUNT=unknown`, `FAKE_IS_READY=1`) and records each invocation to `$FAKE_LOG`. Unit tests of the agent point `BONFIRE_ADAPTER_DIR` at it.
- **Fake state row.** An in-memory dictionary with ETag semantics: a write with a stale ETag raises the same error type the real client does.
- **Fake Discord payloads.** Interactions built by a helper that signs them with a test Ed25519 key; the Function under test is configured with the matching public key.
- **Fake Azure client.** Records `start` and `deallocate` calls and returns a configurable power state.

## Runner

The runner is chosen in the Phase 1 spec together with the agent and Function languages. Feature files are runner-agnostic Gherkin; the only requirement on the runner is tag selection.

## Rules

1. Every scenario in a feature file has a step implementation before the phase that implements the behaviour is called done.
2. `@contract` scenarios run in CI on every change to `games/`.
3. `@e2e` scenarios run manually before a phase is closed, and their results are recorded in the phase spec.
```

- [ ] **Step 2: Verify**

Run: `python3 scripts/check_docs.py`
Expected: `OK`.

- [ ] **Step 3: Commit**

```bash
git add docs/testing.md
git commit -m "$(cat <<'MSG'
Add testing document

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_019c6Rp3J5mVAC8oVoAceqPG
MSG
)"
```

---

### Task 11: Feature files for ignite, extinguish and check

**Files:**
- Create: `tests/features/ignite.feature`
- Create: `tests/features/extinguish.feature`
- Create: `tests/features/check.feature`

**Interfaces:**
- Consumes: message IDs and copy from `docs/contracts/discord.md`; field names from `docs/contracts/data-schema.md`.
- Produces: step phrasing (`the bonfire is <state>`, `a member runs "/bonfire <sub>"`, `the reply is message "<id>"`, `the state row has ...`, `a "<type>/<action>" event is recorded`) reused by Tasks 12 and 13.

- [ ] **Step 1: Write `tests/features/ignite.feature`**

```gherkin
Feature: Ignite the bonfire
  Any member of the Discord server starts the game server with one command.
  Messages are quoted by ID from docs/contracts/discord.md.

  Background:
    Given the configured game is "valheim"
    And the adapter declares ready_timeout_minutes 5

  @unit
  Scenario: Ignite from out
    Given the bonfire is out
    When a member runs "/bonfire ignite"
    Then the Function acknowledges within 3 seconds with a deferred channel reply
    And the reply is message "igniting"
    And the state row has vm_state "igniting", a new session_id, session_started_at now, and lock_until 5 minutes ahead
    And a VM start is requested exactly once
    And a "command/ignite" event is recorded with the member as actor and ok true

  @unit
  Scenario: The start alias behaves like ignite
    Given the bonfire is out
    When a member runs "/bonfire start"
    Then the reply is message "igniting"
    And the state row has vm_state "igniting"

  @unit
  Scenario: Ignite while lit only replies with status
    Given the bonfire is lit with 2 players online
    When a member runs "/bonfire ignite"
    Then the reply is message "status_lit"
    And no VM start is requested
    And the state row is unchanged

  @unit
  Scenario: Ignite while igniting only replies with status
    Given the bonfire is igniting
    When a member runs "/bonfire ignite"
    Then the reply is message "status_igniting"
    And no VM start is requested

  @unit
  Scenario: Ignite while extinguishing only replies with status
    Given the bonfire is extinguishing
    When a member runs "/bonfire ignite"
    Then the reply is message "status_extinguishing"
    And no VM start is requested

  @unit
  Scenario: The agent marks the bonfire lit when the game is ready
    Given the bonfire is igniting since 90 seconds ago
    And the adapter reports is_ready success
    When the agent runs its check
    Then the state row has vm_state "lit", lock_until null, and last_health "ok"
    And the webhook receives message "ready"
    And a "vm/ready" event is recorded with duration_ms of about 90000

  @unit
  Scenario: The agent keeps waiting while the game is not ready
    Given the bonfire is igniting since 60 seconds ago
    And the adapter reports is_ready not ready
    When the agent runs its check
    Then the state row still has vm_state "igniting"
    And no message is posted

  @unit
  Scenario: Failure to become ready within the deadline
    Given the bonfire is igniting since 5 minutes ago
    And the adapter reports is_ready not ready
    When the agent runs its check
    Then the state row has vm_state "lit", lock_until null, and last_health "crashed"
    And the webhook receives message "ignite_failed"
    And a "vm/ignite_failed" event is recorded with ok false
    And no VM deallocate is requested
```

- [ ] **Step 2: Write `tests/features/extinguish.feature`**

```gherkin
Feature: Extinguish the bonfire
  A manual stop goes through the agent so the game saves cleanly.

  @unit
  Scenario: Extinguish with nobody online
    Given the bonfire is lit with 0 players online
    When a member runs "/bonfire extinguish"
    Then the reply is message "extinguished_manual" mentioning the member
    And the state row has vm_state "extinguishing", session_ended_at now, and lock_until 5 minutes ahead
    And no VM deallocate is requested by the Function
    And a "command/extinguish" event is recorded with the member as actor

  @unit
  Scenario: The stop alias behaves like extinguish
    Given the bonfire is lit with 0 players online
    When a member runs "/bonfire stop"
    Then the reply is message "extinguished_manual" mentioning the member
    And the state row has vm_state "extinguishing"

  @unit
  Scenario: The agent performs the clean stop and deallocates
    Given the bonfire is extinguishing
    When the agent runs its check
    Then the adapter "stop" subcommand is invoked before any deallocate
    And a VM deallocate is requested by the agent exactly once

  @unit
  Scenario: Extinguish with players online asks for confirmation
    Given the bonfire is lit with 3 players online
    When a member runs "/bonfire extinguish"
    Then the reply is message "confirm_extinguish" with n 3 and buttons "Extinguish" and "Cancel"
    And the state row is unchanged

  @unit
  Scenario: Confirming extinguish with players online
    Given the bonfire is lit with 3 players online
    And a member has been shown message "confirm_extinguish"
    When that member clicks "Extinguish" within 2 minutes
    Then the message is edited to "extinguished_manual_with_players" with n 3
    And the state row has vm_state "extinguishing"
    And a "command/extinguish" event is recorded with player_count 3

  @unit
  Scenario: Cancelling the confirmation
    Given the bonfire is lit with 3 players online
    And a member has been shown message "confirm_extinguish"
    When that member clicks "Cancel"
    Then the message is edited to "confirm_cancelled"
    And the state row is unchanged

  @unit
  Scenario: Someone else cannot confirm
    Given the bonfire is lit with 3 players online
    And a member has been shown message "confirm_extinguish"
    When a different member clicks "Extinguish"
    Then the different member receives ephemeral message "confirm_not_yours"
    And the state row is unchanged

  @unit
  Scenario: The confirmation expires
    Given the bonfire is lit with 3 players online
    And a member has been shown message "confirm_extinguish" 3 minutes ago
    When that member clicks "Extinguish"
    Then the message is edited to "confirm_expired"
    And the state row is unchanged

  @unit
  Scenario: Extinguish while out only replies with status
    Given the bonfire is out
    When a member runs "/bonfire extinguish"
    Then the reply is message "status_out"
    And the state row is unchanged

  @unit
  Scenario: Extinguish during igniting is refused
    Given the bonfire is igniting
    When a member runs "/bonfire extinguish"
    Then the reply is message "status_igniting"
    And the state row is unchanged

  @unit
  Scenario: Deallocation completion is recorded as out
    Given the bonfire is extinguishing with session_started_at 3 hours ago and session_ended_at 2 minutes ago
    And hours_this_month is 10.0 for the current month
    And the VM power state is deallocated
    When the safety-net timer runs
    Then the state row has vm_state "out", session fields null, lock_until null
    And hours_this_month is about 12.97
    And a "vm/deallocated" event is recorded

  @unit
  Scenario: Ignite right after a burn-out proceeds once the VM is off
    Given the bonfire is extinguishing with lock_until 3 minutes ahead
    And the VM power state is deallocated
    When a member runs "/bonfire ignite"
    Then the state row passes through vm_state "out" and ends in "igniting"
    And a VM start is requested exactly once
    And the reply is message "igniting"

  @unit
  Scenario: Extinguish with a dead agent is finished by the next handler
    Given the bonfire is extinguishing with lock_until 1 minute in the past
    And the VM power state is running
    When a member runs "/bonfire check"
    Then a VM deallocate is requested by the Function exactly once
    And the reply is message "status_extinguishing"
```

- [ ] **Step 3: Write `tests/features/check.feature`**

```gherkin
Feature: Check the bonfire
  The status reply is posted in channel and chosen by the rules in docs/contracts/discord.md.

  Background:
    Given idle_timeout_minutes is 45

  @unit
  Scenario: Check while out
    Given the bonfire is out
    When a member runs "/bonfire check"
    Then the Function acknowledges with a deferred channel reply
    And the reply is message "status_out"
    And a "command/check" event is recorded

  @unit
  Scenario: Check while igniting
    Given the bonfire is igniting since 1 minute ago
    When a member runs "/bonfire check"
    Then the reply is message "status_igniting" with m 1

  @unit
  Scenario: Check while lit with players
    Given the bonfire is lit with 3 players online, lit for 1 hour 20 minutes
    When a member runs "/bonfire check"
    Then the reply is message "status_lit" with n 3, h 1, mm 20

  @unit
  Scenario: Check while lit with nobody online
    Given the bonfire is lit with 0 players online, lit for 2 hours 5 minutes
    And idle_since is 13 minutes ago
    When a member runs "/bonfire check"
    Then the reply is message "status_lit_idle" with h 2, mm 05, r 32

  @unit
  Scenario: Check while the player count is unknown
    Given the bonfire is lit and the last player count is unknown
    When a member runs "/bonfire check"
    Then the reply is message "status_lit_unknown"

  @unit
  Scenario: Check while the game is down
    Given the bonfire is lit and last_health is "crashed"
    When a member runs "/bonfire check"
    Then the reply is message "status_lit_crashed"

  @unit
  Scenario: Check while extinguishing
    Given the bonfire is extinguishing
    When a member runs "/bonfire check"
    Then the reply is message "status_extinguishing"
```

- [ ] **Step 4: Verify**

Run: `python3 scripts/check_docs.py && grep -c 'Scenario:' tests/features/ignite.feature tests/features/extinguish.feature tests/features/check.feature`
Expected: `OK` and counts 8, 13, 7.

- [ ] **Step 5: Commit**

```bash
git add tests/features/ignite.feature tests/features/extinguish.feature tests/features/check.feature
git commit -m "$(cat <<'MSG'
Add feature files for ignite, extinguish and check

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_019c6Rp3J5mVAC8oVoAceqPG
MSG
)"
```

---

### Task 12: Feature files for idle shutdown, concurrency and watchdog

**Files:**
- Create: `tests/features/idle-shutdown.feature`
- Create: `tests/features/concurrency.feature`
- Create: `tests/features/watchdog.feature`

**Interfaces:**
- Consumes: step phrasing from Task 11; PRD 7.3 logic; decisions D4, D9.

- [ ] **Step 1: Write `tests/features/idle-shutdown.feature`**

```gherkin
Feature: Agent check: idle shutdown, warnings and health
  The agent runs these rules on every check. An unknown player count never extinguishes.
  The unknown alert threshold is the 60-minute constant in docs/contracts/configuration.md.

  Background:
    Given idle_timeout_minutes is 45
    And idle_warning_minutes is "15,5"
    And idle_check_interval is 1
    And the bonfire is lit

  @unit
  Scenario: The idle timer starts on the first zero-player check
    Given idle_since is null
    And the adapter reports 0 players
    When the agent runs its check at 20:00
    Then idle_since is 20:00
    And warnings_posted is ""
    And no message is posted

  @unit
  Scenario: A player before any warning resets the timer silently
    Given idle_since is 10 minutes ago and warnings_posted is ""
    And the adapter reports 2 players
    When the agent runs its check
    Then idle_since is null
    And no message is posted

  @unit
  Scenario: First warning when 15 minutes remain
    Given idle_since is 30 minutes ago and warnings_posted is ""
    And the adapter reports 0 players
    When the agent runs its check
    Then the webhook receives message "warning" with w 15
    And warnings_posted is "15"
    And a "watchdog/warning" event is recorded with player_count 0

  @unit
  Scenario: A warning is posted once
    Given idle_since is 31 minutes ago and warnings_posted is "15"
    And the adapter reports 0 players
    When the agent runs its check
    Then no message is posted
    And warnings_posted is "15"

  @unit
  Scenario: Second warning when 5 minutes remain
    Given idle_since is 40 minutes ago and warnings_posted is "15"
    And the adapter reports 0 players
    When the agent runs its check
    Then the webhook receives message "warning" with w 5
    And warnings_posted is "15,5"

  @unit
  Scenario: A player joining after a warning cancels auto-extinguish
    Given idle_since is 32 minutes ago and warnings_posted is "15"
    And the adapter reports 1 player
    When the agent runs its check
    Then the webhook receives message "idle_cancelled"
    And idle_since is null and warnings_posted is ""
    And a "watchdog/idle_cancelled" event is recorded with player_count 1

  @unit
  Scenario: Burn out when the timeout is reached
    Given idle_since is 45 minutes ago and warnings_posted is "15,5"
    And the adapter reports 0 players
    When the agent runs its check
    Then the state row has vm_state "extinguishing", session_ended_at now, and lock_until 5 minutes ahead
    And idle_since is null and warnings_posted is ""
    And the webhook receives message "idle_shutdown"
    And a "watchdog/idle_shutdown" event is recorded with player_count 0
    And the adapter "stop" subcommand is invoked before the deallocate
    And a VM deallocate is requested by the agent exactly once

  @unit
  Scenario: Unknown player count never extinguishes
    Given idle_since is 50 minutes ago and warnings_posted is "15,5"
    And the adapter reports "unknown"
    When the agent runs its check
    Then no VM deallocate is requested
    And the state row has vm_state "lit"
    And idle_since is still 50 minutes ago
    And no message is posted

  @unit
  Scenario: A failing player_count is treated as unknown
    Given idle_since is 50 minutes ago
    And the adapter player_count exits non-zero
    When the agent runs its check
    Then no VM deallocate is requested
    And last_player_count is -1

  @unit
  Scenario: Unknown for over an hour raises one alert
    Given unknown_since is 61 minutes ago and unknown_alerted is false
    And the adapter reports "unknown"
    When the agent runs its check
    Then the webhook receives message "unknown_alert"
    And unknown_alerted is true
    And a "watchdog/unknown_alert" event is recorded

  @unit
  Scenario: The unknown alert is not repeated
    Given unknown_since is 90 minutes ago and unknown_alerted is true
    And the adapter reports "unknown"
    When the agent runs its check
    Then no message is posted

  @unit
  Scenario: A known count ends the unknown streak
    Given unknown_since is 30 minutes ago
    And the adapter reports 0 players
    When the agent runs its check
    Then unknown_since is null and unknown_alerted is false

  @unit
  Scenario: The timer survives an agent restart
    Given the state row has idle_since 20 minutes ago and warnings_posted ""
    And the agent process has just started with no memory of earlier checks
    And the adapter reports 0 players
    When the agent runs its check
    Then idle_since is still 20 minutes ago

  @unit
  Scenario: Every check writes a heartbeat
    Given the adapter reports 2 players and health "ok"
    When the agent runs its check at 20:00
    Then last_heartbeat is 20:00, last_player_count is 2, and last_health is "ok"

  @unit
  Scenario: A crash is announced once and the agent does not restart the game
    Given last_health is "ok"
    And the adapter reports health "degraded" and player count "unknown"
    When the agent runs its check
    Then the webhook receives message "crash"
    And a "game/crash" event is recorded
    And the adapter "start" subcommand is not invoked
    And last_health is "degraded"

  @unit
  Scenario: Docker giving up is announced once
    Given last_health is "degraded"
    And the adapter reports health "crashed" and player count "unknown"
    When the agent runs its check
    Then the webhook receives message "crash_gave_up"
    And a "game/crash_gave_up" event is recorded
    And no VM deallocate is requested
```

- [ ] **Step 2: Write `tests/features/concurrency.feature`**

```gherkin
Feature: Concurrent commands and lock expiry
  A lock in the state row makes transitions exclusive for 5 minutes; expired locks are reconciled.

  @unit
  Scenario: Two ignites at once start the VM once
    Given the bonfire is out
    When member A and member B run "/bonfire ignite" at the same time
    Then exactly one conditional write to the state row succeeds
    And the member whose write succeeded receives message "igniting"
    And the other member receives message "status_igniting"
    And a VM start is requested exactly once

  @unit
  Scenario: A stale ETag is never overwritten
    Given the bonfire is out
    And another writer changes the state row between a handler's read and write
    When the handler writes with the ETag it read
    Then the write fails with a precondition error
    And the handler re-reads the row before deciding what to do

  @unit
  Scenario: An expired lock with a deallocated VM is reconciled to out and ignite proceeds
    Given the bonfire is igniting with lock_until 1 minute in the past
    And the VM power state is deallocated
    When a member runs "/bonfire ignite"
    Then the state row passes through vm_state "out" and ends in "igniting"
    And a VM start is requested exactly once
    And the reply is message "igniting"

  @unit
  Scenario: An expired lock with a running VM and a fresh heartbeat is reconciled to lit
    Given the bonfire is igniting with lock_until 1 minute in the past
    And the VM power state is running
    And last_heartbeat is 1 minute ago
    When a member runs "/bonfire check"
    Then the state row has vm_state "lit" and lock_until null
    And the reply is a status message for state "lit"

  @unit
  Scenario: An active lock blocks state changes while the VM is still running
    Given the bonfire is extinguishing with lock_until 3 minutes ahead
    And the VM power state is running
    When a member runs "/bonfire ignite"
    Then the reply is message "status_extinguishing"
    And the state row is unchanged
```

- [ ] **Step 3: Write `tests/features/watchdog.feature`**

```gherkin
Feature: Safety-net watchdog
  The Function's timer enforces the session ceiling and heartbeat, and never reads the player count.

  Background:
    Given max_session_hours is 12
    And heartbeat_stale_minutes is 20

  @unit
  Scenario: A healthy session is left alone
    Given the bonfire is lit with session_started_at 3 hours ago
    And last_heartbeat is 1 minute ago
    When the safety-net timer runs
    Then no VM deallocate is requested
    And no message is posted
    And the state row is unchanged

  @unit
  Scenario: The ceiling is announced one hour ahead
    Given the bonfire is lit with session_started_at 11 hours 5 minutes ago
    And last_heartbeat is 1 minute ago and ceiling_warned is false
    When the safety-net timer runs
    Then the webhook receives message "watchdog_ceiling_warning" with h 11
    And ceiling_warned is true
    And a "watchdog/ceiling_warning" event is recorded
    And no VM deallocate is requested

  @unit
  Scenario: The ceiling warning is posted once
    Given the bonfire is lit with session_started_at 11 hours 20 minutes ago
    And last_heartbeat is 1 minute ago and ceiling_warned is true
    When the safety-net timer runs
    Then no message is posted

  @unit
  Scenario: The session ceiling extinguishes regardless of players
    Given the bonfire is lit with session_started_at 12 hours 1 minute ago
    And last_heartbeat is 1 minute ago and last_player_count is 4
    When the safety-net timer runs
    Then the state row has vm_state "extinguishing" and session_ended_at now
    And a VM deallocate is requested by the Function exactly once
    And the webhook receives message "watchdog_ceiling"
    And a "watchdog/ceiling" event is recorded with player_count 4

  @unit
  Scenario: A missing heartbeat extinguishes
    Given the bonfire is lit with session_started_at 2 hours ago
    And last_heartbeat is 21 minutes ago
    When the safety-net timer runs
    Then the state row has vm_state "extinguishing"
    And a VM deallocate is requested by the Function exactly once
    And the webhook receives message "watchdog_heartbeat"
    And a "watchdog/heartbeat_missing" event is recorded

  @unit
  Scenario: A missing heartbeat while igniting is tolerated for heartbeat_stale_minutes
    Given the bonfire is igniting since 3 minutes ago
    And last_heartbeat is null
    When the safety-net timer runs
    Then no VM deallocate is requested

  @unit
  Scenario: A boot that never reports in is a failed ignite
    Given the bonfire is igniting since 21 minutes ago
    And last_heartbeat is null
    And the VM power state is running
    When the safety-net timer runs
    Then the state row has vm_state "extinguishing" and session_ended_at now
    And a VM deallocate is requested by the Function exactly once
    And the webhook receives message "watchdog_boot_failed"
    And a "watchdog/boot_failed" event is recorded

  @unit
  Scenario: Drift: the row says out but the VM is running and the agent is silent
    Given the bonfire is out
    And the VM power state is running
    And last_heartbeat is 25 minutes ago
    When the safety-net timer runs
    Then a VM deallocate is requested by the Function exactly once
    And the webhook receives message "watchdog_heartbeat"

  @unit
  Scenario: Extinguishing with an expired lock and a running VM is finished by the timer
    Given the bonfire is extinguishing with lock_until 1 minute in the past
    And the VM power state is running
    When the safety-net timer runs
    Then a VM deallocate is requested by the Function exactly once
```

- [ ] **Step 4: Verify**

Run: `python3 scripts/check_docs.py && grep -c 'Scenario:' tests/features/idle-shutdown.feature tests/features/concurrency.feature tests/features/watchdog.feature`
Expected: `OK` and counts 16, 5, 9.

- [ ] **Step 5: Commit**

```bash
git add tests/features/idle-shutdown.feature tests/features/concurrency.feature tests/features/watchdog.feature
git commit -m "$(cat <<'MSG'
Add feature files for idle shutdown, concurrency and watchdog

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_019c6Rp3J5mVAC8oVoAceqPG
MSG
)"
```

---

### Task 13: Valheim adapter feature file

**Files:**
- Create: `tests/features/adapter-valheim.feature`
- Modify: `docs/contracts/adapter-interface.md` (restore TODO-LINK)

**Interfaces:**
- Consumes: the adapter contract (Task 6); PRD 7.6 Valheim notes.

- [ ] **Step 1: Write the feature file**

```gherkin
Feature: Valheim adapter conformance
  Instantiates the conformance checklist in docs/contracts/adapter-interface.md for games/valheim.
  Contract scenarios run on any Docker host with the real image; e2e scenarios run on the pilot VM.

  Background:
    Given BONFIRE_GAME is "valheim"
    And BONFIRE_ADAPTER_DIR is the games/valheim directory
    And BONFIRE_DATA_DIR is an empty temporary directory
    And BONFIRE_BACKUP_DIR is an empty temporary directory
    And BONFIRE_STOP_GRACE_SECONDS is 60, copied from adapter.json
    And the valheim server password is provided in the environment

  @contract
  Scenario: adapter.json declares ports and the two tunables
    Given the games/valheim directory
    When adapter.json is parsed
    Then ports contains 2456/udp and 2457/udp
    And stop_grace_seconds is 60 and ready_timeout_minutes is 10

  @contract
  Scenario: install pulls the image
    Given the image is not present locally
    When "adapter.sh install" runs
    Then it exits 0 within 15 minutes
    And the image is present locally

  @contract
  Scenario: start brings the container up
    Given the image is present locally
    When "adapter.sh start" runs
    Then it exits 0 within 2 minutes
    And a container for the adapter is running

  @contract
  Scenario: is_ready reports not ready before the game listens
    Given the container started 5 seconds ago
    When "adapter.sh is_ready" runs
    Then it exits 1 within 10 seconds

  @contract
  Scenario: is_ready reports ready once A2S answers
    Given the container is running and A2S on 127.0.0.1:2457 answers
    When "adapter.sh is_ready" runs
    Then it exits 0 within 10 seconds

  @contract
  Scenario: player_count prints 0 with nobody connected
    Given the game is ready
    When "adapter.sh player_count" runs
    Then it exits 0 and prints exactly "0"

  @contract
  Scenario: player_count prints unknown when the game is unreachable
    Given the container is stopped
    When "adapter.sh player_count" runs
    Then it exits 0 and prints exactly "unknown"

  @contract
  Scenario: health reports ok while running
    Given the game is ready
    When "adapter.sh health" runs
    Then it exits 0 and prints exactly "ok"

  @contract
  Scenario: health reports degraded while Docker restarts the container
    Given the game process was killed and Docker is restarting the container
    When "adapter.sh health" runs
    Then it exits 0 and prints exactly "degraded"

  @contract
  Scenario: health reports crashed when Docker has given up
    Given the container has exited after three failed restarts
    When "adapter.sh health" runs
    Then it exits 0 and prints exactly "crashed"

  @contract
  Scenario: stop saves the world cleanly
    Given the game is ready and a world file exists in BONFIRE_DATA_DIR
    When "adapter.sh stop" runs
    Then it exits 0 within 120 seconds
    And no container for the adapter is running
    And the world file was modified after stop began

  @contract
  Scenario: backup copies the world files
    Given a world file exists in BONFIRE_DATA_DIR
    When "adapter.sh backup" runs
    Then it exits 0 within 5 minutes
    And BONFIRE_BACKUP_DIR contains a copy of every world file

  @contract
  Scenario: Every subcommand writes only its value to stdout
    Given the game is ready
    When each subcommand in the contract runs
    Then stdout contains nothing beyond the value the contract specifies

  @e2e
  Scenario: player_count reflects a real connection
    Given the game is ready on the pilot VM
    When a player connects to BONFIRE_PUBLIC_ADDRESS
    Then "adapter.sh player_count" prints "1" within 60 seconds
    When the player disconnects
    Then "adapter.sh player_count" prints "0" within 60 seconds

  @e2e
  Scenario: A2S answers with crossplay enabled
    Given the compose file enables crossplay
    And the game is ready on the pilot VM
    When "adapter.sh is_ready" and "adapter.sh player_count" run
    Then is_ready exits 0 and player_count prints an integer

  @e2e
  Scenario: Start to ready within the target on the pilot VM
    Given the VM has just booted and the image is present
    When "adapter.sh start" runs and is_ready is polled every 10 seconds
    Then is_ready exits 0 within 3 minutes of start
```

- [ ] **Step 2: Restore the TODO-LINK** in `docs/contracts/adapter-interface.md` to `../../tests/features/adapter-valheim.feature`.

- [ ] **Step 3: Verify**

Run: `python3 scripts/check_docs.py && grep -rn TODO-LINK docs/ | wc -l && grep -c 'Scenario:' tests/features/adapter-valheim.feature`
Expected: `OK`, `0`, `16`.

- [ ] **Step 4: Commit**

```bash
git add tests/features/adapter-valheim.feature docs/contracts/adapter-interface.md
git commit -m "$(cat <<'MSG'
Add Valheim adapter conformance feature file

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_019c6Rp3J5mVAC8oVoAceqPG
MSG
)"
```

---

### Task 14: PRD v0.4

**Files:**
- Modify: `docs/prd.md`

**Interfaces:**
- Consumes: every document created in Tasks 2 to 13.
- Produces: a PRD that links rather than repeats.

- [ ] **Step 1: Update the header**

Change `**Version:** 0.3` to `**Version:** 0.4` and add after the existing changelog line:

```markdown
**Changelog v0.3 → v0.4:** decisions moved to ADRs; Terraform layout and sequences moved to architecture.md; adapter interface, configuration, data model and Discord messages moved to contracts/; prior art moved to prior-art.md. This document now links instead of repeating.
```

- [ ] **Step 2: Replace section 6**

Delete everything from `## 6. Architecture decisions` up to (not including) `## 7. Functional requirements`, and insert:

```markdown
## 6. Architecture decisions

Each decision is recorded in an ADR under [adr/](adr/README.md). The system-level design that follows from them is in [architecture.md](architecture.md).

| Decision | Summary | ADR |
|---|---|---|
| Compute | One VM running Docker; the adapter is a container | [0001](adr/0001-compute-vm-plus-docker.md) |
| VM size | D4as v5, not the burstable B4as v2 | [0002](adr/0002-vm-size-d4as-v5.md) |
| Controller | Azure Function as the Discord Interactions Endpoint; no persistent bot | [0003](adr/0003-controller-azure-function-interactions-endpoint.md) |
| Watchdog | On-VM agent is primary; the Function is the safety net | [0004](adr/0004-watchdog-local-agent-primary-function-safety-net.md) |
| Storage | Table Storage for state, Cosmos serverless for events, Key Vault, Blob backups | [0005](adr/0005-storage-table-cosmos-keyvault-blob.md) |
| Infrastructure as code | Terraform for everything; the VM is disposable | [0006](adr/0006-infrastructure-as-code-terraform.md) |

Timing and other tunables are defined in [contracts/configuration.md](contracts/configuration.md).
```

- [ ] **Step 3: Trim section 7**

- In 7.1, keep the command table. Add below it: `Exact reply copy and the interaction flow are in [contracts/discord.md](contracts/discord.md).`
- In 7.2, keep the two bullets. Add: `Lock fields and ETag rules are in [contracts/data-schema.md](contracts/data-schema.md#lock-semantics).`
- In 7.3, keep the pseudo-code and the persistence sentence; keep the v1.5 paragraph. Add: `Scenarios: [tests/features/idle-shutdown.feature](../tests/features/idle-shutdown.feature).`
- In 7.4, keep the list. Add: `Copy for every message is in the [message catalog](contracts/discord.md#message-catalog).`
- Replace 7.6 entirely with:

```markdown
### 7.6 Adapter interface

The core knows no game. Each game is an adapter in `games/<name>/` implementing [contracts/adapter-interface.md](contracts/adapter-interface.md). The safety rule that an `unknown` player count never extinguishes is part of that contract.

**Valheim adapter (pilot):**
- Image: `lloesche/valheim-server` (SteamCMD built in, auto-update).
- `player_count`: Steam A2S_INFO query on `127.0.0.1:2457`. Fallback: log parsing (`Got connection SteamID` / `Closing socket`).
- `is_ready`: A2S responds.
- Ports: 2456–2457/UDP.
- Known risk: with `-crossplay` (PlayFab) A2S may behave differently; test in phase 0.
- Conformance: [tests/features/adapter-valheim.feature](../tests/features/adapter-valheim.feature).
```

- [ ] **Step 4a: Amend the ceiling exception in section 8**

Change the bullet `- Zero shutdowns with a player connected.` to `- Zero shutdowns with a player connected, except the announced session ceiling (ADR 0004).`

- [ ] **Step 4: Replace section 9**

```markdown
## 9. Data model

Defined in [contracts/data-schema.md](contracts/data-schema.md): one Table Storage row for operational state and a Cosmos `events` container with a 90-day TTL. The metrics in section 11 are computed from `events`; the queries are listed at the end of that contract.
```

- [ ] **Step 5: Update section 13**

Keep the comparison table and the "What makes Bonfire different" paragraph. Add as the first line of the section: `A broader survey and code-level notes on the closest projects are in [prior-art.md](prior-art.md).`

- [ ] **Step 6: Verify no duplicated content remains**

```bash
python3 scripts/check_docs.py
for s in "burst credits" "AKS rejected" "System node pool" "prevent_destroy" "print an integer" "lock_until" "idle_check_interval  = 1"; do
  printf '%-28s %s\n' "$s" "$(grep -c "$s" docs/prd.md)"
done
grep -c '](adr/\|](contracts/\|](architecture.md\|](prior-art.md\|](../tests/' docs/prd.md
wc -l docs/prd.md
```

Expected: `OK`; every sentinel count `0`; at least 14 internal links; under 260 lines.

Note: `prior-art.md` does not exist until Task 15. If Task 15 has not run yet, apply the TODO-LINK holding pattern to that one link and let Task 15 restore it.

- [ ] **Step 7: Commit**

```bash
git add docs/prd.md
git commit -m "$(cat <<'MSG'
PRD v0.4: link to ADRs and contracts instead of repeating them

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_019c6Rp3J5mVAC8oVoAceqPG
MSG
)"
```

---

### Task 15: Prior-art survey

This task needs web access (WebSearch and WebFetch). It is independent of Tasks 2 to 14 except for the final link restore.

**Files:**
- Create: `docs/prior-art.md`
- Modify: `docs/prd.md` (restore the TODO-LINK if Task 14 left one)

**Interfaces:**
- Consumes: PRD section 13 and references R7 to R11.
- Produces: the survey the PRD links; patterns that the Phase 1 spec may cite.

- [ ] **Step 1: Research the survey candidates**

For each project below, fetch its README (and for the three code-level projects, the source files named in Step 3) and record: what it does, cloud or host, trigger (command, voice, connection, schedule), shutdown signal (player count, traffic, timer, none), IaC, last activity date, licence.

Candidates; add any others found while searching for "discord bot start stop game server cloud" and "on-demand game server autoscale to zero":

1. nichogx/game-servers-manager-bot (R7)
2. CoderCoco/game-server-deploy (R8)
3. Azure VM start/stop from Discord voice activity, the article in R9
4. timvisee/lazymc (R10)
5. coding-kiko/mc-server-control-dc-bot, ModzabazeR/simple-mc-bot, DeMislead/Discord-GS-Bot (R11)
6. gekware/minecraft-server-hibernation
7. haveachin/infrared (Minecraft proxy with wake-on-connect)
8. Pterodactyl panel
9. CubeCoders AMP
10. LinuxGSM
11. Crafty Controller
12. Microsoft Start/Stop VMs v2 (Azure Functions sample)
13. AWS Instance Scheduler
14. Agones (Kubernetes game-server orchestration)
15. Azure PlayFab Multiplayer Servers

- [ ] **Step 2: Write the survey table**

`docs/prior-art.md` begins:

```markdown
# Prior art

Retrieved 2026-09-08. The comparison the PRD uses to position Bonfire is in [prd.md section 13](prd.md#13-prior-art); this file is the wider survey behind it and the code-level notes that feed the contracts.

## Survey

| Project | What it does | Host | Trigger | Shutdown signal | IaC | Activity | Licence |
|---|---|---|---|---|---|---|---|
```

One row per project from Step 1, at least ten rows. After the table, one paragraph: what the field mostly does (persistent bots, single game, AWS or self-hosted), and the three gaps Bonfire fills (Azure, serverless bot, player-count shutdown with the unknown rule).

- [ ] **Step 3: Write the code-level patterns section**

```markdown
## Patterns from the closest projects

For each pattern: where it lives in the source, what it does, and whether Bonfire copies, adapts, or avoids it.
```

Cover, with a link to the specific file and a two-to-four-sentence note each:

- **nichogx/game-servers-manager-bot**: the start → wait-for-ready → post-address loop; the player-count poll and its interval; how it decides "empty".
- **CoderCoco/game-server-deploy**: Lambda handler for the Interactions Endpoint, especially signature verification and the deferred-response edit; the Terraform layout; the traffic-based watchdog and why Bonfire avoids it.
- **timvisee/lazymc**: the per-server config shape and the sleep/wake state machine; what its adapter-like boundary looks like; why wake-on-connect does not transfer to a UDP game behind a deallocated VM.

End the section with a bulleted list titled **Adopted**, naming each pattern Bonfire copies and the Bonfire document it landed in.

- [ ] **Step 4: Verify**

Run:

```bash
python3 scripts/check_docs.py
grep -c '^| \[' docs/prior-art.md
grep -c 'https://github.com/' docs/prior-art.md
wc -l docs/prior-art.md
```

Expected: `OK`; at least 10 survey rows; at least 12 GitHub links (the three code-level projects link individual files); under 300 lines. If Task 14 left a TODO-LINK in `docs/prd.md`, restore it and re-run the checker.

- [ ] **Step 5: Commit**

```bash
git add docs/prior-art.md docs/prd.md
git commit -m "$(cat <<'MSG'
Add prior-art survey and code-level patterns

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_019c6Rp3J5mVAC8oVoAceqPG
MSG
)"
```

---

### Task 16: Acceptance check and README

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: everything.
- Produces: a README that routes a reader to the right document.

- [ ] **Step 1: Run the spec's acceptance list**

```bash
python3 scripts/check_docs.py
grep -rn TODO-LINK docs/ tests/ ; echo "todo-links: $?"
ls docs/adr docs/contracts tests/features
grep -c 'Scenario:' tests/features/*.feature
wc -l docs/*.md docs/adr/*.md docs/contracts/*.md | sort -n | tail -5
```

Expected: `OK`; `todo-links: 1` (grep found nothing); six ADRs plus README, four contracts, seven feature files; scenario counts 8, 13, 7, 16, 5, 9, 16; no file over 300 lines.

- [ ] **Step 2: Replace `README.md`**

```markdown
# bonfire

🔥 On-demand game server. Anyone in the Discord group lights the bonfire; it burns out by itself when nobody is playing.

Bonfire starts and stops one dedicated game server VM on Azure from Discord slash commands, warns the channel as the idle timer runs down, and extinguishes the server after a configurable time with no players. Games are adapters; Valheim is the first.

## Documents

| Read | For |
|---|---|
| [docs/prd.md](docs/prd.md) | What Bonfire is for, requirements, metrics, roadmap |
| [docs/architecture.md](docs/architecture.md) | Components, state machine, sequences, glossary |
| [docs/adr/](docs/adr/README.md) | Why each architecture decision was made |
| [docs/contracts/](docs/contracts/adapter-interface.md) | The adapter CLI, configuration, data schema and Discord contracts code is written against |
| [docs/testing.md](docs/testing.md) | Test levels and fakes |
| [tests/features/](tests/features/idle-shutdown.feature) | Gherkin scenarios for every behaviour |
| [docs/prior-art.md](docs/prior-art.md) | Similar tools and the patterns borrowed from them |

Status: documentation complete; Phase 0 (Terraform and the Valheim adapter) not started.
```

- [ ] **Step 3: Verify and commit**

Run: `python3 scripts/check_docs.py`
Expected: `OK`.

```bash
git add README.md
git commit -m "$(cat <<'MSG'
README: route readers to the documentation map

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_019c6Rp3J5mVAC8oVoAceqPG
MSG
)"
```

---

## Self-review

**Spec coverage.** Spec section 3 layout: every path appears in a task (ADR files Tasks 2 to 4; architecture Task 5; four contracts Tasks 6 to 9; testing Task 10; seven feature files Tasks 11 to 13; PRD Task 14; prior-art Task 15). Spec 4.1 PRD changes: each bullet is a step in Task 14. Spec 4.2 architecture contents: components, layout, state machine, sequences, glossary, security in Task 5; crash handling added per D10 (Docker-owned). Spec 4.3 to 4.10: matched one to one. Spec 4.11 per-phase specs are out of this plan by design. Spec section 7 acceptance: Task 16 Step 1 runs it.

**Placeholders.** The only forward references are the TODO-LINK holding comments, each of which names the task that removes it, and Task 16 asserts none remain.

**Consistency.** Field names in feature files (`idle_since`, `warnings_posted`, `unknown_since`, `unknown_alerted`, `last_heartbeat`, `last_player_count`, `last_health`, `ceiling_warned`, `session_started_at`, `session_ended_at`, `lock_until`, `hours_this_month`, `pending_command`) match Task 8. Message IDs in feature files match the Task 9 catalog. Configuration names in Backgrounds match Task 7. Action names in events match the Task 8 enum, including `vm/deallocated`, `watchdog/ceiling_warning`, `watchdog/ceiling`, `watchdog/heartbeat_missing`, `watchdog/boot_failed`, `watchdog/unknown_alert`, `game/crash`, `game/crash_gave_up`. The Task 8 row count of 37 assumes 17 state fields, 4 values-per-state rows, 11 event fields, the action table header and 4 action rows as written.
