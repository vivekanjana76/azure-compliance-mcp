"""Seeded, synthetic, ARG-shaped data for offline use (SPEC §2).

The dataset is fixed and deterministic. ``properties`` are shaped like real Azure
Resource Graph rows (storage ``minimumTlsVersion`` / ``publicNetworkAccess``, VM
``securityProfile.encryptionAtHost``), so the *same* control-mapping logic in
``compliance.py`` runs for both mock and live (the cross-mode equivalence
discipline from #7).

Guest-configuration posture is *not* a ``resources`` field — extensions and
guest-config assignment results live elsewhere — so it is modeled separately as
``policyresources`` policy-state rows. VMs with no policy-state row surface as
``not_evaluable`` (never ``pass``), exactly as live mode behaves with no policy
assigned.

The fixture deliberately includes real gaps — an untagged VM, weak TLS, public
network access, host encryption off, and VMs with no guest-config policy data —
so every control returns a mix of pass / fail / not_evaluable.
"""

from __future__ import annotations

import copy

from providers.base import PolicyStateRow, ResourceFilter, ResourceRow
from providers.filtering import apply_filter

SUBSCRIPTION_ID = "00000000-0000-0000-0000-000000000001"


def _vm_id(name: str, resource_group: str) -> str:
    return (
        f"/subscriptions/{SUBSCRIPTION_ID}/resourceGroups/{resource_group}"
        f"/providers/Microsoft.Compute/virtualMachines/{name}"
    )


def _vm(
    name: str,
    resource_group: str,
    location: str,
    tags: dict[str, str],
    encryption_at_host: bool,
) -> ResourceRow:
    return ResourceRow(
        id=_vm_id(name, resource_group),
        name=name,
        type="microsoft.compute/virtualmachines",
        resourceGroup=resource_group,
        subscriptionId=SUBSCRIPTION_ID,
        location=location,
        tags=tags,
        # ARG-faithful: encryption-at-host lives under securityProfile.
        properties={"securityProfile": {"encryptionAtHost": encryption_at_host}},
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
    # Fully compliant prod VM (tags present, host encryption on; guest-config
    # Compliant via policyresources below).
    _vm(
        "vm-web-prod-01",
        "rg-prod",
        "eastus",
        {"env": "prod", "owner": "alice", "costCenter": "CC-1001"},
        True,
    ),
    # Tagged, host encryption off (disk_encryption -> not_evaluable), and
    # guest-config NonCompliant via policyresources.
    _vm(
        "vm-web-prod-02",
        "rg-prod",
        "eastus",
        {"env": "prod", "owner": "alice", "costCenter": "CC-1001"},
        False,
    ),
    # Partial tags (no owner/costCenter), host encryption on, NO guest-config
    # policy data (guest_config_extension -> not_evaluable).
    _vm(
        "vm-batch-dev-01",
        "rg-dev",
        "westus",
        {"env": "dev"},
        True,
    ),
    # The untagged VM: zero tags, host encryption off, no guest-config policy data.
    _vm(
        "vm-legacy-01",
        "rg-shared",
        "westeurope",
        {},
        False,
    ),
    # Fully compliant storage account (all storage controls pass).
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


def _policy_state(name: str, resource_group: str, compliance_state: str) -> PolicyStateRow:
    # ARG lowercases the resourceId on policystate records.
    return PolicyStateRow(
        resourceId=_vm_id(name, resource_group).lower(),
        policyAssignmentName="guest-config-baseline",
        policyDefinitionName="[Preview]: Audit machines with guest configuration baseline",
        complianceState=compliance_state,
    )


# Guest-configuration policy states (the ARG `policyresources` analogue). Only
# VMs with a row here are evaluable; the other two VMs have no policy data, so
# guest_config_extension reports not_evaluable for them.
_MOCK_POLICY_STATES: list[PolicyStateRow] = [
    _policy_state("vm-web-prod-01", "rg-prod", "Compliant"),
    _policy_state("vm-web-prod-02", "rg-prod", "NonCompliant"),
]


class MockProvider:
    """In-memory ``Provider`` backed by the seeded dataset above."""

    async def list_resources(
        self, resource_filter: ResourceFilter | None = None
    ) -> list[ResourceRow]:
        # Deep copy so callers cannot mutate the shared fixture.
        rows = copy.deepcopy(_MOCK_RESOURCES)
        if resource_filter is None:
            return rows
        return apply_filter(rows, resource_filter)

    async def list_guest_config_states(self) -> list[PolicyStateRow]:
        return copy.deepcopy(_MOCK_POLICY_STATES)
