---
name: audit-research-evidence
description: Inspect a supplied or discovered primary-source set, extract traceable claims, align populations and denominators, separate reported results from inference and unreported content, and produce a bounded evidence dossier. Use for source verification, claim audits, conflicting-evidence synthesis, or preparing reliable evidence for research framing. Accept partial or equivalent source inventories and return useful provisional findings.
---

# Audit Research Evidence

Determine what the available primary evidence supports and where its limits lie. Do not select a research direction or formulate hypotheses.

## Take the shortest useful path

1. Identify the claim or decision the user needs checked.
2. Open the primary source sections that bear on that claim.
3. Record the object, population, method, result, denominator, uncertainty, and access level.
4. Return the narrow supported statement, its boundary, and any unresolved verification need.

Start from a `search-package.json`, a `collect-research-sources` inventory, bibliography, source folder, citations in a report, user-supplied papers, or an equivalent source list. Preserve reliable prior screening and state its provenance. Collection metadata, rankings, snippets, and `full_text_candidate` labels identify what to inspect; they do not establish claim support. Ask for help only when access authority, source identity, or an ambiguity would materially change the conclusion.

## Scale with risk

For multi-source synthesis, disputed claims, high-stakes decisions, or novelty support, read [references/source-review.md](references/source-review.md). Audit source status, versions, corrections, method, result tables or figures, source dependencies, denominator alignment, contrary results, and transfer limits.

Use labels consistently:

- `DIRECT`: primary data or an owning source directly reports the claim;
- `SOURCE_CLAIM`: the owning source states it, without independent verification here;
- `INFERENCE`: the dossier derives it from named evidence records;
- `UNKNOWN`: the inspected material cannot establish it.

State unreported content as unreported. Qualify absence and research-status claims to their method sensitivity and audited search coverage.

## Produce a dossier when useful

Create `evidence-dossier.json` according to [references/evidence-dossier.md](references/evidence-dossier.md), optionally accompanied by a readable synthesis. A small task may return an equivalent evidence card with stable source locators and explicit boundaries.

Run:

```bash
python3 scripts/validate_evidence_dossier.py evidence-dossier.json
```

Warnings identify review opportunities; they are not scientific verdicts. Freeze only the records and synthesis actually reviewed for the intended use.

Provide the dossier to `formulate-research-hypotheses`, a report audit, an experiment review, or any task that needs bounded claims.
