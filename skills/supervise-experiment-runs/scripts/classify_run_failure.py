#!/usr/bin/env python3
"""Classify structured run evidence without inferring scientific meaning."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


PRIORITY = (
    "GPU_DEVICE_ERROR",
    "ECC_UNCORRECTABLE",
    "OUT_OF_MEMORY",
    "DISK_EXHAUSTED",
    "THERMAL_THROTTLING",
    "POWER_THROTTLING",
    "PROGRESS_STALL",
    "PROCESS_EXIT",
    "VALIDATION_FAILURE",
    "TRANSPORT_UNOBSERVABLE",
)


def classify(value: Any) -> tuple[dict[str, Any] | None, list[str]]:
    errors: list[str] = []
    if not isinstance(value, dict):
        return None, ["root must be an object"]
    if value.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    transport = value.get("transport_observable")
    if not isinstance(transport, bool):
        errors.append("transport_observable must be boolean")
    telemetry = value.get("telemetry", {})
    disk = value.get("disk", {})
    if not isinstance(telemetry, dict):
        errors.append("telemetry must be an object")
        telemetry = {}
    if not isinstance(disk, dict):
        errors.append("disk must be an object")
        disk = {}
    if errors:
        return None, errors

    observed: dict[str, list[str]] = {}

    def add(code: str, evidence: str) -> None:
        observed.setdefault(code, []).append(evidence)

    if telemetry.get("device_error") is True or telemetry.get("xid_codes") or telemetry.get("ras_errors"):
        add("GPU_DEVICE_ERROR", "telemetry.device_error_or_code")
    ecc_delta = telemetry.get("ecc_uncorrectable_delta")
    if isinstance(ecc_delta, (int, float)) and not isinstance(ecc_delta, bool) and ecc_delta > 0:
        add("ECC_UNCORRECTABLE", "telemetry.ecc_uncorrectable_delta")
    if telemetry.get("oom") is True or value.get("oom") is True:
        add("OUT_OF_MEMORY", "oom")
    if disk.get("write_error") is True:
        add("DISK_EXHAUSTED", "disk.write_error")
    free_bytes = disk.get("free_bytes")
    required_bytes = disk.get("required_bytes")
    if all(isinstance(item, int) and not isinstance(item, bool) and item >= 0 for item in (free_bytes, required_bytes)) and free_bytes < required_bytes:
        add("DISK_EXHAUSTED", "disk.free_bytes_below_required")
    if telemetry.get("thermal_throttle") is True:
        add("THERMAL_THROTTLING", "telemetry.thermal_throttle")
    if telemetry.get("power_throttle") is True:
        add("POWER_THROTTLING", "telemetry.power_throttle")
    if value.get("progress_stalled") is True or value.get("runner_state") == "STALLED":
        add("PROGRESS_STALL", "progress_or_runner_state")
    exit_code = value.get("process_exit_code")
    if isinstance(exit_code, int) and not isinstance(exit_code, bool) and exit_code != 0:
        add("PROCESS_EXIT", "process_exit_code")
    validation_exit = value.get("completion_validation_exit_code")
    if isinstance(validation_exit, int) and not isinstance(validation_exit, bool) and validation_exit != 0:
        add("VALIDATION_FAILURE", "completion_validation_exit_code")
    if transport is False:
        add("TRANSPORT_UNOBSERVABLE", "transport_observable")

    classes = [
        {"code": code, "evidence_fields": observed[code]}
        for code in PRIORITY
        if code in observed
    ]
    primary = classes[0]["code"] if classes else "UNKNOWN"
    result = {
        "schema_version": 1,
        "artifact_type": "run_failure_classification",
        "runner_state": value.get("runner_state"),
        "transport_observable": transport,
        "primary_class": primary,
        "classes": classes,
        "scientific_interpretation": "not_assessed",
    }
    return result, []


def self_test() -> None:
    oom, errors = classify({"schema_version": 1, "transport_observable": True, "runner_state": "FAILED", "process_exit_code": 1, "telemetry": {"oom": True}, "disk": {}})
    assert errors == [] and oom is not None
    assert oom["primary_class"] == "OUT_OF_MEMORY"
    assert {item["code"] for item in oom["classes"]} == {"OUT_OF_MEMORY", "PROCESS_EXIT"}
    disconnected, errors = classify({"schema_version": 1, "transport_observable": False, "runner_state": "RUNNING", "telemetry": {}, "disk": {}})
    assert errors == [] and disconnected is not None
    assert disconnected["primary_class"] == "TRANSPORT_UNOBSERVABLE"
    throttled, errors = classify({"schema_version": 1, "transport_observable": True, "runner_state": "SUCCEEDED", "telemetry": {"thermal_throttle": True, "power_throttle": True}, "disk": {}})
    assert errors == [] and throttled is not None and len(throttled["classes"]) == 2
    print("self-test: PASS")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence", nargs="?", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.evidence is None:
        parser.error("evidence is required unless --self-test is used")
    try:
        value = json.loads(args.evidence.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        print(f"ERROR: invalid JSON: {exc}")
        return 2
    result, errors = classify(value)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    assert result is not None
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
