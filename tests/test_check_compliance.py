"""Tests for the check_compliance tool (SPEC §1.1).

Covers the control=None default, status_filter behavior (incl. not_evaluable),
the source field, scope filtering, and the honest control→source mapping — both
against the orchestration directly and through an in-memory FastMCP client.
"""

import asyncio

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

import server
from compliance import CONTROLS, run_check_compliance
from providers.mock import MockProvider

# Expected mock totals across all (resource, applicable control) rows:
#   fail=10, pass=9, not_evaluable=2  ->  21 total.
# (disk_encryption OFF is a fail; only guest_config with no policy data is
# not_evaluable.)
TOTAL_FAIL = 10
TOTAL_PASS = 9
TOTAL_NOT_EVALUABLE = 2
TOTAL_ALL = TOTAL_FAIL + TOTAL_PASS + TOTAL_NOT_EVALUABLE


def _run(**kwargs):
    return asyncio.run(run_check_compliance(MockProvider(), **kwargs))


# --- control=None default + status_filter behavior ---------------------------


def test_default_returns_only_failures():
    # control=None, status_filter defaults to "fail".
    rows = _run()
    assert len(rows) == TOTAL_FAIL
    assert {r["status"] for r in rows} == {"fail"}
    # Every result carries evidence and a remediation hint.
    assert all(r["evidence"] for r in rows)
    assert all(r["remediation"] for r in rows)


def test_default_excludes_not_evaluable():
    # The default "what's actively non-compliant?" call must not include
    # not_evaluable rows (SPEC §1.1).
    rows = _run()
    assert all(r["status"] != "not_evaluable" for r in rows)


def test_status_filter_all_returns_every_status():
    rows = _run(status_filter="all")
    assert len(rows) == TOTAL_ALL
    assert {r["status"] for r in rows} == {"pass", "fail", "not_evaluable"}


def test_status_filter_pass_returns_only_passes():
    rows = _run(status_filter="pass")
    assert len(rows) == TOTAL_PASS
    assert {r["status"] for r in rows} == {"pass"}


def test_status_filter_not_evaluable_returns_only_not_evaluable():
    rows = _run(status_filter="not_evaluable")
    assert len(rows) == TOTAL_NOT_EVALUABLE
    assert {r["status"] for r in rows} == {"not_evaluable"}
    # not_evaluable rows still explain themselves and point at where to look.
    assert all(r["evidence"] for r in rows)
    assert all(r["remediation"] for r in rows)


def test_statuses_partition_all():
    assert len(_run(status_filter="fail")) + len(_run(status_filter="pass")) + len(
        _run(status_filter="not_evaluable")
    ) == len(_run(status_filter="all"))


# --- source field ------------------------------------------------------------


def test_every_row_carries_a_valid_source():
    rows = _run(status_filter="all")
    assert all(r["source"] in {"arg", "azure_policy", "defender"} for r in rows)


def test_source_matches_control_mapping():
    rows = _run(status_filter="all")
    by_control: dict[str, set[str]] = {}
    for r in rows:
        by_control.setdefault(r["control"], set()).add(r["source"])
    # Resource-row controls are sourced from ARG.
    assert by_control["required_tags"] == {"arg"}
    assert by_control["tls_min_1_2"] == {"arg"}
    assert by_control["public_network_access"] == {"arg"}
    assert by_control["disk_encryption"] == {"arg"}
    # Guest-config posture comes from Azure Policy (policyresources), not the row.
    assert by_control["guest_config_extension"] == {"azure_policy"}


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


def test_guest_config_pass_fail_and_not_evaluable():
    rows = _run(control="guest_config_extension", status_filter="all")
    status_by_name = {r["name"]: r["status"] for r in rows}
    assert status_by_name == {
        "vm-web-prod-01": "pass",  # policy reports Compliant
        "vm-web-prod-02": "fail",  # policy reports NonCompliant
        "vm-batch-dev-01": "not_evaluable",  # no policy data
        "vm-legacy-01": "not_evaluable",  # no policy data
    }
    assert {r["source"] for r in rows} == {"azure_policy"}


def test_guest_config_not_evaluable_explains_missing_policy():
    rows = _run(control="guest_config_extension", status_filter="not_evaluable")
    assert {r["name"] for r in rows} == {"vm-batch-dev-01", "vm-legacy-01"}
    assert all("policyresources" in r["evidence"] for r in rows)


def test_disk_encryption_host_level_pass_or_fail():
    # encryption-at-host is the only signal in ARG: ON -> pass, OFF -> fail
    # (positive evidence a protection is absent), never not_evaluable.
    rows = _run(control="disk_encryption", status_filter="all")
    status_by_name = {r["name"]: r["status"] for r in rows}
    assert status_by_name == {
        "vm-web-prod-01": "pass",
        "vm-web-prod-02": "fail",
        "vm-batch-dev-01": "pass",
        "vm-legacy-01": "fail",
    }
    assert "not_evaluable" not in {r["status"] for r in rows}
    assert {r["source"] for r in rows} == {"arg"}


def test_disk_encryption_fail_evidence_stays_scope_honest():
    rows = _run(control="disk_encryption", status_filter="fail")
    assert rows  # there are failing VMs
    for r in rows:
        # Honest about what was (not) assessed: host-level only, ADE excluded.
        assert "Encryption at host is not enabled" in r["evidence"]
        assert "ADE" in r["evidence"]


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
    assert len(rows) == TOTAL_FAIL
    assert {r.status for r in rows} == {"fail"}


def test_client_not_evaluable_exposes_source():
    async def _call():
        async with Client(server.mcp) as client:
            return await client.call_tool(
                "check_compliance", {"status_filter": "not_evaluable"}
            )

    rows = asyncio.run(_call()).data
    assert len(rows) == TOTAL_NOT_EVALUABLE
    assert {r.status for r in rows} == {"not_evaluable"}
    assert all(r.source in {"arg", "azure_policy"} for r in rows)


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
