---
name: design-research-experiments
description: Turn a hypothesis, question, or equivalent research brief into a proportionate experimental design with comparisons, variables, measurements, analysis choices, decision rules, stopping conditions, and—when needed—data and execution contracts. Use for preregistration, pilot design, confirmatory planning, identifiability review, or preparing an executable study handoff. Produce useful drafts from incomplete inputs and do not run experiments.
---

# Design Research Experiments

Design the smallest study that can produce an interpretable update to the stated question. Preserve freedom to choose domain-appropriate methods, tools, statistics, and presentation.

## Take the shortest useful path

1. Restate the question or hypothesis and its observable falsifier.
2. Define the unit, comparison, outcome, and measurement window.
3. Identify the strongest confounder or validity threat and one control.
4. Draft the decision states and the next feasibility check.

Return a `draft` protocol with visible assumptions when inputs are incomplete. Ask only when a choice would materially change the research object, interpretation, safety, ethics, resource authorization, or external action.

Accept a frozen hypothesis brief, a user-stated hypothesis, a protocol revision, pilot observations, or an equivalent research specification. Reuse reliable existing definitions and record provenance. Suggest upstream evidence or hypothesis work only when its absence prevents an interpretable design.

## Scale the design with risk

For a small exploratory task, keep a compact design card. For confirmatory, expensive, adaptive, safety-relevant, multi-arm, clustered, longitudinal, or publication-facing work, read [references/protocol.md](references/protocol.md) and [references/statistical-design.md](references/statistical-design.md).

Choose controls, randomization, blocking, blinding, sampling, models, intervals, multiplicity handling, and sensitivity analyses from the domain and estimand. Separate exploratory from confirmatory analyses, construct checks from target outcomes, and scientific decisions from operational failures.

Predeclare support, rejection, boundary, and inconclusive states. Treat invalid instruments, corrupt data, contract deviations, and insufficient sensitivity as validity or execution outcomes, not as hypothesis falsification.

For GPU kernels, training, inference, reliability, or scaling studies, read [references/gpu-measurement.md](references/gpu-measurement.md). Freeze timing and synchronization boundaries, warm-up and compilation state, raw observation granularity, device/environment identity, telemetry expectations, and metric formulas. Select profilers and statistical methods by capability and question.

## Add handoff contracts when needed

Read [references/data-contract.md](references/data-contract.md) when measurements cross tools, agents, machines, or time. Specify stable IDs, units, raw/derived boundaries, provenance, integrity checks, and reproducible transformations without forcing irrelevant fields.

Read [references/execution-contract.md](references/execution-contract.md) when another system will run the study. Freeze code identity, run cells, seeds where applicable, entrypoint, progress, completion validation, runtime and safety bounds, recovery semantics, and required raw artifacts. Use relative logical paths; let the executor create a separate endpoint binding.

## Package and validate

A compact task may produce only `experiment-protocol.json` or an equivalent design card. A durable execution handoff commonly adds:

```text
experiment-design/
  experiment-protocol.json
  data-contract.json
  execution-contract.json
  decision-register.md
```

Run the mechanical validator on a JSON protocol or package directory:

```bash
python3 scripts/validate_experiment_package.py PATH
```

Warnings indicate optional or scientific work for agent review. Freeze only the artifacts needed for the declared use. Provide them to an execution system such as `supervise-experiment-runs`, or use the design independently. This skill does not connect to infrastructure, run the study, interpret collected results, draw figures, or revise a report.
