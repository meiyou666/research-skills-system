---
name: formulate-research-hypotheses
description: Turn an evidence dossier, literature notes, project observations, or other traceable evidence into a bounded research object, answerable questions, and falsifiable hypotheses. Use when framing a research direction, separating a scientific question from a favored mechanism, challenging a proposed gap, or preparing a hypothesis brief for later study design. Work from incomplete material when useful and label assumptions and evidence limits.
---

# Formulate Research Hypotheses

Shape traceable evidence into research questions and falsifiable hypotheses. Preserve domain flexibility and stop before experimental design.

## Take the shortest useful path

1. Identify what the available evidence establishes and where it stops.
2. State a provisional research object and one narrow unknown.
3. Draft one conditional hypothesis with an observable falsifier.
4. State the evidence boundary, alternative explanation, and maximum claim.

Return a useful `draft` even when evidence or scope is incomplete. Mark assumptions and the next most valuable check. Ask only when a missing decision would materially change the object, claim, safety boundary, or authorized external action.

Accept an `evidence-dossier.json`, reviewed source notes, measurements, a project brief, or an equivalent traceable evidence set. Reuse reliable prior audit work. For unreviewed sources, qualify the draft and suggest `audit-research-evidence`; do not force that detour for a bounded exploratory task.

## Keep levels distinct

Read [references/research-layers.md](references/research-layers.md) when the discussion mixes evidence, gap, question, hypothesis, mechanism, and experiment. Park implementation ideas as candidate mechanisms. A question and hypothesis should remain meaningful after removing a favored mechanism's name.

Derive a gap from a missing evidentiary connection, unresolved boundary, conflict, or untested transfer. Freeze only the object, unit, population, context, outcome, time horizon, boundary, and claim ceiling needed for the current questions.

Write each hypothesis as:

`prior evidence → warranted inference → unresolved gap → conditional hypothesis → observable falsifier`

Separate mechanism, measurement validity, decision value, economics, and external validity when they require different evidence. Leave metric thresholds, sampling, statistics, runtime, and execution to experiment design.

## Scale review with risk

For consequential, multi-hypothesis, disputed, or publication-facing work, read [references/adversarial-review.md](references/adversarial-review.md). Challenge evidence dependencies, population and denominator alignment, construct validity, measurement disturbance, alternative explanations, temporal leakage, and claim ceiling.

## Package the result when useful

Create `hypothesis-brief.json` according to [references/hypothesis-brief.md](references/hypothesis-brief.md), optionally with a readable projection. A small task may return an equivalent question-and-hypothesis card with evidence locators, falsifier, and boundary.

Run:

```bash
python3 scripts/validate_hypothesis_brief.py hypothesis-brief.json
```

Warnings identify open scientific work. Freeze only after the included questions, hypotheses, evidence references, and blockers match the intended downstream use. Provide the brief to `design-research-experiments` or any other task that needs a bounded hypothesis; equivalent inputs remain acceptable downstream.
