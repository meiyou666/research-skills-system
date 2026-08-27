# High-Assurance Finalization

Use this extension for sensitive, durable, delegated, long-context, or explicitly auditable delivery. Retain the core decision rule from `SKILL.md`.

## Establish boundaries

Treat this as a prompt-level mitigation. Verify host activation, context isolation, script access, final-surface visibility, and readback independently. State a material limitation before mutation when a required surface cannot be protected or inspected.

Choose an authoritative baseline per surface: the starting repository state for repository changes, a released artifact for release claims, or a user-approved artifact for editorial work. Temporary assistant drafts are working history. Executed sends, publications, uploads, deletions, migrations, and partial failures remain audit facts.

## Protect sensitive information

Classify credentials, personal data, confidential names, and related facts by audience and destination. Use the least revealing accurate statement. Obtain direction before placing an exact sensitive value on a durable surface when accuracy, law, or audit requires it.

Keep raw sensitive values out of producer and validator prompts, command lines, visible traces, and the bundled scanner's term file. Use an authorized secret or DLP facility for deterministic sensitive-data checks.

## Isolate production

For strongly primed or delegated work, create a production specification containing only:

- positive target;
- accepted baseline and observed-state facts;
- required facts and audience per surface;
- final formats and permitted files.

Use a genuinely fresh producer when the host can prove absence of inherited conversation, summary, memory, and narrative handoff. Otherwise generate from the positive specification in the current context and label isolation as best effort. Give downstream producers the same specification.

## Freeze and read back

1. **Preflight:** Render and freeze every available surface. Record audience and baseline. Check direct terms, semantic residue, wrappers, task preservation, and unrelated changes.
2. **Mutation:** Use the frozen content unchanged for the authorized commit, publication, send, release, or pull request.
3. **Readback:** Read the resulting artifact and metadata, including hook- or platform-modified surfaces where accessible.
4. **Postflight:** Recheck every readable surface. Draft the exact handoff from readback, validate it, and send it unchanged.

Any later surface change invalidates the earlier check. With `check_surface.py`, pass `--root` when root-relative paths are in scope. Inspect suspicious Unicode and semantic paraphrases manually.

For media, validate pixels, audio, subtitles, or embedded metadata with an appropriate tool before claiming inspection of that modality.

## Validate independently

When a provably fresh validator is available, provide frozen surfaces, non-sensitive session-only alternatives, required facts, audiences, and baseline classes. Request structured `PASS` or violation codes and no mutations. Keep sensitive values in trusted deterministic checks.

Validate both residue control and task preservation. On preflight failure, revise and rerun the full preflight. After two unsuccessful repair rounds with material ambiguity, pause the durable mutation and request direction. On postflight failure, repair within existing authorization, read back again, and report any state that cannot be repaired or inspected.
