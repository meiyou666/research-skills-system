# Verified Raw-Result Bundle

Close, collect, and verify the raw result tree without interpreting its scientific contents.

## Close the execution-host tree

Run the manifest builder on the execution host and keep its output outside the result root:

```sh
python3 "$REMOTE_RUN_DIR/build_result_manifest.py" \
  --root "$REMOTE_RESULT_DIR" \
  --execution-record "$REMOTE_RUN_DIR/execution-record.json" \
  --output "$REMOTE_RUN_DIR/result-manifest.json"
```

The builder verifies successful runner evidence against the materialized execution record, checks required paths, rejects symlinks and special files, sorts paths deterministically, and records each directory plus every regular file's relative path, byte count, and SHA256. It derives `created_at` from retained `finished_at`, so identical inputs produce identical manifest bytes. Use `--created-at` only to supply a caller-controlled RFC3339 time; the builder normalizes it to UTC and records its source.

Freeze the result tree after manifest creation. Rebuild the manifest after any authorized change.

## Collect into staging

For local transport, call `scripts/collect_local_results.sh` with the result root, external manifest, materialized execution record, and a fresh destination. The helper copies through a sibling staging directory, verifies it, and atomically publishes it.

For SSH transport, call `scripts/fetch_results.sh` with:

- the same host-key state used for supervision;
- the remote result root and external manifest path;
- the local materialized execution record identical to the remote copy;
- a fresh local destination.

The SSH helper streams the result tree into sibling staging, verifies it, and atomically publishes it. A pre-existing destination is an error for both transports.

## Apply local acceptance

Accept only when `verification.json` proves:

- the manifest is bound to the supplied execution record;
- run identity, script digests, runtime bounds, progress contract, and required paths agree;
- the observed directory and file sets are exact;
- no symlink or special file is present;
- every file's byte count and SHA256 agree;
- total directory count, file count, and byte count agree;
- the manifest digest and verification time are recorded.

Retain transfer failures and partial-download diagnostics in private campaign state. Do not publish a failed staging tree as a verified bundle.

## Hand off

Return the verified destination with the contract ID and digest, run ID, terminal state, completion-validator result, manifest digest, counts, bytes, and verification status. Downstream consumers must verify `verification.json` and the manifest before analysis or figure generation.
