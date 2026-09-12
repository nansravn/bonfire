# 0008. The Function acknowledges over HTTP and does its work from a queue

**Status:** Accepted
**Date:** 2026-09-10

## Context

Discord requires an answer to every interaction within 3 seconds ([ADR 0003](0003-controller-azure-function-interactions-endpoint.md)). An Azure Function invocation ends when it returns its HTTP response, so the deferred acknowledgement and the real work (reading the state row, reconciling, starting a VM, recording an event, editing the reply) cannot share one invocation. A cold start alone can consume most of the deadline.

## Decision

Two functions. The HTTP trigger verifies the Ed25519 signature, answers PING, and for commands and buttons puts the raw interaction on a Storage Queue in the Function's own storage account, then returns the deferred acknowledgement. A queue-triggered worker does the work and edits the original reply through the interaction token, which stays valid for 15 minutes. The safety-net timer is a third function in the same app.

## Alternatives considered

### Do the work before responding

Rejected. A cold start plus a table read plus a VM start call overruns the deadline; Discord shows "did not respond" and does not retry.

### Durable Functions

Rejected. An orchestrator, a task hub and several storage tables to solve one hop.

## Consequences

- The HTTP function imports only what signature verification needs, so its cold start stays short; the 15-minute watchdog timer keeps the app warm.
- Two ignites at once become two worker runs racing on the state row's ETag, which is the concurrency model the data schema already defines.
- A reply edit can fail after the state has changed and Azure has acted; the worker records the failure in the event and never rolls the state back.
- No bot token is needed in Phase 1: reply edits use the interaction token and later messages use the channel webhook.
- Observed on 2026-09-12: the Discord portal accepted the endpoint on the first save (the PING answered within the deadline on a cold app), and about ten commands completed with a reply edited roughly 5 seconds after Discord sent them when the worker was cold, well inside the token's 15-minute validity. The queue's `maxDequeueCount` of 2 means a worker crash retries the interaction once; handlers are idempotent enough for that (an ignite retry on a running VM only replies with status, and a failed VM start reverts the row to `out` so the retry does not strand it).
