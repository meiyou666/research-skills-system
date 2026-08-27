# Search Package Contract

Use JSON when a durable or cross-skill handoff is useful. Keep domain-specific extensions under `extensions`.

## Core fields

- `schema_version`: integer `1`;
- `search_id`: stable string;
- `version`: positive integer;
- `status`: `draft` or `frozen`;
- `scope`: object describing the current research object, concepts, and boundaries;
- `cutoff`: search cutoff date when known;
- `entry_points`: services, collections, registries, repositories, or citation routes actually used;
- `queries`: complete query and filter records, or a reference to an external query log;
- `sources`: candidate records;
- `coverage`: covered concepts, access gaps, omitted routes, and stop rationale;
- `extensions`: optional domain-specific content.

`entry_points` and `queries` may be a non-empty text reference, one non-empty provenance object,
or a non-empty list of text references or record objects. This permits an equivalent supplied
inventory or external query log without accepting an opaque truthy scalar. `coverage` is an object
and `coverage.stop_reason` is text when present.

## Candidate record

Give each candidate a stable `id`, primary `locator`, `source_type`, `discovery_route`, `access_level`, `relevance`, `decision`, and textual `decision_reason`. Suggested decisions are `include`, `exclude`, `pending`, and `context_only`. Preserve version relations and correction or retraction status when discovered.

Use access levels `V0` discovery, `V1` abstract, `V2` partial primary content, and `V3` primary methods/results review. The downstream audit decides whether a level is sufficient for a particular claim.

## Freeze semantics

`frozen` means the inventory and coverage statement are fixed for the declared downstream use. It does not mean the field is exhausted. A later update creates a new version and preserves the earlier package.
Before freeze, retain at least one entry-point or supplied-inventory provenance record, the actual
queries or an external query-log reference, and the disposition reason plus discovery route for
each candidate. These are traceability facts, not a required database count or scientific score.
