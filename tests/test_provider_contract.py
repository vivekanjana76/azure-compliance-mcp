"""Contract test: the pushed-down filter equals the reference Python filter.

For each provider, ``list_resources(rf)`` (mock = Python filter, live = KQL
pushdown) must return the same rows as applying the shared reference filter
(``apply_filter``) to that provider's *unfiltered* data. This proves the two
filtering implementations are equivalent on identical input.

A direct mock-vs-live row comparison is meaningless — they back different data
(synthetic vs your tenant) — so equivalence is asserted per provider, between its
two filter paths. The mock case runs in CI; the live case is opt-in.
"""

import asyncio
import copy
import os

import pytest

from providers.base import ResourceFilter
from providers.factory import get_provider
from providers.filtering import apply_filter

_LIVE = pytest.param(
    "live",
    marks=pytest.mark.skipif(
        os.getenv("RUN_LIVE_TESTS") != "1",
        reason="set RUN_LIVE_TESTS=1 to run live Azure Resource Graph tests",
    ),
)

# `limit` is left None so neither path truncates — set comparison is order-free.
CASES = [
    ResourceFilter(),
    ResourceFilter(resource_type="microsoft.compute/virtualmachines"),
    ResourceFilter(resource_type="microsoft.storage/storageaccounts"),
    ResourceFilter(location="eastus"),
    ResourceFilter(tag_filters={"env": "prod"}),
    ResourceFilter(name_contains="prod"),
    ResourceFilter(
        resource_type="microsoft.compute/virtualmachines", location="eastus"
    ),
]


def _ids(rows):
    return sorted(row["id"].lower() for row in rows)


@pytest.mark.parametrize("mode", ["mock", _LIVE])
@pytest.mark.parametrize("rf", CASES, ids=repr)
def test_pushdown_matches_reference(mode, rf):
    provider = get_provider(mode)
    full = asyncio.run(provider.list_resources(None))
    pushed = asyncio.run(provider.list_resources(rf))
    reference = apply_filter(copy.deepcopy(full), rf)
    assert _ids(pushed) == _ids(reference)


@pytest.mark.parametrize("mode", ["mock", _LIVE])
def test_limit_caps_count(mode):
    provider = get_provider(mode)
    full = asyncio.run(provider.list_resources(ResourceFilter()))
    capped = asyncio.run(provider.list_resources(ResourceFilter(limit=1)))
    assert len(capped) == min(1, len(full))
