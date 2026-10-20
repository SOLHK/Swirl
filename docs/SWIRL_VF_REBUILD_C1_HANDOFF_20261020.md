# Swirl-VF C1: resumable TTC infrastructure handoff

## Status and ownership

Repository: `SOLHK/Swirl`. C1 branch: `work/vf-rebuild-c1`.
Starting integration HEAD, independently re-read before branching:
`e505326486202ad4c8e98bb8b66a17b4547c559f`.

This branch adds an independent staging layer, strict structure validation,
streaming TTC packing, original fixture generators, stress tooling and a
dedicated cross-platform workflow. It does **not** modify `rebuild.py`,
`hvf.py`, `batch_geometry.py`, `coretext_extract.swift`, or the integration
branch. Existing reconstruction and metric algorithms are called unchanged.

**Original Apple reconstruction remains 0/32 faces.** No private Apple font
or original outline data was present in this C1 workspace. No production
`Swirl-VF.ttc` is generated, published, installed or accepted. A3 and B1 remain
unintegrated production requirements. The historical 1,088 and 26,780 geometry
comparisons are prior evidence; they are not executions performed by C1.

## Delivered components

| Component | Purpose and actual boundary |
| --- | --- |
| `tools/ttc_staging_store.py` | Fixed all-GID batch plans, content-addressed payloads and immutable checksummed receipts, exact recipe binding, process writer lock, crash/replay and integrity checks |
| `tools/ttc_staging_engine.py` | A working synthetic-only batch reconstruction pipeline around the existing `reconstruct_glyph`, with save/restore, exact coefficient comparison, source-table preservation and checked TTC assembly |
| `tools/ttc_staging_validate.py` | All-GID structural checks, exact identity contracts, gvar/phantom/HVAR/VVAR relations, layout references, collection order and table preservation |
| `tools/ttc_staging_pack.py` | Chunked TTC serialization, exact-byte table sharing, range/checksum verification, no-clobber publication |
| `tools/ttc_staging_contract.py` | Fixed six-category public-safe failures; private paths, glyph names and sample commands are excluded from reports |
| `platform/rebuild_c1_fixture.py` | Original 32-face variable fixture with independent regional identities, cmap/UVS, empty and unencoded glyphs, mixed-axis terms and layout tables |
| `platform/rebuild_c1_preflight.py` | Read-only exact-original identity and table inventory; always BLOCKED until accepted A3/B1 adapters exist |
| `platform/rebuild_c1_stress.py` | Reproducible original 47,102-GID single-face stress, separate validation/packing memory measurements, automatic temporary-font cleanup |
| `.github/workflows/swirl-vf-rebuild-c1.yml` | Linux, macOS and Windows synthetic tests; Linux complete original stress and existing portable regression/audit suites |

All relative paths in the table are under `tools/swirl_vf`, except the workflow.
The collection fixture is 32 faces by 7 GIDs; a separate validation fixture is
32 faces by 5 GIDs. End-to-end reconstruction uses 3 faces by 3 GIDs, and the
complete-size stress uses one face by 47,102 GIDs. All are original geometric
fixtures, separate from the unchanged original Apple 0/32 completion count.

## Batch integrity and recovery

The fixed 32-face / 47,102-GID plan has **1,507,264 face/GID model slots**.
At batch size 64 it has **23,552 batches**; every face's final batch contains
62 GIDs. Tests enumerate the complete plan to prove no gap, duplicate,
out-of-range GID or lost tail. This is a coverage-plan check, not 1.5 million
completed reconstructions.

Each checkpoint directory binds the complete canonical recipe: source SHA-256,
source table identity, reconstruction/module hashes, exact oracle identity,
Python/FontTools/NumPy versions, error budgets, batch size and data budgets.
A changed recipe is rejected before using confirmed data. Current on-disk
format is `swirl-vf-c1-batches-v2`; there is no automatic migration or
reinterpretation of earlier records.

The commit protocol is:

1. Obtain the operating system's exclusive writer lock. A competing writer
   is rejected; an abruptly terminated process releases its lock.
2. Reconstruct every GID in a batch and finish its complete synthetic session.
   Check exact requested GID coverage, summary counts and unchanged source.
3. Write and fsync a content-addressed model payload, then publish without
   replacing any existing inode.
4. Write and fsync an immutable receipt containing the exact range, recipe,
   payload digest and finished-session evidence. The receipt also contains a
   checksum covering that evidence. Its publication is the commit point.
5. On restore, verify the canonical receipt, receipt checksum, recipe, source,
   payload bytes/hash, exact GIDs and complete model schema again.

An orphan payload or `.uncommitted` file is never counted or promoted. An
interruption before the receipt therefore loses at most the unfinished batch.
A completed receipt followed by a process death before temporary-link cleanup
still restores normally. Repeating identical work is idempotent; conflicting
work or corrupt confirmed data is rejected without overwriting the old bytes.
Actual subprocess termination and concurrent locking are tested, in addition
to deterministic write-failure injection.

