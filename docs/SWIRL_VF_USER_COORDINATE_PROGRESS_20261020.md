# Swirl-VF user-coordinate and metric continuation

This phase starts at `b5a84bfacc48e6b2a8be8f0797f34639530766c9` on
`work/core-completion-20261017`; every push is non-forced and based on a fresh
remote head. UI, animations and Rust Core are outside the changes.

## Actual source and first native result

The uploaded 61,473,880-byte file matches SHA-256
`39d42acd292ed5c9de5cf185b54a3c460630d610a718ed84c9e4f148e226f890`.
All 32 physical faces contain 47,102 GIDs. The original remains unchanged.

Executable diagnostic commit:
`0531127a0babcd8242b9d7f81db9f5c9c0202d3c`.
Native run: https://github.com/SOLHK/Swirl/actions/runs/39359357221
Apple job 118421592043 actually used xcode-27 / macOS 27.0.1. Python and Windows
synthetic jobs passed. The unchanged strict CoreText metric gate still fails at
849 versus 850. The new precision experiment completed successfully; this is a
diagnostic completion, not metric or font acceptance.

Each of three independently generated fixture expressions was measured at 58
requests x 3 GIDs x 4 point-size scales. Neither changing measurement size
(0.25, 1, 16, 64 times UPEM) nor using a verified single-glyph CTRun eliminates
the error in source font units. For each scale:

| Original fixture expression | Glyph observations | Outside 1/32 budget | Maximum height error |
| --- | ---: | ---: | ---: |
| gvar-only | 174 | 107 | 1.3375 FUnit |
| equivalent production HVAR/VVAR | 174 | 4 | 0.3375 FUnit |
| equivalent explicit bearing maps | 174 | 4 | 0.3375 FUnit |

Explicit bearing maps improve the maximum vertical-origin error to about
0.0039453 FUnit but do not cure integer vertical advances. These observations
exclude a simple output-size/JSON-format fix. Raw API measurements must remain
distinct from exact source-table metrics. No uniform +1 correction is valid.
The new `SourceMetrics` module evaluates hmtx/HVAR, vmtx/VVAR/VORG and gvar
phantoms at explicitly supplied design coordinates. It is an independent
reference; user-axis mapping must be verified before production use.

## New original-user geometry experiment

`probe_user_axis_geometry.py` pairs actual CoreText instances constructed from
the requested user values and their API readbacks. Separately it compares each
requested instance against the already repaired HVGL evaluator under global,
falsifiable mapping candidates. It retains all 32 physical faces, the earlier
structural GID selector, endpoints/defaults, fractional and joint axis samples,
and both sides of raw avar knots. The 1/32 FUnit geometry budget is unchanged.
No per-point best-model mixture can create a global pass. Original paths remain
process-private; only coordinates, counts, GIDs and discrepancies are published.
This new experiment has not yet been declared a native pass in this checkpoint.

## Recovery for full reconstruction

`rebuild.py --checkpoint-dir /private/checkpoints` now retains already fully
verified physical faces. The manifest binds the original and oracle hashes,
relevant converter-source hashes, runtime versions, error budgets and adaptive
limits. Resumption checks cached bytes and identity before skipping native work;
the original final TTC table verification is still required. Cached TTFs are
private data, never public Actions artifacts. Six new tests include an actual
three-face synthetic build failing on face two, then resuming successfully.

Failure records now identify stage, face, glyph or glyph range, user location,
sample number and available errors. A started face is not a completed face.

The current unchanged sampling scheme needs 130,001,520 native glyph
observations before adaptive work: faces 0-19 have 27+64 locations, faces 20-23
27+46, and faces 24-31 27+54. Five minutes cannot be treated as a full-build
acceptance timeout. Shared source tables and measured throughput need attention
after the source-coordinate and metric gates are understood.

## Boundaries

No accepted `Swirl-VF.ttc` has been generated. No original-derived candidate has
passed Windows 11 installation, Qt/Swirl or DPI tests. The previous design-space
1088/1088 result remains valid in its original scope and is not a full font.
The 141 HVAR quantization questions remain under explicit investigation.
No Apple font, Apple outline, derived font or credential is included here.

