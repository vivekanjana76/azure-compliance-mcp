"""Seeded, synthetic, ARG-shaped data for offline use (SPEC §2).

The dataset is fixed and deterministic. It deliberately includes real gaps — an
untagged VM, VMs missing the guest-configuration extension, and a mix of
pass/fail across all five controls — so every tool returns meaningful data with
zero Azure setup.
"""

from __future__ import annotations

import copy

from providers.base import ResourceRow

SUBSCRIPTION_ID = "00000000-0000-0000-0000-000000000001"


def _vm(
    name: str,
    resource_group: str,
    location: str,
    tags: dict[str, str],
    extensions: list[str],
    encryption_at_host: bool,
) -> ResourceRow:
    return ResourceRow(
        id=(
            f"/subscriptions/{SUBSCRIPTION_ID}/resourceGroups/{resource_group}"
            f"/providers/Microsoft.Compute/virtualMachines/{name}"
        ),
        name=name,
        type="microsoft.compute/virtualmachines",
        resourceGroup=resource_group,
        subscriptionId=SUBSCRIPTION_ID,
        location=location,
        tags=tags,
        properties={"extensions": extensions, "encryptionAtHost": encryption_at_host},
    )


def _storage(
    name: str,
    resource_group: str,
    location: str,
    tags: dict[str, str],
    min_tls_version: str,
    public_network_access: str,
) -> ResourceRow:
    return ResourceRow(
        id=(
            f"/subscriptions/{SUBSCRIPTION_ID}/resourceGroups/{resource_group}"
            f"/providers/Microsoft.Storage/storageAccounts/{name}"
        ),
        name=name,
        type="microsoft.storage/storageaccounts",
        resourceGroup=resource_group,
        subscriptionId=SUBSCRIPTION_ID,
        location=location,
        tags=tags,
        properties={
            "minimumTlsVersion": min_tls_version,
            "publicNetworkAccess": public_network_access,
        },
    )


# Seeded fixture. Comments note the intentional gaps each row exercises.
# Locations are deliberately spread across regions so query_resources location
# filtering is meaningful: eastus x3, westus x2, westeurope x2.
_MOCK_RESOURCES: list[ResourceRow] = [
    # Fully compliant prod VM (all controls pass).
    _vm(
        "vm-web-prod-01",
        "rg-prod",
        "eastus",
        {"env": "prod", "owner": "alice", "costCenter": "CC-1001"},
        ["Microsoft.GuestConfiguration", "AzureMonitorLinuxAgent"],
        True,
    ),
    # Tagged, but missing guest-config extension and disk encryption.
    _vm(
        "vm-web-prod-02",
        "rg-prod",
        "eastus",
        {"env": "prod", "owner": "alice", "costCenter": "CC-1001"},
        ["AzureMonitorLinuxAgent"],
        False,
    ),
    # Partial tags (no owner/costCenter) and no extensions at all.
    _vm(
        "vm-batch-dev-01",
        "rg-dev",
        "westus",
        {"env": "dev"},
        [],
        True,
    ),
    # The untagged VM: zero tags, no encryption (but has guest config).
    _vm(
        "vm-legacy-01",
        "rg-shared",
        "westeurope",
        {},
        ["Microsoft.GuestConfiguration"],
        False,
    ),
    # Fully compliant storage account (all controls pass).
    _storage(
        "stprodassets01",
        "rg-prod",
        "eastus",
        {"env": "prod", "owner": "bob", "costCenter": "CC-2002"},
        "TLS1_2",
        "Disabled",
    ),
    # Tagged, but weak TLS and public network access enabled.
    _storage(
        "stdevscratch01",
        "rg-dev",
        "westus",
        {"env": "dev", "owner": "carol", "costCenter": "CC-3003"},
        "TLS1_0",
        "Enabled",
    ),
    # Partial tags, weak TLS, public access enabled (fails every applicable control).
    _storage(
        "stsharedlogs01",
        "rg-shared",
        "westeurope",
        {"owner": "dave"},
        "TLS1_1",
        "Enabled",
    ),
]


class MockProvider:
    """In-memory ``Provider`` backed by the seeded dataset above."""

    async def list_resources(self) -> list[ResourceRow]:
        # Deep copy so callers cannot mutate the shared fixture.
        return copy.deepcopy(_MOCK_RESOURCES)
