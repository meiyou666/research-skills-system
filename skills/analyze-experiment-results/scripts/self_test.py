#!/usr/bin/env python3
"""Offline GPU-oriented fixtures for the bundled analysis tools."""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import os
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent


def run(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(args, text=True, capture_output=True, check=False)
    if check and result.returncode != 0:
        raise AssertionError(f"command failed: {' '.join(args)}\n{result.stdout}\n{result.stderr}")
    return result


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_summarizer():
    module_path = SCRIPT_DIR / "summarize_measurements.py"
    module_spec = importlib.util.spec_from_file_location("analysis_summarizer_under_test", module_path)
    assert module_spec is not None and module_spec.loader is not None
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


def assert_rejected(package: Path, expected: str) -> None:
    result = run(
        "python3",
        str(SCRIPT_DIR / "validate_analysis_package.py"),
        str(package),
        check=False,
    )
    assert result.returncode != 0, result.stdout
    assert expected in result.stdout, result.stdout


def write_fixture(path: Path) -> None:
    rows = [
        {"run_id": "r1", "sample_id": "1", "variant": "base", "device": "0", "status": "OK", "latency_ms": "10", "power_w": "200"},
        {"run_id": "r1", "sample_id": "2", "variant": "base", "device": "0", "status": "OK", "latency_ms": "12", "power_w": "202"},
        {"run_id": "r2", "sample_id": "1", "variant": "candidate", "device": "1", "status": "OK", "latency_ms": "7", "power_w": "210"},
        {"run_id": "r2", "sample_id": "2", "variant": "candidate", "device": "1", "status": "OK", "latency_ms": "30", "power_w": "215"},
        {"run_id": "r2", "sample_id": "3", "variant": "candidate", "device": "1", "status": "THROTTLED", "latency_ms": "40", "power_w": "220"},
        {"run_id": "r3", "sample_id": "1", "variant": "candidate", "device": "1", "status": "OOM", "latency_ms": "", "power_w": ""},
        {"run_id": "r3", "sample_id": "2", "variant": "candidate", "device": "1", "status": "OK", "latency_ms": "NaN", "power_w": "205"},
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def spec() -> dict[str, object]:
    return {
        "schema_version": 1,
        "analysis_id": "gpu-analysis-fixture",
        "status": "draft",
        "id_columns": ["run_id", "sample_id"],
        "group_by": ["variant"],
        "context_columns": ["device"],
        "record_status": {"column": "status", "valid": ["OK"], "execution_failure": ["OOM"], "contamination": ["THROTTLED"], "missing": ["MISSING"]},
        "metrics": [
            {"id": "latency_ms", "column": "latency_ms", "description": "per-sample device latency", "unit": "ms", "direction": "lower", "numerator": "elapsed device milliseconds", "denominator": "one measured sample", "bootstrap_samples": 100, "confidence": 0.9, "bad_case": {"operator": "above", "threshold": 20}},
            {"id": "power_w", "column": "power_w", "description": "sampled device power", "unit": "W", "direction": "context", "numerator": "reported watts", "denominator": "one telemetry sample", "bootstrap_samples": 0},
        ],
        "comparisons": [{"id": "candidate-vs-base", "metric_id": "latency_ms", "baseline_filters": {"variant": "base"}, "candidate_filters": {"variant": "candidate"}, "bootstrap_samples": 100, "confidence": 0.9}],
        "seed": 7,
        "unresolved_blockers": [],
    }


def write_three_status_fixture(path: Path) -> None:
    rows = [
        {"run_id": "s1", "run_status": "SUCCEEDED", "measurement_status": "VALID", "scientific_status": "PASS", "latency_ms": "10"},
        {"run_id": "s2", "run_status": "OOM", "measurement_status": "MISSING", "scientific_status": "NOT_EVALUATED", "latency_ms": ""},
        {"run_id": "s3", "run_status": "SUCCEEDED", "measurement_status": "THROTTLED", "scientific_status": "PASS", "latency_ms": "20"},
        {"run_id": "s4", "run_status": "SUCCEEDED", "measurement_status": "VALID", "scientific_status": "FAIL", "latency_ms": "30"},
        {"run_id": "s5", "run_status": "SUCCEEDED", "measurement_status": "VALID", "scientific_status": "EXCLUDED", "latency_ms": "40"},
        {"run_id": "s6", "run_status": "SUCCEEDED", "measurement_status": "MISSING", "scientific_status": "PASS", "latency_ms": ""},
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def three_status_spec() -> dict[str, object]:
    return {
        "schema_version": 1,
        "analysis_id": "three-status-fixture",
        "status": "draft",
        "id_columns": ["run_id"],
        "group_by": [],
        "record_status": {},
        "status_columns": {
            "execution": {"column": "run_status", "accepted": ["SUCCEEDED"], "failed": ["OOM"], "missing": ["MISSING"]},
            "measurement": {"column": "measurement_status", "accepted": ["VALID"], "contaminated": ["THROTTLED"], "missing": ["MISSING"]},
            "scientific": {"column": "scientific_status", "observed": ["PASS", "FAIL"], "excluded": ["EXCLUDED"], "missing": ["NOT_EVALUATED"]},
        },
        "metrics": [
            {
                "id": "latency_ms",
                "column": "latency_ms",
                "description": "per-sample latency",
                "unit": "ms",
                "direction": "lower",
                "numerator": "elapsed milliseconds",
                "denominator": "one eligible sample",
            }
        ],
        "unresolved_blockers": ["replication batch is pending"],
    }


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="experiment-analysis-test-") as directory:
        root = Path(directory)
        data = root / "measurements.csv"
        spec_path = root / "spec.json"
        write_fixture(data)
        spec_path.write_text(json.dumps(spec(), indent=2, sort_keys=True) + "\n", encoding="utf-8")

        first = root / "analysis-a"
        second = root / "analysis-b"
        command = ["python3", str(SCRIPT_DIR / "summarize_measurements.py"), "--input", str(data), "--spec", str(spec_path), "--output-dir"]
        run(*command, str(first))
        run(*command, str(second))
        for relative in ("analysis-spec.json", "metric-dictionary.json", "derived/observations.csv", "derived/summary.csv", "derived/bad-cases.csv", "statistics.json", "findings.md", "analysis-manifest.json"):
            assert sha256(first / relative) == sha256(second / relative)

        statistics_value = json.loads((first / "statistics.json").read_text(encoding="utf-8"))
        candidate_latency = next(item for item in statistics_value["summaries"] if item["metric_id"] == "latency_ms" and item["variant"] == "candidate")
        assert candidate_latency["total_count"] == 5
        assert candidate_latency["analyzed_count"] == 2
        assert candidate_latency["execution_failure_count"] == 1
        assert candidate_latency["contamination_count"] == 1
        assert candidate_latency["nonfinite_count"] == 1
        bad_cases = (first / "derived" / "bad-cases.csv").read_text(encoding="utf-8")
        assert "30.0" in bad_cases and "40.0" not in bad_cases

        jsonl = root / "measurements.jsonl"
        with data.open("r", encoding="utf-8", newline="") as handle:
            jsonl.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in csv.DictReader(handle)), encoding="utf-8")
        jsonl_output = root / "analysis-jsonl"
        run(*command[:2], "--input", str(jsonl), "--spec", str(spec_path), "--output-dir", str(jsonl_output))
        assert (jsonl_output / "derived" / "observations.csv").is_file()

        three_status_data = root / "three-status.csv"
        three_status_spec_path = root / "three-status-spec.json"
        write_three_status_fixture(three_status_data)
        three_status_spec_path.write_text(
            json.dumps(three_status_spec(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        three_status_output = root / "three-status-analysis"
        run(
            "python3",
            str(SCRIPT_DIR / "summarize_measurements.py"),
            "--input",
            str(three_status_data),
            "--spec",
            str(three_status_spec_path),
            "--output-dir",
            str(three_status_output),
        )
        three_statistics = json.loads(
            (three_status_output / "statistics.json").read_text(encoding="utf-8")
        )
        three_summary = three_statistics["summaries"][0]
        assert three_summary["total_count"] == 6
        assert three_summary["analyzed_count"] == 2
        assert three_summary["execution_failure_count"] == 1
        assert three_summary["contamination_count"] == 1
        assert three_summary["measurement_missing_count"] == 2
        assert three_summary["scientific_excluded_count"] == 1
        assert three_summary["scientific_observed_count"] == 4
        observations_text = (three_status_output / "derived" / "observations.csv").read_text(encoding="utf-8")
        assert "analysis_execution_status" in observations_text and "analysis_eligible" in observations_text
        findings_text = (three_status_output / "findings.md").read_text(encoding="utf-8")
        assert "BLOCKER: replication batch is pending" in findings_text
        assert "not an accepted scientific conclusion" in findings_text
        three_validated = run(
            "python3",
            str(SCRIPT_DIR / "validate_analysis_package.py"),
            str(three_status_output),
            "--input-file",
            str(three_status_data),
            "--source-spec",
            str(three_status_spec_path),
        )
        assert "unresolved blocker" in three_validated.stdout and "analysis package: PASS" in three_validated.stdout

        validated = run("python3", str(SCRIPT_DIR / "validate_analysis_package.py"), str(first), "--input-file", str(data), "--source-spec", str(spec_path))
        assert "analysis package: PASS" in validated.stdout

        # Input and spec links are deliberately dereferenced; output links are not.
        data_link = root / "measurements-link.csv"
        spec_link = root / "spec-link.json"
        data_link.symlink_to(data.name)
        spec_link.symlink_to(spec_path.name)
        linked_input_output = root / "analysis-linked-inputs"
        run(*command[:2], "--input", str(data_link), "--spec", str(spec_link), "--output-dir", str(linked_input_output))
        linked_validation = run(
            "python3",
            str(SCRIPT_DIR / "validate_analysis_package.py"),
            str(linked_input_output),
            "--input-file",
            str(data_link),
            "--source-spec",
            str(spec_link),
        )
        assert "analysis package: PASS" in linked_validation.stdout

        protected = root / "protected-output.txt"
        protected.write_bytes(b"protected-output-bytes")
        output_link = root / "analysis-output-link"
        output_link.symlink_to(protected.name)
        linked_output_attempt = run(*command, str(output_link), check=False)
        assert linked_output_attempt.returncode != 0
        assert output_link.is_symlink() and protected.read_bytes() == b"protected-output-bytes"

        dangling_output = root / "analysis-dangling-output"
        dangling_output.symlink_to("absent-output-target")
        dangling_attempt = run(*command, str(dangling_output), check=False)
        assert dangling_attempt.returncode != 0
        assert dangling_output.is_symlink() and os.readlink(dangling_output) == "absent-output-target"

        existing_output = root / "analysis-existing"
        existing_output.mkdir()
        existing_marker = existing_output / "owner.txt"
        existing_marker.write_bytes(b"existing-owner")
        existing_attempt = run(*command, str(existing_output), check=False)
        assert existing_attempt.returncode != 0
        assert existing_marker.read_bytes() == b"existing-owner"

        actual_parent = root / "actual-output-parent"
        actual_parent.mkdir()
        linked_parent = root / "linked-output-parent"
        linked_parent.symlink_to(actual_parent.name, target_is_directory=True)
        intermediate_output = linked_parent / "analysis"
        intermediate_attempt = run(*command, str(intermediate_output), check=False)
        assert intermediate_attempt.returncode != 0
        assert not (actual_parent / "analysis").exists()

        if hasattr(os, "mkfifo"):
            fifo_output = root / "analysis-output-fifo"
            os.mkfifo(fifo_output)
            fifo_output_attempt = run(*command, str(fifo_output), check=False)
            assert fifo_output_attempt.returncode != 0
            assert stat.S_ISFIFO(fifo_output.lstat().st_mode)

        # Exercise the same publish primitive after staging but after a target appears.
        summarizer = load_summarizer()
        late_staging = root / ".late-target.partial"
        late_staging.mkdir()
        (late_staging / "analysis-manifest.json").write_bytes(b"staged-manifest")
        late_target = root / "analysis-late-target"
        late_target.write_bytes(b"late-owner-bytes")
        try:
            summarizer.publish_staging(late_staging, late_target)
        except summarizer.AnalysisError:
            pass
        else:
            raise AssertionError("late-created output target was replaced")
        assert late_target.read_bytes() == b"late-owner-bytes"
        assert (late_staging / "analysis-manifest.json").read_bytes() == b"staged-manifest"

        package_link = root / "analysis-package-link"
        package_link.symlink_to(first.name, target_is_directory=True)
        assert_rejected(package_link, "analysis package path contains a symlink")

        real_container = root / "real-package-container"
        real_container.mkdir()
        shutil.copytree(first, real_container / "analysis")
        linked_container = root / "linked-package-container"
        linked_container.symlink_to(real_container.name, target_is_directory=True)
        assert_rejected(linked_container / "analysis", "analysis package path contains a symlink")

        manifest_link_package = root / "analysis-manifest-link"
        shutil.copytree(first, manifest_link_package)
        external_manifest = root / "external-manifest.json"
        shutil.copy2(manifest_link_package / "analysis-manifest.json", external_manifest)
        (manifest_link_package / "analysis-manifest.json").unlink()
        (manifest_link_package / "analysis-manifest.json").symlink_to(external_manifest)
        assert_rejected(manifest_link_package, "analysis-manifest.json must be a regular file")

        output_link_package = root / "analysis-member-link"
        shutil.copytree(first, output_link_package)
        external_statistics = root / "external-statistics.json"
        external_statistics.write_text("this is not package JSON\n", encoding="utf-8")
        (output_link_package / "statistics.json").unlink()
        (output_link_package / "statistics.json").symlink_to(external_statistics)
        assert_rejected(output_link_package, "package member is a symlink: statistics.json")

        dangling_member_package = root / "analysis-dangling-member"
        shutil.copytree(first, dangling_member_package)
        (dangling_member_package / "statistics.json").unlink()
        (dangling_member_package / "statistics.json").symlink_to("absent-statistics.json")
        assert_rejected(dangling_member_package, "package member is a symlink: statistics.json")

        intermediate_member_package = root / "analysis-intermediate-member-link"
        shutil.copytree(first, intermediate_member_package)
        external_derived = root / "external-derived"
        shutil.copytree(intermediate_member_package / "derived", external_derived)
        shutil.rmtree(intermediate_member_package / "derived")
        (intermediate_member_package / "derived").symlink_to(external_derived, target_is_directory=True)
        assert_rejected(intermediate_member_package, "package member is a symlink: derived")

        extra_file_package = root / "analysis-extra-file"
        shutil.copytree(first, extra_file_package)
        (extra_file_package / "extra.txt").write_bytes(b"undeclared")
        assert_rejected(extra_file_package, "undeclared package file: extra.txt")

        extra_directory_package = root / "analysis-extra-directory"
        shutil.copytree(first, extra_directory_package)
        (extra_directory_package / "empty-extra").mkdir()
        assert_rejected(extra_directory_package, "undeclared package directory: empty-extra")

        escape_package = root / "analysis-escape-path"
        shutil.copytree(first, escape_package)
        escape_manifest_path = escape_package / "analysis-manifest.json"
        escape_manifest = json.loads(escape_manifest_path.read_text(encoding="utf-8"))
        escape_manifest["outputs"][0]["path"] = "../escaped.json"
        escape_manifest_path.write_text(
            json.dumps(escape_manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        assert_rejected(escape_package, "outputs[0].path is not normalized")

        if hasattr(os, "mkfifo"):
            fifo_package = root / "analysis-fifo-member"
            shutil.copytree(first, fifo_package)
            os.mkfifo(fifo_package / "unexpected.fifo")
            assert_rejected(fifo_package, "package member is a special file: unexpected.fifo")

        frozen_spec = spec()
        frozen_spec["status"] = "frozen"
        frozen_spec_path = root / "frozen-spec.json"
        frozen_spec_path.write_text(
            json.dumps(frozen_spec, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        frozen_attempt = run(
            "python3",
            str(SCRIPT_DIR / "summarize_measurements.py"),
            "--input",
            str(data),
            "--spec",
            str(frozen_spec_path),
            "--output-dir",
            str(root / "invalid-frozen-output"),
            check=False,
        )
        assert frozen_attempt.returncode != 0
        assert "produces draft findings only" in frozen_attempt.stdout
        assert not (root / "invalid-frozen-output").exists()

        (first / "statistics.json").write_text("{}\n", encoding="utf-8")
        rejected = run("python3", str(SCRIPT_DIR / "validate_analysis_package.py"), str(first), check=False)
        assert rejected.returncode != 0 and "SHA256 mismatch" in rejected.stdout
    print("self-test: PASS")


if __name__ == "__main__":
    main()
