#!/usr/bin/env python3
"""Validate analysis package structure, references, hashes, and status consistency."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
from pathlib import Path, PurePosixPath
from typing import Any


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
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        return None
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or not path.parts
        or ":" in path.parts[0]
        or path.as_posix() != value
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        return None
    return path


def lexical_absolute(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def inspect_directory_chain(path: Path, label: str) -> list[str]:
    """Inspect an absolute directory path without following any symlink."""

    errors: list[str] = []
    absolute = lexical_absolute(path)
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        try:
            entry = current.lstat()
        except OSError as exc:
            errors.append(f"{label} component cannot be inspected: {current}: {exc}")
            return errors
        if stat.S_ISLNK(entry.st_mode):
            errors.append(f"{label} path contains a symlink: {current}")
            return errors
        if not stat.S_ISDIR(entry.st_mode):
            errors.append(f"{label} component is not a directory: {current}")
            return errors
    return errors


def inventory_package(root: Path) -> tuple[set[str], set[str], list[str]]:
    """Inventory package members using lstat semantics and no link traversal."""

    files: set[str] = set()
    directories: set[str] = set()
    errors: list[str] = []

    def walk(directory: Path, relative: PurePosixPath) -> None:
        try:
            entries = sorted(os.scandir(directory), key=lambda entry: entry.name)
        except OSError as exc:
            label = relative.as_posix() if relative.parts else "."
            errors.append(f"cannot inspect package directory {label}: {exc}")
            return
        for entry in entries:
            child_relative = relative / entry.name
            label = child_relative.as_posix()
            try:
                metadata = entry.stat(follow_symlinks=False)
            except OSError as exc:
                errors.append(f"cannot inspect package member {label}: {exc}")
                continue
            if stat.S_ISLNK(metadata.st_mode):
                errors.append(f"package member is a symlink: {label}")
            elif stat.S_ISREG(metadata.st_mode):
                files.add(label)
            elif stat.S_ISDIR(metadata.st_mode):
                directories.add(label)
                walk(Path(entry.path), child_relative)
            else:
                errors.append(f"package member is a special file: {label}")

    walk(root, PurePosixPath())
    return files, directories, errors


def expected_directories(paths: set[str]) -> set[str]:
    result: set[str] = set()
    for value in paths:
        parent = PurePosixPath(value).parent
        while parent != PurePosixPath("."):
            result.add(parent.as_posix())
            parent = parent.parent
    return result


def resolve_regular_external(path: Path, label: str, errors: list[str]) -> Path | None:
    """Dereference a caller-supplied input and require a regular target file."""

    try:
        resolved = path.resolve(strict=True)
        metadata = resolved.stat()
    except (OSError, RuntimeError) as exc:
        errors.append(f"{label} cannot be inspected: {exc}")
        return None
    if not stat.S_ISREG(metadata.st_mode):
        errors.append(f"{label} must resolve to a regular file")
        return None
    return resolved


def validate(root: Path, input_file: Path | None = None, source_spec: Path | None = None) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    root = lexical_absolute(root)
    root_chain_errors = inspect_directory_chain(root, "analysis package")
    if root_chain_errors:
        return root_chain_errors, warnings
    try:
        root_metadata = root.lstat()
    except OSError as exc:
        return [f"analysis package cannot be inspected: {exc}"], warnings
    if not stat.S_ISDIR(root_metadata.st_mode) or stat.S_ISLNK(root_metadata.st_mode):
        return ["analysis package must be a regular directory, not a symlink or special file"], warnings
    manifest_path = root / "analysis-manifest.json"
    try:
        manifest_metadata = manifest_path.lstat()
    except OSError:
        return ["analysis-manifest.json must be a regular file"], warnings
    if not stat.S_ISREG(manifest_metadata.st_mode) or stat.S_ISLNK(manifest_metadata.st_mode):
        return ["analysis-manifest.json must be a regular file"], warnings
    manifest = load_json(manifest_path, errors)
    if not isinstance(manifest, dict):
        return errors or ["manifest root must be an object"], warnings
    if manifest.get("schema_version") != 1:
        errors.append("manifest schema_version must be 1")
    if manifest.get("artifact_type") != "experiment_analysis_manifest":
        errors.append("manifest artifact_type is invalid")
    if manifest.get("status") not in {"draft", "frozen"}:
        errors.append("manifest status must be draft or frozen")
    findings_status = manifest.get("findings_status")
    if findings_status is not None and findings_status not in {"draft", "accepted"}:
        errors.append("manifest findings_status must be draft or accepted")
    analysis_id = manifest.get("analysis_id")
    if not isinstance(analysis_id, str) or not analysis_id:
        errors.append("manifest analysis_id is required")

    outputs = manifest.get("outputs")
    if not isinstance(outputs, list):
        errors.append("manifest outputs must be a list")
        outputs = []
    declared: set[str] = set()
    roles: dict[str, Path] = {}
    for index, record in enumerate(outputs):
        if not isinstance(record, dict):
            errors.append(f"outputs[{index}] must be an object")
            continue
        relative = safe_relative(record.get("path"))
        if relative is None:
            errors.append(f"outputs[{index}].path is not normalized")
            continue
        relative_text = relative.as_posix()
        if relative_text == "analysis-manifest.json":
            errors.append("analysis-manifest.json is reserved and must not be declared as an output")
            continue
        if relative_text in declared:
            errors.append(f"duplicate output path: {relative_text}")
            continue
        declared.add(relative_text)
        candidate = root.joinpath(*relative.parts)
        role = record.get("role")
        if not isinstance(role, str) or not role:
            errors.append(f"outputs[{index}].role is required")
        elif role in roles:
            errors.append(f"duplicate output role: {role}")
        else:
            roles[role] = candidate

    actual_files, actual_directories, inventory_errors = inventory_package(root)
    errors.extend(inventory_errors)
    expected_files = declared | {"analysis-manifest.json"}
    expected_dirs = expected_directories(declared)
    for value in sorted(expected_files - actual_files):
        errors.append(f"missing regular package file: {value}")
    for value in sorted(actual_files - expected_files):
        errors.append(f"undeclared package file: {value}")
    for value in sorted(expected_dirs - actual_directories):
        errors.append(f"missing package directory: {value}")
    for value in sorted(actual_directories - expected_dirs):
        errors.append(f"undeclared package directory: {value}")

    roles = {
        role: candidate
        for role, candidate in roles.items()
        if candidate.relative_to(root).as_posix() in actual_files
    }

    for index, record in enumerate(outputs):
        if not isinstance(record, dict):
            continue
        relative = safe_relative(record.get("path"))
        if relative is None or relative.as_posix() not in actual_files:
            continue
        relative_text = relative.as_posix()
        if relative_text == "analysis-manifest.json":
            continue
        candidate = root.joinpath(*relative.parts)
        entry = candidate.lstat()
        if not stat.S_ISREG(entry.st_mode) or stat.S_ISLNK(entry.st_mode):
            errors.append(f"output is not a regular file: {relative_text}")
            continue
        if not isinstance(record.get("bytes"), int) or isinstance(record.get("bytes"), bool) or record.get("bytes") != entry.st_size:
            errors.append(f"byte count mismatch: {relative_text}")
        if record.get("sha256") != sha256_file(candidate):
            errors.append(f"SHA256 mismatch: {relative_text}")

    for role in ("analysis_spec", "metric_dictionary", "derived_observations", "derived_summary", "statistics"):
        if role not in roles:
            errors.append(f"manifest is missing required role: {role}")
    if "bad_cases" not in roles:
        warnings.append("bad-case table is not declared")
    if "draft_findings" not in roles and "findings" not in roles:
        warnings.append("findings are not declared")

    spec = load_json(roles["analysis_spec"], errors) if "analysis_spec" in roles else None
    dictionary = load_json(roles["metric_dictionary"], errors) if "metric_dictionary" in roles else None
    statistics_value = load_json(roles["statistics"], errors) if "statistics" in roles else None
    if isinstance(spec, dict):
        if spec.get("analysis_id") != analysis_id:
            errors.append("analysis spec ID does not match manifest")
        if spec.get("status") != manifest.get("status"):
            errors.append("analysis spec status does not match manifest")
        blockers = spec.get("unresolved_blockers", [])
        if blockers and manifest.get("status") == "draft":
            warnings.append(f"draft package retains {len(blockers)} unresolved blocker(s)")
    metric_ids: set[str] = set()
    if isinstance(dictionary, dict):
        if dictionary.get("analysis_id") != analysis_id:
            errors.append("metric dictionary ID does not match manifest")
        metrics = dictionary.get("metrics")
        if not isinstance(metrics, list):
            errors.append("metric dictionary metrics must be a list")
        else:
            for index, metric in enumerate(metrics):
                metric_id = metric.get("id") if isinstance(metric, dict) else None
                if not isinstance(metric_id, str) or not metric_id:
                    errors.append(f"metric dictionary metrics[{index}].id is required")
                elif metric_id in metric_ids:
                    errors.append(f"duplicate metric id: {metric_id}")
                else:
                    metric_ids.add(metric_id)
                if isinstance(metric, dict):
                    for field in ("numerator", "denominator"):
                        if not metric.get(field):
                            warnings.append(f"metric {metric_id or index} has no {field}")
    if isinstance(statistics_value, dict):
        if statistics_value.get("analysis_id") != analysis_id:
            errors.append("statistics ID does not match manifest")
        for index, summary in enumerate(statistics_value.get("summaries", [])):
            if isinstance(summary, dict) and summary.get("metric_id") not in metric_ids:
                errors.append(f"statistics summary[{index}] references unknown metric")

    input_record = manifest.get("input", {})
    if input_file is not None:
        input_file = resolve_regular_external(input_file, "input file", errors)
        if input_file is not None and (input_record.get("bytes") != input_file.stat().st_size or input_record.get("sha256") != sha256_file(input_file)):
            errors.append("input file does not match manifest")
    else:
        warnings.append("input bytes were not independently rechecked")
    source_record = manifest.get("source_spec", {})
    if source_spec is not None:
        source_spec = resolve_regular_external(source_spec, "source spec", errors)
        if source_spec is not None and (source_record.get("bytes") != source_spec.stat().st_size or source_record.get("sha256") != sha256_file(source_spec)):
            errors.append("source spec does not match manifest")
    else:
        warnings.append("source spec bytes were not independently rechecked")

    if manifest.get("status") == "frozen":
        if "findings" not in roles:
            errors.append("frozen package needs an accepted findings role")
        if findings_status != "accepted":
            errors.append("frozen package findings_status must be accepted")
        if isinstance(spec, dict) and spec.get("unresolved_blockers"):
            errors.append("frozen package has unresolved blockers")
    elif findings_status in {None, "draft"}:
        warnings.append("findings remain draft and need scientific review")
    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("package", type=Path)
    parser.add_argument("--input-file", type=Path)
    parser.add_argument("--source-spec", type=Path)
    args = parser.parse_args()
    try:
        errors, warnings = validate(args.package, args.input_file, args.source_spec)
    except OSError as exc:
        print(f"ERROR: {exc}")
        return 2
    for warning in warnings:
        print(f"WARNING: {warning}")
    for error in errors:
        print(f"ERROR: {error}")
    if errors:
        return 1
    print("analysis package: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
