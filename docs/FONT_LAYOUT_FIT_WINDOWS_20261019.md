# Constrained variable-width labels and Windows font-source acceptance

This work starts from the freshly fetched development branch at `daad7a0`.
Only font code, shared font controls, and their tests are changed. Private font
files, fingerprints, user state, screenshots and local machine evidence remain
outside the public repository in the user's requested evidence directory.

## Layout fitting

`FontAxisPolicy` retains its natural-width contract for general text. The opt-in
`FontManager::fittedText` bridge measures actual advances at real `wdth`
coordinates for single-line button, navigation and page-title labels. It retains
the existing design weight, font size, hinting and every unrelated axis.

`SwirlText` enables fitting only for eliding, unwrapped labels directly inside
Qt Quick Layouts. Layout.preferredWidth publishes the natural advance, so the
compressed font cannot reduce its parent's preferred size and feed back into
its own available width. Explicit caller layout constraints still take priority.
Body text, editors, rich text, numbers, non-layout text, and the shared animated
hero title keep natural width. Unvisited controls are not claimed as inspected.

There are five 2% coordinate steps, bounded by the real axis minimum and 90% of
the design default. The actual advance must decrease before a step is used;
outline-only width axes remain at their default. The entry/release margin is
four logical pixels, with a two-pixel hold band between steps. Text still uses
its original ellipsis, wrapping and clipping rules; a label that cannot fit
within the bounded compression still elides. There is no scale transform or
font-size reduction. Measurement caching is limited to 256 entries and is
invalidated on font database changes. No file is read during layout fitting.

Advanced manual mode remains exact and bypasses fitting. The existing per-family
automatic/manual persistence and optical-size policy are unchanged. HGHT remains
the font's actual default in automatic mode. A missing opsz axis is not invented.
OTC is accepted by the existing validated application-font import and reload
path, alongside TTF/OTF/TTC; public tests use an original generated OTC.

## Resource invalidation and test isolation

Windows/FreeType reproduced a retained preview QFont still using a removed
application-font engine even after the font database no longer listed the
family. The preview now detaches its engine through public QFont family setters
only when fontDatabaseChanged fires. It restores the exact font values and
resolve mask without emitting a fake fontChanged. The regression requires the
new physical raw-font family and an actually changed rendered image, retaining
the existing timeout, idle/coalescing checks and pixel standards.

The standalone source-QML fixture also excludes the application build directory
from its import paths. Otherwise a combined application/test build finds the
application-generated qmldir, which prefers resources linked only into
Swirl.exe. This was reproduced as a missing SwirlFontBinding resource.

## Evidence entry points

`automaticWidthUsesRealAdvances` tests original generated fonts with real advance
variation, invariant advances, bounded compression, hysteresis, weight/size
preservation, body/data exclusions, manual mode, static fonts and OTC import.
`qmlLiveAutomaticFonts` additionally exercises the actual shared Text in a real
RowLayout, natural preferred width, subpixel layout jitter and restoration.
The CI XML gate requires the new width test rather than accepting a skip.

Local-only `optionalPhysicalFontIdentity` compares actual shaped QTextLayout
glyph runs with the original SFNT/TTC name, cmap, fvar and gvar table hashes for
each imported family, four design weights and two widths, then checks manager
restoration in an independent process with strict child XML validation. It
reports a skip without a local authorized font.

An application built with SWIRL_BUILD_UI_TESTS supports
`--font-acceptance-test --font-source-file=<local-font>
--font-acceptance-output=<local-folder>`, together with the existing isolated
font-review import/family arguments. It visits AppState.allPageIds in two themes
and two window sizes, waits for real route transitions, records live design
weights and shaped-run source tables, and saves unmodified Qt renders. Foreign
fallback runs and missing glyphs are separate observations, not hidden passes.
This test does not claim human clarity, all dialog states or physical scanout.

The local Windows report is the authority for run exit codes, original XML,
private matrices, actual system DPI changes and frame traces. A queued-present
event is not GPU completion or panel FPS. Existing pixel tolerance remains 2;
neither animations nor updates are removed to improve measurements.

The existing frame entry also retains all nine original static/slider/three-axis
phases and adds three continuous 9–16 pt phases. Each size input and each raster
records its actual point size; submission coverage requires both the expected
axis coordinates and expected size. Original preview fonts are restored outside
the measured interval. The existing warmup, sample counts and deadlines remain.
Each phase also records native foreground activation. A timed-out phase retains
its failure and the remaining independent modes still run; overall exit remains
nonzero. The six-second phase deadline is not increased to obtain a pass.
`--font-acceptance-current-page` is a shorter restart/DPI probe of the current
page in the same two themes and sizes; it does not substitute for the full walk.

## Primary implementation references

- [Qt 6.10.3 QFont implementation](https://github.com/qt/qtbase/blob/v6.10.3/src/gui/text/qfont.cpp): copied font private data does not retain engineData; public value changes detach it.
- [Qt 6.10.3 font database](https://github.com/qt/qtbase/blob/v6.10.3/src/gui/text/qfontdatabase.cpp): registration invalidates the database and emits fontDatabaseChanged.
- [Qt Windows FreeType database](https://github.com/qt/qtbase/blob/v6.10.3/src/gui/text/windows/qwindowsfontdatabase_ft.cpp): application font handling and physical face matching.
- [Krita font registry](https://github.com/KDE/krita/blob/master/libs/flake/text/KoFontRegistry.cpp): mature separation of requested variation coordinates and font metadata. No code copied.
- [Qt QRawFont](https://doc.qt.io/qt-6.10/qrawfont.html): actual shaped raw-font tables and glyph outlines, rather than family-name-only proof.
