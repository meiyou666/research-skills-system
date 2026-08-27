# Evidence Dossier Contract

Use JSON for durable or cross-skill work. Keep domain extensions under `extensions`.

## Core fields

- `schema_version`: integer `1`;
- `dossier_id`, `version`, and `status` (`draft` or `frozen`);
- `purpose`: claim or decision being audited;
- `source_inventory`: upstream package ID and SHA256, an embedded inventory, or an equivalent-input provenance note;
- `source_records`: reviewed primary-source records;
- `evidence_statements`: bounded direct, source-claim, inference, or unknown statements;
- `conflicts`: unresolved or explained conflicts and source-dependency clusters;
- `coverage_limits`: access, search, population, method, and transfer limits;
- `extensions`: optional domain fields.

`purpose`, `source_inventory`, and a statement `boundary` may be non-empty text or a non-empty
structured object/list when the domain needs several dimensions. `source_inventory` may therefore
identify an upstream package and SHA256, embed an inventory, or record equivalent-input
provenance. Opaque truthy scalars are not valid provenance or claim boundaries. Draft omissions
remain review warnings; a frozen dossier requires purpose, provenance, and every boundary.

## Source record

Give each record a stable `id`, textual `locator`, version or date when known, `access_level`, research object, population, method, directly relevant result, and limitations. Record denominators and uncertainty when the audited claim depends on them; otherwise retain a clear warning rather than inventing values.

Use this closed `access_level` enum to describe what the audit actually inspected:

| Value | Audited access | Permitted use |
| --- | --- | --- |
| `V0` | Discovery material such as metadata, snippets, generated summaries, news, or recommendations | Locate a candidate only; do not support a scientific claim |
| `V1` | Source abstract | Support only a narrow statement explicitly present in that abstract |
| `V2` | Relevant partial primary content | Support a provisional claim limited to the inspected primary sections |
| `V3` | Primary methods, results, population, relevant figures/tables, and limitations reviewed | Support a bounded claim within the reviewed method and population |

Collection-system values such as `public_metadata_api`, `public_feed`, or
`full_text_candidate` describe acquisition, not dossier access. Map them conservatively from the
content actually reviewed; a full-text candidate is not `V3` until the needed primary sections
have been inspected.

## Evidence statement

Require `id`, `text`, `label`, `source_ids`, and `boundary`. An `INFERENCE` names at least one source and explains its reasoning in `reasoning`. An `UNKNOWN` may have no supporting source but states the inspected scope.

`frozen` means these records and statements were reviewed for the stated purpose. It is not a declaration that the wider literature is complete.
Before freeze, preserve source-inventory or equivalent-input provenance and a boundary for every
statement. A `V0` discovery record may remain in the dossier to document a gap, but it cannot be
the supporting source for `DIRECT`, `SOURCE_CLAIM`, or `INFERENCE`.
