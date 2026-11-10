# B1 independent native results: unit control and original refusal

## Terminal run and unaltered acceptance

Native run [39403338270](https://github.com/SOLHK/Swirl/actions/runs/39403338270)
checked out **aeb2574879ca76290f9e22c2e319f27f422e7ae6** on
macOS 27.0.1 arm64. The workflow finished **failure**:

| Job | Terminal result | Meaning |
| --- | --- | --- |
| Python 118563182640 | success | 572 tests run, 565 pass, 7 optional HarfBuzz skips; 6/6 audit tests pass |
| apple-followup 118563371013 | success | A complete diagnostic experiment, not metric acceptance |
| apple-original-ablation 118563371147 | failure | Private variant rejected at startup; original production representation still fails |

No measured value, tolerance, production extractor, production rebuilder, A3
mapping or D1 test changed. Synthetic strict metric acceptance is **FAIL**.
Original reconstruction remains **0/32 faces**.

## Exact coordinate readback and the four channels

The auxiliary request finally exposes the prior rejection. In original HGHT
user units, requested **0.828125** (binary64 `3fea800000000000`) is reported by
CoreText as **0.8281** (`3fea7fcb923a29c7`). The exact equality guard rejects it
before accepting any metric. This observation alone does not prove where
CoreText changes the coordinate or that outline interpolation used 0.8281.

Only the synthetic fvar HGHT user range was reparameterized by 16384; all
normalized coordinates and frozen predictions stayed unchanged. The successful
run contains 16 fixtures, **550 fixture-coordinate observations (52 distinct
normalized coordinate pairs), 1,100 raw records and 550
exact forward/reverse pairs**. All font/table, requested user-axis, size and
matrix identity guards remain strict.

The 51 complete prefix rows of the earlier failed run compare exactly with
the corresponding new-unit rows: **204/204 channel comparisons**, including
binary64 bits, across direct advances, vertical translation, witness path and
vertical layout. The earlier failed 52nd row remains unmeasured and unpaired;
the old partial report is never promoted to native acceptance.
Font-identity objects are excluded from the cross-unit channel comparison and
are independently verified against each variant's own source table bytes.

All 550 witness WDTH inferences match exactly. The 448 geometrically observable
HGHT inferences match exactly. The other 102 records are explicitly
phantom-only controls with unchanged visible top/bottom, so their outlines
cannot independently identify HGHT. There are zero witness failures and zero
layout/direct-advance disagreements.

An independent audit of the archived raw records (not a re-use of the analyzer
implementation) verified 110,176 binary64 paths in 32 raw files, all 550 complete
forward/reverse rows and their relative bit maps, and the 204 cross-unit channel
comparisons.

## Height: what is supported and what is not fixed

Let R mean nearest integer with halves away from zero, U be UPEM, and y the
normalized HGHT coordinate. The post-stage-1, pre-follow-up candidate was:

```text
H = 1000 + R(60*y) - R(-90*y)
gvar candidate = trunc(floor(H*65536/U)*U/65536)
VVAR candidate = trunc(1000 + 150*y)
```

All **308/308 gvar-path** and **242/242 VVAR-path** observations match these
frozen height predictions, **550/550 in total**. This is a finite behavioral
model, not proof of Apple's internal data type or operation order.
In particular, integer vertical outputs do not uniquely identify a 16.16
representation; other quantizers can coincide on these samples.

The new preselected normalized y=53/64 counterexample is decisive against a
universal nondefault minus-one rule:

| UPEM | gvar result | VVAR result | continuous phantom height |
| ---: | ---: | ---: | ---: |
| 1000 | 1125 | 1124 | 1124.21875 |
| 1024 | 1125 | 1124 | 1124.21875 |

The first-stage synthetic endpoint observation is explained by the same candidate: the
stored/interpolated phantom difference 850 yields native 849 at UPEM 1000 but
850 at UPEM 1024. VVAR changes the height computation path; it gives 850 at that
endpoint but truncates fractional heights elsewhere. Neither observation is a
general precision repair.

These are raw CoreText values at a point size equal to UPEM. The binary64
records and actual layout gaps agree with those values; no JSON conversion or
post-processing subtraction is needed to produce the failure. Storage
integers, continuous design-space references, raw API points, their exact
point-to-design conversion and layout positions remain distinct in the full
report.

**All 550 fresh samples still fail at least one unchanged strict metric
comparison against the intended continuous metrics.** A height-model match is
not a metric-equivalence pass.

## Origin Y: a selected hypothesis is rejected

The selected gvar candidate used continuous visible top B and separately rounded
phantom top P:

```text
selected before follow-up: B + P - ceil(B)
predeclared competitor:    B + P - roundHalfAway(B)
```

The selected candidate has **96 counterexamples** and is rejected. Its
algebraically equivalent bearing-floor form is rejected as well. The
predeclared nearest-bbox competitor matches all **308/308 gvar-path** samples;
the selected VVAR/VORG paths match their remaining 242 samples. No predictions
were rewritten in the runner or in the archived reports.

For these positive B values, the surviving expression also equals
`B + ceil((P-B)-1/2)`. Therefore these measurements do not distinguish
nearest-bbox rounding from an equivalent bearing-based calculation. The model
must not be reported as a located internal implementation.

## Origin X: presentation behavior versus stored fields

The odd stored advance 1001 control resolves a behavior obscured by even
advances. Without VORG, the default horizontal center is **500.5**. Adding only
the synthetic VORG table makes the observed vertical X **500** at every tested
WDTH, for both UPEMs. The 24 VORG follow-up records all keep X=500 while current
horizontal advances vary.

That is consistent with an integer half of the stored advance. It does not
uniquely distinguish truncation from every possible half-integer tie rule or
prove a specific internal lookup path. VORG itself stores vertical Y origins,
not an X coordinate. These glyf/VORG fixtures are explicitly nonportable
diagnostic controls: the OpenType VORG contract says a TrueType glyf font must
ignore VORG. They are not proposed output fonts.

## Original font: 60 / 0 / 60, not 60 times three

The unchanged production native oracle and exact replay adapter were used.
The original SHA-256 is
`39d42acd292ed5c9de5cf185b54a3c460630d610a718ed84c9e4f148e226f890`.

| Fresh session | Unique metric records | Result |
| --- | ---: | --- |
| Original | 60 | All 32 physical faces bound; 15 verified batches; final summary/EOF/exit verified |
| Private directory-only no-VORG variant | **0** | Rejected at native startup |
| Original repeat | 60 | Same verification; every metric and binary64 value repeats exactly |

The variant preserves file length 61,473,880, all 640 retained table payloads
and all bytes outside the 32 edited directories. No fontTools save is used;
raw avar order and bytes are untouched. Its SHA-256 is
`9a64e597ba24e0f012504e4371281f82cbab0a90a2cca315e5451940d1c2234a`.
The temporary variant and private protocol files were deleted. Neither
original nor variant font or original outline data is published.

The public failure is only `native_startup / ReconstructionError /
native oracle startup failed`. This is insufficient to identify descriptor
enumeration, font rejection, source identity or protocol failure. It proves
neither successful no-VORG loading nor a measured VORG effect on the original.
No cross-variant metric differences are available. A separate startup-only
experiment is needed, including an unchanged private-copy control.

Both original sessions contain the same **24/60 unique failures** in the
unchanged production phantom representation check, tolerance 1e-5 FUnit.
The accumulated 48/120 count is those same failures measured twice:

| Position / stored advance | Unique failures | native vertical X minus current advance/2 |
| --- | ---: | ---: |
| WDTH minimum / 1000 | 9 | +100 |
| WDTH maximum / 1000 | 9 | -100 |
| WDTH minimum / 600 | 3 | +60 |
| WDTH maximum / 600 | 3 | -60 |

All 60 original native heights are 1000 and Y origins are 860. This bounded
sample does not reproduce 849 in an original glyph and must not be called an
original-font validation of the synthetic height model. All 60 X values equal
horizontal origin X plus half the stored hmtx advance. Current horizontal
advances take values 480, 600, 720, 800, 1000 and 1200.

Original A/A repeat checks are numerically and bit-for-bit exact. The private
variant contributes zero accepted records. The overall workflow remains red.

## Durable evidence and integrity

The log files in [followup/](followup/) preserve the exact connector-decoded
UTF-8 job logs, including their initial BOM. JSON summaries are parsed from
their explicit markers; complete numerical provenance is in the raw ZIP.

| Archive | Bytes | Entries | SHA-256 |
| --- | ---: | ---: | --- |
| [followup-native-12255412252.zip](archives/followup-native-12255412252.zip) | 1509092 | 107 | `1d1e7528d78b504a2b14029f56e3576a1a61f2e815ab279e77b21e13599c3d06` |
| [original-ablation-12255752467.zip](archives/original-ablation-12255752467.zip) | 10507 | 4 | `61d2b4f33c68873eb41e3c75aac488ed489419d98b4ed25b25e141d7be7106b4` |

Both archives were actually downloaded, SHA-256 matched to the GitHub artifact
digest, every ZIP member CRC checked, and font payload/path-traversal entries
excluded. The original 849/850 failure log, first-stage raw ZIP, failed
follow-up raw ZIP and every prior prediction remain preserved.

This stage fixes diagnostic observability and completes the coordinate
discriminator. **It does not fix original metric equivalence, establish an
acceptable production representation, or unblock any original face.**
