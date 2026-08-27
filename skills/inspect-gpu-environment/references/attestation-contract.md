# Capability and attestation contract

## Contents

- Scope and trust model
- Evidence records
- Bundle and hash chain
- Required coverage
- Backend status contract
- Fixture injection
- Validator severity contract
- Tested boundaries

## Scope and trust model

The collector describes the Linux execution view in which it runs. On bare metal that is the
host view. In a container it is the container-visible view: GPU device exposure and the host
driver interface may be observable, while host packages, firmware, service configuration, and
some topology can remain outside the namespace. An attestation is evidence, not a benchmark,
health certificate, compatibility guarantee, or proof that a planned workload will fit.

Local and SSH collection use the same rule: run the script on the target. A command-output
fixture is synthetic evidence and sets `metadata.collection_mode` to `fixture`; never present it
as evidence from a real host.

No GPU is a valid result. `gpu.summary.value == "no-visible-gpu-detected"` and visible count zero
must validate with a warning, not an error.

## Evidence records

Every collected, operator-supplied, or unavailable datum uses an evidence record:

```json
{
  "evidence": true,
  "status": "observed | reported | unavailable",
  "value": "JSON value or null",
  "source": "present for observed/reported",
  "reason": "present for unavailable",
  "source_ref": "optional reference id",
  "unit": "optional unit"
}
```

- `observed`: read from a command, a selected file/path, or a deterministic derivation whose
  source names its inputs. The value must be non-null.
- `reported`: supplied by the operator or declared by the skill contract. The value must be
  non-null; it is not upgraded to observed merely because it is plausible.
- `unavailable`: not supplied, not visible, unsupported, failed, or intentionally not probed.
  The value must be null and `reason` must explain why.

Metadata in `schema`, `references`, and generated warning records is contract metadata rather
than evidence. The `evidence: true` marker prevents vendor JSON fields named `status` from being
misread as contract evidence. A consumer must preserve statuses instead of flattening values.

## Bundle and hash chain

The output directory contains:

- `attestation.json`: schema `gpu-environment-attestation/1.0.0`.
- `manifest.json`: one artifact record with the attestation byte length and SHA-256.
- `manifest.sha256`: SHA-256 of the exact `manifest.json` bytes.

The manifest does not sign identity or establish provenance. Move all three files together. Use
a separate signing system if cryptographic identity, non-repudiation, or a trusted timestamp is
required.

`validate_attestation.py` checks both hash links. Reformatting `attestation.json` changes its
hash and requires intentional regeneration of the manifest.

The collector requires an absent output path, stages direct regular files, and publishes the
directory with one rename. It does not follow an existing output symlink or overwrite an existing
regular, directory, or special-file entry. The validator rejects a symlink supplied as the bundle
root and rejects symlink, directory, or special-file entries inside a bundle. It reads at most
8 MiB for `attestation.json`, 512 KiB for `manifest.json`, and 1 KiB for `manifest.sha256` before
reporting an error.

## Required coverage

The top-level sections are:

- `metadata`, `scope`, and `budget`
- `container`
- `gpu.nvidia` and `gpu.amd_rocm`
- `host` and `software`
- `project` and `device_selection_environment`
- `change_control`, `references`, and `warnings`

NVIDIA device records cover identity, PCI bus, driver, memory, utilization, temperature, power,
clocks, ECC, MIG mode, and PCIe link state. Backend-level evidence covers topology, NVLink, MIG
instances, and the maximum CUDA version reported by the driver.

AMD capability evidence covers CLI availability, `/dev/kfd`, render nodes, AMD SMI or legacy
ROCm SMI output when available, `rocminfo`, and HIP compiler/configuration command availability.
Its structured output remains backend-version-dependent and hardware-unverified.

Host evidence covers kernel, selected OS identifiers, CPU topology, NUMA, memory, cgroup limits,
and storage capacity. Software evidence covers kernel modules, selected runtime libraries,
compilers, container CLI, framework package versions, and optional isolated framework imports.

