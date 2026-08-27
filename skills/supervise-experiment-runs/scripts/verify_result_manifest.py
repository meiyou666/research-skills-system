#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any


RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        temporary = Path(handle.name)
    os.replace(temporary, path)


def normalized_relative(value: Any) -> PurePosixPath:
    if not isinstance(value, str):
        raise ValueError("manifest path must be a string")
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"manifest path is not normalized: {value}")
    return path


def normalized_absolute(value: Any, label: str) -> str:
    if not isinstance(value, str) or not Path(value).is_absolute() or os.path.normpath(value) != value:
        raise ValueError(f"execution record {label} must be a normalized absolute path")
    return value


def load_execution_record(path: Path) -> tuple[dict[str, Any], str, list[str], dict[str, str], str]:
    try:
        record_bytes = path.read_bytes()
        record = json.loads(record_bytes.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"execution record is invalid: {exc}") from exc
    if not isinstance(record, dict) or record.get("schema_version") != 1:
        raise ValueError("execution record schema_version must be 1")
    run_id = record.get("run_id")
    if not isinstance(run_id, str) or RUN_ID.fullmatch(run_id) is None:
        raise ValueError("execution record run_id is invalid")
    project_revision = record.get("project_revision")
    if not isinstance(project_revision, str) or not project_revision:
        raise ValueError("execution record project_revision is missing")
    environment_sha = record.get("environment_validation_sha256")
    if not isinstance(environment_sha, str) or len(environment_sha) != 64 or any(char not in "0123456789abcdef" for char in environment_sha):
        raise ValueError("execution record environment_validation_sha256 is invalid")
    work_dir = normalized_absolute(record.get("remote_work_dir"), "remote_work_dir")
    normalized_absolute(record.get("remote_run_dir"), "remote_run_dir")
    normalized_absolute(record.get("remote_result_dir"), "remote_result_dir")
    required_value = record.get("required_results")
    if not isinstance(required_value, list) or not required_value or any(not isinstance(value, str) for value in required_value):
        raise ValueError("execution record required_results must be a non-empty list")
    required = [normalized_relative(value).as_posix() for value in required_value]
    if len(set(required)) != len(required):
        raise ValueError("execution record contains duplicate required_results")
    launch_sha = record.get("launch_script_sha256")
    validation_sha = record.get("validation_script_sha256")
    for label, value in (("launch_script_sha256", launch_sha), ("validation_script_sha256", validation_sha)):
        if not isinstance(value, str) or len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
            raise ValueError(f"execution record {label} is invalid")
    for label in ("maximum_runtime_seconds", "validation_timeout_seconds", "no_progress_seconds", "heartbeat_seconds"):
        value = record.get(label)
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise ValueError(f"execution record {label} must be a positive integer")
    progress_source = record.get("progress_source")
    normalized_absolute(progress_source, "progress_source")
    recovery_entry_point = record.get("recovery_entry_point")
    if not isinstance(recovery_entry_point, str) or not recovery_entry_point.strip():
        raise ValueError("execution record recovery_entry_point is missing")
    expected_evidence = {
        "state": "SUCCEEDED",
        "run.id": run_id,
        "work.dir": work_dir,
        "launch.exit_code": "0",
        "validation.exit_code": "0",
        "launch.sha256": str(launch_sha),
        "validation.sha256": str(validation_sha),
        "maximum_runtime_seconds": str(record.get("maximum_runtime_seconds")),
        "validation_timeout_seconds": str(record.get("validation_timeout_seconds")),
        "no_progress_seconds": str(record.get("no_progress_seconds")),
        "heartbeat_seconds": str(record.get("heartbeat_seconds")),
        "progress.file": progress_source,
    }
    telemetry = record.get("telemetry")
    if telemetry is not None:
        if not isinstance(telemetry, dict):
            raise ValueError("execution record telemetry must be an object")
        for label in ("sampler_sha256", "config_sha256"):
            value = telemetry.get(label)
            if not isinstance(value, str) or len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
                raise ValueError(f"execution record telemetry.{label} is invalid")
        telemetry_output = normalized_absolute(telemetry.get("output"), "telemetry.output")
        required_telemetry = telemetry.get("required", False)
        if not isinstance(required_telemetry, bool):
            raise ValueError("execution record telemetry.required must be boolean")
        if required_telemetry:
            result_root = PurePosixPath(normalized_absolute(record.get("remote_result_dir"), "remote_result_dir"))
            try:
                telemetry_relative = PurePosixPath(telemetry_output).relative_to(result_root).as_posix()
            except ValueError as exc:
                raise ValueError("required telemetry output must be inside the result root") from exc
            if telemetry_relative not in required:
                raise ValueError("required telemetry output must be a declared result")
        expected_evidence.update(
            {
                "telemetry.sampler_sha256": telemetry["sampler_sha256"],
                "telemetry.config_sha256": telemetry["config_sha256"],
                "telemetry.output": telemetry_output,
            }
        )
        if required_telemetry:
            expected_evidence.update(
                {"telemetry.start_exit_code": "0", "telemetry.stop_exit_code": "0"}
            )
    return record, run_id, required, expected_evidence, hashlib.sha256(record_bytes).hexdigest()


