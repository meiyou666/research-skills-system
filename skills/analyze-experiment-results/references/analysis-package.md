# Analysis Package Contract

Use a package when derived results cross tools, agents, or publication stages. Keep domain extensions under `extensions`.

## Analysis specification

`analysis-spec.json` uses `schema_version: 1`, a stable `analysis_id`, positive `version`, and `status` (`draft` or `frozen`). Record:

- purpose, questions or hypotheses, and design reference when available;
- input files and SHA256 values or verified bundle identity;
- observation unit, identifier fields, `record_status` namespaces, and valid states;
- metrics, grouping or stratification, transformations, exclusions, and missing-data rules;
- statistical or descriptive methods, seed, software identity, and sensitivity variants;
- claim boundary and unresolved blockers.

For existing one-column data, map `record_status.column` plus `valid`, `execution_failure`, `contamination`, and `missing`. When the source already separates lifecycle and validity, use any subset of these optional mappings:

```json
{
  "status_columns": {
    "execution": {
      "column": "run_status",
      "accepted": ["SUCCEEDED"],
      "failed": ["OOM", "EXITED"],
      "missing": ["UNKNOWN"]
    },
    "measurement": {
      "column": "measurement_status",
      "accepted": ["VALID"],
      "contaminated": ["THROTTLED"],
      "missing": ["MISSING"]
    },
    "scientific": {
      "column": "scientific_status",
      "observed": ["PASS", "FAIL"],
      "excluded": ["OUT_OF_SCOPE"],
      "missing": ["NOT_EVALUATED"]
    }
  }
}
```

Map project-specific values rather than renaming raw data. A scientific `FAIL` is often the primary reliability observation and belongs in `observed`; use `excluded` only for a declared scientific exclusion. Unconfigured namespaces do not block analysis. The baseline script appends normalized `analysis_*_status` and `analysis_eligible` fields to its derived observations while retaining the source status columns.

## Metric dictionary

For each metric record stable ID, description, source fields, formula or transformation, numerator, denominator, unit, direction, valid states, aggregation, interval or uncertainty semantics, and interpretation limits. Use `not_applicable` when a concept has no meaningful numerator or denominator rather than inventing one.

## Derived artifacts

Keep normalized fine-grained tables separately from summaries. Include stable input row or event IDs in derived rows. Statistics identify the metric, population or stratum, valid and total counts, missing, non-finite, execution-failure and contamination counts, estimand, effect or summary, interval, method, and sensitivity ID.

Bad-case tables retain the observation IDs and context needed to inspect long tails, correctness failures, recovery failures, or influential cases.

The baseline `findings.md` remains `draft`, summarizes only recorded coverage and descriptive values, and lists warnings and `unresolved_blockers`. Replace it with reviewed, bounded findings before freezing a package; the validator rejects a frozen package whose findings are still draft.
The bundled summarizer therefore accepts only a draft analysis spec for generation. It refuses a
`frozen` spec instead of creating a package whose manifest claims freeze while its findings remain
an unreviewed scaffold. Freeze is a separate, explicit review and manifest update.

## Manifest

`analysis-manifest.json` records the analysis ID and status, spec and metric-dictionary hashes, input identities, transformation script identities, and every output's relative path, byte count, SHA256, and role. Use normalized relative paths and reject symlinks or special files in a verified package.

Treat the manifest as the package commit marker. Declare every regular file except
`analysis-manifest.json`; its location is fixed by the contract. The implied directory set must
match the package exactly, so undeclared files, empty directories, symlinks, FIFOs, devices, and
missing members fail verification. The bundled producer refuses an existing destination entry,
including a dangling symlink, and claims the absent destination before moving staged artifacts;
it moves the manifest last. It also refuses symlinks in the output path. This ordering is a
process-level commit convention, not a filesystem transaction. An ordinary caught failure is
cleaned up, while forced termination, power loss, or storage failure can leave any partial state.
Always validate exact membership and hashes before consuming the package, even when the manifest
is present.

Caller-supplied input and spec paths may be symlinks. The bundled tools deliberately dereference
them, require regular-file targets, and hash the target bytes. This convenience does not extend to
package roots or output paths, where every component must be a real directory entry.

`frozen` means the recorded transformations and findings were accepted for the stated purpose. It does not certify that a statistical model or scientific conclusion is universally valid.
