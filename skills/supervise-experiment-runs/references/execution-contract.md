# Execution Contract and Supervision

Treat a supplied portable execution contract as immutable. Materialize deployment paths and operational evidence without changing experimental semantics. For an explicit small run, first convert the equivalent specification into a draft contract with the same operational fields.

## Validate the portable contract

Require these field groups before connecting:

- identity: schema version, contract ID, run ID, freeze time, and content digest;
- provenance: upstream protocol digest, source revision, input and checkpoint digests;
- environment: requirements identity and validation requirements;
- workload: launch artifact, interpreter, arguments, working-role name, and content digest;
- progress: source type, monotonic signal, heartbeat interval, and no-progress deadline;
- limits: maximum runtime, completion-validation timeout, storage bound, and recovery policy;
- completion: validator artifact and digest;
- results: normalized relative required paths with declared file or directory type.

For GPU work, also bind the environment-attestation digest, logical device or rank assignment, expected device count, telemetry capability and sampling contract when relevant, and approved power, clock, temperature, memory, energy, or cost bounds. Treat unavailable optional telemetry as an explicit capability gap; treat a missing safety signal required by the protocol as a blocker.

Reject secret-bearing arguments or environment values. Resolve secret references only through caller-owned runtime facilities. Treat missing descriptive provenance as a warning when launch identity, authority, completion, artifact, and resource bounds remain unambiguous.

## Create a materialized execution record

Bind logical roles to the private deployment, then create a bundle-safe record for the bundled manifest tools. Preserve the portable contract digest in an additional field. The current scripts require at least:

```json
{
  "schema_version": 1,
  "run_id": "stable-run-id",
  "project_revision": "immutable-source-or-content-id",
  "environment_validation_sha256": "64-lowercase-hex",
  "remote_work_dir": "/remote/work",
  "remote_run_dir": "/remote/run-state/stable-run-id",
  "remote_result_dir": "/remote/results/stable-run-id",
  "launch_script_sha256": "64-lowercase-hex",
  "validation_script_sha256": "64-lowercase-hex",
  "required_results": ["records.jsonl", "artifacts/final"],
  "progress_source": "/remote/work/progress.jsonl",
  "heartbeat_seconds": 30,
  "no_progress_seconds": 600,
  "maximum_runtime_seconds": 36000,
  "validation_timeout_seconds": 600,
  "recovery_entry_point": "frozen-recovery-artifact-id",
  "telemetry": {
    "sampler_sha256": "64-lowercase-hex",
    "config_sha256": "64-lowercase-hex",
    "output": "/remote/results/stable-run-id/telemetry.jsonl",
    "required": false
  }
}
```

Use canonical execution-host absolute paths and normalized relative result paths. Omit `telemetry` when sampling is not part of the run. Set `required` only when the completion gate must reject absent or failed telemetry. Schema version 1 retains the `remote_*` field names for compatibility in both transports. Add the portable contract digest, runner digest, manifest-builder digest, and deployment-binding digest when available. Exclude endpoint, account, authentication, secret, and controller-local path fields. Place the record unchanged on the execution host before launch and retain an identical controller copy.

## Launch once

Run `remote_runner.sh preflight`, upload all artifacts, verify their digests, and call:

```sh
remote_runner.sh start \
  --run-id "$RUN_ID" \
  --run-dir "$REMOTE_RUN_DIR" \
  --work-dir "$REMOTE_WORK_DIR" \
  --launch-script "$REMOTE_RUN_DIR/launch.sh" \
  --validation-script "$REMOTE_RUN_DIR/validate.sh" \
  --expected-launch-sha256 "$LAUNCH_SHA256" \
  --expected-validation-sha256 "$VALIDATION_SHA256" \
  --maximum-runtime-seconds "$MAXIMUM_RUNTIME_SECONDS" \
  --validation-timeout-seconds "$VALIDATION_TIMEOUT_SECONDS" \
  --progress-file "$PROGRESS_SOURCE" \
  --no-progress-seconds "$NO_PROGRESS_SECONDS" \
  --heartbeat-seconds "$HEARTBEAT_SECONDS"
```

To let the runner manage generic telemetry, add all five arguments:

```sh
  --telemetry-sampler "$REMOTE_RUN_DIR/telemetry_sampler.py" \
  --telemetry-config "$REMOTE_RUN_DIR/telemetry-config.json" \
  --expected-telemetry-sampler-sha256 "$TELEMETRY_SAMPLER_SHA256" \
  --expected-telemetry-config-sha256 "$TELEMETRY_CONFIG_SHA256" \
  --telemetry-output "$REMOTE_RESULT_DIR/telemetry.jsonl"
```

Read [telemetry-sampling.md](telemetry-sampling.md) for the probe schema and independent lifecycle. Omitting these arguments leaves runner behavior unchanged.

Keep the actual workload in the foreground of `launch.sh`, normally with `exec`. Treat a run directory as immutable after start and use a new run ID for a new attempt. The bundled runner records `STARTING` before launch and starts its worker under `nohup` plus a new `setsid` session. A vanished worker changes an unfinished `STARTING` or `RUNNING` observation to `INTERRUPTED` unless a live workload requires the more specific `ORPHANED` state.

The runner preserves complete workload stdout and stderr in append-only files; it does not rotate
or truncate them. Include their worst-case growth in the contract's storage bound, prefer a
workload-side bounded structured log when output can be verbose, and monitor remaining storage.
Crossing the approved storage reserve is an operational stop, not permission to discard raw
records or silently trim a required result.

Session detachment protects against terminal hangup; it cannot override host policy. An SSH service, container runtime, lease controller, or job cgroup may remove all session descendants after disconnect. Select a host-owned persistence profile—such as a systemd unit, terminal multiplexer, container supervisor, or batch scheduler—when the host documents that requirement, and retain its job identity in private deployment state. The bundled tests exercise local Linux detachment. Persistence across an actual SSH disconnect remains an execution-host validation step; do not claim it from the offline test alone.

## Monitor retained state

Poll `remote_runner.sh status --run-dir ...` through bounded local commands or SSH calls. Track separate signals:

- supervisor heartbeat proves control-plane observability;
- the frozen progress signal proves useful work.
- sampler heartbeat and per-probe outcomes prove only the telemetry actually observed.

Retain compact observations: UTC time, runner state, heartbeat age, progress identity, result count, available storage, and bounded log tails. Interpret transient `STARTING`, active `RUNNING`, and terminal `SUCCEEDED`, `FAILED`, `INTERRUPTED`, `ORPHANED`, `STALLED`, or `TIMED_OUT` as execution evidence. Use `UNOBSERVABLE` only as the monitoring client's current condition, not an execution terminal state.

## Recover and close

Read retained state before recovery. Continue monitoring a live run. For a terminal failed attempt, preserve its logs and state, validate the frozen checkpoint, and create a traceable new attempt through the declared recovery entry point. Retry only operations whose prior outcome is known or whose idempotency key is stable.

Close success only when runner state is `SUCCEEDED`, launch and completion-validator exit codes are zero, all required paths are readable, terminal metadata and logs are flushed, and a result manifest can inventory the result root. Let the contract's completion validator remain authoritative for domain completeness.
