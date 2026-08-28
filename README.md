# Composable Research and GPU Experiment Skills

This repository contains small, interoperable Agent Skills for evidence-led research and practical GPU experiments. It covers GPU kernels and microbenchmarks, training, inference, reliability or fault-injection studies, single- or multi-device work, local or SSH execution, and bare-metal or container environments without binding the core interfaces to a model, framework, vendor, or project.

Each skill has its own trigger, accepts equivalent inputs, produces useful drafts from partial material, and scales its checks with the task's risk. The modules can be used alone or combined.

## Capabilities

| Skill | Primary input | Primary output | Completion boundary |
| --- | --- | --- | --- |
| [`collect-research-sources`](skills/collect-research-sources/SKILL.md) | topic, query plan, seed locators, or prior campaign state | resumable SQLite state, candidate inventory, query log, snapshots or references, and failure/gap report | lifecycle status and collection outcome are distinct; every configured task is terminal or explicitly resumable, and hashes, provenance, limits, and observed gaps are consistent |
| [`search-primary-evidence`](skills/search-primary-evidence/SKILL.md) | topic, question, seed source, or prior search | candidate inventory or `search-package.json` | searched scope, source provenance, access limits, and stopping rationale are explicit |
| [`audit-research-evidence`](skills/audit-research-evidence/SKILL.md) | source set, citations, or search package | evidence cards or `evidence-dossier.json` | bounded claims trace to reviewed sources and preserve population, denominator, and access limits |
| [`formulate-research-hypotheses`](skills/formulate-research-hypotheses/SKILL.md) | evidence dossier or equivalent traceable observations | question-and-hypothesis card or `hypothesis-brief.json` | the research object, questions, falsifiers, and claim ceiling are explicit for the intended use |
| [`design-research-experiments`](skills/design-research-experiments/SKILL.md) | hypothesis, question, or research brief | protocol and optional data/execution contracts | comparisons, measurements, decision states, and relevant handoff invariants are explicit |
| [`inspect-gpu-environment`](skills/inspect-gpu-environment/SKILL.md) | local or SSH-accessible Linux environment and optional budget/project inputs | read-only GPU environment attestation | observed capabilities, unavailable fields, code/environment identities, and mutation boundaries are explicit |
| [`supervise-experiment-runs`](skills/supervise-experiment-runs/SKILL.md) | execution contract or equivalent approved run specification plus local/SSH binding | byte-verified raw result bundle and private campaign state | the declared completion check passes and collected bytes match the execution-host manifest |
| [`analyze-experiment-results`](skills/analyze-experiment-results/SKILL.md) | verified result bundle or equivalent traceable measurements | derived tables, metric dictionary, statistics, bad cases, and bounded findings | lineage, denominators, statuses, uncertainty, and analysis boundaries are explicit |
| [`create-publication-figures`](skills/create-publication-figures/SKILL.md) | machine-readable data and figure intent/specification | reproducible PDF, SVG, PNG, and figure manifest | file integrity and mechanical QA pass; visual and scientific warnings are reviewed |
| [`revise-evidence-report`](skills/revise-evidence-report/SKILL.md) | existing evidence-backed report and available sources/figures | revised Markdown, self-contained HTML, PDF, and delivery evidence | accepted revisions, evidence checks, conversion, and final visual QA are complete |
| [`no-negative-echo`](skills/no-negative-echo/SKILL.md) | accepted state and final release surfaces | inspected, read-back release bundle and handoff | required facts remain while session-only residue is absent from every checked surface |

## Why these boundaries

Internet collection, evidence search, and evidence interpretation change for different reasons. Collection owns bounded fan-out, acquisition, canonical identities, resume state, and byte provenance; search owns question-driven vocabulary, scientific screening, contrary propositions, and coverage judgment; audit owns what inspected primary content actually supports. Any of the three can consume a reliable equivalent input or run independently. Research framing decides what is worth testing; experiment design decides how to test it. GPU inspection proves observed environment capabilities without taking ownership of deployment mutation. Run supervision preserves an approved execution contract, lifecycle evidence, and raw bytes. Result analysis owns derived evidence before figure creation and report revision. Figure creation owns reproducible graphics, while report revision owns narrative integration and delivery QA. The finalization gate applies across every durable surface.

These seams keep each module independently useful and make handoffs inspectable without constraining domain methods.

## Common composition

The arrows below show compatible artifacts, not a required workflow. Enter at any module whose input is already reliable and available.

```text
collection campaign → candidate inventory
                         ↓
search package → evidence dossier → hypothesis brief → experiment design

GPU environment attestation + execution contract → supervised run → verified raw result bundle
                                                                    ↓
report delivery ← publication figure bundle ← analysis package

no-negative-echo checks each durable artifact and its release wrapper
```

Examples:

- Collect GPU papers, vendor documentation, repositories, issues, releases, and feeds across several bounded connectors, then hand the inventory to evidence search for scientific screening.
- Audit citations already present in a report, then return directly to report revision.
- Draft a small experiment from a user-stated hypothesis and add data or execution contracts only when a handoff needs them.
- Inspect a GPU host and budget before choosing a run matrix, or use the attestation only for reproducibility evidence.
- Render figures from an existing dataset without using the research-framing modules.
- Supervise an approved local or SSH run specification supplied by another planning system.
- Analyze traceable measurements that were produced outside the bundled supervisor.

The detailed GPU ownership, inputs, outputs, runtime dependencies, backend boundaries, scenario coverage, and actual verification status are recorded in [`docs/gpu-experiment-capability-matrix.md`](docs/gpu-experiment-capability-matrix.md).

## Validation philosophy

Bundled validators check facts that software can decide: syntax, IDs, references, paths, hashes, file properties, status consistency, and declared rendering properties. They report optional or scientific completeness as warnings for agent review. Scientific adequacy, search saturation, experimental validity, visual meaning, and publication suitability remain contextual judgments.

Each `SKILL.md` provides the shortest useful path. Detailed references are loaded for broader claims, expensive or safety-relevant work, durable handoffs, and publication delivery. `agents/openai.yaml` is optional interface metadata; core behavior depends only on `SKILL.md` and relative bundled resources.

## Sources and licensing

The primary-source survey and adoption decisions are recorded in [`docs/open-source-skill-landscape.md`](docs/open-source-skill-landscape.md). The reviewed native installation and bounded smoke-test evidence for SearXNG, RSSHub, and GitHub CLI is recorded in [`docs/third-party-search-runtime.md`](docs/third-party-search-runtime.md). Redistributed third-party material and optional runtime dependencies are recorded in [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).

The repository currently has no project-wide license. The nested MIT license in `skills/no-negative-echo/` applies to the upstream-derived material identified by that skill's notice and provenance records.
