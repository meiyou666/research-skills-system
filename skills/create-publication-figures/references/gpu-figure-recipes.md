# GPU figure recipes

Read this reference for GPU training, inference, reliability, scaling, or hardware telemetry figures. Choose the encoding from the question and data-generating process; do not force all experiments into a uniform visual grammar.

## Contents

- Shared rules
- Per-step trajectories
- Latency distributions
- Throughput
- Roofline
- Memory, utilization, power, and temperature
- Single- and multi-GPU scaling
- Error position, bit, and layer heatmaps
- Bad-case context

## Shared rules

- Keep the hashed source at the observational grain: request, step, run, device sample, injected fault, or bad case.
- Give every rate a numerator and denominator. State whether work is attempted, completed, valid, useful, non-padding, or steady-state.
- Put units in field names or axis labels: `ms`, `s`, `J`, `W`, `°C`, `bytes`, `GiB`, `tokens/s`, `samples/s`, `FLOP/s`, `FLOP/byte`, `%`, or errors per stated exposure.
- Keep `run_id`, hardware/model/config identifiers, warm-up policy, precision, batch/concurrency, device count, and status available for stratification.
- Preserve timeout, OOM, crash, thermal-throttle, invalid-output, missing-telemetry, and censored states in the source. Use an explicit `filter` only for the plotted estimand; report excluded counts and denominators in caption/alt text, and add a companion failure-count/rate panel or figure when material.
- Treat missing as unknown/unobserved, never as zero. In heatmaps the renderer masks absent cells gray. Zero must be an observed numeric zero.
- Aggregate, normalize, smooth, align, or interpolate only through an explicit upstream method. Record it in the spec/caption. Show run-level variation when a mean would hide instability.

## Per-step trajectories

Question: how does a metric evolve with training/inference step, token, or wall time?

- Required fields: `run_id`, ordered `step` (or `tokens_seen`/`elapsed_s`), numeric metric, and `status`. Add `seed`, `gpu_id`, configuration, and phase when relevant.
- Denominator/unit: state whether step means optimizer update, microbatch, token, request, or kernel sample. Label metric units and any window size.
- Missing/failure: retain missing steps and failed runs. Do not bridge a crash, resume boundary, evaluation gap, or logging outage with a continuous line; split series or use points.
- Use: line for genuinely ordered continuous progression; scatter for irregular samples/gaps; per-run faint lines plus an explicitly defined summary for replicated runs.
- Not appropriate: a connected line across unordered configurations, or smoothed trajectories when transient spikes/instability are the question.

Runnable baseline:

```json
{
  "chart": "line",
  "x": "step",
  "y": "loss",
  "series": "run_id",
  "filter": {"status": "ok"},
  "xlabel": "Optimizer step",
  "ylabel": "Training loss",
  "sort_x": true,
  "caption": "Per-run training loss; failed runs remain in the source and their terminal steps are reported separately."
}
```

## Latency distributions

Question: what is the latency distribution, including tails and failures?

- Required fields: one row per attempted request with `request_id`, latency, `status`, configuration/series, and preferably arrival/completion time. Add warm-up and censoring flags.
- Denominator/unit: attempted requests is the failure-rate denominator; completed valid requests is commonly the latency-distribution denominator. State both. Use one consistent unit, usually ms.
- Missing/failure: timeout/crash rows keep status and may have blank latency. Filter `status: ok` explicitly for latency, then report timeouts/failures separately. If timeouts are censored observations rather than missing, use survival methods instead of silently dropping them.
- ECDF: best for quantiles/tails and bin-free comparison; every completion has equal weight. It can visually compress rare extreme values, so annotate/report key quantiles.
- Histogram: best for modes and absolute/frequency shape; use common predeclared bin edges across series and report whether y is count or density. Conclusions can change with bins.
- Violin: useful for large continuous samples and compact group comparison, with identical bandwidth rules and visible `n`; avoid when small/multimodal samples or tails matter. The baseline renderer does not implement violin—extend it while preserving the manifest contract.
- Box: useful for robust summary across many groups, preferably with raw points and `n`; it does not show tail shape or failure frequency. Extend the renderer or use a task-local tool under the same package contract.
- Not appropriate: mean-only bars for skewed latency, mixing warm-up and steady state without labeling, or percentile curves with unequal/unstated denominators.

