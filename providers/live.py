"""Live Azure Resource Graph provider (SPEC §2).

Implements ``list_resources`` against Azure Resource Graph (ARG) via
``azure-mgmt-resourcegraph``, authenticating with ``DefaultAzureCredential``
(``azure-identity``). Queries are strictly read-only.

When a ``ResourceFilter`` is supplied, the filter is pushed *into* the KQL query
(``where`` clauses + ``take``) rather than fetched-then-filtered, so large
tenants stay cheap. ARG has no bind-parameter mechanism, so every user-supplied
value is encoded as an escaped KQL string literal via ``_kql_str`` — never
concatenated raw — which prevents query injection. (ARG is a read-only query API
regardless, so there is no mutation surface.)

The Azure SDK clients are synchronous, so calls run in a worker thread. Heavy
imports (azure.*) are deferred to first use so importing this module — and
constructing ``LiveProvider`` — stays cheap and credential-free.
"""

from __future__ import annotations

import asyncio
from typing import Any

from providers.base import ResourceFilter, ResourceRow

_PROJECT = (
    "| project id, name, type, location, resourceGroup, "
    "subscriptionId, tags, properties"
)

_PAGE_SIZE = 1000


def _kql_str(value: str) -> str:
    """Encode an arbitrary string as a safe, double-quoted KQL string literal.

    Backslashes and quotes are escaped, so the value can only ever be read as a
    literal — it cannot break out into query syntax.
    """
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )
    return f'"{escaped}"'


def _build_query(resource_filter: ResourceFilter | None) -> str:
    """Build the read-only ARG KQL query, pushing the filter down."""
    lines = ["resources"]
    if resource_filter is not None:
        rf = resource_filter
        if rf.resource_type is not None:
            lines.append(f"| where type =~ {_kql_str(rf.resource_type)}")
        if rf.location is not None:
            lines.append(f"| where location =~ {_kql_str(rf.location)}")
        if rf.name_contains is not None:
            lines.append(f"| where name contains {_kql_str(rf.name_contains)}")
        if rf.tag_filters:
            for key, value in rf.tag_filters.items():
                lines.append(f"| where tags[{_kql_str(key)}] == {_kql_str(value)}")
    lines.append(_PROJECT)
    if resource_filter is not None and resource_filter.limit is not None:
        # Deterministic order so `take` truncation matches the mock provider.
        lines.append("| order by tolower(id) asc")
        lines.append(f"| take {int(resource_filter.limit)}")
    return "\n".join(lines)


def _to_resource_row(item: dict[str, Any]) -> ResourceRow:
    """Normalize one ARG object-array record into a ``ResourceRow``."""
    return ResourceRow(
        id=item.get("id", ""),
        name=item.get("name", ""),
        type=(item.get("type") or "").lower(),
        resourceGroup=item.get("resourceGroup", "") or "",
        subscriptionId=item.get("subscriptionId", "") or "",
        location=item.get("location", "") or "",
        tags=item.get("tags") or {},
        properties=item.get("properties") or {},
    )


class LiveProvider:
    """``Provider`` backed by Azure Resource Graph."""

    def __init__(self) -> None:
        self._client: Any | None = None

    def _ensure_client(self) -> Any:
        if self._client is None:
            from azure.identity import DefaultAzureCredential
            from azure.mgmt.resourcegraph import ResourceGraphClient

            self._client = ResourceGraphClient(DefaultAzureCredential())
        return self._client

    async def list_resources(
        self, resource_filter: ResourceFilter | None = None
    ) -> list[ResourceRow]:
        return await asyncio.to_thread(self._list_resources_sync, resource_filter)

    def _list_resources_sync(
        self, resource_filter: ResourceFilter | None
    ) -> list[ResourceRow]:
        from azure.mgmt.resourcegraph.models import (
            QueryRequest,
            QueryRequestOptions,
            ResultFormat,
        )

        client = self._ensure_client()
        query = _build_query(resource_filter)
        rows: list[ResourceRow] = []
        skip_token: str | None = None
        while True:
            options = QueryRequestOptions(
                result_format=ResultFormat.OBJECT_ARRAY,
                top=_PAGE_SIZE,
                skip_token=skip_token,
                # Query across all subscriptions the credential can reach.
                allow_partial_scopes=True,
            )
            request = QueryRequest(query=query, options=options)
            response = client.resources(request)
            for item in response.data or []:
                rows.append(_to_resource_row(item))
            skip_token = getattr(response, "skip_token", None)
            if not skip_token:
                break
        return rows
