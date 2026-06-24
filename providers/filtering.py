"""Shared in-Python resource filtering — the reference implementation (SPEC §1.2).

The mock provider filters with this. The live provider pushes the same semantics
into a Resource Graph KQL query; the opt-in contract test asserts the two paths
return the same rows for the same input data.

Results are sorted by lowercased ``id`` so ``limit`` truncation is deterministic
and matches the live provider's ``order by tolower(id) | take`` ordering.
"""

from __future__ import annotations

from providers.base import ResourceFilter, ResourceRow


def matches(row: ResourceRow, rf: ResourceFilter) -> bool:
    """Whether a single row satisfies every set field of the filter (AND)."""
    if rf.resource_type is not None and row["type"].lower() != rf.resource_type.lower():
        return False
    if rf.location is not None and row["location"].lower() != rf.location.lower():
        return False
    if (
        rf.name_contains is not None
        and rf.name_contains.lower() not in row["name"].lower()
    ):
        return False
    if rf.tag_filters:
        for key, value in rf.tag_filters.items():
            if row["tags"].get(key) != value:
                return False
    return True


def apply_filter(rows: list[ResourceRow], rf: ResourceFilter) -> list[ResourceRow]:
    """Filter, deterministically sort, then apply ``limit`` (if any)."""
    matched = [row for row in rows if matches(row, rf)]
    matched.sort(key=lambda row: row["id"].lower())
    if rf.limit is not None:
        matched = matched[: rf.limit]
    return matched
