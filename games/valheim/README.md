# Valheim adapter

Implements [the adapter interface](../../docs/contracts/adapter-interface.md) for Valheim.

- **Image:** `lloesche/valheim-server` (SteamCMD built in). Its own backup and update features are disabled; `adapter.sh install` updates, `adapter.sh backup` backs up.
- **Networking:** host mode. Players connect to `<ip>:2456/udp`. The Steam query port 2457 stays loopback-only; the server runs with `SERVER_PUBLIC=true` so A2S answers there.
- **Player count:** Steam A2S `info` on `127.0.0.1:2457` through `a2s_query.py` (needs `python-a2s` in `$BONFIRE_PYTHON`). Fallback: count `Got connection SteamID` minus `Closing socket` in the last 24 h of container logs, only once `Game server connected` has been logged. Otherwise `unknown`.
- **Health:** `ok` while running; `degraded` while Docker restarts the container or when the restart count grew since the last call; `crashed` when the container has exited. Inside the image, supervisord restarts a crashed game process without the container exiting; Docker-level restarts happen only when the whole container dies.
- **Data layout:** `$BONFIRE_DATA_DIR/config` is the container's `/config`. Worlds live under `config/worlds_local/<WORLD_NAME>/` as a directory (`_main.N.db2`, `_main.N.fwl2`, `_main.N.chunks` and `*.chunk` files); older server builds wrote a flat `<WORLD_NAME>.db`/`.fwl` pair instead, which the adapter still handles. `$BONFIRE_DATA_DIR/server` is `/opt/valheim` so the game download survives `compose down`.
- **Environment file** (`$BONFIRE_GAME_ENV_FILE`, default `/etc/bonfire/valheim.env`): `SERVER_NAME`, `WORLD_NAME`, `SERVER_PASS` (5+ characters), `SERVER_PUBLIC=true`, optional `SERVER_ARGS=-crossplay`.
- **Restore a backup:** stop the adapter, copy the world directory (or the legacy `.db`/`.fwl` pair) back into `config/worlds_local/`, start.
