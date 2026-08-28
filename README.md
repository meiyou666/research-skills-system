<div align="center">

# Research Skills

**Composable Agent Skills for traceable research, reproducible GPU experiments, and auditable publication workflows.**

[Quick start](#quick-start) · [Explore the 11 skills](#skills-by-responsibility) · [Compose a workflow](#composable-workflows) · [Check GPU support](#gpu-experiment-support) · [Read the docs](#documentation)

</div>

Research Skills is a collection of 11 focused, interoperable [Agent Skills](https://github.com/agentskills/agentskills). Use one for a bounded task or connect several through explicit, inspectable handoffs—from source collection and evidence audit to experiment execution, result analysis, figures, and reports.

Each skill accepts useful partial or equivalent inputs when they are traceable. Its `SKILL.md` gives the shortest useful path; detailed methods, safety guidance, and durable artifact contracts live in progressively loaded `references/`. The core is platform-neutral, while `agents/openai.yaml` supplies optional host metadata.

## Core capabilities

| | |
| --- | --- |
| **Traceable discovery**<br>Run bounded, resumable source collection and question-driven primary-evidence searches with provenance, coverage, and failure records. | **Bounded evidence**<br>Audit primary sources, preserve populations and denominators, and distinguish reported results, inference, and unknowns. |
| **Research framing**<br>Turn available evidence into falsifiable hypotheses and proportionate protocols, data contracts, and execution contracts. | **Supervised experiments**<br>Prove the visible GPU environment, supervise local or SSH runs, classify failures, and collect byte-verified raw results. |
| **Publication delivery**<br>Derive metrics and findings, render reproducible figures, and revise evidence-backed Markdown, HTML, and PDF reports. | **Release integrity**<br>Inspect accepted artifacts, metadata, wrappers, and handoffs with `no-negative-echo` before durable release. |

## Quick start

For collaborators with repository access, clone the repository:

```bash
git clone https://github.com/meiyou666/research-skills-system.git
cd research-skills-system
```

Choose the skill closest to the reliable material you already have. Make its complete directory available to an Agent Skills-compatible host so `SKILL.md` can resolve its relative `references/`, `scripts/`, fixtures, and assets.

For example, give your agent a question and ask it to use the evidence-search skill:

```text
Use search-primary-evidence to find primary evidence for whether the proposed
optimization improves tail latency under sustained inference load. Record
contrary evidence, access limits, searched scope, and a stopping rationale.
Start from the attached paper and repository.
```

Start at any reliable stage: an existing source set can enter at evidence audit, traceable measurements can enter at analysis, and an existing report can enter at revision.

## Skills by responsibility

### Discover and establish evidence

| Skill | Use it to | Main handoff |
| --- | --- | --- |
| [`collect-research-sources`](skills/collect-research-sources/SKILL.md) | Run or resume bounded collection across papers, repositories, standards, vendor docs, issues, releases, and feeds. | Campaign state, candidate inventory, query log, snapshots or references, and recorded gaps |
| [`search-primary-evidence`](skills/search-primary-evidence/SKILL.md) | Search around a research question, including contrary propositions and explicit coverage limits. | Candidate inventory or `search-package.json` |
| [`audit-research-evidence`](skills/audit-research-evidence/SKILL.md) | Inspect primary content and determine exactly what supplied or discovered sources support. | Evidence cards or `evidence-dossier.json` |

### Frame the study

| Skill | Use it to | Main handoff |
| --- | --- | --- |
| [`formulate-research-hypotheses`](skills/formulate-research-hypotheses/SKILL.md) | Define the research object, answerable questions, falsifiable hypotheses, alternatives, and claim ceiling. | Question-and-hypothesis card or `hypothesis-brief.json` |
| [`design-research-experiments`](skills/design-research-experiments/SKILL.md) | Specify comparisons, variables, measurements, analysis choices, decision rules, and stopping conditions. | Protocol plus optional data and execution contracts |

### Prepare and supervise execution

| Skill | Use it to | Main handoff |
| --- | --- | --- |
| [`inspect-gpu-environment`](skills/inspect-gpu-environment/SKILL.md) | Capture a read-only, hash-manifested attestation of the visible Linux host or container environment. | GPU environment attestation and integrity manifest |
| [`supervise-experiment-runs`](skills/supervise-experiment-runs/SKILL.md) | Bind and supervise an approved local or SSH run, retain lifecycle evidence, classify failures, and collect results. | Byte-verified raw result bundle and resumable campaign state |

### Turn results into publication assets

| Skill | Use it to | Main handoff |
| --- | --- | --- |
| [`analyze-experiment-results`](skills/analyze-experiment-results/SKILL.md) | Preserve observation-level lineage while deriving metrics, statistics, bad cases, sensitivity checks, and bounded findings. | Analysis package with tables, metric dictionary, statistics, findings, and manifest |
| [`create-publication-figures`](skills/create-publication-figures/SKILL.md) | Render accessible, reproducible scientific figures from CSV or JSON data and a figure specification. | PDF, SVG, PNG, captions or alt text, QA record, and figure manifest |
| [`revise-evidence-report`](skills/revise-evidence-report/SKILL.md) | Audit and revise an existing evidence-backed report, integrate figures, and perform delivery QA. | Revised Markdown, self-contained HTML, PDF, and delivery evidence |

### Finalize durable surfaces

| Skill | Use it to | Main handoff |
| --- | --- | --- |
| [`no-negative-echo`](skills/no-negative-echo/SKILL.md) | Inspect final prose, code, metadata, wrappers, and handoffs against the accepted state. | Inspected release bundle and read-back handoff |

## Composable workflows

Each skill is independently callable and composes through explicit artifact boundaries. Replace a bundled artifact with a traceable equivalent whenever it satisfies the receiving skill's invariants.

```text
collect ─▶ search ─▶ audit ─▶ formulate hypotheses ─▶ design
                                                        │
inspect environment ───────────┐                        │
                               └──────┬─────────────────┘
                                      ▼
                                  supervise ─▶ analyze ─▶ figures ─▶ revise report

no-negative-echo ─────────────── checks every durable release surface ─────────────▶
```

| Starting point | Useful composition | Result |
| --- | --- | --- |
| A broad GPU research topic | `collect` → `search` → `audit` | A bounded, reviewed evidence set with explicit coverage gaps |
| A reliable hypothesis for a new benchmark | `design` + `inspect` → `supervise` → `analyze` | A protocol, environment proof, verified raw bundle, and bounded findings |
| Existing traceable measurements | `analyze` → `create-publication-figures` → `revise-evidence-report` | Derived evidence, reproducible graphics, and an integrated report |
| A report with questionable citations | `audit-research-evidence` → `revise-evidence-report` | Claims bounded by the inspected sources |
| A host-readiness question | `inspect-gpu-environment` | A standalone environment attestation |

Apply `no-negative-echo` to the final artifacts and release wrappers in any composition.

## GPU experiment support

The GPU-facing skills cover the experiment lifecycle through model-, framework-, profiler-, cloud-, scheduler-, and statistics-tool-neutral contracts.

| Dimension | Supported scope |
| --- | --- |
| Access | Local Linux and SSH-accessible Linux targets |
| Execution view | Bare metal or containers, with host and container evidence kept distinct |
| Device scale | Single- and multi-GPU contracts that preserve device and rank identity before aggregation |
| Study types | Kernels and microbenchmarks, training, inference, simulations, reliability, and fault-injection studies |
| Lifecycle | Read-only environment proof, measurement design, detached supervision, telemetry retention, operational failure classification, byte-verified collection, analysis, figures, and reports |

Backend claims remain tied to recorded evidence:

- **NVIDIA is the current parser and contract baseline.** Fixtures exercise `nvidia-smi` parsing, missing telemetry, and a two-device environment. The repository does not contain direct physical-NVIDIA execution evidence.
- **AMD/ROCm is capability-probed.** `amd-smi`, legacy `rocm-smi`, `rocminfo`, device nodes, and HIP/compiler signals can be recorded; hardware and profiler behavior require target-side verification.
- **Other accelerators can enter through equivalent workload, telemetry, and evidence contracts.** Their adapters and hardware behavior require target-specific proof.

See the [GPU experiment capability matrix](docs/gpu-experiment-capability-matrix.md) for scenario ownership, runtime dependencies, fixture coverage, and validation limits.

## Repository layout

```text
.
├── skills/
│   └── <skill-name>/
│       ├── SKILL.md            # trigger, shortest path, and responsibility boundary
│       ├── references/         # progressively loaded methods and artifact contracts
│       ├── scripts/            # generators, validators, and/or offline self-tests
│       ├── agents/openai.yaml  # optional host metadata
│       ├── fixtures/           # deterministic test inputs, when needed
│       └── assets/             # rendering assets, when needed
├── docs/                       # capability, landscape, and runtime evidence
├── README.md
└── THIRD_PARTY_NOTICES.md
```

## Validation

Run the bundled offline self-tests from the repository root after installing the dependencies named by each skill:

```bash
for test in skills/*/scripts/self_test.py; do
  python3 "$test" || exit 1
done
```

The figure self-test uses Matplotlib, NumPy, and Pillow. Other optional runtime requirements are scoped by the relevant `SKILL.md` and references.

Validate durable handoffs with the validator owned by the producing skill. Examples from the repository root:

```bash
python3 skills/collect-research-sources/scripts/validate_campaign.py campaign-package/
python3 skills/search-primary-evidence/scripts/validate_search_package.py search-package.json
python3 skills/audit-research-evidence/scripts/validate_evidence_dossier.py evidence-dossier.json
python3 skills/formulate-research-hypotheses/scripts/validate_hypothesis_brief.py hypothesis-brief.json
python3 skills/design-research-experiments/scripts/validate_experiment_package.py experiment-package/
python3 skills/inspect-gpu-environment/scripts/validate_attestation.py gpu-environment-attestation/
python3 skills/analyze-experiment-results/scripts/validate_analysis_package.py analysis/
python3 skills/create-publication-figures/scripts/validate_figure_package.py figure-package/
```

Validators check mechanical facts such as syntax, identities, references, path safety, hashes, status consistency, and declared file properties. Warnings surface incomplete or contextual work; they are not scientific verdicts. Evidence adequacy, search saturation, experiment validity, interpretation, and publication suitability still require review.

## Optional runtimes and host metadata

The collection core uses Python's standard library and source-owned interfaces. A caller can add a SearXNG endpoint, an RSSHub-produced feed, or the GitHub CLI adapter for broader discovery. Their access terms, credentials, rate limits, privacy boundaries, and operating costs remain with the caller.

`agents/openai.yaml` is optional presentation metadata. Portable behavior is defined by `SKILL.md` and its relative resources.

## Documentation

| Document | What it establishes |
| --- | --- |
| [GPU experiment capability matrix](docs/gpu-experiment-capability-matrix.md) | Capability ownership, backend boundaries, scenario coverage, dependencies, and verification status |
| [Open-source skill landscape](docs/open-source-skill-landscape.md) | Primary-source survey, adoption decisions, and interface rationale |
| [Third-party search runtime](docs/third-party-search-runtime.md) | Reviewed installation and bounded smoke-test evidence for optional search components |
| [Third-party notices](THIRD_PARTY_NOTICES.md) | Redistributed material, provenance boundaries, optional runtime software, and external-service boundaries |

Each skill's `SKILL.md` is the primary task entry point. Follow its references as the task's scope, risk, or handoff requirements grow.

## Contributing

Changes should preserve the properties that make the skills composable:

- Keep one clear responsibility and completion boundary per skill.
- Accept useful partial or equivalent inputs; require a complete upstream package only when a downstream invariant depends on it.
- Keep the shortest path in `SKILL.md` and move detailed, risk-specific guidance into progressive references.
- Preserve provenance, missing states, failures, and denominators.
- Separate mechanically validated facts from scientific or editorial judgment.
- Keep core contracts platform-, model-, framework-, and vendor-neutral; isolate optional integrations.
- Add or update focused fixtures, self-tests, validators, and documentation whenever a capability or claimed boundary changes.

## License

This repository currently has **no project-wide `LICENSE` file**. Access to the repository does not by itself grant permission to copy, modify, or redistribute its contents.

The MIT license under `skills/no-negative-echo/` applies only to the upstream-derived material scoped by that skill's notice and provenance records. Other redistributed material, optional runtime software, and external services have separate boundaries documented in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
