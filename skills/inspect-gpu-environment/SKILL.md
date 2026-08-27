---
name: inspect-gpu-environment
description: Create and validate a read-only, hash-manifested Linux GPU environment attestation for a local host, SSH target, bare-metal machine, or container. Use when Codex must prove or compare GPU/CPU/NUMA/memory/storage capacity; inspect NVIDIA identity, topology, PCIe, NVLink, MIG, telemetry, drivers, CUDA/runtime/compiler/framework evidence; capability-probe AMD/ROCm without overstating validation; capture optional project revision, dependency-lock hashes, container image digest, device-selection environment, or compute budget; or produce an honest draft or no-GPU attestation before an experiment, benchmark, migration, or remote run.
---

# Inspect GPU Environment

Produce evidence from the target execution view, preserve uncertainty, and leave the machine
unchanged. Use the bundled standard-library scripts instead of assembling ad hoc shell probes.

## Keep the boundary read-only

Run only the collector's fixed inspection commands. Never install or remove drivers, firmware,
kernel modules, runtimes, or system packages. Never change power limits, clocks, performance
levels, MIG/partition configuration, persistence/compute modes, or reset a device.

If inspection suggests a change, list it separately with its target, reason, risk, rollback, and
validation plan. Request explicit authorization for that distinct action. Do not implement it
with this skill. Read
[budgets-and-change-authorization.md](references/budgets-and-change-authorization.md) whenever
cost constraints or a possible host/device change matters.

Do not request or capture credentials. Pass no secrets in labels, image references, or project
paths. The collector records only its literal device-selection environment allowlist, never the
complete environment.

## Choose the shortest sufficient input

Proceed with partial input. All of these are optional:

- requested GPU and CPU counts;
- expected duration and disk capacity;
- hourly and total cost ceilings plus their currency/accounting unit;
- project root and extra lockfile paths;
- container runtime, image reference, and immutable image digest;
- a non-secret target label.

Leave missing facts as `unavailable`. Default to a `draft`; use `complete` only after reviewing
scope and evidence. Do not turn reported input into observed evidence.

## Collect on the target

Require Linux and Python 3.9 or newer. The collector uses only the Python standard library and
invokes commands without a shell. It drains stdout and stderr concurrently, accepts at most
128 KiB from each stream, and runs every probe in a dedicated process group. A timeout or output
overflow makes that probe unavailable and terminates its process group; partial output is not
treated as evidence.

For a minimal local draft, run from the skill directory:

```bash
python3 scripts/inspect_gpu_environment.py \
  --output-dir ./gpu-environment-attestation
```

Add whatever planning context is available:

```bash
python3 scripts/inspect_gpu_environment.py \
  --output-dir ./gpu-environment-attestation \
  --target-label training-node-a \
  --gpu-count 2 \
  --cpu-count 32 \
  --duration-hours 6 \
  --disk-gb 500 \
  --hourly-cost-cap 4.50 \
  --total-cost-cap 30 \
  --currency USD \
  --project-root /work/project \
  --image-digest sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
```

Create a new output directory each time; the collector refuses every existing output entry,
including a regular file, directory, symbolic link, or special file. It stages the three
artifacts and publishes the directory with one rename, then removes temporary staging data on
failure.

For SSH, execute the script on the target rather than inspecting the caller. Streaming needs no
installation because the collector is standalone:

```bash
ssh user@target 'python3 - --output-dir gpu-environment-attestation' \
  < scripts/inspect_gpu_environment.py
scp -r user@target:gpu-environment-attestation ./gpu-environment-attestation
```

Use an appropriate remote absolute output path when the login directory is not durable. Quote
all user-controlled SSH arguments and do not embed credentials. Collection inside a container
attests the container-visible view; it does not prove host package or firmware state.

Pass `--probe-frameworks` only when framework-level accelerator visibility is needed. The
default records installed package versions without importing them. The option imports PyTorch,
TensorFlow, and JAX, when installed, in bounded subprocesses; it stays read-only but may initialize
their accelerator runtimes.

## Validate the bundle

Run the validator beside the collector:

```bash
python3 scripts/validate_attestation.py ./gpu-environment-attestation
```

Require zero errors before using the bundle. Keep warnings: absent GPUs and unavailable hardware
or telemetry are legal evidence gaps. Errors are limited to schema, reference, hash, and evidence
status consistency. The validator accepts only direct regular files as bundle entries; it
rejects a symbolic-link bundle root and symbolic-link, directory, or special-file entries.

Move these files together:

- `attestation.json`
- `manifest.json`, which hashes the attestation bytes
- `manifest.sha256`, which hashes the manifest bytes

The hash chain detects accidental or uncoordinated edits; it is not a signature or trusted
timestamp. Read [attestation-contract.md](references/attestation-contract.md) before building a
consumer, altering the schema, using fixtures, or interpreting validator severity.

## Interpret backend evidence precisely

Treat NVIDIA as the executable baseline. A target status of `tested` means its `nvidia-smi`
identity query executed successfully; it does not promise complete telemetry or workload
compatibility. Read [nvidia.md](references/nvidia.md) when NVIDIA, CUDA, NVLink, PCIe, ECC, or MIG
evidence affects a decision.

Treat AMD/ROCm as capability detection with an explicit real-hardware-unverified boundary. Never
describe the backend as tested merely because `amd-smi`, `rocm-smi`, `rocminfo`, `/dev/kfd`, or a
fixture exists. Read [amd-rocm.md](references/amd-rocm.md) whenever AMD evidence is present or
required.

Accept a clear no-GPU result as a valid attestation. It should report zero visible devices and a
warning, not fail validation. In containers, distinguish visible devices and user-space
toolkits/frameworks from the host driver boundary.

Compare requested budgets with observed capacity explicitly. Do not infer availability,
exclusivity, peer connectivity, performance, or price fit from device count alone. Preserve every
`observed`, `reported`, and `unavailable` wrapper in summaries and downstream manifests.

## Exercise offline scenarios

Replay a fixture without touching live GPU tools:

```bash
python3 scripts/inspect_gpu_environment.py \
  --fixture fixtures/nvidia-2gpu.json \
  --output-dir ./fixture-attestation
python3 scripts/validate_attestation.py ./fixture-attestation
```

Run all hermetic scenarios with:

```bash
python3 scripts/self_test.py
```

The fixtures cover no GPU, two NVIDIA GPUs, missing NVIDIA telemetry, and AMD capability. Fixture
success proves contract/parser behavior only; preserve the backend test boundaries recorded in
the attestation.
