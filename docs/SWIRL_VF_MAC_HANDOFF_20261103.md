# Mac reference handoff, 2026-11-03

This branch continues Windows Beta commit `b7a455cf2cbad547e262b6984b2a87280dcbabf5`.
It does not modify PR #53, PR #54, main, test, or the existing Windows candidate.
The private export is a research reference, not another font release. Native
Windows acceptance and the Beta's outstanding geometry/size issues remain open.

## Implementation and research

The existing HVGL parser, batched evaluator, metric evaluator, raw ordered avar
mapper and symbolic branch locator are reused. Research branch changes since
the Windows baseline were inspected; unrelated CFF2 encoding and optimization
work remains on its research branch. No restricted reference-font outline is
used by the exporter or evaluator.

Before implementation, the following actual upstream source and tests were
reviewed, in addition to the earlier Windows research recorded in
`SWIRL_VF_WINDOWS_NATIVE_20261103.md`:

* [fontTools 4.61.1 SFNT reader](https://github.com/fonttools/fonttools/blob/4.61.1/Lib/fontTools/ttLib/sfnt.py),
  [tests](https://github.com/fonttools/fonttools/blob/4.61.1/Tests/ttLib/sfnt_test.py),
  [MIT license](https://github.com/fonttools/fonttools/blob/4.61.1/LICENSE).
  Reuse its table parser and checksum primitive; independently check raw TTC
  directories, lengths, aliases and overlapping ranges. Record both literal
  and zero-adjustment head sums. This source TTC uses literal sums including
  head.checkSumAdjustment; the original bytes must not be rewritten to suppress
  a tool warning. See the [OpenType collection/checksum rules](https://learn.microsoft.com/en-us/typography/opentype/spec/otff)
  and [specification discussion](https://github.com/MicrosoftDocs/typography-issues/issues/417).
* [CPython 3.12 gzip implementation](https://github.com/python/cpython/blob/v3.12.0/Lib/gzip.py),
  [tests](https://github.com/python/cpython/blob/v3.12.0/Lib/test/test_gzip.py),
  [PSF license](https://github.com/python/cpython/blob/v3.12.0/LICENSE).
  Use streaming gzip JSONL with fixed mtime, CRC/trailer verification and a
  separate SHA256 manifest. Records retain binary64 numbers. No pickle or
  executable serialized objects; no archive extraction or embedded dependency
  binaries. Path validation is identical on Windows and POSIX.
  A new offline replay regression exposed macOS `/var` being a symlink to
  `/private/var`. After reading [pathlib.resolve and its tests](https://github.com/python/cpython/blob/v3.12.0/Lib/test/test_pathlib.py),
  canonicalize the selected bundle root before rejecting links inside it.
  The original failing log is retained privately; the regression now passes.
* Existing native oracle source and Apple's SDK `hvf/Scaler.h` were reviewed.
  The added request stream reuses one Apple renderer per face, validates every
  GID/coordinate, and emits ordered request IDs and exact requested coordinates.
  Authored integration tests compare it to independent legacy one-request calls
  and reject malformed requests. No Apple implementation code is copied.
* The complete first replay exposed 146 Display advance differences caused by
  comparing different coordinates: HarfBuzz constructed the source Display
  fonts at normalized wght **-0.02398681640625**, whereas the exported baseline
  explicitly means **design zero**. Read [HarfBuzz hb-font.cc](https://github.com/harfbuzz/harfbuzz/blob/df9e6d15140d6bc5e983dcb5508ad254e76c8a0e/src/hb-font.cc),
  its [font API tests](https://github.com/harfbuzz/harfbuzz/blob/df9e6d15140d6bc5e983dcb5508ad254e76c8a0e/test/api/test-font.c)
  and [Old MIT license](https://github.com/harfbuzz/harfbuzz/blob/df9e6d15140d6bc5e983dcb5508ad254e76c8a0e/COPYING).
  The validator now records constructor readback, explicitly sets normalized
  zero, and checks that it was applied. All 376,816 default advance fields then
  agree in the independent control. An authored noncanonical avar + HVAR
  regression reproduces the issue. No source data, thresholds or mapping
  acceptance flags change; the first failed report is retained.

The repository's own license remains PolyForm Noncommercial. The dependency
licenses do not grant redistribution rights to Apple fonts or private geometry.

## Tools and execution boundary

| Tool | Environment | Input and purpose |
|---|---|---|
| `platform/hvf_oracle.c`, `hvf_coverage.py` | macOS, Apple HVF SDK/runtime | Native normalized-design outline extraction |
| `platform/macos_source_baseline.py`, `diagnose_coretext_formats.py` | macOS, CoreText | Exact-source identity and authored format controls |
| `platform/export_mac_handoff.py` | macOS for native extraction | Four-face catalog, complete default baseline, separate training/validation samples |
| `platform/export_handoff_boundaries.py` | macOS for native extraction | Independent nested axis/clamp/projection contact samples |
| `tools/handoff_bundle.py` | Python 3.12, Windows/macOS/Linux | Manifest/CRC verification, on-demand baseline and arbitrary design-coordinate reference evaluation |
| `tools/validate_handoff_reference.py` | Python, portable | Full saved-reference replay and independent HarfBuzz standard-advance checks |
| `tools/hvf.py`, `batch_geometry.py`, `source_metrics.py` | Python, portable | Source parsing, geometry, unhinted table metrics |
| `tools/target_axis_mapping.py` | Python, portable | Raw ordered avar and explicitly unaccepted user-map candidate |
| Existing `windows_font_builder.py`, `windows_full_audit.py`, `windows_explicit_deltas.py`, `ttc_staging_pack.py` | Python, portable | Windows compilation, geometry/metrics auditing and size work |
| Existing DirectWrite C++/PowerShell probes | Windows | Actual native Windows acceptance, still required |

Dependencies are `fonttools==4.61.1`, `numpy==2.2.6`, and `uharfbuzz==0.56.3`.
The portable reader does not import CoreText, load Apple libraries, access a
system font directory, or assume a Mac source path. A source copy inside the
private bundle is addressed by a relative path and pinned SHA256.

## Input identity and four-face baseline

Original: **22.0d5e2**, 61,473,880 bytes, 32 physical faces, SHA256
`39d42acd292ed5c9de5cf185b54a3c460630d610a718ed84c9e4f148e226f890`.
Reference: **21.4d1e1**, 102,151,892 bytes, five physical faces, SHA256
`124bab748149ea99cd26727384c80f53c92b8abbb3299c66770668ca55ae438b`.
They are different versions and formats; reference geometry is not substituted
for source geometry. Original and reference files remain unchanged in place.

| Target | Source index | GIDs | Best Unicode cmap | UPM | hhea ascent/descent/gap | Default user wght |
|---|---:|---:|---:|---:|---|---:|
| SC Text | 0 | 47,102 | 34,555 | 1028 | 884/-144/0 | 501 |
| SC Display | 5 | 47,102 | 34,555 | 1064 | 915/-149/0 | 499 |
| TC Text | 1 | 47,102 | 31,177 | 1028 | 884/-144/0 | 501 |
| TC Display | 6 | 47,102 | 31,177 | 1064 | 915/-149/0 | 499 |

Text/Display share exact `hvgl`, `hmtx`, `vmtx`, `HVAR`, `VORG`, `GSUB`,
`cmap`, `STAT`, `trak` and other table bytes within each language. They differ
in `head`, `hhea`, `OS/2`, `BASE`, `fvar`, `avar`, `name` and `meta`. The optical
size boundary is 20 pt. A shared design-zero FUnit outline does **not** imply
identical em geometry or identical user-coordinate mapping.

Raw source axis order is **WDTH,wght,HGHT**. WDTH/HGHT have user ranges
1/500/1000; wght has 100/501/900 for Text and 100/499/900 for Display.
The source fvar named weights are Light 300, Regular 400, Medium 500,
Semibold 600 and Bold 700. Raw avar record order and duplicates are retained.
Medium's candidate post-avar wght q is -1146/16384 for Text and 13/16384 for
Display. These are explicitly the retained A3 **candidate**, not a new global
CoreText mapping acceptance. Windows `wdth` percent values must not be passed
directly to the source WDTH axis.
In particular, the exported **design-zero baseline is not a certified CoreText
user-default instance**. HarfBuzz's differing Display default readback is a
concrete reason to preserve this distinction during Windows development.

The full reference gvar census again found 47,643 variable GIDs, 284,201 tuples,
nine distinct supports and at most six tuples/GID. All supports are single-axis;
there are no double/triple-axis tuples. 268,613 tuples use inferred points.
The glyf/gvar tables occupy 22,850,535/74,466,010 bytes. This explains reusable
standard encoding/IUP practice, not original HVF coupling fidelity.

## Native and portable evidence

* The original TTC has 147 unique table ranges, all in bounds and all matching
  literal table checksums. Exact table aliases are allowed; partial overlaps
  are rejected. All 32 head records differ under the zero-adjustment checksum
  convention, which is recorded rather than silently repaired.
* All **70,047 HVF parts** decode and pass DAG/offset validation: 69,870 Composite,
  177 Shape, tree depth at most 12. This file contains tangent types 0/1/2.
  Other versions and unsupported types 3/4 are not declared supported.
* **47,102/47,102 default GIDs** were freshly extracted through Apple HVF and
  compared to portable evaluation. Zero failures; maximum control-coordinate
  difference **9.890754881780595e-12 FUnit**. Original empty GIDs 1,2,3,4,46687
  remain empty. The common hvgl payload is exported once, not counted as four
  independent full native extractions.
* Four faces × 167 GIDs × 27 training and 30 independent validation positions:
  **38,076** native comparisons, zero failures, maximum **1.5916157281026244e-12**.
  Glyph seed 2026110331 and validation seed 2026110337 are retained. Noninteger
  single/double/triple-axis samples, corners, interiors and root-zero neighbors
  are distinct from the tensor training grid.
* Four faces × 355 branch-neighborhood requests: **1,420** native comparisons,
  zero failures, maximum **5.684341886080801e-13**. GIDs 1166,19177,35045,14813
  use independent symbolic three-axis chords. Located contacts include 2,402
  internal axis zeros, 14 lower and 15 upper tangent projection contacts.
  Float64 roots and a bounded selection are documented; no full clamp-surface
  or continuous-cube proof is claimed.
* Final local suite: **1,068 run, 1,061 passed, 7 skipped, 0 failed**; separate
  audit suite **6/6 passed**. The 13 handoff regressions pass on this Mac,
  including two actual Apple request-stream integration tests.
* [CI 41594442756](https://github.com/SOLHK/Swirl/actions/runs/41594442756), at
  code commit `04771ddc1ad0116ef03e21c8e427657ee2190bba`, passed on Windows
  Server 2022, Windows Server 2025, Ubuntu and macOS 15. Each Windows job ran
  13 handoff tests (11 passed, two Mac-only skips) plus 65 retained HVF tests
  (65 passed). These use authored data only. The real private package has
  **not** been uploaded or executed on a Windows machine.

These numbers concern HVF decoding and reference geometry. They are not new
glyf/gvar precision, DirectWrite or desktop visual results. The 1/32 FUnit
target remains unchanged. No Windows candidate was generated in this task.

## CoreText blocker and Mac retirement decision

On this machine, macOS 26.5.1 (25F80), the exact original and its byte-identical
bundle copy both return zero URL/data descriptors, fail CGFont construction,
and return registration error **103**. Identity verified **0/32**; subsequent
axis/metric requests are blocked, not passed. No font-name fallback or relaxed
table identity was introduced. Authored standard glyf and glyf+HVGL controls
load and verify 1/1; authored HVGL-only verifies 0/1 and also returns 103.
This isolates a current loading-path limitation without proving Apple's
private implementation cause or calling the source's valid geometry corrupt.
The installed font inventory was also queried: system PingFangUI is version
**21.4d1e1**, 47,098 GIDs, SHA256
`13b201d63324db59de86956c11c46d1f0ad9ac0aeaa0b9d035c012a794062db7`;
the available CFF PingFang is **21.0d1e1**, 49,533 GIDs. Neither is the supplied
22.0d5e2/47,102-GID source. Loading an installed same-family font would therefore
not establish exact source identity. A matching Apple environment remains
necessary for the unresolved original CoreText observations.

| Retirement question | Evidence-based answer |
|---|---|
| Original completely validated? | Binary structure and every default GID passed; original CoreText loading/layout acceptance is incomplete. |
| Four target faces recognized? | Yes: exact indices, names, mappings, metrics and real Text/Display table differences exported. |
| Three-axis relation confirmed? | Raw tags/ranges/defaults/avar are preserved; normalized-design finite samples pass. Global user→design mapping remains a candidate. |
| Apple HVF parser complete? | All structures in this particular source parse. Other HVF versions/types and the entire continuous domain are not certified. |
| Portable evaluator independent? | Yes for explicit normalized-design coordinates, with finite native evidence. It cannot certify unverified CoreText user semantics. |
| Can Windows read the handoff? | The reader/evaluator passed actual Windows CI on authored data. Real private-package Windows execution remains to be performed. |
| Tasks still requiring CoreText? | Native user-axis semantics, vertical origins, optical-size/tracking/layout and visual reference confirmation. |
| Unsolved Apple behavior? | Source loading on this OS, noncanonical avar user behavior, native vertical origin x, size-dependent tracking and untested source-domain regions. |
| Stop daily Mac engineering? | Main compiler/optimization/geometry work can move to Windows. Preserve a Mac/native oracle for unresolved behavior and new counterexamples. Full retirement is not accepted. |
| Work transferred to Windows? | glyf/gvar compilation, TTC sharing/size work, finite reference comparisons, interpolation research and actual DirectWrite/private-font/desktop acceptance. |

## Private delivery and repeatability

Local bundle: `private/handoff-windows/`, version `mac-handoff-0.1`. It contains
the exact source copy, four full GID/cmap/default-metric indices, raw axis data,
46 default geometry blocks, separate variation cohorts, native receipts,
an offline source-code snapshot, pinned requirements and Windows instructions.
All large geometry is compressed JSONL; no pickle is used. The source version,
coordinates, seeds, code identity and SHA256 manifest make each finite sample
reproducible without expanding all GIDs across an unbounded variation space.

Use Python 3.12 and install the pinned requirements into a private environment.
From the bundle directory:

```powershell
python -B code/tools/swirl_vf/tools/handoff_bundle.py verify .
python -B code/tools/swirl_vf/tools/handoff_bundle.py evaluate . --face 0 --gid 1166 --design=0.125,-0.375,0.625 --output D:/PrivateResults/gid1166.json
python -B code/tools/swirl_vf/tools/validate_handoff_reference.py . --output D:/PrivateResults/replay.json
```

`-B` preserves the sealed directory by avoiding pycache writes. Results must be
fresh files outside the bundle and public Git repositories. The PowerShell
launcher provides the same operations. Transfer only using a user-controlled
encrypted drive or an authorized direct SSH/SFTP connection, then check the
archive hash and run `verify`. No private delivery has been transmitted.

Final full-replay and archive receipts are added after the ongoing independent
bundle-code execution completes. The public PR contains only source, authored
tests, research notes and aggregate statistics, never these private data files.
