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
<!-- TODO-LINK: contracts/configuration.md -->
- Configuration values flow from Terraform variables to Function app settings and the agent's environment file; the mapping is in contracts/configuration.md.
- Destroying and re-creating the VM keeps the data disk and its saves.
