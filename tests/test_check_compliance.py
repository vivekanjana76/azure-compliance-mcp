"""Tests for the check_compliance tool (SPEC §1.1).

Covers the control=None default, status_filter behavior, and scope filtering —
both against the orchestration directly and through an in-memory FastMCP client.
"""

import asyncio

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

import server
from compliance import CONTROLS, run_check_compliance
from providers.mock import MockProvider


def _run(**kwargs):
    return asyncio.run(run_check_compliance(MockProvider(), **kwargs))


# --- control=None default + status_filter behavior ---------------------------


def test_default_returns_only_failures():
    # control=None, status_filter defaults to "fail".
    rows = _run()
    assert len(rows) == 11
    assert {r["status"] for r in rows} == {"fail"}
    # Every result carries evidence and a remediation hint.
    assert all(r["evidence"] for r in rows)
    assert all(r["remediation"] for r in rows)


def test_status_filter_all_returns_pass_and_fail():
    rows = _run(status_filter="all")
    assert len(rows) == 21
    assert {r["status"] for r in rows} == {"pass", "fail"}


def test_status_filter_pass_returns_only_passes():
    rows = _run(status_filter="pass")
    assert len(rows) == 10
    assert {r["status"] for r in rows} == {"pass"}


def test_default_plus_pass_equals_all():
    assert len(_run(status_filter="fail")) + len(_run(status_filter="pass")) == len(
        _run(status_filter="all")
    )


# --- single control ----------------------------------------------------------


def test_required_tags_covers_every_resource():
    rows = _run(control="required_tags", status_filter="all")
    assert len(rows) == 7  # one per resource
    assert {r["control"] for r in rows} == {"required_tags"}
    failing = {r["name"] for r in rows if r["status"] == "fail"}
    assert failing == {"vm-batch-dev-01", "vm-legacy-01", "stsharedlogs01"}


def test_vm_only_control_skips_storage():
    rows = _run(control="guest_config_extension", status_filter="all")
    assert len(rows) == 4  # only the four VMs
    assert {r["type"] for r in rows} == {"microsoft.compute/virtualmachines"}


# --- scope filtering ---------------------------------------------------------


def test_scope_filters_to_resource_group():
    rows = _run(scope="rg-prod", status_filter="all")
    # rg-prod has 2 VMs (3 controls each) + 1 storage (3 controls) = 9 rows.
    assert len(rows) == 9
    assert all("/resourcegroups/rg-prod/" in r["resourceId"].lower() for r in rows)


def test_scope_to_single_resource_name():
    rows = _run(scope="vm-legacy-01", status_filter="all")
    assert {r["name"] for r in rows} == {"vm-legacy-01"}
    assert len(rows) == 3  # three VM controls


def test_resource_type_filter():
    rows = _run(resource_type="microsoft.storage/storageaccounts", status_filter="all")
    assert {r["type"] for r in rows} == {"microsoft.storage/storageaccounts"}
    # 3 storage accounts x 2 applicable controls (tls, pna) + required_tags = 9.
    assert len(rows) == 9


# --- invalid args raise ToolError --------------------------------------------


def test_invalid_control_raises_toolerror():
    with pytest.raises(ToolError, match="Unknown control"):
        _run(control="not_a_control")


def test_invalid_status_filter_raises_toolerror():
    with pytest.raises(ToolError, match="Invalid status_filter"):
        _run(status_filter="maybe")


# --- in-memory FastMCP client ------------------------------------------------


def test_tool_registered():
    async def _list():
        async with Client(server.mcp) as client:
            return [t.name for t in await client.list_tools()]

    assert "check_compliance" in asyncio.run(_list())


def test_client_default_call_returns_failures():
    async def _call():
        async with Client(server.mcp) as client:
            return await client.call_tool("check_compliance", {})

    result = asyncio.run(_call())
    rows = result.data  # list of typed objects (FastMCP output schema)
    assert len(rows) == 11
    assert {r.status for r in rows} == {"fail"}


def test_client_scope_filter():
    async def _call():
        async with Client(server.mcp) as client:
            return await client.call_tool(
                "check_compliance", {"scope": "rg-prod", "status_filter": "all"}
            )

    rows = asyncio.run(_call()).data
    assert len(rows) == 9
    assert all(r.resourceGroup == "rg-prod" for r in rows)


def test_control_constant_matches_spec():
    assert set(CONTROLS) == {
        "guest_config_extension",
        "tls_min_1_2",
        "required_tags",
        "disk_encryption",
        "public_network_access",
    }
