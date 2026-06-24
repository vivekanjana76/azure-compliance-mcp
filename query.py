"""The ``query_resources`` orchestration (SPEC §1.2).

Builds a ``ResourceFilter`` and delegates filtering to the provider, then returns
an ARG-shaped projection. The mock provider applies the filter in Python; the
live provider pushes it into a Resource Graph KQL query — both honor the same
``ResourceFilter`` semantics.
"""

from __future__ import annotations

from fastmcp.exceptions import ToolError

from providers.base import Provider, QueryResultRow, ResourceFilter, ResourceRow

DEFAULT_LIMIT = 100


def _project(row: ResourceRow) -> QueryResultRow:
    return QueryResultRow(
        id=row["id"],
        name=row["name"],
        type=row["type"],
        location=row["location"],
        resourceGroup=row["resourceGroup"],
        tags=row["tags"],
        subscriptionId=row["subscriptionId"],
    )


async def run_query_resources(
    provider: Provider,
    *,
    resource_type: str | None = None,
    location: str | None = None,
    tag_filters: dict[str, str] | None = None,
    name_contains: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> list[QueryResultRow]:
    """Filter the provider's resources and return an ARG-shaped projection.

    Depends only on the ``Provider`` protocol, never on a concrete mode. Raises
    ``ToolError`` for a non-positive ``limit``.
    """
    if limit < 1:
        raise ToolError(f"limit must be >= 1, got {limit}.")

    resource_filter = ResourceFilter(
        resource_type=resource_type,
        location=location,
        tag_filters=tag_filters,
        name_contains=name_contains,
        limit=limit,
    )
    rows = await provider.list_resources(resource_filter)
    return [_project(row) for row in rows]
