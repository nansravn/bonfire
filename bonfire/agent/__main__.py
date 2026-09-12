"""python -m bonfire.agent: one check, then exit (run by bonfire-agent.timer)."""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Mapping

from bonfire.core.config import ConfigError, load_config

REQUIRED = ("BONFIRE_ADAPTER_DIR", "BONFIRE_BACKUP_DIR", "BONFIRE_BACKUP_ACCOUNT_URL", "DISCORD_WEBHOOK_URL")


def main(env: Mapping[str, str] | None = None) -> int:
    env = os.environ if env is None else env
    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="bonfire-agent: %(levelname)s %(message)s")
    try:
        config = load_config(env)
    except ConfigError as exc:
        print(f"bonfire-agent: invalid configuration: {exc}", file=sys.stderr)
        return 2
    missing = [name for name in REQUIRED if not env.get(name)]
    if missing:
        print(f"bonfire-agent: missing {', '.join(missing)}", file=sys.stderr)
        return 2

    from azure.identity import ManagedIdentityCredential

    from bonfire.agent.adapter import ShellAdapter, load_adapter_meta
    from bonfire.agent.backup import BlobBackupStore
    from bonfire.agent.check import AgentClients, run_check
    from bonfire.core.clock import Clock
    from bonfire.core.compute import AzureCompute
    from bonfire.core.discord import HttpWebhook
    from bonfire.core.events import CosmosEventSink
    from bonfire.core.state import AzureStateTable

    adapter_dir = Path(env["BONFIRE_ADAPTER_DIR"])
    meta = load_adapter_meta(adapter_dir)
    credential = ManagedIdentityCredential()
    clients = AgentClients(
        config=config,
        clock=Clock(),
        state=AzureStateTable(config.state_table_endpoint, credential),
        events=CosmosEventSink(config.events_endpoint, credential),
        compute=AzureCompute(config.vm_resource_id, credential),
        webhook=HttpWebhook(env["DISCORD_WEBHOOK_URL"]),
        adapter=ShellAdapter(adapter_dir, {"BONFIRE_STOP_GRACE_SECONDS": str(meta["stop_grace_seconds"])}),
        backup=BlobBackupStore(env["BONFIRE_BACKUP_ACCOUNT_URL"], "backups", credential),
        staging_dir=Path(env["BONFIRE_BACKUP_DIR"]),
        ready_timeout_minutes=int(meta["ready_timeout_minutes"]),
        stop_grace_seconds=int(meta["stop_grace_seconds"]),
    )
    try:
        return run_check(clients)
    except Exception as exc:  # Table, Cosmos or ARM unreachable: log and let the next tick retry
        logging.getLogger("bonfire.agent").error("check aborted: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
