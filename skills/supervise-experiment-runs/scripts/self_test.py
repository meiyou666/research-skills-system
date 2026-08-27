#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def linux_process_stat(pid: int) -> tuple[str, int]:
    raw = Path(f"/proc/{pid}/stat").read_bytes()
    fields = raw[raw.rfind(b") ") + 2 :].split()
    return fields[0].decode("ascii"), int(fields[19])


def write_execution_fixture(root: Path, results: Path, run_id: str, required: list[str]) -> Path:
    run_dir = root / f"{run_id}-evidence"
    run_dir.mkdir()
    launch_sha = "a" * 64
    validation_sha = "b" * 64
    progress_file = str((root / f"{run_id}-progress.jsonl").resolve())
    evidence = {
        "state": "SUCCEEDED",
        "run.id": run_id,
        "work.dir": str(root.resolve()),
        "launch.exit_code": "0",
        "validation.exit_code": "0",
        "launch.sha256": launch_sha,
        "validation.sha256": validation_sha,
        "maximum_runtime_seconds": "3600",
        "validation_timeout_seconds": "300",
        "no_progress_seconds": "300",
        "heartbeat_seconds": "30",
        "progress.file": progress_file,
        "started_at": "2026-01-01T00:00:00Z",
        "finished_at": "2026-01-01T00:01:00Z",
    }
    for name, value in evidence.items():
        (run_dir / name).write_text(f"{value}\n", encoding="utf-8")
    record = {
        "schema_version": 1,
        "run_id": run_id,
        "project_revision": "fixture-revision",
        "environment_validation_sha256": "c" * 64,
        "remote_work_dir": str(root.resolve()),
        "remote_run_dir": str(run_dir.resolve()),
        "remote_result_dir": str(results.resolve()),
        "launch_script_sha256": launch_sha,
        "validation_script_sha256": validation_sha,
        "required_results": required,
        "progress_source": progress_file,
        "heartbeat_seconds": 30,
        "no_progress_seconds": 300,
        "maximum_runtime_seconds": 3600,
        "validation_timeout_seconds": 300,
        "recovery_entry_point": "fixture-resume",
    }
    record_path = root / f"{run_id}-execution-record.json"
    record_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return record_path


