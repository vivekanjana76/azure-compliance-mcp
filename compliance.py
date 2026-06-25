"""Control definitions and the ``check_compliance`` orchestration (SPEC §1.1).

Control evaluation is pure and shared across providers: a provider supplies
ARG-shaped resource rows (``Provider.list_resources``) and guest-config policy
states (``Provider.list_guest_config_states``), and these functions evaluate the
named controls against them — so the *same* mapping serves mock and live modes.

Honesty about provenance (SPEC §1.1): every finding carries a ``source``
(``arg`` | ``azure_policy`` | ``defender``) saying where its verdict came from,
and a third status ``not_evaluable`` for controls whose signal is not exposed by
the available data, so nothing is guessed.

Control → source mapping:
    required_tags          arg           resources.tags
    tls_min_1_2            arg           resources.properties.minimumTlsVersion
    public_network_access  arg           resources.properties.publicNetworkAccess
    disk_encryption        arg           resources.properties.securityProfile
                                         .encryptionAtHost (host-level only; OFF
                                         ⇒ fail, ADE not assessed)
    guest_config_extension azure_policy  policyresources (guest-config states)
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

StatusFilter = Literal["pass", "fail", "not_evaluable", "all"]
STATUS_FILTERS: tuple[str, ...] = get_args(StatusFilter)

# Where a finding's verdict came from (SPEC §1.1).
SOURCE_ARG = "arg"
SOURCE_AZURE_POLICY = "azure_policy"
SOURCE_DEFENDER = "defender"  # reserved; not yet produced by any control

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


def _evaluate(
    control: str, row: ResourceRow, guest_config_states: dict[str, str]
) -> tuple[str, str, str, str]:
    """Return ``(status, source, evidence, remediation)`` for one control on one row.

    ``guest_config_states`` maps a lowercased resource id to its guest-config
    ``complianceState`` (from ``policyresources``); a missing key means no policy
    data, which yields ``not_evaluable``.
    """
    name, rg, props = row["name"], row["resourceGroup"], row["properties"]

    if control == "required_tags":
        missing = [t for t in REQUIRED_TAGS if not row["tags"].get(t)]
        if missing:
            return (
                "fail",
                SOURCE_ARG,
                f"Missing required tag(s): {', '.join(missing)}.",
                f"az resource tag --ids {row['id']} --tags "
                + " ".join(f"{t}=<value>" for t in missing),
            )
        return (
            "pass",
            SOURCE_ARG,
            "All required tags present (env, owner, costCenter).",
            "",
        )

    if control == "tls_min_1_2":
        tls = props.get("minimumTlsVersion", "TLS1_0")
        if tls != "TLS1_2":
            return (
                "fail",
                SOURCE_ARG,
                f"properties.minimumTlsVersion is {tls} (below TLS1_2).",
                f"az storage account update --name {name} --resource-group {rg} "
                f"--min-tls-version TLS1_2",
            )
        return ("pass", SOURCE_ARG, "properties.minimumTlsVersion is TLS1_2.", "")

    if control == "public_network_access":
        pna = props.get("publicNetworkAccess", "Enabled")
        if pna != "Disabled":
            return (
                "fail",
                SOURCE_ARG,
                f"properties.publicNetworkAccess is {pna}; reachable from the public internet.",
                f"az storage account update --name {name} --resource-group {rg} "
                f"--public-network-access Disabled",
            )
        return ("pass", SOURCE_ARG, "properties.publicNetworkAccess is Disabled.", "")

    if control == "disk_encryption":
        # Host-level control: ARG resources rows expose encryption-at-host only.
        # OFF is positive evidence a protection is absent — an actionable fail
        # that belongs in the default view. The evidence stays honest about
        # scope (disk-level / Azure Disk Encryption posture is not assessed from
        # ARG). This differs from guest_config, where the signal is genuinely
        # absent (not_evaluable).
        sec = props.get("securityProfile") or {}
        if sec.get("encryptionAtHost", False):
            return (
                "pass",
                SOURCE_ARG,
                "properties.securityProfile.encryptionAtHost is true "
                "(encryption at host enabled).",
                "",
            )
        return (
            "fail",
            SOURCE_ARG,
            "Encryption at host is not enabled "
            "(properties.securityProfile.encryptionAtHost is false; disk-level/ADE "
            "posture not assessed from ARG).",
            f"az vm update --name {name} --resource-group {rg} "
            f"--set securityProfile.encryptionAtHost=true",
        )

    if control == "guest_config_extension":
        # Guest-config posture is not in the resources row — sourced from the ARG
        # policyresources table. No policy data => not_evaluable, never pass.
        state = guest_config_states.get(row["id"].lower())
        if state is None:
            return (
                "not_evaluable",
                SOURCE_AZURE_POLICY,
                "No guest-configuration policy state found for this VM in the ARG "
                "policyresources table. Guest-config posture is not exposed in the "
                "resources table, so it cannot be evaluated from resource "
                "configuration alone.",
                "Assign a Guest Configuration policy/initiative (e.g. the Azure "
                "Security Benchmark) to this scope; its compliance will then appear "
                "in policyresources.",
            )
        if state.lower() == "compliant":
            return (
                "pass",
                SOURCE_AZURE_POLICY,
                f"Guest-configuration policy reports {state}.",
                "",
            )
        return (
            "fail",
            SOURCE_AZURE_POLICY,
            f"Guest-configuration policy reports {state}.",
            "Review the guest-configuration assignment findings in Azure Policy and "
            "remediate the failing settings on the VM.",
        )

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

    The default call (``control=None``, ``status_filter="fail"``) answers "what's
    actively non-compliant?" and therefore *excludes* ``not_evaluable`` rows;
    those are reachable via ``status_filter="not_evaluable"`` (or ``"all"``).
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

    # Only pay for the policyresources query when guest-config is in scope.
    guest_config_states: dict[str, str] = {}
    if "guest_config_extension" in controls:
        states = await provider.list_guest_config_states()
        guest_config_states = {s["resourceId"].lower(): s["complianceState"] for s in states}

    results: list[ComplianceResult] = []
    for row in rows:
        if not _in_scope(row, scope):
            continue
        if resource_type is not None and row["type"].lower() != resource_type.lower():
            continue
        for ctrl in controls:
            if not _applies(ctrl, row["type"]):
                continue
            status, source, evidence, remediation = _evaluate(
                ctrl, row, guest_config_states
            )
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
                    source=source,
                    evidence=evidence,
                    remediation=remediation,
                )
            )
    return results
