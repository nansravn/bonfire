"""Compute REST calls and power-state mapping (decision P8)."""
import pytest

from bonfire.core.compute import AzureCompute

pytestmark = pytest.mark.unit
VM = "/subscriptions/s/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm-bonfire"


class FakeToken:
    token = "t"


class FakeCredential:
    def get_token(self, scope):
        assert scope == "https://management.azure.com/.default"
        return FakeToken()


class FakeResponse:
    def __init__(self, status, payload=None):
        self.status_code = status
        self._payload = payload or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


class FakeSession:
    def __init__(self, statuses):
        self.calls = []
        self.statuses = statuses

    def post(self, url, headers=None, timeout=None):
        self.calls.append(("POST", url))
        return FakeResponse(202)

    def get(self, url, headers=None, timeout=None):
        self.calls.append(("GET", url))
        return FakeResponse(200, {"statuses": [{"code": s} for s in self.statuses]})


@pytest.mark.parametrize("statuses,expected", [
    (["ProvisioningState/succeeded", "PowerState/running"], "running"),
    (["PowerState/deallocated"], "deallocated"),
    (["PowerState/stopped"], "running"),
    (["PowerState/deallocating"], "transitioning"),
    (["PowerState/starting"], "transitioning"),
    ([], "transitioning"),
])
def test_power_state_mapping(statuses, expected):
    session = FakeSession(statuses)
    assert AzureCompute(VM, FakeCredential(), session=session).power_state() == expected
    assert session.calls[0][1].startswith(f"https://management.azure.com{VM}/instanceView?api-version=")


def test_start_and_deallocate_post_to_the_vm():
    session = FakeSession([])
    compute = AzureCompute(VM, FakeCredential(), session=session)
    compute.start()
    compute.deallocate()
    assert [c[0] for c in session.calls] == ["POST", "POST"]
    assert session.calls[0][1].startswith(f"https://management.azure.com{VM}/start?")
    assert session.calls[1][1].startswith(f"https://management.azure.com{VM}/deallocate?")
