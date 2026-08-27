# Data Contract

Define a machine-readable `data-contract.json` with `schema_version: 1`, a stable canonical
`contract_id`, a positive `version`, `status`, and the upstream protocol lineage. The validator
also accepts equivalent `data_contract_id`; if both fields appear, their values must match.

## Dataset classes

- **Raw observations:** immutable measurements received from the instrument or workload.
- **Events:** timestamped assignments, interventions, transitions, failures, and recovery actions.
- **Run metadata:** configuration, code and environment identity, seeds, clocks, host capabilities, and contract hashes.
- **Derived data:** deterministic transformations with code revision, input hashes, and parameters.

## Field definition

For every field, record:

- stable name and description;
- primitive or structured type;
- unit and scale;
- valid range or enum;
- nullable state and missing-value meaning;
- collection stage and timestamp semantics;
- entity and foreign-key relation;
- raw or derived classification;
- derivation and dependency fields when derived;
- privacy or sensitivity class; and
- validation severity.

## Integrity rules

Require globally stable run IDs and unique observation IDs within a run. Define ordering, clock source, time zone, monotonic-time use, duplicate handling, partial-write detection, schema evolution, and atomic close markers.

Hash every closed file with SHA256. Preserve immutable raw files, transformations, exclusions, and validation reports. Keep credentials, access tokens, and unrelated host data outside the result bundle.

Define required tables, partition layout, serialization, character encoding, compression, maximum record size, and whether non-finite numeric values are valid. Prefer open, documented formats and include the exact schema with the results.
