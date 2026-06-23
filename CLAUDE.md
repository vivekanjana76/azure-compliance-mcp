# CLAUDE.md — azure-compliance-mcp

## What this is
An MCP server exposing Azure resource-compliance data (VM compliance, patch
status, orphaned RBAC) so an LLM agent can query infrastructure health in
natural language. Built with FastMCP 3.x.

## Tech stack (pin these)
- Python 3.12+, managed with uv
- FastMCP 3.x (`from fastmcp import FastMCP`)
- azure-identity + azure-mgmt-resourcegraph (live mode only)
- pytest + ruff
- Transports: stdio (local), Streamable HTTP + OAuth 2.1 (remote)

## Architecture
- server.py — FastMCP instance + 5–6 read-only tools
- providers/ — data layer, two modes:
  - mock (default): synthetic, seeded, ARG-schema-shaped data incl. non-compliant resources
  - live: real Azure Resource Graph against the user's OWN tenant via DefaultAzureCredential
- Mode via `--mode mock|live`; default mock so the repo runs with zero Azure setup.

## GitHub automation — how you (Claude) manage this repo
- Use the `gh` CLI for ALL GitHub operations (it's authenticated; never ask for a token).
- Repo metadata: description "MCP server for natural-language Azure compliance & infra-health queries";
  topics: mcp, model-context-protocol, azure, devops, ai-agents, fastmcp, python.
- License: MIT.
- Workflow, every feature: open a GitHub issue -> branch `feat/NN-short-name` ->
  implement -> commit -> `gh pr create` referencing the issue -> wait for the user to merge.
- NEVER push directly to main. main is protected.
- Conventional Commits: feat:, fix:, docs:, test:, chore:
- Tag releases (v0.1.0, ...) at milestones.
- Keep commits meaningful and scoped — no padding, no noise commits.

## Hard rules — NEVER violate
- NEVER commit secrets, tenant IDs, connection strings, or .env (gitignored).
- NEVER use or commit real company/client data. Mock or personal-tenant data only.
- In stdio mode, NEVER write to stdout (no print()). Log to stderr only.
- All Azure tools are READ-ONLY. No tool may modify Azure resources.
- Keep the tool surface to 5–6 tools; update SPEC.md before adding any.

## Code conventions
- Every tool = typed function + accurate docstring (FastMCP builds the schema from these).
- ToolError for client-visible errors; mask internal exceptions.
- Async for all I/O.

## Commands
- Run (local):  uv run server.py
- Run (remote): uv run server.py --transport http
- Inspect:      uv run fastmcp dev inspector server.py
- Test:         uv run pytest
- Lint:         uv run ruff check .