Project evidence is optional. Automatic lockfile discovery is deliberately limited to common
root-level files plus `requirements*.txt`; pass repeatable `--lock-file` paths for other files.
Only files resolving within the project root are hashed. Git dirty state excludes untracked file
names.

Only the literal names in `device_selection_environment.allowlist` can be captured. The
collector never serializes the complete process environment.

## Backend status contract

NVIDIA target statuses:

- `tested`: the target's `nvidia-smi` identity query completed; individual telemetry may still
  be unavailable.
- `probe-failed`: `nvidia-smi` was found but both full and basic identity queries failed.
- `capability-detected-tool-unavailable`: numeric NVIDIA device nodes are visible but
  `nvidia-smi` is absent, so model and telemetry identity remain unavailable.
- `not-detected`: neither `nvidia-smi` nor a numeric NVIDIA device node was found in the
  execution view.

The NVIDIA implementation status is `executable-baseline-fixture-tested`. This states exactly
that the command/parsing path is exercised by offline fixtures; it does not claim validation on
every driver, GPU, hypervisor, or container runtime.

AMD/ROCm target statuses:

- `capability-detected-unverified`: a management/enumeration command or device node was found.
- `not-detected`: no supported command or device node was found.

The AMD implementation status is
`capability-path-fixture-tested; real-hardware-unverified`. Do not rename this to “tested” after
merely replaying fixtures. Establish and document a separate real-hardware test before changing
that boundary.

## Fixture injection

`--fixture FILE` accepts schema `gpu-environment-command-fixture/1.0`. The fixture may contain:

```json
{
  "fixture_schema": "gpu-environment-command-fixture/1.0",
  "metadata": {"name": "scenario-name"},
  "which": {"nvidia-smi": "/usr/bin/nvidia-smi"},
  "commands": {"nvidia_smi_query_full": {"returncode": 0, "stdout": "..."}},
  "files": {"/proc/meminfo": "..."},
  "paths": {"/dev/kfd": true},
  "globs": {"/dev/dri/renderD*": ["/dev/dri/renderD128"]},
  "environment": {"CUDA_VISIBLE_DEVICES": "0"},
  "packages": {"torch": "2.5.1"}
}
```

An unrecorded fixture command returns synthetic code 127; it never falls through to the live
host. This makes offline tests hermetic. Live and fixture commands permit at most 128 KiB on each
of stdout and stderr. The live runner drains both streams concurrently without a shell and gives
each probe its own process group. Timeout or stream overflow terminates that group, discards
partial output, and records the probe as unavailable. Selected host-file reads use the same
128 KiB default byte bound and become unavailable rather than returning a truncated value.

## Validator severity contract

Only these families are errors:

- `schema.*`: wrong/missing document structure or unreadable JSON.
- `reference.*`: missing, unknown, altered, or unresolved reference metadata.
- `hash.*`: missing or inconsistent manifest/hash artifacts.
- `status.*`: malformed evidence or mutually inconsistent backend/safety statuses.

Missing GPUs, topology, telemetry, or host capacity are `WARNING` and do not change the zero exit
status. This distinction permits honest partial and no-GPU attestations while rejecting claims
whose structure or integrity is inconsistent.

## Tested boundaries

`self_test.py` runs entirely offline and covers no GPU, two NVIDIA GPUs, missing NVIDIA telemetry,
and one AMD capability fixture. It also verifies simultaneous stdout/stderr drainage, per-stream
overflow failure, process-group timeout cleanup, bounded host-file reads, streamed execution,
output-path guards, bundle symlink rejection, environment allowlisting, bundle tamper detection,
status inconsistency detection, and staging cleanup. These tests validate the collector contract
and parsers against fixtures. They are not substitute evidence for AMD hardware, all NVIDIA
generations, vendor CLI changes, privileged topology, SR-IOV, vGPU, or every container boundary.