The checksum detects accidental corruption; this private build store is not
an authentication system against someone able to rewrite payloads, receipts
and all their hashes. POSIX directory fsync is used. Windows file contents are
fsynced and publication is atomic, but a directory-fsync/power-loss guarantee
is not claimed on Windows.

## Reconstruction and table contracts

`run_synthetic_staging(...)` is intentionally separate from production
`rebuild.run`. It admits only the named original standard-font test families,
rejects HVF/Apple input and non-identity synthetic avar, and reserves the final
filename `Swirl-VF.ttc`. Calling a test factory or supplying a JSON boolean
cannot enable the future production path.

The working engine samples each batch through a new explicit synthetic
session, calls the unchanged existing glyph reconstruction algorithm, stores
its complete integer base/tuple/metric model and restores that model into one
physical face at a time. The original `WDTH`, `wght`, `HGHT` spellings and order
remain unchanged. The synthetic staging profile keeps the existing 1 FUnit
reconstruction budget and 0.05 FUnit cubic budget; it does not reinterpret or
weaken the separate historical 1/32 FUnit geometry gate.

This C1 synthetic runner does not enable adaptive training. Any model that
fails its initial independent checks is rejected and retained as incomplete.
The shared production converter's existing adaptive logic remains unchanged.
There is no fallback font, skipped failing GID, reduced glyph count or
changed-axis workaround.

After saving each face, the shared exact serialization verifier compares all
base coordinates, contour topology, four phantoms and full gvar coefficients.
The C1 engine additionally compares the source physical glyph order and all
retained tables, including fvar/avar/name/OS2/STAT/cmap/GSUB/GPOS/GDEF/post.
It cannot accidentally change a valid name or width class and then bless a
contract derived only from the changed candidate. Fault injection tests alter
valid name, OS/2, fvar and STAT values and verify refusal while keeping all
previously committed batch data recoverable.

The strict expanded-glyf output profile checks maxp/loca/glyf coverage, raw gvar
header/offsets, tuple supports and cardinality including phantoms, cmap and UVS,
axis and instance metadata, every localized name, HVAR/VVAR region/map indices
and exact advance coefficient parity with gvar. Lazy GSUB/GPOS/GDEF subtables
are explicitly decoded before checking glyph references. Original serialized
out-of-range GSUB/GDEF examples first reproduced a lazy-reader false pass;
the fixed checker and eager/lazy coverage regression now reject them.

Unsupported retained variation stores and FeatureVariations are rejected.
VORG is not accepted as a fix for an independent vertical X origin in glyf.
The table checks establish standard-model structure and internal coefficient
consistency; they do not solve B1 or establish original CoreText equivalence.

For TTC assembly, contracts come from the saved and reopened independently
checked standalone faces. Both raw serialized table hashes and compiled
coefficient hashes are bound. All table bytes are preserved except the
specification's unused TTC `head.checkSumAdjustment`. Hash candidates receive
an exact byte comparison before sharing. Input files are rehashed and checked
for changes; offsets, alignment, overlap, table checksums and the 32-bit TTC
address limit are enforced. Existing destinations are never overwritten.

