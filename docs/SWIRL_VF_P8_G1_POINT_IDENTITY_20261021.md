# Swirl-VF P8-G1 checkpoint: conservative point identity

Date: 2026-10-21  
Branch: `work/vf-p8-gvar-pro`

## Scope and parent

This branch was created from the live `work/vf-takeover-abc-20261021` ref,
not from the historical P7 handoff SHA. The P7 handoff states that the tested
source checkpoint is `67a6196d3075821ffe5a3235bf1d1a393c41fe8b`, and that the
later evidence successor does not change tested source. P7 also explicitly
reports that only five GIDs have sampled variable models and that precision,
metrics, mapping and full-face variable equivalence remain unaccepted.

The branch adds an isolated utility; it does not alter the P7 conversion entry
point, the closure compactor, the TTC builder, production admission, or any
other development branch.

## Implemented

`tools/swirl_vf_point_identity.py` provides a conservative mapping between
two already encoded TrueType outlines. It permits contour permutation, cyclic
start-point changes and reversed winding only where point coordinates and
on-curve flags match exactly. The result maps each target outline point index
to its source index.

It rejects malformed contour endpoints, empty contours, point-count changes,
unmatched rings, duplicate/symmetric point mappings and non-unique contour
assignments. This deliberately does not guess correspondences for genuinely
different shapes. Four phantom points are outside this module's outline-point
domain and must be handled by the caller as a separate four-point suffix.

## Tests

`tests/test_swirl_vf_point_identity.py` adds ten authored unit tests for empty
outlines, cyclic rotation, reversed winding, contour permutation, on/off-curve
identity, changed point count, duplicate contours, symmetric point ambiguity,
malformed endpoints and empty-contour rejection.

**Execution status: NOT_RUN in this environment.** The GitHub connector can
read/write repository content but does not provide a local checkout or Python
test runner. The commit status endpoint returned no status records and the
commit workflow-run lookup returned no runs. Therefore no claim is made that
these tests passed or that CI ran. Before integration, run:

```sh
python -m unittest tests.test_swirl_vf_point_identity
```

## Algorithm limits / next steps

This is an exact-identity gate, not a shape-fitting algorithm. It cannot map
different point counts, infer newly introduced extrema, align points across
interpolated shapes, generate TupleVariation deltas, or implement IUP. It must
be integrated only as a fail-closed precondition for any later gvar builder.
The next checkpoint should add tests against fontTools-serialized authored
glyf/gvar data, preserving point indices and phantom deltas after save/reopen,
before implementing sparse-delta optimization.

## Open-source references and licensing

The existing P7 handoff identifies the mature fontTools `TTGlyphPen`,
`pointPen`, and `VariationModel` APIs and the OpenType `glyf` and
`otvarcommonformats` specifications. The new matcher is an independent
implementation of conservative identity checks; no third-party source code
was copied. This connector-only pass did not independently re-audit the full
licenses or execute HarfBuzz/FreeType interoperability tests.
