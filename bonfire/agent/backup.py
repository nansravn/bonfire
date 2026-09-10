"""Upload the adapter's backup staging directory to the backups container."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol


class BackupStore(Protocol):
    def upload(self, staging_dir: Path, prefix: str) -> int: ...


class BlobBackupStore:
    def __init__(self, account_url: str, container: str, credential: Any) -> None:
        from azure.storage.blob import ContainerClient

        self._container = ContainerClient(account_url, container, credential=credential)

    def upload(self, staging_dir: Path, prefix: str) -> int:
        count = 0
        for path in sorted(p for p in Path(staging_dir).rglob("*") if p.is_file()):
            name = f"{prefix}/{path.relative_to(staging_dir).as_posix()}"
            with path.open("rb") as fh:
                self._container.upload_blob(name, fh, overwrite=True)
            count += 1
        return count


def clear_staging(staging_dir: Path) -> None:
    for path in sorted(Path(staging_dir).rglob("*"), reverse=True):
        if path.is_file():
            path.unlink()
        elif path.is_dir():
            path.rmdir()
