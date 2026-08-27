# Evidence Search and Coverage Audit

Use this procedure before treating a source collection as the state of research. The objective is an inspectable coverage claim, not a claim of exhaustive discovery.

## Choose a mode

- **Open search:** Treat supplied sources as seeds and search beyond them.
- **Bounded corpus:** Use only a user-declared corpus for substantive conclusions. Qualify every synthesis to that corpus.
- **Search update:** Preserve the prior protocol and cutoff, then search new records, versions, corrections, and retractions.

Record the mode and any later transition. A transition creates a new coverage version.

## Define the search boundary

Record before searching:

- research object and population;
- exposure, intervention, mechanism, or comparison;
- processes and intermediate states;
- outcomes and measurement families;
- methods and adjacent technical traditions;
- time, language, geography, and source-type limits;
- inclusion and exclusion criteria;
- contrary propositions and alternative explanations;
- search date and evidence cutoff.

## Select complementary entry points

Use entry points with different collection mechanisms where the field supports them:

1. cross-disciplinary scholarly indexes;
2. field-specific databases, registries, or standards indexes;
3. official publisher, society, venue, regulator, or statistics pages;
4. preprint and institutional repositories;
5. data, code, protocol, and supplementary-material repositories;
6. backward and forward citation graphs;
7. author or research-group publication records; and
8. general web search for discovery.

Record the actual service and filters used. Return discovery hits to the source-owning page or artifact before using them as evidence.

When a collection campaign already supplies canonical identifiers, version clusters, query logs, content scopes, and access gaps, preserve those fields. Add scientific screening decisions alongside them instead of rewriting collection history. A collection task marked `complete` means only that its configured bounds terminated; it does not establish search saturation.

## Build a vocabulary map

For each concept face—object, exposure, mechanism, outcome, method, boundary, and contrary proposition—record:

- canonical terms;
- synonyms and near-synonyms;
- abbreviations and expansions;
- former and current names;
- broader and narrower terms;
- spelling, language, and regional variants;
- terminology used by adjacent research traditions; and
- ambiguous terms and disambiguators.

Expand the map from controlled vocabularies, seed papers, related-work sections, and newly screened records. Version queries when the vocabulary changes.

## Execute query families

For each core question, run and log:

- direct queries combining object, condition, and outcome;
- mechanism or intermediate-state queries;
- nearest-work queries matching the full target tuple;
- boundary queries for different populations, settings, and scales;
- contrary queries for null, failure, conflict, non-replication, and alternative explanations; and
- record-status queries for corrections, withdrawals, comments, and later versions.

Keep at least one query free of the favored mechanism name. Log the complete query string, service, filters, sort order, screened window, date, and result disposition.

## Find the nearest work

Compare candidates on:

`object × condition or mechanism × method × outcome × scale`

Start with all dimensions fixed, then relax one dimension at a time. For highly relevant records, trace references, citations, versions, supplements, data, code, replications, comments, and corrections. Record the exact remaining difference; title similarity and citation count are insufficient.

## Search for contrary evidence

Search concurrently for null results, opposite effects, method failures, false positives and negatives, non-replication, conflicting populations, alternative mechanisms, and registered studies with divergent outcomes. Rewrite the central claim as a contrary proposition instead of relying only on words such as `failure` or `limitation`.

Apply relevance criteria before recording result direction. Never screen a record out because its result challenges the working hypothesis.

## Screen and verify

Use two stages:

1. screen title and abstract for relevance;
2. inspect the primary content to establish what claim it can support.

Record every candidate, version relation, decision, and exclusion reason. Check object, population, denominator, conditions, method, outcome, independence, official status, corrections, and access level.

Use these access levels:

| Level | Evidence use |
| --- | --- |
| `V0 discovery` | Result snippets, generated summaries, news, and recommendations locate candidates only. |
| `V1 abstract` | Support only a narrow statement explicitly present in the source abstract. |
| `V2 partial` | Support a provisional claim limited to the inspected primary sections. |
| `V3 primary` | Methods, results, population, figures or tables, and limitations have been checked. |

Map collection scopes conservatively: `metadata` and `discovery_snippet` remain `V0`; `abstract` may reach `V1`; `partial_content` may reach `V2` only after the relevant primary section is actually inspected; `full_text_candidate` is not `V3` until a human or agent has reviewed the needed methods and results.

When full text is unavailable, try the official page, accepted manuscript, institutional repository, preprint, supplements, data, and code, or ask the user for authorized access. Record attempts. Do not bypass access controls.

## Stop and declare coverage

Declare saturation within the recorded scope only when:

1. mode, boundary, criteria, and cutoff are recorded;
2. complementary entry points and principal terminology are covered;
3. nearest-work and contrary-evidence searches are complete;
4. independent seeds have backward and forward tracing;
5. duplicates, versions, screening decisions, and exclusions are recorded;
6. two independent expansion rounds add no source that changes a central synthesis, boundary, or nearest-work ordering; and
7. no unverified key source is likely to change a central claim.

Otherwise declare constrained coverage and list the unsearched entry points, inaccessible records, language or time limits, and likely omission risks.

Maintain three tables: a search protocol, a query log, and a candidate-source ledger. Any statement about absence, novelty, or nearest work must trace to all three.
