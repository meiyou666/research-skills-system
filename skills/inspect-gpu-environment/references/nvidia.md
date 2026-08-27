# NVIDIA inspection reference

## Official sources

- [NVIDIA System Management Interface](https://docs.nvidia.com/deploy/nvidia-smi/index.html)
- [NVIDIA MIG user guide](https://docs.nvidia.com/datacenter/tesla/mig-user-guide/getting-started-with-mig.html)
- [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/)
- [CUDA compatibility](https://docs.nvidia.com/deploy/cuda-compatibility/)

## Read-only command baseline

The collector invokes commands without a shell and never passes setting, reset, creation, or
destruction options. Its NVIDIA command set is:

```text
nvidia-smi --query-gpu=... --format=csv,noheader,nounits
nvidia-smi topo -m
nvidia-smi nvlink --status
nvidia-smi -L
nvidia-smi
nvcc --version
nvidia-container-cli --version
```

The identity query has a five-field fallback when a driver rejects a telemetry field. A
successful identity query gives target status `tested`; this means the command executed on the
target, not that every telemetry field was returned or that a workload was run.

The collector also inventories numeric `/dev/nvidia*` device nodes. If nodes are visible but
`nvidia-smi` is absent, it reports `capability-detected-tool-unavailable` and a node-derived count;
it leaves device identity and telemetry unavailable instead of calling the host no-GPU.

## Interpretation

- Treat UUID or PCI bus ID as more stable than enumeration index. Index order can change across
  boots and visibility filters.
- `CUDA Version` in the `nvidia-smi` header is the maximum CUDA version supported by the driver;
  it is not proof that the corresponding toolkit or `libcudart` is installed.
- A present `nvcc` reports a toolkit compiler. Runtime library names from `ldconfig` are separate
  evidence and do not prove loadability inside every process namespace.
- `topo -m` describes the devices visible to NVML and may include CPU/NUMA affinity. NVLink
  absence can be normal for a model or topology.
- MIG mode and `nvidia-smi -L` are observations. They do not prove that a requested profile is
  available or that reconfiguration is safe.
- Power, temperature, utilization, clocks, ECC, PCIe, and memory readings are point-in-time
  telemetry. `N/A` is recorded as `unavailable`, never as zero.

## Container and host boundary

In a GPU container, `nvidia-smi` usually crosses to a host-driver interface while toolkits and
frameworks can come from the image. Record both sides when available. The collector cannot prove
host package versions, firmware, daemon configuration, or image identity unless those facts are
explicitly visible or the operator supplies an immutable image digest.

## Excluded mutations

Enabling/disabling MIG, creating or deleting GPU/compute instances, changing power limits or
application clocks, resetting a GPU, changing persistence/compute modes, and installing or
upgrading drivers/toolkits are separate change operations. The skill only reports them as
possible follow-up actions after explicit authorization; it never runs them.

## Validation boundary

The shipped NVIDIA path is an executable Linux baseline with offline parser fixtures. Hardware,
driver, vGPU, SR-IOV, MIG generation, permission, and container-runtime differences can suppress
fields. Preserve `unavailable` values and warnings instead of inferring success.
