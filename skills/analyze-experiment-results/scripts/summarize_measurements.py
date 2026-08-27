#!/usr/bin/env python3
"""Create deterministic descriptive tables from fine-grained CSV or JSONL measurements."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import random
import shutil
import stat
import statistics
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any, Iterable


VERSION = "1.2"
STATUS_NAMESPACES = {
    "execution": ("accepted", "failed", "missing"),
    "measurement": ("accepted", "contaminated", "missing"),
    "scientific": ("observed", "excluded", "missing"),
}


class AnalysisError(ValueError):
    pass


def lexical_absolute(path: Path) -> Path:
    """Return an absolute path without dereferencing any filesystem component."""

    return Path(os.path.abspath(os.fspath(path)))


def path_exists_lstat(path: Path) -> bool:
    """Return whether a directory entry exists, including a dangling symlink."""

    try:
        path.lstat()
    except FileNotFoundError:
        return False
    return True


def check_directory_chain(path: Path, *, allow_missing: bool) -> None:
    """Reject symlinks and non-directories in an absolute directory chain."""

    absolute = lexical_absolute(path)
    current = Path(absolute.anchor)
    missing = False
    for part in absolute.parts[1:]:
        current /= part
        if missing:
            continue
        try:
            entry = current.lstat()
        except FileNotFoundError:
            if allow_missing:
                missing = True
                continue
            raise AnalysisError(f"output parent does not exist: {current}")
        if stat.S_ISLNK(entry.st_mode):
            raise AnalysisError(f"output path contains a symlink: {current}")
        if not stat.S_ISDIR(entry.st_mode):
            raise AnalysisError(f"output parent component is not a directory: {current}")


def require_output_missing(path: Path) -> None:
    if path_exists_lstat(path):
        raise AnalysisError("output directory entry already exists")


def publish_staging(staging: Path, output_dir: Path) -> None:
    """Claim an absent destination without replacing a late-created entry.

    The final manifest moves last and acts as the process-level commit marker.  The
    atomic mkdir prevents an existing file, directory, special file, or
    dangling symlink from being replaced on every supported Python platform.
    """

    check_directory_chain(output_dir.parent, allow_missing=False)
    require_output_missing(output_dir)
    try:
        output_dir.mkdir(mode=0o700)
    except FileExistsError as exc:
        raise AnalysisError("output directory entry appeared before publish") from exc
    except OSError as exc:
        if path_exists_lstat(output_dir):
            raise AnalysisError("output directory entry appeared before publish") from exc
        raise

    claimed = True
    try:
        children = sorted(staging.iterdir(), key=lambda item: item.name)
        children.sort(key=lambda item: item.name == "analysis-manifest.json")
        for child in children:
            os.replace(child, output_dir / child.name)
        staging.rmdir()
        claimed = False
    finally:
        if claimed:
            try:
                entry = output_dir.lstat()
            except FileNotFoundError:
                pass
            else:
                if stat.S_ISDIR(entry.st_mode) and not stat.S_ISLNK(entry.st_mode):
                    shutil.rmtree(output_dir, ignore_errors=True)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_rows(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".csv":
        with path.open("r", encoding="utf-8", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    if path.suffix.lower() in {".jsonl", ".ndjson"}:
        rows: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    value = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise AnalysisError(f"invalid JSONL at line {line_number}: {exc}") from exc
                if not isinstance(value, dict):
                    raise AnalysisError(f"JSONL line {line_number} must be an object")
                rows.append(value)
        return rows
    raise AnalysisError("input format must be CSV or JSONL")


def numeric(value: Any) -> tuple[str, float | None]:
    if value is None or value == "":
        return "missing", None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return "invalid", None
    if not math.isfinite(parsed):
        return "nonfinite", None
    return "finite", parsed


def quantile(values: list[float], probability: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = probability * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def bootstrap_interval(values: list[float], samples: int, confidence: float, seed: int) -> list[float] | None:
    if samples < 1 or not values:
        return None
    rng = random.Random(seed)
    means = [statistics.fmean(rng.choice(values) for _ in values) for _ in range(samples)]
    alpha = 1.0 - confidence
    lower = quantile(means, alpha / 2)
    upper = quantile(means, 1 - alpha / 2)
    assert lower is not None and upper is not None
    return [lower, upper]


def stable_seed(base: int, *parts: str) -> int:
    material = "\x00".join(parts).encode("utf-8")
    return base + int(hashlib.sha256(material).hexdigest()[:12], 16)


def group_key(row: dict[str, Any], fields: list[str]) -> tuple[str, ...]:
    return tuple(str(row.get(field, "")) for field in fields)


def status_class(row: dict[str, Any], status_spec: dict[str, Any]) -> str:
    column = status_spec.get("column")
    if not column:
        return "valid"
    value = str(row.get(column, ""))
    if value in status_spec.get("valid", []):
        return "valid"
    if value in status_spec.get("execution_failure", []):
        return "execution_failure"
    if value in status_spec.get("contamination", []):
        return "contamination"
    if value in status_spec.get("missing", []):
        return "missing_status"
    return "other_status"


def namespace_status(row: dict[str, Any], status_columns: dict[str, Any], namespace: str) -> str:
    namespace_spec = status_columns.get(namespace)
    if not isinstance(namespace_spec, dict):
        return "not_configured"
    value = str(row.get(namespace_spec["column"], ""))
    for category in STATUS_NAMESPACES[namespace]:
        if value in namespace_spec.get(category, []):
            return category
    return "other"


def status_snapshot(row: dict[str, Any], spec: dict[str, Any]) -> dict[str, str]:
    status_columns = spec.get("status_columns")
    if isinstance(status_columns, dict) and status_columns:
        return {
            namespace: namespace_status(row, status_columns, namespace)
            for namespace in STATUS_NAMESPACES
        }
    compact_status = status_class(row, spec.get("record_status", {}))
    return {
        "execution": (
            "failed"
            if compact_status == "execution_failure"
            else "missing"
            if compact_status == "missing_status"
            else "other"
            if compact_status == "other_status"
            else "accepted"
        ),
        "measurement": "contaminated" if compact_status == "contamination" else ("missing" if compact_status == "missing_status" else "accepted"),
        "scientific": "missing" if compact_status == "missing_status" else "observed",
    }


def status_is_analyzable(snapshot: dict[str, str]) -> bool:
    return (
        snapshot["execution"] in {"accepted", "not_configured"}
        and snapshot["measurement"] in {"accepted", "not_configured"}
        and snapshot["scientific"] in {"observed", "not_configured"}
    )


def selected_values(rows: Iterable[dict[str, Any]], metric: dict[str, Any], spec: dict[str, Any], filters: dict[str, Any] | None = None) -> list[float]:
    values: list[float] = []
    for row in rows:
        if filters and any(str(row.get(field, "")) != str(expected) for field, expected in filters.items()):
            continue
        if not status_is_analyzable(status_snapshot(row, spec)):
            continue
        state, value = numeric(row.get(metric["column"]))
        if state == "finite" and value is not None:
            values.append(value)
    return values


def validate_spec(spec: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(spec, dict):
        return ["spec root must be an object"]
    if spec.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    if not isinstance(spec.get("analysis_id"), str) or not spec.get("analysis_id", "").strip():
        errors.append("analysis_id is required")
    if spec.get("status") not in {"draft", "frozen"}:
        errors.append("status must be draft or frozen")
    if not isinstance(spec.get("unresolved_blockers", []), list):
        errors.append("unresolved_blockers must be a list")
    for field in ("id_columns", "group_by"):
        if not isinstance(spec.get(field, []), list) or any(not isinstance(item, str) or not item for item in spec.get(field, [])):
            errors.append(f"{field} must be a list of column names")
    status_spec = spec.get("record_status", {})
    if not isinstance(status_spec, dict):
        errors.append("record_status must be an object")
    else:
        for field in ("valid", "execution_failure", "contamination", "missing"):
            if not isinstance(status_spec.get(field, []), list):
                errors.append(f"record_status.{field} must be a list")
    status_columns = spec.get("status_columns", {})
    if not isinstance(status_columns, dict):
        errors.append("status_columns must be an object")
    else:
        for namespace, categories in STATUS_NAMESPACES.items():
            namespace_spec = status_columns.get(namespace)
            if namespace_spec is None:
                continue
            if not isinstance(namespace_spec, dict):
                errors.append(f"status_columns.{namespace} must be an object")
                continue
            if not isinstance(namespace_spec.get("column"), str) or not namespace_spec.get("column"):
                errors.append(f"status_columns.{namespace}.column is required")
            assigned: list[str] = []
            for category in categories:
                values = namespace_spec.get(category, [])
                if not isinstance(values, list) or any(not isinstance(item, (str, int, float)) for item in values):
                    errors.append(f"status_columns.{namespace}.{category} must be a list of status values")
                else:
                    assigned.extend(str(item) for item in values)
            if len(assigned) != len(set(assigned)):
                errors.append(f"status_columns.{namespace} assigns a status value more than once")
            accepted_key = "observed" if namespace == "scientific" else "accepted"
            if not isinstance(namespace_spec.get(accepted_key), list) or not namespace_spec.get(accepted_key):
                errors.append(f"status_columns.{namespace}.{accepted_key} must not be empty")
    metrics = spec.get("metrics")
    if not isinstance(metrics, list) or not metrics:
        errors.append("metrics must be a non-empty list")
        return errors
    metric_ids: set[str] = set()
    for index, metric in enumerate(metrics):
        if not isinstance(metric, dict):
            errors.append(f"metrics[{index}] must be an object")
            continue
        for field in ("id", "column", "unit", "direction"):
            if not isinstance(metric.get(field), str) or not metric.get(field):
                errors.append(f"metrics[{index}].{field} is required")
        metric_id = metric.get("id")
        if isinstance(metric_id, str):
            if metric_id in metric_ids:
                errors.append(f"duplicate metric id: {metric_id}")
            metric_ids.add(metric_id)
        samples = metric.get("bootstrap_samples", 0)
        if not isinstance(samples, int) or isinstance(samples, bool) or samples < 0:
            errors.append(f"metrics[{index}].bootstrap_samples must be a non-negative integer")
        confidence = metric.get("confidence", 0.95)
        if not isinstance(confidence, (int, float)) or isinstance(confidence, bool) or not 0 < confidence < 1:
            errors.append(f"metrics[{index}].confidence must be between 0 and 1")
    for index, comparison in enumerate(spec.get("comparisons", [])):
        if not isinstance(comparison, dict):
            errors.append(f"comparisons[{index}] must be an object")
            continue
        if comparison.get("metric_id") not in metric_ids:
            errors.append(f"comparisons[{index}] references unknown metric")
        if not isinstance(comparison.get("baseline_filters"), dict) or not isinstance(comparison.get("candidate_filters"), dict):
            errors.append(f"comparisons[{index}] needs baseline_filters and candidate_filters")
    return errors


def build_summary(rows: list[dict[str, Any]], spec: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    group_fields = spec.get("group_by", [])
    groups: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault(group_key(row, group_fields), []).append(row)
    if not groups:
        groups[tuple()] = []

    summaries: list[dict[str, Any]] = []
    bad_cases: list[dict[str, Any]] = []
    warnings: list[str] = []
    base_seed = int(spec.get("seed", 0))
    context_columns = list(dict.fromkeys(spec.get("id_columns", []) + group_fields + spec.get("context_columns", [])))
    status_spec = spec.get("record_status", {})
    using_status_columns = bool(spec.get("status_columns"))
    status_column = status_spec.get("column")
    if status_column:
        context_columns.append(status_column)
    if isinstance(spec.get("status_columns"), dict):
        for namespace_spec in spec["status_columns"].values():
            if isinstance(namespace_spec, dict) and isinstance(namespace_spec.get("column"), str):
                context_columns.append(namespace_spec["column"])
    context_columns = list(dict.fromkeys(context_columns))

    for key in sorted(groups):
        group_rows = groups[key]
        group_values = dict(zip(group_fields, key))
        snapshots = [status_snapshot(row, spec) for row in group_rows]
        classes = [status_class(row, status_spec) for row in group_rows]
        analyzable = [status_is_analyzable(snapshot) for snapshot in snapshots]
        for metric in spec["metrics"]:
            finite_values: list[float] = []
            missing_count = nonfinite_count = invalid_count = 0
            bad_case = metric.get("bad_case")
            for row_index, row in enumerate(group_rows):
                if not analyzable[row_index]:
                    continue
                numeric_state, value = numeric(row.get(metric["column"]))
                if numeric_state == "missing":
                    missing_count += 1
                elif numeric_state == "nonfinite":
                    nonfinite_count += 1
                elif numeric_state == "invalid":
                    invalid_count += 1
                elif value is not None:
                    finite_values.append(value)
                    if isinstance(bad_case, dict):
                        operator = bad_case.get("operator")
                        threshold = bad_case.get("threshold")
                        matched = isinstance(threshold, (int, float)) and not isinstance(threshold, bool) and ((operator == "above" and value > threshold) or (operator == "below" and value < threshold))
                        if matched:
                            record = {field: row.get(field, "") for field in context_columns}
                            record.update({"metric_id": metric["id"], "metric_value": value, "bad_case_rule": f"{operator}:{threshold}", "input_row_index": row_index})
                            bad_cases.append(record)
            if not finite_values:
                warnings.append(f"no finite valid values for {metric['id']} in group {group_values}")
            summary: dict[str, Any] = {
                **group_values,
                "metric_id": metric["id"],
                "unit": metric["unit"],
                "total_count": len(group_rows),
                "valid_status_count": sum(analyzable),
                "analyzed_count": len(finite_values),
                "missing_count": missing_count,
                "nonfinite_count": nonfinite_count,
                "invalid_numeric_count": invalid_count,
                "execution_failure_count": (
                    sum(snapshot["execution"] == "failed" for snapshot in snapshots)
                    if using_status_columns
                    else classes.count("execution_failure")
                ),
                "contamination_count": (
                    sum(snapshot["measurement"] == "contaminated" for snapshot in snapshots)
                    if using_status_columns
                    else classes.count("contamination")
                ),
                "missing_status_count": (
                    sum("missing" in snapshot.values() for snapshot in snapshots)
                    if using_status_columns
                    else classes.count("missing_status")
                ),
                "other_status_count": (
                    sum("other" in snapshot.values() for snapshot in snapshots)
                    if using_status_columns
                    else classes.count("other_status")
                ),
                "mean": statistics.fmean(finite_values) if finite_values else None,
                "standard_deviation": statistics.stdev(finite_values) if len(finite_values) > 1 else None,
                "minimum": min(finite_values) if finite_values else None,
                "p50": quantile(finite_values, 0.50),
                "p90": quantile(finite_values, 0.90),
                "p95": quantile(finite_values, 0.95),
                "p99": quantile(finite_values, 0.99),
                "maximum": max(finite_values) if finite_values else None,
                "mean_bootstrap_interval": bootstrap_interval(
                    finite_values,
                    int(metric.get("bootstrap_samples", 0)),
                    float(metric.get("confidence", 0.95)),
                    stable_seed(base_seed, metric["id"], json.dumps(group_values, sort_keys=True)),
                ),
            }
            if using_status_columns:
                summary.update(
                    {
                        "execution_accepted_count": sum(snapshot["execution"] in {"accepted", "not_configured"} for snapshot in snapshots),
                        "execution_missing_count": sum(snapshot["execution"] == "missing" for snapshot in snapshots),
                        "execution_other_count": sum(snapshot["execution"] == "other" for snapshot in snapshots),
                        "measurement_accepted_count": sum(snapshot["measurement"] in {"accepted", "not_configured"} for snapshot in snapshots),
                        "measurement_missing_count": sum(snapshot["measurement"] == "missing" for snapshot in snapshots),
                        "measurement_other_count": sum(snapshot["measurement"] == "other" for snapshot in snapshots),
                        "scientific_observed_count": sum(snapshot["scientific"] in {"observed", "not_configured"} for snapshot in snapshots),
                        "scientific_excluded_count": sum(snapshot["scientific"] == "excluded" for snapshot in snapshots),
                        "scientific_missing_count": sum(snapshot["scientific"] == "missing" for snapshot in snapshots),
                        "scientific_other_count": sum(snapshot["scientific"] == "other" for snapshot in snapshots),
                    }
                )
            summaries.append(summary)

    comparisons: list[dict[str, Any]] = []
    metric_by_id = {metric["id"]: metric for metric in spec["metrics"]}
    for index, comparison in enumerate(spec.get("comparisons", [])):
        metric = metric_by_id[comparison["metric_id"]]
        baseline = selected_values(rows, metric, spec, comparison["baseline_filters"])
        candidate = selected_values(rows, metric, spec, comparison["candidate_filters"])
        record: dict[str, Any] = {
            "id": comparison.get("id", f"comparison-{index + 1}"),
            "metric_id": metric["id"],
            "baseline_filters": comparison["baseline_filters"],
            "candidate_filters": comparison["candidate_filters"],
            "baseline_count": len(baseline),
            "candidate_count": len(candidate),
            "mean_difference_candidate_minus_baseline": statistics.fmean(candidate) - statistics.fmean(baseline) if baseline and candidate else None,
            "ratio_of_means": statistics.fmean(candidate) / statistics.fmean(baseline) if baseline and candidate and statistics.fmean(baseline) != 0 else None,
        }
        bootstrap_samples = int(comparison.get("bootstrap_samples", metric.get("bootstrap_samples", 0)))
        if baseline and candidate and bootstrap_samples > 0:
            rng = random.Random(stable_seed(base_seed, record["id"], metric["id"]))
            effects = [statistics.fmean(rng.choice(candidate) for _ in candidate) - statistics.fmean(rng.choice(baseline) for _ in baseline) for _ in range(bootstrap_samples)]
            confidence = float(comparison.get("confidence", metric.get("confidence", 0.95)))
            alpha = 1 - confidence
            record["mean_difference_bootstrap_interval"] = [quantile(effects, alpha / 2), quantile(effects, 1 - alpha / 2)]
        else:
            record["mean_difference_bootstrap_interval"] = None
        if not baseline or not candidate:
            warnings.append(f"comparison {record['id']} has an empty analysis group")
        comparisons.append(record)
    return summaries, comparisons, bad_cases, warnings


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("\n", encoding="utf-8")
        return
    fields: list[str] = []
    for row in rows:
        for field in row:
            if field not in fields:
                fields.append(field)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: json.dumps(value, sort_keys=True) if isinstance(value, (list, dict)) else value for field, value in row.items()})


def audited_observations(rows: list[dict[str, Any]], spec: dict[str, Any]) -> list[dict[str, Any]]:
    if not spec.get("status_columns"):
        return rows
    reserved = {
        "analysis_execution_status",
        "analysis_measurement_status",
        "analysis_scientific_status",
        "analysis_eligible",
    }
    if any(reserved.intersection(row) for row in rows):
        raise AnalysisError("input uses reserved analysis status columns")
    result: list[dict[str, Any]] = []
    for row in rows:
        snapshot = status_snapshot(row, spec)
        result.append(
            {
                **row,
                "analysis_execution_status": snapshot["execution"],
                "analysis_measurement_status": snapshot["measurement"],
                "analysis_scientific_status": snapshot["scientific"],
                "analysis_eligible": status_is_analyzable(snapshot),
            }
        )
    return result


def draft_findings_text(
    spec: dict[str, Any],
    rows: list[dict[str, Any]],
    summaries: list[dict[str, Any]],
    warnings: list[str],
) -> str:
    blockers = spec.get("unresolved_blockers", [])
    snapshots = [status_snapshot(row, spec) for row in rows]
    eligible_count = sum(status_is_analyzable(snapshot) for snapshot in snapshots)
    lines = [
        "# Draft Findings",
        "",
        "This is a review scaffold derived from recorded counts and summaries. It is not an accepted scientific conclusion.",
        "",
        "## Coverage",
        "",
        f"- Input observations: {len(rows)}",
        f"- Status-eligible observations: {eligible_count}",
        f"- Execution failures: {sum(snapshot['execution'] == 'failed' for snapshot in snapshots)}",
        f"- Measurement contamination states: {sum(snapshot['measurement'] == 'contaminated' for snapshot in snapshots)}",
        f"- Scientific exclusions: {sum(snapshot['scientific'] == 'excluded' for snapshot in snapshots)}",
        "",
        "## Derived summary index",
        "",
    ]
    for summary in summaries[:20]:
        group = {key: summary[key] for key in spec.get("group_by", []) if key in summary}
        lines.append(
            f"- `{summary['metric_id']}` group `{json.dumps(group, ensure_ascii=False, sort_keys=True)}`: "
            f"analyzed {summary['analyzed_count']} of {summary['total_count']}; "
            f"mean={summary['mean']!r}, p50={summary['p50']!r}, p99={summary['p99']!r}."
        )
    if not summaries:
        lines.append("- No summary row was produced.")
    elif len(summaries) > 20:
        lines.append(f"- {len(summaries) - 20} additional summary rows remain in `derived/summary.csv`.")
    lines.extend(["", "## Blockers and warnings", ""])
    if blockers:
        for blocker in blockers:
            lines.append(f"- BLOCKER: {json.dumps(blocker, ensure_ascii=False, sort_keys=True) if isinstance(blocker, (dict, list)) else blocker}")
    if warnings:
        lines.extend(f"- WARNING: {warning}" for warning in warnings)
    if not blockers and not warnings:
        lines.append("- No mechanical blocker or warning was recorded; scientific review is still required.")
    lines.extend(
        [
            "",
            "## Interpretation boundary",
            "",
            "Review the estimand, dependencies, exclusions, uncertainty, sensitivity, and alternative explanations before replacing this draft with bounded findings.",
            "",
        ]
    )
    return "\n".join(lines)


def output_record(root: Path, path: Path, role: str) -> dict[str, Any]:
    relative = path.relative_to(root).as_posix()
    normalized = PurePosixPath(relative)
    if normalized.is_absolute() or any(part in {"", ".", ".."} for part in normalized.parts):
        raise AnalysisError("output path is not normalized")
    return {"path": relative, "role": role, "bytes": path.stat().st_size, "sha256": sha256_file(path)}


def run_analysis(input_path: Path, spec_path: Path, output_dir: Path) -> None:
    try:
        input_path = input_path.resolve(strict=True)
        spec_path = spec_path.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise AnalysisError(f"input or spec cannot be resolved: {exc}") from exc
    output_dir = lexical_absolute(output_dir)
    if not stat.S_ISREG(input_path.stat().st_mode) or not stat.S_ISREG(spec_path.stat().st_mode):
        raise AnalysisError("input and spec must be regular files")
    try:
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AnalysisError(f"invalid analysis spec: {exc}") from exc
    errors = validate_spec(spec)
    if errors:
        raise AnalysisError("; ".join(errors))
    if spec["status"] == "frozen":
        raise AnalysisError(
            "the baseline summarizer produces draft findings only; use status=draft, "
            "then review findings and freeze the completed package explicitly"
        )
    rows = load_rows(input_path)
    summaries, comparisons, bad_cases, warnings = build_summary(rows, spec)
    blockers = spec.get("unresolved_blockers", [])
    if blockers:
        warnings.extend(f"unresolved blocker: {blocker}" for blocker in blockers)
    if spec["status"] == "draft":
        warnings.append("analysis status is draft; findings require scientific review")
    observations = audited_observations(rows, spec)

    parent = output_dir.parent
    require_output_missing(output_dir)
    check_directory_chain(parent, allow_missing=True)
    parent.mkdir(parents=True, exist_ok=True)
    check_directory_chain(parent, allow_missing=False)
    require_output_missing(output_dir)
    staging = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.partial.", dir=parent))
    try:
        (staging / "derived").mkdir()
        normalized_spec = staging / "analysis-spec.json"
        normalized_spec.write_text(json.dumps(spec, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        metric_dictionary = {
            "schema_version": 1,
            "analysis_id": spec["analysis_id"],
            "metrics": spec["metrics"],
            "status_columns": spec.get("status_columns"),
        }
        metric_path = staging / "metric-dictionary.json"
        metric_path.write_text(json.dumps(metric_dictionary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        summary_path = staging / "derived" / "summary.csv"
        bad_case_path = staging / "derived" / "bad-cases.csv"
        observations_path = staging / "derived" / "observations.csv"
        write_csv(observations_path, observations)
        write_csv(summary_path, summaries)
        write_csv(bad_case_path, bad_cases)
        statistics_path = staging / "statistics.json"
        statistics_value = {
            "schema_version": 1,
            "analysis_id": spec["analysis_id"],
            "summaries": summaries,
            "comparisons": comparisons,
            "warnings": warnings,
            "warning_records": [
                {"severity": "warning", "code": "ANALYSIS_REVIEW", "message": warning}
                for warning in warnings
            ],
        }
        statistics_path.write_text(json.dumps(statistics_value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
        findings_path = staging / "findings.md"
        findings_path.write_text(
            draft_findings_text(spec, rows, summaries, warnings), encoding="utf-8"
        )
        outputs = [
            output_record(staging, normalized_spec, "analysis_spec"),
            output_record(staging, metric_path, "metric_dictionary"),
            output_record(staging, observations_path, "derived_observations"),
            output_record(staging, summary_path, "derived_summary"),
            output_record(staging, bad_case_path, "bad_cases"),
            output_record(staging, statistics_path, "statistics"),
            output_record(staging, findings_path, "draft_findings"),
        ]
        manifest = {
            "schema_version": 1,
            "artifact_type": "experiment_analysis_manifest",
            "analysis_id": spec["analysis_id"],
            "status": spec["status"],
            "findings_status": "draft",
            "input": {"name": input_path.name, "bytes": input_path.stat().st_size, "sha256": sha256_file(input_path)},
            "source_spec": {"name": spec_path.name, "bytes": spec_path.stat().st_size, "sha256": sha256_file(spec_path)},
            "tool": {"name": "summarize_measurements.py", "version": VERSION},
            "outputs": outputs,
        }
        (staging / "analysis-manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        publish_staging(staging, output_dir)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        run_analysis(args.input, args.spec, args.output_dir)
    except (OSError, AnalysisError) as exc:
        print(f"ERROR: {exc}")
        return 1
    print("analysis package: CREATED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
