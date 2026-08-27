"""SQLite campaign state and deterministic exports."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import sqlite3
import stat
import tempfile
from typing import Any, Iterable

from .model import CONTENT_SCOPES, DiscoveryPage, DiscoveryRecord, Query
from .normalize import candidate_id, identify, sha256_text, stable_json


SCHEMA_VERSION = 1
EXTRACTOR_VERSION = "source-collector/1.0.0"
CONTENT_PRIORITY = {
    "metadata": 0,
    "discovery_snippet": 1,
    "abstract": 2,
    "partial_content": 3,
    "full_text_candidate": 4,
}


def _plain_file_or_missing(path: Path, label: str) -> os.stat_result | None:
    try:
        entry = path.lstat()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise ValueError(f"cannot inspect {label}: {exc}") from exc
    if stat.S_ISLNK(entry.st_mode) or not stat.S_ISREG(entry.st_mode):
        raise ValueError(f"{label} must be a regular file, not a symlink or special file")
    return entry


def _plain_directory(path: Path, label: str, *, create: bool) -> None:
    try:
        entry = path.lstat()
    except FileNotFoundError:
        if not create:
            raise ValueError(f"{label} does not exist") from None
        path.mkdir(parents=True, exist_ok=False)
        return
    except OSError as exc:
        raise ValueError(f"cannot inspect {label}: {exc}") from exc
    if stat.S_ISLNK(entry.st_mode) or not stat.S_ISDIR(entry.st_mode):
        raise ValueError(f"{label} must be a plain directory")


@contextmanager
def _atomic_text_writer(path: Path):  # type: ignore[no-untyped-def]
    """Yield a same-directory text stream and publish it with one rename."""

    _plain_file_or_missing(path, path.name)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.stage.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            descriptor = -1
            yield handle
            handle.flush()
            os.fsync(handle.fileno())
        _plain_file_or_missing(path, path.name)
        os.replace(temporary, path)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)


def _atomic_write_text(path: Path, value: str, *, encoding: str = "utf-8") -> None:
    if encoding != "utf-8":
        data = value.encode(encoding)
        _atomic_write_bytes(path, data)
        return
    with _atomic_text_writer(path) as handle:
        handle.write(value)


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    _plain_file_or_missing(path, path.name)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.stage.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        _plain_file_or_missing(path, path.name)
        os.replace(temporary, path)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class CampaignStore:
    def __init__(self, root: Path, config: dict[str, Any], config_hash: str) -> None:
        self.root = root
        _plain_directory(self.root, "campaign output directory", create=True)
        self.snapshots = self.root / "snapshots"
        _plain_directory(self.snapshots, "snapshots directory", create=True)
        self.database_path = self.root / "campaign.sqlite3"
        _plain_file_or_missing(self.database_path, "campaign.sqlite3")
        self.connection = sqlite3.connect(self.database_path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.execute("PRAGMA journal_mode = DELETE")
        self._create_schema()
        self._initialize(config, config_hash)
        self.connection.execute("UPDATE tasks SET state='pending' WHERE state='running'")
        self.connection.commit()

    def close(self) -> None:
        self.connection.commit()
        self.connection.close()

    def _create_schema(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS schema_info (
                version INTEGER NOT NULL,
                applied_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS campaigns (
                campaign_id TEXT PRIMARY KEY,
                config_hash TEXT NOT NULL,
                config_json TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                response_bytes INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS queries (
                query_id TEXT PRIMARY KEY,
                query_text TEXT NOT NULL,
                language TEXT NOT NULL,
                parent_query_id TEXT,
                direction TEXT,
                depth INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS connectors (
                connector_id TEXT PRIMARY KEY,
                connector_type TEXT NOT NULL,
                options_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS tasks (
                task_key TEXT PRIMARY KEY,
                query_id TEXT NOT NULL REFERENCES queries(query_id),
                connector_id TEXT NOT NULL REFERENCES connectors(connector_id),
                state TEXT NOT NULL,
                cursor TEXT,
                page_count INTEGER NOT NULL DEFAULT 0,
                result_count INTEGER NOT NULL DEFAULT 0,
                attempt_count INTEGER NOT NULL DEFAULT 0,
                next_attempt_at REAL NOT NULL DEFAULT 0,
                last_error TEXT,
                total_hint INTEGER,
                UNIQUE(query_id, connector_id)
            );
            CREATE TABLE IF NOT EXISTS raw_records (
                raw_id TEXT PRIMARY KEY,
                task_key TEXT NOT NULL REFERENCES tasks(task_key),
                source_id TEXT NOT NULL,
                source_rank INTEGER NOT NULL,
                discovered_at TEXT NOT NULL,
                raw_json TEXT NOT NULL,
                record_sha256 TEXT NOT NULL,
                response_page INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS candidates (
                candidate_id TEXT PRIMARY KEY,
                canonical_key TEXT NOT NULL UNIQUE,
                canonical_url TEXT,
                external_id TEXT,
                version TEXT,
                version_cluster TEXT,
                title TEXT,
                source_owner TEXT,
                language TEXT NOT NULL,
                mime_type TEXT,
                http_status INTEGER,
                content_scope TEXT NOT NULL,
                access_level TEXT NOT NULL,
                content_sha256 TEXT NOT NULL,
                hash_scope TEXT NOT NULL,
                snapshot_path TEXT,
                extractor_version TEXT NOT NULL,
                trust_boundary TEXT NOT NULL,
                published_at TEXT,
                updated_at TEXT,
                fetched_at TEXT,
                fetch_status TEXT NOT NULL DEFAULT 'not_requested',
                acquisition_method TEXT NOT NULL,
                retention_scope TEXT NOT NULL,
                collection_notes_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS occurrences (
                candidate_id TEXT NOT NULL REFERENCES candidates(candidate_id),
                raw_id TEXT NOT NULL REFERENCES raw_records(raw_id),
                query_id TEXT NOT NULL REFERENCES queries(query_id),
                connector_id TEXT NOT NULL REFERENCES connectors(connector_id),
                source_rank INTEGER NOT NULL,
                discovered_at TEXT NOT NULL,
                fetched_at TEXT,
                retry_state TEXT NOT NULL,
                error TEXT,
                PRIMARY KEY(candidate_id, raw_id)
            );
            CREATE TABLE IF NOT EXISTS relations (
                candidate_id TEXT NOT NULL REFERENCES candidates(candidate_id),
                kind TEXT NOT NULL,
                target TEXT NOT NULL,
                source TEXT NOT NULL,
                PRIMARY KEY(candidate_id, kind, target, source)
            );
            CREATE TABLE IF NOT EXISTS snapshots (
                sha256 TEXT PRIMARY KEY,
                path TEXT NOT NULL UNIQUE,
                bytes INTEGER NOT NULL,
                mime_type TEXT NOT NULL,
                acquired_at TEXT NOT NULL,
                acquisition_method TEXT NOT NULL,
                retention_scope TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS query_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_key TEXT NOT NULL,
                query_id TEXT NOT NULL,
                connector_id TEXT NOT NULL,
                page_number INTEGER NOT NULL,
                cursor_before TEXT,
                cursor_after TEXT,
                started_at TEXT NOT NULL,
                finished_at TEXT NOT NULL,
                outcome TEXT NOT NULL,
                record_count INTEGER NOT NULL,
                response_bytes INTEGER NOT NULL,
                total_hint INTEGER,
                error TEXT
            );
            CREATE TABLE IF NOT EXISTS errors (
                error_id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_key TEXT NOT NULL,
                phase TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                retry_number INTEGER NOT NULL,
                terminal INTEGER NOT NULL,
                category TEXT NOT NULL,
                message TEXT NOT NULL
            );
            """
        )
        row = self.connection.execute("SELECT version FROM schema_info ORDER BY rowid DESC LIMIT 1").fetchone()
        if row is None:
            self.connection.execute("INSERT INTO schema_info(version, applied_at) VALUES (?, ?)", (SCHEMA_VERSION, utc_now()))
        elif row["version"] != SCHEMA_VERSION:
            raise ValueError(f"unsupported campaign database schema: {row['version']}")
        self.connection.commit()

    def _initialize(self, config: dict[str, Any], config_hash: str) -> None:
        campaign_id = config["campaign_id"]
        row = self.connection.execute("SELECT * FROM campaigns").fetchone()
        if row is not None:
            if row["campaign_id"] != campaign_id or row["config_hash"] != config_hash:
                raise ValueError("existing campaign state has a different campaign ID or configuration hash")
            return
        now = utc_now()
        self.connection.execute(
            "INSERT INTO campaigns VALUES (?, ?, ?, 'partial', ?, ?, 0)",
            (campaign_id, config_hash, stable_json(config), now, now),
        )
        for item in config["queries"]:
            self.connection.execute(
                "INSERT INTO queries VALUES (?, ?, ?, ?, ?, ?)",
                (
                    item["id"], item["text"], item.get("language", "und"), item.get("parent_query_id"),
                    item.get("direction"), item.get("depth", 0),
                ),
            )
        for connector in config["connectors"]:
            if not connector.get("enabled", True):
                continue
            self.connection.execute(
                "INSERT INTO connectors VALUES (?, ?, ?)",
                (connector["id"], connector["type"], stable_json(connector.get("options", {}))),
            )
        max_depth = config["limits"]["max_depth"]
        for query in config["queries"]:
            if query.get("depth", 0) > max_depth:
                continue
            for connector in config["connectors"]:
                if not connector.get("enabled", True):
                    continue
                task_key = "task-" + sha256_text(f"{campaign_id}\0{query['id']}\0{connector['id']}")[:24]
                self.connection.execute(
                    "INSERT INTO tasks(task_key, query_id, connector_id, state) VALUES (?, ?, ?, 'pending')",
                    (task_key, query["id"], connector["id"]),
                )
        self.connection.commit()

    def campaign_row(self) -> sqlite3.Row:
        row = self.connection.execute("SELECT * FROM campaigns").fetchone()
        if row is None:
            raise RuntimeError("campaign row is missing")
        return row

    def ready_tasks(self, limit: int, now_epoch: float) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            """
            SELECT t.*, q.query_text, q.language, q.parent_query_id, q.direction, q.depth,
                   c.connector_type, c.options_json
            FROM tasks t
            JOIN queries q USING(query_id)
            JOIN connectors c USING(connector_id)
            WHERE t.state IN ('pending', 'retry') AND t.next_attempt_at <= ?
            ORDER BY q.depth, t.query_id, t.connector_id
            LIMIT ?
            """,
            (now_epoch, limit),
        ).fetchall()
        tasks = [dict(row) for row in rows]
        for task in tasks:
            self.connection.execute(
                "UPDATE tasks SET state='running', attempt_count=attempt_count+1 WHERE task_key=?",
                (task["task_key"],),
            )
            task["attempt_count"] += 1
            task["options"] = json.loads(task.pop("options_json"))
        self.connection.commit()
        return tasks

    def refresh_connectors(self, connector_ids: set[str]) -> int:
        if not connector_ids:
            return 0
        known = {
            row[0] for row in self.connection.execute("SELECT connector_id FROM connectors")
        }
        unknown = connector_ids - known
        if unknown:
            raise ValueError("unknown refresh connector IDs: " + ", ".join(sorted(unknown)))
        placeholders = ",".join("?" for _ in connector_ids)
        cursor = self.connection.execute(
            f"""
            UPDATE tasks SET state='pending', cursor=NULL, page_count=0, result_count=0, attempt_count=0,
                             next_attempt_at=0, last_error=NULL, total_hint=NULL
            WHERE connector_id IN ({placeholders}) AND state NOT IN ('pending', 'retry', 'running')
            """,
            tuple(sorted(connector_ids)),
        )
        self.connection.execute("UPDATE campaigns SET status='partial', updated_at=?", (utc_now(),))
        self.connection.commit()
        return int(cursor.rowcount)

    def record_page(
        self,
        task: dict[str, Any],
        page: DiscoveryPage,
        *,
        started_at: str,
        finished_at: str,
        max_pages: int,
        max_candidates: int,
        retain_content: bool,
    ) -> None:
        page_number = int(task["page_count"]) + 1
        cursor_before = task.get("cursor")
        discovered_at = finished_at
        base_rank = int(task["result_count"])
        stored_count = 0
        candidate_limit_hit = False
        for index, record in enumerate(page.records, start=1):
            if self.candidate_count() >= max_candidates:
                candidate_limit_hit = True
                break
            try:
                self._record_candidate(
                    task,
                    record,
                    source_rank=base_rank + index,
                    page_number=page_number,
                    discovered_at=discovered_at,
                    retain_content=retain_content,
                )
                stored_count += 1
            except (TypeError, ValueError, UnicodeError) as exc:
                self.connection.execute(
                    "INSERT INTO errors(task_key, phase, occurred_at, retry_number, terminal, category, message) VALUES (?, 'normalize', ?, 0, 1, 'record', ?)",
                    (task["task_key"], discovered_at, f"record {index} rejected ({type(exc).__name__})"),
                )
        if candidate_limit_hit:
            state = "limited"
            cursor_after = page.next_cursor
        elif page.next_cursor and page_number < max_pages:
            state = "pending"
            cursor_after = page.next_cursor
        elif page.next_cursor:
            state = "limited"
            cursor_after = page.next_cursor
        else:
            state = "complete"
            cursor_after = None
        self.connection.execute(
            """
            UPDATE tasks SET state=?, cursor=?, page_count=?, result_count=result_count+?, last_error=NULL, total_hint=?
            WHERE task_key=?
            """,
            (state, cursor_after, page_number, stored_count, page.total_hint, task["task_key"]),
        )
        self.connection.execute(
            """
            INSERT INTO query_events(
                task_key, query_id, connector_id, page_number, cursor_before, cursor_after,
                started_at, finished_at, outcome, record_count, response_bytes, total_hint, error
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
            """,
            (
                task["task_key"], task["query_id"], task["connector_id"], page_number,
                cursor_before, cursor_after, started_at, finished_at, state, stored_count,
                page.response_bytes, page.total_hint,
            ),
        )
        self.connection.execute(
            "UPDATE campaigns SET response_bytes=response_bytes+?, updated_at=?",
            (page.response_bytes, finished_at),
        )
        self.connection.commit()

    def _record_candidate(
        self,
        task: dict[str, Any],
        record: DiscoveryRecord,
        *,
        source_rank: int,
        page_number: int,
        discovered_at: str,
        retain_content: bool,
    ) -> None:
        if record.content_scope not in CONTENT_SCOPES:
            raise ValueError(f"invalid content scope: {record.content_scope}")
        identity = identify(record.external_id or f"{task['connector_id']}:{record.source_id}", record.url)
        canonical_key = str(identity["canonical_key"])
        item_id = candidate_id(canonical_key)
        content = record.content
        raw_value = _redact_content_fields(asdict(record))
        if content is not None:
            raw_value["content_present"] = True
            raw_value["content_sha256"] = sha256_text(content)
        raw_json = stable_json(raw_value)
        record_hash = sha256_text(raw_json)
        raw_id = "raw-" + sha256_text(
            f"{task['task_key']}\0{record.source_id}\0{page_number}\0{source_rank}\0{record_hash}"
        )[:32]
        self.connection.execute(
            """
            INSERT OR IGNORE INTO raw_records(
                raw_id, task_key, source_id, source_rank, discovered_at, raw_json, record_sha256, response_page
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (raw_id, task["task_key"], record.source_id, source_rank, discovered_at, raw_json, record_hash, page_number),
        )
        snapshot_path: str | None = None
        if isinstance(content, str):
            content_hash = sha256_text(content)
            hash_scope = "collected_text"
            if retain_content:
                snapshot_path = self._write_snapshot(
                    content,
                    content_hash,
                    record.mime_type or "text/plain",
                    discovered_at,
                    record.acquisition_method,
                    record.retention_scope,
                )
        else:
            content_hash = record_hash
            hash_scope = "discovery_record"
        notes_json = stable_json(record.notes)
        existing = self.connection.execute(
            "SELECT * FROM candidates WHERE canonical_key=?", (canonical_key,)
        ).fetchone()
        values = (
            item_id, canonical_key, identity.get("canonical_url"), identity.get("external_id"),
            record.version or identity.get("version"), identity.get("version_cluster"), record.title,
            record.source_owner, record.language or "und", record.mime_type, record.http_status,
            record.content_scope, record.access_level, content_hash, hash_scope, snapshot_path,
            EXTRACTOR_VERSION, "untrusted_external_content", record.published_at, record.updated_at,
            record.acquisition_method, record.retention_scope, notes_json,
        )
        if existing is None:
            self.connection.execute(
                """
                INSERT INTO candidates(
                    candidate_id, canonical_key, canonical_url, external_id, version, version_cluster,
                    title, source_owner, language, mime_type, http_status, content_scope, access_level,
                    content_sha256, hash_scope, snapshot_path, extractor_version, trust_boundary,
                    published_at, updated_at, acquisition_method, retention_scope, collection_notes_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                values,
            )
        elif CONTENT_PRIORITY[record.content_scope] > CONTENT_PRIORITY.get(existing["content_scope"], -1):
            self.connection.execute(
                """
                UPDATE candidates SET
                    canonical_url=COALESCE(?, canonical_url), external_id=COALESCE(?, external_id),
                    version=COALESCE(?, version), version_cluster=COALESCE(?, version_cluster),
                    title=COALESCE(?, title), source_owner=COALESCE(?, source_owner), language=?,
                    mime_type=COALESCE(?, mime_type), http_status=COALESCE(?, http_status),
                    content_scope=?, access_level=?, content_sha256=?, hash_scope=?,
                    snapshot_path=COALESCE(?, snapshot_path), published_at=COALESCE(?, published_at),
                    updated_at=COALESCE(?, updated_at), acquisition_method=?, retention_scope=?,
                    collection_notes_json=?
                WHERE candidate_id=?
                """,
                (
                    identity.get("canonical_url"), identity.get("external_id"), record.version or identity.get("version"),
                    identity.get("version_cluster"), record.title, record.source_owner, record.language or "und",
                    record.mime_type, record.http_status, record.content_scope, record.access_level, content_hash,
                    hash_scope, snapshot_path, record.published_at, record.updated_at, record.acquisition_method,
                    record.retention_scope, notes_json, existing["candidate_id"],
                ),
            )
            item_id = existing["candidate_id"]
        else:
            item_id = existing["candidate_id"]
        self.connection.execute(
            """
            INSERT OR IGNORE INTO occurrences(
                candidate_id, raw_id, query_id, connector_id, source_rank, discovered_at,
                fetched_at, retry_state, error
            ) VALUES (?, ?, ?, ?, ?, ?, NULL, 'succeeded', NULL)
            """,
            (item_id, raw_id, task["query_id"], task["connector_id"], source_rank, discovered_at),
        )
        if int(task.get("attempt_count", 1)) > 1:
            self.connection.execute(
                "UPDATE occurrences SET retry_state='succeeded_after_retry' WHERE candidate_id=? AND raw_id=?",
                (item_id, raw_id),
            )
        for relation in record.relations:
            if not isinstance(relation, dict):
                continue
            kind, target, source = relation.get("kind"), relation.get("target"), relation.get("source")
            if all(isinstance(value, str) and value for value in (kind, target, source)):
                self.connection.execute(
                    "INSERT OR IGNORE INTO relations VALUES (?, ?, ?, ?)",
                    (item_id, kind, target, source),
                )

    def _write_snapshot(
        self,
        content: str,
        content_hash: str,
        mime_type: str,
        acquired_at: str,
        acquisition_method: str,
        retention_scope: str,
    ) -> str:
        relative = PurePosixPath("snapshots") / f"{content_hash}.txt"
        target = self.root.joinpath(*relative.parts)
        data = content.encode("utf-8")
        existing = _plain_file_or_missing(target, "content snapshot")
        if existing is not None:
            if target.read_bytes() != data:
                raise RuntimeError("snapshot hash collision")
        else:
            _atomic_write_bytes(target, data)
        self.connection.execute(
            "INSERT OR IGNORE INTO snapshots VALUES (?, ?, ?, ?, ?, ?, ?)",
            (content_hash, relative.as_posix(), len(data), mime_type, acquired_at, acquisition_method, retention_scope),
        )
        return relative.as_posix()

    def record_failure(
        self,
        task: dict[str, Any],
        *,
        started_at: str,
        finished_at: str,
        message: str,
        category: str,
        max_retries: int,
        next_attempt_at: float,
    ) -> None:
        terminal = int(task["attempt_count"] > max_retries)
        state = "failed" if terminal else "retry"
        clean_message = " ".join(message.split())[:500]
        self.connection.execute(
            "UPDATE tasks SET state=?, last_error=?, next_attempt_at=? WHERE task_key=?",
            (state, clean_message, next_attempt_at, task["task_key"]),
        )
        self.connection.execute(
            """
            INSERT INTO query_events(
                task_key, query_id, connector_id, page_number, cursor_before, cursor_after,
                started_at, finished_at, outcome, record_count, response_bytes, total_hint, error
            ) VALUES (?, ?, ?, ?, ?, NULL, ?, ?, ?, 0, 0, NULL, ?)
            """,
            (
                task["task_key"], task["query_id"], task["connector_id"], int(task["page_count"]) + 1,
                task.get("cursor"), started_at, finished_at, state, clean_message,
            ),
        )
        self.connection.execute(
            "INSERT INTO errors(task_key, phase, occurred_at, retry_number, terminal, category, message) VALUES (?, 'discovery', ?, ?, ?, ?, ?)",
            (task["task_key"], finished_at, task["attempt_count"], terminal, category, clean_message),
        )
        self.connection.execute("UPDATE campaigns SET updated_at=?", (finished_at,))
        self.connection.commit()

    def mark_open_tasks_limited(self, reason: str) -> None:
        self.connection.execute(
            "UPDATE tasks SET state='limited', last_error=? WHERE state IN ('pending', 'retry', 'running')",
            (reason,),
        )
        self.connection.commit()

    def candidate_count(self) -> int:
        return int(self.connection.execute("SELECT COUNT(*) FROM candidates").fetchone()[0])

    def response_bytes(self) -> int:
        return int(self.campaign_row()["response_bytes"])

    def package_bytes(self, *, include_manifest: bool = True) -> int:
        excluded = set() if include_manifest else {"manifest.json", "manifest.sha256"}
        return sum(
            path.stat().st_size
            for path in self.root.rglob("*")
            if path.is_file()
            and not path.is_symlink()
            and path.relative_to(self.root).as_posix() not in excluded
        )

    def task_counts(self) -> dict[str, int]:
        return {
            row["state"]: row["count"]
            for row in self.connection.execute("SELECT state, COUNT(*) AS count FROM tasks GROUP BY state")
        }

    def retry_wait(self) -> float | None:
        row = self.connection.execute(
            "SELECT MIN(next_attempt_at) AS next_at FROM tasks WHERE state='retry'"
        ).fetchone()
        return float(row["next_at"]) if row and row["next_at"] is not None else None

    def finalize_status(self, max_work_items_reached: bool) -> str:
        counts = self.task_counts()
        active = sum(counts.get(state, 0) for state in ("pending", "retry", "running"))
        if active or max_work_items_reached:
            status = "partial"
        else:
            status = "complete"
        current = self.campaign_row()
        if current["status"] != status:
            self.connection.execute("UPDATE campaigns SET status=?, updated_at=?", (status, utc_now()))
        self.connection.commit()
        return status

    def collection_outcome(self, lifecycle_status: str) -> str:
        """Describe observed collection utility without implying search completeness."""
        if lifecycle_status == "partial":
            return "in_progress"
        counts = self.task_counts()
        candidate_count = self.candidate_count()
        gap_count = counts.get("failed", 0) + counts.get("limited", 0)
        completed_count = counts.get("complete", 0)
        if candidate_count:
            return "candidates_with_gaps" if gap_count else "candidates_observed"
        if completed_count:
            return "no_candidates_with_gaps" if gap_count else "no_candidates_observed"
        if gap_count:
            return "all_tasks_failed_or_limited"
        return "no_tasks_observed"

    def fetch_candidates(self, limit: int) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            """
            SELECT * FROM candidates
            WHERE canonical_url IS NOT NULL AND fetch_status='not_requested'
            ORDER BY candidate_id LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]

    def record_fetch(
        self,
        candidate: dict[str, Any],
        *,
        text: str,
        mime_type: str,
        status: int,
        fetched_at: str,
        retain_content: bool,
        acquisition_method: str,
        retention_scope: str,
        response_bytes: int,
    ) -> None:
        if not isinstance(response_bytes, int) or isinstance(response_bytes, bool) or response_bytes < 0:
            raise ValueError("fetch response_bytes must be a non-negative integer")
        content_hash = sha256_text(text)
        snapshot_path = None
        if retain_content:
            snapshot_path = self._write_snapshot(
                text, content_hash, mime_type, fetched_at, acquisition_method, retention_scope
            )
        self.connection.execute(
            """
            UPDATE candidates SET mime_type=?, http_status=?, content_scope='partial_content',
                access_level='fetched_public_page', content_sha256=?, hash_scope='fetched_extracted_text',
                snapshot_path=COALESCE(?, snapshot_path), extractor_version='stdlib-html-text/1.0',
                fetched_at=?, fetch_status='succeeded', acquisition_method=?, retention_scope=?
            WHERE candidate_id=?
            """,
            (
                mime_type, status, content_hash, snapshot_path, fetched_at, acquisition_method,
                retention_scope, candidate["candidate_id"],
            ),
        )
        self.connection.execute(
            "UPDATE occurrences SET fetched_at=? WHERE candidate_id=?",
            (fetched_at, candidate["candidate_id"]),
        )
        self.connection.execute(
            "UPDATE campaigns SET response_bytes=response_bytes+?, updated_at=?",
            (response_bytes, fetched_at),
        )
        self.connection.commit()

    def record_fetch_failure(self, candidate: dict[str, Any], message: str, category: str) -> None:
        now = utc_now()
        clean = " ".join(message.split())[:500]
        self.connection.execute(
            "UPDATE candidates SET fetch_status='failed', fetched_at=? WHERE candidate_id=?",
            (now, candidate["candidate_id"]),
        )
        self.connection.execute(
            "INSERT INTO errors(task_key, phase, occurred_at, retry_number, terminal, category, message) VALUES (?, 'fetch', ?, 1, 1, ?, ?)",
            ("fetch:" + candidate["candidate_id"], now, category, clean),
        )
        self.connection.commit()

    def export(self, redacted_config: dict[str, Any]) -> dict[str, Any]:
        self.connection.commit()
        campaign = dict(self.campaign_row())
        accepted_response_bytes = int(campaign["response_bytes"])
        max_total_bytes = int(redacted_config["limits"]["max_total_bytes"])
        if accepted_response_bytes > max_total_bytes:
            raise RuntimeError("accepted response bytes exceed the configured campaign limit")
        initial_payload_bytes = self.package_bytes(include_manifest=False)
        package_stop_watermark = int(
            redacted_config["limits"]["package_stop_watermark_bytes"]
        )
        package_observation = {
            "payload_bytes_after_export": initial_payload_bytes,
            "stop_watermark_bytes": package_stop_watermark,
            "stop_watermark_hit": initial_payload_bytes >= package_stop_watermark,
            "measurement_scope": (
                "regular campaign payload files after this export batch; "
                "manifest.json and manifest.sha256 excluded"
            ),
        }
        response_budget = {
            "accepted_bytes": accepted_response_bytes,
            "max_total_bytes": max_total_bytes,
            "remaining_bytes": max_total_bytes - accepted_response_bytes,
            "exhausted": accepted_response_bytes >= max_total_bytes,
        }
        self._write_json(self.root / "campaign-config.redacted.json", redacted_config)
        inventory_path = self.root / "candidate-inventory.jsonl"
        with _atomic_text_writer(inventory_path) as handle:
            for row in self.connection.execute("SELECT * FROM candidates ORDER BY candidate_id"):
                item = dict(row)
                item["collection_notes"] = json.loads(item.pop("collection_notes_json"))
                item["queries"] = [
                    dict(record)
                    for record in self.connection.execute(
                        """
                        SELECT DISTINCT q.query_id AS id, q.query_text AS text, q.language,
                                        q.parent_query_id, q.direction, q.depth
                        FROM occurrences o JOIN queries q USING(query_id)
                        WHERE o.candidate_id=? ORDER BY q.query_id
                        """,
                        (item["candidate_id"],),
                    )
                ]
                item["occurrences"] = [
                    dict(record)
                    for record in self.connection.execute(
                        """
                        SELECT connector_id AS connector, source_rank AS raw_ranking, discovered_at,
                               fetched_at, retry_state, error
                        FROM occurrences WHERE candidate_id=? ORDER BY connector_id, source_rank
                        """,
                        (item["candidate_id"],),
                    )
                ]
                item["relations"] = [
                    dict(record)
                    for record in self.connection.execute(
                        "SELECT kind, target, source FROM relations WHERE candidate_id=? ORDER BY kind, target",
                        (item["candidate_id"],),
                    )
                ]
                item["snapshot_or_reference"] = item.pop("snapshot_path") or item["canonical_url"] or item["external_id"]
                handle.write(stable_json(item) + "\n")
        query_log_path = self.root / "query-log.jsonl"
        with _atomic_text_writer(query_log_path) as handle:
            for row in self.connection.execute(
                """
                SELECT e.*, q.query_text, q.language, c.connector_type
                FROM query_events e
                JOIN queries q USING(query_id)
                JOIN connectors c USING(connector_id)
                ORDER BY e.event_id
                """
            ):
                handle.write(stable_json(dict(row)) + "\n")
        errors = [dict(row) for row in self.connection.execute("SELECT * FROM errors ORDER BY error_id")]
        tasks = [dict(row) for row in self.connection.execute("SELECT * FROM tasks ORDER BY task_key")]
        connector_counts = [
            dict(row)
            for row in self.connection.execute(
                """
                SELECT connector_id, COUNT(DISTINCT candidate_id) AS unique_candidates,
                       COUNT(*) AS occurrences
                FROM occurrences GROUP BY connector_id ORDER BY connector_id
                """
            )
        ]
        query_counts = [
            dict(row)
            for row in self.connection.execute(
                """
                SELECT query_id, COUNT(DISTINCT candidate_id) AS unique_candidates,
                       COUNT(*) AS occurrences
                FROM occurrences GROUP BY query_id ORDER BY query_id
                """
            )
        ]
        collection_outcome = self.collection_outcome(campaign["status"])
        gaps = {
            "schema_version": 1,
            "campaign_id": campaign["campaign_id"],
            "generated_at": campaign["updated_at"],
            "lifecycle_status": campaign["status"],
            "collection_outcome": collection_outcome,
            "coverage": {
                "unique_candidates": self.candidate_count(),
                "response_bytes": self.response_bytes(),
                "response_budget": response_budget,
                "package_observation": package_observation,
                "connector_counts": connector_counts,
                "query_counts": query_counts,
                "task_counts": self.task_counts(),
            },
            "failed_or_limited_tasks": [
                {
                    "task_key": task["task_key"],
                    "query_id": task["query_id"],
                    "connector_id": task["connector_id"],
                    "state": task["state"],
                    "cursor": task["cursor"],
                    "last_error": task["last_error"],
                }
                for task in tasks if task["state"] in {"failed", "limited", "retry", "pending", "running"}
            ],
            "errors": errors,
            "access_gaps": [
                dict(row)
                for row in self.connection.execute(
                    """
                    SELECT candidate_id, canonical_url, content_scope, access_level, fetch_status,
                           CASE
                             WHEN fetch_status='failed' THEN 'fetch_failed'
                             WHEN hash_scope IN ('collected_text', 'fetched_extracted_text') AND snapshot_path IS NULL
                               THEN 'content_not_retained'
                             ELSE 'content_not_reviewed_or_unavailable'
                           END AS gap_reason
                    FROM candidates
                    WHERE content_scope IN ('metadata', 'discovery_snippet') OR fetch_status='failed'
                       OR (hash_scope IN ('collected_text', 'fetched_extracted_text') AND snapshot_path IS NULL)
                    ORDER BY candidate_id
                    """
                )
            ],
            "coverage_claim": "Bounded counts describe only configured sources, queries, pages, limits, and observed failures.",
        }
        self._write_json(self.root / "failure-gaps.json", gaps)
        state = {
            "schema_version": 1,
            "campaign_id": campaign["campaign_id"],
            "config_sha256": campaign["config_hash"],
            "status": campaign["status"],
            "collection_outcome": collection_outcome,
            "created_at": campaign["created_at"],
            "updated_at": campaign["updated_at"],
            "response_bytes": campaign["response_bytes"],
            "response_budget": response_budget,
            "package_observation": package_observation,
            "candidate_count": self.candidate_count(),
            "task_counts": self.task_counts(),
            "tasks": [
                {
                    key: task[key]
                    for key in (
                        "task_key", "query_id", "connector_id", "state", "cursor", "page_count", "result_count",
                        "attempt_count", "last_error", "total_hint",
                    )
                }
                for task in tasks
            ],
        }
        self._write_json(self.root / "campaign-state.json", state)
        for _ in range(8):
            observed = self.package_bytes(include_manifest=False)
            if observed == package_observation["payload_bytes_after_export"]:
                break
            package_observation["payload_bytes_after_export"] = observed
            package_observation["stop_watermark_hit"] = observed >= package_stop_watermark
            self._write_json(self.root / "failure-gaps.json", gaps)
            self._write_json(self.root / "campaign-state.json", state)
        else:
            raise RuntimeError("package byte observation did not stabilize")
        self.connection.commit()
        return state

    @staticmethod
    def _write_json(path: Path, value: Any) -> None:
        _atomic_write_text(
            path,
            json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )


def write_manifest(root: Path, state: dict[str, Any]) -> dict[str, Any]:
    output_names = [
        "campaign-config.redacted.json",
        "campaign.sqlite3",
        "campaign-state.json",
        "candidate-inventory.jsonl",
        "failure-gaps.json",
        "query-log.jsonl",
    ]
    output_names.extend(
        path.relative_to(root).as_posix()
        for path in sorted((root / "snapshots").glob("*.txt"))
    )
    artifacts = []
    for relative in sorted(output_names):
        path = root / relative
        entry = _plain_file_or_missing(path, f"manifest artifact {relative}")
        if entry is None:
            raise ValueError(f"manifest artifact is missing: {relative}")
        artifacts.append(
            {
                "path": relative,
                "bytes": entry.st_size,
                "sha256": sha256_file(path),
                "role": _role(relative),
            }
        )
    manifest = {
        "schema_version": 1,
        "artifact_type": "research_source_campaign",
        "campaign_id": state["campaign_id"],
        "status": state["status"],
        "collection_outcome": state["collection_outcome"],
        "generated_at": state["updated_at"],
        "artifacts": artifacts,
    }
    manifest_path = root / "manifest.json"
    _atomic_write_text(manifest_path, json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    digest = sha256_file(manifest_path)
    _atomic_write_text(
        root / "manifest.sha256", f"{digest}  manifest.json\n", encoding="ascii"
    )
    return manifest


def _role(relative: str) -> str:
    roles = {
        "campaign-config.redacted.json": "redacted_config",
        "campaign.sqlite3": "resume_state",
        "campaign-state.json": "campaign_state",
        "candidate-inventory.jsonl": "candidate_inventory",
        "failure-gaps.json": "failure_gap_report",
        "query-log.jsonl": "query_log",
    }
    return roles.get(relative, "content_snapshot")


def _redact_content_fields(value: Any, key: str | None = None) -> Any:
    """Keep raw provenance without duplicating potentially restricted text."""

    text_keys = {"content", "body", "abstract", "abstracttext", "summary", "description", "snippet"}
    if isinstance(value, dict):
        output: dict[str, Any] = {}
        for child_key, child in value.items():
            if child_key.casefold() in text_keys and isinstance(child, str):
                output[child_key + "_presence"] = {
                    "present": True,
                    "sha256": sha256_text(child),
                    "bytes": len(child.encode("utf-8")),
                }
            else:
                output[child_key] = _redact_content_fields(child, child_key)
        return output
    if isinstance(value, list):
        return [_redact_content_fields(child, key) for child in value]
    return value
