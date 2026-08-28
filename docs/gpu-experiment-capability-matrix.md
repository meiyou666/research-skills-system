# GPU Experiment Capability Matrix

Verified through 2026-08-28. This document describes composable capabilities, not a mandatory workflow. Start with the skill whose reliable inputs are already available and skip, repeat, or replace other capabilities as the question requires.

## Verification labels

| Label | Meaning |
| --- | --- |
| `live-no-gpu` | The code ran in a Linux environment with no visible physical accelerator and represented that state without inventing device facts. |
| `offline-fixture` | Deterministic fixtures exercised parser, state, integrity, or rendering behavior without accelerator hardware. |
| `offline-execution` | A real bundled script ran locally against temporary processes and files, but not against an external GPU server. |
| `backend-neutral` | The contract does not require a GPU vendor or framework; actual support follows the supplied workload and installed tools. |
| `hardware-unverified` | The repository has no direct execution evidence for that hardware/backend behavior. |

The validation environment exposed no NVIDIA or AMD GPU. NVIDIA CLI parsing and two-device behavior are fixture-tested; AMD/ROCm is capability-detection only and explicitly real-hardware-unverified. No result below turns documentation support into hardware validation.

## Capability ownership

| Capability | Owning skill | Minimum useful input | Output and completion boundary | Runtime dependencies | Backend and test status |
| --- | --- | --- | --- | --- | --- |
| GPU research-source collection | `collect-research-sources`; `search-primary-evidence` owns scientific screening | Topic, seed URL/repository, or a partial query plan | Resumable candidate inventory with query/connector provenance, canonical IDs, version clusters, content hashes, snapshots or external references, lifecycle/outcome separation, and failure/access gaps; search saturation is decided separately | Python standard library; optional `gh`, RSSHub-produced feed, or caller-operated SearXNG | Offline forward tests covered 606 mixed-language candidates, resume, simulated `gh` repository/code/issue/PR/commit/release paths, loopback Atom refresh, partial content, failure isolation, and tamper detection. On 2026-08-28, checksum-verified `gh` returned three GPU-code repository candidates, a pinned RSSHub test feed reached its configured five-candidate limit and reported `candidates_with_gaps`, and a pinned SearXNG connector completed with zero candidates while service logs showed upstream-engine failures that the campaign did not retain; Crossref/OpenAlex online attempts on 2026-08-27 ended in recorded transport failures; no claim of exhaustive coverage |
| Resource, duration, disk, and cost framing | `inspect-gpu-environment`; `design-research-experiments` for study allocation | Any available budget or resource limit | Reported planning values remain distinct from observed capacity; missing values remain available for later completion | Python standard library | `live-no-gpu`, `offline-fixture`; provider pricing remains caller-supplied |
| Host/container environment proof | `inspect-gpu-environment` | Access to the target Linux execution view | `attestation.json`, `manifest.json`, and `manifest.sha256`; schema, references, status consistency, and both hash links validate | Linux, Python 3.9+; vendor CLIs are optional | NVIDIA `offline-fixture`; AMD capability `offline-fixture` and `hardware-unverified`; no-GPU `live-no-gpu` |
| GPU identity and topology | `inspect-gpu-environment` | Target view or command fixture | Visible physical/logical devices, UUID/BDF, PCIe, topology, NVLink, MIG/partition evidence, plus explicit unavailable states | Installed `nvidia-smi`, `amd-smi`/legacy tools, or equivalent fixture | Two-device NVIDIA `offline-fixture`; AMD capability `offline-fixture`; physical topology `hardware-unverified` |
| CPU, NUMA, memory, storage, software, and provenance | `inspect-gpu-environment` | Target view; optional project root, lockfiles, image identity | CPU/NUMA/memory/storage evidence; driver/runtime/compiler/framework availability; Git revision, lock hashes, image digest, and device-selection allowlist when supplied | Standard Linux interfaces and available read-only CLIs | `live-no-gpu`, `offline-fixture`; container-visible evidence is not promoted to host evidence |
| GPU measurement design | `design-research-experiments` | Question, hypothesis, or equivalent benchmark intent | A compact protocol or frozen data/execution contracts defining observation grain, timing/synchronization, warm-up, repetitions, metrics, statuses, stops, and required raw artifacts | No fixed framework or profiler | `backend-neutral`; validator self-test; CUDA/HIP semantics are method references, not hardware tests |
| Local or SSH run supervision | `supervise-experiment-runs` | Frozen execution contract or an equivalent explicit launch/completion/artifact specification plus a private transport binding | Detached run with retained lifecycle evidence; success requires runner, launch, completion validator, required paths, and manifest closure | Linux, Bash, Python 3.10+, core utilities; OpenSSH only for `ssh` | `offline-execution` for local runner, recovery states, integrity collection, and SSH interface tests; external GPU SSH host `hardware-unverified` |
| Business progress versus control-plane liveness | `supervise-experiment-runs` | Progress source and heartbeat/stall bounds | Independent runner heartbeat, useful-progress identity, bounded observations, and terminal state | Bundled `remote_runner.sh` | `offline-execution`; workload-specific progress semantics come from the execution contract |
| Runtime telemetry retention | `design-research-experiments` defines the sampling contract; `supervise-experiment-runs` executes the approved collector | Approved telemetry command/artifact, cadence, clock, device/rank identity, and missing-sample policy | Timestamped raw telemetry with tool identity, availability gaps, and sampling boundary in the result set or private diagnostics | Any authorized backend telemetry tool; none is mandatory | Contract path is `backend-neutral`; NVIDIA/AMD live telemetry collection is `hardware-unverified` |
| Operational failure classification | `supervise-experiment-runs` | Structured runner, transport, storage, validation, and available telemetry evidence | Deterministic primary and concurrent classes for OOM, device error, uncorrectable ECC, thermal/power throttle, stall, process exit, disk exhaustion, transport unobservability, and validation failure | Python standard library | `offline-execution`; classifier keeps runner state and scientific interpretation separate |
| Byte-verified raw result bundle | `supervise-experiment-runs` | Closed result tree plus bundle-safe execution record | Exact regular-file membership, sizes, SHA-256 values, verification record, and atomic local publication | Python, Bash, `tar`, SHA-256 utilities; OpenSSH for remote transfer | Local collect and tamper rejection `offline-execution`; SSH transfer protocol tested offline |
| Fine-grained result analysis | `analyze-experiment-results` | Verified raw bundle or equivalent measurements with traceable identities | Derived observation/summary/bad-case tables, metric dictionary, statistics, bounded findings, and hashed analysis manifest | Python 3 standard library for the baseline script; domain tools may replace it | GPU-like kernel/training/reliability data `offline-fixture`; methods are `backend-neutral` |
| Publication figures and GPU recipes | `create-publication-figures` | Machine-readable data plus a minimal figure specification | Deterministic PDF, SVG, print-resolution PNG, manifest, captions/alt text, and mechanical QA; scientific/visual review remains explicit | Python 3.10+, Matplotlib, NumPy, Pillow | Line/scatter/bar/hist/ECDF/heatmap and GPU recipes `offline-execution`; four venue profiles tested mechanically |
| Report integration and release | `revise-evidence-report`; `no-negative-echo` as horizontal gate | Existing evidence-backed report and available analysis/figure artifacts | Revised Markdown, self-contained HTML, PDF, render manifest, evidence/visual QA, and inspected release surfaces | Python 3.10+, Pandoc, selected PDF engine | Renderer offline self-test plus real Pandoc/PDF-engine smoke; scientific review remains contextual |

