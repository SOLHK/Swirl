# SwirlVF Windows native test builds

This branch continues `669678c9a5dd1a7bf769a9d9b222161b68e981bd` from PR #53.
The old CFF2/avar2 research remains intact. The first Windows test build is
allowed to miss the 0.03125 source-FUnit research target; every such result is
reported. Neither an Alpha filename nor successful parsing accepts a final font.

## Actual input inspection

| Input | SHA256 | Bytes | Faces | Version | Outlines |
|---|---|---:|---:|---|---|
| Original `PingFangUI.ttc` | `39d42acd292ed5c9de5cf185b54a3c460630d610a718ed84c9e4f148e226f890` | 61,473,880 | 32 | 22.0d5e2 | hvgl |
| Windows reference `A_PingFangUI-VF.ttc` | `124bab748149ea99cd26727384c80f53c92b8abbb3299c66770668ca55ae438b` | 102,151,892 | 5 | 21.4d1e1 | glyf/gvar |

The reference is SC/TC/HK/MO/JA, not four Text/Display faces. Face 0 contains:
glyf 22,850,535; gvar 74,466,010; loca 190,592; hmtx 190,580; cmap 887,242;
GSUB 134,170; vmtx 95,296; name 2,780; HVAR 1,398; fvar 238; STAT 226;
BASE 174; OS/2 96; avar 78; head 54; hhea/vhea 36 each; maxp/post 32 each
(all sizes in bytes). GPOS and MVAR are absent. No converter provenance can be
recovered from these structures alone.

The complete reference census inspected all 47,647 glyphs. 47,643 vary, using
284,201 tuples, at most six per glyph. All tuples are single-axis: 94,185 wdth,
95,834 wght, 94,182 HGHT. There are **no two-axis or three-axis tuples**. Nine
distinct supports occur, no repeated support within a glyph, and 114 tuples
are all-zero or inferred. 268,613 tuples use inferred points (32,090,182 omitted
point entries versus 25,518,877 explicit entries). This proves a separable
outline model, not that it reproduces HVF coupling. It does not prove which
sampling program generated the reference.

Physical TTC table sharing reduces 493,868,039 summed per-face table bytes to
102,150,245 unique table bytes. SC/TC share glyf/gvar and most common tables.
IUP and exact table sharing are useful precedents; copying the reference's
private contours, ignoring coupled residuals, and relabelling it are excluded.

Original faces 0/5/1/6 are the SC Text/SC Display/TC Text/TC Display sources.
Their hvgl, hmtx, vmtx and HVAR tables are byte-identical. Text and Display
nevertheless differ in UPM (1028/1064), hhea ascent/descent (884/-144 versus
915/-149), weight default (501/499), avar and optical-size metadata (below/above
20 points). Target names alone cannot preserve those distinctions.

Both versions have height 1..1000, default 500. Original width is custom WDTH
1..1000/default 500; reference registered wdth is 80..120/default 100. The new
builder explicitly maps the negative and positive width intervals separately.
Weight is 100..900; original named Medium is 500, not necessarily the default.
Light/Regular/Medium/Semibold/Bold are read from the original fvar instances.
The reference uses a different release with 545 more GIDs: cross-version shape
differences cannot all be attributed to a conversion algorithm.

## Implementation and upstream review

Reviewed actual versioned source, tests and licences, not just project READMEs:

