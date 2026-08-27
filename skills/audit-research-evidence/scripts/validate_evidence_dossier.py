#!/usr/bin/env python3
"""Check mechanical integrity of an evidence dossier without judging science."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


LABELS = {"DIRECT", "SOURCE_CLAIM", "INFERENCE", "UNKNOWN"}
ACCESS_LEVELS = ("V0", "V1", "V2", "V3")


def _nonempty_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _structured_note(value: Any) -> str:
    """Classify a textual or structured provenance/boundary note."""

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
    if not _nonempty_text(value.get("dossier_id")):
        errors.append("dossier_id is required")
    if not isinstance(value.get("version"), int) or isinstance(value.get("version"), bool) or value.get("version", 0) < 1:
        errors.append("version must be a positive integer")
    if value.get("status") not in {"draft", "frozen"}:
        errors.append("status must be draft or frozen")
    purpose_state = _structured_note(value.get("purpose"))
    inventory_state = _structured_note(value.get("source_inventory"))
    if purpose_state == "missing":
        warnings.append("audit purpose is not recorded")
    elif purpose_state == "invalid":
        errors.append("purpose must be a non-empty string, object, or list of records")
    if inventory_state == "missing":
        warnings.append("source-inventory provenance is not recorded")
    elif inventory_state == "invalid":
        errors.append("source_inventory must be a non-empty string, object, or list of records")

    records = value.get("source_records")
    if not isinstance(records, list):
        errors.append("source_records must be a list")
        records = []
    source_ids: set[str] = set()
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            errors.append(f"source_records[{index}] must be an object")
            continue
        source_id = record.get("id")
        if not _nonempty_text(source_id):
            errors.append(f"source_records[{index}].id is required")
        elif source_id in source_ids:
            errors.append(f"duplicate source id: {source_id}")
        else:
            source_ids.add(source_id)
        if not _nonempty_text(record.get("locator")):
            errors.append(f"source_records[{index}].locator is required")
        access_level = record.get("access_level")
        if access_level not in ACCESS_LEVELS:
            allowed = ", ".join(ACCESS_LEVELS)
            errors.append(
                f"source_records[{index}].access_level must be one of {allowed}; got {access_level!r}"
            )
        for field in ("object", "population", "method", "result", "limitations"):
            if not record.get(field):
                warnings.append(f"source_records[{index}] has no {field}")

    statements = value.get("evidence_statements")
    if not isinstance(statements, list):
        errors.append("evidence_statements must be a list")
        statements = []
    statement_ids: set[str] = set()
    for index, statement in enumerate(statements):
        if not isinstance(statement, dict):
            errors.append(f"evidence_statements[{index}] must be an object")
            continue
        statement_id = statement.get("id")
        if not _nonempty_text(statement_id):
            errors.append(f"evidence_statements[{index}].id is required")
        elif statement_id in statement_ids:
            errors.append(f"duplicate evidence statement id: {statement_id}")
        else:
            statement_ids.add(statement_id)
        if statement.get("label") not in LABELS:
            errors.append(f"evidence_statements[{index}].label is invalid")
        if not _nonempty_text(statement.get("text")):
            errors.append(f"evidence_statements[{index}].text is required")
        source_refs = statement.get("source_ids", [])
        if not isinstance(source_refs, list):
            errors.append(f"evidence_statements[{index}].source_ids must be a list")
            source_refs = []
        else:
            for source_id in source_refs:
                if not _nonempty_text(source_id):
                    errors.append(
                        f"evidence_statements[{index}].source_ids entries must be non-empty strings"
                    )
                elif source_id not in source_ids:
                    errors.append(f"evidence_statements[{index}] references unknown source {source_id}")
        if statement.get("label") in {"DIRECT", "SOURCE_CLAIM", "INFERENCE"} and not source_refs:
            errors.append(f"evidence_statements[{index}] needs a source reference")
        if statement.get("label") in {"DIRECT", "SOURCE_CLAIM", "INFERENCE"}:
            access_by_id = {
                record.get("id"): record.get("access_level")
                for record in records
                if isinstance(record, dict) and isinstance(record.get("id"), str)
            }
            discovery_only = [
                source_id
                for source_id in source_refs
                if isinstance(source_id, str) and access_by_id.get(source_id) == "V0"
            ]
            if discovery_only:
                errors.append(
                    f"evidence_statements[{index}] uses discovery-only V0 source(s): "
                    + ", ".join(discovery_only)
                )
        if statement.get("label") == "INFERENCE":
            reasoning_state = _structured_note(statement.get("reasoning"))
            if reasoning_state == "missing":
                warnings.append(f"evidence_statements[{index}] has no inference reasoning")
            elif reasoning_state == "invalid":
                errors.append(
                    f"evidence_statements[{index}].reasoning must be a non-empty string, object, or list of records"
                )
        boundary_state = _structured_note(statement.get("boundary"))
        if boundary_state == "missing":
            warnings.append(f"evidence_statements[{index}] has no boundary")
        elif boundary_state == "invalid":
            errors.append(
                f"evidence_statements[{index}].boundary must be a non-empty string, object, or list of records"
            )

    if not statements:
        warnings.append("dossier has no evidence statements")
    if value.get("status") == "frozen" and not statements:
        errors.append("frozen dossier must contain an evidence statement")
    if value.get("status") == "frozen":
        if purpose_state == "missing":
            errors.append("frozen dossier needs an audit purpose")
        if inventory_state == "missing":
            errors.append("frozen dossier needs source-inventory or equivalent-input provenance")
        for index, statement in enumerate(statements):
            if isinstance(statement, dict) and _structured_note(statement.get("boundary")) == "missing":
                errors.append(f"frozen evidence_statements[{index}] needs a claim boundary")
    return errors, warnings


def fixture() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "dossier_id": "dossier-1",
        "version": 1,
        "status": "draft",
        "purpose": "Check an example claim",
        "source_inventory": {"kind": "equivalent_input", "note": "user-supplied source"},
        "source_records": [{"id": "S1", "locator": "https://example.org/source", "access_level": "V3", "object": "sample", "population": "declared", "method": "measurement", "result": "observed", "limitations": "bounded"}],
        "evidence_statements": [{"id": "E1", "text": "The source reports an observation.", "label": "DIRECT", "source_ids": ["S1"], "boundary": "declared population"}],
        "conflicts": [],
        "coverage_limits": [],
    }


def self_test() -> None:
    assert validate(fixture()) == ([], [])
    partial = fixture()
    partial["source_records"][0]["population"] = ""
    assert validate(partial)[0] == [] and any("population" in warning for warning in validate(partial)[1])
    broken = fixture()
    broken["evidence_statements"][0]["source_ids"] = ["missing"]
    assert any("unknown source" in error for error in validate(broken)[0])
    bad_access = fixture()
    bad_access["source_records"][0]["access_level"] = "public_metadata_api"
    access_errors = validate(bad_access)[0]
    assert any(
        "source_records[0].access_level" in error
        and "V0, V1, V2, V3" in error
        and "public_metadata_api" in error
        for error in access_errors
    )
    invalid_source_reference = fixture()
    invalid_source_reference["evidence_statements"][0]["source_ids"] = [{"id": "S1"}]
    assert any("entries must be non-empty strings" in error for error in validate(invalid_source_reference)[0])
    discovery_claim = fixture()
    discovery_claim["source_records"][0]["access_level"] = "V0"
    assert any("discovery-only V0" in error for error in validate(discovery_claim)[0])
    frozen_missing_provenance = fixture()
    frozen_missing_provenance["status"] = "frozen"
    frozen_missing_provenance["source_inventory"] = {}
    frozen_missing_provenance["evidence_statements"][0]["boundary"] = ""
    frozen_errors, _ = validate(frozen_missing_provenance)
    assert any("source-inventory" in error for error in frozen_errors)
    assert any("claim boundary" in error for error in frozen_errors)
    truthy_scalars = fixture()
    truthy_scalars["status"] = "frozen"
    truthy_scalars["purpose"] = 1
    truthy_scalars["source_inventory"] = 1
    truthy_scalars["source_records"][0]["locator"] = 1
    truthy_scalars["evidence_statements"][0]["text"] = 1
    truthy_scalars["evidence_statements"][0]["boundary"] = 1
    scalar_errors, _ = validate(truthy_scalars)
    assert any("purpose must" in error for error in scalar_errors)
    assert any("source_inventory must" in error for error in scalar_errors)
    assert any("locator is required" in error for error in scalar_errors)
    assert any("text is required" in error for error in scalar_errors)
    assert any("boundary must" in error for error in scalar_errors)
    equivalent = fixture()
    equivalent["status"] = "frozen"
    equivalent["source_inventory"] = [
        {"kind": "equivalent_input", "description": "caller-supplied reviewed primary source"}
    ]
    equivalent["evidence_statements"][0]["boundary"] = {
        "population": "declared population",
        "setting": "reported setting",
    }
    assert validate(equivalent) == ([], [])
    print("self-test: PASS")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("dossier", nargs="?", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.dossier is None:
        parser.error("dossier is required unless --self-test is used")
    try:
        value = json.loads(args.dossier.read_text(encoding="utf-8"))
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
    print("evidence dossier: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