Runnable ECDF preserving failed attempts in the input:

```json
{
  "chart": "ecdf",
  "x": "latency_ms",
  "series": "system",
  "filter": {"status": "ok", "phase": "steady"},
  "xlabel": "End-to-end latency (ms)",
  "denominator": "Completed valid steady-state requests; all attempts and failures reported in caption"
}
```

Runnable histogram alternative:

```json
{
  "chart": "hist",
  "x": "latency_ms",
  "series": "system",
  "filter": {"status": "ok"},
  "bins": [0, 5, 10, 20, 40, 80, 160],
  "density": false,
  "xlabel": "End-to-end latency (ms)",
  "ylabel": "Completed requests"
}
```

## Throughput

Question: how much useful work completes per wall-clock time as load/configuration changes?

- Required fields: configuration x variable (`batch_size`, `concurrency`, sequence length, etc.), throughput, `run_id`, `status`, GPU count, precision, and workload identity.
- Denominator/unit: define useful outputs (non-padding tokens, samples, images, requests) and elapsed interval. State whether initialization, compilation, warm-up, data loading, synchronization, and failures are included.
- Missing/failure: retain OOM/timeouts/crashes at their attempted configuration. Do not connect through failed load points; use a companion success/failure encoding.
- Use: scatter for raw runs; line only when x is ordered and interpolation is meaningful; distribution per configuration when run variance matters.
- Not appropriate: comparing different work definitions, sequences, accuracy targets, or GPU counts as if throughput were directly comparable.

```json
{
  "chart": "line",
  "x": "batch_size",
  "y": "tokens_per_s",
  "series": "system",
  "filter": {"status": "ok"},
  "xlabel": "Batch size (sequences)",
  "ylabel": "Non-padding output tokens/s",
  "xscale": "log",
  "sort_x": true
}
```

## Roofline

Question: is measured performance limited by arithmetic intensity, memory bandwidth, or peak compute?

- Required fields: arithmetic intensity in FLOP/byte, achieved performance in FLOP/s, workload/kernel identifier, and explicit compute and memory ceilings for the exact device/precision. Record whether bytes are DRAM, cache, or modeled traffic.
- Denominator/unit: use a consistent FLOP convention (for example, whether FMA counts as two) and byte boundary. State sustained versus theoretical ceilings.
- Missing/failure: retain unsupported/failed kernels and measurements below resolution; do not map them to zero on log axes.
- Use: log-log scatter for measured points plus separately calculated piecewise roof lines. Label precision and device. A task-local composite script is usually clearer than connecting measurements.
- Not appropriate: when operation counts/traffic are not defensible, when ceilings come from a different device/precision, or when latency rather than throughput is the primary limit.

Baseline measured points:

```json
{
  "chart": "scatter",
  "x": "arithmetic_intensity_flop_per_byte",
  "y": "achieved_tflop_per_s",
  "series": "kernel_family",
  "filter": {"status": "ok"},
  "xlabel": "Arithmetic intensity (FLOP/byte from DRAM)",
  "ylabel": "Achieved performance (TFLOP/s)",
  "xscale": "log",
  "yscale": "log"
}
```

## Memory, utilization, power, and temperature

Question: how do device resource and thermal states change over time/step or configuration?

- Required fields: `timestamp` or `step`, `gpu_id`, metric value, status/availability, and sampling source/interval. Memory also needs allocated/reserved/total semantics; utilization needs engine definition; power needs board/chip scope; temperature needs sensor location.
- Denominator/unit: bytes/GiB and percent of which capacity; utilization percentage over which sampling interval; W; °C. Energy requires integrating power over elapsed seconds and reports J.
- Missing/failure: keep unavailable samples and logging gaps. Never forward-fill across process death, device reset, or logger outage without an explicit imputation method.
- Use: separate aligned line panels/figures for metrics with different units; per-GPU series when imbalance matters; distributions for steady-state variability.
- Not appropriate: dual axes that imply a false relationship, averaging GPUs when imbalance/throttling is the finding, or treating vendor utilization as achieved FLOP efficiency.

Use the line recipe with `series: gpu_id` separately for `memory_allocated_gib`, `sm_utilization_pct`, `board_power_w`, and `temperature_c`, or create a multipanel task-local extension under the same manifest contract.

