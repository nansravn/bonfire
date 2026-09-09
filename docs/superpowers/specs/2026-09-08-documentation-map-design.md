# Bonfire documentation map — design

**Date:** 2026-09-08
**Status:** Approved in brainstorming; awaiting written review
**Input:** `docs/prd.md` (PRD v0.3)

## 1. Purpose

Define which documents Bonfire keeps, what each one holds, where it lives, and in what order they are written. The documentation is a working spec: its readers are the owner and AI coding agents, and code is written against it. Precision beats narrative; small, focused files beat one large one.

## 2. Decisions taken in brainstorming

| Question | Decision |
|---|---|
| Audience | Owner plus AI agents, as the working spec. |
| Design granularity | One system-level architecture doc, then one design spec and one implementation plan per roadmap phase, written as each phase starts. |
| Test cases | Gherkin scenarios, one `.feature` file per behavior, mapping one-to-one to automated tests. |
| Settled decisions | Backfill the six decisions in PRD section 6 as ADRs now. |
| Prior art | A broader survey beyond PRD section 13, ending with a code-level section on the three closest projects. |
| Feature file location | `tests/features/`, because every BDD runner reads from there and the files are meant to execute. |
| Discord and data contracts | Written before Phase 0 along with the rest, since the PRD already drafts them and the extra cost is small. |

## 3. Layout

```
docs/
  prd.md                       PRD, v0.4 once slimmed (section 4)
  architecture.md              system-level design, written once
  adr/
    README.md                  index and the ADR template
    0001-compute-vm-plus-docker.md
    0002-vm-size-d4as-v5.md
    0003-controller-azure-function-interactions-endpoint.md
    0004-watchdog-local-agent-primary-function-safety-net.md
    0005-storage-table-cosmos-keyvault-blob.md
    0006-infrastructure-as-code-terraform.md
  contracts/
    adapter-interface.md       the game-adapter CLI contract
    configuration.md           Terraform variables -> Function settings -> agent env
    data-schema.md             Table `state` row and Cosmos `events` document
    discord.md                 /bonfire subcommands, responses, message catalog
  testing.md                   test levels and what runs without Azure
  prior-art.md                 broader survey plus code-level patterns to reuse
  superpowers/
    specs/                     one design spec per phase
    plans/                     the matching implementation plans
tests/
  features/
    ignite.feature
    extinguish.feature
    check.feature
    idle-shutdown.feature
    concurrency.feature
    watchdog.feature
    adapter-valheim.feature
```

Three rules govern the layout:

1. **One home per fact.** A fact lives in exactly one file. Other files link to it. The PRD stops repeating what the ADRs and contracts say.
2. **Load-whole files.** Each file stays small enough for an agent to read in full. If a file grows past roughly 300 lines, split it.
3. **Contracts get the most precision and the fewest words.** They are the surfaces code is written against.

## 4. Document contents

### 4.1 `docs/prd.md` (v0.4)

Keeps: summary, problem, goals, non-goals, personas, functional requirements, non-functional requirements, cost estimate, success metrics, risks, roadmap, open questions, references.

Changes from v0.3:

- Section 6 (architecture decisions) becomes a short table: decision, one-line summary, link to the ADR. The alternatives tables and reasoning move into the ADRs.
- Section 6.6 (Terraform layout) moves to `architecture.md`. Section 6.7 (configuration) moves to `contracts/configuration.md`.
- Section 7.6 (adapter interface) shrinks to a paragraph linking `contracts/adapter-interface.md`. The Valheim-specific notes stay in the PRD as the pilot definition.
- Section 9 (data model) becomes a link to `contracts/data-schema.md`.
- Section 13 (prior art) keeps the comparison table and links `prior-art.md` for the survey.
- The changelog gains a v0.3 → v0.4 entry describing the split.

### 4.2 `docs/architecture.md`

The one system-level design. Written once before Phase 0; amended only when an ADR changes it.

Contents:

- **Components.** The four runtime parts and what each owns: the Azure Function (Discord endpoint, safety-net timer), the on-VM agent (idle timer, heartbeat, notifications), the game adapter (container plus `adapter.sh`), and Terraform (provisioning only). One paragraph each, with dependencies named.
- **Repository layout.** The `infra/`, `games/`, `agent/`, `function/` tree, moved from PRD 6.6 and extended to cover the agent and Function code directories.
- **VM state machine.** States: `out`, `igniting`, `lit`, `extinguishing`. Every transition with its trigger, the actor allowed to cause it, and the lock it takes. This is the reference for the concurrency feature file.
- **Sequences.** Ignite (command to ready notification) and idle shutdown (zero players to deallocation), each as a numbered list or Mermaid sequence diagram.
- **Glossary.** lit, out, igniting, extinguishing, ignite, extinguish, keep it lit, adapter, agent, controller, safety net. Agents use these names in code and messages.
- **Security notes.** Discord signature validation, managed identity scopes, Key Vault use, NSG rules from the adapter. A section, not a separate threat model.

### 4.3 `docs/adr/`

Format is MADR-lite: title, status, date, context, decision, alternatives considered, consequences. `README.md` holds the template and an index table.

The six backfilled ADRs are extracted from PRD section 6 with the alternatives already listed there. New decisions (agent language, Function runtime, A2S library, backup method) get the next numbers as they are made, each in its phase spec first and then promoted to an ADR when settled.

### 4.4 `docs/contracts/adapter-interface.md`

Turns PRD 7.6 into a contract. For each subcommand (`install`, `start`, `stop`, `is_ready`, `player_count`, `health`, `backup`): purpose, arguments, exit codes, stdout format, timeout, and idempotency. Plus:

