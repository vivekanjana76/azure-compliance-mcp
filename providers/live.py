"""Live Azure Resource Graph provider (SPEC §2).

Implements ``list_resources`` against Azure Resource Graph (ARG) via
``azure-mgmt-resourcegraph``, authenticating with ``DefaultAzureCredential``
(``azure-identity``). The query is strictly read-only — a single ``resources``
projection — and runs across every subscription the credential can access.

Filtering (resource_type / location / tags / name / limit) is applied by the
shared tool orchestration on top of these rows, so live and mock behave
identically. The Azure SDK clients are synchronous, so calls run in a worker
thread to keep the async tool non-blocking.

Heavy imports (azure.*) are deferred to first use so importing this module — and
constructing ``LiveProvider`` — stays cheap and credential-free.
"""

from __future__ import annotations

import asyncio
from typing import Any

from providers.base import ResourceRow

# Read-only projection of the columns the tools need (ARG returns lowercased
# types). `properties` is included so compliance-style tools can reuse it later.
_ARG_QUERY = (
    "resources "
    "| project id, name, type, location, resourceGroup, "
    "subscriptionId, tags, properties"
)

_PAGE_SIZE = 1000


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

    async def list_resources(self) -> list[ResourceRow]:
        return await asyncio.to_thread(self._list_resources_sync)

    def _list_resources_sync(self) -> list[ResourceRow]:
        from azure.mgmt.resourcegraph.models import (
            QueryRequest,
            QueryRequestOptions,
            ResultFormat,
        )

        client = self._ensure_client()
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
            request = QueryRequest(query=_ARG_QUERY, options=options)
            response = client.resources(request)
            for item in response.data or []:
                rows.append(_to_resource_row(item))
            skip_token = getattr(response, "skip_token", None)
            if not skip_token:
                break
        return rows
