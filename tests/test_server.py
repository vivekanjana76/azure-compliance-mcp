"""Smoke tests for the server scaffold.

These intentionally only assert that the FastMCP server object loads and is
wired up correctly. Tool-behavior tests arrive with the tools (see SPEC.md).
"""

import server


def test_server_imports_and_is_named():
    """The module exposes a FastMCP instance with the expected name."""
    assert server.mcp is not None
    assert server.mcp.name == "azure-compliance-mcp"
