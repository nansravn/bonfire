"""Start, deallocate and read the power state of the one VM through the ARM REST API."""
from __future__ import annotations

from typing import Any, Protocol

ARM = "https://management.azure.com"
API_VERSION = "2024-07-01"
SCOPE = "https://management.azure.com/.default"


class Compute(Protocol):
    def start(self) -> None: ...
    def deallocate(self) -> None: ...
    def power_state(self) -> str: ...


class AzureCompute:
    def __init__(self, vm_resource_id: str, credential: Any, session: Any = None) -> None:
        self._vm = vm_resource_id
        self._credential = credential
        if session is None:
            import requests

            session = requests.Session()
        self._session = session

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._credential.get_token(SCOPE).token}"}

    def _url(self, suffix: str) -> str:
        return f"{ARM}{self._vm}/{suffix}?api-version={API_VERSION}"

    def start(self) -> None:
        self._session.post(self._url("start"), headers=self._headers(), timeout=30).raise_for_status()

    def deallocate(self) -> None:
        self._session.post(self._url("deallocate"), headers=self._headers(), timeout=30).raise_for_status()

    def power_state(self) -> str:
        response = self._session.get(self._url("instanceView"), headers=self._headers(), timeout=30)
        response.raise_for_status()
        codes = [s.get("code", "") for s in response.json().get("statuses", [])]
        for code in codes:
            if code == "PowerState/running" or code == "PowerState/stopped":
                return "running"
            if code == "PowerState/deallocated":
                return "deallocated"
        return "transitioning"
