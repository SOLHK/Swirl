# Three-axis ramp-basis checkpoint — 2026-11-03

The full design cubes for GIDs 1166 and 19177 still fail acceptance. The
1/32 FUnit limit is unchanged. This checkpoint adds a verified local encoding
primitive, not a completed SwirlVF font. No test/main merge is authorized here.

`hvf_branch_cells` removes only algebraically redundant internal sign branches:
the positive and negative outgoing coefficients must cancel exactly. Active
rotation branches are conservatively retained. `hvf_cubic_batch` preserves every
contour and explicitly closing point while avoiding per-observation pen calls.
The expanded Apple libhvf probe covers 179 observations across GIDs 0, 2, 12,
1166 and 19177: zero failures, maximum portable/native error 5.085e-13 FUnit.

`local_cff2_geometry` changes a rectangular nodal interpolant into either tent
or truncated-power ramp regions. Tensor second divided differences eliminate
affine-span redundancy without changing the pre-quantization interpolant.
Signed 16.16 rounding occurs once; only exactly encoded zero rows are removed.
All blends remain ordinary. An authored 729-node multilinear example needs
only five nonconstant ramp regions. Arbitrary dense source geometry does not
inherit that compression ratio.

The native probe saves real CFF2 TTCs, reopens them, then compares CoreText
outlines against independently executed Apple libhvf observations. Each case
has 256 independent mathematical/serialized samples and 72 native positions.
CoreText exact-axis replay is required. Results on macOS 26.5.1 ARM64:

| Source GID | Tested domain | Regions | Serialized maximum | CoreText/libhvf maximum |
| --- | --- | ---: | ---: | ---: |
| 0 | Full cube, sampled | 70 | 0.000220967 | 0.009804686 |
| 12 | Full cube, sampled | 38 | 0.004513523 | 0.007795613 |
| 1166 | One small box near a retained failure | 35 | 0.000478336 | 0.008403318 |
| 19177 | One small box near a retained failure | 22 | 0.001188489 | 0.010325509 |

All 1,024 serialized and 288 native observations pass, with unchanged topology.
These research fonts have an authored three-glyph template, not source cmap or
metrics. Local-domain models cannot enter normal installation: the explicit
diagnostic switch does not certify domain selection or complete glyphs.

Failures remain recorded. One thousand fixed local tensor patches per target
still give independent maxima 0.1127361 / 0.1318838 (129 / 151 failures out of
2,048 each). Minimax plane insertion for GID 1166 gives 0.6492496 with 128 boxes.
At the fixed-patch worst points, source traces identify an internal-axis hinge
in part 47120 for GID 1166 and an inherited upstream branch for GID 19177.
Quadratic-curvature ablation does not remove these errors. Finer ramp models
of those larger boxes reach 0.0177801 / 0.0250405, but need 2,665 / 1,178 regions
and exceed the ordinary-blend operand stack. They are rejected, not installed.

The exact code checkpoint passes 984 Python tests (977 passed, seven platform
skips) and six parser audits. New-basis Windows/DirectWrite, HarfBuzz and Qt
checks have not run. Old native results do not certify this new basis.
See the [aggregate receipt](evidence/SWIRL_VF_RAMP_20261103.json) for hashes,
retained failures, platform receipts and precise scope.

Reproduction uses private manifests containing the declared boxes and seeds:

```sh
python -m unittest discover -s tools/swirl_vf/tests -v
python -m unittest discover -s tools/swirl_vf/audit -p 'test_*.py' -v
python tools/swirl_vf/platform/probe_hvf_branch_cells.py \
  --source "$PRIVATE_SOURCE" --manifest "$BRANCH_MANIFEST" \
  --binary "$HVF_ORACLE" --private-output "$FRESH_BRANCH_OUTPUT"
python tools/swirl_vf/platform/probe_local_cff2_basis.py \
  --source "$PRIVATE_SOURCE" --manifest "$BASIS_MANIFEST" \
  --private-output "$FRESH_BASIS_OUTPUT" \
  --coretext-binary "$CORETEXT_ORACLE" --hvf-binary "$HVF_ORACLE"
```

Full-cube target models, source metrics/layout, a viable complete-font region
budget and Windows acceptance remain necessary. There is no final SwirlVF.ttc
or delivery checksum at this checkpoint. Private fonts, coefficients, failure
coordinates and source transcripts remain outside Git.

## Native-matrix follow-up

The authored fixture now has a `--ramp` mode for the existing nonlinear
three-axis source (`.11 * WDTH^2 * wght^2 * HGHT`), with independent fit
holdouts. The DirectWrite matrix and CoreText gate include it and compare
against that source, not against the target model. HarfBuzz 14.6.0 passes 546
outline observations over two faces, all three GIDs and 91 positions. The
reference explicitly emits the implicit straight closure; no native segment
is removed. Focused CFF2/adaptive/local/HarfBuzz tests: 40 passed, zero failed.
The DirectWrite run is pending until the newly pushed CI completes.

PR #51's `39d1186a` nested-blend admission guard is selectively ported, with
regression coverage. Normal construction rejects the known incompatible
encoding; authored diagnostics still retain and test its native failures.
