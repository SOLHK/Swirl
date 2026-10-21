# P5: bounded coefficient representation and continuous design-model error

Work stays in `work/vf-takeover-abc-20261021` and its existing isolated worktree.
Fresh remote/local starting HEAD is5c187caecaef26d49fb909855643fad8d1532d9a,
with no uncommitted changes. A3/B1/C1 remain66594e9/7902cdb/c0fe6c4; their
latest handoffs and P4's source/failure evidence were read. No other branch is
written, merged, rebased or deleted. PR23/24 stay draft and unmerged.

## Actual root cause and font-level fix

The unchanged P4 regression reconstructs the original authored3/16 coefficient
at an eightfold endpoint as2/8 instead of3/16, error1/16. This is coefficient
integerization, not a source input change or a rasterizer artifact. At a legal
normalized HVAR corner each region scalar is0or1; integer hmtx plus integer
VarStore coefficients remains integer. Therefore a target value1.5 cannot be
recovered by adding regions at that corner. This proof concerns HVAR advances;
it is not a claim about fractional composite outline transformations.

`bounded_rebase.py` computes exact Fraction endpoint lattice lower bounds from
decoded source metrics at all27corner/default combinations. It evaluates legal
integer UPEM grids rather than assuming a larger power of two is better. It
reuses the existing fontTools scaler/partial instancer and exact metric writer,
regenerates HVAR/VVAR from final gvar phantoms, serializes/reopens the candidate,
then accepts only an independent full design-domain coefficient certificate.
There is no tolerance option and no production gate change.

The known witness selects5x:3/16×5=15/16 rounds to1, giving source value1/5,
error1/80=0.0125, below1/32. The independent serialized model certificate proves
maximum metric error1/80 and maximum point error squared1/6400 throughout the
three-axis design cube, including all contour points and four phantoms/GID.
All six source UPEM families can use this legal grid. The separate half-domain
witness selects2x and has zero model error. Original P4 failure tests remain.
Targeted local checks:6bounded-rebase,10exact-continuum,9serialized-font and
10metric-unit tests pass; all16existing P4 model/precision regressions pass.
The old759-test suite was not manually repeated before this checkpoint.

## Independent proof and retained limits

`continuous_model.py` uses exact rational region scalars. The difference of two
tensor-product region models is multi-affine inside every cell bounded by the
union of source/target support knots and the endpoint-basis zero planes.
Absolute component error and squared point norm attain their maxima at cell
vertices. `font_model_certificate.py` extracts actual serialized/reopened
glyphs and HVAR/VVAR, verifies both advance encodings against gvar, and checks
every vertex in that exact partition. Unsupported discontinuities, IUP,
composites, bearing maps and exhausted point/global-vertex budgets fail closed.
This is a continuous proof for supplied ideal design models, not a finite
sample extrapolation. It excludes user/avar mapping, native rounding, layout,
hinting, rasterization and original HVF equivalence.

A new authored seven-coefficient fixture at UPEM1144 defeats every legal
integer grid1..14 at metric corners. It is rejected before candidate building;
it is not proof against noninteger UPEM ratios or all standard font encodings.
The old96readback failures,849/850 synthetic API discrepancy, quarter-cell and
same-FLOAT source collision remain unchanged.

## Metric units and publication boundary

`precision_metrics.py` separately scales known design-unit MVAR data while
retaining caret-slope ratios and gasp PPEM units. Aliased rows with different
units are split/remapped. VORG default and per-glyph records are scaled
explicitly. Unknown/private tags, missing base semantics and overflow are
refused. VORG remains ignored by conforming TrueType consumers; preserving its
table does not establish native vertical-origin equivalence.

The bounded coefficient path still refuses MVAR until its reparameterized
dimensionless values have a separate continuous certificate. Scaling support
is not full MVAR/native acceptance. Original first-face reconstruction,
Windows11, actual Qt/Swirl and third-party Windows software remain NOT_RUN.
No Apple font, converted font, raw glyph data or private log is published.

Primary references reviewed before implementation:
[fontTools scaler](https://github.com/fonttools/fonttools/blob/4.61.1/Lib/fontTools/ttLib/scaleUpem.py),
[fontTools partial instancer](https://github.com/fonttools/fonttools/blob/4.61.1/Lib/fontTools/varLib/instancer/__init__.py),
[region/packed-delta formats](https://learn.microsoft.com/en-us/typography/opentype/spec/otvarcommonformats),
[interpolation](https://learn.microsoft.com/en-us/typography/opentype/spec/otvaroverview),
[MVAR](https://learn.microsoft.com/en-us/typography/opentype/spec/mvar),
[VORG](https://learn.microsoft.com/en-us/typography/opentype/spec/vorg).
Public APIs and existing project code are reused without copying upstream code.
