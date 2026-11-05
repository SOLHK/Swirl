# C1 reconstruction infrastructure: audit and production boundary

## Scope and evidence

Audit baseline: `e505326486202ad4c8e98bb8b66a17b4547c559f`, read from the
remote integration branch before creating `work/vf-rebuild-c1`.
This document concerns the independent C1 infrastructure work. It does not
change the already verified HVF hierarchy, tangent, rotation, or batch geometry
algorithms. `rebuild.py`, `hvf.py`, and `coretext_extract.swift` remain shared
entry points; this branch's C1 work does not patch them without owner approval.

The handoff's 1,088/1,088 and 26,780/26,780 bounded geometry results are prior
evidence. They are not C1 executions, all-GID coverage, production mapping
acceptance, or Windows acceptance. The exact Apple source was not present in
this C1 local workspace. The tests below generate independent geometric font
fixtures from source code in temporary directories. No Apple outlines, private
fonts, or private derivative files are checked in.

## Existing converter inspection

| Area | Observed mechanism | C1 implication |
| --- | --- | --- |
| GIDs and character map | The original glyph order is assigned before rebuilding every GID; saved `cmap` bytes must match the source | Preserve the physical index and every encoded or unencoded GID; never infer completion from only the cmap |
| Geometry | `reconstruct_glyph` reuses compatible path conversion, explicit topology and shared variation modelling | Retain this implementation and its failure conditions; C1 adds storage and scheduling around it |
| Sampling | Training, independent holdouts, named instances and raw avar knots are checked; adaptive promotions add fresh holdouts | A completed observation or sampled model is not a proof over the continuous source space |
| Metrics | Explicit origins become four phantoms; non-representable vertical X origins are rejected | B1 remains a hard blocker; no uniform origin correction is introduced |
| HVAR and VVAR | Rebuilt advance coefficient maps are checked exactly against gvar phantoms | This is equality between standard encodings; it does not repair a native CoreText disagreement |
| VORG | Removed after expanded glyf/phantom construction | Source vertical semantics still require native B1 evidence; VORG cannot represent a missing independent vertical X origin |
| Serialization | Every decoded outline, topology, phantom and complete gvar coefficient is checked after save/reopen | Keep exact coefficient checks in addition to structural validity |
| TTC packing | All serialized face-table bytes are compared, except `head.checkSumAdjustment` | The same comparison must remain after streaming packaging; no GID renumbering |
| Naming and region mapping | `rename_face` replaces identity names using physical face-index groups, preserving other labels | Bind the original face index and metadata rather than sorting faces by display name |
| Layout | GSUB/GPOS/BASE top-level variable stores and FeatureVariations are rejected before identity avar replacement | There is a demonstrated missing GDEF-linked case; see below |
| Existing checkpoints | Whole-face checkpoints bind source, code, dependency versions and completed native session proof | Useful existing safeguards, but no partial-face recovery and no concurrent-writer lease; see below |
| Existing memory | All rebuilt glyph objects remain live for the active face; FontTools shared-table packing caches complete table bytes | C1 bounds batches and TTC copying; it must state separately that compiling one whole face is not yet a proven fixed-memory operation |

The existing `retained_aat_behavior_windows=NOT_VERIFIED` declaration remains
material. Retaining AAT table bytes does not establish that DirectWrite, Qt or
Swirl apply the same shaping behavior.

## Reproduced shared-entry defect 1: indirect GDEF variation store

`test_reproducer_unremapped_gdef_changes_layout_after_shared_rebuild` creates a
three-GID, three-axis original analytic font. It adds:

1. A non-identity `avar` segment that maps normalized wght 0.5 to 0.25.
2. A GDEF 1.3 `VarStore` containing a 100-unit advance delta on wght.
3. A GPOS single-positioning `VariationIndex` referring to that store.

The unchanged `rebuild.run` is then executed using the established explicit
synthetic oracle double. All existing reconstruction and serialization gates
execute. It returns `RECONSTRUCTION_SAMPLED_PASS_PLATFORM_UNVERIFIED`.
At the same user request `WDTH=500, wght=700, HGHT=500`, the referenced layout
variation is **25 units in the input and 50 units in the output**. The input
bytes remain unchanged. This is a real layout-semantic counterexample on an
original fixture, not a measurement of the Apple font.

Cause: the current admission loop examines GSUB, GPOS and BASE top-level
stores, but does not examine `GDEF.VarStore`. A GPOS `VariationIndex` can refer
indirectly to that store. Copying its bytes while replacing avar changes its
effective user-coordinate function.

**Proposed shared patch, requiring coordinator approval:** extend source
preflight to reject any retained GDEF variation store before sampling until an
independent remapping strategy is implemented. The narrow first patch is to
include GDEF in the existing top-level variation-store admission guard. Keep
an explicit regression containing the indirect GPOS reference. Later support
must preserve the normalized coordinate semantics of every retained store;
passing an identity-byte check alone is insufficient.

