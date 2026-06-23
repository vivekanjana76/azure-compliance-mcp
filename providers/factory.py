"""Provider selection (SPEC §2). Defaults to the offline mock provider."""

from __future__ import annotations

from providers.base import Provider
from providers.mock import MockProvider


def get_provider(mode: str = "mock") -> Provider:
    """Return the data provider for ``mode`` ("mock" | "live"). Defaults to mock."""
    if mode == "mock":
        return MockProvider()
    if mode == "live":
        from providers.live import LiveProvider

        return LiveProvider()
    raise ValueError(f"Unknown provider mode {mode!r}. Expected 'mock' or 'live'.")