- Working directory and environment variables the core guarantees to the adapter.
- The `unknown` rule stated as a requirement on callers: any caller that receives `unknown` from `player_count` must not extinguish.
- The three adapter files (`docker-compose.yml`, `adapter.sh`, `ports.tf`) and the shape of `ports.tf`.
- A conformance checklist a new adapter must pass, which `tests/features/adapter-valheim.feature` instantiates for Valheim.

### 4.5 `docs/contracts/configuration.md`

Every configuration variable with: name in Terraform, name in Function app settings, name in the agent environment file, type, default, and validation rule. Starts with the four timing variables from PRD 6.7 and grows as phases add settings.

### 4.6 `docs/contracts/data-schema.md`

- **Table Storage `state` row.** Every field with type, meaning, which component writes it, which components read it, and its value in each VM state. Lock semantics for `lock_until`: who takes it, TTL, what happens on expiry.
- **Cosmos `events` document.** Every field with type and allowed values. The `type` and `action` enums pinned. Partition key and TTL stated. Two example documents: a command event and an idle-shutdown event.

### 4.7 `docs/contracts/discord.md`

- Command registration: the `/bonfire` command and each subcommand with its options and description strings, including the `start` and `stop` aliases.
- Interaction flow: the three-second acknowledgement deadline, when to defer, when to reply ephemerally versus in channel, and how follow-ups are posted.
- Signature validation requirements.
- Message catalog: every message the channel can receive (PRD 7.4), with exact copy, trigger, and sender (webhook versus bot). This is the single source for user-facing text.

### 4.8 `docs/testing.md`

Three levels and what each needs:

| Level | Runs where | Exercises | Needs Azure |
|---|---|---|---|
| Unit | Local | Agent idle logic against a fake adapter; Function handlers against signed fake Discord payloads | No |
| Adapter contract | Local Docker | `adapter.sh` conformance for each game | No |
| End-to-end | Real VM | Full ignite-to-ready and idle-to-deallocate paths | Yes |

Maps each feature file to its level. States the fake-adapter approach: a shell script implementing the contract with scripted responses, so idle logic is tested without a game.

### 4.9 `docs/prior-art.md`

- **Survey.** Beyond PRD section 13: hosting panels (Pterodactyl, AMP), other Discord start/stop bots, Azure Automation and Start/Stop VM samples, wake-on-demand proxies. Per project: what it does, provider, trigger, shutdown signal, IaC, status. One table.
- **Patterns to reuse.** Code-level notes on the three closest projects (nichogx/game-servers-manager-bot, CoderCoco/game-server-deploy, timvisee/lazymc): Discord signature validation, wait-for-ready loop, player-count polling, adapter shape. Each pattern links the file in the source repo and says whether Bonfire copies, adapts, or avoids it.

### 4.10 `tests/features/*.feature`

One file per behavior, Gherkin syntax. Scenarios are written from the PRD's functional requirements and the state machine in `architecture.md`. Each scenario names the level it runs at in a tag (`@unit`, `@contract`, `@e2e`).

Initial coverage:

- `ignite.feature`: from out, from lit, from igniting, failure to become ready.
- `extinguish.feature`: with zero players, with players (confirmation), during igniting.
- `check.feature`: each state, time remaining, unknown player count.
- `idle-shutdown.feature`: warnings at each threshold, cancellation on join, `unknown` never extinguishes, timer survives agent restart, alert after 60 minutes of `unknown`.
- `concurrency.feature`: two ignites, extinguish during igniting, lock expiry.
- `watchdog.feature`: session ceiling, missing heartbeat, no trigger when agent healthy.
- `adapter-valheim.feature`: the conformance checklist instantiated for Valheim, including A2S with and without crossplay.

### 4.11 Per-phase specs and plans

Each roadmap phase gets `docs/superpowers/specs/YYYY-MM-DD-phase-N-design.md` and a matching plan, written through the brainstorming and writing-plans skills when the phase starts. A phase spec covers only that phase's components and links the contracts it implements. Decisions made in a phase spec are promoted to ADRs when settled.

## 5. Deferred

- **Runbook** (deploy, add a game, troubleshoot): after the pilot, once procedures are known.
- **Threat model:** only if multi-group or non-Discord authentication ever lands.
- **Cost tracking doc:** PRD section 10 is enough.
- **Contributor guide:** the adapter contract and conformance checklist serve this until a second contributor exists.

## 6. Sequencing

All of the following are written before Phase 0 code starts, in this order because later items link earlier ones:

1. `docs/adr/` README and the six ADRs.
2. `docs/architecture.md`.
3. `docs/contracts/` (all four).
4. `docs/testing.md`.
5. `tests/features/` (all seven).
6. `docs/prd.md` slimmed to v0.4, now that every link target exists.
7. `docs/prior-art.md`. Research; can run in parallel with items 1 to 6.

Then the Phase 0 spec, through the brainstorming skill.

## 7. Acceptance

The map is done when:

- Every file in section 3 exists with the contents in section 4.
- `docs/prd.md` is at v0.4 and contains no content that also lives in an ADR or contract.
- Every link between documents resolves.
- Each feature file has at least the scenarios listed in 4.10, each tagged with a level.
- `docs/prior-art.md` covers at least ten projects in the survey and all three in the patterns section.

## 8. Amendments during execution

Two plan decisions, approved before execution, supersede the text above:

- Section 4.4: adapters declare ports and per-game tunables in `adapter.json`, not `ports.tf`. Terraform cannot select a `.tf` file by variable; it reads `jsondecode(file(...)).ports`. See ADR 0006 and plan decision D1.
- Section 4.10: "extinguish during igniting" is covered in both `extinguish.feature` and `concurrency.feature`; the extinguish file holds the primary scenario.
