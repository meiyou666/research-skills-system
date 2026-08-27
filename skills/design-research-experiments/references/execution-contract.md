# Execution Contract

Create `execution-contract.json` as the immutable handoff to an execution system. Use `schema_version: 1`.

Use canonical `contract_id`; the validator accepts equivalent `execution_contract_id`. If both
appear, their values must match.

## Required fields

| Field | Meaning |
| --- | --- |
| `contract_id`, `version`, `status` | Stable identity and freeze state |
| `protocol_sha256` | SHA256 of `experiment-protocol.json` |
| `data_contract_sha256` | SHA256 of `data-contract.json` |
| `code_revision` | Immutable source revision or content digest |
| `environment` | Platform requirements, dependency lock artifacts, bootstrap entry point, and validation entry point |
| `run_matrix` | Stable run ID, protocol cell, seed, immutable configuration, and input references for every run |
| `entrypoint` | Argument array, project-relative work directory, allowed environment-variable names, and launcher digest |
| `progress` | Machine-readable progress path, format, update expectation, and stall threshold |
| `completion` | Validator entry point, timeout, and required raw artifacts |
| `runtime_limits` | Per-run maximum, campaign maximum, resource cap, and concurrency cap |
| `recovery` | Checkpoint identity, resumability, idempotency key, and attempt lineage policy |
| `stop_policy` | Scientific, safety, resource, data-quality, and operational stops with authority |
| `result_bundle` | Required layout, manifest algorithm, and secret exclusions |

Use project-relative paths and argument arrays. Keep endpoint, username, credentials, remote absolute paths, and local download destinations in the execution system's operational binding.

## Frozen and bound records

The execution system must retain the frozen contract byte-for-byte. It may create a separate bound execution record containing endpoint-specific paths, uploaded script hashes, environment validation hash, attempt ID, and timestamps. Bindings must reference the frozen contract SHA256 and must not change hypotheses, run cells, seeds, metrics, decisions, or required raw artifacts.

## Recovery semantics

Define whether a run is resumable, which checkpoints are valid, what state is restored, how resumed attempts retain the same scientific run ID, and which operational attempt ID changes. A retry requires a known prior outcome or a stable idempotency key.
