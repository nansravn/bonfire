# Discord contract

Discord is the only control surface. This file defines the command tree, the interaction flow, and every message Bonfire sends.

## Commands

One top-level command `/bonfire` with subcommands, registered per guild (instant propagation) with `PUT /applications/{application_id}/guilds/{guild_id}/commands`.

| Subcommand | Description string | Options | Handler |
|---|---|---|---|
| `ignite` | Light the bonfire (start the server) | none | ignite |
| `start` | Alias of ignite | none | ignite |
| `extinguish` | Put out the bonfire (stop the server) | none | extinguish |
| `stop` | Alias of extinguish | none | extinguish |
| `check` | Is the bonfire lit? Players, uptime, time left | none | check |
| `cost` | Hours lit this month and estimated cost | none | cost |
| `restart` | Restart the game only; the bonfire stays lit (Phase 1.5; not registered in Phase 1) | none | restart |

Registration is `scripts/register-commands.py`, run by the owner with the bot token; it registers the Phase 1 subcommands.

## Interaction flow

1. Discord POSTs to the Function with headers `X-Signature-Ed25519` and `X-Signature-Timestamp`. The Function verifies the Ed25519 signature of `timestamp + raw body` against `DISCORD_PUBLIC_KEY`. Invalid or missing signature: HTTP 401, nothing else.
2. Interaction type 1 (PING): respond `{"type": 1}`.
3. Interaction type 2 (command) and type 3 (button): respond within 3 seconds with a deferred acknowledgement, before any I/O. Commands use response type 5 (`DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE`); buttons use type 6 (`DEFERRED_UPDATE_MESSAGE`).
4. Every reply is in channel, so a `check` answers "is it up?" for everyone. The only ephemeral message is `confirm_not_yours` (`flags: 64`).
5. The handler then does its work and edits the original reply with `PATCH /webhooks/{application_id}/{interaction_token}/messages/@original`. The token is valid for 15 minutes.
6. Messages that happen later (ready, warnings, burn-out) are posted by the agent to the channel webhook `DISCORD_WEBHOOK_URL`, not through an interaction token.

### Extinguish confirmation

When `last_player_count > 0`, the extinguish handler edits its reply to `confirm_extinguish` with two buttons: `Extinguish` (style danger, `custom_id = extinguish:confirm:<user_id>:<unix_ts>`) and `Cancel` (style secondary, `custom_id = extinguish:cancel:<user_id>:<unix_ts>`). When the count is `-1` (unknown), nobody can be shown to be online, so the extinguish proceeds without confirmation and the event's `player_count` is null. Rules:

- Only the user whose ID is in `custom_id` may click. Anyone else gets an ephemeral `confirm_not_yours`.
- If `now - unix_ts > 120` seconds, either click edits the message to `confirm_expired`.
- `Extinguish` proceeds as a confirmed extinguish and edits the message to `extinguished_manual_with_players`.
- `Cancel` edits the message to `confirm_cancelled`.

## Message catalog

Placeholders in braces are substituted; everything else is verbatim. Feature files quote these strings.

| ID | Sent by | Where | Copy |
|---|---|---|---|
| `igniting` | Function | channel | Lighting the bonfire, ~2 min. |
| `status_out` | Function | channel | The bonfire is out. /bonfire ignite to light it. |
| `status_igniting` | Function | channel | The bonfire is igniting ({m} min so far, usually ready in ~2 min). |
| `status_lit` | Function | channel | The bonfire is lit: {n} players online, lit for {h}h {mm}m. |
| `status_lit_idle` | Function | channel | The bonfire is lit: 0 players online, lit for {h}h {mm}m. Burns out in {r} min unless someone joins. |
| `status_lit_unknown` | Function | channel | The bonfire is lit, but the player count is unknown (auto-extinguish paused). Lit for {h}h {mm}m. |
| `status_lit_crashed` | Function | channel | The bonfire is lit but the game is down. Try /bonfire restart. |
| `status_extinguishing` | Function | channel | The bonfire is being extinguished. |
| `ready` | agent | webhook | Bonfire lit — server ready. Connect to {address}. |
| `ignite_failed` | agent | webhook | Failed to ignite: the game did not become ready in {ready_timeout_minutes} min. The VM stays up for diagnosis until the session ceiling. |
| `warning` | agent | webhook | The bonfire will burn out in {w} min with nobody around. |
| `idle_cancelled` | agent | webhook | Someone joined — auto-extinguish cancelled. |
| `idle_shutdown` | agent | webhook | The bonfire burned out after {idle_timeout_minutes} min with no one around. /bonfire ignite to bring it back. |
| `unknown_alert` | agent | webhook | Player count has been unknown for {UNKNOWN_ALERT_MINUTES} min. Auto-extinguish is paused; check the server. |
| `extinguished_manual` | Function | channel | Bonfire extinguished by {user}. |
| `confirm_extinguish` | Function | channel, with buttons | {n} players are online. Extinguish anyway? |
| `extinguished_manual_with_players` | Function | channel | Bonfire extinguished by {user} with {n} players online. |
| `confirm_cancelled` | Function | channel (edited) | Kept lit. |
| `confirm_not_yours` | Function | ephemeral | Only the person who ran /bonfire extinguish can confirm. |
| `confirm_expired` | Function | channel (edited) | This prompt expired. Run /bonfire extinguish again. |
| `restarting` | Function | channel | Restarting the game; the bonfire stays lit. |
| `crash` | agent | webhook | The game crashed; Docker is restarting it. |
| `crash_gave_up` | agent | webhook | The game crashed repeatedly and stays down. Fix it and use /bonfire restart. |
| `watchdog_ceiling_warning` | Function | webhook | The bonfire has been lit for {h} h; the safety net puts it out at {max_session_hours} h. |
| `watchdog_ceiling` | Function | webhook | Safety net: the bonfire has been lit for {max_session_hours} h and was extinguished. /bonfire ignite to bring it back. |
| `watchdog_heartbeat` | Function | webhook | Safety net: no heartbeat from the server for {heartbeat_stale_minutes} min; the bonfire was extinguished. |
| `watchdog_boot_failed` | Function | webhook | Safety net: the server never reported in after {heartbeat_stale_minutes} min; the bonfire was extinguished. Check the VM boot logs. |
| `cost` | Function | channel | Lit {h} h this month: about US${vm} for the VM plus US${fixed} fixed (disks, IP, storage). |

`{user}` is a Discord mention (`<@user_id>`). `{address}` is `BONFIRE_PUBLIC_ADDRESS`. `{vm}` is `hours_this_month × vm_hourly_usd` with two decimals; `{fixed}` is `fixed_monthly_usd`. `{h}` in `status_*` and `cost` is whole hours; `{mm}` is zero-padded minutes.

In v1.5 the `warning`, `idle_cancelled` and `idle_shutdown` rows move from the agent's webhook to the Function so they can carry the keep-it-lit button; their copy does not change.

## Status reply selection

`check`, any redundant `ignite` or `extinguish`, and a `restart` issued while not `lit`, reply with the status message chosen by this order: `vm_state` is `out` → `status_out`; `igniting` → `status_igniting`; `extinguishing` → `status_extinguishing`; `lit` and `last_health = crashed` → `status_lit_crashed`; `lit` and `last_player_count = -1` → `status_lit_unknown`; `lit` and `last_player_count = 0` → `status_lit_idle` with `{r} = idle_timeout_minutes − (now − idle_since)`; otherwise `status_lit`.
