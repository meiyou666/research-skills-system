# GPU Experiment Analysis

Load this reference for GPU kernels, microbenchmarks, training, inference, energy, scaling, and reliability studies. Use the recorded backend capabilities and measurement contract; do not infer unavailable telemetry.

## Kernel and microbenchmark results

Separate warm-up, compilation or autotuning, profiled, and steady-state observations. Analyze device-event and wall-clock durations as different metrics. Report latency distributions and tails, throughput, effective operation rate, bandwidth, memory, and correctness using their declared work and byte counts.

For roofline analysis, state whether operation count and bytes are algorithmic, profiler-observed, or modeled; identify the memory level and measured or vendor-reported ceilings. A roofline point is only comparable within compatible definitions.

Inspect shape, dtype, kernel variant, fusion, graph capture, stream, cache, clock, temperature, power, and profiler strata when recorded.

## Training and inference

Keep per-step or per-request records before run summaries. Separate input/data time, host scheduling, device compute, communication, and synchronization when instrumentation supports them. Report throughput with its batch, sequence, token, or request denominator and retain latency tails.

Analyze memory peaks, OOM attempts, compilation phases, cache state, correctness or quality checks, utilization, power, energy, and cost as separate outcomes. Preserve trajectories and identify regime changes, stalls, spikes, and important cases rather than relying only on run means.

## Multi-device scaling

Retain rank and device identities. Report strong or weak scaling, baseline device count, speedup, scaling efficiency, per-rank work, communication share, imbalance, stragglers, topology, and missing ranks. Do not merge runs with different eligible workloads or quality constraints.

## Reliability and fault injection

Define the event opportunity population and denominator. Preserve injection ID, location hierarchy, bit or corruption class when applicable, time, targeted state, observed propagation, detector result, validator result, recovery action, residual error, and terminal run state.

Separate detection, localization, correction, recovery, false-positive, false-negative, validation, and execution-failure rates. Analyze bad cases and strata by relevant location, timing, magnitude, persistence, workload state, and recovery boundary. Keep injected, naturally observed, and simulated events as different populations.

## Telemetry and contamination

Use timestamp alignment and sampling semantics from the environment or run records. Analyze power, energy, temperature, clocks, utilization, memory, ECC, and throttle indicators only when available and calibrated for the claim. Flag thermal or power throttling, shared tenancy, profiler overhead, clock drift, data starvation, and transport gaps as strata or contamination states.

NVIDIA-tested scripts do not establish AMD equivalence. For AMD or another backend, record detected tools and fields, validate their semantics, and narrow claims to the actually observed capabilities.
