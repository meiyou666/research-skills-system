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


RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def normalize_relative(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"required path must be a normalized relative path: {value}")
    return path


def read_text(path: Path, label: str | None = None) -> str:
    evidence_label = label or path.name
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"run evidence is missing or not a regular file: {evidence_label}")
    value = path.read_text(encoding="utf-8").strip()
    if not value:
        raise ValueError(f"run evidence is empty: {evidence_label}")
    return value


def normalized_absolute(value: object, label: str) -> Path:
    if not isinstance(value, str) or not Path(value).is_absolute() or os.path.normpath(value) != value:
        raise ValueError(f"execution record {label} must be a normalized absolute path")
    return Path(value)


def load_execution_record(
    path: Path, root: Path
) -> tuple[dict[str, object], list[PurePosixPath], dict[str, object], str]:
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
    result_path = normalized_absolute(record.get("remote_result_dir"), "remote_result_dir")
    run_path = normalized_absolute(record.get("remote_run_dir"), "remote_run_dir")
    work_path = normalized_absolute(record.get("remote_work_dir"), "remote_work_dir")
    if result_path.resolve(strict=True) != root or str(root) != str(result_path):
        raise ValueError("execution record result directory does not match --root")
    run_dir = run_path.resolve(strict=True)
    if not run_dir.is_dir() or str(run_dir) != str(run_path):
        raise ValueError("execution record run directory is invalid")
    work_dir = work_path.resolve(strict=True)
    if not work_dir.is_dir() or str(work_dir) != str(work_path):
        raise ValueError("execution record work directory is invalid")
    try:
        run_dir.relative_to(root)
    except ValueError:
        pass
    else:
        raise ValueError("execution record run directory must be outside the result root")

    required_value = record.get("required_results")
    if not isinstance(required_value, list) or not required_value or any(not isinstance(value, str) for value in required_value):
        raise ValueError("execution record required_results must be a non-empty list")
    required = [normalize_relative(value) for value in required_value]
    if len({value.as_posix() for value in required}) != len(required):
        raise ValueError("execution record contains duplicate required_results")

    expected_launch = record.get("launch_script_sha256")
    expected_validation = record.get("validation_script_sha256")
    for label, value in (("launch_script_sha256", expected_launch), ("validation_script_sha256", expected_validation)):
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

    expected_fields = {
        "state": "SUCCEEDED",
        "run.id": run_id,
        "work.dir": str(work_dir),
        "launch.exit_code": "0",
        "validation.exit_code": "0",
        "launch.sha256": expected_launch,
        "validation.sha256": expected_validation,
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
            if not telemetry_output.exists():
                raise ValueError("required telemetry output is missing")
            if not telemetry_output.is_file() or telemetry_output.is_symlink():
                raise ValueError("required telemetry output is not a regular file")
            try:
                telemetry_relative = telemetry_output.resolve(strict=True).relative_to(root).as_posix()
            except ValueError as exc:
                raise ValueError("required telemetry output must be inside the result root") from exc
            if telemetry_relative not in {path.as_posix() for path in required}:
                raise ValueError("required telemetry output must be a declared regular result")
        expected_fields.update(
            {
                "telemetry.sampler_sha256": telemetry["sampler_sha256"],
                "telemetry.config_sha256": telemetry["config_sha256"],
                "telemetry.output": str(telemetry_output),
            }
        )
    observed: dict[str, object] = {}
    for name, expected in expected_fields.items():
        actual = read_text(run_dir / name, name)
        if actual != expected:
            raise ValueError(f"run evidence mismatch for {name}: expected {expected}, observed {actual}")
        observed[name] = actual
    observed["started_at"] = read_text(run_dir / "started_at")
    observed["finished_at"] = read_text(run_dir / "finished_at")
    if telemetry is not None:
        observed["telemetry.start_exit_code"] = read_text(
            run_dir / "telemetry.start_exit_code", "telemetry.start_exit_code"
        )
        observed["telemetry.stop_exit_code"] = read_text(
            run_dir / "telemetry.stop_exit_code", "telemetry.stop_exit_code"
        )
        observed["telemetry.state"] = read_text(run_dir / "telemetry" / "state", "telemetry.state")
        if telemetry.get("required", False):
            if observed["telemetry.start_exit_code"] != "0" or observed["telemetry.stop_exit_code"] != "0":
                raise ValueError("required telemetry sampler did not start and stop cleanly")
            if observed["telemetry.state"] not in {"COMPLETED", "STOPPED"}:
                raise ValueError("required telemetry sampler has no valid terminal state")
            if not telemetry_output.is_file() or telemetry_output.is_symlink():
                raise ValueError("required telemetry output is missing or not a regular file")
    return record, required, observed, hashlib.sha256(record_bytes).hexdigest()


def resolve_member(root: Path, relative: PurePosixPath) -> Path:
    candidate = root.joinpath(*relative.parts)
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"symlink is not allowed: {relative}")
    resolved = candidate.resolve(strict=True)
    resolved.relative_to(root)
    return resolved


