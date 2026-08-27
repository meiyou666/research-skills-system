#!/usr/bin/env python3
"""Check experiment artifact structure, references, hashes, and freeze consistency."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


PROTOCOL_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "research_input": ("hypothesis_input", "research_brief"),
    "questions_or_hypotheses": ("questions", "hypotheses", "hypothesis_map"),
    "design": ("study_design",),
    "outcomes": ("outcome_variables", "metrics"),
    "decision_rules": ("decisions",),
    "sampling": ("sampling_plan",),
    "analysis": ("analysis_plan",),
    "stop_rules": ("stopping_rules", "stop_policy"),
    "unresolved_blockers": ("blockers",),
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path, errors: list[str]) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        errors.append(f"{path.name}: invalid JSON: {exc}")
        return None


def check_common(
    name: str,
    value: Any,
    errors: list[str],
    *,
    id_field: str = "contract_id",
    id_aliases: tuple[str, ...] = (),
) -> None:
    if not isinstance(value, dict):
        errors.append(f"{name}: root must be an object")
        return
    if value.get("schema_version") != 1:
        errors.append(f"{name}: schema_version must be 1")
    identifiers: list[tuple[str, Any]] = [
        (field, value[field]) for field in (id_field, *id_aliases) if field in value
    ]
    valid_identifiers = [
        (field, identifier)
        for field, identifier in identifiers
        if isinstance(identifier, str) and identifier.strip()
    ]
    if not valid_identifiers:
        aliases = f" (accepted alias: {', '.join(id_aliases)})" if id_aliases else ""
        errors.append(f"{name}.{id_field} is required{aliases}")
    else:
        distinct = {identifier.strip() for _, identifier in valid_identifiers}
        if len(distinct) > 1:
            detail = ", ".join(f"{field}={identifier!r}" for field, identifier in valid_identifiers)
            errors.append(f"{name}: identifier aliases conflict: {detail}")
        for field, identifier in identifiers:
            if not isinstance(identifier, str) or not identifier.strip():
                errors.append(f"{name}.{field} must be a non-empty string when present; got {identifier!r}")
    if not isinstance(value.get("version"), int) or isinstance(value.get("version"), bool) or value.get("version", 0) < 1:
        errors.append(f"{name}: version must be a positive integer")
    if value.get("status") not in {"draft", "frozen"}:
        errors.append(f"{name}: status must be draft or frozen")


def equivalent_field(value: dict[str, Any], canonical: str) -> tuple[Any, str | None]:
    for field in (canonical, *PROTOCOL_FIELD_ALIASES.get(canonical, ())):
        candidate = value.get(field)
        if candidate not in (None, "", [], {}):
            return candidate, field
    return None, None


def contract_declarations(
    protocol: dict[str, Any], errors: list[str]
) -> dict[str, dict[str, Any]]:
    declarations = {
        "data": {"declared": False, "required": False, "contract_id": None, "sha256": None},
        "execution": {"declared": False, "required": False, "contract_id": None, "sha256": None},
    }
    contracts = protocol.get("contracts")
    if contracts is not None and not isinstance(contracts, dict):
        errors.append(f"experiment-protocol.json.contracts must be an object; got {type(contracts).__name__}")
        contracts = None
    for kind in declarations:
        declaration = declarations[kind]
        value = contracts.get(kind) if isinstance(contracts, dict) else None
        if value is None:
            equivalent_contract = protocol.get(f"{kind}_contract")
            equivalent_id = protocol.get(f"{kind}_contract_id")
            if any(
                item not in (None, "", False, {}, [])
                for item in (equivalent_contract, equivalent_id)
            ):
                declaration["declared"] = True
                declaration["required"] = True
                if isinstance(equivalent_id, str) and equivalent_id.strip():
                    declaration["contract_id"] = equivalent_id.strip()
                elif isinstance(equivalent_contract, str) and equivalent_contract.strip():
                    declaration["contract_id"] = equivalent_contract.strip()
            continue
        declaration["declared"] = True
        if isinstance(value, bool):
            declaration["required"] = value
        elif isinstance(value, str):
            if not value.strip():
                errors.append(
                    f"experiment-protocol.json.contracts.{kind} string ID must be non-empty"
                )
            else:
                declaration["required"] = True
                declaration["contract_id"] = value.strip()
        elif isinstance(value, dict):
            required = value.get("required", True)
            if not isinstance(required, bool):
                errors.append(
                    f"experiment-protocol.json.contracts.{kind}.required must be a boolean; got {required!r}"
                )
            else:
                declaration["required"] = required
            id_fields = ("contract_id", f"{kind}_contract_id")
            identifiers = [(field, value[field]) for field in id_fields if field in value]
            valid_identifiers = [
                (field, identifier.strip())
                for field, identifier in identifiers
                if isinstance(identifier, str) and identifier.strip()
            ]
            for field, identifier in identifiers:
                if not isinstance(identifier, str) or not identifier.strip():
                    errors.append(
                        f"experiment-protocol.json.contracts.{kind}.{field} "
                        "must be a non-empty string when present"
                    )
            distinct_ids = {identifier for _, identifier in valid_identifiers}
            if len(distinct_ids) > 1:
                errors.append(
                    f"experiment-protocol.json.contracts.{kind}: identifier aliases conflict"
                )
            elif valid_identifiers:
                declaration["contract_id"] = valid_identifiers[0][1]
            declared_hash = value.get("sha256")
            if declared_hash is not None:
                if not isinstance(declared_hash, str) or not re.fullmatch(
                    r"[0-9a-fA-F]{64}", declared_hash
                ):
                    errors.append(
                        f"experiment-protocol.json.contracts.{kind}.sha256 "
                        "must be 64 hexadecimal characters"
                    )
                else:
                    declaration["sha256"] = declared_hash.lower()
        else:
            errors.append(
                f"experiment-protocol.json.contracts.{kind} must be a boolean, string ID, or object; "
                f"got {type(value).__name__}"
            )
    return declarations


def validate_protocol(
    protocol: Any, errors: list[str], warnings: list[str]
) -> dict[str, dict[str, Any]]:
    check_common(
        "experiment-protocol.json",
        protocol,
        errors,
        id_field="protocol_id",
        id_aliases=("contract_id",),
    )
    if not isinstance(protocol, dict):
        return {
            "data": {"declared": False, "required": False, "contract_id": None, "sha256": None},
            "execution": {"declared": False, "required": False, "contract_id": None, "sha256": None},
        }
    for field in ("research_input", "questions_or_hypotheses", "design", "outcomes", "decision_rules"):
        _, actual_field = equivalent_field(protocol, field)
        if actual_field is None:
            aliases = ", ".join(PROTOCOL_FIELD_ALIASES.get(field, ()))
            suffix = f" (accepted equivalents: {aliases})" if aliases else ""
            warnings.append(f"experiment-protocol.json.{field} is not recorded{suffix}")
    for field in ("sampling", "analysis", "stop_rules"):
        _, actual_field = equivalent_field(protocol, field)
        if actual_field is None:
            aliases = ", ".join(PROTOCOL_FIELD_ALIASES.get(field, ()))
            suffix = f" (accepted equivalents: {aliases})" if aliases else ""
            warnings.append(f"experiment-protocol.json.{field} is not recorded{suffix}")
    blockers, blocker_field = equivalent_field(protocol, "unresolved_blockers")
    blockers = [] if blocker_field is None else blockers
    if blockers and not isinstance(blockers, list):
        errors.append(
            f"experiment-protocol.json.{blocker_field} must be a list; got {type(blockers).__name__}"
        )
    if protocol.get("status") == "frozen" and blockers:
        errors.append("experiment-protocol.json: frozen protocol has unresolved blockers")
    return contract_declarations(protocol, errors)


def artifact_identifier(
    value: Any, canonical: str, aliases: tuple[str, ...]
) -> str | None:
    if not isinstance(value, dict):
        return None
    for field in (canonical, *aliases):
        identifier = value.get(field)
        if isinstance(identifier, str) and identifier.strip():
            return identifier.strip()
    return None


def check_protocol_declaration(
    kind: str,
    declaration: dict[str, Any],
    path: Path,
    artifact: Any,
    errors: list[str],
) -> None:
    aliases = ("data_contract_id",) if kind == "data" else ("execution_contract_id",)
    declared_id = declaration.get("contract_id")
    if declared_id is not None:
        actual_id = artifact_identifier(artifact, "contract_id", aliases)
        if actual_id is not None and actual_id != declared_id:
            errors.append(
                f"experiment-protocol.json.contracts.{kind}.contract_id mismatch: "
                f"declared {declared_id!r}, actual {actual_id!r}"
            )
    declared_hash = declaration.get("sha256")
    if declared_hash is not None and digest(path) != declared_hash:
        errors.append(f"experiment-protocol.json.contracts.{kind}.sha256 mismatch")


def validate(root_or_protocol: Path) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    if root_or_protocol.is_file():
        if root_or_protocol.name == "experiment-protocol.json":
            return validate(root_or_protocol.parent)
        protocol = load(root_or_protocol, errors)
        if not errors:
            declarations = validate_protocol(protocol, errors, warnings)
            for kind, declaration in declarations.items():
                if declaration["required"]:
                    message = (
                        f"experiment-protocol.json declares {kind}-contract.json required; "
                        "protocol-only validation cannot verify it"
                    )
                    if isinstance(protocol, dict) and protocol.get("status") == "frozen":
                        errors.append(message)
                    else:
                        warnings.append(message)
        return errors, warnings

    root = root_or_protocol
    protocol_path = root / "experiment-protocol.json"
    if not protocol_path.is_file() or protocol_path.is_symlink():
        return ["missing regular file: experiment-protocol.json"], warnings
    protocol = load(protocol_path, errors)
    if errors:
        return errors, warnings
    declarations = validate_protocol(protocol, errors, warnings)

    data_path = root / "data-contract.json"
    execution_path = root / "execution-contract.json"
    data_present = data_path.is_file() and not data_path.is_symlink()
    execution_present = execution_path.is_file() and not execution_path.is_symlink()
    data = load(data_path, errors) if data_present else None
    execution = load(execution_path, errors) if execution_present else None
    if not data_present:
        if declarations["data"]["required"]:
            message = "data-contract.json is declared required but is not present"
            if isinstance(protocol, dict) and protocol.get("status") == "frozen":
                errors.append(message)
            else:
                warnings.append(message)
    else:
        check_protocol_declaration(
            "data", declarations["data"], data_path, data, errors
        )
        if data is not None:
            check_common(
                "data-contract.json", data, errors, id_aliases=("data_contract_id",)
            )
            if isinstance(data, dict) and not data.get("datasets"):
                warnings.append("data-contract.json: datasets are not recorded")
    if not execution_present:
        if declarations["execution"]["required"]:
            message = "execution-contract.json is declared required but is not present"
            if isinstance(protocol, dict) and protocol.get("status") == "frozen":
                errors.append(message)
            else:
                warnings.append(message)
    else:
        check_protocol_declaration(
            "execution", declarations["execution"], execution_path, execution, errors
        )
        if execution is not None:
            check_common(
                "execution-contract.json",
                execution,
                errors,
                id_aliases=("execution_contract_id",),
            )
        if isinstance(execution, dict):
            if execution.get("protocol_sha256") and execution.get("protocol_sha256") != digest(protocol_path):
                errors.append("execution-contract.json: protocol_sha256 mismatch")
            if data is not None and execution.get("data_contract_sha256") and execution.get("data_contract_sha256") != digest(data_path):
                errors.append("execution-contract.json: data_contract_sha256 mismatch")
            for field in ("run_matrix", "entrypoint", "completion", "runtime_limits", "result_bundle"):
                if not execution.get(field):
                    warnings.append(f"execution-contract.json: {field} is not recorded")
            runs = execution.get("run_matrix", [])
            if runs and not isinstance(runs, list):
                errors.append("execution-contract.json: run_matrix must be a list")
            elif isinstance(runs, list):
                seen: set[str] = set()
                for index, run in enumerate(runs):
                    if not isinstance(run, dict):
                        errors.append(f"execution-contract.json: run_matrix[{index}] must be an object")
                        continue
                    run_id = run.get("run_id")
                    if not isinstance(run_id, str) or not run_id:
                        errors.append(f"execution-contract.json: run_matrix[{index}].run_id is required")
                    elif run_id in seen:
                        errors.append(f"execution-contract.json: duplicate run_id {run_id}")
                    else:
                        seen.add(run_id)

    artifacts = [value for value in (protocol, data, execution) if isinstance(value, dict)]
    if any(value.get("status") == "frozen" for value in artifacts) and len({value.get("status") for value in artifacts}) > 1:
        errors.append("present contracts cannot mix frozen and draft status")
    if isinstance(execution, dict) and execution.get("status") == "frozen":
        if data is None:
            errors.append("frozen execution contract needs data-contract.json")
        if not execution.get("protocol_sha256") or not execution.get("data_contract_sha256"):
            errors.append("frozen execution contract needs cross-file hashes")
    return errors, warnings


def fixture() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "protocol_id": "protocol-1",
        "version": 1,
        "status": "draft",
        "research_input": {"kind": "equivalent_input"},
        "questions_or_hypotheses": [{"id": "H1"}],
        "design": {"comparison": "A versus B"},
        "outcomes": [{"name": "outcome"}],
        "decision_rules": [{"id": "D1"}],
        "sampling": {"basis": "precision"},
        "analysis": {"estimand": "difference"},
        "stop_rules": [{"id": "S1"}],
        "unresolved_blockers": [],
    }


def self_test() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        protocol = fixture()
        protocol_path = root / "experiment-protocol.json"
        protocol_path.write_text(json.dumps(protocol), encoding="utf-8")
        errors, warnings = validate(root)
        assert errors == [] and warnings == []
        equivalent = fixture()
        equivalent["contract_id"] = equivalent.pop("protocol_id")
        equivalent["hypotheses"] = equivalent.pop("questions_or_hypotheses")
        equivalent["study_design"] = equivalent.pop("design")
        equivalent["metrics"] = equivalent.pop("outcomes")
        equivalent["stopping_rules"] = equivalent.pop("stop_rules")
        equivalent_path = root / "equivalent-protocol.json"
        equivalent_path.write_text(json.dumps(equivalent), encoding="utf-8")
        assert validate(equivalent_path) == ([], [])
        conflict = fixture()
        conflict["contract_id"] = "different-protocol"
        conflict_path = root / "conflicting-protocol.json"
        conflict_path.write_text(json.dumps(conflict), encoding="utf-8")
        assert any("identifier aliases conflict" in error for error in validate(conflict_path)[0])
        protocol["contracts"] = {"data": {"required": True}, "execution": {"required": False}}
        protocol_path.write_text(json.dumps(protocol), encoding="utf-8")
        assert any("data-contract.json" in warning for warning in validate(root)[1])
        protocol.pop("contracts")
        protocol_path.write_text(json.dumps(protocol), encoding="utf-8")
        data = {"schema_version": 1, "contract_id": "data-1", "version": 1, "status": "draft", "datasets": [{"name": "raw"}]}
        data_path = root / "data-contract.json"
        data_path.write_text(json.dumps(data), encoding="utf-8")
        execution = {"schema_version": 1, "contract_id": "execution-1", "version": 1, "status": "draft", "protocol_sha256": digest(protocol_path), "data_contract_sha256": digest(data_path), "run_matrix": [{"run_id": "run-1"}], "entrypoint": {"argv": ["run"]}, "completion": {"validator": "check"}, "runtime_limits": {"seconds": 1}, "result_bundle": {"required": ["raw"]}}
        (root / "execution-contract.json").write_text(json.dumps(execution), encoding="utf-8")
        assert validate(root) == ([], [])
        execution["protocol_sha256"] = "0" * 64
        (root / "execution-contract.json").write_text(json.dumps(execution), encoding="utf-8")
        assert any("mismatch" in error for error in validate(root)[0])

        optional_root = root / "optional"
        optional_root.mkdir()
        optional_protocol = fixture()
        optional_protocol["contracts"] = {
            "data": {"required": False},
            "execution": False,
        }
        (optional_root / "experiment-protocol.json").write_text(
            json.dumps(optional_protocol), encoding="utf-8"
        )
        assert validate(optional_root) == ([], [])

        frozen_missing_root = root / "frozen-missing"
        frozen_missing_root.mkdir()
        frozen_missing = fixture()
        frozen_missing["status"] = "frozen"
        frozen_missing["contracts"] = {
            "data": {"required": True},
            "execution": {"required": True},
        }
        (frozen_missing_root / "experiment-protocol.json").write_text(
            json.dumps(frozen_missing), encoding="utf-8"
        )
        missing_errors, missing_warnings = validate(frozen_missing_root)
        assert any("data-contract.json is declared required" in error for error in missing_errors)
        assert any(
            "execution-contract.json is declared required" in error for error in missing_errors
        )
        assert not any("declared required" in warning for warning in missing_warnings)
        (frozen_missing_root / "data-contract.json").write_text("{", encoding="utf-8")
        invalid_errors, _ = validate(frozen_missing_root)
        assert any("data-contract.json: invalid JSON" in error for error in invalid_errors)
        assert not any(
            "data-contract.json is declared required" in error for error in invalid_errors
        )

        declared_root = root / "declared"
        declared_root.mkdir()
        declared_data = {
            "schema_version": 1,
            "data_contract_id": "data-declared",
            "version": 1,
            "status": "draft",
            "datasets": [{"name": "raw"}],
        }
        declared_data_path = declared_root / "data-contract.json"
        declared_data_path.write_text(json.dumps(declared_data), encoding="utf-8")
        declared_execution = {
            "schema_version": 1,
            "execution_contract_id": "execution-declared",
            "version": 1,
            "status": "draft",
            "run_matrix": [{"run_id": "run-1"}],
            "entrypoint": {"argv": ["run"]},
            "completion": {"validator": "check"},
            "runtime_limits": {"seconds": 1},
            "result_bundle": {"required": ["raw"]},
        }
        declared_execution_path = declared_root / "execution-contract.json"
        declared_execution_path.write_text(json.dumps(declared_execution), encoding="utf-8")
        declared_protocol = fixture()
        declared_protocol["contracts"] = {
            "data": {
                "required": True,
                "contract_id": "data-declared",
                "sha256": digest(declared_data_path),
            },
            "execution": {
                "required": True,
                "execution_contract_id": "execution-declared",
                "sha256": digest(declared_execution_path),
            },
        }
        declared_protocol_path = declared_root / "experiment-protocol.json"
        declared_protocol_path.write_text(json.dumps(declared_protocol), encoding="utf-8")
        assert validate(declared_root) == ([], [])

        declared_protocol["contracts"]["data"]["contract_id"] = "wrong-data"
        declared_protocol_path.write_text(json.dumps(declared_protocol), encoding="utf-8")
        assert any(
            "contracts.data.contract_id mismatch" in error
            for error in validate(declared_root)[0]
        )
        declared_protocol["contracts"]["data"]["contract_id"] = "data-declared"
        declared_protocol["contracts"]["execution"]["sha256"] = "0" * 64
        declared_protocol_path.write_text(json.dumps(declared_protocol), encoding="utf-8")
        assert any(
            "contracts.execution.sha256 mismatch" in error
            for error in validate(declared_root)[0]
        )

        standalone_frozen = fixture()
        standalone_frozen["status"] = "frozen"
        standalone_frozen["contracts"] = {"data": {"required": True}}
        standalone_path = root / "standalone-frozen.json"
        standalone_path.write_text(json.dumps(standalone_frozen), encoding="utf-8")
        assert any(
            "protocol-only validation cannot verify" in error
            for error in validate(standalone_path)[0]
        )
    print("self-test: PASS")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.path is None:
        parser.error("path is required unless --self-test is used")
    errors, warnings = validate(args.path)
    for warning in warnings:
        print(f"WARNING: {warning}")
    for error in errors:
        print(f"ERROR: {error}")
    if errors:
        return 1
    print("experiment artifacts: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
