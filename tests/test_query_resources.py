"""Tests for the query_resources tool (SPEC §1.2).

Covers resource_type / location / tag / name filters, limit, and the ARG-shaped
projection — both against the orchestration directly and through an in-memory
FastMCP client.
"""

import asyncio

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

import server
from providers.mock import MockProvider
from query import run_query_resources

VM_TYPE = "microsoft.compute/virtualmachines"
STORAGE_TYPE = "microsoft.storage/storageaccounts"
PROJECTION_KEYS = {
    "id",
    "name",
    "type",
    "location",
    "resourceGroup",
    "tags",
    "subscriptionId",
}


def _run(**kwargs):
    return asyncio.run(run_query_resources(MockProvider(), **kwargs))


# --- no filter / projection --------------------------------------------------


def test_no_filter_returns_all():
    rows = _run()
    assert len(rows) == 7


def test_projection_shape_excludes_properties():
    rows = _run()
    for row in rows:
        assert set(row) == PROJECTION_KEYS
        assert "properties" not in row


# --- resource_type -----------------------------------------------------------


def test_filter_by_resource_type_vm():
    rows = _run(resource_type=VM_TYPE)
    assert len(rows) == 4
    assert {r["type"] for r in rows} == {VM_TYPE}


def test_filter_by_resource_type_is_case_insensitive():
    rows = _run(resource_type="Microsoft.Storage/StorageAccounts")
    assert len(rows) == 3
    assert {r["type"] for r in rows} == {STORAGE_TYPE}


# --- location ----------------------------------------------------------------


def test_filter_by_location():
    assert len(_run(location="eastus")) == 3
    assert len(_run(location="westus")) == 2
    assert len(_run(location="westeurope")) == 2


# --- tags --------------------------------------------------------------------


def test_filter_by_single_tag():
    rows = _run(tag_filters={"env": "prod"})
    assert {r["name"] for r in rows} == {
        "vm-web-prod-01",
        "vm-web-prod-02",
        "stprodassets01",
    }


def test_filter_by_multiple_tags_is_and():
    rows = _run(tag_filters={"env": "prod", "owner": "alice"})
    # stprodassets01 is env=prod but owner=bob, so it is excluded.
    assert {r["name"] for r in rows} == {"vm-web-prod-01", "vm-web-prod-02"}


def test_filter_by_tag_no_match():
    assert _run(tag_filters={"env": "staging"}) == []


# --- name_contains -----------------------------------------------------------


def test_filter_by_name_contains():
    rows = _run(name_contains="vm-web")
    assert {r["name"] for r in rows} == {"vm-web-prod-01", "vm-web-prod-02"}


def test_name_contains_is_case_insensitive():
    rows = _run(name_contains="ST")
    assert len(rows) == 3
    assert all(r["type"] == STORAGE_TYPE for r in rows)


# --- combined + limit --------------------------------------------------------


def test_combined_filters():
    rows = _run(resource_type=STORAGE_TYPE, location="westus")
    assert {r["name"] for r in rows} == {"stdevscratch01"}


def test_limit_caps_results():
    assert len(_run(limit=2)) == 2
    assert len(_run(limit=3)) == 3
    # A limit larger than the dataset returns everything.
    assert len(_run(limit=1000)) == 7


def test_limit_below_one_raises_toolerror():
    with pytest.raises(ToolError, match="limit must be >= 1"):
        _run(limit=0)


# --- in-memory FastMCP client ------------------------------------------------


def test_tool_registered():
    async def _list():
        async with Client(server.mcp) as client:
            return [t.name for t in await client.list_tools()]

    assert "query_resources" in asyncio.run(_list())


def test_client_default_call_returns_all():
    async def _call():
        async with Client(server.mcp) as client:
            return await client.call_tool("query_resources", {})

    rows = asyncio.run(_call()).data
    assert len(rows) == 7


def test_client_filter_and_limit():
    async def _call():
        async with Client(server.mcp) as client:
            return await client.call_tool(
                "query_resources", {"resource_type": STORAGE_TYPE, "limit": 2}
            )

    rows = asyncio.run(_call()).data
    assert len(rows) == 2
    assert all(r.type == STORAGE_TYPE for r in rows)
