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

# Column caps are tuned so every table stays ≤ 80 columns wide — legible in a
# phone-sized screen recording. The `guest_config_extension` control name forces
# a 22-col control column, so section 1's evidence is capped tighter to fit.
EVIDENCE_WIDTH = 32
WHY_WIDTH = 40


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
    call_line = f"    {call}" + (f"   # {note}" if note else "")
    width = max(len(title), len(call_line)) + 1
    print()
    print("═" * width)
    print(title)
    print(call_line)
    print("═" * width)


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
    # Every not_evaluable row is guest_config_extension, so the control is noted
    # in the caption rather than spending a column on a constant value.
    _section(
        2,
        "What can't be evaluated?",
        'check_compliance(status_filter="not_evaluable")',
    )
    _render_table(
        ["Resource", "Source", "Why"],
        [[r.name, r.source, _trim(r.evidence, WHY_WIDTH)] for r in not_evaluable],
        caps=[18, 14, WHY_WIDTH],
    )
    print(
        f"  → {len(not_evaluable)} guest_config_extension rows — "
        "no policy data, never a pass."
    )

    # 3. Real resources via Azure Resource Graph (ARG-shaped rows)
    _section(3, "Real resources via Azure Resource Graph", "query_resources()")
    _render_table(
        ["Name", "Type", "Resource Group"],
        [[r.name, r.type, r.resourceGroup] for r in resources],
        caps=[18, 34, 16],
    )
    print(f"  → {len(resources)} resources.\n")


if __name__ == "__main__":
    asyncio.run(main())
