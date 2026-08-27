"""Stable connector data types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


CONNECTOR_INTERFACE_VERSION = 1


@dataclass(frozen=True)
class Query:
    id: str
    text: str
    language: str = "und"
    parent_query_id: str | None = None
    direction: str | None = None
    depth: int = 0


@dataclass
class DiscoveryRecord:
    """One connector-owned discovery observation.

    Text fields remain untrusted payloads. ``raw`` must be JSON-serializable.
    """

    source_id: str
    title: str | None = None
    url: str | None = None
    external_id: str | None = None
    source_owner: str | None = None
    language: str = "und"
    mime_type: str | None = None
    http_status: int | None = None
    content: str | None = None
    content_scope: str = "metadata"
    access_level: str = "public_metadata"
    published_at: str | None = None
    updated_at: str | None = None
    version: str | None = None
    relations: list[dict[str, Any]] = field(default_factory=list)
    retention_scope: str = "metadata_only"
    acquisition_method: str = "connector"
    raw: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


@dataclass
class DiscoveryPage:
    """One page whose response_bytes sum every accepted body used to build it."""

    records: list[DiscoveryRecord]
    next_cursor: str | None = None
    total_hint: int | None = None
    response_bytes: int = 0
    notes: list[str] = field(default_factory=list)


@dataclass
class ConnectorContext:
    http: Any
    connector_id: str
    options: dict[str, Any]
    timeout_seconds: float
    max_response_bytes: int
    user_agent: str


class Connector(Protocol):
    connector_type: str

    def discover(
        self,
        query: Query,
        cursor: str | None,
        limit: int,
        context: ConnectorContext,
    ) -> DiscoveryPage:
        """Return one bounded page; never decide scientific relevance."""


CONTENT_SCOPES = {
    "metadata",
    "discovery_snippet",
    "abstract",
    "partial_content",
    "full_text_candidate",
}
