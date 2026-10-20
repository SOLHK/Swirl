# Swirl-VF precision continuation: verified checkpoints

Branch: `work/core-completion-20261017` only. This continuation starts at
`056f7ea6dc7cf3a703da63e8522b89d33d1166f4`, not the older prompt baseline.
All concurrent Core changes remain in ancestry. No UI, animation or Core source
is changed. Original input was rechecked: 61,473,880 bytes, SHA-256
`39d42acd292ed5c9de5cf185b54a3c460630d610a718ed84c9e4f148e226f890`.
The input and all Apple-derived private data remain outside this repository.

## A1: preserve the existing replay solution; close a strict-path omission hole

The existing v2 verifier remains the production replay implementation. It
predeclares T/T(T) before native requests, checks an exactly stable replay echo,
compares every requested GID's complete raw paths and metrics with zero
tolerance, and returns the original observations only after the batch passes.
The earlier 91-batch / 5,824-observation original run remains a finite sampled
result, not complete user/design mapping or all-GID acceptance.

An independent counterexample exposed a different issue in the default Swift
strict path: a missing WDTH report at requested `500.0000005` was filled with
the default `500` and accepted by the existing `1e-6` numeric test. This
contradicted the explicit rule that only exact defaults may be omitted. This
is a validator counterexample; it is not claimed as an observed source-font
CoreText response. The v2 Python adapter already rejected this case.

`coretext_extract.swift` now separately requires the nondefault axis to be
present and retains the same `1e-6` numerical check and error code. It calls a
shared Swift helper, allowing original synthetic regression inputs to execute
the exact production validation code. The diagnostic GUARD contract is updated
with it, so observation-only helpers still remove the whole strict check rather
than accidentally adopting a partial acceptance rule.

`check_coretext_axis_guard.py`, invoked by the existing native test, compiles
the production helper verbatim and executes 22 independent cases: omitted and
explicit defaults; all three axes just above/below the default, including the
next binary64 value; explicit values inside/outside the unchanged tolerance;
exact nondefaults; the known `600.5859375 -> 600.5859` mismatch; and an absent
requested coordinate. Passing this logic test alone never claims that an actual
font instance or its metrics pass.

Baseline local regression: **320/320 Python tests, zero skips, 6/6 audits**,
using Python 3.12.14, fontTools 4.61.1, NumPy 2.2.6 and uharfbuzz 0.53.3.
After this fix: **324/324 Python tests, zero skips, 6/6 audits**; the full suite
completed in 12.780 seconds and `git diff --check` passed.
The new Swift cases need the exact pushed source on xcode-27; Linux has no
CoreText/Swift runtime. **Native verification is pending in this implementation
checkpoint.** The next evidence entry must record its exact commit and final
Actions result before calling this fix natively verified.

## Newly retrieved prior evidence (not new execution in this continuation)

- At exact source `056f7ea6dc7cf3a703da63e8522b89d33d1166f4`,
  [39374382394](https://github.com/SOLHK/Swirl/actions/runs/39374382394)
  completed all three actual-layout jobs successfully. The downloaded CoreText
  artifact 12243395032 has ZIP SHA-256
  `9a3cb17c0f0bb970a86eca90defc14e7318e0fc947018f7d2994c75431b7f9e1`.
  Its six fixture processes completed 2,016 layout calls, 1,764 paired glyph
  comparisons, zero native errors, zero GSUB/regional differences and zero
  source/candidate raw-metric differences. This confirms the earlier fixture
  registration repair's execution, not production origin equivalence.
- Same-source [39374382335](https://github.com/SOLHK/Swirl/actions/runs/39374382335)
  passed Python and Windows synthetic jobs; Apple job 118469106724 still
  failed the strict raw metric check: face 0, GID 2, height 849 versus 850 at
  tolerance 0.03125. The failure is retained and must not be hidden by the new
  axis-logic tests.
- The earlier 3,048-location HVAR evidence was downloaded and its archive hash
  rechecked as `0b6323fb51d03d13f70266facd9ced88f1b06107d96077e6070cb8e3579f09ba`.
  Existing code reproduces the 141 simple-model disagreements. The previous
  normalized-16 truncation candidate has 36 other disagreements; neither is a
  complete explanation or an accepted geometry mapping.

## Next smallest task and unchanged blockers

Read the actual A1 native result, then continue A2 with the existing raw-order
avar diagnostics and independent native outlines/HVAR. Do not replace the 141
questions with a formula fitted only to archived advances. Preserve all raw
records and duplicates and the 1/32 geometry threshold.

The 849/850 raw metric failure, independent vertical X-origin representation,
all-face/all-GID reconstruction, Windows 11 and Qt/Swirl acceptance remain
unresolved. Original completed GID models: **0**; original faces: **0/32**;
accepted Apple-derived `Swirl-VF.ttc`: **not generated**. The earlier complete
two-face synthetic TTC must never be counted as the original deliverable.

Primary references reviewed for this continuation: Microsoft OpenType
[normalization](https://learn.microsoft.com/en-us/typography/opentype/spec/otvaroverview),
[avar](https://learn.microsoft.com/en-us/typography/opentype/spec/avar),
HarfBuzz's `src/hb-ot-var-avar-table.hh`, and FreeType's `src/truetype/ttgxvar.c`.
These are comparison references, not proof of Apple's undocumented behavior;
no upstream implementation is copied into the new validator regression.
