# Preregistration-Style Protocol

Create one protocol cell for each distinct comparison. Keep confirmatory and exploratory cells visibly separate.

## JSON field contract

Use `protocol_id` as the canonical stable ID in `experiment-protocol.json`; the validator accepts
equivalent `contract_id` when it carries the same role. If both appear, their values must
match. Data and execution artifacts use canonical `contract_id`; their accepted equivalent IDs
are documented in their own contracts.

Use these canonical protocol fields. The validator also accepts the listed equivalents so a
bounded input does not need a cosmetic rewrite:

| Canonical field | Accepted equivalent fields |
| --- | --- |
| `research_input` | `hypothesis_input`, `research_brief` |
| `questions_or_hypotheses` | `questions`, `hypotheses`, `hypothesis_map` |
| `design` | `study_design` |
| `outcomes` | `outcome_variables`, `metrics` |
| `decision_rules` | `decisions` |
| `sampling` | `sampling_plan` |
| `analysis` | `analysis_plan` |
| `stop_rules` | `stopping_rules`, `stop_policy` |
| `unresolved_blockers` | `blockers` |

Do not emit both names for one concept unless a compatibility consumer requires them. When both
ID aliases appear, keep them identical.

Data and execution contracts are optional for a compact design. Declare them only when the
handoff needs them:

```json
"contracts": {
  "data": {"required": true, "contract_id": "data-1", "sha256": "..."},
  "execution": {"required": false}
}
```

For each object, `contract_id` is canonical; `data_contract_id` or `execution_contract_id` is
accepted in its corresponding entry. If an ID or SHA256 is declared, the package validator
compares it with the actual contract ID and exact file bytes. Avoid circular hashes: an execution
contract can hash the protocol while the protocol identifies that execution contract by ID.

Omitting `contracts`, omitting one entry, or setting `required: false` produces no missing-file
diagnostic. A string ID or boolean is also accepted for each entry. Equivalent top-level
`data_contract`, `data_contract_id`, `execution_contract`, and `execution_contract_id` imply that
the corresponding artifact is required. In a draft, a missing required artifact is a warning; in
a frozen protocol it is an error. Validate the package directory whenever contracts are required;
protocol-only validation cannot prove their presence and therefore rejects an unverifiable frozen
handoff.

## Required protocol sections

1. **Lineage:** `protocol_id` and version, frozen brief ID and SHA256, approval state, and change policy.
2. **Scope:** research object, target population, unit, boundaries, claim ceiling, and ethical or safety constraints.
3. **Hypothesis map:** upstream hypothesis, falsifier, estimand, protocol cells, and decision rule.
4. **Design:** design type, assignment mechanism, controls, blocking, blinding where applicable, interference assumptions, and repeated-measure structure.
5. **Variables:** role, operational definition, unit, measurement method, valid range, timing, and provenance.
6. **Metrics:** formula, direction, denominator, aggregation, uncertainty, minimally meaningful effect, and measurement validation.
7. **Sampling:** frame, strata, randomization unit, replication, seed policy, exclusions, sample-size basis, and resource cap.
8. **Analysis:** transformations, model or test, assumptions, multiplicity, missingness, outliers, sensitivity analyses, and software version.
9. **Decision rules:** support, reject, inconclusive, and boundary-result outcomes for every hypothesis.
10. **Stops:** scientific futility or efficacy, safety, resource, data-quality, and operational-failure rules with authorities and required evidence.
11. **Data and execution:** linked contract IDs and SHA256 values.

## Control selection

Choose controls based on threats:

- a negative control detects background or pipeline artifacts;
- a positive control establishes instrument sensitivity;
- a sham control isolates procedural effects;
- a reference implementation or current best practice provides a strong baseline;
- an ablation isolates a proposed mechanism;
- a randomized order or blocking plan controls drift and batch effects.

Use the same eligible population, denominators, quality constraints, resource accounting, and measurement window across comparisons. Explain any unavoidable mismatch and limit the claim.

## Decision states

- `SUPPORTED`: all predeclared evidence conditions for the bounded hypothesis hold.
- `REJECTED`: a valid, sufficiently sensitive observation meets a falsifier.
- `INCONCLUSIVE`: data integrity, sensitivity, power, or identifiability is insufficient.
- `BOUNDARY`: the relationship holds only in a predeclared subset or range.

Downstream utility cannot rescue an upstream validity failure. Preserve the narrowest interpretable conclusion from each valid outcome.
