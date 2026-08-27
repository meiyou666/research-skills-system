#!/usr/bin/env python3
"""Render a deterministic publication-figure package from CSV/JSON and JSON spec."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import random
import re
import stat
import sys
import warnings
from collections import OrderedDict
from pathlib import Path
from typing import Any, Iterable

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from matplotlib import font_manager
from matplotlib.legend import Legend
from matplotlib.text import Text
from PIL import Image


SCRIPT_PATH = Path(__file__).resolve()
SKILL_DIR = SCRIPT_PATH.parent.parent
DEFAULT_PROFILES_PATH = SKILL_DIR / "references" / "submission_profiles.json"
SCHEMA_VERSION = "1.0"
DEFAULT_SEED = 1729
MM_PER_INCH = 25.4

PALETTE = [
    "#0072B2",  # blue
    "#D55E00",  # vermillion
    "#009E73",  # bluish green
    "#CC79A7",  # reddish purple
    "#E69F00",  # orange
    "#56B4E9",  # sky blue
    "#000000",  # black
    "#F0E442",  # yellow; intentionally last because of white-background contrast
]
MARKERS = ["o", "s", "^", "D", "v", "P", "X", "<", ">", "h"]
LINESTYLES = ["-", "--", "-.", ":"]
HATCHES = ["", "///", "\\\\", "xx", "..", "++", "oo", "**"]
SUPPORTED_CHARTS = {"line", "scatter", "bar", "hist", "ecdf", "heatmap"}


class FigureSpecError(ValueError):
    """Raised when data or a figure spec cannot be rendered safely."""


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json_object(source: str, label: str) -> tuple[dict[str, Any], dict[str, Any]]:
    candidate = Path(source)
    if not source.lstrip().startswith("{") and candidate.is_file():
        raw = candidate.read_bytes()
        source_name = candidate.name
    else:
        raw = source.encode("utf-8")
        source_name = "inline-json"
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FigureSpecError(f"{label} must be a UTF-8 JSON object: {exc}") from exc
    if not isinstance(value, dict):
        raise FigureSpecError(f"{label} must be a JSON object")
    try:
        canonical = canonical_json_bytes(value)
    except (TypeError, ValueError) as exc:
        raise FigureSpecError(f"{label} contains a non-standard or non-finite JSON value: {exc}") from exc
    provenance = {
        "source": source_name,
        "raw_sha256": sha256_bytes(raw),
        "canonical_sha256": sha256_bytes(canonical),
    }
    return value, provenance


def _records_from_json(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        records = value
    elif isinstance(value, dict) and isinstance(value.get("records"), list):
        records = value["records"]
    elif isinstance(value, dict) and isinstance(value.get("data"), list):
        records = value["data"]
    elif isinstance(value, dict) and value and all(isinstance(item, list) for item in value.values()):
        lengths = {len(item) for item in value.values()}
        if len(lengths) != 1:
            raise FigureSpecError("JSON column arrays must have equal lengths")
        count = next(iter(lengths))
        records = [{name: values[index] for name, values in value.items()} for index in range(count)]
    else:
        raise FigureSpecError(
            "JSON data must be a record list, an object with records/data, or equal-length column arrays"
        )
    if not records:
        raise FigureSpecError("input data is empty")
    if not all(isinstance(record, dict) for record in records):
        raise FigureSpecError("every JSON record must be an object")
    columns = list(records[0].keys())
    if not columns:
        raise FigureSpecError("input records have no columns")
    expected = set(columns)
    for index, record in enumerate(records, start=1):
        if set(record) != expected:
            raise FigureSpecError(f"JSON record {index} has inconsistent columns")
    return [{column: record[column] for column in columns} for record in records]


def _records_from_csv(raw: bytes) -> list[dict[str, Any]]:
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise FigureSpecError("CSV data must be UTF-8") from exc
    rows = list(csv.reader(io.StringIO(text, newline="")))
    if not rows:
        raise FigureSpecError("input data is empty")
    header = rows[0]
    if not header or any(not column.strip() for column in header):
        raise FigureSpecError("CSV must have non-empty header names")
    if len(set(header)) != len(header):
        raise FigureSpecError("CSV header names must be unique")
    records: list[dict[str, Any]] = []
    for row_number, row in enumerate(rows[1:], start=2):
        if not row or all(not value.strip() for value in row):
            continue
        if len(row) != len(header):
            raise FigureSpecError(
                f"CSV row {row_number} has {len(row)} fields; expected {len(header)}"
            )
        records.append(dict(zip(header, row)))
    if not records:
        raise FigureSpecError("input data has headers but no records")
    return records


def load_data(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not path.is_file():
        raise FigureSpecError(f"data file does not exist: {path}")
    raw = path.read_bytes()
    suffix = path.suffix.lower()
    if suffix == ".csv":
        records = _records_from_csv(raw)
        data_format = "csv"
    elif suffix == ".json":
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise FigureSpecError(f"invalid JSON data: {exc}") from exc
        records = _records_from_json(value)
        data_format = "json"
    else:
        raise FigureSpecError("data filename must end in .csv or .json")
    provenance = {
        "source": path.name,
        "format": data_format,
        "sha256": sha256_bytes(raw),
        "bytes": len(raw),
        "row_count": len(records),
        "columns": list(records[0]),
    }
    return records, provenance


def load_profiles(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        raw = path.read_bytes()
        config = json.loads(raw.decode("utf-8"))
    except OSError as exc:
        raise FigureSpecError(f"cannot read submission profiles: {exc}") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FigureSpecError(f"invalid submission profiles JSON: {exc}") from exc
    if not isinstance(config, dict) or not isinstance(config.get("profiles"), dict):
        raise FigureSpecError("submission profile file is missing the profiles object")
    return config, {
        "source": path.name,
        "file_sha256": sha256_bytes(raw),
        "verified_on": config.get("verified_on"),
        "disclaimer": config.get("disclaimer"),
    }


def require_columns(records: list[dict[str, Any]], columns: Iterable[str]) -> None:
    available = set(records[0])
    missing = [column for column in columns if column not in available]
    if missing:
        raise FigureSpecError(f"missing data columns: {', '.join(missing)}")


def apply_filter(
    records: list[dict[str, Any]], filter_spec: Any
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if filter_spec is None:
        return records, {"applied": False, "excluded_rows": 0, "rules": {}}
    if not isinstance(filter_spec, dict) or not filter_spec:
        raise FigureSpecError("filter must be a non-empty object mapping columns to allowed values")
    require_columns(records, filter_spec)
    allowed_by_column: dict[str, list[Any]] = {}
    for column, allowed in filter_spec.items():
        allowed_values = allowed if isinstance(allowed, list) else [allowed]
        if not allowed_values:
            raise FigureSpecError(f"filter for {column!r} has no allowed values")
        allowed_by_column[column] = allowed_values
    selected = [
        record
        for record in records
        if all(record[column] in allowed for column, allowed in allowed_by_column.items())
    ]
    if not selected:
        raise FigureSpecError("filter excludes every input row")
    return selected, {
        "applied": True,
        "excluded_rows": len(records) - len(selected),
        "rules": allowed_by_column,
    }


def finite_float(value: Any, field: str, row_number: int) -> float:
    if isinstance(value, bool) or value is None or (isinstance(value, str) and not value.strip()):
        raise FigureSpecError(f"row {row_number}: {field!r} is missing or not numeric")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise FigureSpecError(f"row {row_number}: {field!r} is not numeric: {value!r}") from exc
    if not math.isfinite(number):
        raise FigureSpecError(f"row {row_number}: {field!r} is non-finite: {value!r}")
    return number


def category_value(value: Any, field: str, row_number: int) -> str:
    if value is None or (isinstance(value, str) and not value.strip()):
        raise FigureSpecError(f"row {row_number}: {field!r} is missing")
    return str(value)


def validate_spec(spec: dict[str, Any]) -> None:
    chart = spec.get("chart")
    if chart not in SUPPORTED_CHARTS:
        raise FigureSpecError(
            f"chart must be one of {', '.join(sorted(SUPPORTED_CHARTS))}; got {chart!r}"
        )
    if not isinstance(spec.get("x"), str) or not spec["x"]:
        raise FigureSpecError("spec.x must name a data column")
    if chart in {"line", "scatter", "bar"}:
        y = spec.get("y")
        if not isinstance(y, (str, list)) or (isinstance(y, list) and not y):
            raise FigureSpecError(f"{chart} requires spec.y as a column name or non-empty list")
        if isinstance(y, list) and not all(isinstance(item, str) and item for item in y):
            raise FigureSpecError("every item in spec.y must be a column name")
        if spec.get("series") is not None and not isinstance(y, str):
            raise FigureSpecError("long-form spec.series requires exactly one y column")
    if chart == "heatmap":
        if not isinstance(spec.get("y"), str) or not spec["y"]:
            raise FigureSpecError("heatmap requires spec.y as the row/category column")
        if not isinstance(spec.get("value"), str) or not spec["value"]:
            raise FigureSpecError("heatmap requires spec.value as the cell-value column")
    if chart in {"hist", "ecdf"} and spec.get("y") is not None:
        raise FigureSpecError(f"{chart} uses spec.x as the measured value; omit spec.y")
    if spec.get("series") is not None and not isinstance(spec["series"], str):
        raise FigureSpecError("spec.series must name a data column")
    if spec.get("nonfinite", "error") not in {"error", "drop"}:
        raise FigureSpecError("spec.nonfinite must be 'error' or 'drop'")
    for scale_field in ("xscale", "yscale"):
        if spec.get(scale_field, "linear") not in {"linear", "log", "symlog", "logit"}:
            raise FigureSpecError(f"{scale_field} must be linear, log, symlog, or logit")
    if chart == "heatmap" and (
        spec.get("xscale", "linear") != "linear" or spec.get("yscale", "linear") != "linear"
    ):
        raise FigureSpecError("heatmap categorical axes support only linear scales")
    if chart == "bar" and spec.get("xscale", "linear") != "linear":
        raise FigureSpecError("bar categorical x axes support only a linear scale")
    if chart == "ecdf" and spec.get("yscale", "linear") != "linear":
        raise FigureSpecError("ECDF probability axes support only a linear y scale")


def _series_label(spec: dict[str, Any], key: Any, fallback: str) -> str:
    labels = spec.get("series_labels", {})
    if not isinstance(labels, dict):
        raise FigureSpecError("series_labels must be an object")
    return str(labels.get(str(key), labels.get(key, fallback)))


def _style(index: int) -> dict[str, Any]:
    return {
        "color": PALETTE[index % len(PALETTE)],
        "marker": MARKERS[index % len(MARKERS)],
        "linestyle": LINESTYLES[index % len(LINESTYLES)],
        "hatch": HATCHES[index % len(HATCHES)],
    }


def _numeric_or_drop(
    record: dict[str, Any],
    fields: list[str],
    row_number: int,
    policy: str,
    dropped: list[dict[str, Any]],
) -> list[float] | None:
    try:
        return [finite_float(record[field], field, row_number) for field in fields]
    except FigureSpecError as exc:
        if policy == "drop":
            dropped.append({"row": row_number, "reason": str(exc)})
            return None
        raise


def prepare_xy_series(
    records: list[dict[str, Any]], spec: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    chart = spec["chart"]
    x_column = spec["x"]
    y_spec = spec["y"]
    y_columns = [y_spec] if isinstance(y_spec, str) else list(y_spec)
    group_column = spec.get("series")
    required = [x_column, *y_columns]
    if group_column:
        required.append(group_column)
    require_columns(records, required)
    policy = spec.get("nonfinite", "error")
    dropped: list[dict[str, Any]] = []
    prepared: list[dict[str, Any]] = []

    if group_column:
        groups: OrderedDict[str, list[tuple[int, dict[str, Any]]]] = OrderedDict()
        raw_group_values: dict[str, Any] = {}
        for row_number, record in enumerate(records, start=1):
            raw_group = record[group_column]
            key = category_value(raw_group, group_column, row_number)
            groups.setdefault(key, []).append((row_number, record))
            raw_group_values.setdefault(key, raw_group)
        series_inputs = [
            (key, _series_label(spec, raw_group_values[key], key), y_columns[0], rows)
            for key, rows in groups.items()
        ]
    else:
        indexed_records = list(enumerate(records, start=1))
        series_inputs = [
            (column, _series_label(spec, column, column), column, indexed_records)
            for column in y_columns
        ]

    for index, (key, label, y_column, rows) in enumerate(series_inputs):
        x_values: list[float | str] = []
        y_values: list[float] = []
        for row_number, record in rows:
            numbers = _numeric_or_drop(record, [y_column], row_number, policy, dropped)
            if numbers is None:
                continue
            if chart == "bar":
                try:
                    x_value: float | str = category_value(record[x_column], x_column, row_number)
                except FigureSpecError as exc:
                    if policy == "drop":
                        dropped.append({"row": row_number, "reason": str(exc)})
                        continue
                    raise
            else:
                x_number = _numeric_or_drop(record, [x_column], row_number, policy, dropped)
                if x_number is None:
                    continue
                x_value = x_number[0]
            x_values.append(x_value)
            y_values.append(numbers[0])
        if not x_values:
            raise FigureSpecError(f"series {label!r} has no finite plottable observations")
        if spec.get("sort_x") and chart != "bar":
            ordered = sorted(zip(x_values, y_values), key=lambda pair: pair[0])
            x_values, y_values = map(list, zip(*ordered))
        prepared.append(
            {
                "key": str(key),
                "label": label,
                "source_y": y_column,
                "x": x_values,
                "values": y_values,
                "style": _style(index),
            }
        )
    return prepared, dropped


def prepare_distribution_series(
    records: list[dict[str, Any]], spec: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    x_column = spec["x"]
    group_column = spec.get("series")
    required = [x_column] + ([group_column] if group_column else [])
    require_columns(records, required)
    policy = spec.get("nonfinite", "error")
    dropped: list[dict[str, Any]] = []
    groups: OrderedDict[str, list[tuple[int, dict[str, Any]]]] = OrderedDict()
    if group_column:
        raw_values: dict[str, Any] = {}
        for row_number, record in enumerate(records, start=1):
            raw_group = record[group_column]
            key = category_value(raw_group, group_column, row_number)
            groups.setdefault(key, []).append((row_number, record))
            raw_values.setdefault(key, raw_group)
        series_inputs = [
            (key, _series_label(spec, raw_values[key], key), rows)
            for key, rows in groups.items()
        ]
    else:
        series_inputs = [
            (x_column, _series_label(spec, x_column, x_column), list(enumerate(records, start=1)))
        ]
    prepared: list[dict[str, Any]] = []
    for index, (key, label, rows) in enumerate(series_inputs):
        values: list[float] = []
        for row_number, record in rows:
            numbers = _numeric_or_drop(record, [x_column], row_number, policy, dropped)
            if numbers is not None:
                values.append(numbers[0])
        if not values:
            raise FigureSpecError(f"series {label!r} has no finite observations")
        prepared.append(
            {
                "key": str(key),
                "label": label,
                "source_x": x_column,
                "values": values,
                "style": _style(index),
            }
        )
    return prepared, dropped


def prepare_heatmap(
    records: list[dict[str, Any]], spec: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    x_column, y_column, value_column = spec["x"], spec["y"], spec["value"]
    require_columns(records, [x_column, y_column, value_column])
    policy = spec.get("nonfinite", "error")
    dropped: list[dict[str, Any]] = []
    cells: dict[tuple[str, str], float] = {}
    x_values: list[str] = []
    y_values: list[str] = []
    for row_number, record in enumerate(records, start=1):
        try:
            x_value = category_value(record[x_column], x_column, row_number)
            y_value = category_value(record[y_column], y_column, row_number)
        except FigureSpecError as exc:
            if policy == "drop":
                dropped.append({"row": row_number, "reason": str(exc)})
                continue
            raise
        # Preserve categorical support even when this row has no usable cell
        # value.  A declared category with only missing/non-finite observations
        # must remain visible as missing rather than disappearing from the plot.
        if x_value not in x_values:
            x_values.append(x_value)
        if y_value not in y_values:
            y_values.append(y_value)
        number = _numeric_or_drop(record, [value_column], row_number, policy, dropped)
        if number is None:
            continue
        key = (x_value, y_value)
        if key in cells:
            raise FigureSpecError(
                f"heatmap cell ({x_value!r}, {y_value!r}) is duplicated; aggregate explicitly upstream"
            )
        cells[key] = number[0]
    if not cells:
        raise FigureSpecError("heatmap has no finite cells")
    if spec.get("sort_x"):
        x_values = sorted(x_values)
    if spec.get("sort_y"):
        y_values = sorted(y_values)
    if "x_order" in spec:
        x_values = _validated_order(spec["x_order"], x_values, "x_order")
    if "y_order" in spec:
        y_values = _validated_order(spec["y_order"], y_values, "y_order")
    matrix = np.full((len(y_values), len(x_values)), np.nan, dtype=float)
    for y_index, y_value in enumerate(y_values):
        for x_index, x_value in enumerate(x_values):
            if (x_value, y_value) in cells:
                matrix[y_index, x_index] = cells[(x_value, y_value)]
    return {
        "x_values": x_values,
        "y_values": y_values,
        "matrix": matrix,
        "source_value": value_column,
        "missing_cells": int(np.isnan(matrix).sum()),
    }, dropped


def _validated_order(value: Any, actual: list[str], field: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, (str, int, float)) for item in value):
        raise FigureSpecError(f"{field} must be a list of category values")
    order = [str(item) for item in value]
    if len(set(order)) != len(order):
        raise FigureSpecError(f"{field} must not contain duplicate categories")
    missing_observed = set(actual) - set(order)
    if missing_observed:
        raise FigureSpecError(
            f"{field} must contain every observed category; missing: {', '.join(sorted(missing_observed))}"
        )
    return order


def _require_scale_domain(values: Iterable[float], scale: str, axis: str) -> None:
    values = list(values)
    if scale == "log" and any(value <= 0 for value in values):
        raise FigureSpecError(f"{axis}scale='log' requires every plotted {axis} value to be positive")
    if scale == "logit" and any(value <= 0 or value >= 1 for value in values):
        raise FigureSpecError(f"{axis}scale='logit' requires every plotted {axis} value to be between 0 and 1")


def validate_scale_domains(chart: str, prepared: Any, spec: dict[str, Any]) -> None:
    xscale, yscale = spec.get("xscale", "linear"), spec.get("yscale", "linear")
    if chart in {"line", "scatter"}:
        for item in prepared:
            _require_scale_domain(item["x"], xscale, "x")
            _require_scale_domain(item["values"], yscale, "y")
    elif chart == "bar":
        for item in prepared:
            _require_scale_domain(item["values"], yscale, "y")
    elif chart in {"hist", "ecdf"}:
        for item in prepared:
            _require_scale_domain(item["values"], xscale, "x")


def resolve_font(profile: dict[str, Any], override: Any) -> tuple[str, str, bool]:
    if override is not None and (not isinstance(override, str) or not override.strip()):
        raise FigureSpecError("font_family must be a non-empty string")
    font_config = profile["font"]
    candidates = [override] if override else list(font_config.get("preferred", []))
    fallback = font_config.get("fallback", "DejaVu Sans")
    for candidate in candidates:
        try:
            path = font_manager.findfont(candidate, fallback_to_default=False)
            return str(candidate), Path(path).name, False
        except ValueError:
            continue
    try:
        path = font_manager.findfont(fallback, fallback_to_default=False)
    except ValueError as exc:
        raise FigureSpecError(f"no configured font is available; fallback {fallback!r} is missing") from exc
    return str(fallback), Path(path).name, bool(candidates and fallback not in candidates)


def positive_float(value: Any, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise FigureSpecError(f"{field} must be numeric") from exc
    if not math.isfinite(number) or number <= 0:
        raise FigureSpecError(f"{field} must be finite and greater than zero")
    return number


def resolve_render_settings(
    spec: dict[str, Any],
    profile_id: str,
    profile: dict[str, Any],
    size_override: str | None,
    dpi_override: int | None,
    seed_override: int | None,
) -> dict[str, Any]:
    size_name = size_override or spec.get("size") or profile["default_size"]
    presets = profile.get("size_presets", {})
    if size_name not in presets:
        raise FigureSpecError(
            f"unknown size {size_name!r} for profile {profile_id!r}; choose from {', '.join(presets)}"
        )
    preset = presets[size_name]
    width_mm = positive_float(spec.get("width_mm", preset["width_mm"]), "width_mm")
    height_mm = positive_float(spec.get("height_mm", preset["height_mm"]), "height_mm")
    dpi = int(dpi_override if dpi_override is not None else spec.get("dpi", profile["png_dpi"]))
    if dpi <= 0 or dpi > 2400:
        raise FigureSpecError("dpi must be between 1 and 2400")
    font_family, font_file, used_fallback = resolve_font(profile, spec.get("font_family"))
    font_size = positive_float(
        spec.get("font_size_pt", profile["font"]["default_size_pt"]), "font_size_pt"
    )
    seed = int(seed_override if seed_override is not None else spec.get("seed", DEFAULT_SEED))
    return {
        "profile_id": profile_id,
        "size_name": size_name,
        "size_basis": preset.get("basis"),
        "width_mm": width_mm,
        "height_mm": height_mm,
        "dpi": dpi,
        "font_family": font_family,
        "font_file": font_file,
        "font_fallback_used": used_fallback,
        "font_size_pt": font_size,
        "seed": seed,
    }


def _apply_axes_options(ax: Any, spec: dict[str, Any], chart: str) -> None:
    if spec.get("title"):
        ax.set_title(str(spec["title"]))
    if spec.get("xlabel"):
        ax.set_xlabel(str(spec["xlabel"]))
    if spec.get("ylabel"):
        ax.set_ylabel(str(spec["ylabel"]))
    for axis_name, setter in (("xscale", ax.set_xscale), ("yscale", ax.set_yscale)):
        scale = spec.get(axis_name, "linear")
        if scale not in {"linear", "log", "symlog", "logit"}:
            raise FigureSpecError(f"{axis_name} must be linear, log, symlog, or logit")
        if chart == "heatmap":
            if scale != "linear":
                raise FigureSpecError(f"{axis_name} is not supported for categorical heatmaps")
            # imshow plus explicit ticks already establishes the categorical
            # coordinate system.  Calling set_*scale("linear") afterwards
            # replaces its fixed locator/formatter with numeric ticks.
            continue
        setter(scale)
    if "xlim" in spec:
        _set_limit(ax.set_xlim, spec["xlim"], "xlim")
    if "ylim" in spec:
        _set_limit(ax.set_ylim, spec["ylim"], "ylim")
    if bool(spec.get("grid", False)) and chart != "heatmap":
        ax.grid(True, color="#D0D0D0", linewidth=0.5, alpha=0.8)
        ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)


def _set_limit(setter: Any, value: Any, field: str) -> None:
    if not isinstance(value, list) or len(value) != 2:
        raise FigureSpecError(f"{field} must be [minimum, maximum]")
    low, high = finite_float(value[0], field, 0), finite_float(value[1], field, 0)
    if low >= high:
        raise FigureSpecError(f"{field} minimum must be less than maximum")
    setter(low, high)


def plot_xy(ax: Any, series: list[dict[str, Any]], spec: dict[str, Any]) -> list[Any]:
    chart = spec["chart"]
    artists: list[Any] = []
    if chart in {"line", "scatter"}:
        for item in series:
            style = item["style"]
            if chart == "line":
                (artist,) = ax.plot(
                    item["x"],
                    item["values"],
                    label=item["label"],
                    color=style["color"],
                    marker=style["marker"],
                    linestyle=style["linestyle"],
                    linewidth=1.25,
                    markersize=4.0,
                    markerfacecolor="white",
                    markeredgewidth=0.9,
                )
            else:
                artist = ax.scatter(
                    item["x"],
                    item["values"],
                    label=item["label"],
                    color=style["color"],
                    marker=style["marker"],
                    s=24,
                    linewidths=0.75,
                    edgecolors="white",
                )
            artists.append(artist)
    else:
        categories: list[str] = []
        mappings: list[dict[str, float]] = []
        for item in series:
            mapping: dict[str, float] = {}
            for category, value in zip(item["x"], item["values"]):
                category = str(category)
                if category in mapping:
                    raise FigureSpecError(
                        f"bar category {category!r} repeats within series {item['label']!r}; aggregate explicitly"
                    )
                mapping[category] = value
                if category not in categories:
                    categories.append(category)
            mappings.append(mapping)
        base = np.arange(len(categories), dtype=float)
        count = len(series)
        width = min(0.8 / max(count, 1), 0.7)
        for index, (item, mapping) in enumerate(zip(series, mappings)):
            positions: list[float] = []
            values: list[float] = []
            offset = (index - (count - 1) / 2.0) * width
            for category_index, category in enumerate(categories):
                if category in mapping:
                    positions.append(base[category_index] + offset)
                    values.append(mapping[category])
            style = item["style"]
            artist = ax.bar(
                positions,
                values,
                width=width * 0.92,
                label=item["label"],
                color=style["color"],
                edgecolor="#222222",
                linewidth=0.6,
                hatch=style["hatch"],
            )
            artists.extend(list(artist.patches))
        ax.set_xticks(base, categories)
    if len(series) > 1 and bool(spec.get("legend", True)):
        ax.legend(loc=str(spec.get("legend_location", "best")), frameon=False)
    return artists


def plot_distribution(
    ax: Any, series: list[dict[str, Any]], spec: dict[str, Any]
) -> list[Any]:
    artists: list[Any] = []
    if spec["chart"] == "hist":
        bins = spec.get("bins", 20)
        if isinstance(bins, bool) or not isinstance(bins, (int, list, str)):
            raise FigureSpecError("hist bins must be an integer, a numeric edge list, or NumPy bin rule")
        if isinstance(bins, int) and not 1 <= bins <= 500:
            raise FigureSpecError("hist bins integer must be between 1 and 500")
        if isinstance(bins, list):
            bins = [finite_float(item, "bins", 0) for item in bins]
            if len(bins) < 2 or any(a >= b for a, b in zip(bins, bins[1:])):
                raise FigureSpecError("hist bin edges must be strictly increasing")
        all_values = np.concatenate([np.asarray(item["values"], dtype=float) for item in series])
        edges = np.histogram_bin_edges(all_values, bins=bins)
        density = bool(spec.get("density", False))
        for item in series:
            counts, _ = np.histogram(item["values"], bins=edges, density=density)
            style = item["style"]
            artist = ax.stairs(
                counts,
                edges,
                label=item["label"],
                color=style["color"],
                linestyle=style["linestyle"],
                linewidth=1.4,
            )
            artists.append(artist)
        if not spec.get("ylabel"):
            ax.set_ylabel("Density" if density else "Count")
    else:
        for item in series:
            values = np.sort(np.asarray(item["values"], dtype=float))
            probabilities = np.arange(1, len(values) + 1, dtype=float) / len(values)
            style = item["style"]
            mark_every = max(1, len(values) // 10)
            (artist,) = ax.step(
                values,
                probabilities,
                where="post",
                label=item["label"],
                color=style["color"],
                linestyle=style["linestyle"],
                marker=style["marker"],
                markevery=mark_every,
                markersize=3.5,
                linewidth=1.25,
            )
            artists.append(artist)
        if not spec.get("ylabel"):
            ax.set_ylabel("Empirical cumulative probability")
        if "ylim" not in spec:
            ax.set_ylim(0.0, 1.0)
    if len(series) > 1 and bool(spec.get("legend", True)):
        ax.legend(loc=str(spec.get("legend_location", "best")), frameon=False)
    return artists


def plot_heatmap(
    fig: Any, ax: Any, heatmap: dict[str, Any], spec: dict[str, Any]
) -> list[Any]:
    cmap_name = str(spec.get("cmap", "cividis"))
    try:
        cmap = matplotlib.colormaps[cmap_name].copy()
    except KeyError as exc:
        raise FigureSpecError(f"unknown Matplotlib colormap: {cmap_name}") from exc
    cmap.set_bad(str(spec.get("missing_color", "#D9D9D9")))
    kwargs: dict[str, Any] = {"cmap": cmap, "aspect": "auto", "interpolation": "nearest"}
    if "vmin" in spec:
        kwargs["vmin"] = finite_float(spec["vmin"], "vmin", 0)
    if "vmax" in spec:
        kwargs["vmax"] = finite_float(spec["vmax"], "vmax", 0)
    if "vmin" in kwargs and "vmax" in kwargs and kwargs["vmin"] >= kwargs["vmax"]:
        raise FigureSpecError("vmin must be less than vmax")
    image = ax.imshow(np.ma.masked_invalid(heatmap["matrix"]), **kwargs)
    ax.set_xticks(np.arange(len(heatmap["x_values"])), heatmap["x_values"])
    ax.set_yticks(np.arange(len(heatmap["y_values"])), heatmap["y_values"])
    colorbar = fig.colorbar(image, ax=ax, fraction=0.046, pad=0.04)
    if spec.get("colorbar_label"):
        colorbar.set_label(str(spec["colorbar_label"]))
    if bool(spec.get("annotate", False)):
        for row in range(heatmap["matrix"].shape[0]):
            for column in range(heatmap["matrix"].shape[1]):
                value = heatmap["matrix"][row, column]
                if math.isfinite(float(value)):
                    ax.text(column, row, f"{value:g}", ha="center", va="center", fontsize="small")
    return [image]


def _number_range(values: Iterable[float]) -> list[float]:
    values = list(values)
    return [float(min(values)), float(max(values))]


def auto_text(
    spec: dict[str, Any], prepared: Any
) -> tuple[str, str, bool, bool]:
    chart = spec["chart"]
    chart_names = {
        "line": "Line chart",
        "scatter": "Scatter plot",
        "bar": "Grouped bar chart" if isinstance(prepared, list) and len(prepared) > 1 else "Bar chart",
        "hist": "Histogram",
        "ecdf": "Empirical cumulative distribution plot",
        "heatmap": "Heatmap",
    }
    caption_generated = not bool(spec.get("caption"))
    alt_generated = not bool(spec.get("alt_text"))
    xlabel = str(spec.get("xlabel") or spec.get("x"))
    if chart == "heatmap":
        ylabel = str(spec.get("ylabel") or spec.get("y"))
        value_label = str(spec.get("colorbar_label") or spec.get("value"))
        caption_default = f"{chart_names[chart]} of {value_label} by {xlabel} and {ylabel}."
        finite_values = prepared["matrix"][np.isfinite(prepared["matrix"])]
        alt_default = (
            f"{chart_names[chart]} with {len(prepared['y_values'])} rows and "
            f"{len(prepared['x_values'])} columns. {value_label} ranges from "
            f"{float(np.min(finite_values)):g} to {float(np.max(finite_values)):g}; "
            f"{prepared['missing_cells']} cells are missing."
        )
    elif chart in {"hist", "ecdf"}:
        labels = ", ".join(item["label"] for item in prepared)
        caption_default = f"{chart_names[chart]} of {xlabel} for {labels}."
        ranges = "; ".join(
            f"{item['label']}: n={len(item['values'])}, range {_number_range(item['values'])[0]:g}–{_number_range(item['values'])[1]:g}"
            for item in prepared
        )
        alt_default = f"{chart_names[chart]} showing {len(prepared)} series. {ranges}."
    else:
        ylabel = str(spec.get("ylabel") or spec.get("y"))
        labels = ", ".join(item["label"] for item in prepared)
        caption_default = f"{chart_names[chart]} of {ylabel} by {xlabel} for {labels}."
        ranges = "; ".join(
            f"{item['label']}: n={len(item['values'])}, y range {_number_range(item['values'])[0]:g}–{_number_range(item['values'])[1]:g}"
            for item in prepared
        )
        alt_default = f"{chart_names[chart]} showing {len(prepared)} series. {ranges}."
    return (
        str(spec.get("caption") or caption_default),
        str(spec.get("alt_text") or alt_default),
        caption_generated,
        alt_generated,
    )


def mechanical_probes(fig: Any, data_artists: list[Any]) -> dict[str, Any]:
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    canvas = fig.bbox
    text_boxes: list[tuple[str, Any]] = []
    crop_items: list[str] = []
    for text_artist in fig.findobj(match=Text):
        text_value = text_artist.get_text().strip()
        if not text_value or not text_artist.get_visible():
            continue
        try:
            box = text_artist.get_window_extent(renderer)
        except Exception:
            continue
        if not all(math.isfinite(value) for value in box.extents):
            continue
        text_boxes.append((text_value, box))
        if box.x0 < canvas.x0 - 1 or box.y0 < canvas.y0 - 1 or box.x1 > canvas.x1 + 1 or box.y1 > canvas.y1 + 1:
            crop_items.append(text_value[:80])
    overlaps: list[dict[str, str]] = []
    for index, (first_text, first_box) in enumerate(text_boxes):
        for second_text, second_box in text_boxes[index + 1 :]:
            intersection_width = min(first_box.x1, second_box.x1) - max(first_box.x0, second_box.x0)
            intersection_height = min(first_box.y1, second_box.y1) - max(first_box.y0, second_box.y0)
            if intersection_width > 2 and intersection_height > 2:
                overlaps.append({"a": first_text[:80], "b": second_text[:80]})
                if len(overlaps) >= 20:
                    break
        if len(overlaps) >= 20:
            break
    legend_overlaps = 0
    legends = [artist for artist in fig.findobj(match=Legend) if artist.get_visible()]
    for legend in legends:
        try:
            legend_box = legend.get_window_extent(renderer)
        except Exception:
            continue
        if (
            legend_box.x0 < canvas.x0 - 1
            or legend_box.y0 < canvas.y0 - 1
            or legend_box.x1 > canvas.x1 + 1
            or legend_box.y1 > canvas.y1 + 1
        ):
            crop_items.append("legend")
        for artist in data_artists:
            if not getattr(artist, "get_visible", lambda: False)():
                continue
            try:
                data_box = artist.get_window_extent(renderer)
            except Exception:
                continue
            if legend_box.overlaps(data_box):
                legend_overlaps += 1
                break
    for index, artist in enumerate(data_artists):
        if not getattr(artist, "get_visible", lambda: False)():
            continue
        try:
            box = artist.get_window_extent(renderer)
        except Exception:
            continue
        if not all(math.isfinite(value) for value in box.extents):
            continue
        if box.x0 < canvas.x0 - 1 or box.y0 < canvas.y0 - 1 or box.x1 > canvas.x1 + 1 or box.y1 > canvas.y1 + 1:
            crop_items.append(f"data-artist-{index}")
    return {
        "method": "Matplotlib artist bounding-box approximation after layout",
        "inspected_artist_types": ["text", "legend", "data"],
        "canvas_crop_risk_count": len(crop_items),
        "canvas_crop_risk_items": crop_items[:20],
        "text_overlap_pair_count": len(overlaps),
        "text_overlap_pairs": overlaps,
        "legend_data_overlap_count": legend_overlaps,
        "requires_visual_review": True,
    }


def series_metadata(chart: str, prepared: Any, spec: dict[str, Any]) -> list[dict[str, Any]]:
    if chart == "heatmap":
        finite_values = prepared["matrix"][np.isfinite(prepared["matrix"])]
        return [
            {
                "key": prepared["source_value"],
                "label": str(spec.get("colorbar_label") or prepared["source_value"]),
                "point_count": int(finite_values.size),
                "value_range": [float(np.min(finite_values)), float(np.max(finite_values))],
                "style": {
                    "colormap": str(spec.get("cmap", "cividis")),
                    "missing_color": str(spec.get("missing_color", "#D9D9D9")),
                },
            }
        ]
    result: list[dict[str, Any]] = []
    for item in prepared:
        entry = {
            "key": item["key"],
            "label": item["label"],
            "point_count": len(item["values"]),
            "value_range": _number_range(item["values"]),
            "style": item["style"],
        }
        result.append(entry)
    return result


def save_outputs(
    fig: Any,
    output_dir: Path,
    basename: str,
    settings: dict[str, Any],
    title: str,
    caption: str,
    alt_text: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    paths = {
        "pdf": output_dir / f"{basename}.pdf",
        "svg": output_dir / f"{basename}.svg",
        "png": output_dir / f"{basename}.png",
    }
    metadata = {
        "pdf": {
            "Title": title,
            "Author": "",
            "Subject": caption,
            "Keywords": "publication figure; reproducible",
            "Creator": "create-publication-figures",
            "Producer": f"Matplotlib {matplotlib.__version__}",
            "CreationDate": None,
            "ModDate": None,
        },
        "svg": {
            "Title": title,
            "Creator": "create-publication-figures",
            "Description": alt_text,
            "Date": None,
        },
        "png": {
            "Software": "create-publication-figures",
            "Title": title,
            "Description": alt_text,
        },
    }
    common = {"facecolor": "white", "edgecolor": "none", "bbox_inches": None, "pad_inches": 0}
    fig.savefig(paths["pdf"], format="pdf", metadata=metadata["pdf"], **common)
    fig.savefig(paths["svg"], format="svg", metadata=metadata["svg"], **common)
    fig.savefig(paths["png"], format="png", dpi=settings["dpi"], metadata=metadata["png"], **common)
    with Image.open(paths["png"]) as image:
        image.load()
        pixels = [int(image.width), int(image.height)]
        dpi_info = image.info.get("dpi", (settings["dpi"], settings["dpi"]))
        png_dpi = [float(dpi_info[0]), float(dpi_info[1])]
    media_types = {"pdf": "application/pdf", "svg": "image/svg+xml", "png": "image/png"}
    files: list[dict[str, Any]] = []
    for extension in ("pdf", "svg", "png"):
        path = paths[extension]
        entry: dict[str, Any] = {
            "name": path.name,
            "media_type": media_types[extension],
            "sha256": sha256_file(path),
            "bytes": path.stat().st_size,
            "width_mm": settings["width_mm"],
            "height_mm": settings["height_mm"],
        }
        if extension == "png":
            entry["pixels"] = pixels
            entry["dpi"] = png_dpi
        files.append(entry)
    return files, metadata


def render_package(
    data_path: Path,
    spec_source: str,
    output_dir: Path,
    *,
    profiles_path: Path = DEFAULT_PROFILES_PATH,
    profile_override: str | None = None,
    size_override: str | None = None,
    dpi_override: int | None = None,
    seed_override: int | None = None,
    basename: str = "figure",
    overwrite: bool = False,
) -> dict[str, Any]:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", basename):
        raise FigureSpecError("basename may contain only letters, digits, dot, underscore, and hyphen")
    spec, spec_provenance = load_json_object(spec_source, "figure spec")
    validate_spec(spec)
    records, input_provenance = load_data(data_path)
    selected_records, filter_metadata = apply_filter(records, spec.get("filter"))
    profiles_config, profiles_provenance = load_profiles(profiles_path)
    profile_id = profile_override or str(spec.get("profile", "draft"))
    if profile_id not in profiles_config["profiles"]:
        raise FigureSpecError(
            f"unknown profile {profile_id!r}; choose from {', '.join(profiles_config['profiles'])}"
        )
    profile = profiles_config["profiles"][profile_id]
    settings = resolve_render_settings(
        spec, profile_id, profile, size_override, dpi_override, seed_override
    )
    spec_resolved = dict(spec)
    spec_resolved.update(
        {
            "profile": profile_id,
            "size": settings["size_name"],
            "width_mm": settings["width_mm"],
            "height_mm": settings["height_mm"],
            "dpi": settings["dpi"],
            "font_family": settings["font_family"],
            "font_size_pt": settings["font_size_pt"],
            "seed": settings["seed"],
        }
    )
    spec_provenance["resolved_sha256"] = sha256_bytes(canonical_json_bytes(spec_resolved))

    chart = spec["chart"]
    if chart in {"line", "scatter", "bar"}:
        prepared, dropped = prepare_xy_series(selected_records, spec)
    elif chart in {"hist", "ecdf"}:
        prepared, dropped = prepare_distribution_series(selected_records, spec)
    else:
        prepared, dropped = prepare_heatmap(selected_records, spec)
    validate_scale_domains(chart, prepared, spec)
    caption, alt_text, caption_generated, alt_generated = auto_text(spec, prepared)

    try:
        output_entry = output_dir.lstat()
    except FileNotFoundError:
        output_dir.mkdir(parents=True, exist_ok=False)
    except OSError as exc:
        raise FigureSpecError(f"cannot inspect output directory: {exc}") from exc
    else:
        if stat.S_ISLNK(output_entry.st_mode) or not stat.S_ISDIR(output_entry.st_mode):
            raise FigureSpecError("output directory must be a plain directory, not a symlink or special file")
    expected = [output_dir / f"{basename}.{suffix}" for suffix in ("pdf", "svg", "png")]
    expected.append(output_dir / "manifest.json")
    existing: list[Path] = []
    for path in expected:
        try:
            entry = path.lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise FigureSpecError(f"cannot inspect output target {path.name}: {exc}") from exc
        if stat.S_ISLNK(entry.st_mode) or not stat.S_ISREG(entry.st_mode):
            raise FigureSpecError(
                f"output target must be a regular file, not a symlink or special file: {path.name}"
            )
        existing.append(path)
    if existing and not overwrite:
        raise FigureSpecError(
            "output files already exist; choose an empty directory or pass --overwrite: "
            + ", ".join(path.name for path in existing)
        )

    random.seed(settings["seed"])
    np.random.seed(settings["seed"] % (2**32))
    rc = {
        "font.family": settings["font_family"],
        "font.size": settings["font_size_pt"],
        "axes.titlesize": settings["font_size_pt"],
        "axes.labelsize": settings["font_size_pt"],
        "xtick.labelsize": max(5.0, settings["font_size_pt"] - 1.0),
        "ytick.labelsize": max(5.0, settings["font_size_pt"] - 1.0),
        "legend.fontsize": max(5.0, settings["font_size_pt"] - 1.0),
        "axes.linewidth": 0.75,
        "lines.solid_capstyle": "round",
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
        "svg.fonttype": "none",
        "svg.hashsalt": "create-publication-figures-v1",
        "axes.unicode_minus": False,
        "savefig.transparent": False,
    }
    layout_warnings: list[str] = []
    with matplotlib.rc_context(rc):
        fig, ax = plt.subplots(
            figsize=(settings["width_mm"] / MM_PER_INCH, settings["height_mm"] / MM_PER_INCH),
            dpi=settings["dpi"],
        )
        if chart in {"line", "scatter", "bar"}:
            data_artists = plot_xy(ax, prepared, spec)
        elif chart in {"hist", "ecdf"}:
            data_artists = plot_distribution(ax, prepared, spec)
        else:
            data_artists = plot_heatmap(fig, ax, prepared, spec)
        _apply_axes_options(ax, spec, chart)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            fig.tight_layout(pad=0.6)
        layout_warnings = [str(item.message) for item in caught]
        probes = mechanical_probes(fig, data_artists)
        title = str(spec.get("title") or "Publication figure")
        files, export_metadata = save_outputs(
            fig, output_dir, basename, settings, title, caption, alt_text
        )
        plt.close(fig)

    review_warnings: list[str] = []
    if settings["font_fallback_used"]:
        review_warnings.append(
            f"Preferred profile font was unavailable; rendered with {settings['font_family']}. Verify venue acceptance."
        )
    if caption_generated:
        review_warnings.append("Caption was generated from field names; replace it with study-aware text.")
    if alt_generated:
        review_warnings.append("Alt text was generated mechanically; review it for the intended finding and context.")
    if dropped:
        review_warnings.append(
            f"Dropped {len(dropped)} non-finite or missing observations under explicit nonfinite='drop'."
        )
    if filter_metadata["excluded_rows"]:
        review_warnings.append(
            f"An explicit filter excluded {filter_metadata['excluded_rows']} source rows; report the denominator and excluded/failure states."
        )
    if probes["canvas_crop_risk_count"]:
        review_warnings.append("Artist bounds suggest possible canvas clipping; inspect all output edges.")
    if probes["text_overlap_pair_count"]:
        review_warnings.append("Text bounding boxes overlap in a mechanical approximation; inspect labels and legend.")
    if probes["legend_data_overlap_count"]:
        review_warnings.append("Legend bounds overlap data-artist bounds; inspect whether marks are obscured.")
    review_warnings.extend(f"Layout warning: {message}" for message in layout_warnings)
    if isinstance(prepared, list) and len(prepared) > len(PALETTE):
        review_warnings.append("Series count exceeds the unique default palette; verify color and redundant styles.")
    if chart == "bar" and (
        spec.get("yscale", "linear") != "linear"
        or (isinstance(spec.get("ylim"), list) and spec["ylim"] and spec["ylim"][0] != 0)
    ):
        review_warnings.append("Bar baseline or y scale is nonstandard; verify that the encoding does not exaggerate differences.")

    figure_metadata: dict[str, Any] = {
        "chart": chart,
        "x": spec["x"],
        "y": spec.get("y"),
        "value": spec.get("value"),
        "series_column": spec.get("series"),
        "title": spec.get("title", ""),
        "xlabel": spec.get("xlabel", ""),
        "ylabel": spec.get("ylabel", ""),
        "colorbar_label": spec.get("colorbar_label", ""),
        "xscale": spec.get("xscale", "linear"),
        "yscale": spec.get("yscale", "linear"),
        "caption": caption,
        "caption_generated": caption_generated,
        "alt_text": alt_text,
        "alt_text_generated": alt_generated,
        "denominator": spec.get("denominator"),
        "series": series_metadata(chart, prepared, spec),
        "plotted_observation_count": int(
            np.isfinite(prepared["matrix"]).sum()
            if chart == "heatmap"
            else sum(len(item["values"]) for item in prepared)
        ),
    }
    if chart == "heatmap":
        figure_metadata["heatmap_shape"] = [
            len(prepared["y_values"]),
            len(prepared["x_values"]),
        ]
        figure_metadata["missing_cell_count"] = prepared["missing_cells"]

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "package_type": "reproducible-publication-figure",
        "generator": {
            "name": "create-publication-figures/render_figure.py",
            "tool_sha256": sha256_file(SCRIPT_PATH),
            "matplotlib_version": matplotlib.__version__,
            "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        },
        "input": input_provenance,
        "spec": spec_provenance,
        "profile": {
            "id": profile_id,
            "display_name": profile.get("display_name"),
            "kind": profiles_config.get("profile_kind"),
            "profile_sha256": sha256_bytes(canonical_json_bytes(profile)),
            "config": profiles_provenance,
            "scope": profile.get("scope"),
            "conflict_status": profile.get("conflict_status"),
            "sources": profile.get("sources", []),
            "variable_items": profile.get("variable_items", []),
        },
        "render": {
            "seed": settings["seed"],
            "profile_id": profile_id,
            "size_name": settings["size_name"],
            "size_basis": settings["size_basis"],
            "width_mm": settings["width_mm"],
            "height_mm": settings["height_mm"],
            "png_dpi": settings["dpi"],
            "font_family": settings["font_family"],
            "font_file": settings["font_file"],
            "font_fallback_used": settings["font_fallback_used"],
            "font_size_pt": settings["font_size_pt"],
            "crop_mode": "fixed_canvas",
            "bbox_inches": None,
            "color_space": "RGB",
            "export_metadata": export_metadata,
        },
        "figure": figure_metadata,
        "files": files,
        "qa": {
            "input_row_count": len(records),
            "selected_row_count": len(selected_records),
            "filter": filter_metadata,
            "nonfinite_policy": spec.get("nonfinite", "error"),
            "dropped_observation_count": len(dropped),
            "dropped_observations": dropped,
            "accessibility": {
                "palette": "Okabe-Ito-derived categorical palette",
                "default_heatmap_colormap": "cividis",
                "redundant_encodings": {
                    "line": "color + marker + linestyle",
                    "scatter": "color + marker",
                    "bar": "color + hatch",
                    "hist": "color + linestyle",
                    "ecdf": "color + marker + linestyle",
                },
            },
            "mechanical_probes": probes,
            "review_warnings": review_warnings,
            "human_review_required": True,
        },
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Render deterministic PDF, SVG, PNG, and manifest from CSV/JSON data."
    )
    parser.add_argument("--data", required=True, type=Path, help="Input .csv or .json file")
    parser.add_argument("--spec", required=True, help="Spec JSON file path or inline JSON object")
    parser.add_argument("--output-dir", required=True, type=Path, help="Output package directory")
    parser.add_argument(
        "--profiles", type=Path, default=DEFAULT_PROFILES_PATH, help="Submission profiles JSON"
    )
    parser.add_argument("--profile", help="Override profile from spec")
    parser.add_argument("--size", help="Override named size preset")
    parser.add_argument("--dpi", type=int, help="Override PNG DPI")
    parser.add_argument("--seed", type=int, help=f"Override fixed seed (default {DEFAULT_SEED})")
    parser.add_argument("--basename", default="figure", help="Output basename (default: figure)")
    parser.add_argument("--overwrite", action="store_true", help="Replace expected package files")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        manifest = render_package(
            args.data,
            args.spec,
            args.output_dir,
            profiles_path=args.profiles,
            profile_override=args.profile,
            size_override=args.size,
            dpi_override=args.dpi,
            seed_override=args.seed,
            basename=args.basename,
            overwrite=args.overwrite,
        )
    except (FigureSpecError, OSError) as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "status": "ok",
                "output_dir": str(args.output_dir),
                "profile": manifest["profile"]["id"],
                "chart": manifest["figure"]["chart"],
                "files": [item["name"] for item in manifest["files"]] + ["manifest.json"],
                "warning_count": len(manifest["qa"]["review_warnings"]),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