No shared patch is applied in C1. The committed reproducer deliberately asserts
the current limitation. Its passing test result means **the defect is
reproduced**, not fixed, waived, or accepted for production.

## Reproduced shared-entry defect 2: stale whole-face manifest writer

`test_reproducer_shared_checkpoint_stale_writer_drops_prior_index` creates two
instances of the existing `FaceCheckpoints` class against the same empty
directory. Both hold the same initial manifest snapshot. The first saves a
complete original synthetic face 0. The second saves complete face 1 using its
older snapshot. Both serialized face files survive, but the final
`verified-faces.json` contains only face 1: face 0's confirmed recovery entry is
lost. This deterministic interleaving needs no timing-dependent thread test.

The two test transcripts are explicitly synthetic; the test concerns storage
transactions and does not claim native platform validation.

**Proposed shared patch, requiring coordinator approval:** add one exclusive
writer lease spanning manifest read, face publication and manifest update;
re-read and validate the recipe and previous accepted records under that lease.
Alternatively, retain an immutable per-face commit log and reconstruct the
index from accepted commits. A plain `os.replace` makes one file replacement
atomic but does not prevent a stale writer from replacing newer state. Reject
concurrent or stale writes rather than silently clearing accepted entries.

C1's new storage implementation is independent of this mutable manifest.
Do not re-use the legacy class as a partial-batch transaction manager. The
existing shared code is left unchanged and the open limitation is recorded.

## Typed failures and public-safe reporting

`ttc_staging_contract.py` defines six source categories: `input_axis`,
`metrics`, `outline`, `serialization`, `platform_read`, and `font_tables`.
They describe a failure's cause, not a policy for skipping it. A failed item
must keep its face/GID/range identity and must never increase completion.

`StagingError` exposes `category`, fixed `code`, and a filtered `context`.
Reports retain whitelisted finite numeric identifiers, SHA-256 digests,
four-character table/axis tags and fixed stage names. Arbitrary exception
strings, paths, glyph names, native commands and unknown payload fields are
discarded. Local private batch data and public failure reports are distinct.

## Read-only production preparation command

```sh
python tools/swirl_vf/platform/rebuild_c1_preflight.py --source /private/PingFangUI.ttc
```

The source profile is fixed to SHA-256
`39d42acd292ed5c9de5cf185b54a3c460630d610a718ed84c9e4f148e226f890`,
61,473,880 bytes, 32 physical faces, 47,102 GIDs per face and original axis
tags/order `WDTH`, `wght`, `HGHT`. The exact hash binds the original axis
definitions and raw avar/name/cmap/layout records; no dictionary normalization
of original avar is performed. The command inventories metadata only after
the exact source identity matches, then rechecks that identity after reading.

The command always returns **BLOCKED / exit 2** at this checkpoint, even when
the source identity and metadata checks pass. A3 and B1 accepted production
interfaces are not integrated. There is no `accepted=true` evidence-file
argument and no tolerance override that can grant production admission. The
report separates `physical_faces_checked` from `reconstructed_faces` (zero),
and keeps production permission, font generation and acceptance false.

This command was tested with independent synthetic and malformed inputs and
mocked identity responses, including a source changing during inspection.
It was not run against the absent private Apple source. A source metadata
inventory is never described as completed reconstruction or platform testing.

## Primary references inspected

- [FontTools 4.61.1 TTCollection implementation](https://github.com/fonttools/fonttools/blob/4.61.1/Lib/fontTools/ttLib/ttCollection.py): physical-face list, lazy access and shared-table serialization. The GitHub source was fetched; the installed matching library's `TTFont._writeTable` was also read to inspect the full-byte cache keys.
- [FontTools 4.61.1 TTFont implementation](https://github.com/fonttools/fonttools/blob/4.61.1/Lib/fontTools/ttLib/ttFont.py): dependency ordering and table-cache behavior. Existing FontTools APIs are reused; no upstream implementation is copied into C1.
- [OpenType file and collection structure](https://learn.microsoft.com/en-us/typography/opentype/spec/otff): TTC offsets, table alignment/checksums, shared tables and GID-renumbering implications.
- [OpenType variation overview](https://learn.microsoft.com/en-us/typography/opentype/spec/otvaroverview): normalized coordinate semantics and variation data in tables other than glyf/gvar.
- [OpenType GDEF](https://learn.microsoft.com/en-us/typography/opentype/spec/gdef): GDEF variation stores and positioning references.

The final C1 handoff records the exact new source commits, complete test counts
and actual CI outcomes. This audit does not convert queued or unrun checks
into a pass, and does not authorize `Swirl-VF.ttc` production publication.
