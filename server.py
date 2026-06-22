"""azure-compliance-mcp — FastMCP server entrypoint.

This is a scaffold stub. Tools are not implemented yet; see SPEC.md for the
planned tool surface and the mock|live provider design.

Run (local, stdio):   uv run server.py
Run (remote, HTTP):   uv run server.py --transport http
Inspect:              uv run fastmcp dev server.py
"""

from fastmcp import FastMCP

mcp = FastMCP("azure-compliance-mcp")

# Tools will be registered here. Do NOT print() to stdout in stdio mode —
# logging must go to stderr only (see CLAUDE.md).


if __name__ == "__main__":
    mcp.run()
