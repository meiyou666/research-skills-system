#!/usr/bin/env python3
"""Run or resume a bounded multi-source collection campaign."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
import threading
import time
from typing import Any
from urllib.parse import urlsplit

from source_collector.config import load_config
from source_collector.connectors import create_connector
from source_collector.model import ConnectorContext, DiscoveryPage, Query
from source_collector.page_fetch import PageFetcher
from source_collector.security import NetworkError, SafeHttpClient, SafetyError
from source_collector.store import CampaignStore, utc_now, write_manifest


DEFAULT_INTERVALS = {
    "arxiv": 3.0,
    "crossref": 1.0,
    "pubmed": 0.34,
    "openalex": 0.2,
    "europe-pmc": 1.0,
    "rss": 1.0,
    "searxng": 0.5,
    "github-gh": 2.1,
    "web-seed": 0.0,
    "fixture": 0.0,
}
USER_AGENT = "research-source-collector/1.0 (+bounded provenance collection)"


class RateLimiter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._last: dict[str, float] = {}

    def wait(self, key: str, interval: float) -> None:
        if interval <= 0:
            return
        with self._lock:
            now = time.monotonic()
            scheduled = max(now, self._last.get(key, 0.0) + interval)
            self._last[key] = scheduled
        delay = scheduled - now
        if delay > 0:
            time.sleep(delay)


@dataclass
class WorkResult:
    task: dict[str, Any]
    page: DiscoveryPage | None
    started_at: str
    finished_at: str
    error: str | None = None
    category: str | None = None


def run_task(
    task: dict[str, Any],
    *,
    http: SafeHttpClient,
    limiter: RateLimiter,
    limits: dict[str, Any],
    response_byte_allocation: int,
) -> WorkResult:
    started_at = utc_now()
    try:
        interval = task["options"].get("min_interval_seconds", DEFAULT_INTERVALS.get(task["connector_type"], 1.0))
        if not isinstance(interval, (int, float)) or interval < 0 or interval > 60:
            raise SafetyError("min_interval_seconds must be in [0, 60]")
        limiter.wait(_rate_limit_key(task), float(interval))
        connector = create_connector(task["connector_type"])
        query = Query(
            id=task["query_id"],
            text=task["query_text"],
            language=task["language"],
            parent_query_id=task["parent_query_id"],
            direction=task["direction"],
            depth=task["depth"],
        )
        context = ConnectorContext(
            http=http,
            connector_id=task["connector_id"],
            options=task["options"],
            timeout_seconds=float(limits["timeout_seconds"]),
            max_response_bytes=response_byte_allocation,
            user_agent=USER_AGENT,
        )
        page = connector.discover(query, task.get("cursor"), int(limits["max_items_per_page"]), context)
        if (
            not isinstance(page.response_bytes, int)
            or isinstance(page.response_bytes, bool)
            or page.response_bytes < 0
        ):
            raise SafetyError("connector response_bytes must be a non-negative integer")
        if page.response_bytes > response_byte_allocation:
            raise SafetyError("connector response exceeds its allocated campaign byte budget")
        return WorkResult(task, page, started_at, utc_now())
    except SafetyError as exc:
        return WorkResult(task, None, started_at, utc_now(), str(exc), "safety")
    except NetworkError as exc:
        return WorkResult(task, None, started_at, utc_now(), str(exc), "network")
    except Exception as exc:  # Connector bugs are isolated and labeled without source data.
        return WorkResult(task, None, started_at, utc_now(), f"connector exception ({type(exc).__name__})", "connector")


def _rate_limit_key(task: dict[str, Any]) -> str:
    endpoint = task["options"].get("endpoint") or task["options"].get("feed_url")
    if isinstance(endpoint, str):
        host = urlsplit(endpoint).hostname
        if host:
            return "host:" + host.lower()
    return "backend:" + task["connector_type"]


def run_discovery(
    store: CampaignStore,
    config: dict[str, Any],
    *,
    max_work_items: int | None,
) -> tuple[int, bool]:
    limits = config["limits"]
    http = SafeHttpClient(USER_AGENT)
    limiter = RateLimiter()
    completed_work = 0
    stopped_by_work_limit = False
    started_monotonic = time.monotonic()
    with ThreadPoolExecutor(max_workers=int(limits["concurrency"])) as pool:
        while True:
            if store.candidate_count() >= int(limits["max_candidates"]):
                store.mark_open_tasks_limited("campaign candidate limit reached")
                break
            remaining_response_bytes = int(limits["max_total_bytes"]) - store.response_bytes()
            if remaining_response_bytes <= 0:
                store.mark_open_tasks_limited("campaign byte limit reached")
                break
            if store.package_bytes(include_manifest=False) >= int(limits["package_stop_watermark_bytes"]):
                store.mark_open_tasks_limited("campaign package stop watermark reached")
                break
            if time.monotonic() - started_monotonic >= int(limits["max_wall_seconds"]):
                store.mark_open_tasks_limited("campaign wall-time limit reached")
                break
            remaining_work = None if max_work_items is None else max_work_items - completed_work
            if remaining_work is not None and remaining_work <= 0:
                stopped_by_work_limit = True
                break
            batch_size = min(int(limits["concurrency"]), remaining_response_bytes)
            if remaining_work is not None:
                batch_size = min(batch_size, remaining_work)
            tasks = store.ready_tasks(batch_size, time.time())
            if not tasks:
                retry_at = store.retry_wait()
                counts = store.task_counts()
                if retry_at is not None and counts.get("retry", 0):
                    time.sleep(max(0.0, min(30.0, retry_at - time.time())))
                    continue
                break
            allocations = _allocate_response_budgets(
                len(tasks),
                remaining_response_bytes,
                int(limits["max_response_bytes"]),
            )
            futures = [
                pool.submit(
                    run_task,
                    task,
                    http=http,
                    limiter=limiter,
                    limits=limits,
                    response_byte_allocation=allocation,
                )
                for task, allocation in zip(tasks, allocations, strict=True)
            ]
            for future in as_completed(futures):
                result = future.result()
                completed_work += 1
                if result.page is not None:
                    store.record_page(
                        result.task,
                        result.page,
                        started_at=result.started_at,
                        finished_at=result.finished_at,
                        max_pages=int(limits["max_pages_per_task"]),
                        max_candidates=int(limits["max_candidates"]),
                        retain_content=bool(config["fetch_policy"]["retain_content"]),
                    )
                else:
                    delay = min(30.0, float(limits["backoff_seconds"]) * (2 ** max(0, result.task["attempt_count"] - 1)))
                    store.record_failure(
                        result.task,
                        started_at=result.started_at,
                        finished_at=result.finished_at,
                        message=result.error or "connector failed",
                        category=result.category or "connector",
                        max_retries=int(limits["max_retries"]),
                        next_attempt_at=time.time() + delay,
                    )
    return completed_work, stopped_by_work_limit


def _allocate_response_budgets(task_count: int, remaining: int, per_response_cap: int) -> list[int]:
    """Reserve disjoint positive byte budgets for one concurrent task batch."""

    if task_count < 0 or task_count > remaining:
        raise ValueError("task count exceeds the remaining response-byte budget")
    allocations: list[int] = []
    unallocated = remaining
    for index in range(task_count):
        tasks_left = task_count - index
        allocation = min(per_response_cap, max(1, unallocated // tasks_left))
        allocations.append(allocation)
        unallocated -= allocation
    return allocations


def fetch_pages(store: CampaignStore, config: dict[str, Any]) -> int:
    policy = config["fetch_policy"]
    allowed_hosts = {host.encode("idna").decode("ascii").lower() for host in policy["allowed_hosts"]}
    if not allowed_hosts:
        raise ValueError("--fetch-pages requires fetch_policy.allowed_hosts")
    http = SafeHttpClient(USER_AGENT)
    fetcher = PageFetcher(http, USER_AGENT)
    fetched = 0
    for candidate in store.fetch_candidates(int(policy["max_fetch_pages"]) * 4 + 1):
        if fetched >= int(policy["max_fetch_pages"]):
            break
        remaining_response_bytes = int(config["limits"]["max_total_bytes"]) - store.response_bytes()
        if remaining_response_bytes <= 0:
            break
        if store.package_bytes(include_manifest=False) >= int(config["limits"]["package_stop_watermark_bytes"]):
            break
        host = (urlsplit(candidate["canonical_url"]).hostname or "").lower()
        if host not in allowed_hosts:
            continue
        try:
            text, mime_type, status, response_bytes = fetcher.fetch(
                candidate["canonical_url"],
                allowed_hosts=allowed_hosts,
                allow_private_hosts=bool(policy["allow_private_hosts"]),
                allowed_mime_types=set(policy["allowed_mime_types"]),
                robots_unavailable=policy["robots_unavailable"],
                timeout_seconds=float(config["limits"]["timeout_seconds"]),
                max_bytes=min(
                    int(config["limits"]["max_response_bytes"]),
                    remaining_response_bytes,
                ),
            )
            if response_bytes > remaining_response_bytes:
                raise SafetyError("page fetch exceeds the remaining campaign byte budget")
            store.record_fetch(
                candidate,
                text=text,
                mime_type=mime_type,
                status=status,
                fetched_at=utc_now(),
                retain_content=bool(policy["retain_content"]),
                acquisition_method="robots-checked-public-page",
                retention_scope="caller_review_required",
                response_bytes=response_bytes,
            )
            fetched += 1
        except SafetyError as exc:
            store.record_fetch_failure(candidate, str(exc), "safety")
        except NetworkError as exc:
            store.record_fetch_failure(candidate, str(exc), "network")
    return fetched


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-work-items", type=int)
    parser.add_argument("--fetch-pages", action="store_true")
    parser.add_argument(
        "--refresh-connectors",
        help="comma-separated connector IDs to re-run for an incremental update",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.max_work_items is not None and args.max_work_items < 1:
        print("ERROR: --max-work-items must be positive")
        return 2
    try:
        config, config_hash, warnings = load_config(args.config)
        if args.output.exists() and args.output.is_symlink():
            raise ValueError("output directory must not be a symbolic link")
        store = CampaignStore(args.output, config, config_hash)
        try:
            if args.refresh_connectors:
                refresh_ids = {item.strip() for item in args.refresh_connectors.split(",") if item.strip()}
                if not refresh_ids:
                    raise ValueError("--refresh-connectors did not contain an ID")
                store.refresh_connectors(refresh_ids)
            work_items, stopped = run_discovery(store, config, max_work_items=args.max_work_items)
            fetched = fetch_pages(store, config) if args.fetch_pages else 0
            store.export(config)
            store.finalize_status(stopped)
            state = store.export(config)
        finally:
            store.close()
        write_manifest(args.output, state)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}")
        return 2
    for warning in warnings:
        print(f"WARNING: {warning}")
    print(
        f"campaign {state['campaign_id']}: status={state['status']} "
        f"work_items={work_items} candidates={state['candidate_count']} fetched_pages={fetched}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
