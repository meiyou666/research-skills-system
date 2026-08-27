#!/usr/bin/env python3
"""Create a bounded, reviewable query fragment from collected relation edges."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any


DEFAULT_KINDS = {
    "references",
    "is-preprint-of",
    "is-version-of",
    "related",
    "author",
    "has-code",
    "belongs-to-repository",
}


def load_inventory(path: Path) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"line {number} is not valid JSON: {exc.msg}") from exc
        if not isinstance(item, dict):
            raise ValueError(f"line {number} must be an object")
        output.append(item)
    return output


def build_queries(
    inventory: list[dict[str, Any]],
    *,
    kinds: set[str],
    max_items: int,
    max_depth: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    candidates: list[tuple[str, str, str | None, int]] = []
    skipped: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in inventory:
        source_id = item.get("candidate_id")
        queries = item.get("queries")
        parent = queries[0] if isinstance(queries, list) and queries and isinstance(queries[0], dict) else {}
        parent_id = parent.get("id") if isinstance(parent.get("id"), str) else None
        parent_depth = parent.get("depth", 0) if isinstance(parent.get("depth", 0), int) else 0
        relations = item.get("relations")
        if not isinstance(relations, list):
            continue
        for relation in relations:
            if not isinstance(relation, dict):
                continue
            kind, target = relation.get("kind"), relation.get("target")
            if kind not in kinds or not isinstance(target, str) or not target.strip():
                continue
            depth = parent_depth + 1
            if depth > max_depth:
                skipped.append({"candidate_id": source_id, "kind": kind, "target": target, "reason": "max_depth"})
                continue
            normalized_target = " ".join(target.split())
            key = (str(kind), normalized_target.casefold())
            if key in seen:
                continue
            seen.add(key)
            candidates.append((str(kind), normalized_target, parent_id, depth))
    candidates.sort(key=lambda item: (item[0], item[1].casefold(), item[2] or ""))
    selected = candidates[:max_items]
    for kind, target, parent_id, depth in candidates[max_items:]:
        skipped.append({"candidate_id": None, "kind": kind, "target": target, "reason": "max_items"})
    queries = []
    for kind, target, parent_id, depth in selected:
        digest = hashlib.sha256(f"{kind}\0{target}".encode("utf-8")).hexdigest()[:16]
        query = {
            "id": f"relation-{_slug(kind)}-{digest}",
            "text": target,
            "language": "und",
            "direction": kind,
            "depth": depth,
        }
        if parent_id:
            query["parent_query_id"] = parent_id
        queries.append(query)
    return queries, skipped


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return slug[:32] or "edge"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("inventory", type=Path)
    parser.add_argument("--kinds", default=",".join(sorted(DEFAULT_KINDS)))
    parser.add_argument("--max-items", type=int, default=100)
    parser.add_argument("--max-depth", type=int, default=1)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.max_items < 0 or args.max_depth < 0:
        print("ERROR: --max-items and --max-depth must be non-negative", file=sys.stderr)
        return 2
    kinds = {item.strip() for item in args.kinds.split(",") if item.strip()}
    if not kinds:
        print("ERROR: --kinds must include at least one relation kind", file=sys.stderr)
        return 2
    try:
        inventory = load_inventory(args.inventory)
        queries, skipped = build_queries(
            inventory,
            kinds=kinds,
            max_items=args.max_items,
            max_depth=args.max_depth,
        )
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    output = {
        "schema_version": 1,
        "artifact_type": "relation_query_fragment",
        "source_inventory": args.inventory.name,
        "source_inventory_bytes": args.inventory.stat().st_size,
        "source_inventory_sha256": hashlib.sha256(args.inventory.read_bytes()).hexdigest(),
        "selected_relation_kinds": sorted(kinds),
        "limits": {"max_items": args.max_items, "max_depth": args.max_depth},
        "queries": queries,
        "skipped": skipped,
        "review_required": True,
    }
    encoded = json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(encoded, encoding="utf-8")
    else:
        sys.stdout.write(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
