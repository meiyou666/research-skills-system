---
name: search-primary-evidence
description: Find and scope primary evidence for a research question while recording search coverage, source provenance, access limits, contrary evidence, and stopping rationale. Use for literature discovery, nearest-work searches, evidence updates, or source-set bias checks. Start from partial topics or seed sources and return a useful candidate inventory without requiring a complete downstream research workflow.
---

# Search Primary Evidence

Build an auditable candidate source set. Preserve room to change databases, discovery tools, terminology, and search tactics for the domain.

## Take the shortest useful path

1. Infer a provisional object, outcome, and boundary from available material.
2. Select two complementary discovery routes appropriate to the domain.
3. Search the direct proposition and one contrary or alternative proposition.
4. Return primary-source candidates with locators, access levels, relevance, and current coverage limits.

Mark the result `draft` when the scope or coverage is still developing. Ask only when a missing choice would materially change the research object, claim boundary, access authority, cost, or external action.

Accept a topic, question, seed paper, project bibliography, prior query log, a `collect-research-sources` candidate inventory, or an equivalent source inventory. Reuse reliable existing discovery work and record its provenance instead of repeating it. Treat collection rankings and snippets as candidate provenance, not inclusion decisions or evidence.

## Scale with claim risk

For a narrow orientation task, stop after a useful, explicitly bounded inventory. For a broad state-of-research, novelty, safety-critical, or high-stakes claim, read [references/search-workflow.md](references/search-workflow.md) and expand databases, terminology, nearest-work comparison, citation tracing, contrary evidence, screening, and saturation checks.

Use official records, primary papers, original datasets, first-party code, standards, and author-owned artifacts for substantive evidence. Use snippets, generated summaries, reviews, and recommendation systems to find candidates, then return to the source-owning artifact.

For a few bounded queries, use the host's available search and source APIs directly. For multi-source fan-out, large or incremental campaigns, resumable acquisition, canonicalization, content hashes, or connector failure accounting, call `collect-research-sources` and consume its inventory. This skill still owns vocabulary strategy, inclusion and exclusion, contrary propositions, and the coverage stopping judgment.

Never claim exhaustive absence. State the searched scope, cutoff, and likely omissions.

## Package the result when useful

Create `search-package.json` using [references/search-package.md](references/search-package.md). A lightweight task may instead return an equivalent table containing source ID, primary locator, relevance, access level, and coverage note.

Run the structural check when producing JSON:

```bash
python3 scripts/validate_search_package.py search-package.json
```

Warnings guide further exploration and do not invalidate a useful draft. Freeze a package only when the recorded scope, source dispositions, and stop rationale match the intended claim risk.

Hand the package or equivalent inventory to `audit-research-evidence`, or use it directly for another task that needs candidate sources.