Primary references consulted: Apple CTFontCopyVariation and metric APIs;
OpenType otvaroverview normalization precision, avar, gvar, HVAR/VVAR/VORG;
fontTools VarStoreInstancer/VariationModel; Skia TypefaceMacTest at
709209322f9597b6712079a4386f4d1c7e9b5d44; HarfBuzz and Fontations raw avar
compatibility handling. These sources inform falsifiable hypotheses, not an
assumption that Apple's entire implementation matches one candidate.
# Fourth implementation checkpoint: native counterexamples and batched references

The exact-source user-coordinate run `39359956472` completed at
`ff3b59190ed1a6c6a628aba9e915aaf9eed18247`: 32 faces, 2,328 user positions
and 74,496 glyph checks per model. The raw/final-F2/two-F2 models retained
454/290/290 failures respectively; none passes the entire sample. Some are
strict L/Q correspondence failures rather than a measured large path error.
Requested versus readback-created native paths had zero discrepancy in all
74,496 comparisons. This did not compare every raw metric or prove a universal
coordinate mapping, and is not complete-font acceptance.

At `4461798c9989d7230affc1d46560f6147b859e8c`, run `39361349404`
reproduced the original blocker at face 0, GIDs 0–63, sample 41, location
WDTH=600.5859375, wght=368.22259521484375, HGHT=975.7080078125.
All 32 source faces verified; zero glyphs/faces completed and no output font.
CFNumber direct reads, NSNumber and descriptor metadata agree on the stored
limited readback, so this is not merely a JSON display or NSNumber read issue.

Run `39361349387` actually passed the 174-record analytical native-path and
source-table-metric gate (native control-point error <=0.00660285213 FUnit),
plus two six-record static gates. Its full synthetic reconstruction remains
blocked by the same WDTH assertion; the raw API gate still fails at 849/850.
Python and Windows Server DirectWrite jobs passed, not Windows 11 acceptance.

The original native data also rejects current-width/2 as a universal Apple
vertical-origin-X interpretation (38,775/74,496 outside 1/32; max126.398987).
The standard SourceMetrics X convention is now explicitly labelled; the
HVGL adapter remains refused. A separate native origin probe tests predeclared
current/default/static-width hypotheses. No original metric was overwritten.

The portable reference computation is now batched across a whole face. Private
face-0 equivalence testing checked all 7,200 glyph/model positions: identical
source topology and maximum raw coordinate difference 0.0. Pure rendering CPU
was 96.3299s versus 2.3830s; parsing/native work is excluded from this ratio.
All per-face native observations remain independent. The revised diagnostic
preserves the old models, adds a separately falsifiable signed-zero hypothesis,
adds targeted counterexample coordinates and retains more failure context.

Local checkpoint regression: **202/202 Python tests pass**. Original 141 HVAR
quantization disagreements are retained, not relabelled as fixed.

# Third implementation checkpoint: transparent metric provenance

The xcode-27 run at `0531127a0babcd8242b9d7f81db9f5c9c0202d3c`
(`39359357221`) observed macOS 27.0.1. Increasing measurement size from
0.25 to 64 UPEM and using CTRun did not remove the retained raw CoreText
metric discrepancies. A new adapter uses explicit source-table coordinates
for exact metrics while retaining every raw API field and discrepancy.
Its CLI currently accepts only standard glyf fonts with verified identity
avar; it explicitly rejects an Apple/HVGL mapping guess or a diagnostic
axis-guard bypass. The old strict CoreText API gate remains unchanged.

The independent table-metric gate checks the original analytical fixture,
blank glyphs, fractional and static instances, then actually invokes the
complete reconstruction and independent serialized/native reread. It fails
if the existing production axis guard rejects a request. This is a separate
converter-data gate, not a claim that Apple's API metrics have passed.

The new quantization analysis retains all 141 original F2DOT14 discrepancies.
A normalized-16.16 truncation candidate explains those cases but introduces
36 different mismatches; no globally valid replacement is accepted. Native
construction diagnostics now read the same CFNumber through the C API and
inspect descriptor attributes to distinguish transport from stored values.

Local verification before this checkpoint: **180/180 Python tests and 6/6
audit tests pass**. Original 32-face reconstruction is still blocked before
the first completed face; no final font and no Windows 11/Qt acceptance.

