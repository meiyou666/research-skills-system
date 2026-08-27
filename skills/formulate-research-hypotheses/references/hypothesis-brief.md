# Hypothesis Brief Contract

Use JSON for durable or cross-skill work. Keep domain extensions under `extensions`. A readable Markdown projection is optional.

## Core fields

- `schema_version`: integer `1`;
- `brief_id`, positive `version`, and `status` (`draft` or `frozen`);
- `purpose`: intended downstream decision or study;
- `evidence_input`: dossier ID and SHA256, embedded evidence statements, or an equivalent-input provenance note;
- `evidence_statements`: stable IDs and bounded statements used by this brief; every record uses
  a non-empty `text` field for the statement itself;
- `gap`: established capability, unresolved connection, scope qualifier, and claim ceiling;
- `research_object`: unit, population, context, conditions, outcomes, horizon, and boundaries;
- `questions`: answerable question records;
- `hypotheses`: falsifiable hypothesis records;
- `adversarial_review`: objections and unresolved blockers when review was proportionate;
- `approval`: approval evidence for a frozen brief;
- `extensions`: optional domain-specific fields.

## Question record

Use a stable `id`, the `question`, optional `rationale`, `observables`, and `depends_on`. Express one principal unknown when practical; record linked unknowns explicitly when the domain requires them.

`depends_on` contains bare IDs local to this brief. For a question, the allowed ID namespaces are
`evidence_statements[*].id` and `questions[*].id`; self-dependencies and external IDs are invalid.
For a hypothesis, the allowed namespaces are `questions[*].id` and `hypotheses[*].id`; use
`prior_evidence_ids` for evidence dependencies. Forward references within the same brief are
allowed. Keep IDs unique across evidence, question, and hypothesis records so a bare reference is
unambiguous, and keep each question or hypothesis dependency graph acyclic. Omit `depends_on`
while a draft has no dependency to record; do not add placeholders.

## Hypothesis record

Use a stable `id`, `statement`, `prior_evidence_ids`, `falsifiers`, and `depends_on`. Add rationale, claim ceiling, alternative explanations, and retained learning when useful for the task risk.

Do not place selected tests, sample sizes, infrastructure endpoints, credentials, or remote paths in this brief.

## Evidence statement record

Use a stable non-empty `id` and a non-empty string `text`. Keep optional source IDs, label,
boundary, and provenance fields from the upstream dossier when available. Do not substitute
`statement`, `claim`, or a display label for `text`; downstream hypothesis references use the
evidence record's `id`.

## Adversarial review object

When proportionate review is performed, encode `adversarial_review` as an object, never a list:

```json
{
  "objections": [
    {
      "id": "O1",
      "affected_claim_ids": ["H1"],
      "objection": "A competing explanation remains viable.",
      "evidence_dependency": "E1 and the population boundary",
      "severity": "NARROWING",
      "resolution_needed": "Bound the claim to the observed population.",
      "status": "OPEN"
    }
  ],
  "unresolved_blockers": []
}
```

Use severity `BLOCKING`, `NARROWING`, or `INFORMATIVE`, and status `OPEN`, `RESOLVED`, or
`ACCEPTED_RISK`. A frozen brief cannot contain a `BLOCKING` objection whose status is anything
other than `RESOLVED`; `ACCEPTED_RISK` does not resolve a blocking objection.

Every `affected_claim_ids` entry is a bare ID of an evidence statement, question, or hypothesis
in the same brief. The validator checks these references; it does not decide whether the reviewer
identified every scientifically affected claim.

`unresolved_blockers` is an optional denormalized summary of objection IDs. It may also contain
standalone non-empty strings or concise objects containing `id`, `text`, or `description`. Objection
records are authoritative for matching IDs, so agents do not need to duplicate each blocker in
this summary. The validator reports disagreement between a matching summary ID and objection
state as a warning. An unmatched summary entry explicitly declares a standalone unresolved blocker
and therefore still prevents freeze.
Omit the whole review object when adversarial review was not proportionate; do not use an empty
array as shorthand for the object.

## Freeze semantics

`frozen` means the included scope, questions, hypotheses, evidence references, and blockers were accepted for the declared use. It does not certify scientific truth or search completeness. Record the file SHA256 at downstream intake instead of creating a self-referential hash.
