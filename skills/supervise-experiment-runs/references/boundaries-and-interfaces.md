# Boundaries and Interfaces

Use four distinct artifact classes. Preserve their trust and disclosure boundaries throughout the campaign. Scale documentation to operational risk.

## Portable execution contract

Use an immutable contract produced after experimental design is complete for long, costly, multi-attempt, or high-assurance work. Bind its stable contract ID, schema version, content digest, run ID, source and input identities, workload artifact digests, progress and timeout rules, completion validator, required raw outputs, recovery entry point, and resource bounds.

Keep the contract platform-neutral. Express work, run-state, result, checkpoint, and progress locations as logical roles. Exclude hostnames, account names, authentication data, secret-bearing environment variables, and controller-local paths.

For a small task whose command and acceptance conditions are already explicit, accept an equivalent specification containing the launch artifact or command, working-role name, progress or liveness signal, runtime limit, completion check, required artifacts, result identity, and recovery behavior. Materialize a draft contract before mutation. Confirm only unresolved choices that materially change authority, safety, cost, completion meaning, or result identity.

Classify structural errors, digest mismatches, ambiguous authority, invalid state transitions, and failed completion as hard failures. Classify absent descriptive metadata and non-critical provenance as warnings while retaining draft status.

## Private deployment binding

Bind the portable roles to one observed deployment:

- transport mode (`local` or `ssh`) and, for SSH, host, user, and port;
- campaign `known_hosts` location and authentication handle;
- normalized execution-host work, run-state, result, checkpoint, cache, and progress paths;
- selected storage and effective compute limits;
- environment bootstrap and validation artifact locations;
- local campaign-state and result staging locations.

Keep this binding caller-owned and private. Hash it for audit, but do not copy it wholesale into a raw-result bundle. Derive a bundle-safe materialized execution record containing only the fields needed to prove execution and result integrity.

## Private campaign state

Retain operational evidence outside the verified raw-result bundle:

```text
campaign-state/
  connection/known_hosts
  connection/attempts.jsonl
  server-inspection.txt
  environment/bootstrap.log
  environment/validation.log
  runs/<run-id>/observations.jsonl
  runs/<run-id>/log-tails/
  transfer/
```

Treat endpoint and account identifiers, host keys, process IDs, device identifiers, mounts, absolute deployment paths, environment inspection, and workload logs as sensitive operational data. Redact retained connection summaries. Never retain password values or private-key contents.

## Verified raw-result bundle

Publish only after local byte verification succeeds:

```text
result-bundle/
  raw/
  execution-record.json
  result-manifest.json
  verification.json
```

The execution record must bind the portable contract digest, run identity, source identity, environment-validation digest, workload and validator digests, declared progress and timeout rules, required result paths, and bundle-safe execution-host role bindings. It must contain no endpoint, account, credential, secret, or controller-local path.

The bundle proves provenance, terminal completion, membership, size, and byte integrity. It does not certify a scientific conclusion, statistical interpretation, figure, or report.

## Responsibility handoffs

Receive a frozen contract or equivalent explicit execution specification. Return the verified raw-result bundle to `analyze-experiment-results` or another authorized consumer. Route requests that change hypotheses, arms, controls, variables, metrics, sampling, statistical rules, or scientific stopping criteria back to the design owner and require a newly frozen contract.
