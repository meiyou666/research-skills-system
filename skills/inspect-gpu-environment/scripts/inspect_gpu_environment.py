#!/usr/bin/env python3
"""Create a read-only Linux GPU environment attestation.

The script has no third-party dependencies.  Run it on the target host, including
inside a container, or stream it to ``python3 -`` over SSH.  Command fixtures make
the probe deterministic and offline-testable without pretending that a fixture is
real hardware validation.
"""

from __future__ import annotations

import argparse
import csv
import glob as glob_module
import hashlib
import importlib.metadata
import io
import json
import os
from pathlib import Path
import platform
import re
import selectors
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Iterable
import uuid


SCHEMA_NAME = "gpu-environment-attestation"
SCHEMA_VERSION = "1.0.0"
MANIFEST_SCHEMA_NAME = "gpu-environment-attestation-manifest"
MANIFEST_SCHEMA_VERSION = "1.0.0"
FIXTURE_SCHEMA = "gpu-environment-command-fixture/1.0"
MAX_COMMAND_OUTPUT = 128 * 1024
COMMAND_TIMEOUT_RETURN_CODE = 124
COMMAND_OUTPUT_LIMIT_RETURN_CODE = 125
COMMAND_START_ERROR_RETURN_CODE = 126
COMMAND_NOT_FOUND_RETURN_CODE = 127
COMMAND_READ_CHUNK = 16 * 1024
COMMAND_TERMINATION_GRACE_SECONDS = 0.25

REFERENCE_CATALOG: dict[str, dict[str, str]] = {
    "nvidia-smi": {
        "title": "NVIDIA System Management Interface documentation",
        "url": "https://docs.nvidia.com/deploy/nvidia-smi/index.html",
    },
    "nvidia-mig": {
        "title": "NVIDIA Multi-Instance GPU User Guide",
        "url": "https://docs.nvidia.com/datacenter/tesla/mig-user-guide/getting-started-with-mig.html",
    },
    "amd-smi": {
        "title": "AMD SMI CLI tool usage",
        "url": "https://rocm.docs.amd.com/projects/amdsmi/en/latest/how-to/amdsmi-cli-tool.html",
    },
    "rocminfo": {
        "title": "AMD rocminfo documentation",
        "url": "https://rocm.docs.amd.com/projects/rocminfo/en/latest/",
    },
    "oci-image-descriptor": {
        "title": "Open Container Initiative image descriptor specification",
        "url": "https://specs.opencontainers.org/image-spec/descriptor/",
    },
}

ENV_ALLOWLIST = (
    "CUDA_VISIBLE_DEVICES",
    "NVIDIA_VISIBLE_DEVICES",
    "NVIDIA_DRIVER_CAPABILITIES",
    "ROCR_VISIBLE_DEVICES",
    "HIP_VISIBLE_DEVICES",
    "GPU_DEVICE_ORDINAL",
    "ZE_AFFINITY_MASK",
)

NVIDIA_FIELDS = (
    "index",
    "uuid",
    "name",
    "pci.bus_id",
    "driver_version",
    "memory.total",
    "memory.used",
    "memory.free",
    "utilization.gpu",
    "utilization.memory",
    "temperature.gpu",
    "power.draw",
    "power.limit",
    "clocks.current.graphics",
    "clocks.current.memory",
    "ecc.errors.corrected.volatile.total",
    "ecc.errors.uncorrected.volatile.total",
    "mig.mode.current",
)

NVIDIA_BASIC_FIELDS = NVIDIA_FIELDS[:5]
NVIDIA_PCIE_FIELDS = (
    "index",
    "pcie.link.gen.current",
    "pcie.link.gen.max",
    "pcie.link.width.current",
    "pcie.link.width.max",
)

UNAVAILABLE_TOKENS = {
    "",
    "n/a",
    "na",
    "not supported",
    "[not supported]",
    "not available",
    "unknown error",
}


def evidence(
    status: str,
    value: Any,
    source: str | None = None,
    *,
    reason: str | None = None,
    source_ref: str | None = None,
    unit: str | None = None,
) -> dict[str, Any]:
    item: dict[str, Any] = {"evidence": True, "status": status, "value": value}
    if source is not None:
        item["source"] = source
    if reason is not None:
        item["reason"] = reason
    if source_ref is not None:
        item["source_ref"] = source_ref
    if unit is not None:
        item["unit"] = unit
    return item


def observed(
    value: Any, source: str, *, source_ref: str | None = None, unit: str | None = None
) -> dict[str, Any]:
    return evidence("observed", value, source, source_ref=source_ref, unit=unit)


def reported(
    value: Any, source: str, *, source_ref: str | None = None, unit: str | None = None
) -> dict[str, Any]:
    return evidence("reported", value, source, source_ref=source_ref, unit=unit)


def unavailable(reason: str, *, source_ref: str | None = None, unit: str | None = None) -> dict[str, Any]:
    return evidence("unavailable", None, reason=reason, source_ref=source_ref, unit=unit)


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str
    source: str
    failure_reason: str | None = None

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def close_process_pipes(process: subprocess.Popen[bytes]) -> None:
    """Close local pipe endpoints without waiting on an untrusted child."""

    for pipe in (process.stdout, process.stderr):
        if pipe is not None and not pipe.closed:
            pipe.close()


