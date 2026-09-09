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
