# SPEC — azure-compliance-mcp

Design spec for the MCP server. This document is the source of truth for the
tool surface; **update it before adding or changing any tool** (per `CLAUDE.md`,
the tool count stays at 5–6).

Built with **FastMCP 3.x** (`from fastmcp import FastMCP`). All tools are
**read-only** — no tool may create, update, or delete an Azure resource.

---

## 1. Tools

Each tool is an async, typed Python function with an accurate docstring; FastMCP
derives the input schema from the signature and the description from the
docstring. Client-visible failures raise `ToolError`; internal exceptions are
masked.

Returns are JSON-serializable structures (typed dataclasses / `TypedDict`),
shaped to mirror Azure Resource Graph (ARG) rows where applicable.

### 1.1 `check_compliance`
Evaluate named security/governance controls by inspecting resource
configuration via Azure Resource Graph (ARG). Honest about provenance and about
controls it cannot evaluate from available data — it never guesses.

- **Params:** `control`, `status_filter`, `scope`, `resource_type` (unchanged),
  except `status_filter` now also accepts `"not_evaluable"`
  (values: `pass|fail|not_evaluable|all`, default `fail`).
- **Returns:** list of `{ resourceId, name, type, resourceGroup, subscriptionId,
  control, status: "pass"|"fail"|"not_evaluable", source, evidence, remediation }`
  - `source: "arg" | "azure_policy" | "defender"` — which data source produced this finding.
  - `not_evaluable` rows carry `evidence` explaining why (e.g. "guest-config posture
    not exposed in ARG resources table") and `remediation` pointing to where to look.

#### Control → source mapping
| control                  | source        | evaluable from base ARG? |
|--------------------------|---------------|--------------------------|
| required_tags            | arg           | yes (resources.tags)     |
| tls_min_1_2              | arg           | yes (resources.properties) |
| public_network_access    | arg           | yes (resources.properties) |
| disk_encryption          | arg           | OFF ⇒ fail (host-level only; ADE not assessed) |
| guest_config_extension   | azure_policy  | no — via policyresources/guestconfig |

- **Live behavior:** controls map to the table above. `guest_config_extension`
  queries the ARG `policyresources` table (guest-config compliance); if no data
  exists (no policy assigned), it returns `not_evaluable`, not `pass`.
- **Mock behavior:** the mock dataset is reshaped to be ARG-faithful, so the same
  mapping logic serves both modes (preserving the cross-mode equivalence discipline).
- **Notes:** `required_tags` checks `env`, `owner`, `costCenter`. The default call
  (`control=None`, `status_filter="fail"`) answers "what's actively non-compliant?"
  and excludes `not_evaluable`; those are reachable via `status_filter="not_evaluable"`
  and surfaced as a coverage count in `summarize_health`.

### 1.2 `query_resources`
General resource lookup with structured filters (a guarded subset of ARG/KQL).

- **Params:**
  - `resource_type: str | None`
  - `location: str | None`
  - `tag_filters: dict[str, str] | None`
  - `name_contains: str | None`
  - `limit: int = 100`
- **Returns:** list of ARG-shaped rows `{ id, name, type, location, resourceGroup, tags, subscriptionId }`.
- **Notes:** Read-only projection only; no mutating KQL operators accepted.

### 1.3 `get_patch_status`
Patch / update assessment across virtual machines.

- **Params:**
  - `scope: str | None`
  - `severity: Literal["critical", "security", "all"] = "all"`
  - `only_pending: bool = True`
- **Returns:** list of `{ vmId, name, osType, pendingUpdates, lastAssessed, rebootPending, classifications }`.

### 1.4 `find_orphaned_rbac`
Find role assignments whose principal (user / group / service principal) no
longer exists — a common security-hygiene gap.

- **Params:**
  - `scope: str | None`
  - `principal_type: Literal["user", "group", "servicePrincipal", "all"] = "all"`
- **Returns:** list of `{ roleAssignmentId, roleDefinitionName, principalId, principalType, scope, reason }`
  where `reason` explains why it is considered orphaned (e.g. `principal_not_found`).

### 1.5 `summarize_health`
Rolled-up infrastructure-health summary across the above signals — intended as
the agent's "give me the overall picture" entry point.

- **Params:**
  - `scope: str | None`
- **Returns:** `{ totals: {...}, compliance: {...}, patching: {...}, rbac: {...}, topFindings: [...] }`
  — counts plus a short prioritized list of the most important findings.

---

## 2. Provider design (`mock` | `live`)

A single `Provider` protocol abstracts the data layer; the concrete
implementation is chosen at startup by `--mode` (default `mock`).

```
providers/
  base.py     # Provider protocol: async methods backing each tool
  mock.py     # MockProvider  — seeded synthetic data
  live.py     # LiveProvider  — Azure Resource Graph
  factory.py  # get_provider(mode) -> Provider
```

- **`mock` (default):** Deterministic, seeded synthetic dataset shaped like ARG
  rows, deliberately including non-compliant resources, pending patches, and
  orphaned role assignments so every tool returns meaningful data. Requires **no
  Azure account or credentials** — the repo runs out of the box.
- **`live`:** Queries real **Azure Resource Graph** via
  `azure-mgmt-resourcegraph`, authenticating with `DefaultAzureCredential`
  (`azure-identity`) against the operator's **own** tenant. Strictly read-only.

Tools depend only on the `Provider` protocol, never on a concrete mode, so the
same tool code serves both.

**Filtering.** `list_resources` accepts an optional `ResourceFilter`
(resource_type / location / tag_filters / name_contains / limit). The mock
provider applies it in Python; the live provider pushes it into the ARG **KQL**
query (`where` clauses + `take`), with every user value encoded as an escaped
string literal (no raw concatenation → injection-safe; ARG is read-only anyway).
An opt-in contract test asserts the pushed-down path is equivalent to the
reference Python filter, so the two modes are provably consistent.

---

## 3. Transports

FastMCP transport selection via a `--transport` flag:

- **stdio** (default) — local use (e.g. Claude Desktop / IDE). `mcp.run()`.
  In this mode **stdout is reserved for the protocol**; all logging goes to stderr.
- **Streamable HTTP** — remote use. `mcp.run(transport="http", host=..., port=...)`,
  served at `/mcp`. Intended to sit behind **OAuth 2.1** for remote auth.
- SSE is legacy and not supported.

CLI (implemented in `server.py`; default mock + stdio):

```
uv run server.py [--mode mock|live] [--transport stdio|http] [--host H] [--port P]
```

---

## 4. Test plan

Tooling: **pytest** + **ruff**.

1. **Provider unit tests** — `MockProvider` returns deterministic, seeded data;
   each backing method yields the expected ARG-shaped rows, including the
   intentional non-compliant / orphaned / pending records.
2. **Tool tests (in-memory)** — exercise tools through an in-memory FastMCP
   client (no network), asserting schemas, defaults, and filter behavior, with
   the server bound to the mock provider.
3. **Error handling** — invalid arguments surface as `ToolError`; internal
   exceptions are masked, not leaked.
4. **Contract/schema** — each tool exposes the parameters and return shape
   documented above (guards against drift from this SPEC).
5. **Lint/format gate** — `ruff check .` is clean in CI.
6. **Live mode** — excluded from default CI (needs credentials); covered by an
   opt-in, manually-run smoke test against a personal tenant.
7. **Provider contract** — the same filter cases run against both providers; each
   provider's pushed-down filter must equal the reference Python filter over its
   own unfiltered data. The mock half runs in CI; the live half is opt-in
   (`RUN_LIVE_TESTS=1`). KQL generation/escaping is unit-tested in CI (no creds).

CI runs on every PR: `uv sync` → `uv run ruff check .` → `uv run pytest`.
