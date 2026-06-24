"""Provider protocol and shared data shapes for the data layer (SPEC §2).

Tools depend only on the ``Provider`` protocol defined here, never on a concrete
mode (mock | live), so the same tool code serves both.
"""

from __future__ import annotations

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
    """One control evaluation against one resource (a ``check_compliance`` row)."""

    resourceId: str
    name: str
    type: str
    resourceGroup: str
    subscriptionId: str
    control: str
    status: str  # "pass" | "fail"
    evidence: str
    remediation: str


class QueryResultRow(TypedDict):
    """ARG-shaped projection returned by ``query_resources`` (SPEC §1.2)."""

    id: str
    name: str
    type: str
    location: str
    resourceGroup: str
    tags: dict[str, str]
    subscriptionId: str


@runtime_checkable
class Provider(Protocol):
    """Read-only data source backing the tools (SPEC §2)."""

    async def list_resources(self) -> list[ResourceRow]:
        """Return all resources in scope as ARG-shaped rows."""
        ...
