#!/usr/bin/env python3
"""Validate mechanical facts in a publication-figure package and emit review warnings."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import stat
import sys
import xml.etree.ElementTree as ET
from itertools import combinations
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError


SCRIPT_PATH = Path(__file__).resolve()
SCRIPT_DIR = SCRIPT_PATH.parent
DEFAULT_PROFILES_PATH = SCRIPT_DIR.parent / "references" / "submission_profiles.json"
RENDERER_PATH = SCRIPT_DIR / "render_figure.py"
MM_PER_INCH = 25.4
PT_PER_INCH = 72.0
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class Report:
    def __init__(self, package_dir: Path) -> None:
        self.package_dir = package_dir
        self.errors: list[dict[str, Any]] = []
        self.warnings: list[dict[str, Any]] = []
        self.checks: list[dict[str, Any]] = []

    def error(self, code: str, message: str, **details: Any) -> None:
        self.errors.append({"severity": "ERROR", "code": code, "message": message, **details})

    def warning(self, code: str, message: str, **details: Any) -> None:
        self.warnings.append({"severity": "WARNING", "code": code, "message": message, **details})

    def check(self, code: str, message: str, **details: Any) -> None:
        self.checks.append({"code": code, "message": message, **details})

    def as_dict(self) -> dict[str, Any]:
        if self.errors:
            status = "invalid"
        elif self.warnings:
            status = "valid_with_warnings"
        else:
            status = "valid"
        return {
            "schema_version": "1.0",
            "report_type": "publication-figure-package-validation",
            "package": self.package_dir.name,
            "status": status,
            "summary": {
                "error_count": len(self.errors),
                "warning_count": len(self.warnings),
                "passed_check_count": len(self.checks),
            },
            "errors": self.errors,
            "warnings": self.warnings,
            "passed_checks": self.checks,
            "policy": {
                "error_boundary": "mechanical file, structure, hash, readability, size, font-range, and DPI facts only",
                "warning_boundary": "scientific, semantic, accessibility, venue, and visual judgments",
            },
        }


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _valid_hash(value: Any) -> bool:
    return isinstance(value, str) and bool(SHA256_PATTERN.fullmatch(value))


def _load_json(path: Path, report: Report, code: str) -> dict[str, Any] | None:
    try:
        entry = path.lstat()
    except OSError as exc:
        report.error(code, f"Cannot inspect {path.name}: {exc}")
        return None
    if stat.S_ISLNK(entry.st_mode) or not stat.S_ISREG(entry.st_mode):
        report.error(code, f"{path.name} must be a regular file, not a symlink or special file")
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        report.error(code, f"Cannot read {path.name}: {exc}")
        return None
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        report.error(code, f"{path.name} is not valid UTF-8 JSON: {exc}")
        return None
    if not isinstance(value, dict):
        report.error(code, f"{path.name} root must be a JSON object")
        return None
    return value


def _pdf_dimensions(path: Path) -> tuple[float, float]:
    raw = path.read_bytes()
    if not raw.startswith(b"%PDF-") or b"%%EOF" not in raw[-2048:]:
        raise ValueError("missing PDF header or EOF marker")
    number = rb"([+-]?(?:\d+(?:\.\d*)?|\.\d+))"
    match = re.search(
        rb"/MediaBox\s*\[\s*" + number + rb"\s+" + number + rb"\s+" + number + rb"\s+" + number + rb"\s*\]",
        raw,
    )
    if not match:
        raise ValueError("PDF MediaBox was not found")
    x0, y0, x1, y1 = (float(item) for item in match.groups())
    if x1 <= x0 or y1 <= y0:
        raise ValueError("PDF MediaBox is non-positive")
    return (x1 - x0) / PT_PER_INCH * MM_PER_INCH, (y1 - y0) / PT_PER_INCH * MM_PER_INCH


def _length_to_mm(value: str) -> float:
    match = re.fullmatch(r"\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*(mm|cm|in|pt|px)?\s*", value)
    if not match:
        raise ValueError(f"unsupported SVG length: {value!r}")
    number = float(match.group(1))
    unit = match.group(2) or "px"
    factors = {
        "mm": 1.0,
        "cm": 10.0,
        "in": MM_PER_INCH,
        "pt": MM_PER_INCH / PT_PER_INCH,
        "px": MM_PER_INCH / 96.0,
    }
    result = number * factors[unit]
    if not math.isfinite(result) or result <= 0:
        raise ValueError("SVG dimension is non-positive")
    return result


def _svg_dimensions(path: Path) -> tuple[float, float, str]:
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        raise ValueError(f"invalid SVG XML: {exc}") from exc
    if root.tag.rsplit("}", 1)[-1] != "svg":
        raise ValueError("XML root is not svg")
    width, height = root.get("width"), root.get("height")
    if not width or not height:
        raise ValueError("SVG width/height attributes are missing")
    raw_text = path.read_text(encoding="utf-8")
    return _length_to_mm(width), _length_to_mm(height), raw_text


def _png_facts(path: Path) -> tuple[float, float, list[int], list[float]]:
    try:
        with Image.open(path) as image:
            if image.format != "PNG":
                raise ValueError(f"expected PNG, found {image.format}")
            image.load()
            pixels = [int(image.width), int(image.height)]
            dpi_value = image.info.get("dpi")
    except (OSError, UnidentifiedImageError) as exc:
        raise ValueError(f"unreadable PNG: {exc}") from exc
    if not dpi_value or len(dpi_value) < 2:
        raise ValueError("PNG has no two-axis DPI metadata")
    dpi = [float(dpi_value[0]), float(dpi_value[1])]
    if any(not math.isfinite(item) or item <= 0 for item in dpi):
        raise ValueError("PNG DPI is invalid")
    width_mm = pixels[0] / dpi[0] * MM_PER_INCH
    height_mm = pixels[1] / dpi[1] * MM_PER_INCH
    return width_mm, height_mm, pixels, dpi


def _close(a: float, b: float, tolerance: float) -> bool:
    return abs(a - b) <= tolerance


def _check_hash_field(report: Report, parent: dict[str, Any], field: str, location: str) -> None:
    if not _valid_hash(parent.get(field)):
        report.error("HASH_STRUCTURE", f"{location}.{field} must be a lowercase SHA-256 digest")
    else:
        report.check("HASH_STRUCTURE", f"{location}.{field} has valid SHA-256 structure")


def _check_manifest_structure(manifest: dict[str, Any], report: Report) -> bool:
    required = ["schema_version", "package_type", "generator", "input", "spec", "profile", "render", "figure", "files", "qa"]
    missing = [key for key in required if key not in manifest]
    if missing:
        report.error("MANIFEST_STRUCTURE", f"Manifest is missing keys: {', '.join(missing)}")
        return False
    object_keys = ["generator", "input", "spec", "profile", "render", "figure", "qa"]
    wrong = [key for key in object_keys if not isinstance(manifest.get(key), dict)]
    if wrong or not isinstance(manifest.get("files"), list):
        report.error("MANIFEST_STRUCTURE", "Manifest sections have incorrect JSON types", fields=wrong)
        return False
    if not manifest["files"]:
        report.error("MANIFEST_STRUCTURE", "Manifest files list is empty")
        return False
    report.check("MANIFEST_STRUCTURE", "Required manifest sections are present")
    for parent_name, field in [
        ("generator", "tool_sha256"),
        ("input", "sha256"),
        ("spec", "raw_sha256"),
        ("spec", "canonical_sha256"),
        ("spec", "resolved_sha256"),
        ("profile", "profile_sha256"),
    ]:
        _check_hash_field(report, manifest[parent_name], field, parent_name)
    return True


def _validate_sources(
    manifest: dict[str, Any],
    report: Report,
    data_path: Path | None,
    spec_path: Path | None,
) -> None:
    if data_path is not None:
        if not data_path.is_file():
            report.error("INPUT_SOURCE", f"Input source does not exist: {data_path}")
        elif sha256_file(data_path) != manifest["input"].get("sha256"):
            report.error("INPUT_HASH", "Input source SHA-256 does not match manifest")
        else:
            report.check("INPUT_HASH", "Input source SHA-256 matches manifest")
    if spec_path is not None:
        if not spec_path.is_file():
            report.error("SPEC_SOURCE", f"Spec source does not exist: {spec_path}")
        elif sha256_file(spec_path) != manifest["spec"].get("raw_sha256"):
            report.error("SPEC_HASH", "Spec source SHA-256 does not match manifest")
        else:
            report.check("SPEC_HASH", "Spec source SHA-256 matches manifest")


def _validate_profile(
    manifest: dict[str, Any], report: Report, profiles_path: Path
) -> dict[str, Any] | None:
    config = _load_json(profiles_path, report, "PROFILE_CONFIG")
    if config is None:
        return None
    profiles = config.get("profiles")
    if not isinstance(profiles, dict):
        report.error("PROFILE_CONFIG", "Profile config is missing profiles object")
        return None
    profile_id = manifest["profile"].get("id")
    if profile_id not in profiles:
        report.error("PROFILE_ID", f"Manifest profile {profile_id!r} is absent from current config")
        return None
    profile = profiles[profile_id]
    current_hash = hashlib.sha256(canonical_json_bytes(profile)).hexdigest()
    if current_hash != manifest["profile"].get("profile_sha256"):
        report.error("PROFILE_HASH", "Current profile content does not match manifest profile SHA-256")
    else:
        report.check("PROFILE_HASH", "Current profile content matches manifest SHA-256")
    config_hash = sha256_file(profiles_path)
    recorded_config_hash = manifest["profile"].get("config", {}).get("file_sha256")
    if config_hash != recorded_config_hash:
        report.error("PROFILE_CONFIG_HASH", "Current profile file does not match manifest config SHA-256")
    else:
        report.check("PROFILE_CONFIG_HASH", "Current profile file matches manifest SHA-256")
    if RENDERER_PATH.is_file():
        renderer_hash = sha256_file(RENDERER_PATH)
        if renderer_hash != manifest["generator"].get("tool_sha256"):
            report.error("TOOL_HASH", "Current renderer does not match manifest tool SHA-256")
        else:
            report.check("TOOL_HASH", "Current renderer matches manifest tool SHA-256")
    return profile


def _validate_files(
    manifest: dict[str, Any],
    report: Report,
    dpi_tolerance: float,
    size_tolerance_mm: float,
) -> tuple[dict[str, dict[str, Any]], str | None]:
    expected_types = {"application/pdf", "image/svg+xml", "image/png"}
    seen_names: set[str] = set()
    found_types: set[str] = set()
    actual_by_type: dict[str, dict[str, Any]] = {}
    svg_text: str | None = None
    render = manifest["render"]
    declared_width, declared_height = render.get("width_mm"), render.get("height_mm")
    if not _is_number(declared_width) or declared_width <= 0 or not _is_number(declared_height) or declared_height <= 0:
        report.error("RENDER_SIZE", "Manifest render dimensions must be positive finite numbers")
        declared_width = declared_height = None
    else:
        report.check("RENDER_SIZE", "Manifest render dimensions are positive")
    for entry in manifest["files"]:
        if not isinstance(entry, dict):
            report.error("FILE_STRUCTURE", "Every files item must be an object")
            continue
        name, media_type = entry.get("name"), entry.get("media_type")
        if not isinstance(name, str) or Path(name).name != name or name in {"", ".", ".."}:
            report.error("FILE_PATH", f"Unsafe or invalid package filename: {name!r}")
            continue
        if name in seen_names:
            report.error("FILE_STRUCTURE", f"Duplicate file entry: {name}")
            continue
        seen_names.add(name)
        if not isinstance(media_type, str):
            report.error("FILE_STRUCTURE", f"File {name} has invalid media_type")
            continue
        found_types.add(media_type)
        path = report.package_dir / name
        try:
            file_entry = path.lstat()
        except OSError:
            report.error("FILE_MISSING", f"Declared file is missing or unreadable: {name}")
            continue
        if stat.S_ISLNK(file_entry.st_mode) or not stat.S_ISREG(file_entry.st_mode):
            report.error("FILE_TYPE", f"Declared file is not a regular file: {name}")
            continue
        if file_entry.st_size <= 0:
            report.error("FILE_EMPTY", f"Declared file is empty: {name}")
            continue
        if file_entry.st_size != entry.get("bytes"):
            report.error("FILE_SIZE", f"Byte count differs for {name}")
        else:
            report.check("FILE_SIZE", f"Byte count matches for {name}")
        if not _valid_hash(entry.get("sha256")):
            report.error("FILE_HASH_STRUCTURE", f"File {name} has invalid SHA-256 structure")
        elif sha256_file(path) != entry["sha256"]:
            report.error("FILE_HASH", f"SHA-256 mismatch for {name}")
        else:
            report.check("FILE_HASH", f"SHA-256 matches for {name}")
        try:
            if media_type == "application/pdf":
                width_mm, height_mm = _pdf_dimensions(path)
                facts: dict[str, Any] = {"width_mm": width_mm, "height_mm": height_mm}
            elif media_type == "image/svg+xml":
                width_mm, height_mm, svg_text = _svg_dimensions(path)
                facts = {"width_mm": width_mm, "height_mm": height_mm}
            elif media_type == "image/png":
                width_mm, height_mm, pixels, dpi = _png_facts(path)
                facts = {"width_mm": width_mm, "height_mm": height_mm, "pixels": pixels, "dpi": dpi}
            else:
                report.error("FILE_TYPE", f"Unsupported declared media type: {media_type}")
                continue
        except (OSError, ValueError) as exc:
            report.error("FILE_READABILITY", f"Cannot read {name}: {exc}")
            continue
        actual_by_type[media_type] = facts
        report.check("FILE_READABILITY", f"{name} is readable as {media_type}")
        for axis, actual, declared in [
            ("width", facts["width_mm"], entry.get("width_mm")),
            ("height", facts["height_mm"], entry.get("height_mm")),
        ]:
            if not _is_number(declared) or not _close(actual, float(declared), size_tolerance_mm):
                report.error(
                    "FILE_DIMENSION",
                    f"Actual {axis} differs from manifest for {name}",
                    actual_mm=actual,
                    declared_mm=declared,
                )
            elif declared_width is not None:
                render_value = declared_width if axis == "width" else declared_height
                if not _close(actual, float(render_value), size_tolerance_mm):
                    report.error(
                        "RENDER_DIMENSION",
                        f"Actual {axis} differs from render canvas for {name}",
                        actual_mm=actual,
                        render_mm=render_value,
                    )
                else:
                    report.check("FILE_DIMENSION", f"{name} {axis} matches manifest and canvas")
        if media_type == "image/png":
            declared_pixels = entry.get("pixels")
            if declared_pixels != facts["pixels"]:
                report.error("PNG_PIXELS", "PNG pixel dimensions differ from manifest")
            else:
                report.check("PNG_PIXELS", "PNG pixel dimensions match manifest")
            declared_dpi = entry.get("dpi")
            render_dpi = render.get("png_dpi")
            if not isinstance(declared_dpi, list) or len(declared_dpi) != 2 or not all(_is_number(item) for item in declared_dpi):
                report.error("PNG_DPI", "Manifest PNG DPI must contain two finite numbers")
            elif any(not _close(a, float(b), dpi_tolerance) for a, b in zip(facts["dpi"], declared_dpi)):
                report.error("PNG_DPI", "Actual PNG DPI differs from file manifest", actual=facts["dpi"], declared=declared_dpi)
            elif not _is_number(render_dpi) or any(not _close(item, float(render_dpi), dpi_tolerance) for item in facts["dpi"]):
                report.error("PNG_DPI", "Actual PNG DPI differs from render DPI", actual=facts["dpi"], render=render_dpi)
            else:
                report.check("PNG_DPI", "PNG DPI matches file and render metadata")
    missing_types = expected_types - found_types
    extra_types = found_types - expected_types
    if missing_types:
        report.error("FILE_SET", f"Missing required media types: {', '.join(sorted(missing_types))}")
    if extra_types:
        report.error("FILE_SET", f"Unexpected media types: {', '.join(sorted(extra_types))}")
    if not missing_types and not extra_types:
        report.check("FILE_SET", "PDF, SVG, and PNG entries are all present")
    return actual_by_type, svg_text


def _validate_profile_constraints(
    manifest: dict[str, Any], profile: dict[str, Any] | None, report: Report, dpi_tolerance: float
) -> None:
    if profile is None:
        return
    render = manifest["render"]
    height = render.get("height_mm")
    max_height = profile.get("max_height_mm")
    if _is_number(max_height) and _is_number(height):
        if height > max_height + 0.01:
            report.error("PROFILE_HEIGHT", "Figure exceeds profile maximum height", height_mm=height, maximum_mm=max_height)
        else:
            report.check("PROFILE_HEIGHT", "Figure does not exceed profile maximum height")
    font_config = profile.get("font", {})
    font_size = render.get("font_size_pt")
    if font_config.get("range_is_official") and _is_number(font_size):
        minimum, maximum = font_config.get("min_size_pt"), font_config.get("max_size_pt")
        if not _is_number(minimum) or not _is_number(maximum):
            report.error("PROFILE_FONT_CONFIG", "Official font range in profile is malformed")
        elif font_size < minimum or font_size > maximum:
            report.error("PROFILE_FONT_SIZE", "Font size is outside profile range", size_pt=font_size, allowed=[minimum, maximum])
        else:
            report.check("PROFILE_FONT_SIZE", "Font size is within the official profile range")
    if not isinstance(render.get("font_family"), str) or not render["font_family"].strip():
        report.error("FONT_STRUCTURE", "Resolved font family is missing")
    else:
        report.check("FONT_STRUCTURE", "Resolved font family is recorded")
    if render.get("font_fallback_used"):
        report.warning("FONT_FALLBACK", "A profile-preferred font was unavailable; visually review the recorded fallback")
    if profile.get("dpi_is_official_minimum"):
        minimum_dpi = profile.get("png_dpi")
        actual_dpi = render.get("png_dpi")
        if not _is_number(minimum_dpi) or not _is_number(actual_dpi) or actual_dpi < minimum_dpi - dpi_tolerance:
            report.error("PROFILE_DPI", "PNG DPI is below the profile minimum", actual=actual_dpi, minimum=minimum_dpi)
        else:
            report.check("PROFILE_DPI", "PNG DPI meets the profile minimum")
    size_name = render.get("size_name")
    preset = profile.get("size_presets", {}).get(size_name)
    if isinstance(preset, dict) and _is_number(preset.get("width_mm")) and _is_number(render.get("width_mm")):
        if not _close(float(render["width_mm"]), float(preset["width_mm"]), 0.01):
            report.warning("PROFILE_WIDTH_OVERRIDE", "Figure width overrides the selected profile preset; confirm the exact venue request")


def _parse_hex(color: Any) -> tuple[float, float, float] | None:
    if not isinstance(color, str) or not re.fullmatch(r"#[0-9A-Fa-f]{6}", color):
        return None
    return tuple(int(color[index : index + 2], 16) / 255.0 for index in (1, 3, 5))


def _cvd_transform(rgb: tuple[float, float, float]) -> tuple[float, float, float]:
    matrix = (
        (0.367, 0.861, -0.228),
        (0.280, 0.673, 0.047),
        (-0.012, 0.043, 0.969),
    )
    return tuple(max(0.0, min(1.0, sum(row[index] * rgb[index] for index in range(3)))) for row in matrix)


def _distance(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def _validate_accessibility(manifest: dict[str, Any], report: Report) -> None:
    figure = manifest["figure"]
    chart = figure.get("chart")
    if chart in {"hist", "ecdf"} and not figure.get("denominator"):
        report.warning(
            "DENOMINATOR",
            "Distribution denominator is not recorded; state attempted, completed, valid, filtered, and censored populations as applicable",
        )
    series = figure.get("series")
    if not isinstance(series, list) or not series:
        report.error("SERIES_STRUCTURE", "Figure series metadata is missing or empty")
        return
    for index, item in enumerate(series):
        if not isinstance(item, dict) or not isinstance(item.get("style"), dict):
            report.error("SERIES_STRUCTURE", f"Series {index} lacks style metadata")
            return
        if not isinstance(item.get("label"), str) or not item["label"].strip():
            report.warning("SERIES_LABEL", f"Series {index} has no useful display label")
    if len(series) <= 1 or chart == "heatmap":
        return
    required_style = {
        "line": ("marker", "linestyle"),
        "scatter": ("marker",),
        "bar": ("hatch",),
        "hist": ("linestyle",),
        "ecdf": ("marker", "linestyle"),
    }.get(chart, ())
    signatures = [tuple(item["style"].get(field) for field in required_style) for item in series]
    if required_style and len(signatures) != len(set(signatures)):
        report.warning("REDUNDANT_STYLE", "Multiple series share the same non-color encoding; inspect grayscale legibility")
    else:
        report.check("REDUNDANT_STYLE", "Multiple series have distinct non-color encodings")
    colors = [_parse_hex(item["style"].get("color")) for item in series]
    if any(color is None for color in colors):
        report.warning("COLOR_STRUCTURE", "One or more series colors cannot be mechanically parsed")
        return
    transformed = [_cvd_transform(color) for color in colors if color is not None]
    close_pairs = []
    for (first_index, first), (second_index, second) in combinations(enumerate(transformed), 2):
        if _distance(first, second) < 0.12:
            close_pairs.append([series[first_index]["label"], series[second_index]["label"]])
    if close_pairs:
        report.warning(
            "COLOR_VISION_APPROXIMATION",
            "Approximate deuteranopia transform finds close color pairs; rely on redundant styles and visually review",
            pairs=close_pairs,
        )
    else:
        report.check("COLOR_VISION_APPROXIMATION", "No very close pair found by the approximate color transform")


def _validate_figure_semantics(manifest: dict[str, Any], report: Report, svg_text: str | None) -> None:
    input_info, figure, qa, render = manifest["input"], manifest["figure"], manifest["qa"], manifest["render"]
    if not isinstance(input_info.get("row_count"), int) or input_info["row_count"] <= 0:
        report.error("EMPTY_DATA", "Input row count is missing or non-positive")
    else:
        report.check("EMPTY_DATA", "Input row count is positive")
    if not isinstance(figure.get("plotted_observation_count"), int) or figure["plotted_observation_count"] <= 0:
        report.error("EMPTY_PLOT", "Plotted observation count is missing or non-positive")
    else:
        report.check("EMPTY_PLOT", "Plotted observation count is positive")
    dropped = qa.get("dropped_observation_count", 0)
    if isinstance(dropped, int) and dropped > 0:
        report.warning("NONFINITE_DROPPED", "Non-finite or missing observations were explicitly dropped; audit every omission", count=dropped)
    filter_info = qa.get("filter", {})
    if isinstance(filter_info, dict) and filter_info.get("excluded_rows", 0):
        report.warning("FILTERED_ROWS", "An explicit filter excluded source rows; report denominator and failure states", count=filter_info.get("excluded_rows"))
    for field in ("caption", "alt_text"):
        value = figure.get(field)
        if not isinstance(value, str) or not value.strip():
            report.warning("ACCESSIBLE_TEXT", f"Figure {field} is empty")
        elif figure.get(f"{field}_generated"):
            report.warning("GENERATED_TEXT", f"Figure {field} was mechanically generated and needs study-aware review")
    chart = figure.get("chart")
    if not isinstance(figure.get("xlabel"), str) or not figure.get("xlabel", "").strip():
        report.warning("AXIS_LABEL", "X-axis label is missing; add a descriptive label and units where applicable")
    if chart == "heatmap":
        if not isinstance(figure.get("ylabel"), str) or not figure.get("ylabel", "").strip():
            report.warning("AXIS_LABEL", "Heatmap y-axis label is missing")
        if not isinstance(figure.get("colorbar_label"), str) or not figure.get("colorbar_label", "").strip():
            report.warning("COLORBAR_LABEL", "Heatmap colorbar label is missing; state quantity, denominator, and units")
        if figure.get("missing_cell_count", 0):
            report.warning("HEATMAP_MISSING", "Heatmap contains missing cells; verify that the missing-color encoding and caption explain them", count=figure.get("missing_cell_count"))
    elif not isinstance(figure.get("ylabel"), str) or not figure.get("ylabel", "").strip():
        if chart not in {"hist", "ecdf"}:
            report.warning("AXIS_LABEL", "Y-axis label is missing; add a descriptive label and units where applicable")
    probes = qa.get("mechanical_probes", {})
    if isinstance(probes, dict):
        if probes.get("canvas_crop_risk_count", 0):
            report.warning("CROP_APPROXIMATION", "Artist bounds suggest possible clipping; inspect all edges", count=probes.get("canvas_crop_risk_count"))
        if probes.get("text_overlap_pair_count", 0):
            report.warning("TEXT_OVERLAP_APPROXIMATION", "Text rectangles overlap mechanically; inspect labels and annotations", count=probes.get("text_overlap_pair_count"))
        if probes.get("legend_data_overlap_count", 0):
            report.warning("LEGEND_OVERLAP_APPROXIMATION", "Legend rectangle intersects a data-artist rectangle; inspect occlusion", count=probes.get("legend_data_overlap_count"))
    if render.get("crop_mode") != "fixed_canvas" or render.get("bbox_inches") is not None:
        report.warning("CROP_MODE", "Export did not record the standard fixed-canvas crop mode; visually inspect dimensions and edges")
    if svg_text is not None:
        font_family = render.get("font_family")
        if isinstance(font_family, str) and font_family not in svg_text:
            report.warning("SVG_FONT", "Resolved font-family name was not found literally in SVG; inspect font preservation")


def validate_package(
    package_dir: Path,
    *,
    manifest_name: str = "manifest.json",
    profiles_path: Path = DEFAULT_PROFILES_PATH,
    data_path: Path | None = None,
    spec_path: Path | None = None,
    dpi_tolerance: float = 1.0,
    size_tolerance_mm: float = 0.25,
) -> dict[str, Any]:
    package_dir = Path(os.path.abspath(package_dir))
    report = Report(package_dir)
    try:
        package_entry = package_dir.lstat()
    except OSError:
        report.error("PACKAGE_DIRECTORY", f"Package directory does not exist or is unreadable: {package_dir}")
        return report.as_dict()
    if stat.S_ISLNK(package_entry.st_mode) or not stat.S_ISDIR(package_entry.st_mode):
        report.error("PACKAGE_DIRECTORY", f"Package path must be a plain directory: {package_dir}")
        return report.as_dict()
    manifest_path = package_dir / manifest_name
    manifest = _load_json(manifest_path, report, "MANIFEST_JSON")
    if manifest is None:
        return report.as_dict()
    if not _check_manifest_structure(manifest, report):
        return report.as_dict()
    _validate_sources(manifest, report, data_path, spec_path)
    profile = _validate_profile(manifest, report, profiles_path)
    _, svg_text = _validate_files(manifest, report, dpi_tolerance, size_tolerance_mm)
    _validate_profile_constraints(manifest, profile, report, dpi_tolerance)
    _validate_accessibility(manifest, report)
    _validate_figure_semantics(manifest, report, svg_text)
    report.warning(
        "SCIENTIFIC_REVIEW_REQUIRED",
        "Mechanical validation cannot approve data semantics, transformations, statistics, exclusions, denominators, or conclusions.",
    )
    report.warning(
        "VISUAL_REVIEW_REQUIRED",
        "Inspect PDF/SVG and PNG at final physical size for legibility, clipping, hierarchy, color perception, and overlap.",
    )
    report.warning(
        "TEXT_REVIEW_REQUIRED",
        "Review caption and alt text for study context, complementary information, and unsupported claims.",
    )
    if manifest["profile"].get("id") != "draft":
        report.warning(
            "VENUE_RECHECK_REQUIRED",
            "This is a project submission profile, not an official template; recheck the exact current venue and article-type instructions.",
        )
    return report.as_dict()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate mechanical facts in a publication-figure package."
    )
    parser.add_argument("package", type=Path, help="Directory containing manifest.json and figure files")
    parser.add_argument("--manifest", default="manifest.json", help="Manifest filename")
    parser.add_argument("--profiles", type=Path, default=DEFAULT_PROFILES_PATH, help="Submission profile config")
    parser.add_argument("--data", type=Path, help="Optional original data file for SHA-256 verification")
    parser.add_argument("--spec", type=Path, help="Optional original spec file for raw SHA-256 verification")
    parser.add_argument("--dpi-tolerance", type=float, default=1.0, help="DPI comparison tolerance")
    parser.add_argument("--size-tolerance-mm", type=float, default=0.25, help="Dimension comparison tolerance")
    parser.add_argument("--report", type=Path, help="Optional JSON report output path")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.dpi_tolerance < 0 or args.size_tolerance_mm < 0:
        print(json.dumps({"status": "error", "message": "tolerances must be non-negative"}), file=sys.stderr)
        return 2
    result = validate_package(
        args.package,
        manifest_name=args.manifest,
        profiles_path=args.profiles,
        data_path=args.data,
        spec_path=args.spec,
        dpi_tolerance=args.dpi_tolerance,
        size_tolerance_mm=args.size_tolerance_mm,
    )
    rendered = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 1 if result["summary"]["error_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
