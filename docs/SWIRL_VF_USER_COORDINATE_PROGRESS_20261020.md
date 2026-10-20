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
