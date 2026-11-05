# Bias-preserving CFF2 dictionary extension

The initial lossless pass stores at most 215 local helpers, whose operand and
callsubr together occupy two bytes. CFF2 keeps subroutine bias 107 while the
bank contains at most 1,239 entries. Entries 215 through 1,238 need a two-byte
integer operand and a one-byte call, so a second tier can still save storage
([CFF2 subroutine specification](https://learn.microsoft.com/en-us/typography/opentype/spec/cff2#subroutines)).

`cff2_structural_pool.py` preserves the first tier and scores the additional
patterns using their actual three-byte call cost. Patterns without positive
net savings are rejected. `compress_joint_font.py --maximum-helpers 1239`
enables this optional tier; the default remains 215. No coefficient, outline,
axis, region, glyph, arithmetic operation, or global subroutine index changes.
Every expanded byte sequence is checked before mutation. The same stack,
subroutine depth and expanded-operation limits apply. The bank is capped
before the bias changes; boundary operands and serialized/native execution of
an authored bank exceeding 215 entries have regression tests.

| GID | Original bytes | 215-helper bytes | 1,239-helper bytes | Extra bytes saved | Expanded tokens | Stack / call depth |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1166 | 58,178,796 | 32,200,320 | 28,532,496 | 3,667,824 | 146,163 | 53 / 3 |
| 19177 | 196,056,396 | 89,678,604 | 80,682,776 | 8,995,828 | 140,360 | 44 / 3 |

The reductions from the actual starting fonts are 50.96% and 58.85%. These
are measured serialized file sizes, not compression estimates. Building the
two extended banks takes 32.320 / 115.163 seconds including save/reload checks,
with peak process RSS 377,864,192 / 1,163,624,448 bytes. These are single runs
on the shared host; they do not demonstrate an RSS improvement from enlarging
the dictionary. The measured per-glyph compiler build figures in the main
scaling report concern the unchanged model-to-font stage, before this pass.

[Encoding evidence](evidence/SWIRL_VF_EXTENDED_DICTIONARY_20261103.json)
retains source/candidate hashes, non-CFF2 table equality and execution guards.
The full local regression suite executes 1,069 tests: 1,062 pass and seven
platform skips. Full real-font native revalidation has now completed:

| GID | CT/HB requests each | Independent positions | CoreText maximum | HarfBuzz maximum | fontTools maximum (512) |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1166 | 24,713 | 21,649 | 0.020462832574 | 0.018338193258 | 0.020435461376 |
| 19177 | 28,570 | 22,481 | 0.020124576588 | 0.018596886107 | 0.013433502069 |

All outline, control-point, topology, direction, closure, selection and advance
checks pass at the unchanged 0.03125 original-FUnit threshold. The runs execute
exactly the preceding physical requests, checked for equality, with fresh
CoreText, HarfBuzz, fontTools and Apple HVF observations. CoreText's entire
path and advance arrays match the previous 215-helper encoding exactly at
every request. All three engines' per-observation verdicts, errors and selected
GIDs are also exactly equal. Prior receipts remain in the
[anchor evidence](evidence/SWIRL_VF_FINAL_ANCHORS_20261103.json). These are the
same qualified joint-q results; physical-source-axis parity is still unproved.

## Measured runtime cost

An initial timing run overlapped native verification jobs. It is retained in
full. A second sequence measured original, extended and default encodings
after those jobs finished, with three fresh processes per engine and 128
requests per mode per process. OS file cache is uncontrolled; these are short
same-host comparisons, not a stable application latency estimate.

| GID | Engine | Original outline median, us | 215 helpers, us | 1,239 helpers, us | Original / extended peak RSS bytes |
| --- | --- | ---: | ---: | ---: | ---: |
| 1166 | HarfBuzz | 178.042 | 217.938 | 228.292 | 171,966,464 / 112,738,304 |
| 1166 | CoreText | 92.354 | 117.427 | 125.906 | 84,869,120 / 55,230,464 |
| 19177 | HarfBuzz | 325.146 | 384.136 | 401.729 | 451,117,056 / 220,430,336 |
| 19177 | CoreText | 151.229 | 186.823 | 198.166 | 219,611,136 / 104,235,008 |

The extended tier adds about 4.6–7.2% outline time beyond the default dictionary
in this sequence; total outline time is about 24–36% above the original.
Shaping medians remain approximately 15/18 us in HarfBuzz and 408/255 us in
CoreText. Graphics-load medians are 2.058/5.640 ms in HarfBuzz and 1.859/1.986 ms
in CoreText for the extended fonts; read and instance costs are separate in the
receipt. This is an explicit storage/runtime tradeoff, not a drawing speedup.
Default/omitted computational axes match in all 384 comparisons per font and
engine; direct unshaped base-GID access still differs in all 384. Enlarging the
dictionary does not alter that access-path dependency.

This changes storage cost within the existing research representation. It
does not resolve original physical-axis mapping, per-cell glyph capacity,
DirectWrite nested-blend execution, or full-font production acceptance.
