"""Opt-in manual test for the live Azure Resource Graph provider (SPEC §2, §4.6).

Excluded from default CI: it needs real Azure credentials and network access.
Run it against your own tenant with:

    RUN_LIVE_TESTS=1 uv run pytest tests/test_live_manual.py -v

Authentication uses DefaultAzureCredential (e.g. `az login`, a managed identity,
or environment service-principal vars). The query is strictly read-only.
"""

import asyncio
import os

import pytest

from compliance import run_check_compliance
from providers.factory import get_provider
from query import run_query_resources

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LIVE_TESTS") != "1",
    reason="set RUN_LIVE_TESTS=1 to run live Azure Resource Graph tests",
)

ARG_KEYS = {
    "id",
    "name",
    "type",
    "resourceGroup",
    "subscriptionId",
    "location",
    "tags",
    "properties",
}


def test_live_list_resources_is_arg_shaped():
    provider = get_provider("live")
    rows = asyncio.run(provider.list_resources())
    # An empty tenant is still a valid result; only shape is asserted.
    for row in rows:
        assert ARG_KEYS.issubset(row.keys())
        assert row["id"].startswith("/subscriptions/")
        assert row["type"] == row["type"].lower()


def test_live_query_resources_respects_resource_type_filter():
    provider = get_provider("live")
    rows = asyncio.run(
        run_query_resources(
            provider,
            resource_type="microsoft.compute/virtualmachines",
            limit=5,
        )
    )
    assert len(rows) <= 5
    for row in rows:
        assert row["type"] == "microsoft.compute/virtualmachines"
        assert set(row) == ARG_KEYS - {"properties"}


POLICY_STATE_KEYS = {
    "resourceId",
    "policyAssignmentName",
    "policyDefinitionName",
    "complianceState",
}


def test_live_guest_config_states_are_policystate_shaped():
    # No guest-config policy assigned is a valid result (empty list); only shape
    # is asserted. The query against policyresources is strictly read-only.
    provider = get_provider("live")
    states = asyncio.run(provider.list_guest_config_states())
    for state in states:
        assert set(state) == POLICY_STATE_KEYS


def test_live_check_compliance_guest_config_never_silently_passes():
    # In live mode, guest_config_extension must come from azure_policy and, when
    # no policy data exists, be not_evaluable rather than pass.
    provider = get_provider("live")
    rows = asyncio.run(
        run_check_compliance(
            provider, control="guest_config_extension", status_filter="all"
        )
    )
    for row in rows:
        assert row["source"] == "azure_policy"
        assert row["status"] in {"pass", "fail", "not_evaluable"}
