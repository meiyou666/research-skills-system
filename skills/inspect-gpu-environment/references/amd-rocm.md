# AMD and ROCm capability reference

## Official sources

- [AMD SMI documentation](https://rocm.docs.amd.com/projects/amdsmi/en/latest/)
- [AMD SMI CLI usage](https://rocm.docs.amd.com/projects/amdsmi/en/latest/how-to/amdsmi-cli-tool.html)
- [rocminfo documentation](https://rocm.docs.amd.com/projects/rocminfo/en/latest/)
- [ROCm system requirements](https://rocm.docs.amd.com/projects/install-on-linux/en/latest/reference/system-requirements.html)
- [Legacy ROCm SMI CLI documentation](https://rocm.docs.amd.com/projects/rocm_smi_lib/en/latest/)

AMD documents AMD SMI as the successor to the legacy ROCm SMI tooling. Command syntax and JSON
shape can differ across installed releases, so the collector retains bounded command output and
only infers a device count from simple known list shapes.

## Capability probes

The collector checks command availability for `amd-smi`, `rocm-smi`, `rocminfo`, `hipcc`, and
`hipconfig`, plus `/dev/kfd`, `/dev/dri/renderD*`, and the `amdgpu` kernel-module path. A generic
render node alone does not identify AMD hardware; detection requires an AMD/ROCm command,
`/dev/kfd`, or the `amdgpu` module. When
available, it may execute this read-only subset:

```text
amd-smi version
amd-smi list --json
amd-smi static --json
amd-smi metric --json
rocminfo
rocm-smi --json --showproductname --showbus --showmeminfo vram \
  --showuse --showtemp --showpower --showclocks
hipcc --version
hipconfig --version
```

If `amd-smi` is absent, the legacy `rocm-smi` command supplies a combined inventory/telemetry
record. `rocminfo` independently indicates whether a working ROCm stack can enumerate agents.
A device node alone proves visibility of that node, not a working ROCm user-space stack.

## Interpretation boundary

Any detected AMD path uses target status `capability-detected-unverified`. The implementation
status remains `capability-path-fixture-tested; real-hardware-unverified`. The included AMD
fixture verifies offline routing, status, hashing, and generic JSON retention only. It does not
claim real MI-series/Radeon hardware validation, parser completeness, telemetry units, topology,
XGMI, partitioning, RAS/ECC behavior, SR-IOV, permissions, or container passthrough.

Do not silently map vendor-version-specific AMD fields into NVIDIA semantics. Report available
AMD output, command availability, nodes, compiler/runtime evidence, and the unverified boundary.
For a decision that depends on exact AMD metrics, read the installed CLI's `--help`, compare its
version with current official documentation, and arrange a separately documented hardware test.

## Excluded mutations

Do not invoke `amd-smi set`, reset, partition, firmware, power, clock, fan, performance-level, or
other control operations. Driver/ROCm installation or upgrade is also outside this skill. Present
such changes only as separately authorized follow-up work.
