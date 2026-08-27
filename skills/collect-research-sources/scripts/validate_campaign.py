#!/usr/bin/env python3
"""Validate campaign structure, references, hashes, and lifecycle consistency."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sqlite3
from typing import Any

from source_collector.security import find_secret_shaped_config


SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
CONTENT_SCOPES = {"metadata", "discovery_snippet", "abstract", "partial_content", "full_text_candidate"}
COLLECTION_OUTCOMES = {
    "in_progress",
    "candidates_observed",
    "candidates_with_gaps",
    "no_candidates_observed",
    "no_candidates_with_gaps",
    "all_tasks_failed_or_limited",
    "no_tasks_observed",
}
REQUIRED_ROLES = {
    "redacted_config",
    "resume_state",
    "campaign_state",
    "candidate_inventory",
    "failure_gap_report",
    "query_log",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path, errors: list[str]) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        errors.append(f"{path.name}: invalid JSON: {exc}")
        return None


def safe_relative(value: Any) -> PurePosixPath | None:
    if not isinstance(value, str):
        return None
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        return None
    return path


def read_jsonl(path: Path, errors: list[str]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        errors.append(f"{path.name}: unreadable JSONL: {exc}")
        return output
    for number, line in enumerate(lines, start=1):
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"{path.name}:{number}: invalid JSON: {exc.msg}")
            continue
        if not isinstance(item, dict):
            errors.append(f"{path.name}:{number}: record must be an object")
        else:
            output.append(item)
    return output


def _validate_budget_observations(
    root: Path,
    config: dict[str, Any],
    state: dict[str, Any],
    gaps: dict[str, Any],
    errors: list[str],
    warnings: list[str],
) -> None:
    limits = config.get("limits")
    if not isinstance(limits, dict):
        errors.append("redacted config limits must be an object")
        return
    max_total = limits.get("max_total_bytes")
    watermark = limits.get("package_stop_watermark_bytes")
    if not isinstance(max_total, int) or isinstance(max_total, bool) or max_total < 1:
        errors.append("redacted config max_total_bytes is invalid")
    if not isinstance(watermark, int) or isinstance(watermark, bool) or watermark < 1:
        errors.append("redacted config package_stop_watermark_bytes is invalid")

    accepted = state.get("response_bytes")
    if not isinstance(accepted, int) or isinstance(accepted, bool) or accepted < 0:
        errors.append("campaign-state response_bytes is invalid")
    response_budget = state.get("response_budget")
    if not isinstance(response_budget, dict):
        errors.append("campaign-state response_budget must be an object")
    elif isinstance(max_total, int) and not isinstance(max_total, bool):
        expected_remaining = max_total - accepted if isinstance(accepted, int) and not isinstance(accepted, bool) else None
        if response_budget.get("accepted_bytes") != accepted:
            errors.append("campaign-state response_budget accepted_bytes is inconsistent")
        if response_budget.get("max_total_bytes") != max_total:
            errors.append("campaign-state response_budget max_total_bytes is inconsistent")
        if expected_remaining is None or response_budget.get("remaining_bytes") != expected_remaining:
            errors.append("campaign-state response_budget remaining_bytes is inconsistent")
        if response_budget.get("exhausted") is not (expected_remaining == 0):
            errors.append("campaign-state response_budget exhausted flag is inconsistent")
        if expected_remaining is not None and expected_remaining < 0:
            errors.append("accepted response bytes exceed max_total_bytes")

    coverage = gaps.get("coverage")
    if not isinstance(coverage, dict):
        errors.append("failure-gap coverage must be an object")
        coverage = {}
    elif coverage.get("response_bytes") != accepted:
        errors.append("failure-gap response_bytes is inconsistent with campaign state")
    if coverage.get("response_budget") != response_budget:
        errors.append("failure-gap response_budget is inconsistent with campaign state")

    package_observation = state.get("package_observation")
    if not isinstance(package_observation, dict):
        errors.append("campaign-state package_observation must be an object")
        return
    observed = package_observation.get("payload_bytes_after_export")
    hit = package_observation.get("stop_watermark_hit")
    if not isinstance(observed, int) or isinstance(observed, bool) or observed < 0:
        errors.append("campaign-state package observation byte count is invalid")
    else:
        actual_payload_bytes = sum(
            path.stat().st_size
            for path in root.rglob("*")
            if path.is_file()
            and not path.is_symlink()
            and path.relative_to(root).as_posix() not in {"manifest.json", "manifest.sha256"}
        )
        if observed != actual_payload_bytes:
            errors.append("campaign-state package byte observation does not match package payload")
    if package_observation.get("stop_watermark_bytes") != watermark:
        errors.append("campaign-state package watermark is inconsistent with redacted config")
    if not isinstance(package_observation.get("measurement_scope"), str) or not package_observation[
        "measurement_scope"
    ].strip():
        errors.append("campaign-state package measurement_scope is required")
    if not isinstance(hit, bool):
        errors.append("campaign-state package watermark hit flag must be boolean")
    elif isinstance(observed, int) and not isinstance(observed, bool) and isinstance(watermark, int):
        if hit != (observed >= watermark):
            errors.append("campaign-state package watermark hit flag is inconsistent")
        elif hit:
            warnings.append("campaign package stop watermark was reached by export publication")
    if coverage.get("package_observation") != package_observation:
        errors.append("failure-gap package observation is inconsistent with campaign state")


def validate(root: Path) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    try:
        root = root.resolve(strict=True)
    except OSError as exc:
        return [f"campaign package does not exist: {exc}"], warnings
    if not root.is_dir():
        return ["campaign package must be a directory"], warnings
    manifest_path = root / "manifest.json"
    manifest_hash_path = root / "manifest.sha256"
    if not manifest_path.is_file() or manifest_path.is_symlink():
        return ["manifest.json must be a regular file"], warnings
    if not manifest_hash_path.is_file() or manifest_hash_path.is_symlink():
        errors.append("manifest.sha256 must be a regular file")
    else:
        parts = manifest_hash_path.read_text(encoding="ascii", errors="replace").strip().split()
        if len(parts) != 2 or parts[1] != "manifest.json" or parts[0] != sha256_file(manifest_path):
            errors.append("manifest.sha256 does not match manifest.json")
    manifest = load_json(manifest_path, errors)
    if not isinstance(manifest, dict):
        return errors or ["manifest root must be an object"], warnings
    if manifest.get("schema_version") != 1:
        errors.append("manifest schema_version must be 1")
    if manifest.get("artifact_type") != "research_source_campaign":
        errors.append("manifest artifact_type is invalid")
    if manifest.get("status") not in {"partial", "complete", "failed"}:
        errors.append("manifest status is invalid")
    if manifest.get("collection_outcome") not in COLLECTION_OUTCOMES:
        errors.append("manifest collection_outcome is invalid")
    campaign_id = manifest.get("campaign_id")
    if not isinstance(campaign_id, str) or not campaign_id:
        errors.append("manifest campaign_id is required")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list):
        errors.append("manifest artifacts must be a list")
        artifacts = []
    roles: dict[str, list[Path]] = {}
    declared: set[str] = set()
    for index, artifact in enumerate(artifacts):
        if not isinstance(artifact, dict):
            errors.append(f"artifacts[{index}] must be an object")
            continue
        relative = safe_relative(artifact.get("path"))
        if relative is None:
            errors.append(f"artifacts[{index}].path is unsafe")
            continue
        relative_text = relative.as_posix()
        if relative_text in declared:
            errors.append(f"duplicate manifest path: {relative_text}")
            continue
        declared.add(relative_text)
        target = root.joinpath(*relative.parts)
        try:
            stat = target.lstat()
        except OSError:
            errors.append(f"manifest artifact is missing: {relative_text}")
            continue
        if not target.is_file() or target.is_symlink():
            errors.append(f"manifest artifact is not a regular file: {relative_text}")
            continue
        if artifact.get("bytes") != stat.st_size:
            errors.append(f"byte count mismatch: {relative_text}")
        if artifact.get("sha256") != sha256_file(target):
            errors.append(f"SHA256 mismatch: {relative_text}")
        role = artifact.get("role")
        if not isinstance(role, str) or not role:
            errors.append(f"artifacts[{index}].role is required")
        else:
            roles.setdefault(role, []).append(target)
    missing_roles = sorted(role for role in REQUIRED_ROLES if role not in roles)
    if missing_roles:
        errors.append("manifest is missing roles: " + ", ".join(missing_roles))
    allowed_undeclared = {"manifest.json", "manifest.sha256"}
    actual_files = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and not path.is_symlink()
    }
    undeclared = actual_files - declared - allowed_undeclared
    if undeclared:
        errors.append("unmanifested files: " + ", ".join(sorted(undeclared)))
    for path in root.rglob("*"):
        if path.is_symlink():
            errors.append(f"symbolic links are not allowed: {path.relative_to(root).as_posix()}")

    config = load_json(root / "campaign-config.redacted.json", errors)
    state = load_json(root / "campaign-state.json", errors)
    gaps = load_json(root / "failure-gaps.json", errors)
    if isinstance(config, dict):
        findings = find_secret_shaped_config(config)
        if findings:
            errors.extend(f"redacted config contains secret-shaped field: {item}" for item in findings)
    if isinstance(state, dict):
        if state.get("campaign_id") != campaign_id:
            errors.append("campaign-state ID does not match manifest")
        if state.get("status") != manifest.get("status"):
            errors.append("campaign-state status does not match manifest")
        if state.get("collection_outcome") != manifest.get("collection_outcome"):
            errors.append("campaign-state collection_outcome does not match manifest")
    if isinstance(gaps, dict) and gaps.get("campaign_id") != campaign_id:
        errors.append("failure-gap report ID does not match manifest")
    if isinstance(gaps, dict):
        if gaps.get("lifecycle_status") != manifest.get("status"):
            errors.append("failure-gap lifecycle status does not match manifest")
        if gaps.get("collection_outcome") != manifest.get("collection_outcome"):
            errors.append("failure-gap collection_outcome does not match manifest")
    if isinstance(config, dict) and isinstance(state, dict) and isinstance(gaps, dict):
        _validate_budget_observations(root, config, state, gaps, errors, warnings)

    inventory = read_jsonl(root / "candidate-inventory.jsonl", errors)
    query_log = read_jsonl(root / "query-log.jsonl", errors)
    candidate_ids: set[str] = set()
    for index, item in enumerate(inventory):
        prefix = f"candidate-inventory.jsonl record {index + 1}"
        item_id = item.get("candidate_id")
        if not isinstance(item_id, str) or not item_id:
            errors.append(f"{prefix}: candidate_id is required")
        elif item_id in candidate_ids:
            errors.append(f"{prefix}: duplicate candidate_id")
        else:
            candidate_ids.add(item_id)
        for field in ("canonical_key", "content_sha256", "hash_scope", "extractor_version", "access_level"):
            if not isinstance(item.get(field), str) or not item[field]:
                errors.append(f"{prefix}: {field} is required")
        if not SHA256_RE.fullmatch(str(item.get("content_sha256", ""))):
            errors.append(f"{prefix}: content_sha256 is invalid")
        if item.get("content_scope") not in CONTENT_SCOPES:
            errors.append(f"{prefix}: content_scope is invalid")
        if item.get("trust_boundary") != "untrusted_external_content":
            errors.append(f"{prefix}: trust boundary is missing")
        if not isinstance(item.get("queries"), list) or not item["queries"]:
            errors.append(f"{prefix}: query provenance is required")
        if not isinstance(item.get("occurrences"), list) or not item["occurrences"]:
            errors.append(f"{prefix}: connector occurrence provenance is required")
        reference = item.get("snapshot_or_reference")
        if isinstance(reference, str) and reference.startswith("snapshots/"):
            relative = safe_relative(reference)
            if relative is None or not (root / reference).is_file():
                errors.append(f"{prefix}: snapshot reference is broken")
            elif sha256_file(root / reference) != item.get("content_sha256"):
                errors.append(f"{prefix}: snapshot content hash mismatch")
        elif not isinstance(reference, str) or not reference:
            errors.append(f"{prefix}: snapshot_or_reference is required")
        elif reference.startswith(("/", "\\", ".")) or "\\" in reference or "\x00" in reference:
            errors.append(f"{prefix}: external reference resembles an unsafe local path")
        elif "://" not in reference:
            parts = PurePosixPath(reference).parts
            if any(part == ".." for part in parts):
                errors.append(f"{prefix}: external reference contains path traversal")
    for index, event in enumerate(query_log):
        for field in ("task_key", "query_id", "connector_id", "started_at", "finished_at", "outcome"):
            if not isinstance(event.get(field), str) or not event[field]:
                errors.append(f"query-log.jsonl record {index + 1}: {field} is required")

    database = root / "campaign.sqlite3"
    if database.is_file() and not database.is_symlink():
        _validate_database(
            database,
            campaign_id,
            manifest.get("status"),
            manifest.get("collection_outcome"),
            len(inventory),
            len(query_log),
            state.get("response_bytes") if isinstance(state, dict) else None,
            errors,
            warnings,
        )
    if manifest.get("status") == "partial":
        warnings.append("campaign is partial and may be resumed")
    if isinstance(gaps, dict):
        failed = gaps.get("failed_or_limited_tasks")
        if isinstance(failed, list) and failed:
            warnings.append(f"campaign records {len(failed)} failed, limited, or unfinished tasks")
        access = gaps.get("access_gaps")
        if isinstance(access, list) and access:
            warnings.append(f"campaign records {len(access)} metadata-only, snippet-only, or fetch-gap candidates")
        recorded_errors = gaps.get("errors")
        if isinstance(recorded_errors, list) and recorded_errors:
            warnings.append(f"campaign records {len(recorded_errors)} connector, normalization, or fetch errors")
    return errors, warnings


def _validate_database(
    path: Path,
    campaign_id: Any,
    manifest_status: Any,
    manifest_outcome: Any,
    inventory_count: int,
    query_event_count: int,
    accepted_response_bytes: Any,
    errors: list[str],
    warnings: list[str],
) -> None:
    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            errors.append(f"SQLite integrity check failed: {integrity}")
        required_tables = {
            "schema_info", "campaigns", "queries", "connectors", "tasks", "raw_records",
            "candidates", "occurrences", "relations", "snapshots", "query_events", "errors",
        }
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        missing = required_tables - tables
        if missing:
            errors.append("SQLite state is missing tables: " + ", ".join(sorted(missing)))
            return
        version = connection.execute("SELECT version FROM schema_info ORDER BY rowid DESC LIMIT 1").fetchone()
        if version is None or version[0] != 1:
            errors.append("SQLite schema version is not 1")
        campaign = connection.execute("SELECT * FROM campaigns").fetchone()
        if campaign is None:
            errors.append("SQLite campaign row is missing")
        else:
            if campaign["campaign_id"] != campaign_id:
                errors.append("SQLite campaign ID does not match manifest")
            if campaign["status"] != manifest_status:
                errors.append("SQLite campaign status does not match manifest")
            if campaign["response_bytes"] != accepted_response_bytes:
                errors.append("SQLite response-byte count does not match campaign state")
        if connection.execute("SELECT COUNT(*) FROM candidates").fetchone()[0] != inventory_count:
            errors.append("candidate inventory count does not match SQLite state")
        if connection.execute("SELECT COUNT(*) FROM query_events").fetchone()[0] != query_event_count:
            errors.append("query log count does not match SQLite state")
        task_counts = {
            row[0]: row[1]
            for row in connection.execute("SELECT state, COUNT(*) FROM tasks GROUP BY state")
        }
        failed_or_limited = task_counts.get("failed", 0) + task_counts.get("limited", 0)
        completed = task_counts.get("complete", 0)
        if manifest_status == "partial":
            expected_outcome = "in_progress"
        elif inventory_count:
            expected_outcome = "candidates_with_gaps" if failed_or_limited else "candidates_observed"
        elif completed:
            expected_outcome = "no_candidates_with_gaps" if failed_or_limited else "no_candidates_observed"
        elif failed_or_limited:
            expected_outcome = "all_tasks_failed_or_limited"
        else:
            expected_outcome = "no_tasks_observed"
        if manifest_outcome != expected_outcome:
            errors.append(
                f"collection_outcome is inconsistent with SQLite state: expected {expected_outcome}"
            )
        active = connection.execute(
            "SELECT COUNT(*) FROM tasks WHERE state IN ('pending', 'retry', 'running')"
        ).fetchone()[0]
        if manifest_status == "complete" and active:
            errors.append("complete campaign has unfinished SQLite tasks")
        if manifest_status == "partial" and not active:
            warnings.append("partial campaign has no unfinished tasks; inspect its stop rationale")
        orphan_occurrences = connection.execute(
            """
            SELECT COUNT(*) FROM occurrences o
            LEFT JOIN candidates c USING(candidate_id)
            LEFT JOIN raw_records r USING(raw_id)
            WHERE c.candidate_id IS NULL OR r.raw_id IS NULL
            """
        ).fetchone()[0]
        if orphan_occurrences:
            errors.append("SQLite state has orphan occurrence references")
    except sqlite3.Error as exc:
        errors.append(f"SQLite validation failed: {exc}")
    finally:
        if "connection" in locals():
            connection.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("package", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    errors, warnings = validate(args.package)
    if args.json:
        print(json.dumps({"errors": errors, "warnings": warnings}, indent=2, ensure_ascii=False))
    else:
        for warning in warnings:
            print(f"WARNING: {warning}")
        for error in errors:
            print(f"ERROR: {error}")
        if not errors:
            print("research source campaign: PASS")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
