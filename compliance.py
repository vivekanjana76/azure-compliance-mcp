"""Control definitions and the ``check_compliance`` orchestration (SPEC §1.1).

Control evaluation is pure and shared across providers: a provider supplies
ARG-shaped resource rows (``Provider.list_resources``) and these functions
evaluate the named controls against them, so the same logic serves mock and
live modes.
"""

from __future__ import annotations

from typing import Literal, get_args

from fastmcp.exceptions import ToolError

from providers.base import ComplianceResult, Provider, ResourceRow

Control = Literal[
    "guest_config_extension",
    "tls_min_1_2",
    "required_tags",
    "disk_encryption",
    "public_network_access",
]
CONTROLS: tuple[str, ...] = get_args(Control)

StatusFilter = Literal["pass", "fail", "all"]
STATUS_FILTERS: tuple[str, ...] = get_args(StatusFilter)

REQUIRED_TAGS = ("env", "owner", "costCenter")

VM_TYPE = "microsoft.compute/virtualmachines"
STORAGE_TYPE = "microsoft.storage/storageaccounts"

# Resource type each control applies to; None means "every resource type".
_CONTROL_TYPE: dict[str, str | None] = {
    "required_tags": None,
    "guest_config_extension": VM_TYPE,
    "disk_encryption": VM_TYPE,
    "tls_min_1_2": STORAGE_TYPE,
    "public_network_access": STORAGE_TYPE,
}


def _applies(control: str, resource_type: str) -> bool:
    wanted = _CONTROL_TYPE[control]
    return wanted is None or resource_type.lower() == wanted


def _evaluate(control: str, row: ResourceRow) -> tuple[str, str, str]:
    """Return ``(status, evidence, remediation)`` for one control on one row."""
    name, rg, props = row["name"], row["resourceGroup"], row["properties"]

    if control == "required_tags":
        missing = [t for t in REQUIRED_TAGS if not row["tags"].get(t)]
        if missing:
            return (
                "fail",
                f"Missing required tag(s): {', '.join(missing)}.",
                f"az resource tag --ids {row['id']} --tags "
                + " ".join(f"{t}=<value>" for t in missing),
            )
        return ("pass", "All required tags present (env, owner, costCenter).", "")

    if control == "guest_config_extension":
        if "Microsoft.GuestConfiguration" not in props.get("extensions", []):
            return (
                "fail",
                "No Microsoft.GuestConfiguration extension installed on the VM.",
                f"az vm extension set --publisher Microsoft.GuestConfiguration "
                f"--name ConfigurationforLinux --vm-name {name} --resource-group {rg}",
            )
        return ("pass", "Microsoft.GuestConfiguration extension present.", "")

    if control == "disk_encryption":
        if not props.get("encryptionAtHost", False):
            return (
                "fail",
                "Encryption at host is not enabled; disks are unencrypted at the host.",
                f"az vm update --name {name} --resource-group {rg} "
                f"--set securityProfile.encryptionAtHost=true",
            )
        return ("pass", "Encryption at host is enabled.", "")

    if control == "tls_min_1_2":
        tls = props.get("minimumTlsVersion", "TLS1_0")
        if tls != "TLS1_2":
            return (
                "fail",
                f"minimumTlsVersion is {tls} (below TLS1_2).",
                f"az storage account update --name {name} --resource-group {rg} "
                f"--min-tls-version TLS1_2",
            )
        return ("pass", "minimumTlsVersion is TLS1_2.", "")

    if control == "public_network_access":
        pna = props.get("publicNetworkAccess", "Enabled")
        if pna != "Disabled":
            return (
                "fail",
                f"publicNetworkAccess is {pna}; reachable from the public internet.",
                f"az storage account update --name {name} --resource-group {rg} "
                f"--public-network-access Disabled",
            )
        return ("pass", "publicNetworkAccess is Disabled.", "")

    # Defensive: callers validate `control` before reaching here.
    raise ToolError(f"Unknown control: {control!r}.")


def _in_scope(row: ResourceRow, scope: str | None) -> bool:
    """Scope matches as a case-insensitive substring of the ARG resource ID.

    The resource ID embeds the subscription id, resource group, and resource
    name, so one substring test covers all three (SPEC §1.1).
    """
    return scope is None or scope.lower() in row["id"].lower()


async def run_check_compliance(
    provider: Provider,
    *,
    control: str | None = None,
    status_filter: str = "fail",
    scope: str | None = None,
    resource_type: str | None = None,
) -> list[ComplianceResult]:
    """Evaluate controls against the provider's resources (SPEC §1.1).

    Depends only on the ``Provider`` protocol, never on a concrete mode. Raises
    ``ToolError`` for an unknown ``control`` or ``status_filter``.
    """
    if control is not None and control not in CONTROLS:
        raise ToolError(
            f"Unknown control {control!r}. Valid controls: {', '.join(CONTROLS)}."
        )
    if status_filter not in STATUS_FILTERS:
        raise ToolError(
            f"Invalid status_filter {status_filter!r}. "
            f"Valid values: {', '.join(STATUS_FILTERS)}."
        )

    controls = (control,) if control is not None else CONTROLS
    rows = await provider.list_resources()

    results: list[ComplianceResult] = []
    for row in rows:
        if not _in_scope(row, scope):
            continue
        if resource_type is not None and row["type"].lower() != resource_type.lower():
            continue
        for ctrl in controls:
            if not _applies(ctrl, row["type"]):
                continue
            status, evidence, remediation = _evaluate(ctrl, row)
            if status_filter != "all" and status != status_filter:
                continue
            results.append(
                ComplianceResult(
                    resourceId=row["id"],
                    name=row["name"],
                    type=row["type"],
                    resourceGroup=row["resourceGroup"],
                    subscriptionId=row["subscriptionId"],
                    control=ctrl,
                    status=status,
                    evidence=evidence,
                    remediation=remediation,
                )
            )
    return results
