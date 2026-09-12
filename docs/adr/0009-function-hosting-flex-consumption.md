# 0009. Function hosting: Flex Consumption, key-based host storage, CLI deployment

**Status:** Accepted
**Date:** 2026-09-12

## Context

[ADR 0003](0003-controller-azure-function-interactions-endpoint.md) chose an Azure Function as the Discord Interactions Endpoint and assumed the classic Linux Consumption plan (`Y1`). The first Phase 1 `apply` on 2026-09-12 failed creating that plan: the pilot subscription (Visual Studio Enterprise) has a quota of zero `Y1 VMs` in Brazil South (`Current Limit (Y1 VMs): 0`). A quota increase is a support request with no guaranteed outcome on this subscription type, and Microsoft has announced the retirement of the Linux Consumption plan (30 September 2028), so the classic plan is not a long-term option either way.

The controller's budget is under US$3 a month for Function plus storage (PRD section 8). Discord's 3-second acknowledgement deadline is protected by design ([ADR 0008](0008-function-ack-then-queue.md)): the HTTP function only verifies and enqueues, so cold-start latency shows up in the deferred reply, not in the acknowledgement.

What the day's apply and end-to-end runs established about the candidates:

| Plan | Idle cost | Cold start | Fit | Blocker |
|---|---|---|---|---|
| Consumption `Y1` | zero (free grant) | seconds | the original assumption | quota 0 here; plan retiring |
| **Flex Consumption `FC1`** | zero at pilot volume (its own monthly free grant, listed by Microsoft as 250k executions and 100k GB-s at the time of writing) | seconds; a command completed about 5 s end to end with a cold worker | available in Brazil South; Microsoft's forward path | `azurerm` 4.81 gaps (below) |
| App Service `B1` always on | ~US$13 a month | none | removes cold starts entirely | exceeds the controller budget four times over |
| Premium `EP1` | ~US$150 a month | none | | far outside budget |
| Container Apps | zero at scale-to-zero | seconds | | needs the queue and timer triggers rebuilt outside the Functions model; more moving parts for no gain |

Provider gaps found with `azurerm` 4.81.0 against Flex Consumption:

1. `zip_deploy_file` posts to Kudu's `/api/zipdeploy` and waits for the deployment service; on a freshly created Flex app it fails with `waiting for deployment service to be ready: 404`, leaves the resource tainted, and the next plan proposes recreating the app. The same zip publishes through Azure CLI's One Deploy path (`az functionapp deployment source config-zip --build-remote false`) once the SCM site is up, which took about five minutes after creation.
2. In identity mode (`storage_authentication_type = "SystemAssignedIdentity"`) the provider injects an `AzureWebJobsStorage` app setting with an empty account key next to the `AzureWebJobsStorage__accountName` the user sets, so the Functions host would read a malformed connection string. Verified in the provider source; not exercised, because the pilot applies in connection-string mode.
3. In connection-string mode the provider's read does not return the `AzureWebJobsStorage` setting it manages, so every plan shows it being added again (a perpetual diff; the live value is present and correct).
4. Flex publishes the zip as-is: there is no remote build unless the deploying tool requests one, and the provider requests none. The package must therefore carry its dependencies.

## Decision

The Function runs on Flex Consumption (`FC1`, 2048 MB instances, at most 40) in Brazil South.

- The Functions host and the deployment container use the storage account key (`AzureWebJobsStorage`, `DEPLOYMENT_STORAGE_CONNECTION_STRING`) until the provider handles identity-based host storage; the application code keeps using the managed identity for the state table, the events container and compute. The `host_storage_uses_identity` variable stays as the switch, defaulting to `false` until the override for gap 2 is in place.
- `scripts/build-function.sh` vendors the Python dependencies into `.python_packages/lib/site-packages` (manylinux2014, CPython 3.12, wheels only), so the zip is self-contained.
- Terraform still declares `zip_deploy_file` (which changes with the content hash of `dist/function`), but the package is published with `az functionapp deployment source config-zip -g rg-bonfire-pilot -n <function_app_name> --src dist/function-<hash>.zip --build-remote false` after any change to `bonfire/` or `function/`. If an apply leaves the app tainted after a failed publish, `terraform untaint` restores it rather than recreating it.

## Alternatives considered

### Request a `Y1` quota increase

Rejected. Unbounded waiting time, uncertain outcome on a Visual Studio subscription, and a plan with a published retirement date.

### App Service `B1` always on

Rejected for now. It would remove the ~5-second cold reply latency, but costs more per month than the whole controller budget. It becomes the fallback if cold-start latency turns out to matter to players; the deferred acknowledgement already hides it from Discord's deadline.

### Container Apps

Rejected. Scale-to-zero at similar cost, but the queue worker and the timer would have to be rebuilt outside the Functions bindings, and nothing in the pilot needs containers.

## Consequences

- The "everything is `terraform apply`" goal of [ADR 0006](0006-infrastructure-as-code-terraform.md) has one manual step: publishing the Function package. Closing it (a deploy script or the CI apply path) is a Phase 1.5 item.
- Two connection strings with keys live in app settings, an exception to the architecture's security note that secrets reach code only through Key Vault references. Switching to identity mode needs the `AzureWebJobsStorage` override noted in the controller module and a plan review.
- Every plan shows the perpetual `AzureWebJobsStorage` diff until a `lifecycle` ignore is added; applying it is harmless (a restart).
- The 15-minute watchdog keeps a worker warm most of the time; the first command after a quiet period still takes about 5 seconds to complete, within the interaction token's 15-minute validity and behind an immediate acknowledgement.
- Cost stays within the free grant at pilot volume (about 3,000 timer executions and a few hundred commands a month, a small fraction of any published grant); Application Insights ingestion is the only meaningful controller cost.
