# GPU Measurement Design

Use this reference for GPU kernels, microbenchmarks, training, inference, reliability, and single- or multi-device scaling. Preserve measurement invariants while selecting tools and methods for the workload and available backend.

## Define the measurement object

State whether one observation is a kernel launch, request, batch, training step, fault event, recovery attempt, energy window, or end-to-end run. Keep the finest useful raw grain and give every observation stable run, device, phase, iteration, and sample identifiers.

Link the measurement plan to an `inspect-gpu-environment` attestation or equivalent device/environment evidence. Record code revision, dependency locks, image digest, device selection, compiler and framework identities, and the host/container boundary.

## Establish timing boundaries

Distinguish:

- host wall-clock time, including launch, queueing, synchronization, data movement, and host work as declared;
- device-event time on a named stream or backend queue;
- profiler-derived kernel or range time; and
- end-to-end application latency.

GPU launches and errors may be asynchronous. Declare the synchronization before the start boundary, after the stop boundary, and before accepting success. Preserve asynchronous error checks separately from timing.

Record warm-up iterations and exclude them by an explicit field rather than deleting them. Declare compilation, autotuning, graph capture, kernel cache, allocator cache, data cache, and fusion state. Re-warm after a material shape, code, device, clock, or compilation change.

NVIDIA CUDA event semantics: https://docs.nvidia.com/cuda/cuda-runtime-api/group__CUDART__EVENT.html

AMD HIP event semantics: https://rocm.docs.amd.com/projects/HIP/en/latest/reference/hip_runtime_api/modules/event_management.html

## Control run conditions

Record or control, as relevant:

- repetitions, seeds, input order, shapes, dtypes, and data generation;
- device placement, streams, graph capture, compilation mode, and kernel fusion;
- clock policy, power limit, persistence mode, thermal steady state, and DVFS state;
- memory allocation, cache-reset policy, peak-memory reset, and data residency;
- CPU affinity, NUMA placement, host memory, storage, and input pipeline;
- exclusive or shared tenancy and detected interference;
- multi-device topology, collectives, process placement, and synchronization; and
- profiler or telemetry overhead, with unprofiled controls when it may perturb results.

Treat high-impact clock, power, firmware, driver, MIG, and system changes as separately authorized deployment actions.

## Preserve raw observations

Keep one record per observation or step with, when applicable:

- IDs, timestamp or monotonic index, warm-up flag, seed, device and rank;
- wall and device durations with units and synchronization method;
- work units, declared operation count, bytes moved, batch or token count;
- allocated and reserved memory, peak memory, utilization, power, energy, temperature, and clocks;
- correctness result, error magnitude, injection identity, recovery action, and validator result;
- status namespace: scientific observation, run failure, or measurement contamination;
- missing reason, non-finite marker, exclusion eligibility, and raw source locator.

Retain failed, missing, and non-finite records. Let downstream analysis apply predeclared exclusions while preserving the original denominator.

## Define metrics without conflating them

- latency: distribution at the declared observation boundary;
- throughput: completed work units divided by declared elapsed time;
- effective FLOP/s: declared useful operation count divided by time, distinct from hardware instruction count;
- bandwidth: declared bytes transferred divided by time, with memory level identified;
- memory peak: allocator, framework, or device metric with reset and sampling semantics;
- utilization: tool-specific sampled busy fraction, not a direct efficiency measure;
- power and energy: instantaneous power samples and time-integrated energy with sampling interval;
- speedup: baseline time divided by candidate time on the same workload;
- scaling efficiency: speedup divided by device-count ratio, with strong or weak scaling declared;
- reliability and correctness: event population, denominator, detection, validation, recovery, and residual-error definitions;
- cost: resource time and stated price or allocation model, separated from measured energy.

Keep numerator, denominator, units, direction, aggregation, and confidence procedure with every metric.

## Detect contamination and boundary conditions

Predeclare signals for thermal or power throttling, clock drift, shared-tenant interference, profiler perturbation, compilation during measurement, data-loader starvation, OOM, device errors, disk pressure, and transport interruption. Classify these separately from a valid scientific outcome.

For multiple devices, retain per-rank and per-device records before aggregation. Report load imbalance, communication share, stragglers, topology, and missing ranks. For unsupported backends or unavailable telemetry, record capability gaps and narrow the claim instead of synthesizing measurements.

## Choose tools by capability

Use device events for low-overhead ranges, wall clocks for end-to-end behavior, and profilers or telemetry APIs for attribution. Select NVIDIA Nsight/CUPTI/NVML/DCGM, AMD rocprofiler/ROCm SMI, framework profilers, or other tools only when installed, authorized, and suited to the question. Record tool versions and overhead checks. No one tool is required by this method pack.
