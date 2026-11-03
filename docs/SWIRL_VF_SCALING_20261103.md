# SwirlVF joint compiler scaling — 2026-11-03

This work continues remote `cccc0a39090079542f2e3af064bfce328ed66b5e` on
the existing PR #53. It preserves the independently accepted rational-projection,
localized-tricubic, avar2 and required-GSUB architecture. These are selected-glyph
research fonts, not a full-font release. Private inputs, outlines, coefficients,
coordinates and raw transcripts remain outside Git.

## Checkpoint 1: exact CFF2 instruction sharing

The actual latest inputs were smaller than the historical 62/256 MB HOI fonts:
58,178,796 and 196,056,396 bytes. An SFNT/CFF2 inventory identifies the dominant
cost precisely:

| Face 0 GID | CFF2 table | CharString/subroutine payload | avar | GSUB | Cells | Computational axes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1166 | 56,732,035 | 56,412,582 | 1,300,110 | 134,646 | 2,048 | 8 |
| 19177 | 195,178,174 | 194,883,754 | 625,956 | 230,846 | 4,096 | 16 |

All sizes are bytes. CFF2 has 2,499 / 190 regions and 2,049 / 4,097 variation
data sets. avar2 has 14,442 / 4,062 regions. There were already 32,780 / 33,898
global subroutines, but no local subroutines. Repeated zeros account for
24,795,417 / 102,024,712 encoded numeric tokens. Total axis counts are 11 / 19;
the source also flags WDTH/HGHT hidden, so a raw hidden-flag count is not the
number of computational axes.

`cff2_structural_pool.py` adds a bounded dictionary of at most 215 call-free local
subroutines. It shares complete instruction runs and exact 16.16 literals, using
two-byte calls. It does not alter coefficients, rounding, region selection,
global subroutine indices, contours, control points or arithmetic order. For
every rewritten main/global program, expanding the new calls must recover the
original bytes exactly, before any font mutation. The pass understands the
generated unhinted single-result-blend dialect and rejects unsupported state
changes. Numeric payloads cannot accidentally be interpreted as instructions.

Expanded execution, operand stack and call depth are checked before mutation.
Sharing reduces stored bytes but adds execution overhead; the new maxima stay
below the unmodified HarfBuzz 14.6.0 limit of 200,000 tokens.

| GID | Before | After | Reduction | Compression time | Compressor peak RSS | Expanded tokens before / after |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1166 | 58,178,796 | 32,200,320 | 44.65% | 26.507 s | 411,484,160 | 119,001 / 139,143 |
| 19177 | 196,056,396 | 89,678,604 | 54.26% | 89.666 s | 1,197,998,080 | 117,122 / 134,108 |

Each has 215 helpers; conservative operand-stack bounds are 53 / 44 and call
depth is at most three. Wall times include 27.093 / 91.197 s for the whole
compression command. Peak RSS is process-specific macOS `getrusage`, not machine
memory or a full compile peak. All other tables are byte-identical, including
`head` after excluding only its checksum adjustment. File hashes are in the
[aggregate receipt](evidence/SWIRL_VF_STRUCTURAL_COMPRESSION_20261103.json).

Fresh native acceptance reloads the actual compressed files and obtains new
Apple libhvf source observations. Seeds 2026110611 / 2026110613 add 4,096 new
random triples each, single/dual axes, cube boundaries, branch/Clamp contacts,
640 seam observations, fractional inputs and exact physical replays of every
previous localized request (plus all 33 earlier 1166 maximum-error requests).
Old coordinates may be replayed; old geometry/results are never reused.

| GID | CT/HB observations each | Unique independent positions | CoreText maximum | HarfBuzz maximum | fontTools maximum (512 requests) |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1166 | 12,320 | 11,009 | 0.019469403543 | 0.017497873540 | 0.016362679421 |
| 19177 | 14,553 | 11,530 | 0.017883106686 | 0.017048651460 | 0.016191699900 |

Errors are original-source FUnits; the unchanged limit is 0.03125. All measured
outline, topology, closure, winding, patch-range and advance checks pass.
Exact source-axis readback and candidate table identity are checked in CoreText.
Overlapping/repeated samples remain tested and are not counted as independent.
The compression checkpoint ran 1,032 regression tests: 1,025 pass, seven platform
skips. Its authored serialized control also compares 83 additional HarfBuzz
locations bit-for-bit before/after compression. Subsequent compiler-memory
changes require their own validation and are not covered by this count.

## Remaining scope

This dictionary removes redundant storage, not the underlying patch-per-glyph
and hidden-axis growth. The remaining 32/90 MB files are still research probes.
Full-font applicability, direct unshaped glyph access, subset behavior, system
hidden-axis defaults and current DirectWrite execution are not certified here.
The PR remains Draft. No full-font or Windows success follows from these results.

The existing upstream source/license investigation is retained in
[the open-source comparison](SWIRL_VF_OPEN_SOURCE_INTERPOLATION_20261103.md).
This pass is independently implemented; it imports no upstream font or source.
