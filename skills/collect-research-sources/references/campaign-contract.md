# Campaign Contract

The package is a resumable collection record, not an evidence verdict. Equivalent external inventories are valid inputs to downstream skills.

## Configuration

`schema_version` is `1`. `campaign_id` is a stable, caller-chosen identifier. Queries have a unique `id`, literal `text`, optional BCP 47-like `language`, and optional `parent_query_id`, `direction`, and non-negative `depth`. These optional fields let an agent record multilingual expansion, citation or repository relations, and contrary queries without forcing a particular strategy.

Each connector has a unique `id`, a registered `type`, an `enabled` boolean, and connector-specific `options`. Options may name a supported `credential_env` or `contact_env`; they must never contain the value. The runner rejects secret-shaped keys, inline contact identities, unsupported credential modes, and URL user information. OpenAlex authentication uses an HTTP authorization header. The baseline PubMed connector stays on the unauthenticated rate tier because NCBI documents its key as a request parameter.

Limits are finite and may be reduced for a small task:

- `concurrency`, `max_pages_per_task`, `max_items_per_page`, and `max_candidates`;
- `max_total_bytes`, `package_stop_watermark_bytes`, `max_response_bytes`, `max_wall_seconds`, and `timeout_seconds`;
- `max_retries`, `backoff_seconds`, and `max_depth`.

## Stable connector interface

Every connector implements:

```python
discover(query, cursor, limit, context) -> DiscoveryPage
```

`DiscoveryPage` contains zero or more `DiscoveryRecord` values, an optional opaque `next_cursor`,
and `response_bytes`, the sum of every accepted body used for that page. A connector returns source
records and relations; it does not decide scientific relevance. Connector exceptions are converted
into task-local failures. Other tasks continue.

`scripts/expand_relations.py` can turn selected citation, author, version, or repository edges into a bounded `relation_query_fragment`. It never fetches the targets. Review the fragment, choose appropriate connectors, and start a new campaign version; this keeps depth, purpose, and cost explicit.

Trusted programmatic hosts may add an implementation with `register_connector(type, factory)` before validating and running a campaign. The factory must return an object with the declared `connector_type` and `discover` method. Do not import plugins from collected pages, repositories, configuration URLs, or other untrusted content. Preserve the record semantics and write hermetic fixtures before enabling online use.

## SQLite state

`campaign.sqlite3` is the authoritative resume state. Schema migrations are monotonic and recorded in `schema_info`. Raw and derived records remain separate:

- `campaigns`: configuration hash, lifecycle status, timestamps, and aggregate limits;
- `tasks`: one query-connector-depth unit, opaque cursor, attempt count, page count, and state;
- `raw_records`: immutable normalized JSON returned by a connector, source rank, timestamps, and record hash;
- `candidates`: canonical identity, URL or external ID, content scope, access level, version cluster, and content hash;
- `occurrences`: many-to-many query/connector/rank provenance;
- `relations`: typed candidate-to-identifier or candidate-to-URL edges;
- `snapshots`: retained byte objects, acquisition method, MIME, size, hash, and retention scope;
- `errors`: bounded retry and terminal failure records.

The runner streams each export into a same-directory temporary regular file and publishes that
file with one rename. It rejects symlinks and special files at the campaign database, snapshot
directory, snapshot, export, and manifest boundaries. SQLite remains the authoritative state if
the process stops between independent export replacements; rerunning reconstructs all exports.
A repeated run with the same configuration resumes idempotently. A changed configuration requires
a new campaign ID or a fresh output directory.

`max_total_bytes` is a strict limit on accepted discovery and generic-fetch response bytes. Before
submitting a concurrent discovery batch, the runner reserves disjoint portions of the remaining
budget; a page whose declared `response_bytes` exceeds its reservation is rejected and contributes
no accepted bytes. Generic fetching shares the same remainder, includes a newly fetched robots
body in its accounting, and stops when no byte remains. Each trusted connector must report all
accepted response bodies in `DiscoveryPage.response_bytes`; the runner also checks the report
against its reservation.

`package_stop_watermark_bytes` is intentionally different. It is a disk-use stop watermark checked
before discovery and fetch work, not a hard quota. SQLite page allocation and one atomic export may
cross it. `campaign-state.json` and `failure-gaps.json` expose `response_budget` and
`package_observation`; the latter records `payload_bytes_after_export`, the configured watermark,
and whether export publication reached it. Both the stop check and measured payload exclude
`manifest.json` and `manifest.sha256` so the observation is stable and non-self-referential. The package validator
recomputes that payload count and checks both exports against the redacted configuration and SQLite.

## Candidate inventory

Each line of `candidate-inventory.jsonl` includes at least:

- `candidate_id`, `canonical_key`, `canonical_url`, `external_id`, and `version_cluster`;
- `title`, `source_owner`, `language`, `mime_type`, and `http_status` when known;
- `content_scope`, `access_level`, `content_sha256`, `hash_scope`, and `snapshot_or_reference`;
- `extractor_version` and `trust_boundary`;
- `queries`: query ID and literal query text;
- `occurrences`: connector, source rank, discovery/fetch timestamps, retry state, and error;
- `relations` and `collection_notes`.

Content scopes distinguish `metadata`, `discovery_snippet`, `abstract`, `partial_content`, and `full_text_candidate`. The last means only that bytes appear complete enough for later review; it is never a verified scientific source state.

## Other exports

- `query-log.jsonl`: exact query, connector, page, cursor lineage, timestamps, and outcome;
- `failure-gaps.json`: connector failures, unavailable content, limit stops, access gaps, and measured coverage counts;
- `campaign-state.json`: resume status and remaining or terminal tasks;
- `campaign-config.redacted.json`: the accepted configuration with credential values excluded;
- `manifest.json`: hashes and byte counts for every durable export and retained snapshot;
- `manifest.sha256`: hash of `manifest.json`.

`status=complete` is a lifecycle fact: every bounded task reached a terminal state and exports match state. It does not mean that any connector returned a candidate, nor that internet or literature coverage is exhaustive. Read `collection_outcome` separately: `candidates_observed`, `candidates_with_gaps`, `no_candidates_observed`, `no_candidates_with_gaps`, `all_tasks_failed_or_limited`, `in_progress`, or `no_tasks_observed`. `partial` remains useful and resumable. `failed` is reserved for campaign-level structural failure, not an individual connector outage.

## Downstream mapping

`search-primary-evidence` may treat each inventory line as a discovery candidate and map `content_scope` to its own access levels. Scientific inclusion, source-type sufficiency, contrary evidence, and stopping decisions remain upstream research judgments. `audit-research-evidence` should review the source-owning artifact and record what was actually read.
