---
name: create-publication-figures
description: Create reproducible, accessible publication-quality scientific figures and auditable figure packages from CSV or JSON data plus a short figure specification. Use when Codex needs to draft or revise line, scatter, bar, histogram, ECDF, heatmap, GPU benchmark, training-trajectory, latency, throughput, scaling, roofline, hardware-telemetry, or error-localization figures; export PDF, SVG, or print-resolution PNG; apply Nature Portfolio, Science/AAAS, IEEE, or ACM submission constraints; validate figure dimensions, fonts, DPI, labels, color accessibility, clipping, overlaps, hashes, captions, or alt text; or prepare figures and provenance for manuscript submission.
---

# Create Publication Figures

Create a useful draft from structured data quickly, then add only the review depth the task needs. Treat every bundled venue configuration as this project's submission profile, not as an official publisher template or a guarantee of acceptance.

Use Python 3.10+ with Matplotlib, NumPy, and Pillow available. The scripts use only platform-neutral Python APIs and Matplotlib's non-interactive backend.

## Take the shortest path

1. Inspect the data columns and the user's scientific intent. Do not infer transformations, uncertainty, exclusions, or statistical methods that change the claim.
2. Write a small JSON spec. For a wide CSV, this is enough:

```json
{
  "chart": "line",
  "x": "time_h",
  "y": ["control", "treatment"],
  "xlabel": "Time (h)",
  "ylabel": "Response (%)",
  "caption": "Response over time for control and treatment conditions.",
  "alt_text": "Line chart comparing control and treatment response across five time points."
}
```

3. Render PDF, SVG, 300 dpi PNG, and `manifest.json`:

```bash
python scripts/render_figure.py \
  --data /path/to/data.csv \
  --spec /path/to/spec.json \
  --output-dir /path/to/figure-package
```

`--spec` accepts a JSON file path or an inline JSON object. CSV and JSON record data are accepted. The default `draft` profile is platform-neutral and uses Matplotlib's bundled DejaVu Sans font.

4. Validate mechanical facts and collect human-review warnings:

```bash
python scripts/validate_figure_package.py \
  /path/to/figure-package \
  --report /path/to/figure-package/qa-report.json
```

5. Open at least the PNG and one vector output. Resolve warnings that matter to the claim and delivery context; never treat a clean mechanical report as scientific or visual approval.

## Use the input contract

Keep a simple spec simple. Supported core fields are:

- `chart`: `line`, `scatter`, `bar`, `hist`, `ecdf`, or `heatmap`.
- `x`: the x/category column.
- `y`: one column name or a list of wide-form series columns.
- `series`: optional grouping column for long-form data; use it with one `y` column, or with `x` for `hist`/`ecdf`.
- `value`: cell-value column for `heatmap`, where `x` and `y` are its column and row categories.
- `title`, `xlabel`, `ylabel`, `caption`, `alt_text`: publication text and accessibility metadata.
- `profile`, `size`, `width_mm`, `height_mm`, `dpi`, `font_family`, `font_size_pt`: reproducible rendering controls.
- `series_labels`, `xlim`, `ylim`, `xscale`, `yscale`, `legend`, `grid`, `sort_x`, `nonfinite`: optional presentation controls.
- `filter`: explicit equality filter whose exclusions remain counted in the manifest; use it to keep failed attempts in the hashed input while plotting valid measurements.

Use `nonfinite: "error"` by default. Set it to `"drop"` only after the omission is scientifically justified; the manifest records dropped rows and the validator emits a warning.

For grouped data, use records such as `time,condition,value` with `x: "time"`, `y: "value"`, and `series: "condition"`. Read [references/figure-spec.md](references/figure-spec.md) only for long-form data, grouped bars, overrides, or schema details.

For GPU experiments or system benchmarks, read [references/gpu-figure-recipes.md](references/gpu-figure-recipes.md). It routes step trajectories, latency distributions, throughput, roofline, telemetry, scaling, error heatmaps, and bad-case context without imposing one chart type. Keep attempted runs, timeouts, OOMs, missing samples, denominators, and units explicit.

## Exercise informed freedom

Choose the chart type and visual method that best communicates the scientific question. The bundled renderer supplies a reliable baseline, not a limit on legitimate figure design.

- Use line charts for ordered trajectories where connecting observations is meaningful.
- Use scatter plots for paired observations and relationships; do not add fits or confidence bands without an explicit method.
- Use bar charts for justified aggregate or categorical comparisons; prefer points or distributions when bars would hide important variation.
- Use ECDFs or histograms for distributions according to the estimand; use heatmaps only when both axes form meaningful cells and distinguish missing cells from observed zeros.
- For heatmaps, distributions, uncertainty graphics, multipanel figures, domain plots, or unusual encodings, extend the spec and renderer or write a task-local script. Preserve the package contract: deterministic outputs, input/spec/profile/tool/file SHA-256 hashes, dimensions/DPI, caption, alt text, series styles, and QA warnings.
- Record any transformation, aggregation, model, interval, normalization, or exclusion in the spec and caption. Ask when the choice could change the scientific conclusion.

## Apply a submission profile only when needed

For a named venue, camera-ready task, or submission audit, read [references/submission-profiles.md](references/submission-profiles.md), then select one of:

```bash
--profile nature-portfolio
--profile science-aaas
--profile ieee
--profile acm
```

The executable configuration is [references/submission_profiles.json](references/submission_profiles.json). Each profile records official source URLs, verification date, scope, official constraints, project defaults, and values that must be rechecked. Prefer the target journal or conference's current instructions whenever they differ. Do not copy unverified publisher-branded templates or present these profiles as official artwork.

## Perform proportional QA

The renderer always uses a fixed seed, fixed export metadata, explicit font resolution, explicit physical size, an accessible default palette, and redundant series encodings. Its manifest records:

- raw input, canonical spec, selected profile, renderer, and output file SHA-256 hashes;
- rows/columns, selected chart and series, seed, Matplotlib version, font, size, DPI, and export metadata;
- caption, alt text, per-series color/marker/linestyle/hatch, and dropped non-finite values;
- mechanical approximations for canvas clipping, text collisions, and legend/data overlap.

The validator uses `ERROR` only for mechanical facts such as missing or unreadable files, malformed structure, hash mismatches, invalid dimensions, or wrong PNG DPI. Scientific meaning, chart choice, accessibility interpretation, captions, font fallback acceptability, and visual overlap remain `WARNING` items for review.

For manuscript, multipanel, statistical, image-heavy, or accessibility-critical work, read [references/qa-review.md](references/qa-review.md) and complete the human checklist. Always inspect:

- whether axes, units, uncertainty, sample size, transformations, and exclusions are truthful;
- whether labels remain readable at final physical size and nothing is unintentionally cropped;
- whether series remain distinguishable in grayscale and common color-vision conditions;
- whether legends, annotations, and data marks collide;
- whether caption and alt text communicate the finding without overstating it;
- whether the exact venue and article type changed after the profile's verification date.

## Verify the bundled implementation

Run the self-test after changing scripts, profiles, or the package schema:

```bash
python scripts/self_test.py
python -m py_compile scripts/render_figure.py \
  scripts/validate_figure_package.py scripts/self_test.py
```

The self-test uses a temporary directory, exercises line, scatter, and bar rendering, validates PDF/SVG/PNG readability, physical dimensions, DPI and hashes, compares two identical runs byte-for-byte, prints a machine-readable JSON result, and automatically removes all generated artifacts.