def run(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(args, text=True, capture_output=True)
    if check and result.returncode != 0:
        raise AssertionError(f"command failed ({result.returncode}): {' '.join(args)}\n{result.stdout}\n{result.stderr}")
    return result


def test_ssh_config(root: Path) -> None:
    known_hosts = root / "connection" / "known_hosts"
    command = (
        "bash",
        str(SCRIPT_DIR / "ssh_session.sh"),
        "config",
        "--host",
        "192.0.2.1",
        "--user",
        "fixture",
        "--known-hosts",
        str(known_hosts),
    )
    first = run(*command).stdout
    assert "port 22" in first
    assert "hostkeyalias [192.0.2.1]:22" in first
    assert "batchmode no" in first
    assert "hostkeymode accept-new" in first
    assert "connectionroute direct" in first
    known_hosts.write_text("[192.0.2.1]:22 ssh-ed25519 AAAA\n", encoding="utf-8")
    later = run(*command).stdout
    assert "hostkeymode pinned" in later

    poisoned_home = root / "poisoned-home"
    (poisoned_home / ".ssh").mkdir(parents=True)
    (poisoned_home / ".ssh" / "config").write_text(
        "Host 192.0.2.1\n  HostName 203.0.113.9\n  User redirected\n  ForwardAgent yes\n",
        encoding="utf-8",
    )
    poisoned_environment = os.environ.copy()
    poisoned_environment["HOME"] = str(poisoned_home)
    bound = subprocess.run(command, text=True, capture_output=True, env=poisoned_environment)
    assert bound.returncode == 0
    assert "hostname 192.0.2.1" in bound.stdout
    assert "user fixture" in bound.stdout
    assert "203.0.113.9" not in bound.stdout

    alternate_port = run(*command[:-2], "--port", "2222", "--known-hosts", str(known_hosts)).stdout
    assert "port 2222" in alternate_port
    assert "hostkeyalias [192.0.2.1]:2222" in alternate_port
    assert "hostkeymode accept-new" in alternate_port

    source = root / "upload-source.txt"
    source.write_text("fixture\n", encoding="utf-8")
    invalid_upload = run(
        "bash",
        str(SCRIPT_DIR / "ssh_session.sh"),
        "upload",
        "--host",
        "192.0.2.1",
        "--user",
        "fixture",
        "--known-hosts",
        str(known_hosts),
        "--source",
        str(source),
        "--destination",
        "/tmp/./invalid",
        check=False,
    )
    assert invalid_upload.returncode != 0 and "normalized absolute path" in invalid_upload.stderr


def test_inspection() -> None:
    result = run("bash", str(SCRIPT_DIR / "inspect_server.sh"))
    for marker in ("[system]", "[cpu]", "[memory]", "[storage]", "[gpu]", "[tools]", "[network_configuration]"):
        assert marker in result.stdout


def wait_for_state(run_dir: Path, expected: str, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state_path = run_dir / "state"
        if state_path.exists() and state_path.read_text(encoding="utf-8").strip() == expected:
            return
        time.sleep(0.05)
    raise AssertionError(f"run did not reach {expected}")


def wait_for_sampler(state_dir: Path, expected: str, timeout: float = 10.0) -> dict[str, object]:
    deadline = time.monotonic() + timeout
    last: dict[str, object] = {}
    while time.monotonic() < deadline:
        result = run(
            sys.executable,
            str(SCRIPT_DIR / "telemetry_sampler.py"),
            "status",
            "--state-dir",
            str(state_dir),
            check=False,
        )
        if result.returncode == 0:
            last = json.loads(result.stdout)
            if last.get("status") == expected:
                return last
        time.sleep(0.05)
    raise AssertionError(f"telemetry sampler did not reach {expected}: {last}")


def test_telemetry_sampler(root: Path) -> None:
    helper = root / "telemetry-probe.py"
    helper.write_text(
        """import json
import os
import subprocess
import sys

mode = sys.argv[1]
if mode == "observed":
    print(json.dumps({"temperature_c": 47.5, "availability": "observed"}, sort_keys=True))
elif mode == "failed":
    print("probe failure", file=sys.stderr)
    raise SystemExit(7)
elif mode == "flood":
    chunk = b"x" * 32768
    while True:
        os.write(sys.stdout.fileno(), chunk)
        os.write(sys.stderr.fileno(), chunk)
elif mode == "inherited-pipe":
    subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
else:
    raise SystemExit(2)
""",
        encoding="utf-8",
    )
    config = {
        "schema_version": 1,
        "sampler_id": "offline-fixture",
        "interval_seconds": 0.05,
        "command_timeout_seconds": 1,
        "max_samples": 3,
        "max_output_bytes": 4096,
        "environment_allowlist": ["PATH"],
        "probes": [
            {"id": "observed", "argv": [sys.executable, str(helper), "observed"], "format": "json"},
            {"id": "unavailable", "argv": [str(root / "absent-telemetry-tool")], "format": "text"},
            {"id": "failed", "argv": [sys.executable, str(helper), "failed"], "format": "text"},
        ],
    }
    config_path = root / "telemetry-config.json"
    config_path.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    protected_output_target = root / "protected-telemetry-target.jsonl"
    protected_output_bytes = b"protected telemetry bytes\n"
    protected_output_target.write_bytes(protected_output_bytes)
    linked_output = root / "linked-telemetry-output.jsonl"
    linked_output.symlink_to(protected_output_target)
    linked_output_state = root / "linked-output-state"
    linked_output_rejected = run(
        sys.executable,
        str(SCRIPT_DIR / "telemetry_sampler.py"),
        "start",
        "--config",
        str(config_path),
        "--state-dir",
        str(linked_output_state),
        "--output",
        str(linked_output),
        check=False,
    )
    assert linked_output_rejected.returncode != 0 and "output already exists" in linked_output_rejected.stderr
    assert linked_output.is_symlink()
    assert protected_output_target.read_bytes() == protected_output_bytes
    assert not linked_output_state.exists()

    dangling_output_target = root / "absent-telemetry-target.jsonl"
    dangling_output = root / "dangling-telemetry-output.jsonl"
    dangling_output.symlink_to(dangling_output_target)
    dangling_output_state = root / "dangling-output-state"
    dangling_output_rejected = run(
        sys.executable,
        str(SCRIPT_DIR / "telemetry_sampler.py"),
        "start",
        "--config",
        str(config_path),
        "--state-dir",
        str(dangling_output_state),
        "--output",
        str(dangling_output),
        check=False,
    )
    assert dangling_output_rejected.returncode != 0 and "output already exists" in dangling_output_rejected.stderr
    assert dangling_output.is_symlink()
    assert not dangling_output_target.exists()
    assert not dangling_output_state.exists()

    worker_symlink_state = root / "worker-symlink-state"
    worker_symlink_state.mkdir()
    worker_symlink_rejected = run(
        sys.executable,
        str(SCRIPT_DIR / "telemetry_sampler.py"),
        "_worker",
        "--config",
        str(config_path),
        "--state-dir",
        str(worker_symlink_state),
        "--output",
        str(dangling_output),
        check=False,
    )
    assert worker_symlink_rejected.returncode != 0
    worker_symlink_summary = json.loads((worker_symlink_state / "summary.json").read_text(encoding="utf-8"))
    assert worker_symlink_summary["state"] == "FAILED"
    assert worker_symlink_summary["error"] == "telemetry output already exists"
    assert worker_symlink_summary["output_bytes"] == 0
    assert worker_symlink_summary["output_sha256"] is None
    assert dangling_output.is_symlink()
    assert not dangling_output_target.exists()

    linked_config = root / "linked-telemetry-config.json"
    linked_config.symlink_to(config_path)
    linked_config_output = root / "linked-config-output.jsonl"
    linked_config_state = root / "linked-config-state"
    original_config_bytes = config_path.read_bytes()
    linked_config_rejected = run(
        sys.executable,
        str(SCRIPT_DIR / "telemetry_sampler.py"),
        "start",
        "--config",
        str(linked_config),
        "--state-dir",
        str(linked_config_state),
        "--output",
        str(linked_config_output),
        check=False,
    )
    assert linked_config_rejected.returncode != 0 and "config must be a regular file" in linked_config_rejected.stderr
    assert linked_config.is_symlink()
    assert config_path.read_bytes() == original_config_bytes
    assert not linked_config_output.exists()
    assert not linked_config_state.exists()

    worker_linked_config_state = root / "worker-linked-config-state"
    worker_linked_config_state.mkdir()
    worker_linked_config_output = root / "worker-linked-config-output.jsonl"
    worker_linked_config_rejected = run(
        sys.executable,
        str(SCRIPT_DIR / "telemetry_sampler.py"),
        "_worker",
        "--config",
        str(linked_config),
        "--state-dir",
        str(worker_linked_config_state),
        "--output",
        str(worker_linked_config_output),
        check=False,
    )
    assert worker_linked_config_rejected.returncode != 0
    worker_linked_config_summary = json.loads(
        (worker_linked_config_state / "summary.json").read_text(encoding="utf-8")
    )
    assert worker_linked_config_summary["state"] == "FAILED"
    assert worker_linked_config_summary["error"] == "config must be a regular file"
    assert config_path.read_bytes() == original_config_bytes
    assert not worker_linked_config_output.exists()

    if hasattr(os, "mkfifo"):
        special_output = root / "special-telemetry-output"
        os.mkfifo(special_output)
        special_output_state = root / "special-output-state"
        special_output_rejected = run(
            sys.executable,
            str(SCRIPT_DIR / "telemetry_sampler.py"),
            "start",
            "--config",
            str(config_path),
            "--state-dir",
            str(special_output_state),
            "--output",
            str(special_output),
            check=False,
        )
        assert special_output_rejected.returncode != 0 and "output already exists" in special_output_rejected.stderr
        assert stat.S_ISFIFO(special_output.lstat().st_mode)
        assert not special_output_state.exists()

    state_dir = root / "telemetry-state"
    output = root / "telemetry.jsonl"
    started = run(
        sys.executable,
        str(SCRIPT_DIR / "telemetry_sampler.py"),
        "start",
        "--config",
        str(config_path),
        "--state-dir",
        str(state_dir),
        "--output",
        str(output),
    )
    assert json.loads(started.stdout)["status"] == "STARTED"
    terminal = wait_for_sampler(state_dir, "COMPLETED")
    assert terminal["heartbeat"]["sample_count"] == 3
    records = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert len(records) == 3
    monotonic_values = [record["monotonic_ns"] for record in records]
    assert monotonic_values == sorted(monotonic_values) and len(set(monotonic_values)) == len(monotonic_values)
    assert all(record["elapsed_seconds"] >= 0 for record in records)
    for record in records:
        outcomes = {probe["id"]: probe for probe in record["probes"]}
        assert outcomes["observed"]["status"] == "observed"
        assert outcomes["observed"]["value"]["temperature_c"] == 47.5
        assert outcomes["unavailable"]["status"] == "unavailable"
        assert outcomes["failed"]["status"] == "failed"
        assert "stderr_excerpt" not in outcomes["failed"]
    summary = json.loads((state_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["probe_outcome_counts"] == {"failed": 3, "observed": 3, "unavailable": 3}
    assert summary["output_sha256"] == sha256_file(output)

    flood_config = dict(config)
    flood_config.update(
        {
            "sampler_id": "bounded-output-fixture",
            "max_samples": 1,
            "max_output_bytes": 1024,
            "max_telemetry_bytes": 1024 * 1024,
            "probes": [{"id": "flood", "argv": [sys.executable, str(helper), "flood"], "format": "text"}],
        }
    )
    flood_config_path = root / "telemetry-flood-config.json"
    flood_config_path.write_text(json.dumps(flood_config, sort_keys=True) + "\n", encoding="utf-8")
    flood_state = root / "telemetry-flood-state"
    flood_output = root / "telemetry-flood.jsonl"
    run(
        sys.executable,
        str(SCRIPT_DIR / "telemetry_sampler.py"),
        "start",
        "--config",
        str(flood_config_path),
        "--state-dir",
        str(flood_state),
        "--output",
        str(flood_output),
    )
    wait_for_sampler(flood_state, "COMPLETED")
    flood_record = json.loads(flood_output.read_text(encoding="utf-8"))
    flood_probe = flood_record["probes"][0]
    assert flood_probe["status"] == "failed" and flood_probe["reason"] == "output_limit_exceeded"
    assert flood_probe["output_truncated"] is True
    assert flood_probe["stdout_bytes"] + flood_probe["stderr_bytes"] == 1024

    inherited_config = dict(config)
    inherited_config.update(
        {
            "sampler_id": "inherited-pipe-fixture",
            "command_timeout_seconds": 0.2,
            "max_samples": 1,
            "probes": [
                {
                    "id": "inherited-pipe",
                    "argv": [sys.executable, str(helper), "inherited-pipe"],
                    "format": "text",
                }
            ],
        }
    )
    inherited_config_path = root / "telemetry-inherited-pipe-config.json"
    inherited_config_path.write_text(json.dumps(inherited_config, sort_keys=True) + "\n", encoding="utf-8")
    inherited_state = root / "telemetry-inherited-pipe-state"
    inherited_output = root / "telemetry-inherited-pipe.jsonl"
    run(
        sys.executable,
        str(SCRIPT_DIR / "telemetry_sampler.py"),
        "start",
        "--config",
        str(inherited_config_path),
        "--state-dir",
        str(inherited_state),
        "--output",
        str(inherited_output),
    )
    wait_for_sampler(inherited_state, "COMPLETED")
    inherited_record = json.loads(inherited_output.read_text(encoding="utf-8"))
    assert inherited_record["probes"][0]["reason"] == "timeout"

    cap_config = dict(config)
    cap_config.update(
        {
            "sampler_id": "jsonl-cap-fixture",
            "max_samples": 1,
            "max_telemetry_bytes": 64,
            "probes": [config["probes"][0]],
        }
    )
    cap_config_path = root / "telemetry-cap-config.json"
    cap_config_path.write_text(json.dumps(cap_config, sort_keys=True) + "\n", encoding="utf-8")
    cap_state = root / "telemetry-cap-state"
    cap_output = root / "telemetry-cap.jsonl"
    run(
        sys.executable,
        str(SCRIPT_DIR / "telemetry_sampler.py"),
        "start",
        "--config",
        str(cap_config_path),
        "--state-dir",
        str(cap_state),
        "--output",
        str(cap_output),
    )
    cap_terminal = wait_for_sampler(cap_state, "FAILED")
    assert cap_terminal["summary"]["error_code"] == "telemetry_output_limit_exceeded"
    assert cap_terminal["summary"]["output_bytes"] <= 64
    assert cap_output.stat().st_size <= 64

    stop_config = dict(config)
    stop_config["sampler_id"] = "stop-fixture"
    stop_config["max_samples"] = 1000
    stop_config["probes"] = [config["probes"][0]]
    stop_config_path = root / "telemetry-stop-config.json"
    stop_config_path.write_text(json.dumps(stop_config, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    stop_state = root / "telemetry-stop-state"
    run(
        sys.executable,
        str(SCRIPT_DIR / "telemetry_sampler.py"),
        "start",
        "--config",
        str(stop_config_path),
        "--state-dir",
        str(stop_state),
        "--output",
        str(root / "telemetry-stop.jsonl"),
    )
    running = wait_for_sampler(stop_state, "RUNNING")
    if sys.platform.startswith("linux"):
        sampler_pid = int((stop_state / "pid").read_text(encoding="utf-8").strip())
        launcher_pid = int((stop_state / "launcher.pid").read_text(encoding="utf-8").strip())
        worker_ticks = int((stop_state / "worker.start_ticks").read_text(encoding="utf-8").strip())
        launcher_ticks = int((stop_state / "launcher.start_ticks").read_text(encoding="utf-8").strip())
        assert sampler_pid == launcher_pid
        assert worker_ticks == launcher_ticks == linux_process_stat(sampler_pid)[1]
        assert running["process_check"] == "linux_proc_stat"
        assert running["process_identity_verified"] is True
    stopped = run(
        sys.executable,
        str(SCRIPT_DIR / "telemetry_sampler.py"),
        "stop",
        "--state-dir",
        str(stop_state),
        "--wait-seconds",
        "3",
    )
    assert json.loads(stopped.stdout)["status"] == "STOPPED"

    unsafe_config = dict(config)
    unsafe_config["sampler_id"] = "unsafe-fixture"
    unsafe_config["probes"] = [{"id": "unsafe", "argv": ["sh", "-c", "printf unsafe"], "format": "text"}]
    unsafe_path = root / "unsafe-telemetry-config.json"
    unsafe_path.write_text(json.dumps(unsafe_config, sort_keys=True) + "\n", encoding="utf-8")
    rejected = run(
        sys.executable,
        str(SCRIPT_DIR / "telemetry_sampler.py"),
        "start",
        "--config",
        str(unsafe_path),
        "--state-dir",
        str(root / "unsafe-state"),
        "--output",
        str(root / "unsafe.jsonl"),
        check=False,
    )
    assert rejected.returncode != 0 and "shell command string" in rejected.stderr

    secret_config = dict(config)
    secret_config["sampler_id"] = "secret-environment-fixture"
    secret_config["environment_allowlist"] = ["PATH", "GITHUB_TOKEN"]
    secret_path = root / "secret-telemetry-config.json"
    secret_path.write_text(json.dumps(secret_config, sort_keys=True) + "\n", encoding="utf-8")
    secret_rejected = run(
        sys.executable,
        str(SCRIPT_DIR / "telemetry_sampler.py"),
        "start",
        "--config",
        str(secret_path),
        "--state-dir",
        str(root / "secret-state"),
        "--output",
        str(root / "secret.jsonl"),
        check=False,
    )
    assert secret_rejected.returncode != 0 and "secret-shaped names" in secret_rejected.stderr

    oversized_config = dict(config)
    oversized_config["sampler_id"] = "oversized-jsonl-fixture"
    oversized_config["max_telemetry_bytes"] = 4 * 1024 * 1024 * 1024 + 1
    oversized_path = root / "oversized-telemetry-config.json"
    oversized_path.write_text(json.dumps(oversized_config, sort_keys=True) + "\n", encoding="utf-8")
    oversized_rejected = run(
        sys.executable,
        str(SCRIPT_DIR / "telemetry_sampler.py"),
        "start",
        "--config",
        str(oversized_path),
        "--state-dir",
        str(root / "oversized-state"),
        "--output",
        str(root / "oversized.jsonl"),
        check=False,
    )
    assert oversized_rejected.returncode != 0 and "max_telemetry_bytes must not exceed" in oversized_rejected.stderr

    if sys.platform.startswith("linux"):
        zombie = subprocess.Popen(["true"])
        deadline = time.monotonic() + 3
        zombie_state = ""
        while time.monotonic() < deadline:
            zombie_state, zombie_ticks = linux_process_stat(zombie.pid)
            if zombie_state == "Z":
                break
            time.sleep(0.01)
        assert zombie_state == "Z"
        for recorded_state, pid_name, ticks_name in (
            ("STARTING", "launcher.pid", "launcher.start_ticks"),
            ("RUNNING", "pid", "worker.start_ticks"),
        ):
            fixture = root / f"telemetry-zombie-{recorded_state.lower()}"
            fixture.mkdir()
            (fixture / "state").write_text(recorded_state + "\n", encoding="utf-8")
            (fixture / pid_name).write_text(f"{zombie.pid}\n", encoding="utf-8")
            (fixture / ticks_name).write_text(f"{zombie_ticks}\n", encoding="utf-8")
            observed = json.loads(
                run(
                    sys.executable,
                    str(SCRIPT_DIR / "telemetry_sampler.py"),
                    "status",
                    "--state-dir",
                    str(fixture),
                ).stdout
            )
            assert observed["status"] == "INTERRUPTED"
            assert observed["recorded_state"] == recorded_state
            assert observed["process_alive"] is False
            assert observed["process_proc_state"] == "Z"
            assert observed["process_identity_reason"] == "zombie"
        zombie.wait()

        current_pid = os.getpid()
        _current_state, current_ticks = linux_process_stat(current_pid)
        matching = root / "telemetry-matching-identity"
        matching.mkdir()
        (matching / "state").write_text("RUNNING\n", encoding="utf-8")
        (matching / "pid").write_text(f"{current_pid}\n", encoding="utf-8")
        (matching / "worker.start_ticks").write_text(f"{current_ticks}\n", encoding="utf-8")
        matching_status = json.loads(
            run(
                sys.executable,
                str(SCRIPT_DIR / "telemetry_sampler.py"),
                "status",
                "--state-dir",
                str(matching),
            ).stdout
        )
        assert matching_status["status"] == "RUNNING"
        assert matching_status["process_alive"] is True
        assert matching_status["process_identity_verified"] is True
        assert matching_status["process_identity_reason"] == "active"

        mismatched = root / "telemetry-mismatched-identity"
        mismatched.mkdir()
        (mismatched / "state").write_text("RUNNING\n", encoding="utf-8")
        (mismatched / "pid").write_text(f"{current_pid}\n", encoding="utf-8")
        (mismatched / "worker.start_ticks").write_text(f"{current_ticks + 1}\n", encoding="utf-8")
        mismatched_status = json.loads(
            run(
                sys.executable,
                str(SCRIPT_DIR / "telemetry_sampler.py"),
                "status",
                "--state-dir",
                str(mismatched),
            ).stdout
        )
        assert mismatched_status["status"] == "INTERRUPTED"
        assert mismatched_status["process_alive"] is False
        assert mismatched_status["process_identity_verified"] is False
        assert mismatched_status["process_identity_reason"] == "start_ticks_mismatch"

        launcher_mismatched = root / "telemetry-launcher-mismatched-identity"
        launcher_mismatched.mkdir()
        (launcher_mismatched / "state").write_text("STARTING\n", encoding="utf-8")
        (launcher_mismatched / "launcher.pid").write_text(f"{current_pid}\n", encoding="utf-8")
        (launcher_mismatched / "launcher.start_ticks").write_text(
            f"{current_ticks + 1}\n", encoding="utf-8"
        )
        launcher_mismatched_status = json.loads(
            run(
                sys.executable,
                str(SCRIPT_DIR / "telemetry_sampler.py"),
                "status",
                "--state-dir",
                str(launcher_mismatched),
            ).stdout
        )
        assert launcher_mismatched_status["status"] == "INTERRUPTED"
        assert launcher_mismatched_status["process_pid_source"] == "launcher.pid"
        assert launcher_mismatched_status["process_identity_reason"] == "start_ticks_mismatch"

    sampler_spec = importlib.util.spec_from_file_location(
        "telemetry_sampler_non_linux_test", SCRIPT_DIR / "telemetry_sampler.py"
    )
    assert sampler_spec is not None and sampler_spec.loader is not None
    sampler_module = importlib.util.module_from_spec(sampler_spec)
    sampler_spec.loader.exec_module(sampler_module)
    original_platform = sampler_module.sys.platform
    try:
        sampler_module.sys.platform = "non-linux-fixture"
        degraded = sampler_module.observe_process(os.getpid(), 1)
    finally:
        sampler_module.sys.platform = original_platform
    assert degraded["alive"] is True
    assert degraded["check"] == "signal_only"
    assert degraded["identity_verified"] is False
    assert degraded["reason"] == "active_unverified"


def test_runner(root: Path) -> None:
    preflight = run("bash", str(SCRIPT_DIR / "remote_runner.sh"), "preflight")
    assert "PREFLIGHT_OK" in preflight.stdout
    work = root / "work"
    run_dir = root / "run-success"
    work.mkdir()
    launch = root / "launch.sh"
    validate = root / "validate.sh"
    launch.write_text("set -euo pipefail\nprintf 'payload\\n' > result.txt\n", encoding="utf-8")
    validate.write_text("set -euo pipefail\ntest -s result.txt\n", encoding="utf-8")
    launch_sha256 = sha256_file(launch)
    validation_sha256 = sha256_file(validate)
    run(
        "bash",
        str(SCRIPT_DIR / "remote_runner.sh"),
        "start",
        "--run-id",
        "fixture-success",
        "--run-dir",
        str(run_dir),
        "--work-dir",
        str(work),
        "--launch-script",
        str(launch),
        "--validation-script",
        str(validate),
        "--expected-launch-sha256",
        launch_sha256,
        "--expected-validation-sha256",
        validation_sha256,
        "--maximum-runtime-seconds",
        "10",
        "--validation-timeout-seconds",
        "5",
        "--progress-file",
        str(work / "result.txt"),
        "--no-progress-seconds",
        "5",
        "--heartbeat-seconds",
        "1",
    )
    wait_for_state(run_dir, "SUCCEEDED")
    status = run("bash", str(SCRIPT_DIR / "remote_runner.sh"), "status", "--run-dir", str(run_dir)).stdout
    assert "state=SUCCEEDED" in status
    assert "run.id=fixture-success" in status
    assert f"work.dir={work.resolve()}" in status
    assert (run_dir / "launch.exit_code").read_text(encoding="utf-8").strip() == "0"
    assert (run_dir / "validation.exit_code").read_text(encoding="utf-8").strip() == "0"
    assert "unbound variable" not in (run_dir / "supervisor.log").read_text(encoding="utf-8")
    duplicate = run(
        "bash",
        str(SCRIPT_DIR / "remote_runner.sh"),
        "start",
        "--run-id",
        "fixture-success",
        "--run-dir",
        str(run_dir),
        "--work-dir",
        str(work),
        "--launch-script",
        str(launch),
        "--validation-script",
        str(validate),
        "--expected-launch-sha256",
        launch_sha256,
        "--expected-validation-sha256",
        validation_sha256,
        "--maximum-runtime-seconds",
        "10",
        "--validation-timeout-seconds",
        "5",
        "--progress-file",
        str(work / "result.txt"),
        "--no-progress-seconds",
        "5",
        check=False,
    )
    assert duplicate.returncode != 0

    telemetry_launch = root / "telemetry-launch.sh"
    telemetry_launch.write_text(
        "set -euo pipefail\nsleep 0.2\nprintf 'telemetry payload\\n' > telemetry-result.txt\n",
        encoding="utf-8",
    )
    telemetry_validate = root / "telemetry-validate.sh"
    telemetry_validate.write_text("set -euo pipefail\ntest -s telemetry-result.txt\n", encoding="utf-8")
    telemetry_probe = root / "runner-telemetry-probe.py"
    telemetry_probe.write_text("import json\nprint(json.dumps({'load': 0.5}, sort_keys=True))\n", encoding="utf-8")
    telemetry_config = root / "runner-telemetry-config.json"
    telemetry_config.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "sampler_id": "runner-fixture",
                "interval_seconds": 0.05,
                "command_timeout_seconds": 1,
                "max_samples": 100,
                "max_output_bytes": 4096,
                "environment_allowlist": ["PATH"],
                "probes": [{"id": "load", "argv": [sys.executable, str(telemetry_probe)], "format": "json"}],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    telemetry_run_dir = root / "run-with-telemetry"
    telemetry_output = work / "runner-telemetry.jsonl"
    run(
        "bash",
        str(SCRIPT_DIR / "remote_runner.sh"),
        "start",
        "--run-id",
        "fixture-telemetry",
        "--run-dir",
        str(telemetry_run_dir),
        "--work-dir",
        str(work),
        "--launch-script",
        str(telemetry_launch),
        "--validation-script",
        str(telemetry_validate),
        "--expected-launch-sha256",
        sha256_file(telemetry_launch),
        "--expected-validation-sha256",
        sha256_file(telemetry_validate),
        "--maximum-runtime-seconds",
        "10",
        "--validation-timeout-seconds",
        "5",
        "--progress-file",
        str(work / "telemetry-result.txt"),
        "--no-progress-seconds",
        "5",
        "--heartbeat-seconds",
        "1",
        "--telemetry-sampler",
        str(SCRIPT_DIR / "telemetry_sampler.py"),
        "--telemetry-config",
        str(telemetry_config),
        "--expected-telemetry-sampler-sha256",
        sha256_file(SCRIPT_DIR / "telemetry_sampler.py"),
        "--expected-telemetry-config-sha256",
        sha256_file(telemetry_config),
        "--telemetry-output",
        str(telemetry_output),
    )
    wait_for_state(telemetry_run_dir, "RUNNING")
    telemetry_worker_pid = int((telemetry_run_dir / "worker.pid").read_text(encoding="utf-8").strip())
    assert os.getsid(telemetry_worker_pid) == telemetry_worker_pid
    wait_for_state(telemetry_run_dir, "SUCCEEDED")
    assert (telemetry_run_dir / "telemetry.start_exit_code").read_text(encoding="utf-8").strip() == "0"
    assert (telemetry_run_dir / "telemetry.stop_exit_code").read_text(encoding="utf-8").strip() == "0"
    assert (telemetry_run_dir / "telemetry" / "state").read_text(encoding="utf-8").strip() in {"STOPPED", "COMPLETED"}
    assert telemetry_output.is_file() and telemetry_output.stat().st_size > 0
    telemetry_status = run(
        "bash", str(SCRIPT_DIR / "remote_runner.sh"), "status", "--run-dir", str(telemetry_run_dir)
    ).stdout
    assert "telemetry.state=" in telemetry_status and "telemetry.config_sha256=" in telemetry_status

    stale_dir = root / "run-stale"
    stale_dir.mkdir()
    (stale_dir / "state").write_text("RUNNING\n", encoding="utf-8")
    (stale_dir / "worker.pid").write_text("99999999\n", encoding="utf-8")
    stale = run("bash", str(SCRIPT_DIR / "remote_runner.sh"), "status", "--run-dir", str(stale_dir)).stdout
    assert "state=INTERRUPTED" in stale and "recorded_state=RUNNING" in stale

    live_start = root / "run-live-start"
    live_start.mkdir()
    (live_start / "state").write_text("STARTING\n", encoding="utf-8")
    current_pid = os.getpid()
    current_stat = Path(f"/proc/{current_pid}/stat").read_text(encoding="ascii").rsplit(") ", 1)[1].split()
    (live_start / "supervisor.pid").write_text(f"{current_pid}\n", encoding="utf-8")
    (live_start / "supervisor.start_ticks").write_text(f"{current_stat[19]}\n", encoding="utf-8")
    live_start_status = run(
        "bash", str(SCRIPT_DIR / "remote_runner.sh"), "status", "--run-dir", str(live_start)
    ).stdout
    assert "state=STARTING" in live_start_status and "launcher_process=present" in live_start_status

    interrupted_start = root / "run-interrupted-start"
    interrupted_start.mkdir()
    (interrupted_start / "state").write_text("STARTING\n", encoding="utf-8")
    (interrupted_start / "supervisor.pid").write_text(f"{current_pid}\n", encoding="utf-8")
    (interrupted_start / "supervisor.start_ticks").write_text(f"{current_stat[19]}\n", encoding="utf-8")
    (interrupted_start / "worker.pid").write_text("99999999\n", encoding="utf-8")
    interrupted = run(
        "bash", str(SCRIPT_DIR / "remote_runner.sh"), "status", "--run-dir", str(interrupted_start)
    ).stdout
    assert "state=INTERRUPTED" in interrupted and "recorded_state=STARTING" in interrupted

    fake_bin = root / "fake-bin"
    fake_bin.mkdir()
    fake_sha = fake_bin / "sha256sum"
    fake_sha.write_text("#!/usr/bin/env bash\nexit 42\n", encoding="utf-8")
    fake_sha.chmod(0o700)
    hash_failure_dir = root / "run-hash-failure"
    environment = os.environ.copy()
    environment["PATH"] = f"{fake_bin}:{environment['PATH']}"
    started = subprocess.run(
        (
            "bash",
            str(SCRIPT_DIR / "remote_runner.sh"),
            "start",
            "--run-id",
            "fixture-hash-failure",
            "--run-dir",
            str(hash_failure_dir),
            "--work-dir",
            str(work),
            "--launch-script",
            str(launch),
            "--validation-script",
            str(validate),
            "--expected-launch-sha256",
            launch_sha256,
            "--expected-validation-sha256",
            validation_sha256,
            "--maximum-runtime-seconds",
            "10",
            "--validation-timeout-seconds",
            "5",
            "--progress-file",
            str(work / "result.txt"),
            "--no-progress-seconds",
            "5",
        ),
        text=True,
        capture_output=True,
        env=environment,
    )
    assert started.returncode == 0
    wait_for_state(hash_failure_dir, "FAILED")
    assert not (hash_failure_dir / "launch.sha256").exists()

    hash_mismatch_dir = root / "run-hash-mismatch"
    run(
        "bash",
        str(SCRIPT_DIR / "remote_runner.sh"),
        "start",
        "--run-id",
        "fixture-hash-mismatch",
        "--run-dir",
        str(hash_mismatch_dir),
        "--work-dir",
        str(work),
        "--launch-script",
        str(launch),
        "--validation-script",
        str(validate),
        "--expected-launch-sha256",
        "0" * 64,
        "--expected-validation-sha256",
        validation_sha256,
        "--maximum-runtime-seconds",
        "10",
        "--validation-timeout-seconds",
        "5",
        "--progress-file",
        str(work / "result.txt"),
        "--no-progress-seconds",
        "5",
    )
    wait_for_state(hash_mismatch_dir, "FAILED")

    timeout_launch = root / "timeout-launch.sh"
    timeout_launch.write_text("sleep 5\n", encoding="utf-8")
    timeout_dir = root / "run-timeout"
    run(
        "bash",
        str(SCRIPT_DIR / "remote_runner.sh"),
        "start",
        "--run-id",
        "fixture-timeout",
        "--run-dir",
        str(timeout_dir),
        "--work-dir",
        str(work),
        "--launch-script",
        str(timeout_launch),
        "--validation-script",
        str(validate),
        "--expected-launch-sha256",
        sha256_file(timeout_launch),
        "--expected-validation-sha256",
        validation_sha256,
        "--maximum-runtime-seconds",
        "1",
        "--validation-timeout-seconds",
        "5",
        "--progress-file",
        str(work / "timeout-progress"),
        "--no-progress-seconds",
        "5",
        "--heartbeat-seconds",
        "1",
    )
    wait_for_state(timeout_dir, "TIMED_OUT", timeout=5)

    stalled_launch = root / "stalled-launch.sh"
    stalled_launch.write_text("sleep 10\n", encoding="utf-8")
    stalled_dir = root / "run-stalled"
    run(
        "bash",
        str(SCRIPT_DIR / "remote_runner.sh"),
        "start",
        "--run-id",
        "fixture-stalled",
        "--run-dir",
        str(stalled_dir),
        "--work-dir",
        str(work),
        "--launch-script",
        str(stalled_launch),
        "--validation-script",
        str(validate),
        "--expected-launch-sha256",
        sha256_file(stalled_launch),
        "--expected-validation-sha256",
        validation_sha256,
        "--maximum-runtime-seconds",
        "10",
        "--validation-timeout-seconds",
        "5",
        "--progress-file",
        str(work / "never-created-progress"),
        "--no-progress-seconds",
        "1",
        "--heartbeat-seconds",
        "1",
    )
    wait_for_state(stalled_dir, "STALLED", timeout=10)

    slow_validation = root / "slow-validation.sh"
    slow_validation.write_text("sleep 5\n", encoding="utf-8")
    validation_timeout_dir = root / "run-validation-timeout"
    run(
        "bash",
        str(SCRIPT_DIR / "remote_runner.sh"),
        "start",
        "--run-id",
        "fixture-validation-timeout",
        "--run-dir",
        str(validation_timeout_dir),
        "--work-dir",
        str(work),
        "--launch-script",
        str(launch),
        "--validation-script",
        str(slow_validation),
        "--expected-launch-sha256",
        launch_sha256,
        "--expected-validation-sha256",
        sha256_file(slow_validation),
        "--maximum-runtime-seconds",
        "10",
        "--validation-timeout-seconds",
        "1",
        "--progress-file",
        str(work / "result.txt"),
        "--no-progress-seconds",
        "5",
        "--heartbeat-seconds",
        "1",
    )
    wait_for_state(validation_timeout_dir, "FAILED", timeout=5)
    assert (validation_timeout_dir / "validation.exit_code").read_text(encoding="utf-8").strip() == "124"

    background_launch = root / "background-launch.sh"
    background_launch.write_text(
        "sleep 30 &\nprintf '%s\\n' \"$!\" > background.pid\nprintf 'payload\\n' > result.txt\n",
        encoding="utf-8",
    )
    residual_dir = root / "run-residual-process"
    run(
        "bash",
        str(SCRIPT_DIR / "remote_runner.sh"),
        "start",
        "--run-id",
        "fixture-residual-process",
        "--run-dir",
        str(residual_dir),
        "--work-dir",
        str(work),
        "--launch-script",
        str(background_launch),
        "--validation-script",
        str(validate),
        "--expected-launch-sha256",
        sha256_file(background_launch),
        "--expected-validation-sha256",
        validation_sha256,
        "--maximum-runtime-seconds",
        "10",
        "--validation-timeout-seconds",
        "5",
        "--progress-file",
        str(work / "result.txt"),
        "--no-progress-seconds",
        "5",
        "--heartbeat-seconds",
        "1",
    )
    wait_for_state(residual_dir, "FAILED", timeout=10)
    assert (residual_dir / "residual_processes").exists()
    assert (residual_dir / "validation.exit_code").read_text(encoding="utf-8").strip() == "125"
    background_pid = int((work / "background.pid").read_text(encoding="utf-8").strip())
    process_stat = Path(f"/proc/{background_pid}/stat")
    if process_stat.exists():
        process_state = process_stat.read_text(encoding="utf-8").split(") ", 1)[1].split(" ", 1)[0]
        assert process_state in {"Z", "X"}

    escaped_launch = root / "escaped-launch.sh"
    escaped_launch.write_text(
        "setsid env -u REMOTE_EXPERIMENT_RUN_TOKEN sleep 30 &\nprintf '%s\\n' \"$!\" > escaped.pid\nprintf 'payload\\n' > result.txt\n",
        encoding="utf-8",
    )
    escaped_dir = root / "run-escaped-process"
    run(
        "bash",
        str(SCRIPT_DIR / "remote_runner.sh"),
        "start",
        "--run-id",
        "fixture-escaped-process",
        "--run-dir",
        str(escaped_dir),
        "--work-dir",
        str(work),
        "--launch-script",
        str(escaped_launch),
        "--validation-script",
        str(validate),
        "--expected-launch-sha256",
        sha256_file(escaped_launch),
        "--expected-validation-sha256",
        validation_sha256,
        "--maximum-runtime-seconds",
        "10",
        "--validation-timeout-seconds",
        "5",
        "--progress-file",
        str(work / "result.txt"),
        "--no-progress-seconds",
        "5",
        "--heartbeat-seconds",
        "1",
    )
    wait_for_state(escaped_dir, "FAILED", timeout=10)
    assert (escaped_dir / "residual_processes").exists()
    escaped_pid = int((work / "escaped.pid").read_text(encoding="utf-8").strip())
    escaped_stat = Path(f"/proc/{escaped_pid}/stat")
    if escaped_stat.exists():
        escaped_state = escaped_stat.read_text(encoding="utf-8").split(") ", 1)[1].split(" ", 1)[0]
        assert escaped_state in {"Z", "X"}


def test_manifest(root: Path) -> None:
    results = root / "results"
    (results / "nested").mkdir(parents=True)
    (results / "empty").mkdir()
    (results / "records.jsonl").write_text('{"step":1}\n', encoding="utf-8")
    (results / "nested" / "value.bin").write_bytes(b"\x00\x01\x02")
    manifest = root / "manifest.json"
    report = root / "verification.json"
    execution_record = write_execution_fixture(root, results, "fixture-r1", ["records.jsonl", "nested", "empty"])
    run(
        "python3",
        str(SCRIPT_DIR / "build_result_manifest.py"),
        "--root",
        str(results),
        "--execution-record",
        str(execution_record),
        "--output",
        str(manifest),
    )
    duplicate_manifest = root / "manifest-duplicate.json"
    run(
        "python3",
        str(SCRIPT_DIR / "build_result_manifest.py"),
        "--root",
        str(results),
        "--execution-record",
        str(execution_record),
        "--output",
        str(duplicate_manifest),
    )
    assert manifest.read_bytes() == duplicate_manifest.read_bytes()
    manifest_value = json.loads(manifest.read_text(encoding="utf-8"))
    assert manifest_value["created_at"] == "2026-01-01T00:01:00Z"
    assert manifest_value["created_at_source"] == "run_evidence.finished_at"

    override_manifest = root / "manifest-override.json"
    run(
        "python3",
        str(SCRIPT_DIR / "build_result_manifest.py"),
        "--root",
        str(results),
        "--execution-record",
        str(execution_record),
        "--output",
        str(override_manifest),
        "--created-at",
        "2026-01-01T03:01:00+03:00",
    )
    override_value = json.loads(override_manifest.read_text(encoding="utf-8"))
    assert override_value["created_at"] == "2026-01-01T00:01:00Z"
    assert override_value["created_at_source"] == "caller"

    telemetry_results = root / "telemetry-results"
    telemetry_results.mkdir()
    (telemetry_results / "payload.txt").write_text("payload\n", encoding="utf-8")
    telemetry_output = telemetry_results / "telemetry.jsonl"
    telemetry_output.write_text('{"sample":0}\n', encoding="utf-8")
    telemetry_base_record = write_execution_fixture(
        root,
        telemetry_results,
        "fixture-telemetry-manifest",
        ["payload.txt", "telemetry.jsonl"],
    )
    telemetry_record_value = json.loads(telemetry_base_record.read_text(encoding="utf-8"))
    telemetry_record_value["telemetry"] = {
        "sampler_sha256": "d" * 64,
        "config_sha256": "e" * 64,
        "output": str(telemetry_output.resolve()),
        "required": True,
    }
    telemetry_record = root / "telemetry-execution-record.json"
    telemetry_record.write_text(json.dumps(telemetry_record_value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    telemetry_run_dir = Path(telemetry_record_value["remote_run_dir"])
    (telemetry_run_dir / "telemetry").mkdir()
    for name, value in {
        "telemetry.sampler_sha256": "d" * 64,
        "telemetry.config_sha256": "e" * 64,
        "telemetry.output": str(telemetry_output.resolve()),
        "telemetry.start_exit_code": "0",
        "telemetry.stop_exit_code": "0",
    }.items():
        (telemetry_run_dir / name).write_text(value + "\n", encoding="utf-8")
    (telemetry_run_dir / "telemetry" / "state").write_text("STOPPED\n", encoding="utf-8")
    telemetry_manifest = root / "manifest-telemetry.json"
    run(
        "python3",
        str(SCRIPT_DIR / "build_result_manifest.py"),
        "--root",
        str(telemetry_results),
        "--execution-record",
        str(telemetry_record),
        "--output",
        str(telemetry_manifest),
    )
    telemetry_manifest_value = json.loads(telemetry_manifest.read_text(encoding="utf-8"))
    assert telemetry_manifest_value["run_evidence"]["telemetry.state"] == "STOPPED"
    telemetry_verification = run(
        "python3",
        str(SCRIPT_DIR / "verify_result_manifest.py"),
        "--root",
        str(telemetry_results),
        "--manifest",
        str(telemetry_manifest),
        "--execution-record",
        str(telemetry_record),
    )
    assert json.loads(telemetry_verification.stdout)["status"] == "VERIFIED"

    telemetry_output.unlink()
    missing_telemetry = run(
        "python3",
        str(SCRIPT_DIR / "build_result_manifest.py"),
        "--root",
        str(telemetry_results),
        "--execution-record",
        str(telemetry_record),
        "--output",
        str(root / "manifest-missing-telemetry.json"),
        check=False,
    )
    assert missing_telemetry.returncode != 0
    assert "required telemetry output is missing" in missing_telemetry.stderr
    telemetry_output.write_text('{"sample":0}\n', encoding="utf-8")

    telemetry_state_path = telemetry_run_dir / "telemetry" / "state"
    telemetry_state_path.unlink()
    missing_telemetry_state = run(
        "python3",
        str(SCRIPT_DIR / "build_result_manifest.py"),
        "--root",
        str(telemetry_results),
        "--execution-record",
        str(telemetry_record),
        "--output",
        str(root / "manifest-missing-telemetry-state.json"),
        check=False,
    )
    assert missing_telemetry_state.returncode != 0
    assert "run evidence is missing or not a regular file: telemetry.state" in missing_telemetry_state.stderr
    telemetry_state_path.write_text("STOPPED\n", encoding="utf-8")

    verification = run(
        "python3",
        str(SCRIPT_DIR / "verify_result_manifest.py"),
        "--root",
        str(results),
        "--manifest",
        str(manifest),
        "--execution-record",
        str(execution_record),
        "--report",
        str(report),
    )
    assert json.loads(verification.stdout)["status"] == "VERIFIED"
    assert json.loads(report.read_text(encoding="utf-8"))["file_count"] == 2
    assert json.loads(report.read_text(encoding="utf-8"))["directory_count"] == 2

    missing_recovery = json.loads(execution_record.read_text(encoding="utf-8"))
    del missing_recovery["recovery_entry_point"]
    missing_recovery_path = root / "missing-recovery-execution-record.json"
    missing_recovery_path.write_text(json.dumps(missing_recovery, sort_keys=True) + "\n", encoding="utf-8")
    rejected_recovery = run(
        "python3",
        str(SCRIPT_DIR / "build_result_manifest.py"),
        "--root",
        str(results),
        "--execution-record",
        str(missing_recovery_path),
        "--output",
        str(root / "missing-recovery-manifest.json"),
        check=False,
    )
    assert rejected_recovery.returncode != 0 and "recovery_entry_point" in rejected_recovery.stderr

    wrong_record = json.loads(execution_record.read_text(encoding="utf-8"))
    wrong_record["run_id"] = "another-run"
    wrong_record_path = root / "wrong-execution-record.json"
    wrong_record_path.write_text(json.dumps(wrong_record, sort_keys=True) + "\n", encoding="utf-8")
    wrong_run = run(
        "python3",
        str(SCRIPT_DIR / "verify_result_manifest.py"),
        "--root",
        str(results),
        "--manifest",
        str(manifest),
        "--execution-record",
        str(wrong_record_path),
        check=False,
    )
    assert wrong_run.returncode != 0 and "execution record" in wrong_run.stderr

    (results / "records.jsonl").write_text('{"step":2}\n', encoding="utf-8")
    changed = run(
        "python3",
        str(SCRIPT_DIR / "verify_result_manifest.py"),
        "--root",
        str(results),
        "--manifest",
        str(manifest),
        "--execution-record",
        str(execution_record),
        check=False,
    )
    assert changed.returncode != 0 and "changed" in changed.stderr

    (results / "records.jsonl").write_text('{"step":1}\n', encoding="utf-8")
    (results / "extra.txt").write_text("extra\n", encoding="utf-8")
    extra = run(
        "python3",
        str(SCRIPT_DIR / "verify_result_manifest.py"),
        "--root",
        str(results),
        "--manifest",
        str(manifest),
        "--execution-record",
        str(execution_record),
        check=False,
    )
    assert extra.returncode != 0 and "extra" in extra.stderr
    (results / "extra.txt").unlink()

    (results / "extra-empty").mkdir()
    extra_directory = run(
        "python3",
        str(SCRIPT_DIR / "verify_result_manifest.py"),
        "--root",
        str(results),
        "--manifest",
        str(manifest),
        "--execution-record",
        str(execution_record),
        check=False,
    )
    assert extra_directory.returncode != 0 and "extra_directories" in extra_directory.stderr
    (results / "extra-empty").rmdir()

    os.symlink("records.jsonl", results / "link")
    symlink = run(
        "python3",
        str(SCRIPT_DIR / "build_result_manifest.py"),
        "--root",
        str(results),
        "--execution-record",
        str(execution_record),
        "--output",
        str(root / "manifest-symlink.json"),
        check=False,
    )
    assert symlink.returncode != 0 and "symlink" in symlink.stderr


def test_fetch(root: Path) -> None:
    remote_results = root / "remote-results"
    remote_results.mkdir()
    (remote_results / "payload.txt").write_text("verified payload\n", encoding="utf-8")
    remote_manifest = root / "remote-manifest.json"
    execution_record = write_execution_fixture(root, remote_results, "fetch-fixture", ["payload.txt"])
    run(
        "python3",
        str(SCRIPT_DIR / "build_result_manifest.py"),
        "--root",
        str(remote_results),
        "--execution-record",
        str(execution_record),
        "--output",
        str(remote_manifest),
    )

    tool_dir = root / "fetch-tools"
    tool_dir.mkdir()
    shutil.copy2(SCRIPT_DIR / "fetch_results.sh", tool_dir / "fetch_results.sh")
    shutil.copy2(SCRIPT_DIR / "verify_result_manifest.py", tool_dir / "verify_result_manifest.py")
    fake_ssh = tool_dir / "ssh_session.sh"
    fake_ssh.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
[[ $1 == run ]] || exit 2
shift
while [[ $# -gt 0 && $1 != -- ]]; do
  case $1 in
    --host|--user|--port|--known-hosts|--password-file|--identity-file) shift 2 ;;
    *) exit 2 ;;
  esac
done
shift
bash -c "$1"
""",
        encoding="utf-8",
    )
    for path in tool_dir.iterdir():
        path.chmod(0o700)

    destination = root / "ssh-delivery"
    result = run(
        "bash",
        str(tool_dir / "fetch_results.sh"),
        "--host",
        "fixture",
        "--user",
        "fixture",
        "--known-hosts",
        str(root / "known_hosts"),
        "--remote-root",
        str(remote_results),
        "--remote-manifest",
        str(remote_manifest),
        "--execution-record",
        str(execution_record),
        "--destination",
        str(destination),
    )
    assert "VERIFIED" in result.stdout
    assert (destination / "raw" / "payload.txt").read_text(encoding="utf-8") == "verified payload\n"
    assert json.loads((destination / "verification.json").read_text(encoding="utf-8"))["status"] == "VERIFIED"

    wrong_destination = root / "wrong-run-delivery"
    wrong_record = json.loads(execution_record.read_text(encoding="utf-8"))
    wrong_record["run_id"] = "wrong-run"
    wrong_record_path = root / "fetch-wrong-execution-record.json"
    wrong_record_path.write_text(json.dumps(wrong_record, sort_keys=True) + "\n", encoding="utf-8")
    wrong_run = run(
        "bash",
        str(tool_dir / "fetch_results.sh"),
        "--host",
        "fixture",
        "--user",
        "fixture",
        "--known-hosts",
        str(root / "known_hosts"),
        "--remote-root",
        str(remote_results),
        "--remote-manifest",
        str(remote_manifest),
        "--execution-record",
        str(wrong_record_path),
        "--destination",
        str(wrong_destination),
        check=False,
    )
    assert wrong_run.returncode != 0 and not wrong_destination.exists()

    duplicate = run(
        "bash",
        str(tool_dir / "fetch_results.sh"),
        "--host",
        "fixture",
        "--user",
        "fixture",
        "--known-hosts",
        str(root / "known_hosts"),
        "--remote-root",
        str(remote_results),
        "--remote-manifest",
        str(remote_manifest),
        "--execution-record",
        str(execution_record),
        "--destination",
        str(destination),
        check=False,
    )
    assert duplicate.returncode != 0


def test_local_collection(root: Path) -> None:
    results = root / "local-results"
    results.mkdir()
    (results / "records.jsonl").write_text('{"sample":1}\n', encoding="utf-8")
    execution_record = write_execution_fixture(root, results, "local-r1", ["records.jsonl"])
    manifest = root / "local-manifest.json"
    run(
        "python3",
        str(SCRIPT_DIR / "build_result_manifest.py"),
        "--root",
        str(results),
        "--execution-record",
        str(execution_record),
        "--output",
        str(manifest),
    )
    destination = root / "local-delivery"
    collected = run(
        "bash",
        str(SCRIPT_DIR / "collect_local_results.sh"),
        "--source-root",
        str(results),
        "--manifest",
        str(manifest),
        "--execution-record",
        str(execution_record),
        "--destination",
        str(destination),
    )
    assert "VERIFIED" in collected.stdout
    assert (destination / "raw" / "records.jsonl").read_text(encoding="utf-8") == '{"sample":1}\n'
    duplicate = run(
        "bash",
        str(SCRIPT_DIR / "collect_local_results.sh"),
        "--source-root",
        str(results),
        "--manifest",
        str(manifest),
        "--execution-record",
        str(execution_record),
        "--destination",
        str(destination),
        check=False,
    )
    assert duplicate.returncode != 0


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="remote-experiment-skill-test-") as directory:
        root = Path(directory)
        test_ssh_config(root)
        test_inspection()
        test_telemetry_sampler(root)
        test_runner(root)
        test_manifest(root)
        test_fetch(root)
        test_local_collection(root)
    print("All offline tests passed.")


if __name__ == "__main__":
    main()
