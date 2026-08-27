# Analysis Methods

Choose methods from the experiment design, observation dependencies, estimand, and data quality.

## Start at the observation level

Profile identifiers, status, missingness, non-finite values, ranges, units, duplicates, ordering, and contract deviations before aggregation. Reconcile expected and observed run matrices. Preserve raw counts for every stage from eligible to measured, valid, analyzed, and reported.

Report distributions with robust location and spread, quantiles, and tail counts where useful. A single mean is insufficient when skew, mixtures, failures, or important individual cases affect the decision.

## Estimate the intended contrast

Align populations, baselines, denominators, timing windows, and quality constraints. Respect pairing, blocking, clusters, repeated measures, censoring, and multiple attempts. Report effect sizes and uncertainty intervals. Use a model or test only when its assumptions and fallback behavior are recorded.

Distinguish descriptive exploration, predeclared confirmatory analysis, and post hoc diagnosis. Apply multiplicity control to the declared family when confirmatory claims depend on it.

## Analyze failures and bad cases

Keep an execution failure out of a valid scientific estimate under the predeclared rule while retaining it in the opportunity denominator and operational analysis. Keep measurement contamination separate and show how inclusion or exclusion changes the finding.

Inspect long tails, worst valid cases, sign reversals, correctness violations, failed recoveries, and influential observations with their full context. Preserve heterogeneity that an aggregate would hide.

## Test sensitivity and robustness

Vary justified choices such as exclusion rules, warm-up cutoffs, missing-data handling, strata, model form, interval method, influential-case inclusion, and measurement source. Identify which findings survive and where boundaries change.

Use negative controls, positive controls, alternate measurements, replication batches, or independent implementations when the design provides them. Treat a robustness failure as a claim boundary or unresolved validity issue rather than hiding it.

## Write bounded findings

For each finding state the population, comparison, metric, effect or distribution, uncertainty, exclusions, failure counts, sensitivity result, and maximum supported interpretation. Separate observed result, derived inference, alternative explanation, and next evidence need.
