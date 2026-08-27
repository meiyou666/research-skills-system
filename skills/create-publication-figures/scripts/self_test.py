#!/usr/bin/env python3
"""Exercise the publication-figure renderer and validator entirely in a temp directory."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


sys.dont_write_bytecode = True
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def inspect_package(
    package: Path,
    manifest: dict[str, Any],
) -> None:
    from validate_figure_package import _pdf_dimensions, _png_facts, _svg_dimensions

    pdf = package / "figure.pdf"
    svg = package / "figure.svg"
    png = package / "figure.png"
    assert_true(pdf.read_bytes().startswith(b"%PDF-"), "PDF header is unreadable")
    ET.parse(svg)
    pdf_size = _pdf_dimensions(pdf)
    svg_width, svg_height, _ = _svg_dimensions(svg)
    png_width, png_height, pixels, dpi = _png_facts(png)
    expected_width_mm = float(manifest["render"]["width_mm"])
    expected_height_mm = float(manifest["render"]["height_mm"])
    expected_dpi = float(manifest["render"]["png_dpi"])
    for name, actual in {
        "PDF width": pdf_size[0],
        "PDF height": pdf_size[1],
        "SVG width": svg_width,
        "SVG height": svg_height,
        "PNG width": png_width,
        "PNG height": png_height,
    }.items():
        expected = expected_width_mm if "width" in name else expected_height_mm
        assert_true(abs(actual - expected) <= 0.25, f"{name} differs: {actual} versus {expected}")
    assert_true(all(abs(item - expected_dpi) <= 1.0 for item in dpi), f"PNG DPI differs: {dpi}")
    assert_true(pixels[0] > 0 and pixels[1] > 0, "PNG pixel dimensions are non-positive")
    for location, value in [
        ("input", manifest["input"]["sha256"]),
        ("spec", manifest["spec"]["raw_sha256"]),
        ("profile", manifest["profile"]["profile_sha256"]),
        ("tool", manifest["generator"]["tool_sha256"]),
    ]:
        assert_true(len(value) == 64, f"{location} hash is missing")
    for entry in manifest["files"]:
        target = package / entry["name"]
        assert_true(sha256_file(target) == entry["sha256"], f"file hash differs: {target.name}")


def run_case(
    root: Path,
    name: str,
    data: Path,
    spec: Path,
    profile: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    from render_figure import render_package
    from validate_figure_package import validate_package

    output = root / name
    manifest = render_package(data, str(spec), output, profile_override=profile)
    report = validate_package(output, data_path=data, spec_path=spec)
    assert_true(report["summary"]["error_count"] == 0, f"validator errors for {name}: {report['errors']}")
    assert_true(report["status"] in {"valid", "valid_with_warnings"}, f"bad validation status for {name}")
    inspect_package(output, manifest)
    return manifest, report


def execute(temp_root: Path) -> dict[str, Any]:
    from render_figure import FigureSpecError, render_package
    from validate_figure_package import validate_package

    cases_root = temp_root / "cases"
    cases_root.mkdir()

    line_data = temp_root / "line.csv"
    write_csv(
        line_data,
        [
            {"time_h": 0, "control": 10.0, "treatment": 10.0},
            {"time_h": 1, "control": 12.0, "treatment": 15.0},
            {"time_h": 2, "control": 13.0, "treatment": 20.0},
            {"time_h": 3, "control": 14.0, "treatment": 27.0},
        ],
    )
    line_spec = temp_root / "line-spec.json"
    write_json(
        line_spec,
        {
            "chart": "line",
            "x": "time_h",
            "y": ["control", "treatment"],
            "xlabel": "Time (h)",
            "ylabel": "Response (%)",
            "caption": "Response over time for control and treatment.",
            "alt_text": "Two-line chart; treatment rises faster than control from the shared baseline.",
        },
    )

    scatter_data = temp_root / "scatter.json"
    write_json(
        scatter_data,
        [
            {"dose_mg": 1, "cohort_a": 2.2, "cohort_b": 1.9},
            {"dose_mg": 2, "cohort_a": 3.1, "cohort_b": 2.8},
            {"dose_mg": 4, "cohort_a": 4.6, "cohort_b": 4.0},
        ],
    )
    scatter_spec = temp_root / "scatter-spec.json"
    write_json(
        scatter_spec,
        {
            "chart": "scatter",
            "x": "dose_mg",
            "y": ["cohort_a", "cohort_b"],
            "xlabel": "Dose (mg)",
            "ylabel": "Response (a.u.)",
            "caption": "Observed response by dose for two cohorts.",
            "alt_text": "Scatter plot with both cohorts increasing as dose increases.",
        },
    )

    bar_data = temp_root / "bar.csv"
    write_csv(
        bar_data,
        [
            {"workload": "small", "baseline": 110, "optimized": 145},
            {"workload": "medium", "baseline": 95, "optimized": 138},
            {"workload": "large", "baseline": 72, "optimized": 120},
        ],
    )
    bar_spec = temp_root / "bar-spec.json"
    write_json(
        bar_spec,
        {
            "chart": "bar",
            "x": "workload",
            "y": ["baseline", "optimized"],
            "xlabel": "Workload",
            "ylabel": "Completed samples/s",
            "caption": "Throughput by workload for baseline and optimized systems.",
            "alt_text": "Grouped bars show higher optimized throughput for every workload.",
        },
    )

    latency_data = temp_root / "gpu-latency.csv"
    write_csv(
        latency_data,
        [
            {"request_id": "a1", "system": "A", "phase": "steady", "status": "ok", "latency_ms": 8.2},
            {"request_id": "a2", "system": "A", "phase": "steady", "status": "ok", "latency_ms": 9.8},
            {"request_id": "a3", "system": "A", "phase": "steady", "status": "timeout", "latency_ms": ""},
            {"request_id": "b1", "system": "B", "phase": "steady", "status": "ok", "latency_ms": 6.9},
            {"request_id": "b2", "system": "B", "phase": "steady", "status": "ok", "latency_ms": 7.4},
            {"request_id": "b3", "system": "B", "phase": "warmup", "status": "ok", "latency_ms": 14.0},
        ],
    )
    ecdf_spec = temp_root / "gpu-ecdf-spec.json"
    write_json(
        ecdf_spec,
        {
            "chart": "ecdf",
            "x": "latency_ms",
            "series": "system",
            "filter": {"status": "ok", "phase": "steady"},
            "xlabel": "End-to-end latency (ms)",
            "ylabel": "Empirical cumulative probability",
            "denominator": "Completed valid steady-state requests; all attempts retained in source",
            "caption": "Steady-state latency ECDF; one timeout and one warm-up request remain in the source denominator audit.",
            "alt_text": "ECDF comparing two GPU systems across four completed steady-state requests.",
        },
    )
    hist_spec = temp_root / "gpu-hist-spec.json"
    write_json(
        hist_spec,
        {
            "chart": "hist",
            "x": "latency_ms",
            "series": "system",
            "filter": {"status": "ok", "phase": "steady"},
            "bins": [0, 5, 7, 9, 11, 15],
            "xlabel": "End-to-end latency (ms)",
            "ylabel": "Completed requests",
            "caption": "Common-bin latency histogram for completed steady-state requests.",
            "alt_text": "Histogram with common bins comparing completed request latencies for systems A and B.",
        },
    )

    heatmap_data = temp_root / "gpu-errors.json"
    write_json(
        heatmap_data,
        {
            "records": [
                {"layer": "L0", "bit_position": "0", "errors_per_million": 0.0},
                {"layer": "L0", "bit_position": "1", "errors_per_million": 2.5},
                {"layer": "L1", "bit_position": "0", "errors_per_million": 5.0},
                {"layer": "L2", "bit_position": "1", "errors_per_million": ""},
            ]
        },
    )
    heatmap_spec = temp_root / "gpu-heatmap-spec.json"
    write_json(
        heatmap_spec,
        {
            "chart": "heatmap",
            "x": "bit_position",
            "y": "layer",
            "value": "errors_per_million",
            "x_order": ["0", "1", "2"],
            "y_order": ["L0", "L1", "L2"],
            "nonfinite": "drop",
            "xlabel": "Bit position",
            "ylabel": "Layer",
            "colorbar_label": "Errors per million injections",
            "vmin": 0,
            "caption": "Error rate by injected bit and model layer; gray denotes an unobserved cell, not zero.",
            "alt_text": "Three-by-three error heatmap retaining declared categories and showing missing cells in gray.",
        },
    )

    cases = [
        ("line-a", line_data, line_spec, None),
        ("line-b", line_data, line_spec, None),
        ("scatter", scatter_data, scatter_spec, None),
        ("bar", bar_data, bar_spec, None),
        ("gpu-ecdf", latency_data, ecdf_spec, None),
        ("gpu-hist", latency_data, hist_spec, None),
        ("gpu-heatmap", heatmap_data, heatmap_spec, None),
        ("profile-nature", line_data, line_spec, "nature-portfolio"),
        ("profile-science", line_data, line_spec, "science-aaas"),
        ("profile-ieee", line_data, line_spec, "ieee"),
        ("profile-acm", line_data, line_spec, "acm"),
    ]
    results: dict[str, dict[str, Any]] = {}
    for name, data, spec, profile in cases:
        manifest, report = run_case(cases_root, name, data, spec, profile)
        results[name] = {
            "chart": manifest["figure"]["chart"],
            "errors": report["summary"]["error_count"],
            "warnings": report["summary"]["warning_count"],
        }

    for filename in ("figure.pdf", "figure.svg", "figure.png", "manifest.json"):
        first = cases_root / "line-a" / filename
        second = cases_root / "line-b" / filename
        assert_true(
            sha256_file(first) == sha256_file(second),
            f"determinism failed for {filename}",
        )

    symlink_package = cases_root / "symlink-artifact"
    symlink_package.mkdir()
    source_package = cases_root / "line-a"
    for filename in ("figure.svg", "figure.png", "manifest.json"):
        (symlink_package / filename).write_bytes((source_package / filename).read_bytes())
    (symlink_package / "figure.pdf").symlink_to(source_package / "figure.pdf")
    symlink_report = validate_package(symlink_package)
    assert_true(
        any(item["code"] == "FILE_TYPE" for item in symlink_report["errors"]),
        "validator accepted a symlinked figure artifact",
    )

    overwrite_target = cases_root / "overwrite-symlink"
    overwrite_target.mkdir()
    protected = temp_root / "protected.pdf"
    protected.write_bytes(b"protected")
    (overwrite_target / "figure.pdf").symlink_to(protected)
    try:
        render_package(line_data, str(line_spec), overwrite_target, overwrite=True)
    except FigureSpecError as exc:
        assert_true("regular file" in str(exc), "renderer symlink rejection reason changed")
    else:
        raise AssertionError("renderer followed an output symlink")
    assert_true(protected.read_bytes() == b"protected", "renderer changed a symlink target")
    ecdf_manifest = json.loads((cases_root / "gpu-ecdf" / "manifest.json").read_text(encoding="utf-8"))
    assert_true(ecdf_manifest["qa"]["input_row_count"] == 6, "GPU attempts were not retained")
    assert_true(ecdf_manifest["qa"]["filter"]["excluded_rows"] == 2, "GPU exclusions were not recorded")
    heatmap_manifest = json.loads((cases_root / "gpu-heatmap" / "manifest.json").read_text(encoding="utf-8"))
    assert_true(heatmap_manifest["figure"]["heatmap_shape"] == [3, 3], "Heatmap declared categories were not preserved")
    assert_true(heatmap_manifest["figure"]["missing_cell_count"] == 6, "Heatmap missing cells were not preserved")
    assert_true(heatmap_manifest["qa"]["dropped_observation_count"] == 1, "Heatmap all-missing category was not audited")
    heatmap_svg = (cases_root / "gpu-heatmap" / "figure.svg").read_text(encoding="utf-8")
    for category in (">0<", ">1<", ">2<", ">L0<", ">L1<", ">L2<"):
        assert_true(category in heatmap_svg, f"Heatmap categorical tick is missing: {category}")

    child_environment = dict(os.environ)
    child_environment["PYTHONDONTWRITEBYTECODE"] = "1"
    cli_outputs = [cases_root / "cli-smoke-a", cases_root / "cli-smoke-b"]
    for cli_output in cli_outputs:
        render_cli = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_DIR / "render_figure.py"),
                "--data",
                str(line_data),
                "--spec",
                str(line_spec),
                "--output-dir",
                str(cli_output),
            ],
            check=False,
            capture_output=True,
            text=True,
            env=child_environment,
        )
        assert_true(render_cli.returncode == 0, f"renderer CLI failed: {render_cli.stderr}")
        assert_true(json.loads(render_cli.stdout)["status"] == "ok", "renderer CLI output is not machine-readable")
    for filename in ("figure.pdf", "figure.svg", "figure.png", "manifest.json"):
        assert_true(
            sha256_file(cli_outputs[0] / filename) == sha256_file(cli_outputs[1] / filename),
            f"cross-process determinism failed for {filename}",
        )
    validate_cli = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_DIR / "validate_figure_package.py"),
            str(cli_outputs[0]),
            "--data",
            str(line_data),
            "--spec",
            str(line_spec),
        ],
        check=False,
        capture_output=True,
        text=True,
        env=child_environment,
    )
    assert_true(validate_cli.returncode == 0, f"validator CLI failed: {validate_cli.stderr}")
    assert_true(json.loads(validate_cli.stdout)["summary"]["error_count"] == 0, "validator CLI found errors")

    empty_data = temp_root / "empty.csv"
    empty_data.write_text("x,y\n", encoding="utf-8")
    negative_spec = temp_root / "negative-spec.json"
    write_json(negative_spec, {"chart": "line", "x": "x", "y": "y"})
    try:
        render_package(empty_data, str(negative_spec), cases_root / "must-not-render-empty")
    except FigureSpecError as exc:
        assert_true("no records" in str(exc) or "empty" in str(exc), "empty-data error is unclear")
    else:
        raise AssertionError("empty data was not rejected")

    nonfinite_data = temp_root / "nonfinite.csv"
    write_csv(nonfinite_data, [{"x": 1, "y": "nan"}])
    try:
        render_package(nonfinite_data, str(negative_spec), cases_root / "must-not-render-nonfinite")
    except FigureSpecError as exc:
        assert_true("non-finite" in str(exc), "non-finite error is unclear")
    else:
        raise AssertionError("non-finite data was not rejected")

    tampered_svg = cases_root / "bar" / "figure.svg"
    tampered_svg.write_text(tampered_svg.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    tamper_report = validate_package(cases_root / "bar", data_path=bar_data, spec_path=bar_spec)
    tamper_codes = {item["code"] for item in tamper_report["errors"]}
    assert_true("FILE_HASH" in tamper_codes and "FILE_SIZE" in tamper_codes, "validator missed file tampering")
    return {
        "cases": results,
        "case_count": len(cases),
        "deterministic_files": ["figure.pdf", "figure.svg", "figure.png", "manifest.json"],
        "cross_process_determinism": True,
        "formats_verified": ["PDF", "SVG", "PNG"],
        "gpu_fixtures": ["latency-ecdf", "latency-hist", "error-heatmap-with-declared-missing-categories"],
        "submission_profiles_verified": ["nature-portfolio", "science-aaas", "ieee", "acm"],
        "cli_scripts_verified": ["render_figure.py", "validate_figure_package.py"],
        "physical_dimensions_verified": True,
        "dpi_verified": True,
        "hashes_verified": ["input", "spec", "profile", "tool", "files"],
        "negative_cases_verified": ["empty-data", "non-finite-data", "tampered-file"],
    }


def main() -> int:
    temp_path: Path | None = None
    try:
        with tempfile.TemporaryDirectory(prefix="publication-figure-self-test-") as directory:
            temp_path = Path(directory)
            os.environ["MPLCONFIGDIR"] = str(temp_path / "matplotlib-config")
            result = execute(temp_path)
        result.update({"status": "ok", "temp_cleaned": temp_path is not None and not temp_path.exists()})
        assert_true(result["temp_cleaned"], "temporary directory was not cleaned")
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False))
        return 0
    except Exception as exc:
        cleaned = temp_path is None or not temp_path.exists()
        print(
            json.dumps(
                {
                    "status": "error",
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                    "temp_cleaned": cleaned,
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