On Windows, path and descriptor stat APIs can expose different meanings for
`ctime`. C1 binds their device/file ID, size and modification time, then keeps
each complete snapshot, including its own change-time value, for comparisons
through that same API. The complete-file SHA check has identity checks on both
sides of the read. Regressions cover the API difference, same-byte replacement,
metadata changes in both phases and changed bytes with frozen metadata. See the
[upstream CPython report](https://github.com/python/cpython/issues/157671) and
the primary implementation links in `ttc_staging_pack.py`.

## Memory boundaries and measured original stress

The default engine budgets are 64 MiB of encoded sample data per batch,
64 MiB of encoded checkpoint payload, and 256 MiB of encoded models per face.
Encoding of model arrays stops as the byte-buffer budget is exceeded. Caller
objects and the JSON encoder's current string chunk are not part of that
buffer limit. Exceeding a budget is a failure, not permission to drop data.

The engine processes one face at a time; exact serialization validation holds
two representations of that face. Engine and collection-validation boundaries
explicitly release decoded font objects and collect lazy-reader cycles before
starting the next face. Weak-reference regressions first reproduced prior-face
retention, then verified release without the tests performing collection.
FontTools still materializes the face's
outline and variation objects. These are explicit data budgets, **not a hard
process RSS limit**. The packer independently streams fixed-size byte buffers
and keeps only face/table metadata plus hashes.

An actual original synthetic single-face stress at 47,102 GIDs measured:

| Measurement | Actual local result |
| --- | ---: |
| Original standalone file | 9,083,480 bytes |
| GIDs | 47,102 |
| Outline points | 197,820 |
| gvar tuples | 471,020 |
| Horizontal and vertical metric models | 94,204 |
| Fixture generation | 44.514 s |
| Structural validation | 115.040 s |
| TTC packing | 4.458 s |
| TTC file | 9,083,496 bytes |
| Copy block | 65,536 bytes |
| Packing-only tracemalloc peak | 186,983 bytes |
| Whole-process peak RSS | 631,788 KiB |

This first full stress preceded the later lazy-layout coverage correction;
its all-GID geometry/metric and packing measurements are retained as measured,
not relabeled as a run of the corrected checker. The final CI reruns the full
47,102-GID stress at its exact source commit. The final evidence section below
records that run separately. None of these numbers are Apple reconstruction
time or an original 32-face production memory prediction.

## Running the independent work

Install the same frozen dependencies used by C1 CI:

```sh
python -m pip install fonttools==4.61.1 numpy==2.2.6 uharfbuzz==0.52.0
python -m unittest discover -s tools/swirl_vf/tests -p 'test_ttc_staging_*.py' -v
python -m unittest discover -s tools/swirl_vf/tests -v
python -m unittest discover -s tools/swirl_vf/audit -p 'test_*.py' -v
python tools/swirl_vf/platform/rebuild_c1_stress.py --glyph-count 127
python tools/swirl_vf/platform/rebuild_c1_stress.py
```

The stress commands accept no font input, remove all generated temporary font
files and print only safe JSON. Default stress is one complete original
47,102-GID face; `127` is the faster cross-host CLI smoke. A missing native RSS
API is reported as null, never guessed or represented as zero.

For read-only preparation on a machine that has the exact private original:

```sh
python tools/swirl_vf/platform/rebuild_c1_preflight.py --source /private/PingFangUI.ttc
```

This always exits **2 / BLOCKED** for now. Exact source identity and an inventory
can pass while `production_rebuild_permitted`, `production_acceptance` and
`font_generated` remain false. A3/B1 integration cannot be replaced with a
hand-edited acceptance JSON or a tolerance argument.

## Shared-entry defects reproduced, not patched here

See [the C1 audit](SWIRL_VF_REBUILD_C1_AUDIT_20261020.md) for independent original
reproducers and narrow patch proposals:

- The legacy pipeline replaces avar without rejecting a GDEF variation store
  referenced from GPOS. An original example changes a same-coordinate layout
  delta from 25 to 50 while the old pipeline returns sampled pass. C1 refuses
  that unsupported case; the shared admission patch needs the coordinator.
- Two legacy `FaceCheckpoints` writers using stale manifests can lose a prior
  confirmed face's index entry. The actual files remain, but recovery state is
  lost. C1 uses an OS lock and immutable per-batch receipts independently.

These reproducer tests passing means that the old defects remain reproducible,
not that the shared defects were repaired or production acceptance was granted.

## Staged commits and CI evidence

1. `b0c3500afd58a5ecc55bc09dec259ba4b21bb7a6`: immutable storage, 22 local tests,
   new dedicated workflow. [Run 39398766503](https://github.com/SOLHK/Swirl/actions/runs/39398766503)
   passed Linux/Windows; macOS failed because system temporary paths contain
   the `/var` symlink. Actual logs were read. Test-created roots were then
   canonicalized without allowing arbitrary symlink checkpoint paths.
2. `110d903ac95a0e793911610a0c99c061d199df8a`: structure/packing/preparation and
   integrity fixes, **110/110** local C1 tests. [Run 39399445734](https://github.com/SOLHK/Swirl/actions/runs/39399445734)
   passed Linux/macOS; Windows rejected unchanged input at the path/handle stat
   comparison. Actual logs were read; the following stage repairs that native
   stat distinction while retaining per-path/per-handle snapshots and SHA checks.

The exact final source SHA, test counts and final run results are appended after
the final execution completes. A queued or running check is never recorded as
passing. Documentation-only final evidence updates do not rerun unchanged code.

## Next production integration boundary

The coordinator must first supply reviewed A3 input semantics and B1 metric
semantics, decide the narrow shared admission/checkpoint patches, and define
the native per-batch session evidence contract. Then a separate production
adapter can integrate all-GID training/holdouts, adaptive behavior and native
summary/EOF/exit verification with this staging infrastructure. Its recipe must
bind the exact approved code and interface versions; current synthetic receipts
must never be upgraded into native evidence.

Only after full original reconstruction and independent target-platform checks
may the final original `Swirl-VF.ttc` be published. Windows Server/Python CI,
original fixtures, table integrity and even a successful reconstruction are
separate from Windows 11 installation, DirectWrite semantics and Qt/Swirl
product acceptance. Those production checks remain unperformed in C1.
