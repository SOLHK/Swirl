# P6 native rounding checkpoint (2026-10-21)

Branch: `work/vf-takeover-abc-20261021`; parent checkpoint
`9fff65027d6642f78f793150254c20e13e7ada2c`. PR #24 remains draft.

## First executable fix

`exact_rebase` reuses the existing bounded rebase engine and requires zero
error in the independent certificate of the serialized/reopened continuous
gvar/HVAR/VVAR models. It does not change the existing bounded selection,
1/32 limit, native gates, original data or production builder permission.

For the authored source UPEM1000, weight coefficient1, clipped weight span3/16,
the first exact legal integer multiplier is16 (UPEM16000). At GID2,
q=(63/16384,3/16,0), r=(63/16384,1,0), the old5x model error1/80 and
HarfBuzz advances18714/18726 become exact model error0 and advances18720/18720
at the unchanged physical output scale64000 (64 units/source FUnit).
This removes a coefficient-induced rounding mismatch for this case. It is
not a proof of native parity throughout the parameter domain or of original
Apple font conversion. User-coordinate quantization remains separate.

At source UPEM1144 this fixture needs16x but only14 integer multipliers are
legal: the new path explicitly refuses every approximate grid. This is a
restriction of this representation, not a universal OpenType impossibility.

Local targeted tests: `test_exact_rebase.py`2 PASS and unchanged
`test_bounded_rebase.py`7 PASS. Native Windows/CoreText trace and exact
rounding-bound evidence are the next checkpoint; NOT_RUN for this new path
at this checkpoint. All P5 strict native failures remain recorded.

Primary implementations reviewed before the fix:

- [HarfBuzz14.6 hmtx/HVAR](https://github.com/harfbuzz/harfbuzz/blob/14.6.0/src/hb-ot-hmtx-table.hh)
- [HarfBuzz14.6 font advance callbacks](https://github.com/harfbuzz/harfbuzz/blob/14.6.0/src/hb-ot-font.cc)
- [fontTools public instancer](https://github.com/fonttools/fonttools/tree/4.61.1/Lib/fontTools/varLib/instancer)
- [OpenType head UPEM range](https://learn.microsoft.com/en-us/typography/opentype/spec/head)

No upstream code is copied. Only authored control fonts are used. Original
first-face reconstruction remains blocked; no `Swirl-VF.ttc` is produced.
Windows11, Qt/Swirl and third-party application acceptance are NOT_RUN.