## Scenario coverage

| Scenario | Preparation and execution | Required raw grain | Analysis support | Figure support | Current verification boundary |
| --- | --- | --- | --- | --- | --- |
| Kernel or microbenchmark | Device/wall timing boundary, warm-up, cache/compile/fusion state, work and byte counts, correctness oracle, optional profiler plan | One row per launch/sample with phase, stream/device, status, duration, work, bytes, and correctness | Latency tails, throughput, effective operation rate, bandwidth, roofline inputs, bad cases | ECDF/histogram, throughput, roofline, telemetry, bad-case context | Synthetic GPU-like measurements and rendering; no physical kernel launch |
| Training | Step/batch observation, seed, data/compute/communication boundary, checkpoint and recovery semantics, optional multi-rank telemetry | One row per step/rank/device plus failed, missing, warm-up, compilation, and validation states | Trajectories, regime changes, throughput, memory, energy/cost, strata, sensitivity, failed attempts | Per-step line, resource traces, distributions, scaling, bad-case context | Synthetic step data and detached local runner; no framework/GPU training run |
| Inference | Request/batch concurrency, synchronization and end-to-end boundary, timeout/censor policy, correctness or quality check | One row per request/batch with latency, completed work, timeout/failure status, device/rank, and context | Latency distribution/tails, throughput, memory/energy/cost, long-tail and subgroup analysis | ECDF/histogram, throughput, resource traces, bad cases | Synthetic request-shaped data; no framework/GPU inference run |
| Reliability or fault injection | Event-opportunity population, injection authority, location/time, detector/validator/recovery, operational stops | One row per injection or observed event, including non-events, execution failures, pollution, residual error, and recovery outcome | Detection/localization/correction/recovery rates, false outcomes, error strata, influential failures | Error position/bit/layer heatmap, failure distributions, bad-case context | Synthetic failure and contamination fixtures; no physical fault injection |
| Single GPU | Stable device identity and visible-device selection | Preserve device ID even when only one device is present | Device-specific context and no assumed generalization | All relevant single-device recipes | Contract and fixture coverage; physical execution `hardware-unverified` |
| Multiple GPUs | Physical/logical device and rank map, topology, collective/process placement, strong/weak scaling definition | Per-rank/per-device rows before aggregation, including missing ranks and stragglers | Speedup, scaling efficiency, imbalance, communication share, topology strata | Scaling curves, per-rank/resource traces, distributions | Two-device NVIDIA environment fixture and synthetic analysis; physical collectives `hardware-unverified` |
| Local Linux | Private local binding and fresh campaign/result locations | Same bundle contract as SSH | Transport-independent | Transport-independent | Detached runner and atomic collection `offline-execution` |
| SSH Linux | Caller-owned authentication, pinned campaign host key, normalized remote roles | Same bundle contract as local | Transport-independent | Transport-independent | Interface and failure handling tested offline; no external server in verification environment |
| Bare metal | Target-side inspection and explicit mutation authority | Record host evidence directly | Preserve observed hardware context | Transport-independent | Collector path exercised on Linux; no GPU bare-metal host |
| Container | Image reference/digest, runtime flags, mounts, visible-device-to-host mapping, and separate host evidence when accessible | Preserve host/container context and unavailable host facts | Do not infer host equivalence from image digest | Transport-independent | Namespace/boundary logic and fixtures; no live GPU container |

