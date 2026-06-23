# azure-compliance-mcp

> MCP server for natural-language Azure compliance & infra-health queries

An [MCP](https://modelcontextprotocol.io) server, built with **[FastMCP](https://gofastmcp.com) 3.x**, that exposes read-only Azure resource-compliance data — VM compliance, patch status, orphaned RBAC, and overall health — so an LLM agent can answer infrastructure questions in natural language.

> ⚠️ **Status: scaffold.** The tool surface is specified in [`SPEC.md`](./SPEC.md) but **not implemented yet**.

## Why

Asking "which VMs are non-compliant?" or "do I have orphaned role assignments?" usually means clicking through the Azure portal or hand-writing Resource Graph queries. This server turns those into tools an agent can call.

## Features (planned)

Five read-only tools — see [`SPEC.md`](./SPEC.md) for full contracts:

| Tool | What it answers |
|------|-----------------|
| `check_compliance` | Which resources are (non-)compliant with policy? |
| `query_resources` | Free-form resource lookups (KQL-style filters). |
| `get_patch_status` | Patch/update state across VMs. |
| `find_orphaned_rbac` | Role assignments pointing at deleted principals. |
| `summarize_health` | A rolled-up infra-health summary. |

## Mock vs. live

The server runs in one of two provider modes, selected with `--mode`:

- **`mock`** (default) — seeded, synthetic, Azure-Resource-Graph-shaped data including deliberately non-compliant resources. **Runs with zero Azure setup.**
- **`live`** — real Azure Resource Graph against *your own* tenant via `DefaultAzureCredential`.

## Quickstart

Requires [uv](https://docs.astral.sh/uv/) and Python 3.12+.

```bash
# Install dependencies
uv sync

# Run locally (stdio transport, mock data)
uv run server.py

# Run as a remote server (Streamable HTTP)
uv run server.py --transport http

# Inspect with the MCP dev inspector
uv run fastmcp dev inspector server.py
```

## Development

```bash
uv run pytest        # tests
uv run ruff check .  # lint
```

## Security

- All Azure tools are **read-only** — nothing in this server modifies Azure resources.
- Secrets, tenant IDs, and `.env` are gitignored and must never be committed.
- In stdio mode, logging goes to **stderr only** (stdout is reserved for the protocol).

## License

[MIT](./LICENSE)