```json
{
  "chart": "line",
  "x": "elapsed_s",
  "y": "board_power_w",
  "series": "gpu_id",
  "filter": {"status": "ok"},
  "xlabel": "Elapsed steady-state time (s)",
  "ylabel": "Board power (W)",
  "sort_x": true
}
```

## Single- and multi-GPU scaling

Question: how does performance/efficiency change with device count?

- Required fields: `gpu_count`, measured time or throughput, `run_id`, `status`, workload size, parallelism strategy, interconnect/topology, precision, and baseline configuration.
- Denominator/unit: strong scaling keeps total work fixed; weak scaling keeps per-GPU work fixed. Define speedup relative to which measured baseline and efficiency as `speedup / gpu_count` (or the justified alternative).
- Missing/failure: retain OOM, hang, numerical failure, and invalid-result points. Do not interpolate an apparently smooth scaling curve through them.
- Use: raw-run scatter plus summary; ordered line for measured median/mean with method stated; include a clearly labeled ideal reference series calculated from the baseline.
- Not appropriate: mixing workload size, topology, precision, accuracy, or baseline; reporting GPU count without node count/interconnect when communication dominates.

```json
{
  "chart": "line",
  "x": "gpu_count",
  "y": ["measured_speedup", "ideal_speedup"],
  "filter": {"status": "ok"},
  "xlabel": "GPU count",
  "ylabel": "Speedup vs measured 1-GPU baseline",
  "sort_x": true,
  "caption": "Strong-scaling speedup for fixed total work; efficiency equals speedup divided by GPU count."
}
```

## Error position, bit, and layer heatmaps

Question: where do faults/errors concentrate across two discrete dimensions?

- Required fields: row dimension (`layer`, operator, tensor, or site), column dimension (`bit_position`, step bucket, error class), and a precomputed cell value. Preserve exposure/opportunity counts alongside errors.
- Denominator/unit: prefer error rate per stated injections/operations/elements when exposure differs. Counts are valid only when exposure is equal or itself visible.
- Missing/failure: absent combinations remain missing gray cells; observed zero-error cells are numeric zero. Failed experiments remain status rows and should not become zero.
- Use: `cividis` linear heatmap for non-negative rates/counts; explicit log transform/normalization only when justified and disclosed; annotate only sparse/small matrices.
- Not appropriate: unordered continuous axes better shown as scatter, cells with incomparable denominators, or a diverging palette for one-sided non-negative magnitude.

```json
{
  "chart": "heatmap",
  "x": "bit_position",
  "y": "layer",
  "value": "errors_per_million_injections",
  "filter": {"status": "ok"},
  "xlabel": "Bit position",
  "ylabel": "Layer",
  "colorbar_label": "Errors per million injections",
  "vmin": 0,
  "cmap": "cividis"
}
```

## Bad-case context

Question: which concrete inputs/events fail, where, and under what surrounding context?

- Required fields: stable `case_id`, run/config, status/error class, severity or metric, location (`step`, token, layer, operator, bit), and a privacy-safe context reference. Keep raw context in an access-controlled artifact when it contains sensitive or copyrighted data.
- Denominator/unit: state whether cases are sampled from all attempts, failures, top-k severity, or a labeled audit set. Rates need the eligible-case denominator.
- Missing/failure: preserve uncategorized and unavailable context as explicit states. Do not discard duplicate-looking failures without a documented deduplication key.
- Use: scatter for severity versus location, heatmap for aggregate location/class after explicit denominators, bar for error-class counts, and a linked table/list for actual case context. Often the right deliverable is a figure plus machine-readable bad-case table.
- Not appropriate: stuffing long text into plot annotations, exposing sensitive prompts/data, or presenting a selected bad-case gallery as prevalence.

The baseline renderer does not embed arbitrary text tables. Generate the quantitative figure with its standard package, retain hashed `case_id` links in the data, and deliver the context table separately with matching provenance.

```json
{
  "chart": "scatter",
  "x": "step",
  "y": "severity_score",
  "series": "error_class",
  "xlabel": "Detection step",
  "ylabel": "Declared severity score",
  "caption": "Audited bad cases by detection step and error class; case identifiers link to a separately controlled context table."
}
```
