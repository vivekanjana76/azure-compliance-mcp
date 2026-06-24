"""azure-compliance-mcp — FastMCP server entrypoint.

Exposes read-only Azure compliance / infra-health tools. Tools depend only on
the Provider protocol (SPEC §2); the default provider is the offline mock, so
the server runs with zero Azure setup.

Run (local, stdio):   uv run server.py
Inspect:              uv run fastmcp dev inspector server.py
"""

from __future__ import annotations

from typing import Literal

from fastmcp import FastMCP

from compliance import ComplianceResult, run_check_compliance
from providers import get_provider
from providers.base import QueryResultRow
from query import run_query_resources

mcp = FastMCP("azure-compliance-mcp")

# Default to the offline mock provider (SPEC §2). A --mode CLI arrives later.
_provider = get_provider("mock")

# Do NOT print() to stdout in stdio mode — logging must go to stderr only
# (see CLAUDE.md).


@mcp.tool
async def check_compliance(
    control: Literal[
        "guest_config_extension",
        "tls_min_1_2",
        "required_tags",
        "disk_encryption",
        "public_network_access",
    ]
    | None = None,
    status_filter: Literal["pass", "fail", "all"] = "fail",
    scope: str | None = None,
    resource_type: str | None = None,
) -> list[ComplianceResult]:
    """Evaluate named security/governance controls against resource configuration.

    Inspects each resource's configuration directly (not Azure Policy
    assignments), so it works without any policy assigned.

    Args:
        control: Which control to check, or None to check every applicable
            control. Controls: guest_config_extension, tls_min_1_2,
            required_tags (env/owner/costCenter), disk_encryption,
            public_network_access.
        status_filter: Return only "fail" rows (default), only "pass" rows, or
            "all".
        scope: Restrict to resources whose ARG resource ID contains this string
            (matches a subscription id, resource group, or resource name).
        resource_type: Restrict to a single ARG type, e.g.
            "microsoft.compute/virtualmachines".

    Returns:
        One row per (resource, applicable control), each with the observed
        `evidence` and a copy-pasteable `remediation` hint.
    """
    return await run_check_compliance(
        _provider,
        control=control,
        status_filter=status_filter,
        scope=scope,
        resource_type=resource_type,
    )


@mcp.tool
async def query_resources(
    resource_type: str | None = None,
    location: str | None = None,
    tag_filters: dict[str, str] | None = None,
    name_contains: str | None = None,
    limit: int = 100,
) -> list[QueryResultRow]:
    """Look up resources with structured, read-only filters.

    All filters are combined with AND. Returns an ARG-shaped projection.

    Args:
        resource_type: ARG type to match exactly, e.g.
            "microsoft.storage/storageaccounts".
        location: Azure region to match exactly, e.g. "eastus".
        tag_filters: Tags that must all be present with the given values.
        name_contains: Case-insensitive substring the resource name must contain.
        limit: Maximum number of rows to return (default 100; must be >= 1).

    Returns:
        Rows of: id, name, type, location, resourceGroup, tags, subscriptionId.
    """
    return await run_query_resources(
        _provider,
        resource_type=resource_type,
        location=location,
        tag_filters=tag_filters,
        name_contains=name_contains,
        limit=limit,
    )


if __name__ == "__main__":
    mcp.run()
