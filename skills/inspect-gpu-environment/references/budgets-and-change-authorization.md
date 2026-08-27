# Budgets and change-authorization boundary

## Optional planning inputs

The collector accepts all planning inputs independently:

| Input | CLI option | Unit |
|---|---|---|
| Requested GPU count | `--gpu-count` | devices |
| Requested CPU count | `--cpu-count` | logical CPUs |
| Expected duration | `--duration-hours` | hours |
| Requested disk | `--disk-gb` | decimal GB |
| Hourly cost ceiling | `--hourly-cost-cap` | currency/hour |
| Total cost ceiling | `--total-cost-cap` | currency |
| Cost unit | `--currency` | operator-defined, normally an ISO currency code |

Missing inputs remain `unavailable` and never block collection. The default document status is
`draft`, which is appropriate for a partial brief. Pass `--attestation-status complete` only
after a human or calling workflow has reviewed scope and evidence; “complete” does not convert
missing telemetry into observed facts.

`hourly_cap_times_duration` is a conservative arithmetic product of two reported ceilings, not
a provider price quote. `within_total_cost_cap` compares that product with the reported total
ceiling. Keep currency/accounting units consistent. Provider fees, storage, egress, taxes,
commitments, spot interruption, and idle time require separate cost evidence.

Compare requested counts/capacity with observations explicitly. Do not infer that two visible
GPUs are interchangeable, connected suitably, available for exclusive use, or within budget.

## Optional reproducibility inputs

- `--project-root` enables Git revision, tracked-dirty state, and root-level lockfile hashing.
- Repeat `--lock-file` for additional project-contained dependency files.
- `--container-image` records a reported mutable reference.
- `--image-digest` records a reported immutable OCI-style digest; it does not independently
  prove which image is running.
- `--container-runtime` and `--target-label` are reported labels, not observations.

Never put access tokens, passwords, private registry credentials, signed URLs, or cloud keys in
these arguments. The collector captures only an explicit device-selection environment allowlist.

## Default read-only boundary

Inspection may identify a change that could improve fit, but this skill does not perform it.
Create a separate proposed-action list with rationale, target, rollback, validation, and expected
impact. Request explicit authorization for that list before using a change-capable workflow.

Separate authorization is required for:

- driver, firmware, kernel-module, CUDA/ROCm runtime, or system-package installation/removal;
- host reboot, service/daemon changes, kernel boot arguments, or device permission changes;
- power-limit, clock, performance-level, fan, or persistence/compute-mode changes;
- MIG enable/disable, GPU/compute instance creation/deletion, AMD partitioning, reset, or SR-IOV;
- storage formatting/mount changes or container/image replacement.

Authorization to inspect is not authorization to mutate. If the user authorizes a later change,
use a separate procedure and take a fresh before/after attestation; do not add mutation commands
to this skill's collector.
