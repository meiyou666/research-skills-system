# Run Failure Classification

Keep three namespaces separate:

- runner lifecycle state: retained evidence from the detached supervisor;
- operational failure class: one or more observed causes or conditions;
- scientific decision: a downstream interpretation under the experiment protocol.

A failure class does not rewrite the runner state, and a runner failure does not falsify a hypothesis.

## Capture structured evidence

Record timestamps, source, availability, and baseline for each signal:

- process exit and signal, runner heartbeat, progress age, and completion-validator exit;
- allocator, framework, cgroup, and kernel OOM evidence;
- device-reset, device-lost, NVIDIA Xid, AMD RAS, or backend runtime errors;
- corrected and uncorrected ECC counter deltas rather than unqualified totals;
- thermal, power, reliability, and idle throttling reasons plus temperature, power, and clock samples;
- free storage, inode state, quota, and write errors;
- transport probe results and the last retained execution-host state;
- required-artifact and byte-verification failures.

Keep sampler lifecycle separate from each telemetry signal. A live sampler with an `unavailable` probe is not evidence that the quantity was observed; a failed optional probe does not itself fail the workload. Escalate missing telemetry to validation failure only when the frozen contract marks it required.

Read logs only within authorized scope. Preserve bounded raw excerpts in private campaign state and use redacted structured fields in shareable run evidence.

## Apply classes

Use `scripts/classify_run_failure.py` with a JSON evidence object. It can report multiple classes and a deterministic primary class:

- `OUT_OF_MEMORY`;
- `GPU_DEVICE_ERROR`;
- `ECC_UNCORRECTABLE`;
- `THERMAL_THROTTLING`;
- `POWER_THROTTLING`;
- `PROGRESS_STALL`;
- `PROCESS_EXIT`;
- `DISK_EXHAUSTED`;
- `TRANSPORT_UNOBSERVABLE`;
- `VALIDATION_FAILURE`;
- `UNKNOWN`.

Treat throttling as measurement contamination or a boundary condition unless the protocol studies it. Treat a lost SSH connection as an observability condition until retained runner state is read back. Preserve simultaneous conditions; for example, an OOM may accompany a nonzero process exit.

## Recover safely

Before recovery, retain runner status, process identity, progress, telemetry, disk state, log tails, checkpoint identity, and classification. Resume only through the declared recovery entry point after the prior operational attempt has a known state or stable idempotency key. Keep the scientific run ID and assign a new operational attempt ID.
