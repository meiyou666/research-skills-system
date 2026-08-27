# Adversarial Review

Review the proposed brief with independent roles. Consolidate objections by their underlying evidence dependency so repeated citations do not count as independent confirmation.

## Review roles

- **Coverage reviewer:** challenge databases, vocabulary, language, cutoff, nearest-work search, and contrary-evidence search.
- **Evidence reviewer:** challenge primary-source status, access level, population, denominator, uncertainty, corrections, and source dependence.
- **Logic reviewer:** challenge each step from evidence to gap, question, hypothesis, and claim ceiling.
- **Construct reviewer:** challenge whether the observable represents the stated concept and whether measurement perturbs the object.
- **Alternative-explanation reviewer:** propose confounders, reverse causality, selection mechanisms, and simpler explanations.
- **External-validity reviewer:** challenge population, setting, time, scale, and implementation transfer.

## Objection record

Encode the review under an `adversarial_review` object with an `objections` list. An optional
`unresolved_blockers` list may summarize blocker IDs for a compact consumer view, but the objection
severity and status are authoritative. Do not encode `adversarial_review` itself as a list.

For each material objection object, record:

- `id` and `affected_claim_ids`, using unambiguous IDs from the same brief;
- `objection` and `evidence_dependency`;
- `severity`: `BLOCKING`, `NARROWING`, or `INFORMATIVE`;
- `resolution_needed`, retained assumption, or revised claim ceiling; and
- optional owner, and required `status`: `OPEN`, `RESOLVED`, or `ACCEPTED_RISK`.

Block freeze when a central gap relies on unverified evidence, the unit or denominator changes across the inference, a hypothesis lacks an observable falsifier, or a deployment-time claim relies on information unavailable at deployment.
Mechanically, every `BLOCKING` objection must have status `RESOLVED` before freeze;
`ACCEPTED_RISK` remains non-resolved at this severity. A stale or incomplete optional blocker
summary warrants correction but does not replace this rule. An unmatched standalone summary entry is
an explicit standalone blocker and also prevents freeze.

## Final challenge

Verify that a null or contrary result remains interpretable. Tool failure, inadequate power, invalid measurement, uncontrolled confounding, or corrupted data are inconclusive outcomes rather than scientific falsification.
