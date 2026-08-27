"""Campaign configuration loading and mechanical validation."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

from .connectors import CONNECTOR_FACTORIES
from .normalize import sha256_text, stable_json
from .security import find_secret_shaped_config


ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
DEFAULT_LIMITS = {
    "concurrency": 2,
    "max_pages_per_task": 1,
    "max_items_per_page": 20,
    "max_candidates": 100,
    "max_total_bytes": 5_000_000,
    "package_stop_watermark_bytes": 100_000_000,
    "max_response_bytes": 2_000_000,
    "max_wall_seconds": 3600,
    "timeout_seconds": 20,
    "max_retries": 2,
    "backoff_seconds": 1.0,
    "max_depth": 0,
}
DEFAULT_FETCH_POLICY = {
    "allowed_hosts": [],
    "allowed_mime_types": ["text/html", "text/plain"],
    "allow_private_hosts": False,
    "robots_unavailable": "deny",
    "retain_content": False,
    "max_fetch_pages": 20,
}


def load_config(path: Path) -> tuple[dict[str, Any], str, list[str]]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid campaign configuration: {exc}") from exc
    errors, warnings = validate_config(value)
    if errors:
        raise ValueError("invalid campaign configuration:\n- " + "\n- ".join(errors))
    normalized = normalize_config(value)
    return normalized, sha256_text(stable_json(normalized)), warnings


def validate_config(value: Any) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(value, dict):
        return ["configuration root must be an object"], warnings
    if value.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    _check_id(value.get("campaign_id"), "campaign_id", errors)
    queries = value.get("queries")
    query_ids: set[str] = set()
    if not isinstance(queries, list) or not queries:
        errors.append("queries must be a non-empty list")
        queries = []
    for index, query in enumerate(queries):
        if not isinstance(query, dict):
            errors.append(f"queries[{index}] must be an object")
            continue
        query_id = query.get("id")
        _check_id(query_id, f"queries[{index}].id", errors)
        if isinstance(query_id, str):
            if query_id in query_ids:
                errors.append(f"duplicate query ID: {query_id}")
            query_ids.add(query_id)
        if not isinstance(query.get("text"), str) or not query["text"].strip():
            errors.append(f"queries[{index}].text must be a non-empty string")
        if not isinstance(query.get("language", "und"), str):
            errors.append(f"queries[{index}].language must be a string")
        depth = query.get("depth", 0)
        if not isinstance(depth, int) or isinstance(depth, bool) or depth < 0:
            errors.append(f"queries[{index}].depth must be a non-negative integer")
    for index, query in enumerate(queries):
        if not isinstance(query, dict):
            continue
        parent = query.get("parent_query_id")
        if parent is not None and (not isinstance(parent, str) or parent not in query_ids):
            errors.append(f"queries[{index}].parent_query_id is unknown")
    connectors = value.get("connectors")
    connector_ids: set[str] = set()
    enabled_count = 0
    if not isinstance(connectors, list) or not connectors:
        errors.append("connectors must be a non-empty list")
        connectors = []
    for index, connector in enumerate(connectors):
        if not isinstance(connector, dict):
            errors.append(f"connectors[{index}] must be an object")
            continue
        connector_id = connector.get("id")
        _check_id(connector_id, f"connectors[{index}].id", errors)
        if isinstance(connector_id, str):
            if connector_id in connector_ids:
                errors.append(f"duplicate connector ID: {connector_id}")
            connector_ids.add(connector_id)
        connector_type = connector.get("type")
        if connector_type not in CONNECTOR_FACTORIES:
            errors.append(f"connectors[{index}].type is unsupported")
        enabled = connector.get("enabled", True)
        if not isinstance(enabled, bool):
            errors.append(f"connectors[{index}].enabled must be boolean")
        if enabled is True:
            enabled_count += 1
        if not isinstance(connector.get("options", {}), dict):
            errors.append(f"connectors[{index}].options must be an object")
        else:
            options = connector.get("options", {})
            if "credential_env" in options and connector_type not in {"openalex", "github-gh"}:
                errors.append(
                    f"connectors[{index}].options.credential_env is not supported by {connector_type}"
                )
            if "contact_env" in options and connector_type not in {"crossref", "europe-pmc", "pubmed"}:
                errors.append(
                    f"connectors[{index}].options.contact_env is not supported by {connector_type}"
                )
            for plain_contact in ("mailto", "email"):
                if plain_contact in options:
                    errors.append(
                        f"connectors[{index}].options.{plain_contact} must be supplied through contact_env"
                    )
    if connectors and enabled_count == 0:
        errors.append("at least one connector must be enabled")
    limits = value.get("limits", {})
    if not isinstance(limits, dict):
        errors.append("limits must be an object")
        limits = {}
    merged_limits = {**DEFAULT_LIMITS, **limits}
    unknown_limits = sorted(set(limits) - set(DEFAULT_LIMITS))
    if unknown_limits:
        errors.append("unsupported limits fields: " + ", ".join(unknown_limits))
    integer_ranges = {
        "concurrency": (1, 64),
        "max_pages_per_task": (1, 100_000),
        "max_items_per_page": (1, 10_000),
        "max_candidates": (1, 10_000_000),
        "max_total_bytes": (1, 10**12),
        "package_stop_watermark_bytes": (1, 10**12),
        "max_response_bytes": (1, 10**9),
        "max_wall_seconds": (1, 604_800),
        "max_retries": (0, 20),
        "max_depth": (0, 20),
    }
    for key, (minimum, maximum) in integer_ranges.items():
        item = merged_limits.get(key)
        if not isinstance(item, int) or isinstance(item, bool) or not minimum <= item <= maximum:
            errors.append(f"limits.{key} must be an integer in [{minimum}, {maximum}]")
    for key, minimum, maximum in (("timeout_seconds", 0.1, 300.0), ("backoff_seconds", 0.0, 60.0)):
        item = merged_limits.get(key)
        if not isinstance(item, (int, float)) or isinstance(item, bool) or not minimum <= float(item) <= maximum:
            errors.append(f"limits.{key} must be in [{minimum}, {maximum}]")
    max_depth = merged_limits.get("max_depth")
    if isinstance(max_depth, int):
        skipped = [
            query.get("id") for query in queries
            if isinstance(query, dict) and isinstance(query.get("depth", 0), int) and query.get("depth", 0) > max_depth
        ]
        if skipped:
            warnings.append(f"queries beyond max_depth will not be scheduled: {', '.join(map(str, skipped))}")
    fetch_policy = value.get("fetch_policy", {})
    if not isinstance(fetch_policy, dict):
        errors.append("fetch_policy must be an object")
        fetch_policy = {}
    merged_fetch = {**DEFAULT_FETCH_POLICY, **fetch_policy}
    hosts = merged_fetch.get("allowed_hosts")
    if not isinstance(hosts, list) or any(not isinstance(host, str) or not host for host in hosts):
        errors.append("fetch_policy.allowed_hosts must be a list of host names")
    mimes = merged_fetch.get("allowed_mime_types")
    if not isinstance(mimes, list) or any(not isinstance(mime, str) or "/" not in mime for mime in mimes):
        errors.append("fetch_policy.allowed_mime_types must be a list of MIME types")
    if merged_fetch.get("robots_unavailable") not in {"deny", "allow"}:
        errors.append("fetch_policy.robots_unavailable must be deny or allow")
    for key in ("allow_private_hosts", "retain_content"):
        if not isinstance(merged_fetch.get(key), bool):
            errors.append(f"fetch_policy.{key} must be boolean")
    max_fetch = merged_fetch.get("max_fetch_pages")
    if not isinstance(max_fetch, int) or isinstance(max_fetch, bool) or not 0 <= max_fetch <= 100_000:
        errors.append("fetch_policy.max_fetch_pages must be an integer in [0, 100000]")
    errors.extend(find_secret_shaped_config(value))
    return errors, warnings


def normalize_config(value: dict[str, Any]) -> dict[str, Any]:
    normalized = json.loads(json.dumps(value))
    normalized["limits"] = {**DEFAULT_LIMITS, **normalized.get("limits", {})}
    normalized["fetch_policy"] = {**DEFAULT_FETCH_POLICY, **normalized.get("fetch_policy", {})}
    for query in normalized["queries"]:
        query.setdefault("language", "und")
        query.setdefault("depth", 0)
    for connector in normalized["connectors"]:
        connector.setdefault("enabled", True)
        connector.setdefault("options", {})
    return normalized


def _check_id(value: Any, label: str, errors: list[str]) -> None:
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        errors.append(f"{label} must match {ID_RE.pattern}")
