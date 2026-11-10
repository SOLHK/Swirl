# B1 stage 1: native evidence, not an acceptance claim

Measured commit: `9836e89130694fdc336c4f4d7de22259c51741f6`.
Native workflow: <https://github.com/SOLHK/Swirl/actions/runs/39399674995>.
Terminal workflow conclusion: **failure**. The Python and native discrimination
jobs succeeded; both unchanged strict gates failed. No original font was rebuilt.

## Scope and counts

| Check | Actual result |
| --- | --- |
| Source unit tests | 496 run; 489 passed, 7 optional HarfBuzz skips |
| Audit unit tests | 6/6 passed |
| B1 unit tests within source total | 48/48 passed |
| Self-authored fixtures | 26: 13 table/phantom variants at each UPEM |
| Native unique observations | 624 |
| Independent forward/reverse processes | 52 |
| Native raw records / exact replay pairs | 1,248 / 624 |
| Witness geometry comparisons | 624/624 within unchanged 1/32 FUnit |
| Actual vertical layout gap versus direct API advance | 624/624 exactly equal |
| Strict synthetic metric comparisons | 468/624 failed; includes deliberately nonstandard VORG controls |
| Original physical-face identities | 32/32 verified |
| Bounded original metric sampling | 15 requests, 60 records; all batches finalized |
| Original production X-representation failures | 24/60 |
| Original source-table reference availability | 20 comparable; 40 unavailable due to ambiguous raw avar anchors |
| Original strict comparisons where reference is available | 12 passed; 8 failed, all vertical X |
| Original reconstructed faces / font files produced | 0/32 / 0 |

The original probe's exact replay adapter internally executed 30 requests and
120 glyph extractions. This does not double the 60 independent metric samples.
The 40 unavailable source references are neither passes nor measured failures.

## Four-channel result

At point size equal to UPEM, the raw points already numerically equal design
units. The Swift diagnostic preserves both the raw JSON number and its IEEE
binary64 bits; the Python analyzer retains an exact rational conversion basis.
It applies no rounding or measurement correction. The four observations are
direct advance, direct vertical translation, independently measured witness
path, and actual vertical CTFrame glyph positions. Each layout run verifies its
font table hashes, axes, size, matrix and nominal glyph identity.

At WDTH=0, ordinary gvar fixture heights were:

| HGHT | Continuous phantom height | UPEM 1000 raw API | UPEM 1024 raw API | VVAR raw API, both UPEMs |
| --- | ---: | ---: | ---: | ---: |
| -1 | 850 | 849 | 850 | 850 |
| 0 | 1000 | 1000 | 1000 | 1000 |
| 0.25 | 1037.5 | 1037 | 1038 | 1037 |
| 0.375 | 1056.25 | 1056 | 1057 | 1056 |
| 1 | 1150 | 1149 | 1150 | 1150 |
| -0.625 | 906.25 | 905 | 906 | 906 |
| 0.125 | 1018.75 | 1018 | 1019 | 1018 |
| 0.625 | 1093.75 | 1093 | 1094 | 1093 |

The raw 849 has bits `408a880000000000`; raw 850 has bits
`408a900000000000`. The actual layout gap equals these raw advances, so the
observed loss is not introduced by JSON serialization, the Python conversion,
or a comparison-only display layer. UPEM 1024 removes this endpoint loss but
does not restore fractional metric precision. VVAR selects different advance
behavior and restores the endpoints, but still truncates fractional heights in
these measurements. Neither is a verified precision repair.

The shifted-phantom and fixed-outline controls retain the same height behavior.
HVAR changes horizontal advance and its derived X origin, not vertical advance.
The hhea ascent control changes global CT ascent, not the tested glyph advance;
vhea ascent and the three OS/2 typo/USE_TYPO_METRICS controls produce no change in
the measured glyph channels. These statements are limited to this exact matrix.

## VORG and X-origin source selection

Adding only VORG to the self-authored glyf fixture makes native Y equal the
stored VORG value 911 and makes native X remain 500 while width varies. At
UPEM 1024 this isolates an exact 100 FUnit difference at the width endpoints.
At UPEM 1000 the comparison also includes the separate horizontal quantization
effect (maximum difference 100.006103515625). VORG itself stores only Y, not X.
This is evidence of a CoreText table-dependent origin path, not an X field in
VORG and not a portable OpenType repair: the VORG specification says glyf
consumers must ignore this table. See [primary sources](PRIMARY_SOURCES.md).

In the unmodified original, all 24 width-endpoint samples fail the unchanged
production X representation check: the native origin stays at half the default
stored width, while the varied advance becomes 800/1200 or 480/720. The errors
are respectively +100/-100 or +60/-60 FUnit. The 8 comparable face-31 endpoint
records fail only vertical X; their other compared metric fields match.
Faces 0 and 15 have ambiguous raw avar default anchors, so their source-table
reference is deliberately withheld. Original source SHA-256 remains
`39d42acd292ed5c9de5cf185b54a3c460630d610a718ed84c9e4f148e226f890`.

## Hypothesis status and next independent experiment

No original preregistered height hypothesis explains every first-stage sample.
Those rejected hypotheses and the original training/holdout labels remain
unchanged. A new candidate, inferred after this run, rounds signed phantom
**deltas** to nearest with half ties away from zero, differences those deltas,
then applies UPEM-dependent normalization quantization and an integer truncation.
A 16.16 normalization formula is consistent with the evidence, but these final
vertical integers do not uniquely identify the internal bit width. Other power
of two denominators can be observationally identical here. This is a falsifiable
behavioral model, not proof of Apple's implementation and not a correction.

All first-stage points, including the former holdouts, are now seen data for
that new candidate. A separately frozen follow-up uses 17 new height coordinates,
new width coordinates, VVAR and fixed-outline controls, and VORG with odd stored
width. A private original-font VORG-directory ablation will separately test the
original-source causal link while preserving all remaining table payloads.

## Evidence provenance

The three `.log` files below preserve the decoded GitHub job-log text exactly as
returned, including its leading BOM and line endings. The two summary JSON files
are parsed from named compact JSON log records and pretty-printed; they are
explicit derivatives, not downloaded artifact files. File byte counts and
SHA-256 values are in [stage1/provenance.json](stage1/provenance.json).

- [Native job 118551140161](stage1/native-job-118551140161.log)
- [Strict-gate job 118551394339](stage1/strict-job-118551394339.log)
- [Python job 118550962741](stage1/python-job-118550962741.log)
- [Native compact summary](stage1/native-summary.json)
- [Original bounded metric summary](stage1/original-summary.json)

The original 849/850 failure from run 39394041915 remains separately preserved
in `legacy-39394041915-apple.log`; it has not been replaced by this rerun.
GitHub's uploaded discriminator artifact is 12254476529 and its reported zip
digest is `5914f830d48c145db4e164305efc83604d60b7213401b2c09b5670d1063c6c54`.
The strict artifact is 12255036417 with reported digest
`51de82e316455488e89380c3f19333c4a6c6647768862a4998814cfbc6f9e88f`.
These are server-reported artifact digests, not a claim of locally downloaded
archive verification. Raw scalar, path, run and layout records are in those
artifacts; the log summaries expose the bounded results without font binaries.

No production extractor, rebuilder, mapping, Windows implementation, tolerance,
source metric replacement, or original source bytes changed in this stage.
