"""Terminal demo for azure-compliance-mcp (mock mode).

Drives the *real* server tools through the same in-memory FastMCP client path
the tests use — no network, no Azure account — and prints the results as clean
bordered tables. Designed to be legible in a screen recording.

Run it:

    uv run python scripts/demo.py

Three labeled sections, each showing the actual tool call behind it:
  1. What's non-compliant?      -> check_compliance()  (default: fail rows)
  2. What can't be evaluated?   -> check_compliance(status_filter="not_evaluable")
  3. Real resources via ARG     -> query_resources()   (ARG-shaped projection)
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Allow `import server` when run as `python scripts/demo.py` (script dir, not the
# repo root, is sys.path[0]).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Box-drawing output is UTF-8; make sure Windows consoles don't choke on it.
for _stream in (sys.stdout, sys.stderr):
    reconfigure = getattr(_stream, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(encoding="utf-8")

from fastmcp import Client  # noqa: E402

import server  # noqa: E402

EVIDENCE_WIDTH = 58


def _trim(value: object, width: int) -> str:
    """Render ``value`` as a single line no wider than ``width`` (… if clipped)."""
    text = " ".join(str(value).split())  # collapse internal whitespace/newlines
    if len(text) <= width:
        return text
    return text[: width - 1] + "…"


def _render_table(headers: list[str], rows: list[list[str]], caps: list[int]) -> None:
    widths: list[int] = []
    for i, header in enumerate(headers):
        cap = caps[i]
        cells = [len(_trim(r[i], cap)) for r in rows]
        widths.append(min(cap, max(len(header), *cells) if cells else len(header)))

    def line(left: str, mid: str, right: str) -> str:
        return left + mid.join("─" * (w + 2) for w in widths) + right

    def row(cells: list[str]) -> str:
        padded = [_trim(c, widths[i]).ljust(widths[i]) for i, c in enumerate(cells)]
        return "│ " + " │ ".join(padded) + " │"

    print(line("┌", "┬", "┐"))
    print(row(headers))
    print(line("├", "┼", "┤"))
    for r in rows:
        print(row([str(c) for c in r]))
    print(line("└", "┴", "┘"))


def _section(number: int, question: str, call: str, note: str = "") -> None:
    title = f" {number}. {question}"
    print()
    print("═" * max(len(title) + 1, len(call) + 5))
    print(title)
    suffix = f"   # {note}" if note else ""
    print(f"    {call}{suffix}")
    print("═" * max(len(title) + 1, len(call) + 5))


async def main() -> None:
    print("\nazure-compliance-mcp — demo (mock provider, in-memory MCP client)")

    async with Client(server.mcp) as client:
        fails = (await client.call_tool("check_compliance", {})).data
        not_evaluable = (
            await client.call_tool(
                "check_compliance", {"status_filter": "not_evaluable"}
            )
        ).data
        resources = (await client.call_tool("query_resources", {})).data

    # 1. What's actively non-compliant? (the default view)
    _section(
        1, "What's non-compliant?", "check_compliance()", 'default status_filter="fail"'
    )
    _render_table(
        ["Resource", "Control", "Evidence"],
        [[r.name, r.control, _trim(r.evidence, EVIDENCE_WIDTH)] for r in fails],
        caps=[18, 22, EVIDENCE_WIDTH],
    )
    print(f"  → {len(fails)} failing findings.")

    # 2. What can't be evaluated from the data? (honest, not a fake pass)
    _section(
        2,
        "What can't be evaluated?",
        'check_compliance(status_filter="not_evaluable")',
    )
    _render_table(
        ["Resource", "Control", "Source", "Why"],
        [[r.name, r.control, r.source, _trim(r.evidence, 50)] for r in not_evaluable],
        caps=[16, 22, 12, 50],
    )
    print(
        f"  → {len(not_evaluable)} not-evaluable (no signal — never reported as a pass)."
    )

    # 3. Real resources via Azure Resource Graph (ARG-shaped rows)
    _section(3, "Real resources via Azure Resource Graph", "query_resources()")
    _render_table(
        ["Name", "Type", "Location", "Resource Group"],
        [[r.name, r.type, r.location, r.resourceGroup] for r in resources],
        caps=[18, 34, 12, 16],
    )
    print(f"  → {len(resources)} resources.\n")


if __name__ == "__main__":
    asyncio.run(main())
