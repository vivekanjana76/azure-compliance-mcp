"""Provider protocol and shared data shapes for the data layer (SPEC §2).

Tools depend only on the ``Provider`` protocol defined here, never on a concrete
mode (mock | live), so the same tool code serves both.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, TypedDict, runtime_checkable


class ResourceRow(TypedDict):
    """An Azure-Resource-Graph-shaped resource row.

    Mirrors the columns a ``resources`` ARG query returns, plus the configuration
    needed to evaluate the compliance controls in ``compliance.py``.
    """

    id: str
    name: str
    # ARG returns lowercased types, e.g. "microsoft.compute/virtualmachines".
    type: str
    resourceGroup: str
    subscriptionId: str
    location: str
    tags: dict[str, str]
    properties: dict[str, Any]


class ComplianceResult(TypedDict):
    """One control evaluation against one resource (a ``check_compliance`` row).

    ``status`` is ``"pass" | "fail" | "not_evaluable"`` — the last meaning the
    signal needed to judge the control is not exposed by the data source, so no
    verdict is guessed (SPEC §1.1). ``source`` records which read-only data source
    produced the verdict: ``"arg" | "azure_policy" | "defender"``.
    """

    resourceId: str
    name: str
    type: str
    resourceGroup: str
    subscriptionId: str
    control: str
    status: str  # "pass" | "fail" | "not_evaluable"
    source: str  # "arg" | "azure_policy" | "defender"
    evidence: str
    remediation: str


class PolicyStateRow(TypedDict):
    """A policy-compliance state from the ARG ``policyresources`` table.

    Mirrors the fields a ``policyresources`` query projects for a policy state
    record (Azure Policy, including guest-configuration assignment results).
    Used to evaluate controls that are *not* determinable from a ``resources``
    row alone (e.g. ``guest_config_extension``; SPEC §1.1).
    """

    # The resource the assignment targets (ARG lowercases policystate IDs).
    resourceId: str
    policyAssignmentName: str
    policyDefinitionName: str
    complianceState: str  # e.g. "Compliant" | "NonCompliant"


class QueryResultRow(TypedDict):
    """ARG-shaped projection returned by ``query_resources`` (SPEC §1.2)."""

    id: str
    name: str
    type: str
    location: str
    resourceGroup: str
    tags: dict[str, str]
    subscriptionId: str


@dataclass(frozen=True)
class ResourceFilter:
    """Structured, read-only filter for ``query_resources`` (SPEC §1.2).

    All set fields combine with AND. ``limit`` of ``None`` means no cap. The mock
    provider applies this in Python; the live provider pushes it into KQL. The
    two are equivalent (see the opt-in contract test).
    """

    resource_type: str | None = None
    location: str | None = None
    tag_filters: dict[str, str] | None = None
    name_contains: str | None = None
    limit: int | None = None


@runtime_checkable
class Provider(Protocol):
    """Read-only data source backing the tools (SPEC §2)."""

    async def list_resources(
        self, resource_filter: ResourceFilter | None = None
    ) -> list[ResourceRow]:
        """Return ARG-shaped rows, optionally filtered.

        ``resource_filter=None`` returns everything in scope (used by tools that
        do their own filtering, e.g. check_compliance).
        """
        ...

    async def list_guest_config_states(self) -> list[PolicyStateRow]:
        """Return guest-configuration policy states from ``policyresources``.

        Backs the ``guest_config_extension`` control, whose posture is not in the
        ``resources`` row. An empty list means no guest-config policy data exists
        (e.g. nothing assigned), which the control reports as ``not_evaluable``
        rather than ``pass`` (SPEC §1.1).
        """
        ...
