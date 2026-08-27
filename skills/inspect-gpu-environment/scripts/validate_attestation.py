#!/usr/bin/env python3
"""Validate an inspect-gpu-environment bundle.

Errors are limited to schema, reference, hash, and evidence-status consistency.
Absent GPUs, inaccessible topology, and missing telemetry are warnings so a
well-formed no-GPU attestation remains valid.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import stat
import sys
from typing import Any, Iterator

from inspect_gpu_environment import (
    MANIFEST_SCHEMA_NAME,
    MANIFEST_SCHEMA_VERSION,
    REFERENCE_CATALOG,
    SCHEMA_NAME,
    SCHEMA_VERSION,
)


ALLOWED_EVIDENCE_STATUSES = {"observed", "reported", "unavailable"}
MAX_ATTESTATION_BYTES = 8 * 1024 * 1024
MAX_MANIFEST_BYTES = 512 * 1024
MAX_DIGEST_BYTES = 1024


def diagnostic(severity: str, code: str, path: str, message: str) -> dict[str, str]:
    return {"severity": severity, "code": code, "path": path, "message": message}


def error(code: str, path: str, message: str) -> dict[str, str]:
    assert code.split(".", 1)[0] in {"schema", "reference", "hash", "status"}
    return diagnostic("ERROR", code, path, message)


def warning(code: str, path: str, message: str) -> dict[str, str]:
    return diagnostic("WARNING", code, path, message)


def sha256_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            size += len(chunk)
            digest.update(chunk)
    return digest.hexdigest(), size


def plain_file_issue(path: Path) -> str | None:
    """Return why a bundle artifact is not a direct regular file."""

    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        return "does not exist"
    except OSError as exc:
        return f"cannot inspect file type: {exc.__class__.__name__}"
    if stat.S_ISLNK(mode):
        return "symbolic links are not accepted for bundle artifacts"
    if not stat.S_ISREG(mode):
        return "bundle artifact must be a regular file"
    return None


def read_bounded_text(path: Path, *, encoding: str, max_bytes: int) -> str:
    issue = plain_file_issue(path)
    if issue is not None:
        raise ValueError(issue)
    with path.open("rb") as handle:
        data = handle.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ValueError(f"file exceeds the {max_bytes}-byte validation limit")
    return data.decode(encoding)


def validate_bundle_entry_types(bundle_root: Path) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    try:
        entries = list(bundle_root.iterdir())
    except OSError as exc:
        return [
            error(
                "hash.bundle_read",
                str(bundle_root),
                f"cannot inspect bundle entries: {exc.__class__.__name__}",
            )
        ]
    for entry in entries:
        issue = plain_file_issue(entry)
        if issue is not None:
            messages.append(error("hash.bundle_entry_type", str(entry), issue))
    return messages


def walk(node: Any, path: str = "$") -> Iterator[tuple[str, Any]]:
    yield path, node
    if isinstance(node, dict):
        for key, value in node.items():
            yield from walk(value, f"{path}.{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from walk(value, f"{path}[{index}]")


def at(document: Any, dotted: str) -> Any:
    current = document
    for part in dotted.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def evidence_value(document: Any, dotted: str) -> Any:
    item = at(document, dotted)
    return item.get("value") if isinstance(item, dict) else None


def validate_schema(document: Any) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    if not isinstance(document, dict):
        return [error("schema.root", "$", "root must be a JSON object")]
    schema = document.get("schema")
    expected = {"name": SCHEMA_NAME, "version": SCHEMA_VERSION}
    if schema != expected:
        messages.append(error("schema.version", "$.schema", f"expected {expected!r}"))
    required_sections = (
        "metadata",
        "scope",
        "budget",
        "container",
        "gpu",
        "host",
        "software",
        "project",
        "device_selection_environment",
        "change_control",
        "references",
        "warnings",
    )
    for section in required_sections:
        if section not in document:
            messages.append(error("schema.required", f"$.{section}", "required section is missing"))
    if "references" in document and not isinstance(document["references"], list):
        messages.append(error("schema.type", "$.references", "must be an array"))
    if "warnings" in document and not isinstance(document["warnings"], list):
        messages.append(error("schema.type", "$.warnings", "must be an array"))
    return messages


def validate_references(document: dict[str, Any]) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    declared: dict[str, dict[str, Any]] = {}
    references = document.get("references", [])
    if not isinstance(references, list):
        return messages
    for index, item in enumerate(references):
        path = f"$.references[{index}]"
        if not isinstance(item, dict):
            messages.append(error("reference.type", path, "reference must be an object"))
            continue
        identifier = item.get("id")
        if not isinstance(identifier, str) or not identifier:
            messages.append(error("reference.id", f"{path}.id", "reference id must be a non-empty string"))
            continue
        if identifier in declared:
            messages.append(error("reference.duplicate", f"{path}.id", f"duplicate reference id {identifier!r}"))
        declared[identifier] = item
        expected = REFERENCE_CATALOG.get(identifier)
        if expected is None:
            messages.append(error("reference.unknown", path, f"unknown reference id {identifier!r}"))
        elif item.get("title") != expected["title"] or item.get("url") != expected["url"]:
            messages.append(error("reference.catalog", path, "title or URL differs from the contract catalog"))
    for identifier in REFERENCE_CATALOG:
        if identifier not in declared:
            messages.append(error("reference.missing", "$.references", f"required reference {identifier!r} is absent"))
    for path, node in walk(document):
        if isinstance(node, dict) and "source_ref" in node:
            source_ref = node["source_ref"]
            if source_ref not in declared:
                messages.append(
                    error("reference.unresolved", f"{path}.source_ref", f"unresolved source_ref {source_ref!r}")
                )
    return messages


def validate_evidence_statuses(document: dict[str, Any]) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    evidence_count = 0
    for path, node in walk(document):
        if not isinstance(node, dict):
            continue
        if node.get("evidence") is not True:
            if "status" in node and "value" in node:
                messages.append(error("status.marker", path, "status/value record lacks evidence: true"))
            continue
        evidence_count += 1
        status = node.get("status")
        if status not in ALLOWED_EVIDENCE_STATUSES:
            messages.append(error("status.enum", f"{path}.status", f"unsupported evidence status {status!r}"))
            continue
        if "value" not in node:
            messages.append(error("status.value", path, "evidence record must contain value"))
            continue
        value = node.get("value")
        if status in {"observed", "reported"}:
            if value is None:
                messages.append(error("status.value", f"{path}.value", f"{status} evidence cannot be null"))
            if not isinstance(node.get("source"), str) or not node.get("source"):
                messages.append(error("status.source", f"{path}.source", f"{status} evidence needs a source"))
            if "reason" in node:
                messages.append(error("status.reason", f"{path}.reason", f"{status} evidence cannot carry a reason"))
        elif status == "unavailable":
            if value is not None:
                messages.append(error("status.value", f"{path}.value", "unavailable evidence must be null"))
            if not isinstance(node.get("reason"), str) or not node.get("reason"):
                messages.append(error("status.reason", f"{path}.reason", "unavailable evidence needs a reason"))
            if "source" in node:
                messages.append(error("status.source", f"{path}.source", "unavailable evidence cannot carry a source"))
    if evidence_count == 0:
        messages.append(error("status.missing", "$", "document contains no evidence records"))
    return messages


def validate_backend_consistency(document: dict[str, Any]) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    nvidia_status = evidence_value(document, "gpu.nvidia.target_probe_status")
    nvidia_available = evidence_value(document, "gpu.nvidia.command_availability.nvidia-smi")
    nvidia_nodes = evidence_value(document, "gpu.nvidia.device_nodes")
    nvidia_devices = evidence_value(document, "gpu.nvidia.devices")
    nvidia_count = evidence_value(document, "gpu.nvidia.visible_device_count")
    if nvidia_status not in {"tested", "probe-failed", "capability-detected-tool-unavailable", "not-detected"}:
        messages.append(error("status.backend", "$.gpu.nvidia.target_probe_status", "invalid NVIDIA target status"))
    if nvidia_status == "not-detected" and (nvidia_available is not False or bool(nvidia_nodes)):
        messages.append(error("status.backend", "$.gpu.nvidia", "not-detected conflicts with command availability"))
    if nvidia_status in {"tested", "probe-failed"} and nvidia_available is not True:
        messages.append(error("status.backend", "$.gpu.nvidia", "probe status conflicts with command availability"))
    if nvidia_status == "capability-detected-tool-unavailable" and (
        nvidia_available is not False or not nvidia_nodes
    ):
        messages.append(error("status.backend", "$.gpu.nvidia", "device-node capability status is inconsistent"))
    if isinstance(nvidia_devices, list) and isinstance(nvidia_count, int) and len(nvidia_devices) != nvidia_count:
        messages.append(error("status.count", "$.gpu.nvidia.visible_device_count", "count differs from device list"))
    nvidia_impl = evidence_value(document, "gpu.nvidia.implementation_tested_status")
    if nvidia_impl != "executable-baseline-fixture-tested":
        messages.append(error("status.backend", "$.gpu.nvidia.implementation_tested_status", "unexpected test boundary"))

    amd_status = evidence_value(document, "gpu.amd_rocm.target_probe_status")
    amd_available_values = [
        evidence_value(document, f"gpu.amd_rocm.command_availability.{name}")
        for name in ("amd-smi", "rocm-smi", "rocminfo")
    ]
    amd_nodes = evidence_value(document, "gpu.amd_rocm.device_nodes.dev_kfd")
    amdgpu_module = evidence_value(document, "gpu.amd_rocm.device_nodes.amdgpu_kernel_module")
    if amd_status not in {"capability-detected-unverified", "not-detected"}:
        messages.append(error("status.backend", "$.gpu.amd_rocm.target_probe_status", "invalid AMD/ROCm target status"))
    amd_detected = any(value is True for value in amd_available_values) or amd_nodes is True or amdgpu_module is True
    if amd_status == "not-detected" and amd_detected:
        messages.append(error("status.backend", "$.gpu.amd_rocm", "not-detected conflicts with capability evidence"))
    if amd_status == "capability-detected-unverified" and not amd_detected:
        messages.append(error("status.backend", "$.gpu.amd_rocm", "capability status lacks capability evidence"))
    amd_impl = evidence_value(document, "gpu.amd_rocm.implementation_tested_status")
    if amd_impl != "capability-path-fixture-tested; real-hardware-unverified":
        messages.append(error("status.backend", "$.gpu.amd_rocm.implementation_tested_status", "unexpected test boundary"))

    nvidia_count_item = at(document, "gpu.nvidia.visible_device_count")
    amd_count_item = at(document, "gpu.amd_rocm.visible_device_count")
    global_count_item = at(document, "gpu.visible_device_count")
    if all(
        isinstance(item, dict) and item.get("status") == "observed"
        for item in (nvidia_count_item, amd_count_item, global_count_item)
    ):
        if global_count_item["value"] != nvidia_count_item["value"] + amd_count_item["value"]:
            messages.append(error("status.count", "$.gpu.visible_device_count", "global count differs from backend counts"))

    collection_mode = evidence_value(document, "metadata.collection_mode")
    fixture_name = at(document, "metadata.fixture_name")
    if collection_mode == "fixture" and (
        not isinstance(fixture_name, dict) or fixture_name.get("status") != "observed"
    ):
        messages.append(error("status.fixture", "$.metadata.fixture_name", "fixture mode needs an observed fixture name"))
    if collection_mode == "live" and isinstance(fixture_name, dict) and fixture_name.get("status") != "unavailable":
        messages.append(error("status.fixture", "$.metadata.fixture_name", "live mode cannot claim a fixture name"))
    if collection_mode not in {"fixture", "live"}:
        messages.append(error("status.collection_mode", "$.metadata.collection_mode", "invalid collection mode"))

    if evidence_value(document, "scope.read_only") is not True:
        messages.append(error("status.read_only", "$.scope.read_only", "collector must attest read-only operation"))
    if evidence_value(document, "change_control.actions_performed") != []:
        messages.append(error("status.change_control", "$.change_control.actions_performed", "collector cannot perform changes"))
    if evidence_value(document, "device_selection_environment.full_environment_captured") is not False:
        messages.append(error("status.environment", "$.device_selection_environment", "full environment capture is forbidden"))
    return messages


def validate_hashes(attestation_path: Path, manifest_path: Path | None) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    if manifest_path is None:
        manifest_path = attestation_path.parent / "manifest.json"
    digest_path = manifest_path.parent / "manifest.sha256"
    attestation_issue = plain_file_issue(attestation_path)
    if attestation_issue is not None:
        code = "hash.attestation_missing" if attestation_issue == "does not exist" else "hash.attestation_type"
        return [error(code, str(attestation_path), attestation_issue)]
    manifest_issue = plain_file_issue(manifest_path)
    if manifest_issue is not None:
        code = "hash.manifest_missing" if manifest_issue == "does not exist" else "hash.manifest_type"
        return [error(code, str(manifest_path), manifest_issue)]
    digest_issue = plain_file_issue(digest_path)
    if digest_issue is not None:
        code = "hash.digest_missing" if digest_issue == "does not exist" else "hash.digest_type"
        messages.append(error(code, str(digest_path), digest_issue))
    try:
        manifest = json.loads(
            read_bounded_text(manifest_path, encoding="utf-8", max_bytes=MAX_MANIFEST_BYTES)
        )
    except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
        return messages + [error("hash.manifest_invalid", str(manifest_path), f"cannot read manifest: {exc}")]
    expected_schema = {"name": MANIFEST_SCHEMA_NAME, "version": MANIFEST_SCHEMA_VERSION}
    if manifest.get("schema") != expected_schema:
        messages.append(error("hash.manifest_schema", "$.manifest.schema", f"expected {expected_schema!r}"))
    if manifest.get("attestation_schema") != {"name": SCHEMA_NAME, "version": SCHEMA_VERSION}:
        messages.append(error("hash.attestation_schema", "$.manifest.attestation_schema", "schema reference differs"))
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or len(artifacts) != 1 or not isinstance(artifacts[0], dict):
        messages.append(error("hash.artifacts", "$.manifest.artifacts", "exactly one artifact record is required"))
    else:
        artifact = artifacts[0]
        if artifact.get("path") != "attestation.json":
            messages.append(error("hash.path", "$.manifest.artifacts[0].path", "must be attestation.json"))
        try:
            actual_hash, actual_size = sha256_file(attestation_path)
            if artifact.get("sha256") != actual_hash:
                messages.append(error("hash.attestation", str(attestation_path), "SHA-256 differs from manifest"))
            if artifact.get("bytes") != actual_size:
                messages.append(error("hash.bytes", str(attestation_path), "byte length differs from manifest"))
        except OSError as exc:
            messages.append(error("hash.attestation_missing", str(attestation_path), f"cannot hash attestation: {exc}"))
    if digest_issue is None:
        try:
            digest_line = read_bounded_text(
                digest_path, encoding="ascii", max_bytes=MAX_DIGEST_BYTES
            ).strip()
            match = re.fullmatch(r"([0-9a-f]{64})  manifest\.json", digest_line)
            manifest_hash, _ = sha256_file(manifest_path)
            if not match or match.group(1) != manifest_hash:
                messages.append(error("hash.manifest", str(digest_path), "manifest digest is malformed or incorrect"))
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            messages.append(error("hash.manifest", str(digest_path), f"cannot verify manifest digest: {exc}"))
    return messages


def telemetry_warnings(document: dict[str, Any]) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    summary = evidence_value(document, "gpu.summary")
    if summary == "no-visible-gpu-detected":
        messages.append(warning("hardware.no_gpu", "$.gpu", "no visible GPU was detected; attestation remains valid"))
    nvidia_devices = evidence_value(document, "gpu.nvidia.devices")
    telemetry_fields = (
        "memory_total_mib",
        "memory_used_mib",
        "gpu_utilization_percent",
        "temperature_c",
        "power_draw_w",
        "power_limit_w",
        "graphics_clock_mhz",
        "ecc_corrected_volatile_total",
        "ecc_uncorrected_volatile_total",
        "mig_mode",
    )
    if isinstance(nvidia_devices, list):
        for index, device in enumerate(nvidia_devices):
            if not isinstance(device, dict):
                continue
            missing = [
                field
                for field in telemetry_fields
                if isinstance(device.get(field), dict) and device[field].get("status") == "unavailable"
            ]
            if missing:
                messages.append(
                    warning(
                        "telemetry.nvidia_missing",
                        f"$.gpu.nvidia.devices.value[{index}]",
                        "missing: " + ", ".join(missing),
                    )
                )
    for field in ("topology_matrix", "nvlink_status", "mig_instances"):
        item = at(document, f"gpu.nvidia.{field}")
        if evidence_value(document, "gpu.nvidia.target_probe_status") == "tested" and isinstance(item, dict) and item.get("status") == "unavailable":
            messages.append(warning("telemetry.nvidia_missing", f"$.gpu.nvidia.{field}", "optional NVIDIA telemetry unavailable"))
    amd_status = evidence_value(document, "gpu.amd_rocm.target_probe_status")
    if amd_status == "capability-detected-unverified":
        messages.append(
            warning(
                "backend.amd_unverified",
                "$.gpu.amd_rocm",
                "AMD/ROCm capability is present, but this skill does not claim real-hardware backend validation",
            )
        )
        for field in ("device_listing", "static_properties", "telemetry", "rocminfo_agents"):
            item = at(document, f"gpu.amd_rocm.{field}")
            if isinstance(item, dict) and item.get("status") == "unavailable":
                messages.append(warning("telemetry.amd_missing", f"$.gpu.amd_rocm.{field}", "AMD capability data unavailable"))
    host_paths = (
        "host.cpu.logical_cpu_count",
        "host.cpu.numa_node_count",
        "host.memory.total_bytes",
        "host.storage.total_bytes",
    )
    for path in host_paths:
        item = at(document, path)
        if isinstance(item, dict) and item.get("status") == "unavailable":
            messages.append(warning("telemetry.host_missing", f"$.{path}", "host capacity telemetry unavailable"))
    return messages


def validate_document(
    document: Any, attestation_path: Path, manifest_path: Path | None = None
) -> list[dict[str, str]]:
    messages = validate_schema(document)
    if isinstance(document, dict):
        messages.extend(validate_references(document))
        messages.extend(validate_evidence_statuses(document))
        messages.extend(validate_backend_consistency(document))
        messages.extend(telemetry_warnings(document))
    messages.extend(validate_hashes(attestation_path, manifest_path))
    return messages


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, help="bundle directory or attestation.json")
    parser.add_argument("--manifest", type=Path, help="manifest path; defaults to sibling manifest.json")
    parser.add_argument("--json", action="store_true", help="emit diagnostics as JSON")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.path.is_symlink():
        attestation_path = args.path
        messages = [
            error("schema.input", str(args.path), "bundle path cannot be a symbolic link")
        ]
    else:
        bundle_messages = validate_bundle_entry_types(args.path) if args.path.is_dir() else []
        attestation_path = args.path / "attestation.json" if args.path.is_dir() else args.path
        try:
            document = json.loads(
                read_bounded_text(
                    attestation_path,
                    encoding="utf-8",
                    max_bytes=MAX_ATTESTATION_BYTES,
                )
            )
        except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
            messages = bundle_messages + [
                error("schema.input", str(attestation_path), f"cannot read JSON: {exc}")
            ]
        else:
            messages = bundle_messages + validate_document(document, attestation_path, args.manifest)
    if args.json:
        print(json.dumps(messages, indent=2, sort_keys=True))
    else:
        for item in messages:
            print(f"[{item['severity']}] {item['code']} {item['path']}: {item['message']}")
        errors = sum(item["severity"] == "ERROR" for item in messages)
        warnings = sum(item["severity"] == "WARNING" for item in messages)
        print(f"validation: {errors} error(s), {warnings} warning(s)")
    return 1 if any(item["severity"] == "ERROR" for item in messages) else 0


if __name__ == "__main__":
    raise SystemExit(main())
