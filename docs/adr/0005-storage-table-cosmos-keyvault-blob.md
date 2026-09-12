# 0005. Storage: Table for state, Cosmos for events, Key Vault, Blob

**Status:** Accepted, amended 2026-09-12 (see Amendment)
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

## Amendment (2026-09-12): access paths and backups as built

- **Cosmos has local (key) authentication disabled**, so every reader needs a data-plane role. The agent and the Function hold the built-in Data Contributor through Terraform. The owner's own account, needed to run the PRD section 11 metric queries, was given the built-in Data Reader from the CLI on 2026-09-12, outside Terraform; moving that assignment into the `iam` module is a Phase 1.5 item. The queries themselves work with `azure-cosmos` and `AzureCliCredential`; the first day's events are what section 12 of the Phase 1 spec reports.
- **Table Storage is reached two ways.** Application code (agent and Function) uses managed identity with `Storage Table Data Contributor`. The Functions host itself uses the account key through `AzureWebJobsStorage`, because the provider cannot yet configure identity-based host storage on Flex Consumption ([ADR 0009](0009-function-hosting-flex-consumption.md)). The row's ETag discipline held under real use: three sessions, a race between a handler and the watchdog resolved by a 412 and a re-read, no lost update.
- **Backups happen on every clean extinguish**, not daily: the agent runs the adapter's `backup`, uploads the staging directory under `<session_id>/<timestamp>/` in the `backups` container (44 and 16 files on the first day), then stops the game. The 7-day lifecycle rule prunes them. This is the "data disk lives in the pilot resource group" mitigation the Phase 0 follow-ups asked for; the disk was not moved.
- **Longer-lived world safety is manual for now.** Before the first Phase 1 apply the owner took an incremental snapshot of the data disk into a separate resource group (`rg-bonfire-backups`), outside Terraform, plus a local copy of the world. A snapshot survives `terraform destroy` and a deletion of the pilot resource group, which the 7-day blobs do not. Whether to make that a Terraform-managed policy (Azure Backup for managed disks, or a scheduled snapshot) is a Phase 1.5 question; the cost is cents a month.