def inventory(root: Path) -> tuple[list[dict[str, object]], list[str]]:
    records: list[dict[str, object]] = []
    directories: list[str] = []
    for directory, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
        directory_path = Path(directory)
        if directory_path != root:
            directories.append(directory_path.relative_to(root).as_posix())
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
            records.append({"path": relative, "bytes": info.st_size, "sha256": sha256_file(candidate)})
    records.sort(key=lambda record: str(record["path"]).encode("utf-8"))
    directories.sort(key=lambda value: value.encode("utf-8"))
    return records, directories


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        temporary = Path(handle.name)
    os.replace(temporary, path)


def canonical_utc_timestamp(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty RFC3339 timestamp")
    candidate = value.strip()
    try:
        parsed = datetime.fromisoformat(candidate[:-1] + "+00:00" if candidate.endswith("Z") else candidate)
    except ValueError as exc:
        raise ValueError(f"{label} must be an RFC3339 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{label} must include a UTC offset")
    parsed = parsed.astimezone(timezone.utc)
    timespec = "microseconds" if parsed.microsecond else "seconds"
    return parsed.isoformat(timespec=timespec).replace("+00:00", "Z")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a deterministic SHA256 manifest for a remote result directory.")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--execution-record", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--created-at",
        help="Optional RFC3339 timestamp; defaults deterministically to execution evidence finished_at",
    )
    args = parser.parse_args()

    root = args.root.resolve(strict=True)
    if not root.is_dir() or args.root.is_symlink():
        raise SystemExit("result root must be a real directory")
    output = args.output.resolve(strict=False)
    try:
        output.relative_to(root)
    except ValueError:
        pass
    else:
        raise SystemExit("manifest output must be outside the result root")

    execution_record = args.execution_record.resolve(strict=True)
    try:
        execution_record.relative_to(root)
    except ValueError:
        pass
    else:
        raise SystemExit("execution record must be outside the result root")
    try:
        record, required, run_evidence, execution_record_sha256 = load_execution_record(execution_record, root)
    except (FileNotFoundError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    for relative in required:
        try:
            resolve_member(root, relative)
        except (FileNotFoundError, ValueError) as exc:
            raise SystemExit(f"required result is invalid: {relative}: {exc}") from exc

    try:
        files, directories = inventory(root)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    try:
        created_at = canonical_utc_timestamp(
            args.created_at if args.created_at is not None else run_evidence["finished_at"],
            "--created-at" if args.created_at is not None else "run evidence finished_at",
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    manifest = {
        "schema_version": 1,
        "artifact_type": "experiment_result_manifest",
        "run_id": record["run_id"],
        "created_at": created_at,
        "created_at_source": "caller" if args.created_at is not None else "run_evidence.finished_at",
        "execution_record_sha256": execution_record_sha256,
        "run_evidence": run_evidence,
        "required_paths": [path.as_posix() for path in required],
        "directories": directories,
        "files": files,
        "summary": {
            "directory_count": len(directories),
            "file_count": len(files),
            "total_bytes": sum(int(record["bytes"]) for record in files),
        },
    }
    atomic_json(output, manifest)
    print(
        json.dumps(
            {"status": "MANIFEST_CREATED", "run_id": record["run_id"], **manifest["summary"], "output": str(output)},
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
