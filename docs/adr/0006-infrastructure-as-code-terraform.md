# 0006. Infrastructure as code: Terraform

**Status:** Accepted, amended 2026-09-12 (see Amendment)
**Date:** 2026-09-08

## Context

The whole stack must come up from `terraform apply` on an empty subscription, and the VM must be disposable without losing saves ([PRD](../prd.md) section 3). Day-to-day start and stop are not provisioning and stay out of Terraform.

## Decision

Terraform provisions every Azure resource. The repository is laid out so that each concern is one module:

```
infra/
  bootstrap/   one-time script creating the Terraform state storage account
  modules/
    network/     vnet, subnet, nsg (rules from the adapter's adapter.json), static public IP (Standard)
    vm/          D4as v5, Premium OS disk, separate data disk, managed identity, cloud-init
    iam/         VM -> may deallocate itself, read its secret, write backups; later: function -> VM Contributor
    secrets/     key vault (RBAC) + the game password
    backup/      storage account + "backups" container with a 7-day lifecycle rule
    controller/  (Phase 1) function app, storage account, table, app settings
    data/        (Phase 1) cosmos serverless, events container
  envs/
    pilot/       root module, backend.hcl, terraform.tfvars
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

- Adapters declare their ports in `adapter.json`, not a `.tf` file: Terraform cannot select a `.tf` file or module source by variable, but it can read `jsondecode(file("${path.root}/../../../games/${var.game}/adapter.json")).ports`. The root module is `infra/envs/pilot`, three levels below the repository root.
- Terraform needs a state backend. The pilot uses an `azurerm` backend in a small bootstrap storage account created once outside Terraform; the Phase 0 spec details the bootstrap.
- Configuration values flow from Terraform variables to Function app settings and the agent's environment file; the mapping is in [contracts/configuration.md](../contracts/configuration.md).
- Destroying and re-creating the VM keeps the data disk and its saves.

## Amendment (2026-09-12): where "everything is `terraform apply`" bends

The decision stands; the Phase 1 apply showed its edges.

- **The Function package is published outside Terraform.** `azurerm` 4.81 cannot publish a zip to a Flex Consumption app; the CLI can ([ADR 0009](0009-function-hosting-flex-consumption.md)). Until a deploy script or the CI apply path exists, a code change to `bonfire/` or `function/` is Terraform for the settings plus one `az functionapp deployment source config-zip` call. Terraform still detects the change, because the zip path carries a content hash of `dist/function`; that hash requires `scripts/build-function.sh` to have run before every plan and ignores `__pycache__` so a stray import between plan and apply cannot desynchronise it.
- **The VM's contents come from git, not only from Terraform.** Phase 1 chose to pull `bonfire_git_ref` on every boot, so a merged change reaches the VM at the next ignite without an apply. The corollary is that the ref must point at the branch under test: the first Phase 1 replacement cloned `main`, which had no agent, and the units did not exist. Cloud-init and the boot units are the bootstrap; the update script re-executes itself after the checkout so that the freshly pulled copy runs the rest of the boot.
- **Every cloud-init change replaces the VM.** Two replacements happened on 2026-09-12 and a third follows the merge (the ref back to `main`); the data disk, its world and the public IP survived both, as the design intended. Replacement is the normal path for configuration changes, not an incident, but it needs an empty server.
- **Two things were done from the CLI and must be brought back:** the owner's Cosmos Data Reader role ([ADR 0005](0005-storage-table-cosmos-keyvault-blob.md) amendment) and `terraform untaint` of the Function app after its failed publish. Neither is drift Terraform would repair; the first is a one-line `iam` addition planned for Phase 1.5.
- **Plan noise to expect:** the `AzureWebJobsStorage` app setting is proposed on every plan (a provider read gap); applying it is a harmless restart.
