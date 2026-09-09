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
