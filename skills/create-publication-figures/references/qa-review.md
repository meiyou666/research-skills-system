# QA and human review

Read this reference for submission, multipanel, statistical, image-heavy, dense, or accessibility-critical figures.

## Severity boundary

Treat `ERROR` as a failed mechanical fact: a missing/unreadable file, malformed manifest, wrong or unreadable format, SHA-256 mismatch, non-positive/contradictory dimensions, PNG DPI outside tolerance, empty plotted data, or an enforceable profile size/font/DPI violation.

Treat `WARNING` as a prompt for judgment: chart appropriateness, scientific semantics, transformation choice, statistical method, caption/alt-text accuracy, color perception, font fallback acceptability, or an approximate crop/overlap signal. Do not escalate a visual heuristic into an error.

## Data and scientific meaning

- Reconcile row counts, filters, missing values, exclusions, and derived fields with the analysis.
- State aggregation, normalization, smoothing, model fitting, interval construction, and multiple-comparison handling.
- Define every uncertainty mark and give `n` or the sampling unit where relevant.
- Check that connected lines imply a meaningful order and that bar charts do not conceal important distributions.
- Check axis limits and transforms. A truncated axis may be valid, but it must not mislead; bars generally need a zero baseline.
- Preserve raw data and code provenance outside the figure package when the package contains only hashes.

## Physical output

- View the vector file at 100% and the PNG at final printed size.
- Confirm width, height, DPI, embedded/editable fonts where the venue requires them, stroke weight, marker size, and panel-label size.
- Inspect all four edges for clipped labels, annotations, error bars, and markers. Mechanical crop probes only inspect artist bounding boxes and can miss raster content or unusual transforms.
- Inspect title, axis labels, ticks, annotations, legend, and data for collisions. Automated rectangle overlap is intentionally conservative and produces false positives.

## Accessibility

- Verify every series without hue: line style plus marker for lines, marker shape for scatter, and hatch/pattern for bars.
- Print or preview in grayscale. Check common color-vision simulations with a trusted visual tool if color carries scientific meaning.
- Keep text/background contrast high and do not encode categories with red versus green alone.
- Write alt text that communicates chart type, axes, comparisons, important extrema/trends, and uncertainty. Complement rather than repeat the caption.
- Use the caption for experimental context, definitions, statistical method, and takeaways available to all readers.

The built-in color check is an approximate matrix transform plus style-duplication test. It cannot certify WCAG contrast, perceptual uniformity, or accessibility for every reader.

## Venue handoff

- Open the exact journal or conference author instructions on the submission day.
- Confirm article type, review versus production stage, column size, maximum height, formats, color space, resolution by artwork class, font/editability rules, naming, and source-data requirements.
- Record editor-specific requests as spec overrides.
- Submit only accepted formats. Retain the other generated files as reproducible working artifacts.
- Review publisher-generated PDF and HTML proofs, including captions, alt text, fonts, line weights, and color.
