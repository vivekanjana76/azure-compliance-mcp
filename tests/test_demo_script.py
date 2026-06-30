"""Smoke test: the demo script runs end to end without error (SPEC §4)."""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEMO = REPO_ROOT / "scripts" / "demo.py"


def test_demo_script_runs_without_error():
    result = subprocess.run(
        [sys.executable, str(DEMO)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, result.stderr
    # It drives the real tools, so the three section headers must show up.
    assert "What's non-compliant?" in result.stdout
    assert "What can't be evaluated?" in result.stdout
    assert "Real resources via Azure Resource Graph" in result.stdout
