# Statistical Design

Select methods from the estimand and data-generating structure, not from anticipated results.

## Define the estimand

State the target population, treatment or exposure contrast, outcome, summary measure, time horizon, and handling of intercurrent events. Distinguish unit-level, cluster-level, repeated-measure, and event-level estimands.

## Justify sample size

Use a power or precision target based on a minimally meaningful effect, plausible variance, design effect, attrition, multiplicity, and the actual assignment unit. When these inputs are unknown, preregister a bounded pilot that estimates them and a rule for producing a new confirmatory protocol.

For rare events, justify exposure volume and the attainable confidence bound. Do not report a population rate from an opportunity sample whose denominator is undefined.

## Freeze analysis choices

Record:

- descriptive summaries and uncertainty intervals;
- primary model or test and its assumptions;
- effect size and interval, not only a threshold decision;
- repeated-measure, clustering, censoring, and dependency handling;
- family definition and multiplicity control;
- missing-data mechanism and handling;
- outlier definition and whether exclusions occur blind to outcome;
- model diagnostics and fallback model;
- predeclared subgroup and sensitivity analyses; and
- software, package, and numerical settings needed for reproduction.

Record practical and scientific thresholds separately. A statistical threshold does not establish construct validity, safety, or practical utility.

## Sequential and adaptive designs

Predeclare looks, information fractions, spending or decision boundaries, adaptation variables, and who can see interim results. Keep runtime monitoring separate from statistical interim analysis. An unplanned look cannot silently become a confirmatory decision.

## Failed execution

Classify instrumentation failure, corrupt input, contract deviation, insufficient sensitivity, and missing required artifacts as execution or validity failures. Exclude them only under predeclared rules and retain their audit records.
