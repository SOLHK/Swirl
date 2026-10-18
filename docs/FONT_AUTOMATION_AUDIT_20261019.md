# Intelligent font system: starting audit, 2026-10-19

## Verified starting point

The remote development branch `work/core-completion-20261017` was read again at
the start of this task. Its HEAD was
`fcc5937e9121031ac387f120f8c9dc6f242f71b1`, not an assumed historical revision.
The existing core workflows were green for that SHA. The existing Qt application
workflow did not automatically cover this development branch, and those core
checks were not Windows font validation.

The task uses an isolated cloud checkout. GitHub commits do not write to the
user's Windows `D:\Codex` directory. No private TTC or subscription is needed
for the public font CI.

## Font data flow and defects

`FontManager::importFont` validates and hashes a local SFNT, preserves the bytes,
registers a saved copy through QFontDatabase and stages a preview family.
`axesFor` reads `QFontInfo::variableAxes`; preview coordinates are separately
persisted from the applied selection. `applyPreview` sets the application font
and increments `configurationRevision`. `Theme` and `SwirlText` bind QML font
properties. `VariableFontPreview` uses a bounded, live native raster texture.

The following issues were identified in the actual starting code:

- `variableAxesFor(family, weight)` ignores `weight`. All selected-family text
  receives `m_values`, so an explicit `wght` coordinate masks the existing
  400/500/600/700 component hierarchy. It also places those axes on the inherited
  application font. The old exact-coordinate behavior belongs in manual mode.
- There is no automatic/manual mode or persistent per-family profile. Changing
  the selected family replaces the one global coordinate map.
- Several TextArea/input controls repeat a delayed variable-axis binding;
  shared attached ToolTips have no corresponding per-item policy.
- Metadata invalidation handles an explicit import but does not observe every
  font-database change. The new design must invalidate cached metadata without
  rescanning font files during animation.
- QML's font `pixelSize` and `pointSize` getters synthesize the other unit. Two
  positive numbers do not identify the original unit. The QML adapter must pass
  the original QFont value to C++, which retains the native pixel/point flags.

`VariableFontPreview` already handles `ItemDevicePixelRatioHasChanged` and
`ItemSceneChange` and preserves transformed animation geometry. That native
raster behavior and its pixel-tolerance-2 quality checks remain separate from
the automatic-axis policy.

## Implemented safe policy contract

The independent `FontAxisPolicy` has no filesystem, display or settings access.
It validates supported axis metadata, rejects ambiguous tags and nonfinite
values, clamps to actual ranges, maps Qt 6 design weights directly to `wght`,
and maps explicit point sizes or logical pixels divided by logical DPI to
`opsz`. DPR is not multiplied again. With no usable size, opsz retains its
designer default. `wdth`, `HGHT` and other custom axes retain their defaults;
`ital` and `slnt` remain under the existing QFont style selection in automatic
mode. Manual coordinates are scoped by the caller and normalized independently.

There are currently **no experimentally validated font-specific optimization
profiles**. A mutable HGHT axis does not establish its semantic meaning or prove
better clarity. No empirical size-to-HGHT or universal boldness formula is added.

Roles convey the existing design intention; they do not replace a component's
weight or size. Transform-only animation never drives optical-size changes.

## Primary references inspected

- [Qt 6.10.3 QFont](https://doc.qt.io/qt-6.10/qfont.html) and
  [QFontInfo](https://doc.qt.io/qt-6.10/qfontinfo.html).
- [Qt 6.10.3 QFont implementation](https://github.com/qt/qtbase/blob/v6.10.3/src/gui/text/qfont.cpp)
  and [FreeType engine](https://github.com/qt/qtbase/blob/v6.10.3/src/gui/text/freetype/qfontengine_ft.cpp).
- [Qt 6.10.3 QML font value type](https://github.com/qt/qtdeclarative/blob/v6.10.3/src/quick/util/qquickvaluetypes.cpp),
  including the two size getters' default-DPI conversions.
- [Qt High DPI](https://doc.qt.io/qt-6.10/highdpi.html) and
  [QScreen logical DPI](https://doc.qt.io/qt-6.10/qscreen.html).
- [OpenType optical-size axis](https://learn.microsoft.com/en-us/typography/opentype/spec/dvaraxistag_opsz).
- [Krita font registry](https://github.com/KDE/krita/blob/master/libs/flake/text/KoFontRegistry.cpp),
  inspected for the mature pattern of defaults, explicit coordinates and range
  constraints. No GPL source was copied into Swirl.

## Retained verification boundaries

The historical physical DPI failures and unpassed stable 240 fps target remain
recorded in `FONT_ACTUAL_DPI_20261018.md`. This new policy cannot clear them by
itself. Synthetic font tests establish real axis application, state handling
and fallback; they do not establish physical-panel clarity. The Windows workflow
and its exact pass/skip contract are described in `FONT_SYSTEM_CI.md`.

Qt resolves fonts by family/style. Multiple unrelated font files with the same
family/style can be ambiguous; the UI does not provide a physical-face selector.
The existing metadata-replacement test explicitly removes the previous test
registration before adding the same-name replacement. It must not be used to
claim arbitrary simultaneous same-name imports always select the newest file.
