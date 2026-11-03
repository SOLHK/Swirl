# Mac reference handoff, 2026-11-03

This branch continues Windows Beta commit `b7a455cf2cbad547e262b6984b2a87280dcbabf5`.
It does not modify PR #53, PR #54, main, test, or the existing Windows candidate.
The private export is a research reference, not another font release. Native
Windows acceptance and the Beta's outstanding geometry/size issues remain open.

## Implementation and research

The existing HVGL parser, batched evaluator, metric evaluator, raw ordered avar
mapper and symbolic branch locator are reused. Research branch changes since
the Windows baseline were inspected; unrelated CFF2 encoding and optimization
work remains on its research branch. No restricted reference-font outline is
used by the exporter or evaluator.

Before implementation, the following actual upstream source and tests were
reviewed, in addition to the earlier Windows research recorded in
`SWIRL_VF_WINDOWS_NATIVE_20261103.md`:

* [fontTools 4.61.1 SFNT reader](https://github.com/fonttools/fonttools/blob/4.61.1/Lib/fontTools/ttLib/sfnt.py),
  [tests](https://github.com/fonttools/fonttools/blob/4.61.1/Tests/ttLib/sfnt_test.py),
  [MIT license](https://github.com/fonttools/fonttools/blob/4.61.1/LICENSE).
  Reuse its table parser and checksum primitive; independently check raw TTC
  directories, lengths, aliases and overlapping ranges. Record both literal
  and zero-adjustment head sums. This source TTC uses literal sums including
  head.checkSumAdjustment; the original bytes must not be rewritten to suppress
  a tool warning. See the [OpenType collection/checksum rules](https://learn.microsoft.com/en-us/typography/opentype/spec/otff)
  and [specification discussion](https://github.com/MicrosoftDocs/typography-issues/issues/417).
* [CPython 3.12 gzip implementation](https://github.com/python/cpython/blob/v3.12.0/Lib/gzip.py),
  [tests](https://github.com/python/cpython/blob/v3.12.0/Lib/test/test_gzip.py),
  [PSF license](https://github.com/python/cpython/blob/v3.12.0/LICENSE).
  Use streaming gzip JSONL with fixed mtime, CRC/trailer verification and a
  separate SHA256 manifest. Records retain binary64 numbers. No pickle or
  executable serialized objects; no archive extraction or embedded dependency
  binaries. Path validation is identical on Windows and POSIX.
* Existing native oracle source and Apple's SDK `hvf/Scaler.h` were reviewed.
  The added request stream reuses one Apple renderer per face, validates every
  GID/coordinate, and emits ordered request IDs and exact requested coordinates.
  Authored integration tests compare it to independent legacy one-request calls
  and reject malformed requests. No Apple implementation code is copied.

The repository's own license remains PolyForm Noncommercial. The dependency
licenses do not grant redistribution rights to Apple fonts or private geometry.

## Tools and execution boundary

| Tool | Environment | Input and purpose |
|---|---|---|
| `platform/hvf_oracle.c`, `hvf_coverage.py` | macOS, Apple HVF SDK/runtime | Native normalized-design outline extraction |
| `platform/macos_source_baseline.py`, `diagnose_coretext_formats.py` | macOS, CoreText | Exact-source identity and authored format controls |
| `platform/export_mac_handoff.py` | macOS for native extraction | Four-face catalog, complete default baseline, separate training/validation samples |
| `platform/export_handoff_boundaries.py` | macOS for native extraction | Independent nested axis/clamp/projection contact samples |
| `tools/handoff_bundle.py` | Python 3.12, Windows/macOS/Linux | Manifest/CRC verification, on-demand baseline and arbitrary design-coordinate reference evaluation |
| `tools/hvf.py`, `batch_geometry.py`, `source_metrics.py` | Python, portable | Source parsing, geometry, unhinted table metrics |
| `tools/target_axis_mapping.py` | Python, portable | Raw ordered avar and explicitly unaccepted user-map candidate |
| Existing `windows_font_builder.py`, `windows_full_audit.py`, `windows_explicit_deltas.py`, `ttc_staging_pack.py` | Python, portable | Windows compilation, geometry/metrics auditing and size work |
| Existing DirectWrite C++/PowerShell probes | Windows | Actual native Windows acceptance, still required |

Dependencies are `fonttools==4.61.1`, `numpy==2.2.6`, and `uharfbuzz==0.56.3`.
The portable reader does not import CoreText, load Apple libraries, access a
system font directory, or assume a Mac source path. A source copy inside the
private bundle is addressed by a relative path and pinned SHA256.

## Evidence status

The full export and independent reload are in progress. Final measured counts,
package identity, CI results and Mac retirement conditions will replace this
paragraph before the handoff is declared ready. Successful authored Windows CI
tests alone never certify the real private font or the entire HVF design cube.