def terminate_process_group(process: subprocess.Popen[bytes]) -> None:
    """Terminate the probe and descendants created in its dedicated session."""

    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    except OSError:
        try:
            process.terminate()
        except OSError:
            pass

    try:
        process.wait(timeout=COMMAND_TERMINATION_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        pass

    # The direct child may have exited while a descendant retained a pipe or
    # ignored SIGTERM.  Address the original process group before returning.
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    except OSError:
        try:
            process.kill()
        except OSError:
            pass

    try:
        process.wait(timeout=COMMAND_TERMINATION_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        # A kernel-level uninterruptible process can outlive this bounded
        # cleanup attempt.  Never turn that external state into a caller hang.
        pass


def run_bounded_process(argv: list[str], timeout: float, source: str) -> CommandResult:
    """Run one probe with concurrent byte-bounded stdout/stderr collection."""

    try:
        process = subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            start_new_session=True,
            close_fds=True,
        )
    except FileNotFoundError:
        return CommandResult(
            COMMAND_NOT_FOUND_RETURN_CODE,
            "",
            "executable not found",
            source,
            "executable not found",
        )
    except OSError as exc:
        reason = f"command could not start: {exc.__class__.__name__}"
        return CommandResult(COMMAND_START_ERROR_RETURN_CODE, "", reason, source, reason)

    selector = selectors.DefaultSelector()
    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    failure_code: int | None = None
    failure_reason: str | None = None
    deadline = time.monotonic() + timeout
    try:
        assert process.stdout is not None
        assert process.stderr is not None
        selector.register(process.stdout, selectors.EVENT_READ, "stdout")
        selector.register(process.stderr, selectors.EVENT_READ, "stderr")

        while selector.get_map() or process.poll() is None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                failure_code = COMMAND_TIMEOUT_RETURN_CODE
                failure_reason = f"command timed out after {timeout:g} seconds"
                break

            if not selector.get_map():
                time.sleep(min(0.01, remaining))
                continue

            for key, _ in selector.select(timeout=min(0.05, remaining)):
                stream_name = str(key.data)
                buffer = buffers[stream_name]
                read_size = min(COMMAND_READ_CHUNK, MAX_COMMAND_OUTPUT - len(buffer) + 1)
                try:
                    chunk = os.read(key.fd, read_size)
                except BlockingIOError:
                    continue
                except OSError as exc:
                    failure_code = COMMAND_START_ERROR_RETURN_CODE
                    failure_reason = f"command output capture failed: {exc.__class__.__name__}"
                    break
                if not chunk:
                    selector.unregister(key.fileobj)
                    key.fileobj.close()
                    continue
                buffer.extend(chunk)
                if len(buffer) > MAX_COMMAND_OUTPUT:
                    failure_code = COMMAND_OUTPUT_LIMIT_RETURN_CODE
                    failure_reason = (
                        f"command {stream_name} exceeded the {MAX_COMMAND_OUTPUT}-byte limit"
                    )
                    break
            if failure_code is not None:
                break

        if failure_code is None:
            remaining = max(0.0, deadline - time.monotonic())
            try:
                returncode = process.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                failure_code = COMMAND_TIMEOUT_RETURN_CODE
                failure_reason = f"command timed out after {timeout:g} seconds"
            else:
                return CommandResult(
                    returncode,
                    buffers["stdout"].decode("utf-8", errors="replace"),
                    buffers["stderr"].decode("utf-8", errors="replace"),
                    source,
                )
    finally:
        selector.close()
        if failure_code is not None or process.poll() is None:
            close_process_pipes(process)
            terminate_process_group(process)
        else:
            close_process_pipes(process)

    assert failure_code is not None and failure_reason is not None
    return CommandResult(failure_code, "", failure_reason, source, failure_reason)


class ProbeRunner:
    """Run a fixed read-only command set, or replay a command-output fixture."""

    def __init__(self, fixture_path: Path | None, timeout: float) -> None:
        self.timeout = timeout
        self.fixture: dict[str, Any] | None = None
        if fixture_path is not None:
            with fixture_path.open("r", encoding="utf-8") as handle:
                fixture = json.load(handle)
            if fixture.get("fixture_schema") != FIXTURE_SCHEMA:
                raise ValueError(
                    f"fixture_schema must be {FIXTURE_SCHEMA!r}, got {fixture.get('fixture_schema')!r}"
                )
            self.fixture = fixture

    @property
    def fixture_mode(self) -> bool:
        return self.fixture is not None

    def which(self, executable: str) -> str | None:
        if self.fixture is not None:
            value = self.fixture.get("which", {}).get(executable)
            return str(value) if value else None
        return shutil.which(executable)

    def run(self, key: str, argv: list[str]) -> CommandResult:
        source = f"command:{shlex.join(argv)}"
        if self.fixture is not None:
            record = self.fixture.get("commands", {}).get(key)
            if record is None:
                return CommandResult(
                    COMMAND_NOT_FOUND_RETURN_CODE,
                    "",
                    "fixture command not recorded",
                    f"fixture:{key}",
                    "fixture command not recorded",
                )
            stdout_bytes = str(record.get("stdout", "")).encode("utf-8")
            stderr_bytes = str(record.get("stderr", "")).encode("utf-8")
            if len(stdout_bytes) > MAX_COMMAND_OUTPUT:
                reason = f"fixture stdout exceeded the {MAX_COMMAND_OUTPUT}-byte limit"
                return CommandResult(
                    COMMAND_OUTPUT_LIMIT_RETURN_CODE, "", reason, f"fixture:{key}", reason
                )
            if len(stderr_bytes) > MAX_COMMAND_OUTPUT:
                reason = f"fixture stderr exceeded the {MAX_COMMAND_OUTPUT}-byte limit"
                return CommandResult(
                    COMMAND_OUTPUT_LIMIT_RETURN_CODE, "", reason, f"fixture:{key}", reason
                )
            return CommandResult(
                int(record.get("returncode", 0)),
                stdout_bytes.decode("utf-8", errors="replace"),
                stderr_bytes.decode("utf-8", errors="replace"),
                f"fixture:{key}",
            )
        return run_bounded_process(argv, self.timeout, source)

    def read_text(self, path: str, *, max_bytes: int = MAX_COMMAND_OUTPUT) -> str | None:
        if self.fixture is not None:
            value = self.fixture.get("files", {}).get(path)
            if value is None:
                return None
            encoded = str(value).encode("utf-8")
            if len(encoded) > max_bytes:
                return None
            return encoded.decode("utf-8", errors="replace")
        try:
            if max_bytes < 0:
                raise ValueError("max_bytes must be nonnegative")
            with Path(path).open("rb") as handle:
                data = handle.read(max_bytes + 1)
            if len(data) > max_bytes:
                return None
            return data.decode("utf-8", errors="replace")
        except (OSError, ValueError):
            return None

    def path_exists(self, path: str) -> bool:
        if self.fixture is not None:
            return bool(self.fixture.get("paths", {}).get(path, False))
        return Path(path).exists()

    def glob(self, pattern: str) -> list[str]:
        if self.fixture is not None:
            return [str(value) for value in self.fixture.get("globs", {}).get(pattern, [])]
        return sorted(glob_module.glob(pattern))

    def environment_value(self, name: str) -> str | None:
        if self.fixture is not None:
            value = self.fixture.get("environment", {}).get(name)
            return None if value is None else str(value)
        return os.environ.get(name)

    def package_version(self, distribution: str) -> str | None:
        if self.fixture is not None:
            value = self.fixture.get("packages", {}).get(distribution)
            return None if value is None else str(value)
        try:
            return importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            return None


def command_evidence(
    result: CommandResult,
    *,
    source_ref: str | None = None,
    transform: Callable[[str], Any] | None = None,
    empty_reason: str = "command returned no output",
) -> dict[str, Any]:
    if not result.ok:
        reason = result.failure_reason or f"command failed with return code {result.returncode}"
        return unavailable(reason, source_ref=source_ref)
    text = result.stdout.strip()
    if not text:
        return unavailable(empty_reason, source_ref=source_ref)
    try:
        value = transform(text) if transform else text
    except (ValueError, TypeError, json.JSONDecodeError):
        return unavailable("command output could not be parsed", source_ref=source_ref)
    return observed(value, result.source, source_ref=source_ref)


def parse_number(text: str, integer: bool = False) -> int | float:
    stripped = text.strip()
    if integer:
        return int(float(stripped))
    return float(stripped)


def command_field(
    text: str | None,
    source: str,
    *,
    converter: Callable[[str], Any] | None = None,
    source_ref: str | None = None,
    unit: str | None = None,
    missing_reason: str = "telemetry unavailable",
) -> dict[str, Any]:
    if text is None or text.strip().lower() in UNAVAILABLE_TOKENS:
        return unavailable(missing_reason, source_ref=source_ref, unit=unit)
    try:
        value = converter(text) if converter else text.strip()
    except (ValueError, TypeError):
        return unavailable("telemetry value could not be parsed", source_ref=source_ref, unit=unit)
    return observed(value, source, source_ref=source_ref, unit=unit)


def parse_csv_rows(text: str) -> list[list[str]]:
    return [[cell.strip() for cell in row] for row in csv.reader(io.StringIO(text)) if row]


def availability(runner: ProbeRunner, executable: str) -> dict[str, Any]:
    path = runner.which(executable)
    return observed(bool(path), f"path-lookup:{executable}")


def nvidia_device_from_row(row: list[str], source: str, full: bool) -> dict[str, Any]:
    padded = row + [""] * (len(NVIDIA_FIELDS) - len(row))
    missing_reason = "full NVIDIA telemetry query unavailable" if not full else "device returned N/A"
    ref = "nvidia-smi"
    return {
        "index": command_field(padded[0], source, converter=lambda value: parse_number(value, True), source_ref=ref),
        "uuid": command_field(padded[1], source, source_ref=ref),
        "model": command_field(padded[2], source, source_ref=ref),
        "pci_bus_id": command_field(padded[3], source, source_ref=ref),
        "driver_version": command_field(padded[4], source, source_ref=ref),
        "memory_total_mib": command_field(
            padded[5], source, converter=lambda value: parse_number(value, True), source_ref=ref,
            unit="MiB", missing_reason=missing_reason
        ),
        "memory_used_mib": command_field(
            padded[6], source, converter=lambda value: parse_number(value, True), source_ref=ref,
            unit="MiB", missing_reason=missing_reason
        ),
        "memory_free_mib": command_field(
            padded[7], source, converter=lambda value: parse_number(value, True), source_ref=ref,
            unit="MiB", missing_reason=missing_reason
        ),
        "gpu_utilization_percent": command_field(
            padded[8], source, converter=parse_number, source_ref=ref, unit="percent", missing_reason=missing_reason
        ),
        "memory_utilization_percent": command_field(
            padded[9], source, converter=parse_number, source_ref=ref, unit="percent", missing_reason=missing_reason
        ),
        "temperature_c": command_field(
            padded[10], source, converter=parse_number, source_ref=ref, unit="degree Celsius", missing_reason=missing_reason
        ),
        "power_draw_w": command_field(
            padded[11], source, converter=parse_number, source_ref=ref, unit="W", missing_reason=missing_reason
        ),
        "power_limit_w": command_field(
            padded[12], source, converter=parse_number, source_ref=ref, unit="W", missing_reason=missing_reason
        ),
        "graphics_clock_mhz": command_field(
            padded[13], source, converter=lambda value: parse_number(value, True), source_ref=ref,
            unit="MHz", missing_reason=missing_reason
        ),
        "memory_clock_mhz": command_field(
            padded[14], source, converter=lambda value: parse_number(value, True), source_ref=ref,
            unit="MHz", missing_reason=missing_reason
        ),
        "ecc_corrected_volatile_total": command_field(
            padded[15], source, converter=lambda value: parse_number(value, True), source_ref=ref,
            unit="errors", missing_reason=missing_reason
        ),
        "ecc_uncorrected_volatile_total": command_field(
            padded[16], source, converter=lambda value: parse_number(value, True), source_ref=ref,
            unit="errors", missing_reason=missing_reason
        ),
        "mig_mode": command_field(
            padded[17], source, source_ref="nvidia-mig", missing_reason=missing_reason
        ),
        "pcie": {
            "link_generation_current": unavailable("PCIe query unavailable", source_ref=ref),
            "link_generation_max": unavailable("PCIe query unavailable", source_ref=ref),
            "link_width_current": unavailable("PCIe query unavailable", source_ref=ref),
            "link_width_max": unavailable("PCIe query unavailable", source_ref=ref),
        },
    }


def apply_nvidia_pcie(devices: list[dict[str, Any]], result: CommandResult) -> None:
    if not result.ok:
        return
    by_index = {
        device["index"]["value"]: device
        for device in devices
        if device["index"]["status"] == "observed"
    }
    for row in parse_csv_rows(result.stdout):
        if len(row) < len(NVIDIA_PCIE_FIELDS):
            continue
        try:
            index = parse_number(row[0], True)
        except ValueError:
            continue
        device = by_index.get(index)
        if device is None:
            continue
        pcie = device["pcie"]
        pcie["link_generation_current"] = command_field(
            row[1], result.source, converter=lambda value: parse_number(value, True), source_ref="nvidia-smi"
        )
        pcie["link_generation_max"] = command_field(
            row[2], result.source, converter=lambda value: parse_number(value, True), source_ref="nvidia-smi"
        )
        pcie["link_width_current"] = command_field(
            row[3], result.source, converter=lambda value: parse_number(value, True), source_ref="nvidia-smi",
            unit="lanes"
        )
        pcie["link_width_max"] = command_field(
            row[4], result.source, converter=lambda value: parse_number(value, True), source_ref="nvidia-smi",
            unit="lanes"
        )


def collect_nvidia(runner: ProbeRunner) -> tuple[dict[str, Any], int | None, str]:
    executable = runner.which("nvidia-smi")
    device_nodes = runner.glob("/dev/nvidia[0-9]*")
    command_availability = availability(runner, "nvidia-smi")
    base: dict[str, Any] = {
        "implementation_tested_status": reported(
            "executable-baseline-fixture-tested",
            "skill-contract:offline-self-test",
            source_ref="nvidia-smi",
        ),
        "command_availability": {"nvidia-smi": command_availability},
        "device_nodes": observed(device_nodes, "glob:/dev/nvidia[0-9]*"),
    }
    if not executable:
        target_status = "capability-detected-tool-unavailable" if device_nodes else "not-detected"
        node_count = len(device_nodes)
        base.update(
            {
                "target_probe_status": observed(target_status, "path and device-node probes"),
                "visible_device_count": observed(node_count, "glob:/dev/nvidia[0-9]*"),
                "devices": unavailable(
                    "NVIDIA device nodes are visible but nvidia-smi identity is unavailable",
                    source_ref="nvidia-smi",
                ) if device_nodes else observed([], "path and device-node probes"),
                "topology_matrix": unavailable("nvidia-smi is not available", source_ref="nvidia-smi"),
                "nvlink_status": unavailable("nvidia-smi is not available", source_ref="nvidia-smi"),
                "mig_instances": unavailable("nvidia-smi is not available", source_ref="nvidia-mig"),
                "driver_supported_cuda_version": unavailable("nvidia-smi is not available", source_ref="nvidia-smi"),
            }
        )
        return base, node_count, target_status

    full_query = runner.run(
        "nvidia_smi_query_full",
        ["nvidia-smi", f"--query-gpu={','.join(NVIDIA_FIELDS)}", "--format=csv,noheader,nounits"],
    )
    query = full_query
    full = full_query.ok
    if not full:
        query = runner.run(
            "nvidia_smi_query_basic",
            ["nvidia-smi", f"--query-gpu={','.join(NVIDIA_BASIC_FIELDS)}", "--format=csv,noheader,nounits"],
        )

    if query.ok:
        devices = [nvidia_device_from_row(row, query.source, full) for row in parse_csv_rows(query.stdout)]
        target_status = "tested"
        devices_evidence = observed(devices, query.source, source_ref="nvidia-smi")
        count_evidence = observed(len(devices), query.source, source_ref="nvidia-smi")
        count: int | None = len(devices)
    else:
        devices = []
        target_status = "probe-failed"
        reason = f"identity query failed with return code {query.returncode}"
        devices_evidence = unavailable(reason, source_ref="nvidia-smi")
        count_evidence = unavailable(reason, source_ref="nvidia-smi")
        count = None

    pcie_result = runner.run(
        "nvidia_smi_query_pcie",
        ["nvidia-smi", f"--query-gpu={','.join(NVIDIA_PCIE_FIELDS)}", "--format=csv,noheader,nounits"],
    )
    apply_nvidia_pcie(devices, pcie_result)
    topology = runner.run("nvidia_smi_topology", ["nvidia-smi", "topo", "-m"])
    nvlink = runner.run("nvidia_smi_nvlink", ["nvidia-smi", "nvlink", "--status"])
    listing = runner.run("nvidia_smi_list", ["nvidia-smi", "-L"])
    mig_lines = [line.strip() for line in listing.stdout.splitlines() if line.lstrip().startswith("MIG ")]
    if listing.ok:
        mig_evidence = observed(mig_lines, listing.source, source_ref="nvidia-mig")
    else:
        mig_evidence = unavailable(
            f"device listing failed with return code {listing.returncode}", source_ref="nvidia-mig"
        )

    summary = runner.run("nvidia_smi_summary", ["nvidia-smi"])
    cuda_match = re.search(r"CUDA Version:\s*([0-9.]+)", summary.stdout)
    cuda_supported = (
        observed(cuda_match.group(1), summary.source, source_ref="nvidia-smi")
        if summary.ok and cuda_match
        else unavailable("driver-supported CUDA version was not reported", source_ref="nvidia-smi")
    )
    base.update(
        {
            "target_probe_status": observed(target_status, query.source, source_ref="nvidia-smi"),
            "visible_device_count": count_evidence,
            "devices": devices_evidence,
            "topology_matrix": command_evidence(topology, source_ref="nvidia-smi"),
            "nvlink_status": command_evidence(nvlink, source_ref="nvidia-smi"),
            "mig_instances": mig_evidence,
            "driver_supported_cuda_version": cuda_supported,
        }
    )
    return base, count, target_status


def json_or_text(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def infer_amd_device_count(value: Any) -> int | None:
    if isinstance(value, list):
        return len(value)
    if isinstance(value, dict):
        for key in ("gpu", "gpus", "devices", "GPU", "GPUs"):
            candidate = value.get(key)
            if isinstance(candidate, list):
                return len(candidate)
            if isinstance(candidate, dict):
                return len(candidate)
        numeric_keys = [key for key in value if str(key).isdigit()]
        if numeric_keys:
            return len(numeric_keys)
    return None


def collect_amd(runner: ProbeRunner) -> tuple[dict[str, Any], int | None, str]:
    commands = ("amd-smi", "rocm-smi", "rocminfo", "hipcc", "hipconfig")
    command_availability = {name: availability(runner, name) for name in commands}
    render_nodes = runner.glob("/dev/dri/renderD*")
    amdgpu_module = runner.path_exists("/sys/module/amdgpu")
    device_nodes = {
        "dev_kfd": observed(runner.path_exists("/dev/kfd"), "path-probe:/dev/kfd"),
        "render_nodes": observed(render_nodes, "glob:/dev/dri/renderD*"),
        "amdgpu_kernel_module": observed(amdgpu_module, "path-probe:/sys/module/amdgpu"),
    }
    detected = any(runner.which(name) for name in ("amd-smi", "rocm-smi", "rocminfo"))
    detected = detected or runner.path_exists("/dev/kfd") or amdgpu_module
    base: dict[str, Any] = {
        "implementation_tested_status": reported(
            "capability-path-fixture-tested; real-hardware-unverified",
            "skill-contract:offline-self-test",
            source_ref="amd-smi",
        ),
        "support_boundary": reported(
            "Capability discovery only; AMD/ROCm parsing and telemetry are not asserted as hardware-validated.",
            "skill-contract:backend-boundary",
            source_ref="amd-smi",
        ),
        "command_availability": command_availability,
        "device_nodes": device_nodes,
    }
    if not detected:
        base.update(
            {
                "target_probe_status": observed("not-detected", "AMD capability probes"),
                "visible_device_count": observed(0, "AMD capability probes"),
                "device_listing": observed([], "AMD capability probes"),
                "static_properties": unavailable("AMD management command is not available", source_ref="amd-smi"),
                "telemetry": unavailable("AMD management command is not available", source_ref="amd-smi"),
                "rocminfo_agents": unavailable("rocminfo is not available", source_ref="rocminfo"),
            }
        )
        return base, 0, "not-detected"

    target_status = "capability-detected-unverified"
    count: int | None = None
    if runner.which("amd-smi"):
        version = runner.run("amd_smi_version", ["amd-smi", "version"])
        listing = runner.run("amd_smi_list", ["amd-smi", "list", "--json"])
        static = runner.run("amd_smi_static", ["amd-smi", "static", "--json"])
        metric = runner.run("amd_smi_metric", ["amd-smi", "metric", "--json"])
        listing_evidence = command_evidence(listing, source_ref="amd-smi", transform=json_or_text)
        if listing_evidence["status"] == "observed":
            count = infer_amd_device_count(listing_evidence["value"])
        base["amd_smi_version"] = command_evidence(version, source_ref="amd-smi")
        base["device_listing"] = listing_evidence
        base["static_properties"] = command_evidence(static, source_ref="amd-smi", transform=json_or_text)
        base["telemetry"] = command_evidence(metric, source_ref="amd-smi", transform=json_or_text)
    elif runner.which("rocm-smi"):
        listing = runner.run(
            "rocm_smi_readonly",
            [
                "rocm-smi", "--json", "--showproductname", "--showbus", "--showmeminfo", "vram",
                "--showuse", "--showtemp", "--showpower", "--showclocks",
            ],
        )
        listing_evidence = command_evidence(listing, source_ref="amd-smi", transform=json_or_text)
        if listing_evidence["status"] == "observed":
            count = infer_amd_device_count(listing_evidence["value"])
        base["amd_smi_version"] = unavailable("amd-smi is not available", source_ref="amd-smi")
        base["device_listing"] = listing_evidence
        base["static_properties"] = unavailable("amd-smi static probe is not available", source_ref="amd-smi")
        base["telemetry"] = listing_evidence
    else:
        base["amd_smi_version"] = unavailable("AMD management CLI is not available", source_ref="amd-smi")
        base["device_listing"] = unavailable("AMD management CLI is not available", source_ref="amd-smi")
        base["static_properties"] = unavailable("AMD management CLI is not available", source_ref="amd-smi")
        base["telemetry"] = unavailable("AMD management CLI is not available", source_ref="amd-smi")

    if runner.which("rocminfo"):
        rocminfo = runner.run("rocminfo", ["rocminfo"])
        base["rocminfo_agents"] = command_evidence(rocminfo, source_ref="rocminfo")
    else:
        base["rocminfo_agents"] = unavailable("rocminfo is not available", source_ref="rocminfo")

    base["target_probe_status"] = observed(target_status, "AMD capability probes", source_ref="amd-smi")
    base["visible_device_count"] = (
        observed(count, "AMD management listing or render-node count", source_ref="amd-smi")
        if count is not None
        else unavailable("AMD capability detected but visible device count could not be established", source_ref="amd-smi")
    )
    return base, count, target_status


def collect_container(runner: ProbeRunner, args: argparse.Namespace) -> dict[str, Any]:
    cgroup = runner.read_text("/proc/1/cgroup") or ""
    docker_marker = runner.path_exists("/.dockerenv")
    podman_marker = runner.path_exists("/run/.containerenv")
    cgroup_marker = bool(re.search(r"(?:docker|containerd|kubepods|libpod|lxc)", cgroup, re.IGNORECASE))
    detect_value: str | None = None
    if runner.which("systemd-detect-virt"):
        detection = runner.run("container_detect", ["systemd-detect-virt", "--container"])
        if detection.ok and detection.stdout.strip() not in {"", "none"}:
            detect_value = detection.stdout.strip().splitlines()[0]
    containerized = docker_marker or podman_marker or cgroup_marker or detect_value is not None
    inferred_runtime = detect_value
    if inferred_runtime is None and docker_marker:
        inferred_runtime = "docker-compatible"
    if inferred_runtime is None and podman_marker:
        inferred_runtime = "podman-compatible"
    runtime = (
        reported(args.container_runtime, "argument:--container-runtime")
        if args.container_runtime
        else observed(inferred_runtime, "container boundary markers")
        if inferred_runtime
        else unavailable("container runtime was not reported or identifiable")
    )
    return {
        "is_container": observed(containerized, "container boundary markers"),
        "runtime": runtime,
        "image_reference": (
            reported(args.container_image, "argument:--container-image")
            if args.container_image
            else unavailable("container image reference was not supplied")
        ),
        "image_digest": (
            reported(
                args.image_digest,
                "argument:--image-digest",
                source_ref="oci-image-descriptor",
            )
            if args.image_digest
            else unavailable("container image digest was not supplied", source_ref="oci-image-descriptor")
        ),
        "host_boundary": observed(
            "container-visible view; host packages and firmware may be outside this namespace"
            if containerized
            else "direct host view",
            "container boundary markers",
        ),
    }


def parse_lscpu(text: str) -> dict[str, str]:
    parsed = json.loads(text)
    entries = parsed.get("lscpu", [])
    return {
        str(entry.get("field", "")).rstrip(":"): str(entry.get("data", ""))
        for entry in entries
        if entry.get("field")
    }


def collect_host(runner: ProbeRunner, storage_path: Path) -> dict[str, Any]:
    uname = runner.run("uname", ["uname", "-srmo"])
    lscpu = runner.run("lscpu", ["lscpu", "--json"])
    lscpu_data: dict[str, str] = {}
    if lscpu.ok:
        try:
            lscpu_data = parse_lscpu(lscpu.stdout)
        except (ValueError, TypeError, json.JSONDecodeError):
            lscpu_data = {}

    def cpu_field(label: str, converter: Callable[[str], Any] | None = None) -> dict[str, Any]:
        value = lscpu_data.get(label)
        if value is not None:
            return command_field(value, lscpu.source, converter=converter)
        if not runner.fixture_mode and label == "CPU(s)" and os.cpu_count() is not None:
            return observed(os.cpu_count(), "python:os.cpu_count")
        if not runner.fixture_mode and label == "Architecture":
            return observed(platform.machine(), "python:platform.machine")
        return unavailable(f"lscpu field {label!r} unavailable")

    meminfo = runner.read_text("/proc/meminfo")
    mem_values: dict[str, int] = {}
    if meminfo:
        for line in meminfo.splitlines():
            match = re.match(r"(MemTotal|MemAvailable|SwapTotal):\s+(\d+)\s+kB", line)
            if match:
                mem_values[match.group(1)] = int(match.group(2)) * 1024

    def memory_field(name: str) -> dict[str, Any]:
        if name in mem_values:
            return observed(mem_values[name], "file:/proc/meminfo", unit="bytes")
        return unavailable(f"{name} unavailable in /proc/meminfo", unit="bytes")

    numa_online = runner.read_text("/sys/devices/system/node/online")
    df_result = runner.run(
        "df_storage",
        ["df", "-B1", "--output=fstype,size,used,avail", str(storage_path)],
    )
    storage: dict[str, Any]
    if df_result.ok:
        lines = [line.strip() for line in df_result.stdout.splitlines() if line.strip()]
        values = lines[-1].split() if len(lines) >= 2 else []
        if len(values) >= 4:
            try:
                storage = {
                    "filesystem_type": observed(values[0], df_result.source),
                    "total_bytes": observed(int(values[1]), df_result.source, unit="bytes"),
                    "used_bytes": observed(int(values[2]), df_result.source, unit="bytes"),
                    "available_bytes": observed(int(values[3]), df_result.source, unit="bytes"),
                }
            except ValueError:
                storage = {}
        else:
            storage = {}
    else:
        storage = {}
    if not storage and not runner.fixture_mode:
        try:
            stats = os.statvfs(storage_path)
            storage = {
                "filesystem_type": unavailable("filesystem type unavailable from statvfs"),
                "total_bytes": observed(stats.f_blocks * stats.f_frsize, "python:os.statvfs", unit="bytes"),
                "used_bytes": observed(
                    (stats.f_blocks - stats.f_bfree) * stats.f_frsize, "python:os.statvfs", unit="bytes"
                ),
                "available_bytes": observed(stats.f_bavail * stats.f_frsize, "python:os.statvfs", unit="bytes"),
            }
        except OSError:
            storage = {}
    if not storage:
        storage = {
            "filesystem_type": unavailable("storage probe unavailable"),
            "total_bytes": unavailable("storage probe unavailable", unit="bytes"),
            "used_bytes": unavailable("storage probe unavailable", unit="bytes"),
            "available_bytes": unavailable("storage probe unavailable", unit="bytes"),
        }

    os_release = runner.read_text("/etc/os-release") or ""
    release_values: dict[str, str] = {}
    for line in os_release.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            if key in {"ID", "VERSION_ID"}:
                release_values[key] = value.strip().strip('"')
    return {
        "kernel": command_evidence(uname),
        "operating_system": {
            "id": observed(release_values["ID"], "file:/etc/os-release")
            if "ID" in release_values else unavailable("OS ID unavailable"),
            "version_id": observed(release_values["VERSION_ID"], "file:/etc/os-release")
            if "VERSION_ID" in release_values else unavailable("OS version unavailable"),
        },
        "cpu": {
            "architecture": cpu_field("Architecture"),
            "logical_cpu_count": cpu_field("CPU(s)", lambda value: parse_number(value, True)),
            "model": cpu_field("Model name"),
            "threads_per_core": cpu_field("Thread(s) per core", lambda value: parse_number(value, True)),
            "cores_per_socket": cpu_field("Core(s) per socket", lambda value: parse_number(value, True)),
            "socket_count": cpu_field("Socket(s)", lambda value: parse_number(value, True)),
            "numa_node_count": cpu_field("NUMA node(s)", lambda value: parse_number(value, True)),
        },
        "numa": {
            "online_nodes": observed(numa_online.strip(), "file:/sys/devices/system/node/online")
            if numa_online is not None else unavailable("NUMA node online map unavailable"),
        },
        "memory": {
            "total_bytes": memory_field("MemTotal"),
            "available_bytes": memory_field("MemAvailable"),
            "swap_total_bytes": memory_field("SwapTotal"),
            "cgroup_limit": command_field(
                runner.read_text("/sys/fs/cgroup/memory.max"),
                "file:/sys/fs/cgroup/memory.max",
                missing_reason="cgroup v2 memory limit unavailable",
            ),
        },
        "cpu_cgroup_limit": command_field(
            runner.read_text("/sys/fs/cgroup/cpu.max"),
            "file:/sys/fs/cgroup/cpu.max",
            missing_reason="cgroup v2 CPU limit unavailable",
        ),
        "storage": storage,
    }


def first_installed(runner: ProbeRunner, names: Iterable[str]) -> tuple[str, str] | None:
    for name in names:
        version = runner.package_version(name)
        if version is not None:
            return name, version
    return None


def parse_last_json_line(text: str) -> Any:
    for line in reversed(text.splitlines()):
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            continue
    raise ValueError("no JSON line")


def collect_software(runner: ProbeRunner, args: argparse.Namespace, nvidia: dict[str, Any]) -> dict[str, Any]:
    compiler_commands = {
        "nvcc": ("nvcc_version", ["nvcc", "--version"], "nvidia-smi"),
        "hipcc": ("hipcc_version", ["hipcc", "--version"], "amd-smi"),
        "hipconfig": ("hipconfig_version", ["hipconfig", "--version"], "amd-smi"),
    }
    compilers: dict[str, Any] = {}
    for name, (key, argv, ref) in compiler_commands.items():
        if runner.which(name):
            compilers[name] = command_evidence(runner.run(key, argv), source_ref=ref)
        else:
            compilers[name] = unavailable(f"{name} is not available", source_ref=ref)

    nvidia_container = (
        command_evidence(
            runner.run("nvidia_container_cli_version", ["nvidia-container-cli", "--version"]),
            source_ref="nvidia-smi",
        )
        if runner.which("nvidia-container-cli")
        else unavailable("nvidia-container-cli is not available", source_ref="nvidia-smi")
    )
    ldconfig_value: dict[str, Any]
    if runner.which("ldconfig"):
        ldconfig = runner.run("ldconfig", ["ldconfig", "-p"])
        if ldconfig.ok:
            runtime_names = sorted(
                {
                    match.group(1)
                    for line in ldconfig.stdout.splitlines()
                    if (match := re.search(r"\b(lib(?:cuda|cudart|amdhip64)\.so(?:\.[0-9.]+)*)\b", line))
                }
            )
            ldconfig_value = observed(runtime_names, ldconfig.source)
        else:
            ldconfig_value = unavailable(f"ldconfig failed with return code {ldconfig.returncode}")
    else:
        ldconfig_value = unavailable("ldconfig is not available")

    framework_distributions = {
        "pytorch": ("torch",),
        "tensorflow": ("tensorflow", "tensorflow-cpu"),
        "jax": ("jax",),
        "jaxlib": ("jaxlib",),
        "cupy": ("cupy-cuda12x", "cupy-cuda11x", "cupy"),
    }
    frameworks: dict[str, Any] = {}
    for framework, distributions in framework_distributions.items():
        installed = first_installed(runner, distributions)
        frameworks[framework] = (
            observed(
                {"distribution": installed[0], "version": installed[1]},
                "python:importlib.metadata",
            )
            if installed
            else unavailable("framework distribution is not installed")
        )

    framework_visibility: dict[str, Any] = {}
    probe_code = {
        "pytorch": (
            "framework_probe_pytorch",
            "import json,torch;print(json.dumps({'version':torch.__version__,'cuda_version':torch.version.cuda,"
            "'hip_version':torch.version.hip,'accelerator_available':torch.cuda.is_available(),"
            "'visible_device_count':torch.cuda.device_count()}))",
        ),
        "tensorflow": (
            "framework_probe_tensorflow",
            "import json,tensorflow as tf;g=tf.config.list_physical_devices('GPU');"
            "print(json.dumps({'version':tf.__version__,'visible_device_count':len(g)}))",
        ),
        "jax": (
            "framework_probe_jax",
            "import json,jax;d=jax.devices();print(json.dumps({'version':jax.__version__,"
            "'visible_device_count':len(d),'platforms':sorted(set(x.platform for x in d))}))",
        ),
    }
    for framework, (key, code) in probe_code.items():
        if not args.probe_frameworks:
            framework_visibility[framework] = unavailable("framework import probe was not requested")
        elif frameworks[framework]["status"] != "observed":
            framework_visibility[framework] = unavailable("framework distribution is not installed")
        else:
            result = runner.run(key, [sys.executable, "-c", code])
            framework_visibility[framework] = command_evidence(result, transform=parse_last_json_line)

    kernel_modules = {
        "nvidia": command_field(
            runner.read_text("/sys/module/nvidia/version"),
            "file:/sys/module/nvidia/version",
            source_ref="nvidia-smi",
            missing_reason="NVIDIA kernel module version unavailable",
        ),
        "amdgpu_present": observed(runner.path_exists("/sys/module/amdgpu"), "path-probe:/sys/module/amdgpu"),
    }
    python_version = (
        str(runner.fixture.get("python", {}).get("version"))
        if runner.fixture is not None and runner.fixture.get("python", {}).get("version")
        else platform.python_version()
    )
    return {
        "python_version": observed(python_version, "python:platform.python_version"),
        "kernel_modules": kernel_modules,
        "driver_supported_cuda_version": nvidia["driver_supported_cuda_version"],
        "runtime_libraries": ldconfig_value,
        "nvidia_container_cli": nvidia_container,
        "compilers": compilers,
        "framework_versions": frameworks,
        "framework_accelerator_visibility": framework_visibility,
    }


LOCKFILE_NAMES = (
    "Cargo.lock",
    "Gemfile.lock",
    "Pipfile.lock",
    "composer.lock",
    "conda-lock.yml",
    "environment.yml",
    "go.sum",
    "package-lock.json",
    "pnpm-lock.yaml",
    "poetry.lock",
    "uv.lock",
    "yarn.lock",
)


def sha256_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            size += len(chunk)
            digest.update(chunk)
    return digest.hexdigest(), size


def within_root(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (ValueError, OSError):
        return False


def collect_project(runner: ProbeRunner, args: argparse.Namespace) -> dict[str, Any]:
    if not args.project_root:
        return {
            "root": unavailable("project root was not supplied"),
            "exists": unavailable("project root was not supplied"),
            "git_revision": unavailable("project root was not supplied"),
            "tracked_worktree_dirty": unavailable("project root was not supplied"),
            "dependency_lockfiles": unavailable("project root was not supplied"),
        }
    root = Path(args.project_root)
    root_exists = root.is_dir() if not runner.fixture_mode else bool(runner.fixture.get("project", {}).get("exists", False))
    result: dict[str, Any] = {
        "root": reported(args.project_root, "argument:--project-root"),
        "exists": observed(root_exists, "path-probe:project-root"),
    }
    if not root_exists:
        result.update(
            {
                "git_revision": unavailable("project root does not exist"),
                "tracked_worktree_dirty": unavailable("project root does not exist"),
                "dependency_lockfiles": unavailable("project root does not exist"),
            }
        )
        return result

    if runner.which("git"):
        revision = runner.run("git_revision", ["git", "-C", str(root), "rev-parse", "HEAD"])
        dirty = runner.run(
            "git_tracked_status",
            ["git", "-C", str(root), "status", "--porcelain=v1", "--untracked-files=no"],
        )
        result["git_revision"] = command_evidence(revision)
        result["tracked_worktree_dirty"] = (
            observed(bool(dirty.stdout.strip()), dirty.source)
            if dirty.ok
            else unavailable(f"git status failed with return code {dirty.returncode}")
        )
    else:
        result["git_revision"] = unavailable("git is not available")
        result["tracked_worktree_dirty"] = unavailable("git is not available")

    candidates: set[Path] = set()
    if not runner.fixture_mode:
        for name in LOCKFILE_NAMES:
            candidate = root / name
            if candidate.is_file() and within_root(candidate, root):
                candidates.add(candidate)
        for candidate in root.glob("requirements*.txt"):
            if candidate.is_file() and within_root(candidate, root):
                candidates.add(candidate)
        for supplied in args.lock_file:
            candidate = Path(supplied)
            if not candidate.is_absolute():
                candidate = root / candidate
            if candidate.is_file() and within_root(candidate, root):
                candidates.add(candidate)
    lock_records: list[dict[str, Any]] = []
    for candidate in sorted(candidates, key=lambda value: str(value)):
        digest, size = sha256_file(candidate)
        lock_records.append(
            {
                "path": observed(str(candidate.resolve().relative_to(root.resolve())), "filesystem:lockfile-discovery"),
                "sha256": observed(digest, f"sha256:{candidate.name}"),
                "bytes": observed(size, f"filesystem:{candidate.name}", unit="bytes"),
            }
        )
    result["dependency_lockfiles"] = (
        observed(lock_records, "filesystem:lockfile-discovery")
        if lock_records
        else unavailable("no supported root-level or explicitly selected dependency lockfile was found")
    )
    return result


def optional_reported(value: Any, argument: str, *, unit: str | None = None) -> dict[str, Any]:
    return reported(value, f"argument:{argument}", unit=unit) if value is not None else unavailable(f"{argument} was not supplied", unit=unit)


def collect_budget(args: argparse.Namespace) -> dict[str, Any]:
    requested = {
        "gpu_count": optional_reported(args.gpu_count, "--gpu-count", unit="devices"),
        "cpu_count": optional_reported(args.cpu_count, "--cpu-count", unit="logical CPUs"),
        "duration_hours": optional_reported(args.duration_hours, "--duration-hours", unit="hours"),
        "disk_gb": optional_reported(args.disk_gb, "--disk-gb", unit="GB (10^9 bytes)"),
        "hourly_cost_cap": optional_reported(args.hourly_cost_cap, "--hourly-cost-cap", unit="currency/hour"),
        "total_cost_cap": optional_reported(args.total_cost_cap, "--total-cost-cap", unit="currency"),
        "currency": optional_reported(args.currency, "--currency"),
    }
    if args.duration_hours is not None and args.hourly_cost_cap is not None:
        derived = round(args.duration_hours * args.hourly_cost_cap, 8)
        estimated = observed(
            derived,
            "derived:--duration-hours * --hourly-cost-cap",
            unit="currency",
        )
    else:
        derived = None
        estimated = unavailable("duration and hourly cost cap are both required", unit="currency")
    if derived is not None and args.total_cost_cap is not None:
        within = observed(derived <= args.total_cost_cap, "derived:estimated total <= --total-cost-cap")
    else:
        within = unavailable("estimated total and total cost cap are both required")
    return {
        "requested_limits": requested,
        "hourly_cap_times_duration": estimated,
        "within_total_cost_cap": within,
    }


def collect_environment(runner: ProbeRunner) -> dict[str, Any]:
    selected: dict[str, Any] = {}
    for name in ENV_ALLOWLIST:
        value = runner.environment_value(name)
        selected[name] = (
            observed(value, f"environment-allowlist:{name}")
            if value is not None
            else unavailable("allowlisted variable is not set")
        )
    return {
        "allowlist": reported(list(ENV_ALLOWLIST), "skill-contract:environment-allowlist"),
        "selected_values": selected,
        "full_environment_captured": observed(False, "skill-contract:environment-allowlist"),
    }


def nonnegative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be non-negative")
    return parsed


def nonnegative_float(value: str) -> float:
    parsed = float(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be non-negative")
    return parsed


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default="gpu-environment-attestation", help="new output directory")
    parser.add_argument("--fixture", type=Path, help="offline command-output fixture JSON")
    parser.add_argument("--attestation-status", choices=("draft", "complete"), default="draft")
    parser.add_argument("--target-label", help="operator-supplied non-secret target label")
    parser.add_argument("--project-root", help="optional project root for Git and lockfile evidence")
    parser.add_argument("--lock-file", action="append", default=[], help="project-relative lockfile; repeatable")
    parser.add_argument("--container-runtime", help="reported container runtime")
    parser.add_argument("--container-image", help="reported container image reference")
    parser.add_argument("--image-digest", help="reported immutable OCI image digest")
    parser.add_argument("--gpu-count", type=nonnegative_int, help="requested GPU count")
    parser.add_argument("--cpu-count", type=nonnegative_int, help="requested logical CPU count")
    parser.add_argument("--duration-hours", type=nonnegative_float, help="expected duration")
    parser.add_argument("--disk-gb", type=nonnegative_float, help="requested disk capacity in decimal GB")
    parser.add_argument("--hourly-cost-cap", type=nonnegative_float, help="maximum cost per hour")
    parser.add_argument("--total-cost-cap", type=nonnegative_float, help="maximum total cost")
    parser.add_argument("--currency", help="currency code or accounting unit for cost limits")
    parser.add_argument(
        "--probe-frameworks",
        action="store_true",
        help="import installed frameworks in isolated subprocesses to count visible accelerators",
    )
    parser.add_argument("--command-timeout", type=nonnegative_float, default=15.0)
    args = parser.parse_args(argv)
    if args.command_timeout <= 0 or args.command_timeout > 60:
        parser.error("--command-timeout must be greater than 0 and no more than 60 seconds")
    return args


def build_attestation(args: argparse.Namespace) -> dict[str, Any]:
    runner = ProbeRunner(args.fixture, args.command_timeout)
    nvidia, nvidia_count, nvidia_status = collect_nvidia(runner)
    amd, amd_count, amd_status = collect_amd(runner)
    storage_path = Path(args.project_root) if args.project_root else Path.cwd()
    container = collect_container(runner, args)
    host = collect_host(runner, storage_path)
    software = collect_software(runner, args, nvidia)
    if nvidia_count is not None and amd_count is not None:
        visible_count = observed(nvidia_count + amd_count, "derived:backend visible device counts", unit="devices")
    else:
        visible_count = unavailable("one or more detected backend device counts could not be established", unit="devices")
    if nvidia_count == 0 and amd_count == 0:
        hardware_summary = "no-visible-gpu-detected"
    elif nvidia_status == "probe-failed" and amd_status == "not-detected":
        hardware_summary = "gpu-tool-present-but-probe-failed"
    else:
        hardware_summary = "gpu-capability-detected"

    generation_warnings: list[dict[str, str]] = []
    if hardware_summary == "no-visible-gpu-detected":
        generation_warnings.append(
            {"code": "hardware.no_gpu", "message": "No visible GPU backend was detected; this is a valid attestation."}
        )
    if amd_status == "capability-detected-unverified":
        generation_warnings.append(
            {"code": "backend.amd_unverified", "message": "AMD/ROCm capability was detected; the backend remains hardware-unverified."}
        )
    if container["is_container"]["value"]:
        generation_warnings.append(
            {"code": "boundary.container", "message": "Observations are container-visible and do not prove host package or firmware state."}
        )
    if args.image_digest and not re.fullmatch(r"[A-Za-z0-9_+.-]+:[A-Fa-f0-9]{32,}", args.image_digest):
        generation_warnings.append(
            {"code": "input.image_digest_format", "message": "Reported image digest does not match the usual algorithm:hex form."}
        )

    target_label = (
        reported(args.target_label, "argument:--target-label")
        if args.target_label
        else unavailable("target label was not supplied")
    )
    fixture_name = None
    if runner.fixture is not None:
        fixture_name = str(runner.fixture.get("metadata", {}).get("name", "unnamed-fixture"))
    return {
        "schema": {"name": SCHEMA_NAME, "version": SCHEMA_VERSION},
        "metadata": {
            "attestation_id": str(uuid.uuid4()),
            "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "document_status": observed(args.attestation_status, "argument/default:--attestation-status"),
            "collection_mode": observed("fixture" if runner.fixture_mode else "live", "collector runtime"),
            "fixture_name": observed(fixture_name, "fixture:metadata.name")
            if fixture_name is not None else unavailable("live collection did not use a fixture"),
            "target_label": target_label,
        },
        "scope": {
            "platform": observed("Linux", "collector support contract"),
            "execution_view": observed(
                "container" if container["is_container"]["value"] else "bare-metal-or-host",
                "container boundary markers",
            ),
            "read_only": observed(True, "collector command allowlist"),
        },
        "budget": collect_budget(args),
        "container": container,
        "gpu": {
            "summary": observed(hardware_summary, "derived:backend target probe statuses"),
            "visible_device_count": visible_count,
            "nvidia": nvidia,
            "amd_rocm": amd,
        },
        "host": host,
        "software": software,
        "project": collect_project(runner, args),
        "device_selection_environment": collect_environment(runner),
        "change_control": {
            "actions_performed": observed([], "collector command allowlist"),
            "separate_explicit_authorization_required": reported(
                [
                    "driver, firmware, kernel-module, runtime, or system-package changes",
                    "power-limit or clock changes",
                    "MIG, partitioning, reset, persistence, or compute-mode changes",
                ],
                "skill-contract:change-boundary",
            ),
        },
        "references": [
            {"id": key, "title": value["title"], "url": value["url"]}
            for key, value in REFERENCE_CATALOG.items()
        ],
        "warnings": generation_warnings,
    }


def write_bundle(attestation: dict[str, Any], output_dir: Path) -> None:
    output_dir = output_dir.absolute()
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    if os.path.lexists(output_dir):
        raise FileExistsError(f"output path already exists: {output_dir}")
    stage = Path(tempfile.mkdtemp(prefix=".gpu-attestation-stage-", dir=output_dir.parent))
    try:
        attestation_path = stage / "attestation.json"
        attestation_path.write_text(
            json.dumps(attestation, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        attestation_hash, attestation_size = sha256_file(attestation_path)
        manifest = {
            "schema": {"name": MANIFEST_SCHEMA_NAME, "version": MANIFEST_SCHEMA_VERSION},
            "attestation_schema": {"name": SCHEMA_NAME, "version": SCHEMA_VERSION},
            "artifacts": [
                {
                    "path": "attestation.json",
                    "bytes": attestation_size,
                    "sha256": attestation_hash,
                }
            ],
        }
        manifest_path = stage / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        manifest_hash, _ = sha256_file(manifest_path)
        (stage / "manifest.sha256").write_text(f"{manifest_hash}  manifest.json\n", encoding="ascii")
        if os.path.lexists(output_dir):
            raise FileExistsError(f"output path appeared during collection: {output_dir}")
        os.replace(stage, output_dir)
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(argv)
        attestation = build_attestation(args)
        output_dir = Path(args.output_dir)
        write_bundle(attestation, output_dir)
        print(str(output_dir.resolve()))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
