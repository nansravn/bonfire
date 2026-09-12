# Architecture decision records

One file per decision that shapes Bonfire's structure. A decision is recorded once it is settled; proposals live in phase specs until then.

## Index

| ADR | Title | Status |
|---|---|---|
| [0001](0001-compute-vm-plus-docker.md) | Compute: a single VM running Docker | Accepted |
| [0002](0002-vm-size-d4as-v5.md) | VM size: D4as v5 instead of B4as v2 | Accepted, amended 2026-09-10 |
| [0003](0003-controller-azure-function-interactions-endpoint.md) | Controller: Azure Function with the Discord Interactions Endpoint | Accepted, amended 2026-09-12 |
| [0004](0004-watchdog-local-agent-primary-function-safety-net.md) | Watchdog: on-VM agent primary, Function safety net | Accepted, amended 2026-09-12 |
| [0005](0005-storage-table-cosmos-keyvault-blob.md) | Storage: Table for state, Cosmos for events, Key Vault, Blob | Accepted, amended 2026-09-12 |
| [0006](0006-infrastructure-as-code-terraform.md) | Infrastructure as code: Terraform | Accepted, amended 2026-09-12 |
| [0007](0007-test-runner-pytest-bdd.md) | Test runner: pytest-bdd | Accepted |
| [0008](0008-function-ack-then-queue.md) | The Function acknowledges over HTTP and does its work from a queue | Accepted |
| [0009](0009-function-hosting-flex-consumption.md) | Function hosting: Flex Consumption, key-based host storage, CLI deployment | Accepted |

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
