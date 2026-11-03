# SwirlVF joint compiler scaling — 2026-11-03

This work continues remote `cccc0a39090079542f2e3af064bfce328ed66b5e` on
the existing PR #53. It preserves the independently accepted rational-projection,
localized-tricubic, avar2 and required-GSUB architecture. These are selected-glyph
research fonts, not a full-font release. Private inputs, outlines, coefficients,
coordinates and raw transcripts remain outside Git.

The completed [representative corpus](SWIRL_VF_CORPUS_20261103.md) records
all 14 preselected cases: nine pass the qualified joint-q contract, including
six new unique GIDs; five fail. The stage ledger includes failed attempts and
resumed fits. Optional further storage savings are documented in the
[bias-preserving dictionary extension](SWIRL_VF_EXTENDED_DICTIONARY_20261103.md).

**Axis-contract qualification:** the successful outline comparisons below use
the inherited joint post-avar **q-space** contract. The original raw weight map
has conflicting duplicate records; a decoded fontTools dictionary does not
preserve them. Its reserialized map also lacks a mandatory identity endpoint.
Thus these outline results do **not** establish original physical-user mapping
parity or fully conformant installable fonts. The corpus exposed this through
real HarfBuzz advance failures; see checkpoint 2. Earlier references to source
avar preservation mean dictionary preservation, not raw-record preservation.

The latest post-optimization anchor run is recorded in
[the final anchor receipt](evidence/SWIRL_VF_FINAL_ANCHORS_20261103.json).
It validates the optional 1,239-helper files, now 28,532,496 / 80,682,776 bytes,
and retains the preceding default-dictionary receipts. Their complete CoreText
paths and all engines' per-observation verdicts are exactly equal.
The shared manifest contains 4,096 independent random triples per glyph
(seeds 2026110861 / 2026110863) plus the entire earlier request replay,
including historical maxima. Both encodings execute this manifest afresh
using the corrected serialized fontTools GSUB selector.
No fitting occurs in verification and no previous observed outline is reused
as the new candidate or source observation.

| GID | CT/HB observations each | Unique independent positions | CoreText maximum | HarfBuzz maximum | fontTools maximum (512) |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1166 | 24,713 | 21,649 | 0.020462832574 | 0.018338193258 | 0.020435461376 |
| 19177 | 28,570 | 22,481 | 0.020124576588 | 0.018596886107 | 0.013433502069 |

Both serialized compressed fonts pass control-point, topology, direction,
closure, selection and advance checks. Repeated or training-overlapping
requests remain tested but excluded from independent counts. All errors are
original FUnits, with the unchanged 0.03125 limit. The final local suite runs
1,069 tests: 1,062 pass and seven platform skips, plus six parser-audit passes.
Executed Windows incompatibility controls remain failures and are reported
separately; they are not relabelled regression-suite passes.


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

The later [capacity and native-access audit](SWIRL_VF_SCALING_COMPATIBILITY_20261103.md)
records actual failing Windows server tests, subsetting results and a
conditional glyph-index limit. These replace the initial NOT_RUN status below.

This dictionary removes redundant storage, not the underlying patch-per-glyph
and hidden-axis growth. The remaining 32/90 MB files are still research probes.
Full-font applicability, direct unshaped glyph access, subset behavior, system
hidden-axis defaults and current DirectWrite execution are not certified here.
The PR remains Draft. No full-font or Windows success follows from these results.

The existing upstream source/license investigation is retained in
[the open-source comparison](SWIRL_VF_OPEN_SOURCE_INTERPOLATION_20261103.md).
This pass is independently implemented; it imports no upstream font or source.

## Checkpoint 2: bounded field storage and sampling

`sparse_polynomial_fields.py` stores only columns with an exactly nonzero
coefficient, including arbitrarily small nonzero values. Evaluation retains the
original dense operand shape and contraction order for one cell at a time.
Legacy archives stream one cell at a time; new archives stream ragged columns
without a giant concatenation. `localized_projection_font.py` materializes only
the output glyph being encoded. Clamp localization and fixed-point rounding are
unchanged. Every non-`head` table is byte-identical to a fresh old-code build;
`head` differs only in timestamps/checksum adjustment.

| GID | Old build peak RSS | Streaming build peak RSS | Reduction | Old / new build seconds | New encode / save seconds |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1166 | 2,382,987,264 | 1,525,874,688 | 35.97% | 141.246 / 113.480 | 82.156 / 30.639 |
| 19177 | 7,246,495,744 | 4,444,078,080 | 38.67% | 434.499 / 399.929 | 292.366 / 103.900 |

