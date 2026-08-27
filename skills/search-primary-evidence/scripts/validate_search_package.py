#!/usr/bin/env python3
"""Check mechanical consistency of a primary-evidence search package."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Any


def _nonempty_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _trace_records(value: Any) -> str:
    """Classify a provenance/query collection as missing, valid, or invalid."""

    if value is None or value == "" or value == [] or value == {}:
        return "missing"
    if _nonempty_text(value):
        return "valid"
    if isinstance(value, dict):
        return "valid" if value else "missing"
    if isinstance(value, list):
        if not value:
            return "missing"
        if all(_nonempty_text(item) or (isinstance(item, dict) and bool(item)) for item in value):
            return "valid"
    return "invalid"


def validate(value: Any) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(value, dict):
        return ["root must be an object"], warnings
    if value.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    if not isinstance(value.get("search_id"), str) or not value.get("search_id", "").strip():
        errors.append("search_id is required")
    if not isinstance(value.get("version"), int) or isinstance(value.get("version"), bool) or value.get("version", 0) < 1:
        errors.append("version must be a positive integer")
    if value.get("status") not in {"draft", "frozen"}:
        errors.append("status must be draft or frozen")
    if not isinstance(value.get("scope"), dict):
        errors.append("scope must be an object")

    sources = value.get("sources")
    if not isinstance(sources, list):
        errors.append("sources must be a list")
        sources = []
    seen: set[str] = set()
    for index, source in enumerate(sources):
        if not isinstance(source, dict):
            errors.append(f"sources[{index}] must be an object")
            continue
        source_id = source.get("id")
        if not isinstance(source_id, str) or not source_id.strip():
            errors.append(f"sources[{index}].id is required")
        elif source_id in seen:
            errors.append(f"duplicate source id: {source_id}")
        else:
            seen.add(source_id)
        if not isinstance(source.get("locator"), str) or not source.get("locator", "").strip():
            errors.append(f"sources[{index}].locator is required")
        if source.get("access_level") not in {"V0", "V1", "V2", "V3"}:
            errors.append(f"sources[{index}].access_level is invalid")
        if source.get("decision") not in {"include", "exclude", "pending", "context_only"}:
            errors.append(f"sources[{index}].decision is invalid")
        for field in ("source_type", "discovery_route"):
            field_value = source.get(field)
            if field_value in (None, ""):
                message = f"sources[{index}].{field} is not recorded"
                if value.get("status") == "frozen":
                    errors.append(message)
                else:
                    warnings.append(message)
            elif not _nonempty_text(field_value):
                errors.append(f"sources[{index}].{field} must be a non-empty string")
        relevance = source.get("relevance")
        if relevance in (None, ""):
            warnings.append(f"sources[{index}] has no relevance note")
        elif not _nonempty_text(relevance):
            errors.append(f"sources[{index}].relevance must be a non-empty string")
        decision_reason = source.get("decision_reason")
        if decision_reason in (None, ""):
            message = f"sources[{index}] has no decision reason"
            if value.get("status") == "frozen":
                errors.append(message)
            else:
                warnings.append(message)
        elif not _nonempty_text(decision_reason):
            errors.append(f"sources[{index}].decision_reason must be a non-empty string")

    if not sources:
        warnings.append("source inventory is empty")
    entry_points_state = _trace_records(value.get("entry_points"))
    queries_state = _trace_records(value.get("queries"))
    if entry_points_state == "missing":
        warnings.append("entry points are not recorded")
    elif entry_points_state == "invalid":
        errors.append("entry_points must be a non-empty string, object, or list of records")
    if queries_state == "missing":
        warnings.append("queries or query-log reference are not recorded")
    elif queries_state == "invalid":
        errors.append("queries must be a non-empty string, object, or list of records")
    coverage = value.get("coverage")
    stop_reason_valid = False
    if coverage is None or coverage == {}:
        warnings.append("coverage statement is not recorded")
    elif not isinstance(coverage, dict):
        errors.append("coverage must be an object")
    elif coverage.get("stop_reason") in (None, ""):
        warnings.append("coverage stop rationale is not recorded")
    elif not _nonempty_text(coverage.get("stop_reason")):
        errors.append("coverage.stop_reason must be a non-empty string")
    else:
        stop_reason_valid = True
    if value.get("status") == "frozen":
        if any(source.get("decision") == "pending" for source in sources if isinstance(source, dict)):
            errors.append("frozen package contains pending source decisions")
        if not stop_reason_valid:
            errors.append("frozen package needs a coverage stop rationale")
        if entry_points_state == "missing":
            errors.append("frozen package needs entry-point or supplied-inventory provenance")
        if queries_state == "missing":
            errors.append("frozen package needs query records or an external query-log reference")
    return errors, warnings


def fixture() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "search_id": "search-1",
        "version": 1,
        "status": "draft",
        "scope": {"object": "example"},
        "entry_points": ["official registry"],
        "queries": [{"query": "example outcome"}],
        "sources": [{"id": "S1", "locator": "https://example.org/source", "source_type": "primary article", "discovery_route": "official registry", "access_level": "V1", "decision": "include", "relevance": "direct", "decision_reason": "matches scope"}],
        "coverage": {"stop_reason": "orientation complete"},
    }


def self_test() -> None:
    assert validate(fixture()) == ([], [])
    draft = fixture()
    draft["sources"] = []
    errors, warnings = validate(draft)
    assert errors == [] and "source inventory is empty" in warnings
    frozen = fixture()
    frozen["status"] = "frozen"
    frozen["sources"][0]["decision"] = "pending"
    assert any("pending" in error for error in validate(frozen)[0])
    frozen_missing_provenance = fixture()
    frozen_missing_provenance["status"] = "frozen"
    frozen_missing_provenance["entry_points"] = []
    frozen_missing_provenance["queries"] = []
    frozen_missing_provenance["sources"][0].pop("decision_reason")
    missing_errors, _ = validate(frozen_missing_provenance)
    assert any("entry-point" in error for error in missing_errors)
    assert any("query records" in error for error in missing_errors)
    assert any("decision reason" in error for error in missing_errors)
    truthy_scalars = fixture()
    truthy_scalars["status"] = "frozen"
    truthy_scalars["entry_points"] = 1
    truthy_scalars["queries"] = True
    truthy_scalars["coverage"] = {"stop_reason": 42}
    truthy_scalars["sources"][0]["decision_reason"] = 1
    scalar_errors, _ = validate(truthy_scalars)
    assert any("entry_points must" in error for error in scalar_errors)
    assert any("queries must" in error for error in scalar_errors)
    assert any("coverage.stop_reason" in error for error in scalar_errors)
    assert any("decision_reason must" in error for error in scalar_errors)
    equivalent = fixture()
    equivalent["status"] = "frozen"
    equivalent["entry_points"] = [{"kind": "supplied_inventory", "sha256": "0" * 64}]
    equivalent["queries"] = [{"kind": "external_query_log", "locator": "urn:query-log:1"}]
    equivalent["coverage"] = {"stop_reason": "bounded to the supplied corpus"}
    assert validate(equivalent) == ([], [])
    with tempfile.TemporaryDirectory() as directory:
        Path(directory, "package.json").write_text(json.dumps(fixture()), encoding="utf-8")
    print("self-test: PASS")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("package", nargs="?", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.package is None:
        parser.error("package is required unless --self-test is used")
    try:
        value = json.loads(args.package.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        print(f"ERROR: invalid JSON: {exc}")
        return 2
    errors, warnings = validate(value)
    for warning in warnings:
        print(f"WARNING: {warning}")
    for error in errors:
        print(f"ERROR: {error}")
    if errors:
        return 1
    print("search package: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
