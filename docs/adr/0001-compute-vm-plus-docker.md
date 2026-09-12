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
- Disposability was exercised on 2026-09-12: the VM was replaced three times in one day by cloud-init changes, about five minutes each, and the data disk, the world and the static IP survived each replacement.
