#!/usr/bin/env python3
"""Offline behavior tests for check_surface.py."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path


SCRIPT = Path(__file__).with_name("check_surface.py")


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["python3", str(SCRIPT), *args], text=True, capture_output=True, check=False)


def main() -> int:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        terms = root / "terms.txt"
        surface = root / "surface.md"
        terms.write_text("discarded label\n", encoding="utf-8")
        surface.write_text("Accepted result.\n", encoding="utf-8")
        passed = run("--terms-file", str(terms), "--root", str(root), str(surface))
        assert passed.returncode == 0, passed.stderr + passed.stdout
        assert json.loads(passed.stdout)["status"] == "PASS"

        surface.write_text("Discarded Label\n", encoding="utf-8")
        failed = run("--terms-file", str(terms), "--root", str(root), str(surface))
        assert failed.returncode == 1, failed.stderr + failed.stdout
        payload = json.loads(failed.stdout)
        assert payload["status"] == "FAIL"
        assert payload["failures"][0]["matched_term_count"] == 1
        assert "discarded label" not in failed.stdout.casefold()
    print("self-test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
