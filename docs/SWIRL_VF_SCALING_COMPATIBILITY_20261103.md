# Joint compiler capacity and native access — 2026-11-03

This records executed controls and conditional architecture limits. It does
not certify a full font, original physical-user axis parity or Windows release.

## Actual DirectWrite execution

The independently authored C++ observer loads an isolated local font through
DirectWrite Factory6 / TextLayout4 and captures the actual glyph run and path.
It verifies the run's CFF2, fvar, avar, GSUB and cmap bytes, every requested axis,
advances and contours. The workflow uploads only authored-control transcripts;
no proprietary source or derived font goes to Windows CI.

[Run 41573700485](https://github.com/SOLHK/Swirl/actions/runs/41573700485)
executed ten controls on Windows Server 2022 (build 20348) and Server 2025
(build 26100). Each control has 762 requests: 125 grid points and 256 fixed-seed
random points, each with omitted and explicit computational-axis defaults.
The two server versions produced the same outcomes:

| Control | DirectWrite outline failures / 762 | Maximum comparable error | Patch selection failures / 762 |
| --- | ---: | ---: | ---: |
| Static CFF2 | 0 | 0 | 762 |
| Flat linear CFF2, avar1 | 0 | 0.000762290 | 762 |
| Horner polynomial, avar1 | 762 empty outlines | N/A | 762 |
| Flat CFF2 with avar2 clamp | 754 | 18.028168 | 762 |
| Unshared full program | 762 empty outlines | N/A | 762 |
| Compressed full program | 762 empty outlines | N/A | 762 |
| Flat CFF2, required `rlig` | 0 | 0.000762290 | 762 |
| Flat CFF2, explicitly requested `rvrn` | 0 | 0.000762290 | 0 |
| Full program, required `rlig` | 762 empty outlines | N/A | 762 |
| Full program, explicitly requested `rvrn` | 762 empty outlines | N/A | 0 |

Every variant also has 120 exact FLOAT axis-readback mismatches, maximum
0.00000762939453125 user units. They remain strict failures; no coordinate
tolerance is silently introduced. All advances equal 700. HarfBuzz passes all
762 observations for each control, with full-program maximum 0.003738366.
The [aggregate receipt](evidence/SWIRL_VF_DIRECTWRITE_SCALING_20261103.json)
retains every failure. Its legacy `max_error: 0` on empty paths means **no
comparable points**, not perfect accuracy.

An earlier run tested a real LangSys ReqFeatureIndex; it did not enable default
selection. Explicit `rvrn` fixes selection but leaves high-order paths empty.
Thus default-feature routing, avar2 mapping, and high-order execution are
separate limitations in these tested systems. The Horner/avar1 and unshared
controls isolate the high-order failure from avar2 and the new byte compression.
The exact underlying DirectWrite decoder rejection is not yet traced; this
does not prove all higher-order constructions impossible. The current CFF2
specification marks `blend` itself blendable
([CFF2 specification](https://learn.microsoft.com/en-us/typography/opentype/spec/cff2#charstring-variation-operators)).

Windows 11 **client**, original-source Windows execution, text fallback and
installation remain NOT_RUN. Server 2025 is not relabelled Windows 11. The
dated upstream [avar2 support matrix](https://googlefonts.github.io/how2avar2/docs/support/)
was context; the table above comes from actual native execution.

## Structural capacity

The selector scanned all 47,102 face-0 source glyphs: 47,097 nonempty three-axis
roots and five empty roots. The current fitter starts from eight octants and
the encoder allocates one replacement glyph per cell. Even aliasing each
original glyph to one of its patch glyphs requires at least
`5 + 47,097 × 8 = 376,781` glyphs. Retaining each original base requires
`47,102 + 47,097 × 8 = 423,878`. Both exceed maxp's uint16 glyph count.
This calculation assumes no cross-source glyph aliasing and applies only to
the current distinct-patch architecture. It makes **no** file-size or CPU
extrapolation ([maxp specification](https://learn.microsoft.com/en-us/typography/opentype/spec/maxp)).
`platform/joint_capacity_report.py` makes the assumption and bound reproducible.

CFF2 has a 513-operand stack, 65,535-byte program limit and ten nested calls;
current compressed anchors have conservative stack bounds 53/44, depth three,
and 139,143/134,108 expanded tokens below HarfBuzz 14.6.0's 200,000-token limit.
These are per-program checks, not guarantees that arbitrary glyphs will fit.
The global variation-region count is less than 32,768; the compiler now rejects
32,768 rather than permitting the reserved high bit
([variation formats](https://learn.microsoft.com/en-us/typography/opentype/spec/otvarcommonformats)).

The anchors' CFF2 ItemVariationStore payloads are 212,832/142,354 bytes. fontTools
4.61.1 writes a 65,535 length sentinel and reads the remaining payload for that
sentinel (`cffLib.VarStoreCompiler` / `VarStoreData`,
[fontTools issue 3673](https://github.com/fonttools/fonttools/issues/3673)).
The published Microsoft CFF2 table still describes a uint16 length. The
[sentinel proposal](https://github.com/harfbuzz/boring-expansion-spec/issues/159)
and actual CT/HB acceptance therefore must not be confused with universal
validator compatibility. Small Windows controls do not hit this size and
already fail independently. `profile_joint_font.py` now exposes this payload
and sentinel explicitly.

## Access paths and viable next architecture constraints

Fresh CoreText/HarfBuzz timing runs compare 384 omitted/default-axis requests
per font and engine without mismatch. Direct, unshaped base-GID paths differ
in all 384 comparisons: the implementation requires shaping. A hidden axis is
only a UI flag, not protected state
([fvar specification](https://learn.microsoft.com/en-us/typography/opentype/spec/fvar)).
Application caches, fallback and arbitrary caller mutation are not certified.

Actual fontTools text subsetting of the accepted GID 39903 probe retains 2,050
of 2,051 glyphs, including the patch closure, and reduces 20,575,616 to
20,573,692 bytes. All 512 fresh HarfBuzz comparisons preserve exact outlines
and advances; shuffling the same coordinates through a reused font instance
also gives zero mismatches. The subset step takes 138.452 seconds and the whole
probe peaks at 632,815,616 RSS bytes. A 512-position authored control also
passes. This measures one subsetter and native engine, not CoreText subsetting,
browser sanitizers or arbitrary application caches. Subsetting cannot remove
the patch population needed to retain variation behavior.

A flat CFF2/avar1 control works on both tested Windows systems and is a viable
compatibility baseline. Replacing local Horner programs with ordinary deltas
would still require an accuracy-preserving basis and a cell-selection strategy
within the glyph/region/stack budgets. The earlier fixed-support lower bounds
exclude coefficient-only repair on those supports, not all flat CFF2 partitions.
Axis-copy HOI uses additional avar2 inputs and does not eliminate the measured
Windows mapping problem. VARC retains its earlier native topology failures.
Splitting the source into several fonts or using private interpolation would
change the delivery contract and is not treated as a solution.

Exact instruction sharing, sparse fields and cross-face geometry reuse improve
costs within the research compiler. They do not remove the glyph-index limit,
raw-source axis ambiguity or Windows execution blockers. PR #53 stays Draft.
