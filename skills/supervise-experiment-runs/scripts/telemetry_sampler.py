#!/usr/bin/env python3
"""Run bounded, contract-driven telemetry probes without a shell."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import selectors
import signal
import stat
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
SAMPLER_VERSION = "1.1"
IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")
ENVIRONMENT_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
SECRET_ENVIRONMENT_NAME = re.compile(
    r"(?:^|_)(?:ACCESS_?KEY|API_?KEY|AUTH|BEARER|COOKIE|CREDENTIALS?|PASS(?:WORD|WD)?|PRIVATE_?KEY|SECRET|TOKEN)(?:_|$)",
    re.IGNORECASE,
)
SHELL_NAMES = {"sh", "bash", "dash", "zsh", "ksh", "fish", "cmd", "cmd.exe", "powershell", "powershell.exe", "pwsh", "pwsh.exe"}
SHELL_COMMAND_SWITCHES = {"-c", "/c", "-command", "-encodedcommand"}
TERMINAL_STATES = {"COMPLETED", "STOPPED", "FAILED"}
DEFAULT_MAX_TELEMETRY_BYTES = 256 * 1024 * 1024
MAX_TELEMETRY_BYTES = 4 * 1024 * 1024 * 1024
MAX_PROBE_OUTPUT_BYTES = 16 * 1024 * 1024
MAX_COMMAND_TIMEOUT_SECONDS = 3600
MAX_INTERVAL_SECONDS = 86400
MAX_SAMPLES = 10_000_000
MAX_PROBES = 128
MAX_ARGV_ITEMS = 256
MAX_ARG_BYTES = 16 * 1024
MAX_SAMPLE_CAPTURE_BYTES = 64 * 1024 * 1024
READ_CHUNK_BYTES = 64 * 1024
stop_requested = False


class SamplerError(ValueError):
    pass


class TelemetryOutputLimit(SamplerError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        handle.write(value)
        temporary = Path(handle.name)
    os.replace(temporary, path)


def atomic_json(path: Path, value: Any) -> None:
    atomic_text(path, json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n")


def jsonl_bytes(value: Any) -> bytes:
    line = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    return line.encode("utf-8")


def append_jsonl(handle: Any, value: Any, current_bytes: int, maximum_bytes: int) -> int:
    encoded = jsonl_bytes(value)
    if current_bytes + len(encoded) > maximum_bytes:
        raise TelemetryOutputLimit(
            f"telemetry JSONL byte budget exceeded: next record needs {len(encoded)} bytes "
            f"with {maximum_bytes - current_bytes} bytes remaining"
        )
    handle.write(encoded)
    handle.flush()
    os.fsync(handle.fileno())
    return current_bytes + len(encoded)


def positive_number(value: Any, label: str, minimum: float = 0.0, maximum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SamplerError(f"{label} must be numeric")
    number = float(value)
    if not math.isfinite(number) or number <= minimum:
        raise SamplerError(f"{label} must be greater than {minimum}")
    if maximum is not None and number > maximum:
        raise SamplerError(f"{label} must not exceed {maximum}")
    return number


def bounded_positive_integer(value: Any, label: str, maximum: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise SamplerError(f"{label} must be a positive integer")
    if value > maximum:
        raise SamplerError(f"{label} must not exceed {maximum}")
    return value


def validate_config(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("schema_version") != SCHEMA_VERSION:
        raise SamplerError("config schema_version must be 1")
    sampler_id = value.get("sampler_id")
    if not isinstance(sampler_id, str) or IDENTIFIER.fullmatch(sampler_id) is None:
        raise SamplerError("sampler_id is invalid")
    positive_number(value.get("interval_seconds"), "interval_seconds", maximum=MAX_INTERVAL_SECONDS)
    positive_number(
        value.get("command_timeout_seconds", 10),
        "command_timeout_seconds",
        maximum=MAX_COMMAND_TIMEOUT_SECONDS,
    )
    bounded_positive_integer(value.get("max_samples"), "max_samples", MAX_SAMPLES)
    bounded_positive_integer(
        value.get("max_output_bytes", 65536),
        "max_output_bytes",
        MAX_PROBE_OUTPUT_BYTES,
    )
    bounded_positive_integer(
        value.get("max_telemetry_bytes", DEFAULT_MAX_TELEMETRY_BYTES),
        "max_telemetry_bytes",
        MAX_TELEMETRY_BYTES,
    )
    allowlist = value.get("environment_allowlist", ["PATH", "LANG", "LC_ALL", "TZ"])
    if not isinstance(allowlist, list) or any(
        not isinstance(item, str) or ENVIRONMENT_NAME.fullmatch(item) is None for item in allowlist
    ):
        raise SamplerError("environment_allowlist must be a list of environment-variable names")
    secret_names = sorted({item for item in allowlist if SECRET_ENVIRONMENT_NAME.search(item)})
    if secret_names:
        raise SamplerError(
            "environment_allowlist must contain only non-secret run settings; rejected secret-shaped names: "
            + ", ".join(secret_names)
        )
    probes = value.get("probes")
    if not isinstance(probes, list) or not probes:
        raise SamplerError("probes must be a non-empty list")
    if len(probes) > MAX_PROBES:
        raise SamplerError(f"probes must not contain more than {MAX_PROBES} entries")
    seen: set[str] = set()
    sample_capture_bytes = 0
    for index, probe in enumerate(probes):
        if not isinstance(probe, dict):
            raise SamplerError(f"probes[{index}] must be an object")
        probe_id = probe.get("id")
        if not isinstance(probe_id, str) or IDENTIFIER.fullmatch(probe_id) is None or probe_id in seen:
            raise SamplerError(f"probes[{index}].id is invalid or duplicated")
        seen.add(probe_id)
        argv = probe.get("argv")
        if not isinstance(argv, list) or not argv or any(not isinstance(item, str) or not item or "\x00" in item for item in argv):
            raise SamplerError(f"probes[{index}].argv must be a non-empty string array")
        if len(argv) > MAX_ARGV_ITEMS or any(len(item.encode("utf-8")) > MAX_ARG_BYTES for item in argv):
            raise SamplerError(f"probes[{index}].argv exceeds the item or byte bound")
        executable = Path(argv[0]).name.lower()
        if executable in SHELL_NAMES and any(item.lower() in SHELL_COMMAND_SWITCHES for item in argv[1:3]):
            raise SamplerError(f"probes[{index}].argv must not execute a shell command string")
        if probe.get("format", "json") not in {"json", "text"}:
            raise SamplerError(f"probes[{index}].format must be json or text")
        unavailable = probe.get("unavailable_exit_codes", [])
        if not isinstance(unavailable, list) or any(not isinstance(item, int) or isinstance(item, bool) or item < 0 or item > 255 for item in unavailable):
            raise SamplerError(f"probes[{index}].unavailable_exit_codes must contain exit codes")
        positive_number(
            probe.get("timeout_seconds", value.get("command_timeout_seconds", 10)),
            f"probes[{index}].timeout_seconds",
            maximum=MAX_COMMAND_TIMEOUT_SECONDS,
        )
        probe_output_bytes = bounded_positive_integer(
            probe.get("max_output_bytes", value.get("max_output_bytes", 65536)),
            f"probes[{index}].max_output_bytes",
            MAX_PROBE_OUTPUT_BYTES,
        )
        sample_capture_bytes += probe_output_bytes
        if not isinstance(probe.get("retain_error_output", False), bool):
            raise SamplerError(f"probes[{index}].retain_error_output must be boolean")
    if sample_capture_bytes > MAX_SAMPLE_CAPTURE_BYTES:
        raise SamplerError(
            f"combined per-sample probe output bounds must not exceed {MAX_SAMPLE_CAPTURE_BYTES} bytes"
        )
    return value


def load_config(path: Path) -> tuple[dict[str, Any], bytes]:
    if not direct_regular_file(path):
        raise SamplerError("config must be a regular file")
    raw = path.read_bytes()
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SamplerError(f"config is invalid JSON: {exc}") from exc
    return validate_config(value), raw


def absolute_path_without_resolving(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def direct_regular_file(path: Path) -> bool:
    try:
        return stat.S_ISREG(path.lstat().st_mode)
    except OSError:
        return False


def child_environment(config: dict[str, Any]) -> dict[str, str]:
    names = set(config.get("environment_allowlist", ["PATH", "LANG", "LC_ALL", "TZ"]))
    if os.name == "nt":
        names.update({"SYSTEMROOT", "WINDIR"})
    return {name: value for name, value in os.environ.items() if name in names}


def terminate_probe(process: subprocess.Popen[bytes]) -> None:
    if os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        if process.poll() is None:
            try:
                process.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                pass
        try:
            os.killpg(process.pid, 0)
        except ProcessLookupError:
            return
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            return
        if process.poll() is None:
            process.wait(timeout=1)
        return

    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=0.5)
        return
    except subprocess.TimeoutExpired:
        process.kill()
    process.wait(timeout=1)


def bounded_command(probe: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    started = time.monotonic()
    timeout_seconds = float(probe.get("timeout_seconds", config.get("command_timeout_seconds", 10)))
    max_bytes = int(probe.get("max_output_bytes", config.get("max_output_bytes", 65536)))
    outcome: dict[str, Any] = {"id": probe["id"]}
    process: subprocess.Popen[bytes] | None = None
    stdout = bytearray()
    stderr = bytearray()
    limit_exceeded = False
    timed_out = False
    try:
        try:
            process = subprocess.Popen(
                probe["argv"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=child_environment(config),
                shell=False,
                start_new_session=(os.name == "posix"),
            )
        except FileNotFoundError:
            outcome.update({"status": "unavailable", "reason": "executable_not_found", "exit_code": None})
            return outcome
        except OSError as exc:
            outcome.update(
                {
                    "status": "failed",
                    "reason": "launch_error",
                    "detail": type(exc).__name__,
                    "exit_code": None,
                }
            )
            return outcome

        assert process.stdout is not None and process.stderr is not None
        streams = {process.stdout: stdout, process.stderr: stderr}
        deadline = time.monotonic() + timeout_seconds
        with selectors.DefaultSelector() as selector:
            for stream in streams:
                os.set_blocking(stream.fileno(), False)
                selector.register(stream, selectors.EVENT_READ)
            while selector.get_map():
                remaining_time = deadline - time.monotonic()
                if remaining_time <= 0:
                    timed_out = True
                    terminate_probe(process)
                    break
                events = selector.select(timeout=max(0.0, min(0.1, remaining_time)))
                for key, _mask in events:
                    stream = key.fileobj
                    remaining = max_bytes - len(stdout) - len(stderr)
                    try:
                        chunk = os.read(stream.fileno(), min(READ_CHUNK_BYTES, remaining + 1))
                    except BlockingIOError:
                        continue
                    if not chunk:
                        selector.unregister(stream)
                        stream.close()
                        continue
                    streams[stream].extend(chunk[:remaining])
                    if len(chunk) > remaining:
                        limit_exceeded = True
                        terminate_probe(process)
                        break
                if limit_exceeded:
                    break
        for stream in streams:
            if not stream.closed:
                stream.close()
        if process.poll() is None:
            remaining_time = deadline - time.monotonic()
            try:
                process.wait(timeout=max(0.0, remaining_time))
            except subprocess.TimeoutExpired:
                timed_out = True
                terminate_probe(process)
        outcome.update(
            {
                "exit_code": process.returncode,
                "stdout_bytes": len(stdout),
                "stdout_sha256": sha256_bytes(bytes(stdout)),
                "stderr_bytes": len(stderr),
                "stderr_sha256": sha256_bytes(bytes(stderr)),
                "output_truncated": limit_exceeded,
            }
        )
        if timed_out:
            outcome.update({"status": "failed", "reason": "timeout"})
        elif limit_exceeded or outcome["stdout_bytes"] + outcome["stderr_bytes"] > max_bytes:
            outcome.update({"status": "failed", "reason": "output_limit_exceeded"})
        elif process.returncode in probe.get("unavailable_exit_codes", []):
            outcome.update({"status": "unavailable", "reason": "declared_unavailable_exit"})
        elif process.returncode != 0:
            outcome.update({"status": "failed", "reason": "nonzero_exit"})
        else:
            try:
                decoded = bytes(stdout).decode("utf-8")
                observed: Any = json.loads(decoded) if probe.get("format", "json") == "json" else decoded.rstrip("\n")
                json.dumps(observed, allow_nan=False)
                outcome.update({"status": "observed", "value": observed})
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
                outcome.update({"status": "failed", "reason": "parse_error", "detail": type(exc).__name__})
        if outcome["status"] != "observed" and bool(probe.get("retain_error_output", False)):
            outcome["stdout_excerpt"] = bytes(stdout).decode("utf-8", errors="replace")
            outcome["stderr_excerpt"] = bytes(stderr).decode("utf-8", errors="replace")
        return outcome
    finally:
        outcome["duration_ms"] = round((time.monotonic() - started) * 1000, 3)
        if process is not None:
            for stream in (process.stdout, process.stderr):
                if stream is not None and not stream.closed:
                    stream.close()
            if process.poll() is None:
                terminate_probe(process)


def linux_process_stat(pid: int) -> tuple[str, int] | None:
    if not sys.platform.startswith("linux"):
        return None
    try:
        raw = Path(f"/proc/{pid}/stat").read_bytes()
        fields = raw[raw.rfind(b") ") + 2 :].split()
        return fields[0].decode("ascii"), int(fields[19])
    except (FileNotFoundError, PermissionError, IndexError, UnicodeDecodeError, ValueError):
        return None


def process_start_ticks(pid: int) -> int | None:
    observed = linux_process_stat(pid)
    return observed[1] if observed is not None else None


def observe_process(pid: int, expected_start_ticks: int | None) -> dict[str, Any]:
    if sys.platform.startswith("linux"):
        observed = linux_process_stat(pid)
        if observed is None:
            return {
                "alive": False,
                "check": "linux_proc_stat",
                "identity_verified": False,
                "reason": "proc_stat_unavailable",
            }
        state, start_ticks = observed
        value: dict[str, Any] = {
            "alive": state not in {"Z", "X"},
            "check": "linux_proc_stat",
            "identity_verified": False,
            "proc_state": state,
            "observed_start_ticks": start_ticks,
        }
        if state in {"Z", "X"}:
            value["reason"] = "zombie"
        elif expected_start_ticks is None:
            value["reason"] = "start_ticks_unavailable"
        elif start_ticks != expected_start_ticks:
            value.update({"alive": False, "reason": "start_ticks_mismatch"})
        else:
            value.update({"identity_verified": True, "reason": "active"})
        return value

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        alive = False
    except PermissionError:
        alive = True
    else:
        alive = True
    return {
        "alive": alive,
        "check": "signal_only",
        "identity_verified": False,
        "reason": "active_unverified" if alive else "process_missing",
    }


def state_value(state_dir: Path) -> str:
    try:
        return (state_dir / "state").read_text(encoding="utf-8").strip()
    except OSError:
        return "UNKNOWN"


def write_heartbeat(state_dir: Path, sample_count: int, state: str) -> None:
    atomic_json(
        state_dir / "heartbeat.json",
        {"schema_version": 1, "state": state, "sample_count": sample_count, "observed_at": utc_now()},
    )


def worker(config_path: Path, state_dir: Path, output: Path) -> int:
    global stop_requested

    config_path = absolute_path_without_resolving(config_path)
    output = absolute_path_without_resolving(output)

    def request_stop(_signum: int, _frame: Any) -> None:
        global stop_requested
        stop_requested = True

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    started_at = utc_now()
    started_monotonic_ns = time.monotonic_ns()
    counts = {"observed": 0, "unavailable": 0, "failed": 0}
    sample_count = 0
    output_bytes = 0
    max_telemetry_bytes = DEFAULT_MAX_TELEMETRY_BYTES
    try:
        config, raw = load_config(config_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        if os.path.lexists(output):
            raise SamplerError("telemetry output already exists")
        worker_pid = os.getpid()
        worker_start_ticks = process_start_ticks(worker_pid)
        if worker_start_ticks is not None:
            atomic_text(state_dir / "worker.start_ticks", f"{worker_start_ticks}\n")
        atomic_text(state_dir / "pid", f"{worker_pid}\n")
        atomic_text(state_dir / "state", "RUNNING\n")
        atomic_json(
            state_dir / "metadata.json",
            {
                "schema_version": 1,
                "sampler_id": config["sampler_id"],
                "sampler_version": SAMPLER_VERSION,
                "config_sha256": sha256_bytes(raw),
                "tool_sha256": sha256_file(Path(__file__).resolve()),
                "started_at": started_at,
                "started_monotonic_ns": started_monotonic_ns,
                "max_telemetry_bytes": int(config.get("max_telemetry_bytes", DEFAULT_MAX_TELEMETRY_BYTES)),
            },
        )
        interval = float(config["interval_seconds"])
        next_sample = time.monotonic()
        max_telemetry_bytes = int(config.get("max_telemetry_bytes", DEFAULT_MAX_TELEMETRY_BYTES))
        with output.open("xb") as output_handle:
            os.chmod(output, 0o600)
            for sample_index in range(int(config["max_samples"])):
                if stop_requested or (state_dir / "stop.requested").exists():
                    break
                delay = next_sample - time.monotonic()
                if delay > 0:
                    time.sleep(delay)
                observed_at = utc_now()
                observed_monotonic_ns = time.monotonic_ns()
                probes: list[dict[str, Any]] = []
                for probe in config["probes"]:
                    result = bounded_command(probe, config)
                    counts[result["status"]] += 1
                    probes.append(result)
                output_bytes = append_jsonl(
                    output_handle,
                    {
                        "schema_version": 1,
                        "sampler_id": config["sampler_id"],
                        "sample_index": sample_index,
                        "observed_at": observed_at,
                        "monotonic_ns": observed_monotonic_ns,
                        "elapsed_seconds": round((observed_monotonic_ns - started_monotonic_ns) / 1_000_000_000, 9),
                        "probes": probes,
                    },
                    output_bytes,
                    max_telemetry_bytes,
                )
                sample_count = sample_index + 1
                write_heartbeat(state_dir, sample_count, "RUNNING")
                next_sample += interval
        terminal_state = "STOPPED" if stop_requested or (state_dir / "stop.requested").exists() else "COMPLETED"
        finished_at = utc_now()
        finished_monotonic_ns = time.monotonic_ns()
        if not direct_regular_file(output):
            raise SamplerError("telemetry output is not a regular file")
        summary = {
            "schema_version": 1,
            "sampler_id": config["sampler_id"],
            "state": terminal_state,
            "started_at": started_at,
            "finished_at": finished_at,
            "elapsed_seconds": round((finished_monotonic_ns - started_monotonic_ns) / 1_000_000_000, 9),
            "sample_count": sample_count,
            "probe_outcome_counts": counts,
            "output_bytes": output_bytes,
            "max_telemetry_bytes": max_telemetry_bytes,
            "output_sha256": sha256_file(output),
        }
        atomic_json(state_dir / "summary.json", summary)
        write_heartbeat(state_dir, sample_count, terminal_state)
        atomic_text(state_dir / "state", terminal_state + "\n")
        return 0
    except Exception as exc:
        finished_at = utc_now()
        output_is_regular = direct_regular_file(output)
        actual_output_bytes = output.stat().st_size if output_is_regular else 0
        atomic_json(
            state_dir / "summary.json",
            {
                "schema_version": 1,
                "state": "FAILED",
                "started_at": started_at,
                "finished_at": finished_at,
                "elapsed_seconds": round((time.monotonic_ns() - started_monotonic_ns) / 1_000_000_000, 9),
                "sample_count": sample_count,
                "probe_outcome_counts": counts,
                "output_bytes": actual_output_bytes,
                "max_telemetry_bytes": max_telemetry_bytes,
                "output_sha256": sha256_file(output) if output_is_regular else None,
                "error_code": (
                    "telemetry_output_limit_exceeded"
                    if isinstance(exc, TelemetryOutputLimit)
                    else "sampler_error"
                ),
                "error_type": type(exc).__name__,
                "error": str(exc),
            },
        )
        write_heartbeat(state_dir, sample_count, "FAILED")
        atomic_text(state_dir / "state", "FAILED\n")
        return 1


def start(config_path: Path, state_dir: Path, output: Path) -> dict[str, Any]:
    config_path = absolute_path_without_resolving(config_path)
    output = absolute_path_without_resolving(output)
    config, raw = load_config(config_path)
    if os.path.lexists(output):
        raise SamplerError("telemetry output already exists")
    try:
        state_dir.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        raise SamplerError("state directory already exists; use status or a fresh directory") from exc
    snapshot = state_dir / "config.json"
    snapshot.write_bytes(raw)
    os.chmod(snapshot, 0o400)
    atomic_text(state_dir / "state", "STARTING\n")
    log = (state_dir / "sampler.log").open("ab")
    try:
        process = subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "_worker", "--config", str(snapshot), "--state-dir", str(state_dir.resolve()), "--output", str(output)],
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            close_fds=True,
            start_new_session=(os.name == "posix"),
        )
    finally:
        log.close()
    launcher_start_ticks = process_start_ticks(process.pid)
    if launcher_start_ticks is not None:
        atomic_text(state_dir / "launcher.start_ticks", f"{launcher_start_ticks}\n")
    atomic_text(state_dir / "launcher.pid", f"{process.pid}\n")
    return {
        "status": "STARTED",
        "sampler_id": config["sampler_id"],
        "config_sha256": sha256_bytes(raw),
        "pid": process.pid,
    }


def status(state_dir: Path) -> dict[str, Any]:
    state = state_value(state_dir)
    pid: int | None = None
    pid_source: str | None = None
    expected_start_ticks: int | None = None
    for name, ticks_name in (("pid", "worker.start_ticks"), ("launcher.pid", "launcher.start_ticks")):
        try:
            pid = int((state_dir / name).read_text(encoding="utf-8").strip())
            pid_source = name
            try:
                expected_start_ticks = int((state_dir / ticks_name).read_text(encoding="utf-8").strip())
            except (OSError, ValueError):
                expected_start_ticks = None
            break
        except (OSError, ValueError):
            pass
    observation = (
        observe_process(pid, expected_start_ticks)
        if pid is not None
        else {
            "alive": False,
            "check": "linux_proc_stat" if sys.platform.startswith("linux") else "signal_only",
            "identity_verified": False,
            "reason": "pid_unavailable",
        }
    )
    effective = state
    if state in {"STARTING", "RUNNING"} and not observation["alive"]:
        effective = "INTERRUPTED"
    value: dict[str, Any] = {
        "status": effective,
        "recorded_state": state,
        "process_alive": observation["alive"],
        "process_check": observation["check"],
        "process_identity_verified": observation["identity_verified"],
        "process_identity_reason": observation["reason"],
    }
    if pid_source is not None:
        value["process_pid_source"] = pid_source
    if "proc_state" in observation:
        value["process_proc_state"] = observation["proc_state"]
    if "observed_start_ticks" in observation:
        value["process_observed_start_ticks"] = observation["observed_start_ticks"]
    for name in ("heartbeat.json", "summary.json"):
        path = state_dir / name
        if path.is_file():
            try:
                value[name.removesuffix(".json")] = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                value[name.removesuffix(".json")] = {"status": "unreadable"}
    return value


def stop(state_dir: Path, wait_seconds: float) -> dict[str, Any]:
    if not state_dir.is_dir():
        raise SamplerError("state directory does not exist")
    atomic_text(state_dir / "stop.requested", utc_now() + "\n")
    deadline = time.monotonic() + wait_seconds
    value = status(state_dir)
    while value["status"] not in TERMINAL_STATES | {"INTERRUPTED"} and time.monotonic() < deadline:
        time.sleep(0.05)
        value = status(state_dir)
    if value["status"] not in TERMINAL_STATES | {"INTERRUPTED"}:
        value["status"] = "STOP_REQUESTED"
    return value


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Run bounded telemetry commands from an argv-only JSON contract")
    subparsers = root.add_subparsers(dest="action", required=True)
    start_parser = subparsers.add_parser("start")
    start_parser.add_argument("--config", required=True, type=Path)
    start_parser.add_argument("--state-dir", required=True, type=Path)
    start_parser.add_argument("--output", required=True, type=Path)
    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("--state-dir", required=True, type=Path)
    stop_parser = subparsers.add_parser("stop")
    stop_parser.add_argument("--state-dir", required=True, type=Path)
    stop_parser.add_argument("--wait-seconds", type=float, default=10.0)
    worker_parser = subparsers.add_parser("_worker")
    worker_parser.add_argument("--config", required=True, type=Path)
    worker_parser.add_argument("--state-dir", required=True, type=Path)
    worker_parser.add_argument("--output", required=True, type=Path)
    return root


def main() -> int:
    args = parser().parse_args()
    try:
        if args.action == "start":
            value = start(args.config, args.state_dir, args.output)
        elif args.action == "status":
            value = status(args.state_dir)
        elif args.action == "stop":
            if not math.isfinite(args.wait_seconds) or args.wait_seconds < 0:
                raise SamplerError("--wait-seconds must be non-negative")
            value = stop(args.state_dir, args.wait_seconds)
        else:
            return worker(args.config, args.state_dir, args.output)
    except (OSError, SamplerError) as exc:
        print(json.dumps({"status": "ERROR", "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 1
    print(json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False))
    if args.action == "stop" and value.get("status") in {"STOP_REQUESTED", "INTERRUPTED"}:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
