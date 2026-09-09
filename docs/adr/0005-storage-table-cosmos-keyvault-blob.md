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
<!-- TODO-LINK: contracts/data-schema.md -->
- Concurrency on the state row uses Table Storage ETags: every conditional write sends If-Match and retries on 412. Lock semantics are in contracts/data-schema.md.
- Events expire after 90 days; long-term metrics must be exported before then.
- If the subscription has no Cosmos free-tier account yet, the free tier (1,000 RU/s, 25 GB) is an alternative to serverless with the same schema.
