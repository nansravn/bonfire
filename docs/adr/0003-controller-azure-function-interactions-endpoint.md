# 0003. Controller: Azure Function with the Discord Interactions Endpoint

**Status:** Accepted
**Date:** 2026-09-08

## Context

Players control Bonfire through Discord slash commands. Discord offers two ways to receive them: a persistent gateway connection held open by a bot process, or an Interactions Endpoint URL that Discord calls over HTTPS for each command. The controller must be reachable when the game VM is deallocated, and its idle cost must be near zero ([PRD](../prd.md) section 6.3).

## Decision

An Azure Function on the consumption plan is registered as the Discord Interactions Endpoint. Discord delivers each command as an HTTPS request; the Function validates the Ed25519 signature and acts. No process stays running.

## Alternatives considered

### Gateway bot on the game VM

Rejected. The bot would be off whenever the VM is off, so nobody could ignite.

### Gateway bot on a small always-on host

Rejected. An always-on VM or container costs more per month than the whole controller and storage budget of US$3 (PRD section 8), and adds a host to patch.

### Azure Logic Apps

Rejected. Signature validation and the deferred-response flow need code; a Function is the cheaper and simpler home for it.

## Consequences

<!-- TODO-LINK: contracts/discord.md -->
- Discord requires an acknowledgement within 3 seconds. Every handler responds with a deferred acknowledgement first, then edits the reply. The exact flow is in contracts/discord.md.
- Cold starts on the consumption plan are usually under 3 seconds but not guaranteed; the deferred acknowledgement is sent before any I/O to protect the deadline.
- The Function has no gateway connection, so it cannot see voice-channel events. A voice trigger (PRD phase 4) would need a separate gateway process.
- The same pattern is used by CoderCoco/game-server-deploy on AWS Lambda (PRD reference R8).
