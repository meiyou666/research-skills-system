#!/usr/bin/env python3
"""Offline integration tests for inspect-gpu-environment."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any

from inspect_gpu_environment import (
    COMMAND_OUTPUT_LIMIT_RETURN_CODE,
    COMMAND_TIMEOUT_RETURN_CODE,
    MAX_COMMAND_OUTPUT,
    ProbeRunner,
)


HERE = Path(__file__).resolve().parent
SKILL_ROOT = HERE.parent
INSPECTOR = HERE / "inspect_gpu_environment.py"
VALIDATOR = HERE / "validate_attestation.py"
FIXTURES = SKILL_ROOT / "fixtures"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def sha256_file(path: Path) -> tuple[str, int]:
    data = path.read_bytes()
    return hashlib.sha256(data).hexdigest(), len(data)


def run_checked(argv: list[str], *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(argv, capture_output=True, text=True, env=env, check=False)
    if completed.returncode != 0:
        raise AssertionError(
            f"command failed ({completed.returncode}): {' '.join(argv)}\n"
            f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )
    return completed


def run_failed(argv: list[str]) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(argv, capture_output=True, text=True, check=False)
    require(completed.returncode != 0, f"command unexpectedly succeeded: {' '.join(argv)}")
    return completed


def validate(bundle: Path, expected_returncode: int = 0) -> list[dict[str, str]]:
    completed = subprocess.run(
        [sys.executable, str(VALIDATOR), str(bundle), "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    require(completed.returncode == expected_returncode, f"validator return code: {completed.stdout}\n{completed.stderr}")
    return json.loads(completed.stdout)


def generate(temp_root: Path, fixture_name: str, extra: list[str] | None = None) -> tuple[Path, dict[str, Any]]:
    output = temp_root / fixture_name.removesuffix(".json")
    env = dict(os.environ)
    env["INSPECT_GPU_TEST_SECRET"] = "must-not-appear-in-attestation"
    argv = [
        sys.executable,
        str(INSPECTOR),
        "--fixture",
        str(FIXTURES / fixture_name),
        "--output-dir",
        str(output),
    ]
    if extra:
        argv.extend(extra)
    run_checked(argv, env=env)
    require(not list(temp_root.glob(".gpu-attestation-stage-*")), "collector left a staging directory")
    document_text = (output / "attestation.json").read_text(encoding="utf-8")
    require("INSPECT_GPU_TEST_SECRET" not in document_text, "non-allowlisted environment name leaked")
    require("must-not-appear-in-attestation" not in document_text, "non-allowlisted environment value leaked")
    document = json.loads(document_text)
    diagnostics = validate(output)
    require(not [item for item in diagnostics if item["severity"] == "ERROR"], "valid fixture produced errors")
    return output, document


def refresh_hashes(bundle: Path) -> None:
    attestation_hash, attestation_bytes = sha256_file(bundle / "attestation.json")
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifacts"][0]["sha256"] = attestation_hash
    manifest["artifacts"][0]["bytes"] = attestation_bytes
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest_hash, _ = sha256_file(manifest_path)
    (bundle / "manifest.sha256").write_text(f"{manifest_hash}  manifest.json\n", encoding="ascii")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="inspect-gpu-environment-self-test-") as temp_name:
        temp_root = Path(temp_name)

        # Exercise live subprocess capture without depending on host GPU tools.
        runner = ProbeRunner(None, timeout=2.0)
        normal_size = 96 * 1024
        normal = runner.run(
            "bounded-normal",
            [
                sys.executable,
                "-c",
                (
                    "import os; "
                    f"os.write(1, b'o' * {normal_size}); "
                    f"os.write(2, b'e' * {normal_size})"
                ),
            ],
        )
        require(normal.ok, f"bounded normal command failed: {normal.failure_reason}")
        require(len(normal.stdout) == normal_size, "bounded stdout length mismatch")
        require(len(normal.stderr) == normal_size, "bounded stderr length mismatch")

        for stream_fd, stream_name in ((1, "stdout"), (2, "stderr")):
            oversized = runner.run(
                f"oversized-{stream_name}",
                [
                    sys.executable,
                    "-c",
                    f"import os; os.write({stream_fd}, b'x' * {MAX_COMMAND_OUTPUT + 1})",
                ],
            )
            require(
                oversized.returncode == COMMAND_OUTPUT_LIMIT_RETURN_CODE,
                f"{stream_name} overflow did not fail with the limit code",
            )
            require(not oversized.ok and oversized.stdout == "", "overflow exposed partial stdout")
            require(
                oversized.failure_reason is not None and stream_name in oversized.failure_reason,
                f"{stream_name} overflow reason missing",
            )

        descendant_marker = temp_root / "timed-out-descendant-marker"
        descendant_started = temp_root / "timed-out-descendant-started"
        grandchild_code = (
            "import pathlib,sys,time; time.sleep(1.2); "
            "pathlib.Path(sys.argv[1]).write_text('escaped', encoding='utf-8')"
        )
        parent_code = (
            "import pathlib,subprocess,sys,time; "
            "child=subprocess.Popen([sys.executable, '-c', sys.argv[1], sys.argv[2]]); "
            "pathlib.Path(sys.argv[3]).write_text(str(child.pid), encoding='ascii'); "
            "time.sleep(10)"
        )
        timeout_runner = ProbeRunner(None, timeout=0.4)
        timed_out = timeout_runner.run(
            "timeout-process-group",
            [
                sys.executable,
                "-c",
                parent_code,
                grandchild_code,
                str(descendant_marker),
                str(descendant_started),
            ],
        )
        require(descendant_started.is_file(), "timeout fixture did not start its descendant")
        require(timed_out.returncode == COMMAND_TIMEOUT_RETURN_CODE, "timeout code mismatch")
        require(not timed_out.ok and timed_out.stdout == "", "timeout exposed partial stdout")
        time.sleep(1.3)
        require(not descendant_marker.exists(), "timed-out descendant survived its process group")

        bounded_file = temp_root / "bounded-file.txt"
        bounded_file.write_bytes(b"a" * 32)
        require(runner.read_text(str(bounded_file), max_bytes=32) == "a" * 32, "bounded file read failed")
        bounded_file.write_bytes(b"a" * 33)
        require(runner.read_text(str(bounded_file), max_bytes=32) is None, "oversized file was truncated")

        no_gpu_bundle, no_gpu = generate(temp_root, "no-gpu.json")
        require(no_gpu["metadata"]["document_status"]["value"] == "draft", "short path must create a draft")
        require(no_gpu["gpu"]["summary"]["value"] == "no-visible-gpu-detected", "no-GPU summary mismatch")
        require(no_gpu["gpu"]["visible_device_count"]["value"] == 0, "no-GPU count mismatch")
        no_gpu_diagnostics = validate(no_gpu_bundle)
        require(any(item["code"] == "hardware.no_gpu" for item in no_gpu_diagnostics), "no-GPU warning missing")

        # Simulate ``ssh target 'python3 - ...' < inspect_gpu_environment.py``.
        streamed_bundle = temp_root / "streamed-no-gpu"
        streamed = subprocess.run(
            [
                sys.executable,
                "-",
                "--fixture",
                str(FIXTURES / "no-gpu.json"),
                "--output-dir",
                str(streamed_bundle),
            ],
            input=INSPECTOR.read_text(encoding="utf-8"),
            capture_output=True,
            text=True,
            check=False,
        )
        require(streamed.returncode == 0, f"streamed collector failed: {streamed.stderr}")
        validate(streamed_bundle)

        dangling_output = temp_root / "dangling-output"
        dangling_target = temp_root / "absent-output-target"
        dangling_output.symlink_to(dangling_target, target_is_directory=True)
        run_failed(
            [
                sys.executable,
                str(INSPECTOR),
                "--fixture",
                str(FIXTURES / "no-gpu.json"),
                "--output-dir",
                str(dangling_output),
            ]
        )
        require(dangling_output.is_symlink(), "collector replaced an existing output symlink")

        fifo_output = temp_root / "fifo-output"
        os.mkfifo(fifo_output)
        run_failed(
            [
                sys.executable,
                str(INSPECTOR),
                "--fixture",
                str(FIXTURES / "no-gpu.json"),
                "--output-dir",
                str(fifo_output),
            ]
        )
        require(not list(temp_root.glob(".gpu-attestation-stage-*")), "failed outputs left staging data")

        budget_args = [
            "--gpu-count", "2", "--cpu-count", "64", "--duration-hours", "2", "--disk-gb", "500",
            "--hourly-cost-cap", "3.5", "--total-cost-cap", "8", "--currency", "USD",
            "--image-digest", "sha256:" + "a" * 64,
        ]
        nvidia_bundle, nvidia = generate(temp_root, "nvidia-2gpu.json", budget_args)
        devices = nvidia["gpu"]["nvidia"]["devices"]["value"]
        require(len(devices) == 2, "NVIDIA fixture did not produce two devices")
        require(devices[0]["model"]["value"] == "NVIDIA A100-SXM4-80GB", "NVIDIA model parse failed")
        require(devices[1]["mig_mode"]["value"] == "Enabled", "MIG mode parse failed")
        require(devices[0]["pcie"]["link_width_current"]["value"] == 16, "PCIe parse failed")
        require(nvidia["budget"]["hourly_cap_times_duration"]["value"] == 7.0, "budget derivation failed")
        require(nvidia["budget"]["within_total_cost_cap"]["value"] is True, "budget cap comparison failed")
        env_values = nvidia["device_selection_environment"]["selected_values"]
        require(set(env_values) == {
            "CUDA_VISIBLE_DEVICES", "NVIDIA_VISIBLE_DEVICES", "NVIDIA_DRIVER_CAPABILITIES",
            "ROCR_VISIBLE_DEVICES", "HIP_VISIBLE_DEVICES", "GPU_DEVICE_ORDINAL", "ZE_AFFINITY_MASK",
        }, "environment allowlist changed unexpectedly")

        missing_bundle, missing = generate(temp_root, "nvidia-missing-telemetry.json")
        require(
            missing["gpu"]["nvidia"]["devices"]["value"][0]["temperature_c"]["status"] == "unavailable",
            "missing telemetry was not marked unavailable",
        )
        missing_diagnostics = validate(missing_bundle)
        require(
            any(item["code"] == "telemetry.nvidia_missing" for item in missing_diagnostics),
            "missing telemetry must produce a warning",
        )

        amd_bundle, amd = generate(temp_root, "amd-capability.json")
        require(
            amd["gpu"]["amd_rocm"]["target_probe_status"]["value"] == "capability-detected-unverified",
            "AMD capability boundary mismatch",
        )
        require(amd["gpu"]["amd_rocm"]["visible_device_count"]["value"] == 2, "AMD device count parse failed")
        require(
            "real-hardware-unverified" in amd["gpu"]["amd_rocm"]["implementation_tested_status"]["value"],
            "AMD implementation boundary missing",
        )
        amd_diagnostics = validate(amd_bundle)
        require(any(item["code"] == "backend.amd_unverified" for item in amd_diagnostics), "AMD warning missing")

        symlink_bundle = temp_root / "symlink-artifact-bundle"
        shutil.copytree(no_gpu_bundle, symlink_bundle)
        outside_attestation = temp_root / "outside-attestation.json"
        shutil.copyfile(symlink_bundle / "attestation.json", outside_attestation)
        (symlink_bundle / "attestation.json").unlink()
        (symlink_bundle / "attestation.json").symlink_to(outside_attestation)
        symlink_diagnostics = validate(symlink_bundle, expected_returncode=1)
        require(
            any(item["code"] == "schema.input" for item in symlink_diagnostics),
            "validator accepted a symlinked attestation",
        )

        manifest_symlink_bundle = temp_root / "symlink-manifest-bundle"
        shutil.copytree(no_gpu_bundle, manifest_symlink_bundle)
        outside_manifest = temp_root / "outside-manifest.json"
        shutil.copyfile(manifest_symlink_bundle / "manifest.json", outside_manifest)
        (manifest_symlink_bundle / "manifest.json").unlink()
        (manifest_symlink_bundle / "manifest.json").symlink_to(outside_manifest)
        manifest_symlink_diagnostics = validate(manifest_symlink_bundle, expected_returncode=1)
        require(
            any(item["code"] == "hash.manifest_type" for item in manifest_symlink_diagnostics),
            "validator accepted a symlinked manifest",
        )

        special_manifest_bundle = temp_root / "special-manifest-bundle"
        shutil.copytree(no_gpu_bundle, special_manifest_bundle)
        (special_manifest_bundle / "manifest.json").unlink()
        os.mkfifo(special_manifest_bundle / "manifest.json")
        special_manifest_diagnostics = validate(special_manifest_bundle, expected_returncode=1)
        require(
            any(item["code"] == "hash.manifest_type" for item in special_manifest_diagnostics),
            "validator accepted a special-file manifest",
        )

        root_symlink = temp_root / "symlink-bundle-root"
        root_symlink.symlink_to(no_gpu_bundle, target_is_directory=True)
        root_symlink_diagnostics = validate(root_symlink, expected_returncode=1)
        require(
            any(item["code"] == "schema.input" for item in root_symlink_diagnostics),
            "validator accepted a symlinked bundle root",
        )

        extra_symlink_bundle = temp_root / "extra-symlink-bundle"
        shutil.copytree(no_gpu_bundle, extra_symlink_bundle)
        (extra_symlink_bundle / "unexpected-link").symlink_to(outside_attestation)
        extra_symlink_diagnostics = validate(extra_symlink_bundle, expected_returncode=1)
        require(
            any(item["code"] == "hash.bundle_entry_type" for item in extra_symlink_diagnostics),
            "validator accepted an extra symlink inside the bundle",
        )

        # A byte-level edit must fail hash validation.
        attestation_path = nvidia_bundle / "attestation.json"
        attestation_path.write_text(attestation_path.read_text(encoding="utf-8") + " ", encoding="utf-8")
        hash_diagnostics = validate(nvidia_bundle, expected_returncode=1)
        require(any(item["code"] == "hash.attestation" for item in hash_diagnostics), "tamper was not detected")

        # Refresh hashes so this mutation isolates status-consistency validation.
        mutated = json.loads(attestation_path.read_text(encoding="utf-8"))
        mutated["scope"]["read_only"]["value"] = False
        attestation_path.write_text(json.dumps(mutated, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        refresh_hashes(nvidia_bundle)
        status_diagnostics = validate(nvidia_bundle, expected_returncode=1)
        require(any(item["code"] == "status.read_only" for item in status_diagnostics), "status inconsistency not detected")

    print(
        "self-test: bounded subprocess/file capture, timeout cleanup, output-path guards, "
        "4 fixtures, streamed execution, symlink rejection, and hash/status tamper checks passed"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
