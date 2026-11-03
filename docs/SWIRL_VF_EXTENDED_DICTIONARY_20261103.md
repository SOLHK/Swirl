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
platform skips. At this code checkpoint, full real-font native revalidation
is still running; these sizes alone are not acceptance. The two runs use
exactly the preceding 24,713 / 28,570 physical requests, checked for equality,
and obtain fresh CoreText, HarfBuzz, fontTools and Apple HVF observations.

This changes storage cost within the existing research representation. It
does not resolve original physical-axis mapping, per-cell glyph capacity,
DirectWrite nested-blend execution, or full-font production acceptance.
