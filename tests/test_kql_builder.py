"""Unit tests for the live provider's KQL generation and injection safety.

These run in CI (no Azure needed) — they only build query strings.
"""

from providers.base import ResourceFilter
from providers.live import (
    _GUEST_CONFIG_CATEGORY,
    _PROJECT,
    _build_guest_config_query,
    _build_query,
    _kql_str,
)


def test_kql_str_escapes_quotes_and_backslashes():
    assert _kql_str("eastus") == '"eastus"'
    assert _kql_str('a"b') == r'"a\"b"'
    assert _kql_str("a\\b") == r'"a\\b"'


def test_build_query_no_filter():
    assert _build_query(ResourceFilter()) == "resources\n" + _PROJECT


def test_build_query_resource_type_and_limit():
    q = _build_query(
        ResourceFilter(resource_type="microsoft.compute/virtualmachines", limit=100)
    )
    assert q.splitlines() == [
        "resources",
        '| where type =~ "microsoft.compute/virtualmachines"',
        _PROJECT,
        "| order by tolower(id) asc",
        "| take 100",
    ]


def test_build_query_combined_filters():
    q = _build_query(
        ResourceFilter(
            location="eastus",
            tag_filters={"env": "prod"},
            name_contains="web",
            limit=50,
        )
    )
    assert q.splitlines() == [
        "resources",
        '| where location =~ "eastus"',
        '| where name contains "web"',
        '| where tags["env"] == "prod"',
        _PROJECT,
        "| order by tolower(id) asc",
        "| take 50",
    ]


def test_build_query_escapes_tag_key_and_value():
    # Both the key (inside tags[...]) and the value must be escaped, not just
    # the value — a malicious key cannot break out of the bracket.
    key, value = 'ev"il', 'va"lue'
    q = _build_query(ResourceFilter(tag_filters={key: value}, limit=10))
    assert f"| where tags[{_kql_str(key)}] == {_kql_str(value)}" in q
    assert _kql_str(key) == r'"ev\"il"'  # the quote in the key is escaped


def test_build_guest_config_query_targets_policyresources():
    q = _build_guest_config_query()
    lines = q.splitlines()
    # Reads the policyresources table (not resources) and filters to policystates.
    assert lines[0] == "policyresources"
    assert '| where type =~ "microsoft.policyinsights/policystates"' in lines
    # The one literal (the policy category) is escaped via _kql_str.
    assert _kql_str(_GUEST_CONFIG_CATEGORY) in q
    # Projects the flat PolicyStateRow columns _to_policy_state_row reads.
    for col in (
        "resourceId",
        "policyAssignmentName",
        "policyDefinitionName",
        "complianceState",
    ):
        assert col in q


def test_build_query_is_injection_safe():
    malicious = '"; resources | project secret //'
    q = _build_query(ResourceFilter(name_contains=malicious, limit=10))
    literal = _kql_str(malicious)
    # The payload appears only inside a single escaped string literal...
    assert f"| where name contains {literal}" in q
    # ...and not as bare query structure once that literal is removed.
    assert "project secret" not in q.replace(literal, "")
