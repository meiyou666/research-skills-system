---
name: supervise-experiment-runs
description: "Supervise a frozen or explicitly specified experiment on a local or SSH-accessible Linux host: inspect and idempotently prepare the environment, bind deployment details, launch and monitor a detached workload, classify operational failures, verify terminal completion, and collect a byte-verified raw result bundle. Use for GPU or CPU kernels, training, inference, simulations, reliability campaigns, benchmarks, and other long runs that need retained supervision across controller disconnection under a verified host persistence policy."
---

# Supervise Experiment Runs

Operate one defined run on a local or SSH transport through a verified raw-result bundle. Use the shortest safe path that preserves the caller's execution intent. Keep research design, scientific analysis, figure production, and report writing in their own skills.

## Establish the boundary

Read [references/boundaries-and-interfaces.md](references/boundaries-and-interfaces.md) before acting. Prefer the high-assurance path when the caller supplies:

- an immutable, portable execution contract with a stable ID and digest;
- a private deployment binding that selects `local` or `ssh` transport and maps logical roles to normalized host paths;
- caller-managed authentication material;
- environment requirements plus bootstrap and validation evidence or artifacts;
- a fresh local campaign-state directory and a fresh result destination.

For a small, explicit run, accept an equivalent launch, completion, artifact, timeout, and recovery specification. Materialize it as a draft execution contract and private binding. Ask for confirmation only when a remaining choice changes permissions, safety, cost bounds, completion meaning, or result identity. Treat other missing metadata as a warning and retain draft status.

Reject contradictory hashes, unsafe authority ambiguity, or a missing launch/completion definition. Do not choose treatments, controls, metrics, sample sizes, thresholds, scientific stopping rules, or result interpretations. Preserve a supplied frozen contract unchanged and record deployment materialization separately.

## Select and verify the transport

Read [references/transport.md](references/transport.md). For `local`, run bounded probes and bundled tools directly in the target Linux environment. For `ssh`, use `scripts/ssh_session.sh` for configuration inspection, probes, shells, commands, and regular-file uploads.

For SSH, bind the supplied host, user, and port directly, pin the first observed host key in campaign state, and require it on later calls. Keep credentials outside commands, logs, contracts, manifests, and bundles. For local runs, record the execution host and user as private deployment evidence and do not treat the controller process lifetime as workload lifetime.

Treat raw connection output and endpoint identity as private campaign state.

## Inspect and prepare the environment

Read [references/environment.md](references/environment.md). Run `scripts/inspect_server.sh` on the execution host before changing it and retain its output privately. Use `inspect-gpu-environment` when GPU capability, topology, host/container boundary, or telemetry matters.

Materialize the frozen environment requirements as an idempotent bootstrap within the authorized mutation scope. Pin sources and versions, retain the bootstrap log and digest, then run a separate non-mutating validation. Reuse an environment only when its source identity and validation evidence still match the deployment binding.

Run `scripts/remote_runner.sh preflight` on the exact target environment before launch.

## Materialize and supervise execution

Read [references/execution-contract.md](references/execution-contract.md).

1. Bind logical work, run-state, result, and progress roles to execution-host absolute paths without changing the portable contract.
2. Place the launch, completion-validator, runner, and manifest-builder artifacts on the execution host and verify them.
3. Verify every declared digest and write the bundle-safe materialized execution record before launch.
4. Start the workload once through `scripts/remote_runner.sh`; keep the workload in the launch script foreground. Verify the host's session-retention policy or select its system service, multiplexer, container supervisor, or scheduler profile before relying on disconnect persistence.
5. When telemetry is needed, read [references/telemetry-sampling.md](references/telemetry-sampling.md). Run the generic sampler independently or let the runner host it through its optional, hash-bound telemetry arguments.
6. Poll with bounded local commands or SSH calls. Track transport observability, runner heartbeat, declared useful progress, sampler heartbeat and availability, disk capacity, and bounded log tails separately.
7. Preserve status and diagnostics before recovery. Resume only through the frozen recovery entry point and only after the prior attempt has a known terminal outcome.

Accept success only when the runner reports `SUCCEEDED`, launch and completion validation exit zero, all required result paths exist, and the result manifest closes successfully.

For GPU and other failure-prone workloads, read [references/failure-classification.md](references/failure-classification.md). Preserve OOM, device errors, ECC, thermal or power throttling, hangs, process exits, storage pressure, transport loss, and validation failure as structured evidence. Use `scripts/classify_run_failure.py` on that evidence; never turn transport unobservability into a workload terminal state.

## Collect and verify raw results

Read [references/result-bundle.md](references/result-bundle.md).

1. Run `scripts/build_result_manifest.py` on the execution-host result root and write its manifest outside that root.
2. Use `scripts/collect_local_results.sh` for a local run or `scripts/fetch_results.sh` with the pinned `known_hosts` file for SSH.
3. Let `scripts/verify_result_manifest.py` reject missing, extra, changed, symlinked, or non-regular content.
4. Publish the staging directory only after every path, byte count, and SHA256 matches.

Report the contract and run IDs, terminal state, completion-validator result, file and byte totals, manifest digest, verification status, and final destination. Make no scientific or analytical claim about the contents.

## Preserve operational invariants

- Keep authentication transient and deployment identity private.
- Keep host mutations inside the approved environment, work, run-state, and result scopes, except explicitly authorized system packages.
- Make bootstrap, upload, launch claiming, recovery, manifest generation, and collection idempotent or keyed by stable identities.
- Never replace or overwrite a run or result destination with an existing identity.
- Preserve partial results and private diagnostics after failure.
- Run `scripts/self_test.py` after changing any bundled script or interface contract.

## Resources

- [references/boundaries-and-interfaces.md](references/boundaries-and-interfaces.md): authoritative inputs, private state, result bundle, and responsibility boundary.
- [references/transport.md](references/transport.md): local and SSH transport, host-key, authentication, and failure handling.
- [references/environment.md](references/environment.md): read-only inspection, idempotent bootstrap, and environment validation.
- [references/execution-contract.md](references/execution-contract.md): portable contract binding, detached runner, monitoring, recovery, and completion gate.
- [references/failure-classification.md](references/failure-classification.md): structured operational failure evidence and classification.
- [references/telemetry-sampling.md](references/telemetry-sampling.md): platform-neutral probe contract, lifecycle, retention, and optional runner integration.
- [references/result-bundle.md](references/result-bundle.md): manifest closure, staged transfer, byte verification, and handoff.
- `scripts/ssh_session.sh`: normalized SSH operations.
- `scripts/inspect_server.sh`: read-only server inventory.
- `scripts/remote_runner.sh`: detached workload supervisor and status interface.
- `scripts/telemetry_sampler.py`: bounded argv-only telemetry lifecycle and JSONL recorder.
- `scripts/build_result_manifest.py`: deterministic result inventory.
- `scripts/collect_local_results.sh`: staged local collection and atomic publication.
- `scripts/fetch_results.sh`: staged transfer and atomic publication.
- `scripts/classify_run_failure.py`: deterministic classification of structured run evidence.
- `scripts/verify_result_manifest.py`: exact local inventory verifier.
- `scripts/self_test.py`: offline interface and workflow tests.
