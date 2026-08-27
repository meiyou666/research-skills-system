#!/usr/bin/env python3
"""Explicit, tiny public-endpoint smoke test; excluded from offline acceptance."""

from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import subprocess
import sys
import tempfile


HERE = Path(__file__).resolve().parent
RUNNER = HERE / "run_campaign.py"
VALIDATOR = HERE / "validate_campaign.py"
SUPPORTED = {"crossref", "openalex", "arxiv", "europe-pmc", "pubmed"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--enable", action="store_true", help="confirm that a small public network request is authorized")
    parser.add_argument("--connector", choices=sorted(SUPPORTED), default="crossref")
    parser.add_argument("--query", default="GPU kernel measurement")
    parser.add_argument("--output", type=Path, help="preserve the smoke package at this path")
    args = parser.parse_args()
    if not args.enable:
        print("SKIP: pass --enable to authorize the optional online smoke test")
        return 0
    config = {
        "schema_version": 1,
        "campaign_id": f"online-smoke-{args.connector}-{date.today().isoformat()}",
        "queries": [{"id": "smoke-query", "text": args.query, "language": "en"}],
        "connectors": [{"id": "smoke-source", "type": args.connector, "enabled": True, "options": {}}],
        "limits": {
            "concurrency": 1,
            "max_pages_per_task": 1,
            "max_items_per_page": 3,
            "max_candidates": 3,
            "max_total_bytes": 1_000_000,
            "max_response_bytes": 1_000_000,
            "timeout_seconds": 20,
            "max_retries": 0,
            "backoff_seconds": 0,
            "max_depth": 0,
        },
        "fetch_policy": {"allowed_hosts": [], "retain_content": False, "max_fetch_pages": 0},
    }
    temporary = None
    if args.output is None:
        temporary = tempfile.TemporaryDirectory(prefix="research-source-online-smoke-")
        root = Path(temporary.name)
    else:
        root = args.output
        root.mkdir(parents=True, exist_ok=True)
    config_path = root / "smoke-config.json"
    package = root / "campaign"
    config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    completed = subprocess.run(
        [sys.executable, str(RUNNER), "--config", str(config_path), "--output", str(package)],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        print(json.dumps({
            "date": date.today().isoformat(),
            "connector": args.connector,
            "status": "runner-error",
            "detail": completed.stdout.strip() or completed.stderr.strip(),
        }, ensure_ascii=False))
        if temporary:
            temporary.cleanup()
        return 1
    validation = subprocess.run(
        [sys.executable, str(VALIDATOR), str(package), "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    state = json.loads((package / "campaign-state.json").read_text(encoding="utf-8"))
    gaps = json.loads((package / "failure-gaps.json").read_text(encoding="utf-8"))
    summary = {
        "date": date.today().isoformat(),
        "connector": args.connector,
        "query_count": 1,
        "requested_max_items": 3,
        "candidate_count": state["candidate_count"],
        "campaign_status": state["status"],
        "task_counts": state["task_counts"],
        "failure_count": len(gaps["errors"]),
        "access_gap_count": len(gaps["access_gaps"]),
        "validator_status": "pass" if validation.returncode == 0 else "fail",
    }
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    if temporary:
        temporary.cleanup()
    return 0 if validation.returncode == 0 and state["candidate_count"] > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
