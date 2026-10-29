# Swirl 3.0 brand and Qt foundation candidate

Candidate product version: **0.2.14**. This increment identifies the research,
brand and toolchain stage; the complete Swirl 3.0 page/glass/motion redesign is
still pending the user-directed model checkpoints.

## Implemented

- A single editable cubic-curve knot master and six deterministic SVG exports.
- Local colour progressions, light/dark surfaces, monochrome increased-contrast
  variants, and QML selection of the appropriate mark.
- Existing application/Windows/installer icon resource chain retained; tracked
  legacy ICO refreshed from the same Qt-built canonical mark.
- Project Qt minimum raised to 6.12 and Windows UI CI pinned to verified 6.12.0.
  New SDK repository layout is handled by a checked installer with official
  metadata/archive hashes and path-boundary checks.
- Earlier incomplete page changes preserved locally for deliberate later
  integration. This stage does not claim those pages were migrated.

## Verification performed before candidate submission

| Check | Result | Scope |
| --- | --- | --- |
| Canonical SVG export `--check` | Passed | Six exports match the editable master |
| Portable core boundary | 7 passed | No Qt/platform dependency moved into Rust |
| Qt/GNU versions | 6.12.0 / 15.1.0 | Actual qmake and compiler execution |
| New CMake configure | Passed | Independent source/build/SDK; GuiPrivate warning retained |
| Native `swirl-generate-icon` | Passed | Built with Qt 6.12.0 and GCC 15.1.0 |
| Native brand variants | 4 × 9 frames passed | Light/dark/mono, 16/20/24/32/40/48/64/128/256px |
| ICO dimensions/alpha | Passed | All frames nonempty, transparent background and opaque interior |
| Native raster visual review | Completed | Light/dark/mono proof; tiny curl details remain limited at 16–20px |

The native icon proof uses decoded ICO pixels at their original dimensions.
It is not an application screenshot. The larger design preview uses resvg;
resvg is a local design utility and is not a product dependency.

Full application build, native page interaction checks and CI installer
results are recorded in a subsequent delivery record when actually available.
No private-node/Codex networking, actual 60/120Hz frame timing, Windows DPI
visual acceptance, new glass shader or new global motion acceptance is implied.

## Next model checkpoint

Notify the user to select **GPT-6 Astra Ultra** for the floating glass sidebar
and global Design System. Read the research/design documents and retain the
actual source contracts. After that foundation, notify before switching to
**GPT-6.1 Sol Ultra** for the complete QML page migration.
