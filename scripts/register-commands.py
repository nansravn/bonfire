#!/usr/bin/env python3
"""Register the /bonfire guild command tree (docs/contracts/discord.md, Commands).

Environment: DISCORD_APPLICATION_ID, DISCORD_GUILD_ID, DISCORD_BOT_TOKEN.
Guild commands propagate instantly. Run again whenever the tree changes.
"""
import json
import os
import sys
import urllib.request
import urllib.error

USER_AGENT = "DiscordBot (https://github.com/nansravn/bonfire, 0.1)"

SUBCOMMANDS = [
    ("ignite", "Light the bonfire (start the server)"),
    ("start", "Alias of ignite"),
    ("extinguish", "Put out the bonfire (stop the server)"),
    ("stop", "Alias of extinguish"),
    ("check", "Is the bonfire lit? Players, uptime, time left"),
    ("cost", "Hours lit this month and estimated cost"),
]


def main() -> int:
    try:
        app, guild, token = (os.environ[k] for k in ("DISCORD_APPLICATION_ID", "DISCORD_GUILD_ID", "DISCORD_BOT_TOKEN"))
    except KeyError as exc:
        print(f"missing environment variable {exc}", file=sys.stderr)
        return 2
    body = [{
        "name": "bonfire",
        "description": "On-demand game server",
        "type": 1,
        "options": [{"type": 1, "name": name, "description": desc} for name, desc in SUBCOMMANDS],
    }]
    request = urllib.request.Request(
        f"https://discord.com/api/v10/applications/{app}/guilds/{guild}/commands",
        data=json.dumps(body).encode(), method="PUT",
        headers={"Authorization": f"Bot {token}", "Content-Type": "application/json", "User-Agent": USER_AGENT},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            registered = json.load(response)
    except urllib.error.HTTPError as exc:
        print(f"Discord returned {exc.code}: {exc.read().decode(errors='replace')[:300]}", file=sys.stderr)
        return 1
    names = [o["name"] for o in registered[0]["options"]]
    print(f"registered /bonfire with subcommands: {', '.join(names)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
