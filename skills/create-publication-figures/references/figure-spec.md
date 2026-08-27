# Figure specification

Read this reference when the minimal `chart`/`x`/`y` spec is insufficient.

## Contents

- Data forms and core schema
- Wide- and long-form series
- Grouped bars
- Histograms and ECDFs
- Heatmaps
- Text generation
- Extension contract

## Data forms

CSV must have a header row. JSON may be:

- a list of row objects;
- an object with a `records` list;
- an object whose `data` value is a list of row objects;
- a column-oriented object with equal-length arrays.

The renderer converts numeric-looking values to finite floats when a numeric field is required. It rejects empty input, missing columns, inconsistent JSON records, booleans in numeric fields, and non-finite numeric values by default.

## Core schema

```json
{
  "chart": "line | scatter | bar | hist | ecdf | heatmap",
  "x": "column-name",
  "y": "column-name or [column-name, ...]",
  "series": "optional-long-form-group-column",
  "value": "heatmap-cell-value-column",
  "series_labels": {"raw-name": "Display name"},
  "title": "Optional in-canvas title",
  "xlabel": "Axis label with units",
  "ylabel": "Axis label with units",
  "caption": "Standalone manuscript caption draft",
  "alt_text": "Visual description complementary to the caption",
  "profile": "draft | nature-portfolio | science-aaas | ieee | acm",
  "size": "profile preset name",
  "width_mm": 89.0,
  "height_mm": 60.0,
  "dpi": 300,
  "font_family": "DejaVu Sans",
  "font_size_pt": 8.0,
  "legend": true,
  "legend_location": "best",
  "filter": {"status": ["ok", "valid"]},
  "denominator": "Plain-language population or exposure definition",
  "grid": false,
  "sort_x": false,
  "sort_y": false,
  "xscale": "linear | log | symlog | logit",
  "yscale": "linear | log | symlog | logit",
  "xlim": [0, 10],
  "ylim": [0, 100],
  "nonfinite": "error | drop"
}
```

CLI `--profile`, `--size`, `--dpi`, and `--seed` override the same spec fields. Explicit `width_mm` and `height_mm` override a named size preset.

## Wide-form series

Use one y column per series:

```json
{
  "chart": "scatter",
  "x": "dose_mg",
  "y": ["cohort_a", "cohort_b"],
  "xlabel": "Dose (mg)",
  "ylabel": "Response (a.u.)"
}
```

Rows retain input order unless `sort_x` is true. Sorting occurs independently within each series.

## Long-form series

Use one y column and a grouping column:

```json
{
  "chart": "line",
  "x": "day",
  "y": "value",
  "series": "condition",
  "series_labels": {"ctl": "Control", "tx": "Treatment"}
}
```

Group order follows first appearance in the data. The manifest records raw group values and display labels.

## Grouped bars

Both wide and long forms produce grouped bars. Bars begin at zero unless `ylim` explicitly changes the scale. Review any truncated bar baseline as a scientific warning.

## Histograms and ECDFs

Use `x` as the measured numeric column and omit `y`. An optional `series` column splits the measurements into groups. Histograms accept `bins` as an integer, increasing edge list, or NumPy bin rule, plus `density: true|false`. All histogram groups share bin edges. ECDFs use every finite observation and plot cumulative fractions from 0 to 1.

```json
{
  "chart": "ecdf",
  "x": "latency_ms",
  "series": "implementation",
  "filter": {"status": "ok"},
  "xlabel": "Latency (ms)",
  "denominator": "All attempted requests; timeouts reported separately in caption"
}
```

The explicit filter is applied before numeric parsing, so failed rows may keep a blank measurement in the hashed source. The manifest records input, selected, excluded, dropped, and plotted counts. Never describe selected observations as all attempts.

## Heatmaps

Use long-form records with `x`, `y`, and `value`. Each x/y cell must be unique; aggregate explicitly upstream rather than letting the renderer guess. Missing combinations remain masked in a distinct gray color rather than becoming zero. Use `x_order`/`y_order` for an explicit complete category order. An order must contain every observed category and may declare additional categories with no valid cell; those rows or columns remain visible and masked as missing. Use `cmap` to override `cividis`, and `annotate: true` only when cell text remains readable.

```json
{
  "chart": "heatmap",
  "x": "bit_position",
  "y": "layer",
  "value": "error_rate_per_million",
  "xlabel": "Bit position",
  "ylabel": "Layer",
  "colorbar_label": "Errors per million operations",
  "vmin": 0
}
```

## Text generation

If `caption` or `alt_text` is omitted, the renderer writes a conservative draft using chart type, axes, series names, point counts, and numeric ranges. Replace generated text for submission: it cannot know the study design, uncertainty, causal interpretation, or intended takeaway.

## Extension contract

For unsupported figure types, preserve these manifest sections so the standard validator and downstream agent can audit the package:

- `schema_version`, `package_type`, `generator`;
- `input`, `spec`, `profile`, and `render` with SHA-256 hashes;
- `figure` with chart, labels, caption, alt text, series styles, and row counts;
- `files` with name, media type, SHA-256, dimensions, and PNG DPI/pixels where applicable;
- `qa` with non-finite handling, accessibility metadata, mechanical probes, and review warnings.

Keep output paths relative to the package. Avoid timestamps, absolute paths, random IDs, and environment-specific metadata when deterministic hashes matter.
