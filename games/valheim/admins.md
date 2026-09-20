# Valheim admins

Runbook for granting or revoking in-game admin on the Valheim server. The single source of truth is `adminlist.txt` on the data disk, edited over SSH.

## Scope

In-game admin allows `kick`, `ban`, `unban`, `save` and `devcommands` from the F5 console. It grants nothing else: no SSH, no Azure access, no Discord permissions. Grant it to people you trust with the world, since `devcommands` can alter it.

## Rules

- **Never set `ADMINLIST_IDS`** (nor `BANNEDLIST_IDS`, `PERMITTEDLIST_IDS`) in `game_env`. The image rewrites the matching file from the variable on every container start, silently discarding manual edits. The variable is also documented for bare SteamID64s, which Valheim 1.0 ignores.
- **Never type an ID from memory.** Have the member copy it from their F2 panel and cross-check the digits against the server log (step 2).
- **Player IDs stay out of git.** The table at the end of this file records names and nicknames only.
- `adminlist.txt` is **not in the backups**: `adapter.sh backup` covers `config/worlds_local/` only. After a restore onto a fresh disk, redo this runbook for every row of the table.

## What to ask the member

| Item | Why |
|---|---|
| Name and in-game nickname | The table below; finding their line in the log |
| Platform (Steam, Xbox, Game Pass) | Decides the ID prefix |
| The ID shown in their F2 panel, copied in full (`V_…` for Steam) | This is the line that goes in the file |
| A moment when they can be online | Steps 2 and 5 need them connected |

## Add an admin

Prerequisites: the server is `lit` (`/bonfire check`), the operator has SSH access as `bonfire`, the member is connected to the game.

1. Connect: `ssh bonfire@<public_address>` (`terraform output public_address` in `infra/envs/pilot`).
2. Find the member's ID as the server sees it:

   ```bash
   cid=$(sudo docker ps -qf name=valheim)
   sudo docker logs --since 1h "$cid" 2>&1 | grep -iE 'Got connection|Got character ZDOID|PlatformUserID'
   ```

   Match the connection line to the member by time and nickname, and check that its digits equal the ones in the ID they read in F2.

   **ID format (Valheim 1.0 and later):** the entry is the full platform-prefixed ID exactly as the F2 panel shows it, case sensitive. For Steam players that is `V_<SteamID64>`, for example `V_76561198012345678`. A bare SteamID64, accepted before 1.0, is now silently ignored; most hosting guides still show the old form.
3. Append the ID, one per line, nothing else on the line (no names, no comments):

   ```bash
   echo '<id>' | sudo tee -a /data/valheim/config/adminlist.txt
   sudo cat /data/valheim/config/adminlist.txt
   ```

4. Warn whoever is online, then restart the game: `sudo systemctl restart bonfire-game`. The world saves on stop; expect about a minute of downtime. The agent sees zero players meanwhile, which is harmless for a restart this short.
5. Verify: the member reconnects, opens the console (F5) and runs `save`. An admin sees the save confirmation; a non-admin gets no effect. If it fails, compare prefix and case in `adminlist.txt` against the F2 panel, fix, and repeat step 4.
6. Add the member to the table below in a PR.

## Remove an admin

Delete their line (`sudo nano /data/valheim/config/adminlist.txt`), restart as in step 4, and remove their row from the table.

## Current admins

| Name | In-game nickname | Platform | Since |
|---|---|---|---|

## Later

Candidates for a future phase, not built: a `/bonfire admin add` Discord command, and including `adminlist.txt` in `adapter.sh backup`.