def local_inventory(root: Path) -> tuple[dict[str, tuple[int, str]], set[str]]:
    observed: dict[str, tuple[int, str]] = {}
    directories: set[str] = set()
    for directory, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
        directory_path = Path(directory)
        if directory_path != root:
            directories.add(directory_path.relative_to(root).as_posix())
        for name in list(dirnames):
            candidate = directory_path / name
            if candidate.is_symlink():
                raise ValueError(f"symlink is not allowed: {candidate.relative_to(root).as_posix()}")
        for name in filenames:
            candidate = directory_path / name
            relative = candidate.relative_to(root).as_posix()
            info = candidate.lstat()
            if stat.S_ISLNK(info.st_mode):
                raise ValueError(f"symlink is not allowed: {relative}")
            if not stat.S_ISREG(info.st_mode):
                raise ValueError(f"non-regular file is not allowed: {relative}")
            observed[relative] = (info.st_size, sha256_file(candidate))
    return observed, directories


def validate_manifest(
    value: Any,
) -> tuple[str, str, dict[str, str], dict[str, tuple[int, str]], set[str], list[PurePosixPath], int, int, int]:
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise ValueError("unsupported manifest schema")
    if value.get("artifact_type") not in {"experiment_result_manifest", "remote_experiment_result_manifest"}:
        raise ValueError("unexpected manifest artifact type")
    run_id = value.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("manifest run_id is missing")
    execution_sha = value.get("execution_record_sha256")
    if not isinstance(execution_sha, str) or len(execution_sha) != 64 or any(char not in "0123456789abcdef" for char in execution_sha):
        raise ValueError("manifest execution_record_sha256 is invalid")
    run_evidence = value.get("run_evidence")
    if not isinstance(run_evidence, dict) or any(not isinstance(key, str) or not isinstance(item, str) for key, item in run_evidence.items()):
        raise ValueError("manifest run_evidence is invalid")
    records = value.get("files")
    if not isinstance(records, list):
        raise ValueError("manifest files must be a list")
    expected: dict[str, tuple[int, str]] = {}
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("manifest file record must be an object")
        relative = normalized_relative(record.get("path")).as_posix()
        byte_count = record.get("bytes")
        digest = record.get("sha256")
        if relative in expected:
            raise ValueError(f"duplicate manifest path: {relative}")
        if not isinstance(byte_count, int) or byte_count < 0:
            raise ValueError(f"invalid byte count: {relative}")
        if not isinstance(digest, str) or len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise ValueError(f"invalid SHA256: {relative}")
        expected[relative] = (byte_count, digest)
    directory_value = value.get("directories")
    if not isinstance(directory_value, list):
        raise ValueError("manifest directories must be a list")
    expected_directories = {normalized_relative(path).as_posix() for path in directory_value}
    if len(expected_directories) != len(directory_value):
        raise ValueError("manifest contains duplicate directories")
    required_value = value.get("required_paths")
    if not isinstance(required_value, list):
        raise ValueError("manifest required_paths must be a list")
    required = [normalized_relative(path) for path in required_value]
    summary = value.get("summary")
    if not isinstance(summary, dict):
        raise ValueError("manifest summary is missing")
    file_count = len(expected)
    directory_count = len(expected_directories)
    total_bytes = sum(size for size, _ in expected.values())
    if (
        summary.get("directory_count") != directory_count
        or summary.get("file_count") != file_count
        or summary.get("total_bytes") != total_bytes
    ):
        raise ValueError("manifest summary does not match file records")
    return run_id, execution_sha, run_evidence, expected, expected_directories, required, directory_count, file_count, total_bytes


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify a local result tree against a remote SHA256 manifest.")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--execution-record", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    root = args.root.resolve(strict=True)
    if not root.is_dir() or args.root.is_symlink():
        raise SystemExit("local result root must be a real directory")
    manifest_path = args.manifest.resolve(strict=True)
    execution_record_path = args.execution_record.resolve(strict=True)
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        (
            run_id,
            manifest_execution_sha,
            run_evidence,
            expected,
            expected_directories,
            required,
            directory_count,
            file_count,
            total_bytes,
        ) = validate_manifest(manifest)
        execution_record, expected_run_id, record_required, expected_evidence, execution_record_sha = load_execution_record(execution_record_path)
        observed, observed_directories = local_inventory(root)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc

    if manifest_execution_sha != execution_record_sha:
        raise SystemExit("manifest is not bound to the supplied execution record")
    if run_id != expected_run_id:
        raise SystemExit(f"manifest run_id mismatch: expected {expected_run_id}, observed {run_id}")
    manifest_required = [path.as_posix() for path in required]
    if manifest_required != record_required:
        raise SystemExit("manifest required paths do not match the execution record")
    for name, expected_value in expected_evidence.items():
        if run_evidence.get(name) != expected_value:
            raise SystemExit(f"manifest run evidence does not match the execution record: {name}")
    telemetry = execution_record.get("telemetry")
    if isinstance(telemetry, dict) and telemetry.get("required", False):
        if run_evidence.get("telemetry.state") not in {"COMPLETED", "STOPPED"}:
            raise SystemExit("manifest required telemetry has no valid terminal state")
    if not isinstance(run_evidence.get("started_at"), str) or not isinstance(run_evidence.get("finished_at"), str):
        raise SystemExit("manifest run evidence is missing terminal timestamps")

    missing_required = []
    for relative in required:
        candidate = root.joinpath(*relative.parts)
        try:
            candidate.resolve(strict=True).relative_to(root)
        except (FileNotFoundError, ValueError):
            missing_required.append(relative.as_posix())

    missing = sorted(set(expected) - set(observed), key=lambda value: value.encode("utf-8"))
    extra = sorted(set(observed) - set(expected), key=lambda value: value.encode("utf-8"))
    changed = sorted(
        (path for path in set(expected) & set(observed) if expected[path] != observed[path]),
        key=lambda value: value.encode("utf-8"),
    )
    missing_directories = sorted(expected_directories - observed_directories, key=lambda value: value.encode("utf-8"))
    extra_directories = sorted(observed_directories - expected_directories, key=lambda value: value.encode("utf-8"))
    if missing_required or missing or extra or changed or missing_directories or extra_directories:
        raise SystemExit(
            json.dumps(
                {
                    "missing_required": missing_required,
                    "missing": missing,
                    "extra": extra,
                    "changed": changed,
                    "missing_directories": missing_directories,
                    "extra_directories": extra_directories,
                },
                sort_keys=True,
            )
        )

    report = {
        "schema_version": 1,
        "artifact_type": "experiment_result_verification",
        "status": "VERIFIED",
        "run_id": run_id,
        "verified_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "manifest_sha256": sha256_file(manifest_path),
        "execution_record_sha256": execution_record_sha,
        "directory_count": directory_count,
        "file_count": file_count,
        "total_bytes": total_bytes,
    }
    if args.report:
        atomic_json(args.report, report)
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
