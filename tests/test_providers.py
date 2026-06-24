"""Unit tests for the mock provider and the provider factory (SPEC §2)."""

import asyncio

import pytest

from providers.base import Provider
from providers.factory import get_provider
from providers.live import LiveProvider
from providers.mock import MockProvider

EXPECTED_KEYS = {
    "id",
    "name",
    "type",
    "resourceGroup",
    "subscriptionId",
    "location",
    "tags",
    "properties",
}


def _resources():
    return asyncio.run(MockProvider().list_resources())


def test_factory_default_is_mock():
    provider = get_provider()
    assert isinstance(provider, MockProvider)
    assert isinstance(provider, Provider)  # structural check


def test_factory_unknown_mode_raises():
    with pytest.raises(ValueError, match="Unknown provider mode"):
        get_provider("bogus")


def test_factory_live_returns_live_provider():
    # Construction is offline and credential-free; list_resources (which hits
    # Azure) is exercised only by the opt-in manual live test.
    provider = get_provider("live")
    assert isinstance(provider, LiveProvider)
    assert isinstance(provider, Provider)  # structural check


def test_mock_rows_are_arg_shaped():
    rows = _resources()
    assert len(rows) == 7
    for row in rows:
        assert set(row) == EXPECTED_KEYS
        # ARG returns lowercased types.
        assert row["type"] == row["type"].lower()
        assert row["id"].startswith("/subscriptions/")


def test_mock_includes_untagged_vm():
    rows = _resources()
    untagged_vms = [
        r
        for r in rows
        if r["type"] == "microsoft.compute/virtualmachines" and not r["tags"]
    ]
    assert [r["name"] for r in untagged_vms] == ["vm-legacy-01"]


def test_mock_includes_vms_missing_guest_config():
    rows = _resources()
    missing = [
        r["name"]
        for r in rows
        if r["type"] == "microsoft.compute/virtualmachines"
        and "Microsoft.GuestConfiguration" not in r["properties"]["extensions"]
    ]
    assert set(missing) == {"vm-web-prod-02", "vm-batch-dev-01"}


def test_mock_returns_independent_copies():
    # Mutating one call's result must not leak into the next.
    first = asyncio.run(MockProvider().list_resources())
    first[0]["tags"]["env"] = "mutated"
    second = asyncio.run(MockProvider().list_resources())
    assert second[0]["tags"].get("env") != "mutated"