- [fontTools supportScalar and VariationModel](https://github.com/fonttools/fonttools/blob/4.61.1/Lib/fontTools/varLib/models.py): multiplicative axis tents and zero-peak semantics. The independently implemented anchored tensor differences include pair and triple interactions, avoid a dense model solve, and reproduce every integer grid vertex.
- [gvar writer](https://github.com/fonttools/fonttools/blob/4.61.1/Lib/fontTools/ttLib/tables/_g_v_a_r.py) and [TupleVariation](https://github.com/fonttools/fonttools/blob/4.61.1/Lib/fontTools/ttLib/tables/TupleVariation.py): existing packed-delta serialization is reused, with per-glyph streaming. The internal compileGlyph_ boundary is deliberately version-pinned to 4.61.1.
- [IUP](https://github.com/fonttools/fonttools/blob/4.61.1/Lib/fontTools/varLib/iup.py) and [tests](https://github.com/fonttools/fonttools/blob/4.61.1/Tests/varLib/iup_test.py): tolerance-zero optimization is followed by exact delta reconstruction. Floating arithmetic issue [#3703](https://github.com/fonttools/fonttools/issues/3703) is a reason to verify, not assume, equality.
- [cu2qu multi-master conversion](https://github.com/fonttools/fonttools/blob/4.61.1/Lib/fontTools/pens/cu2quPen.py) and [tests](https://github.com/fonttools/fonttools/blob/4.61.1/Tests/pens/cu2quPen_test.py): the retained reconstruction module already uses compatible conversion. HVF's native quadratic contours do not need a cubic round-trip.
- [TTCollection](https://github.com/fonttools/fonttools/blob/4.61.1/Lib/fontTools/ttLib/ttCollection.py): share by table bytes, not SC/TC glyph-name strings. The existing checked, bounded-copy TTC packer is reused. Post format 3 can synthesize different glyph names for the same GID in different regional cmaps.
- [HarfBuzz glyph execution](https://github.com/harfbuzz/harfbuzz/blob/df9e6d15140d6bc5e983dcb5508ad254e76c8a0e/src/OT/glyf/Glyph.hh): independent native outline execution is used locally. It is not DirectWrite evidence.
- Microsoft [gvar](https://learn.microsoft.com/en-us/typography/opentype/spec/gvar), [variation formats](https://learn.microsoft.com/en-us/typography/opentype/spec/otvarcommonformats), and [DirectWrite axis instancing](https://learn.microsoft.com/en-us/windows/win32/api/dwrite_3/nf-dwrite_3-idwritefontresource-createfontface): tuple count, Offset16, integer deltas and physical axis readback are explicit checks.

fontTools core is [MIT](https://github.com/fonttools/fonttools/blob/4.61.1/LICENSE);
cu2qu files carry Apache-2.0 notices. They remain external dependencies with
their own notices; no third-party source was copied into this branch. This
review does not grant redistribution rights to either proprietary font.

## Candidate scope and remaining gates

The Alpha includes 113 original GIDs, ordinary SC/TC characters, Latin letters,
digits, punctuation, complex Han and GIDs 1166/19177. It is not a full font.
The builder has a full-GID mode and retains the original cmap/UVS/GSUB/layout
only in that mode. It never substitutes a blank for a failed conversion.

Original avar contains duplicate and non-increasing inputs. Legal avar v1 is
built by rebasing the source's reachable design interval, with a separately
reported mapping approximation. The retained A3 source-user hypothesis is not
a newly established global CoreText equivalence proof. Discontinuities near
the original default cannot be reproduced exactly by a continuous gvar font.

Target units are scaled before integer encoding (default 15x: UPM 15420/15960).
At a simple-glyph default, nearest-grid point error may reach sqrt(2)/30 source
units. This is a bound for this representation, not an impossibility theorem
for every TrueType composite representation. Curve approximation, quantization,
interpolation, source-decoder and native-engine errors remain distinct.

Quality groups currently refer to sampled control-point bounds: <=1/32,
<=2 source FUnits, or larger differences. The 2-unit group is an explicitly
declared Alpha geometry screen, **not visual or high-precision acceptance**.
No hinting is synthesized. Source AAT tracking and native vertical x-origin
semantics remain unconverted. Mac raster success is not Windows success.

The public CI generates an independently authored four-face TTC using the same
mixed-tuple compiler, checks DirectWrite axes/outlines/raster captures and native
Medium matching on Server 2022/2025 and Windows 11 ARM64 with an x64 process.
It contains no private font payload. Original-glyph Windows testing requires
an authorized private Windows machine; public CI must not receive these fonts.
Actual run links and final measurements are appended after execution.

## Executed Alpha measurements

The private 113-GID four-face Alpha has been generated, not only designed.
The compact coefficient-rounded build is 628,792 bytes (SHA256
`0c2191036ddd69ba789934adb6c77b8f336c4f414490ec479e5932ca925f90db`).
Its SC/TC best cmaps contain 103/104 Unicode entries. It is not a complete font.
The ordinary glyph grid uses 27 vertices; failed sampled geometry screens are
retried with 125 vertices, retaining the better measured fit. Both encodings
remain available, and both retain exact IUP reconstruction of stored deltas.

The original nodal-rounding Alpha was 1,612,668 bytes. Compact rounding follows
the strategy reviewed in fontTools `varLib._add_gvar`: round coefficients rather
than introducing mixed differences of separately rounded vertices. On these
113 glyphs the maximum vertex quantization bound increases from 0.04714 to
0.20538 original units. This is a measured tradeoff, not high-precision acceptance.
At the same 60 independent positions, maximum saved-font control errors change
from 6.91352/7.95539 to 6.90583/7.91874 for Text/Display. The number above the
2-unit screen changes from 16/16 to 17/15. No claim of every-glyph improvement
is made. The source decoder and interpolation errors are reported separately.

The source HVAR was also evaluated at source design width -1/0/+1. GIDs
0/1166/19177 advance by 800/1000/1200 units; GID 12 advances by 539/674/809.
Target `wdth` 80/100/120 therefore describes the measured approximately
80/100/120-percent width endpoints. This does not establish physical alignment
with the separately versioned Windows reference.

The compact Alpha's four faces have 27,120 saved-font observations, no empty
mismatch, and native HarfBuzz movement on all three axes. Apple libhvf checks
cover 896 nonempty glyph/position observations; maximum decoder discrepancy is
4.55e-13 original units, with zero topology failures in the corresponding native
HarfBuzz samples. These finite observations do not validate the full source.

The reference comparison examines 28 characters per regional Text face at 27
positions. Within the original, maximum second/third-order mixed coefficients
are 8.43501/0.05541 (SC) and 8.30071/0.04585 (TC). Within the reference they are
below 1.14e-13. This independently corroborates the missing coupled terms.
Different font versions and unverified physical-axis alignment prevent calling
these values a cross-version conversion error; the tool deliberately does not
make that comparison.

Actual [Windows run 41578061249](https://github.com/SOLHK/Swirl/actions/runs/41578061249)
tested the authored control on Server 2022, Server 2025 and Windows 11 ARM64.
All three passed native Medium matching. The Server 2025 observer loaded four
physical faces, registered 20 process-private GDI entries, and returned 2,024
outline observations. The unchanged exact-axis gate failed (684 differing axis
readbacks, maximum 7.62939453125e-6). The unchanged 1/32 research geometry gate
also failed: maximum 0.33274718 units, 1,808 failing observations. The workflow
is therefore **failed**, not Windows acceptance. Neither GDI process registration
nor an authored control proves desktop installation of the private candidate.

## Native IUP diagnosis and exact re-encoding

[Windows run 41579230845](https://github.com/SOLHK/Swirl/actions/runs/41579230845)
repeated the authored experiment on all three OS images and added a no-IUP
control. Windows 11 was Enterprise build 26200 on an ARM64 host running the
x64 probes. Each variant produced 2,024 requested outline observations. Medium
matching passed on all images. IUP retained the 0.33274718-unit maximum error;
explicit deltas reduced it to 0.04714046 units (1,304 observations still fail
the unchanged 1/32 research gate). The maximum matches the scale-15 nearest
integer point bound in this experiment. This is neither a general impossibility
theorem nor private-candidate acceptance. All three CI jobs remain failed, and
the 684 exact-axis readback differences remain reported.

`windows_explicit_deltas.py` reconstructs every omitted delta with fontTools,
requires exact integer reconstruction, and writes the same coefficient maps
without IUP. It does not refit any source geometry. A bounded process pool and
SHA256-keyed per-face cache allow the complete font to be re-encoded without
repeating HVF conversion. SC and TC reuse the matching Text/Display tables;
124 shared tuple peaks remove repeated support headers. These mechanisms have
public authored round-trip and complete HVAR/VVAR coefficient equality tests.
The private 113-GID expanded Alpha is 693,596 bytes, SHA256
`c135ba2fd5c6b3383db91beef4e3214752617d07f15ddefc3e44fb298b532d72`.
The saved-font interpolation errors are unchanged; removing IUP is specifically
an engine-execution mitigation with a measured size cost.

The offline Windows kit pins both the candidate and diagnostic executables by
SHA256, captures requested positions and native Medium matching, and retains
the original strict probe's failures. It never uploads results or installs a
persistent system font. Its capture status requires subsequent geometry and
visual review; it is not a release acceptance flag. Only independently authored
data is permitted in the public CI test of this kit.

User-coordinate/layout checks use the Apache-2.0-licensed uharfbuzz binding,
after reading its [variation API implementation](https://github.com/harfbuzz/uharfbuzz/blob/v0.56.3/src/uharfbuzz/_font.pxi),
[file-backed blob implementation](https://github.com/harfbuzz/uharfbuzz/blob/v0.56.3/src/uharfbuzz/_blob.pxi)
and [shaping tests](https://github.com/harfbuzz/uharfbuzz/blob/v0.56.3/tests/test_uharfbuzz.py).
The verifier sets actual user coordinates, reads HarfBuzz's normalized result,
and compares source/target OpenType glyph IDs, clusters, advances and offsets
in horizontal and vertical runs. Source normalized coordinates come from the
explicitly retained A3 hypothesis, not an assumed equality of axis numbers.
File-backed blobs avoid repeatedly copying the full TTC during native checks.

## Windows line spacing correction

The original OS/2 table has USE_TYPO_METRICS clear and typographic line metrics
860/-140/400, while source hhea is 884/-144/0 (Text) or 915/-149/0 (Display).
Keeping both sets without a Windows mapping leaves inconsistent line spacing.
The target now copies each source hhea triplet into OS/2 sTypo fields and sets
USE_TYPO_METRICS, retaining the larger original Win clipping bounds. This follows
the [Microsoft variable-font metric guidance](https://learn.microsoft.com/en-us/typography/opentype/spec/os2#os2-table-and-opentype-font-variations).
The [gftools metric fixer](https://github.com/googlefonts/gftools/blob/main/Lib/gftools/fix.py)
and its Apache-2.0 license were inspected; its legacy Windows source-metric
choice is deliberately not used for this Mac-source conversion.

`windows_line_metrics.py` updates a fresh TTC copy, rewrites affected checksums,
and verifies every byte outside OS/2, head, name and their directory checksums
is unchanged. It therefore preserves previously audited geometry/variation data.
The authored native control has distinct Text/Display hhea values and larger
clipping bounds; DirectWrite records and checks actual line metrics at every
requested location. The private original's strict CoreText baseline separately
returned BLOCKED_SOURCE_IDENTITY (0/32 faces), so these source table values are
not presented as newly measured CoreText global metrics.

The layout diagnostic measured source tracking increments of 21, 20, 13 and
4.578125 units at 12, 16, 24 and 48 pt. It also compares native per-glyph advances
separately from positioned advances. HarfBuzz's
[tracking implementation](https://github.com/harfbuzz/harfbuzz/blob/main/src/hb-aat-layout-trak-table.hh)
and [shape-plan selection](https://github.com/harfbuzz/harfbuzz/blob/main/src/hb-ot-shape.cc)
explain the size-dependent source behavior. The Windows target still does not
implement AAT tracking; no fixed spacing substitute is claimed to be equivalent.

Per-glyph work uses Python's PSF-licensed [ProcessPoolExecutor](https://github.com/python/cpython/blob/3.12/Lib/concurrent/futures/process.py),
reviewed along with [its licence](https://github.com/python/cpython/blob/3.12/LICENSE).
The project scheduler submits at most twice the worker count and streams results
in GID order; no upstream scheduler code was copied. Full conversion retains
per-glyph progress even if stopped. An initial exact-nodal full build was stopped
after 11,382 Text glyphs and 229,880,280 gvar bytes, to avoid a multi-gigabyte test
delivery. Its partial files and measurements are retained privately.

Reproduce a private test build using the pinned environment:

```sh
python tools/swirl_vf/tools/windows_font_builder.py \
  --source /absolute/private/PingFangUI.ttc \
  --output /absolute/private/new-test-directory \
  --adaptive --workers 6 --quantization coefficients
```

Add `--full` for all source GIDs and original cmap/UVS/GSUB. Output must be a new
directory outside Git. `--quantization vertices` preserves the nodal encoding
for precision comparisons. Windows outcomes remain separately required.
