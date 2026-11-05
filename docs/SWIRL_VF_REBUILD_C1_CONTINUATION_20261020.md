# Swirl-VF C1 continuation: independently verified TTC bytes

## Final verified source and scope

- Branch: `work/vf-rebuild-c1`; repository: `SOLHK/Swirl`.
- Tested source: `75628e3eef45043e88689fd6ee191178ba179622`.
- Tested tree: `47cd5292fc271aed7ac88c8b8557b2c2c14d3bec`.
- Dedicated [CI run 39404296030](https://github.com/SOLHK/Swirl/actions/runs/39404296030)
  finished **completed/success**, all three jobs successful, on 2026-10-20.
  The final run update was 09:57:49 UTC / 17:57:49 Asia/Singapore.
- **Original Apple reconstruction remains 0/32.** Production input and metric
  adapters remain unintegrated; no production `Swirl-VF.ttc` was generated.

This continuation re-read the existing C1 remote HEAD
`b8d10801e60a5b0f00540a060b7bd43efab57995` and the then-current integration HEAD
`bbb79c1e5038d9cfe6b88954094833bae6f7cd4e`. It continued C1 instead of recreating
or resetting it. The inherited 150 C1 tests and infrastructure are described
in [the earlier handoff](SWIRL_VF_REBUILD_C1_HANDOFF_20261020.md); they are not
claimed as new work in this continuation. All writes remained on C1, with
non-forced updates conditional on the previous remote SHA. No integration
merge was performed.

This document is a documentation-only successor to the tested source above.
Do not substitute its later commit SHA for the actual CI checkout SHA.

## Two completed implementation stages

### 1. Committed-source evidence, 15 new tests

Commit: `88c4474b7faea263d6e1b21ba846915269f398c6`.

`platform/rebuild_c1_evidence.py` reads immutable Git blobs rather than the
working tree. The ZIP records exact commit/tree identity, byte counts,
SHA-256 and Git blob IDs. Source text is allowlisted; font binaries, JSON/JSONL
sample or checkpoint files, unrelated paths and untracked files are excluded.
Dirty working-tree edits cannot change a claimed committed-source snapshot.

Publication is no-clobber and failed writes remove temporary files. Limits
bound source input buffers; no total-process RSS guarantee is claimed. Tests
cover deterministic reproduction, dirty/untracked exclusion, old revision
selection, hashes, file and aggregate budgets, invalid revisions, binary text,
Git symlinks, interrupted writes, existing targets and publication races.

The dedicated workflow now retains this source-only evidence for 14 days.
It is an audit snapshot, not a complete repository export: excluded JSON files
and other repository paths must still be obtained from the exact Git commit
when reproducing the complete repository test suite.

### 2. Real TTC padding false pass, 33 new tests

Commit: `75628e3eef45043e88689fd6ee191178ba179622`.

Original PAD1/PAD2/PAD3 metadata tables force respectively three, two and one
alignment bytes. Before the fix, corrupting any of these six bytes inside the
validation callback still allowed the old packer to publish its result:
**6/6 original corruption cases reproduced the false pass**. Logical table
bytes and directories were compared, but the alignment padding was not.

New `tools/ttc_staging_binary.py` independently parses the actual candidate
file after the callback and existing table-byte verification, before atomic
publication. It checks header and face directory identity, SFNT search fields,
sorted unique tags, table ranges and alignment, integer bounds, sharing
consistency, overlapping intervals, table checksums, zero-filled padding and
gaps, head adjustment, complete file extent, and streamed whole-file SHA-256.
Unexpected trailing bytes are rejected even when they are zero.

All six corruptions now fail as `serialization:ttc_nonzero_padding`. No final
output or temporary candidate survives, and original input hashes remain
unchanged. Existing checkpoint receipts are not overwritten by failed packing.
Additional tests cover 32-face shared/unshared packing, truncation, invalid
metadata, empty tables, directory aliases, partial overlaps, mutation after
hashing, bounded byte buffers and cross-platform file identity handling.

`ttc_staging_pack.py` attaches this independent binary evidence to its report.
`ttc_staging_engine.py` binds the checker into `builder_identity()`, so changes
to verification code cannot silently reuse a checkpoint from an older recipe.
There is no automatic migration or deletion of old checkpoints.

The checker is deliberately a C1 unsigned TrueType TTC v1 output profile,
not a generic font sanitizer. It does not decode glyph semantics or grant
native equivalence; the existing semantic/table validators remain necessary.

## Exact-source execution evidence

All three actual job logs were read, including checkout identity, dependency
installation, test termination and stress output. Dependencies were
FontTools 4.61.1, NumPy 2.2.6 and uharfbuzz 0.52.0 on Python 3.12.

| Actual job | Completed checks |
| --- | --- |
| [Ubuntu 24.04 / 118566341844](https://github.com/SOLHK/Swirl/actions/runs/39404296030/job/118566341844) | 198 C1 tests; 646 complete portable tests; 6 source audits; 47,102-GID original single-face stress |
| [macOS 14 / 118566341412](https://github.com/SOLHK/Swirl/actions/runs/39404296030/job/118566341412) | 198 C1 tests; 127-GID original cross-host CLI stress |
| [Windows Server 2022 / 118566341811](https://github.com/SOLHK/Swirl/actions/runs/39404296030/job/118566341811) | 198 C1 tests; 127-GID original cross-host CLI stress |

All listed unit tests passed with zero unittest skips. The 646-test portable
suite **includes** the 198 C1 tests; these are not disjoint totals. Linux-only
workflow steps are intentionally not run on the other two hosts. Tests of
unavailable native-runtime behavior retain their explicit NOT_RUN results;
passing such a test does not constitute an Apple native measurement.

The continuation added **48 tests**, taking the inherited C1 suite from 150
to 198. The local 33 new binary tests, all 198 C1 tests and six audits also
passed. Local Python 3.13.5 / FontTools 4.63.0 / NumPy 2.3.5 differ from CI.
The local complete-suite attempt hit its command time limit and is not
counted as a pass; the complete 646-test claim is from the finished pinned CI.

### Full-size original stress, not an Apple conversion

| Measurement at source 75628e3 | Actual Linux CI value |
| --- | ---: |
| Physical faces | 1 |
| GIDs structurally checked | 47,102 |
| Outline points checked | 197,820 |
| gvar tuples checked | 471,020 |
| Horizontal and vertical metric models checked | 94,204 |
| Standalone source bytes | 9,083,480 |
| TTC bytes | 9,083,496 |
| Copy block bytes | 65,536 |
| Packing-only new Python allocation peak | 199,659 bytes |
| Whole-process peak RSS | 673,501,184 bytes |
| Temporary synthetic font cleanup | Complete |

The packing allocation measurement excludes prior validation; the RSS includes
fixture generation and complete-face FontTools validation. Neither is a
production 32-face memory prediction. A face is still materialized by
FontTools, and a hard process memory ceiling is not implemented. Windows
reported unavailable RSS as null, not zero.

The separate 32-face collection fixtures are small original fonts. The full
32 x 47,102 plan is checked for exact ranges and tail coverage; this is not
1,507,264 completed native reconstructions.

## Independently downloaded source artifact

Artifact `12255983932` from the exact-source run was downloaded after completion.
The outer ZIP contains only `public-source.zip`.

- Outer size: **637,303 bytes**.
- Outer SHA-256: `2083f27b50c6b02fad36cb89139acc8088b754364aff3b7e4fee6af7efa0ee28`.
- Inner SHA-256: `8bc04f72377d8fbf4fdeb1217c2d31973e77f7bd4a14604e0b72ee0decf55a60`.
- Manifest: source commit `75628e3eef45043e88689fd6ee191178ba179622`,
  tree `47cd5292fc271aed7ac88c8b8557b2c2c14d3bec`.
- **154/154 files** independently checked for byte count, SHA-256 and Git
  blob identity; **154/154** matched the local tested source bytes.
- No font binaries or checkpoint payloads included. This continuation document
  postdates that immutable source snapshot and is not retroactively included.

## Preserved boundaries and remaining work

No changes were made to `hvf.py`, `rebuild.py`, `batch_geometry.py` or
`platform/coretext_extract.swift`. Original axis spelling, order and semantics
remain unchanged. Historical 1,088/1,088 and 26,780/26,780 geometry evidence
was not reclassified as new C1 execution. No glyphs or failed models were
silently discarded, and no replacement font was introduced.

The read-only preflight was executed without a private original and returned
**exit 2 / BLOCKED**, with A3 `NOT_INTEGRATED`, B1 `NOT_INTEGRATED`,
`source_not_supplied`, `reconstructed_faces=0`, and every production permission
false. This verifies refusal, not the identity or contents of an unavailable
original. The original-data admission and production gates remain closed.

The existing shared-entry GDEF variation remapping and mutable-checkpoint
issues remain documented in [the C1 audit](SWIRL_VF_REBUILD_C1_AUDIT_20261020.md).
Their reproducer tests passing means the known problem was reproduced, not
that a shared entry point was repaired. Unsupported layout variation data is
rejected by C1 instead of removed or silently copied under changed semantics.

Next integration step: the coordinator reviews/merges the C1 infrastructure,
then jointly binds accepted A3 input and B1 metric interfaces to a separate
production adapter with exact source, algorithm and transcript identities.
Only after those prerequisites and original-data admission pass may the full
32-face build be launched. This checkpoint does not claim CoreText parity,
Windows 11 DirectWrite/Qt/Swirl acceptance, or an installable final font.

## Reproduction from the exact repository checkout

```sh
python -m pip install fonttools==4.61.1 numpy==2.2.6 uharfbuzz==0.52.0
python -m unittest discover -s tools/swirl_vf/tests -p "test_ttc_staging_*.py" -v
python -m unittest discover -s tools/swirl_vf/tests -v
python -m unittest discover -s tools/swirl_vf/audit -p "test_*.py" -v
python tools/swirl_vf/platform/rebuild_c1_stress.py --glyph-count 47102
python tools/swirl_vf/platform/rebuild_c1_preflight.py
```

The final command is expected to exit 2 while production remains blocked.
The stress generator creates and removes its own original temporary fixtures;
no user font input or public font artifact is needed.