## Backend support

| Backend | Environment inspection | Measurement/execution | Analysis and figures | Tested boundary |
| --- | --- | --- | --- | --- |
| NVIDIA | Structured `nvidia-smi` identity, topology, NVLink, MIG, PCIe and telemetry paths with per-field availability | Any approved CUDA, framework, profiler, or standalone workload; no bundled CUDA dependency | Vendor-neutral metric contracts plus NVIDIA-aware context | Parser and two-device/missing-telemetry fixtures; no physical NVIDIA GPU |
| AMD/ROCm | `amd-smi`, legacy `rocm-smi`, `rocminfo`, device-node and HIP/compiler capability detection | Any approved HIP, framework, profiler, or standalone workload; capability must be proven on target | Vendor-neutral metric contracts with original AMD field semantics retained | Capability fixture only; real hardware and profiler behavior `hardware-unverified` |
| Other accelerators | Generic Linux/CPU/storage/software evidence; no bundled vendor parser | Explicit workload and telemetry commands can use the common execution contract | Generic status, metric, analysis, and figure contracts | Interface-only; vendor-specific inspection and hardware behavior `hardware-unverified` |
| CPU-only/no GPU | Full host/software inspection with a valid zero-visible-device result | GPU-independent workloads use the same runner and bundle tools | General analysis, figures, and reports remain usable | `live-no-gpu` and offline runner tests |

No framework, model, GPU vendor, profiler, cloud, scheduler, or statistics package is a core requirement. Optional framework imports are isolated and opt-in during environment inspection because they may initialize an accelerator runtime.

## Useful compositions

These are starting points, not state transitions:

- For a new kernel benchmark, combine `inspect-gpu-environment`, the GPU method reference in `design-research-experiments`, `supervise-experiment-runs`, `analyze-experiment-results`, and the relevant figure recipe.
- For a GPU literature, kernel, driver, framework, issue/PR, release, hardware-documentation, or reliability-event survey, use `collect-research-sources` for bounded multi-source acquisition and `search-primary-evidence` for inclusion, contrary queries, and coverage judgment; either remains optional when a reliable source set already exists.
- For a small training or inference run whose design is already reliable, start at environment inspection or supervision and hand the verified bundle directly to analysis.
- For a reliability campaign, keep injection authorization and scientific stops in the design, operational failure classes in supervision, event denominators in analysis, and location/bit/layer encoding in figures.
- For existing measurements, start at `analyze-experiment-results`; use environment evidence only when it affects comparability or claim boundaries.
- For a no-GPU server decision, `inspect-gpu-environment` alone can produce a useful attestation.
- Apply `no-negative-echo` to any durable contract, result manifest, figure package, report, commit, or handoff independently of the other capabilities.

## Hard boundaries and adaptive choices

The hard boundaries are limited to authority, safe target identity, immutable or explicitly drafted execution meaning, raw-data retention, status separation, relative-path safety, reference resolution, byte integrity, and internally consistent durable states.

The agent may choose or extend profilers, event APIs, framework timers, sample sizes, randomization, statistical models, resampling methods, telemetry cadence, chart types, venue overrides, and report structure. Missing optional telemetry or descriptive metadata normally narrows the claim and produces a warning. Pause only when the gap changes the research object, conclusion, experimental safety, resource/cost authorization, or authority for an external action.

## Known validation limits

- Physical NVIDIA, AMD, multi-GPU, MIG, NVLink, PCIe peer access, ECC, power/clock control, and live telemetry behavior were not exercised in the validation environment.
- SSH semantics were tested through offline interfaces and local fixtures, not against a rented external server.
- Active diagnostics, profilers, stress tests, fault injection, driver or firmware changes, power/clock setters, resets, and partition changes require a separately approved execution contract and suitable hardware.
- Venue profiles are project-maintained submission aids. The exact journal, conference, article type, artwork class, and current author instructions remain authoritative.
