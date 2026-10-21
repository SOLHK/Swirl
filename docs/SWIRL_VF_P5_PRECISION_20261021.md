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
the best lower bound across those grids is7/208, still above1/32.
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

## Saved checkpoint and native controls

Algorithm checkpoint88b6ca4fee854bc18ccf0c5cd958fb8cbac30f6c is saved by normal
fast-forward on this branch. Its three existing automatic CI jobs passed in
[run39564242758](https://github.com/SOLHK/Swirl/actions/runs/39564242758).
No full baseline was manually dispatched. The following native-driver stage
does not change the coefficient proof or relax any strict comparison.

Actual authored32-face controls use six UPEM families,7GIDs per face, the
unchanged original numeric axis ranges and target nominal user inputs. Both
collections pass the C1 binary/table packer. Every face's serialized design
model satisfies the same continuous1/80 metric and1/6400 squared-point bounds.
The reference is already scaled5x; it is not the unscaled source's native
rounding contract.384frozen positions exercise all three axes and combinations.

Actual local HarfBuzz14.6.0 measurements retain failures:490/5376advance
comparisons,350/10752extent fields and560/12288layout fields exceed1/32,
maximum0.203125 source FUnit.768shaping runs preserve GIDs/clusters. On this
finite metric cohort, exact coordinate-composition error is0, coefficient
error1/80, reference rounding max105/1024 and target rounding max17/160.
These separate terms expose the native integer-grid effects rather than
incorrectly attributing them to coefficient-model error. HarfBuzz vertical
advance signs are converted to the VVAR magnitude before this decomposition.
Aggregate: [local controls](evidence/SWIRL_VF_P5_LOCAL_20261021.json).

A real integration defect in the new scaler was also fixed: freshly authored
avar v1 can have segments but no internal `.table`. A detached in-memory
serialization before the upstream visitor makes it valid without changing the
source.11metric-unit tests now pass, including that exact former exception.

`target_axis_transport --precision-grid 5` is an explicit new diagnostic:
it divides errors by the physical grid multiplier and counts every strict
native metric/outline failure without treating completion as equivalence.
Old q/font-level modes retain their original thresholds and behavior. The P5
workflow separately reuses the existing all-GID DirectWrite load/raster probe
on the actual bounded target, including its multi-DPI controls. Only fixed
summaries are exported; fonts/TSV/raw output/rasters remain unexported.
Windows execution was pending when that driver checkpoint was saved; actual
results follow below.

Local authored target:
`build/vf-takeover-private/p5-precision-controls-stage3/precision.ttc`,201268bytes,
SHA256f1cb8e2719028151f45c9a55bd0c850d5159c656127813146a1829efe5008451.
It is not an original PingFang conversion or Swirl-VF delivery font.

## Actual native result and retained acceptance failure

Driver checkpointf3f04cff27c87359883f6fa10f78bab3bbb0de09 is saved remotely.
Its [P5 diagnostic run39565842706](https://github.com/SOLHK/Swirl/actions/runs/39565842706)
completed both jobs; existing takeover/P4 workflows also passed. Portable CI
ran795tests+6audits. P5 has36targeted tests at that checkpoint. Success here
means model/protocol/raster completion, not strict native equivalence.

Actual Windows Server2022 Datacenter/build20348:32faces,768requests,
5376glyph pairs,37632metric fields,10752outline pairs,33792point pairs,
9216actual FLOAT/readback checks. No target FLOAT input rounding or outline
topology failure occurred. Strict failures remain:1260metric fields,
4760outline points,140requests; maximum metric error0.2 and point error
0.2000244140625source FUnit. Native parity is **FAIL** at unchanged1/32.
The separate existing loader/raster probe passed all32faces and produced10
multi-DPI/theme rasters. Raster pixel equivalence was not tested.
Aggregate: [Windows diagnostic and render scope](evidence/SWIRL_VF_P5_WINDOWS_20261021.json).

A new executable minimal case isolates that amplification. For authoredGID2,
design positions q=(63/16384,3/16,0),r=(63/16384,1,0), the exact source/target
HVAR models are299515/1024 and1497639/5120: difference1/80. At the same physical
HarfBuzz output scale they actually return18714and18726 in26.6 units,
difference3/16FUnit. Both fonts are legal and use unchanged target nominal
coordinates; the candidate's continuous-model bound still passes. This is a
retained raw-native failure, not a target user-coordinate fix. The bounded
test file now has7passing regressions, including the explicit reproduction of
failed native parity. That case is also frozen into the next32-face native
cohort; it is not fitted away.

The workflow now has a separate final strict-native acceptance step after
successful load/render measurement. It checks the same1/32 result and must
fail while these native discrepancies remain. Fixed summaries are still
uploaded with always(); no failure is converted into an acceptance pass.
