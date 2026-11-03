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
