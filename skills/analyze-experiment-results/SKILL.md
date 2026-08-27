---
name: analyze-experiment-results
description: Transform a verified raw result bundle or equivalent traceable measurements into reproducible derived tables, metric definitions, statistical results, bad-case and long-tail analyses, sensitivity checks, and bounded findings. Use after benchmarks, training, inference, simulations, reliability or fault-injection studies, and before publication figures or report revision. Preserve fine-grained observations, failures, missing values, and provenance while allowing domain-appropriate analysis methods.
---

# Analyze Experiment Results

Build traceable derived evidence from raw measurements. Keep scientific outcomes, execution failures, and measurement contamination distinct.

## Take the shortest useful path

1. Verify available input provenance and identify the finest observation unit.
2. Define one metric with numerator, denominator, unit, direction, and valid states.
3. Produce a derived table that retains run and observation IDs plus status.
4. Inspect its distribution, missing and non-finite values, failures, and influential cases.
5. State one bounded finding and the next uncertainty that matters.

Accept a verified result bundle, local measurements with hashes, an existing derived dataset plus transformation provenance, or equivalent traceable input. Mark analysis `draft` when verification, definitions, or design context is incomplete. Ask only when ambiguity changes the observation unit, denominator, scientific interpretation, safety, or authority to access data.

## Preserve evidence lineage

Treat raw files as immutable. Record input hashes, contract or run IDs when available, transformation code identity, parameters, exclusions, and output hashes. Keep per-run, per-sample, per-request, per-event, or per-step rows before aggregation.

Use three status namespaces:

- scientific observation;
- execution failure; and
- measurement contamination or validity failure.

Retain missing, failed, excluded, and non-finite states with reasons. Never turn them into zero or silently remove them from a denominator.

## Scale the analysis with the question

Read [references/analysis-methods.md](references/analysis-methods.md) for confirmatory, multi-group, repeated-measure, long-tail, or consequential analysis. Choose estimands, intervals, tests, models, resampling, multiple-comparison handling, subgroup analyses, and robustness checks from the design and data-generating process.

Read [references/gpu-analysis.md](references/gpu-analysis.md) for GPU kernels, training, inference, energy, scaling, and reliability studies. Analyze device and wall timing separately, preserve warm-up and throttling states, retain per-device and per-rank data, and keep correctness, performance, energy, reliability, and cost questions distinct.

Use `scripts/summarize_measurements.py` for a reproducible baseline over CSV or JSONL when its groupwise descriptive, bootstrap, and bad-case functions fit the task. It accepts a compact single `record_status` mapping or independent execution, measurement, and scientific `status_columns`; a scientific failure may remain an analyzable observation. Its generated `findings.md` is always a review draft that exposes mechanical warnings and unresolved blockers. Extend or replace the script for domain-specific methods and record that code in the manifest.

## Produce an analysis package when useful

Read [references/analysis-package.md](references/analysis-package.md). A durable handoff commonly contains:

```text
analysis/
  analysis-spec.json
  metric-dictionary.json
  derived/
  statistics.json
  findings.md
  analysis-manifest.json
```

A small task may return one derived table and a compact metric/finding record. Run:

```bash
python3 scripts/validate_analysis_package.py analysis/
```

Warnings identify optional scientific work. Structural, reference, and hash failures block a verified handoff. Provide machine-readable derived data and figure-relevant metadata to `create-publication-figures`; provide findings, limitations, and provenance to `revise-evidence-report`. This skill does not alter raw data, execute new runs, render publication figures, or rewrite a report.
