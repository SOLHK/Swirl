# Open-source interpolation comparison — 2026-11-03

This is a source-and-execution comparison, not a README survey. The inspected
repositories were cloned outside Git and pinned to:

| Project | Inspected revision | License |
| --- | --- | --- |
| [googlefonts/how2avar2](https://github.com/googlefonts/how2avar2/tree/7f69eaece10f7006b240fb469f1be7136d400997) | `7f69eaece10f7006b240fb469f1be7136d400997` | SIL OFL 1.1 |
| [arrowtype/HOI-test](https://github.com/arrowtype/HOI-test/tree/02c265d8f20bd063b014190e90f1beb3bfc3034b) | `02c265d8f20bd063b014190e90f1beb3bfc3034b` | MIT, Arrow Type / Stephen Nixon |

OFL's font-software scope can include build scripts and sources; derivatives
cannot simply be relicensed under Swirl's PolyForm Noncommercial license. MIT
copies require the copyright and permission notice. This change incorporates
neither project's code, master outlines, binaries, documentation nor screenshots.
The local reference clones retain their licenses. Swirl's new implementation
uses the mathematical axis-synchronization technique independently; no claim
of a new commercial grant, upstream endorsement or blanket license clearance
is made.

## What the code actually does

HOI-test's `sources/nli-test.designspace` places the same intermediate UFO at
both off-diagonal corners of a two-axis square. Its cubic designspace uses four
UFOs at the eight cube corners, with repeated masters according to Hamming
weight. `index.html` explicitly writes one slider value into all two or three
CSS variation settings. Restricting a tensor multilinear field to this diagonal
gives the quadratic/cubic Bernstein polynomial. The UFO control points and
actual compiled `gvar` tables were inspected. The repository contains visual
test fonts and a slider demonstration, not an automated sub-FUnit error suite.

how2avar2's `avar2QuadraticRotation.designspace` maps `ZROT` into `AAAA` and
`BBBB` simultaneously. The Glyphs source defines the independent auxiliary
masters. Its build script invokes `fonttools varLib.avar.build`, which delegates
to fontTools' `_add_avar`/variation-store construction. It is not a rational-HVF
fitter. The fences designspace clamps one corner and uses a narrow `90`/`90.02`
transition. The alternate-glyph feature source and HTML reftests check mapped
FeatureVariations as well as outlines. The test site classifies screenshots
and `.fail.md` files; its `make test` runs fontspector and permits QA failures.
Those tests do not constitute a numerical 1/32-FUnit certificate.

The separate avar1 rotation script deliberately duplicates axis tags and avoids
fontTools decompilation after renaming. That workaround is not adopted:
Swirl retains unique tags, three independent physical inputs and standard
simultaneous avar2 outputs.

## Executed upstream controls

Both fonts were rebuilt from their actual source design files, with fontmake
3.11.1 and fontTools 4.62.1 in an isolated reference environment. The how2avar2
build's axis-bound correction and actual avar2 build command were executed.
Swirl's observer then used CoreText, HarfBuzz 14.6.0 and fontTools 4.61.1 to
compare real, reloaded fonts. It verified actual run table hashes and exact
user-axis readback. No browser screenshots are reported as numerical tests.

| Rebuilt control | Positions per engine | CoreText maximum | HarfBuzz maximum | fontTools maximum |
| --- | ---: | ---: | ---: | ---: |
| HOI cubic, all three axes synchronized, Bernstein reference | 65 | 0.010140797 | 0.000062099 | 0 |
| how2avar2 rotation, integer degrees, unquantized explicit-axes reference | 91 | 0.059004472 | 0.071268847 | 0.056942626 |

The HOI cubic passes all 65 positions. Moving only its first axis instead of
all three produces a maximum residual of 930.945756 FUnits against the intended
cubic: consuming Swirl's three physical dimensions as this one diagonal would
destroy their independence. The proposed internal copies avoid that problem.

The how2avar2 control has **38/91 failures in each engine at Swirl's unchanged
threshold**. This does not contradict its visual conformance purpose. Against
the F2DOT14-quantized reference, fontTools becomes exact and CoreText reaches
0.010709733 with zero failures, isolating their mapping quantization. HarfBuzz
still reaches 0.118778103 with 12 failures against that reference; this additional
glyf execution difference is retained, not attributed solely to avar2. The
upstream examples therefore supply a useful representation mechanism, not a
drop-in solution to original HVF accuracy or a stronger interpolation fitter.

## Integration in SwirlVF

`joint_hoi` adds two distinct, hidden copies of each physical normalized input.
All copies read the same post-avar1 vector in one avar2 evaluation. A support
over one, two or three copies evaluates the corresponding first, second or
third local power. Products across independent physical groups express the
full tricubic tensor, including degree-nine simultaneous-axis paths. Projection
directions retain the separately encoded clamp ramps.

This changes the encoding basis, not fitted coefficients, sample density or
acceptance values. Source branch partitioning, rational projection factorization
and sparse unclamped-parameter fitting remain Swirl's own algorithm. A full
tensor uses up to 63 regions per cell; a nine-region axis-power fallback allows
the reencoder to stay within a declared global uint16 region budget. No regions
or coefficients are dropped to meet that budget. CFF2 stack and byte guards
remain active. Extremely dense independent directions can still exceed the
single-drawing-operation byte limit; such inputs are rejected, not accepted
as truncated geometry.

Authored tensor and axis-power controls both pass **155 positions per engine**:
CoreText maximum 0.004174495, HarfBuzz 0.002863535, fontTools 0.003309031 FUnit.
Their maximum stacks are 31 and 39. The first full-tensor GID 1166 reencoding
reduces 166,353,412 bytes to **86,598,392 bytes** (47.94% smaller), using 59,582
CFF2 regions and a maximum stack of 165. Native original-source verification
now passes the same independent seed `2026110443`: 3,140 CoreText observations
at 0.019082125035 FUnit, 3,140 HarfBuzz observations at 0.018971427426, and 269
fontTools observations at 0.012548240657, all with zero outline, topology,
direction or advance failures. The authored control alone did not admit it.
There are 3,121 distinct user positions and 3,065 observations provably off
the shared dyadic training grid; all 2,048 random triples are training-disjoint.

The simultaneous remote expression-pool change `04336e74` was merged without
overwriting it. Pooling and tensor-power encoding address different costs and
their combined authored control also passes all 155 positions per engine,
with identical maximum errors and a 9,440-byte font. Public counts and hashes
are in the [comparison receipt](evidence/SWIRL_VF_OPEN_SOURCE_20261103.json).
The combined real GID 1166 font is **62,247,684 bytes**. A fresh seed
`2026110445` passes 3,153 observations (3,134 distinct positions) per native
engine: CoreText maximum **0.025831485558**, HarfBuzz **0.023699382672**, and
271 fontTools observations at **0.018391232668** FUnit. All 2,048 random triples
are off the coefficient/parameter training grid. No failed outline, topology,
direction or advance comparison is hidden in these aggregates.

The merged regression run executes **1,013 tests: 1,006 pass, seven skips**.
Two preceding full runs retained a failing TTC memory assertion. Allocation
tracing located 1,922,992 bytes in `pathlib`'s `sys.intern` dictionary resize,
not a full-table font buffer. The same measurement now runs in a clean child
process, retaining every writer allocation and the original 1 MiB threshold.
No production packer or precision threshold was changed. Six parser audits
also pass; remote CI has not been claimed.

PR #53 stays Draft while both target glyphs and
the final serialized encodings are still under acceptance. No full-font
conversion or release is implied by these one-source-glyph fonts.

Reproduction tools: `platform/probe_open_source_interpolation.py`,
`platform/probe_polynomial_clamp.py --encoding hoi`,
`platform/reencode_joint_candidate.py`, and
`platform/verify_joint_candidate.py`. All generated fonts, control coordinates,
source coefficients and raw test records must remain outside the repository.