These are separate measured macOS processes on 16 GB RAM, not theoretical
estimates. Other research jobs were concurrent; timings are individual runs,
not a stable performance distribution. RSS is not macOS memory footprint.
Compression remains a separate bounded pass and produces the same sizes as
checkpoint 1. Fresh streaming builds were compressed, reloaded and validated:

| GID | Seed | CT/HB observations each | Unique independent | CoreText maximum | HarfBuzz maximum | fontTools maximum (512) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1166 | 2026110753 | 12,615 | 11,086 | 0.020462832574 | 0.017497873540 | 0.016397893012 |
| 19177 | 2026110757 | 14,902 | 11,597 | 0.017883106686 | 0.017048651460 | 0.013912359161 |

All reported geometry, topology, closure, direction, selection and advance
checks pass at the unchanged 0.03125 FUnit threshold. Each run includes 4,096
new random triples plus the complete historical physical-request replay.
Hashes, categories, counts and stage timings are in the
[streaming receipt](evidence/SWIRL_VF_STREAMING_20261103.json).

`ProjectionSource.parameter_values()` avoids allocating direction fields while
sampling the rational projection parameters. On the preselected maximum-factor
GID 35709 (12 factors), 16,384 samples produce exactly the same parameter bytes:
11.486 to 5.381 seconds; RSS 435,781,632 to 252,362,752 bytes. Zero-factor glyphs
need no sparse parameter grid, hidden axes or avar2 store.

Field refinement skips quadratic tangent contacts handled by the separate
parameter model and deduplicates exactly identical chord probes. Same-sign
piecewise operations and zero-angle rigid transforms use their exact limits.
A 32-cell GID 46459 profiling experiment is 65.567 to 38.654 seconds, with
identical bounds, coefficients, training receipts and 4,096 holdout results.
That small model still fails precision; it is a CPU comparison, not acceptance.
Resumed refinement retains every previous fitting receipt and does not use old
holdout failures to train. Holdout evaluation streams in batches without
reducing its sample count.

Three fresh-process native timing repetitions use 128 fixed-seed coordinates
each. Explicit/omitted computational defaults give identical results in all
384 comparisons per engine/font. CoreText peak RSS drops from 85,229,568 to
59,228,160 bytes for 1166 and 219,709,440 to 113,344,512 for 19177. HarfBuzz peaks
drop from 172,294,144 to 120,209,408 and 451,428,352 to 238,616,576. Timing
distributions are retained in the receipt; OS file cache is uncontrolled.

The extra subroutine calls have a measured execution cost. Median outline
extraction time per request, in microseconds, is:

| GID | Engine | Original | Compressed |
| --- | --- | ---: | ---: |
| 1166 | HarfBuzz | 213.625 | 263.656 |
| 1166 | CoreText | 100.812 | 127.771 |
| 19177 | HarfBuzz | 400.563 | 445.875 |
| 19177 | CoreText | 160.240 | 201.917 |

Shaping medians remain about 19/22 microseconds in HarfBuzz and 434/275 in
CoreText after compression. These three-process measurements expose the
storage/runtime tradeoff; they do not establish application-level latency or
stable percent improvements. Load, instance and shaping timings remain separate
in the machine-readable receipt. Compression does not claim faster drawing.

Direct, unshaped base-GID access differs from normal shaped output in all
384 comparisons per engine/font. Hidden flags are a UI recommendation, not a
read-only mechanism ([fvar specification](https://learn.microsoft.com/en-us/typography/opentype/spec/fvar)).

The first corpus cases exposed physical mapping failures that the two anchors'
constant weight advance had masked. GID 50/117 geometry passes but HarfBuzz
source advance differs by up to 15/23 FUnits. Copying raw avar bytes back fixes
GID 50's HarfBuzz advance but breaks both native outline comparisons, reaching
17.937 FUnits. This is not a valid repair. The new aggregate raw-axis audit and
verifier scope field prevent joint-q success being mistaken for user-axis
equivalence. The pre-existing [axis mapping investigation](SWIRL_VF_P4_FONT_MAPPING_20261021.md)
remains relevant; no endpoint or precision requirement is silently relaxed.

Checkpoint 2 executes 1,044 regression tests: 1,037 pass, seven platform skips;
six parser audit tests also pass. A newly extended tiny-angle test initially
used a positive-only bound for negative extrapolation; its expected value now
includes the analytical first-order rotation term and uses a tighter 1e-13
tolerance. The 0.03125 acceptance threshold and every existing case remain.
The region-count guards now enforce the specification's reserved high bit:
at most 32,767 regions, not 65,535
([common variation formats](https://learn.microsoft.com/en-us/typography/opentype/spec/otvarcommonformats)).
