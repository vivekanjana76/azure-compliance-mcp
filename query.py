"""The ``query_resources`` orchestration (SPEC §1.2).

Reuses ``Provider.list_resources`` and applies read-only, structured filters,
returning an ARG-shaped projection. The same filter logic runs for every
provider (mock | live), so filters behave identically regardless of mode.
"""

from __future__ import annotations

from fastmcp.exceptions import ToolError

from providers.base import Provider, QueryResultRow, ResourceRow

DEFAULT_LIMIT = 100


def _matches(
    row: ResourceRow,
    *,
    resource_type: str | None,
    location: str | None,
    tag_filters: dict[str, str] | None,
    name_contains: str | None,
) -> bool:
    if resource_type is not None and row["type"].lower() != resource_type.lower():
        return False
    if location is not None and row["location"].lower() != location.lower():
        return False
    if name_contains is not None and name_contains.lower() not in row["name"].lower():
        return False
    if tag_filters:
        for key, value in tag_filters.items():
            if row["tags"].get(key) != value:
                return False
    return True


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

    rows = await provider.list_resources()
    results: list[QueryResultRow] = []
    for row in rows:
        if _matches(
            row,
            resource_type=resource_type,
            location=location,
            tag_filters=tag_filters,
            name_contains=name_contains,
        ):
            results.append(_project(row))
            if len(results) >= limit:
                break
    return results
