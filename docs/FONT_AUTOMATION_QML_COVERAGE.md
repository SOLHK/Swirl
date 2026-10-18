# Intelligent variable fonts: QML integration and coverage

This document covers the application integration, not a physical-screen clarity or
240 Hz acceptance report. The policy itself is implemented in `FontAxisPolicy`;
there are no width, height, weight or optical-size formulas in page QML.

## One application binding path

`SwirlFontBinding.qml` is the only production QML writer of `font.variableAxes`.
It passes the actual `QFont`, the text role and the owning window's display
context through `Theme` to `FontManager.resolvedAxesForFont`. Its preview path
uses `previewResolvedAxesForFont` and the separately saved preview mode/values.

Passing the complete `QFont` is necessary. Qt 6.10.3's QML font value getters
synthesize both a positive pixel size and a positive point size, even when the
original `QFont` specified only one unit. Reading both QML getters and preferring
one would lose the original unit and could use the default screen's DPI. The
C++ bridge reads `QFont::pixelSize()` and `pointSizeF()` instead, preserving the
original `-1` sentinel and converting pixel sizes using the owning window's
vertical logical DPI. DPR is not multiplied into the requested optical size.

`FontDisplayContext` attaches one observer to each `QWindow`. All text items in
that window share its `logicalDpi` and actual `QWindow::devicePixelRatio()`.
Screen replacement reconnects the DPI signals; a window DPR event updates the
context only when the values changed. Destruction follows the owning window.
Text movement, opacity changes and the animation clock are not font inputs.

Font subproperties share one `fontChanged` signal. The helper therefore listens
for font/configuration/display changes, queues one `Qt.callLater` refresh for
that event turn, and sends the complete font to C++. Its delayed `Binding.value`
reads only its cached result, so writing `font.variableAxes` cannot recursively
reevaluate a binding that reads `target.font`. Equal maps do not change the
cache or rewrite the font. The policy reads the requested design font without
using its old axis map. There is no frame timer or font-file read in QML.

`SwirlText` and the single-line fields retain their existing pixel-size defaults
and design weights. A caller must not also set `font.pointSize` on those
pixel-based components: Qt rejects simultaneous explicit pixel and point sizes.
The point-size integration probe uses the actual `SwirlTextArea` / TextEdit path,
which does not impose a pixel-size default, and verifies the native point unit.

## Coverage map

| Surface | Actual rendering path | Integration |
| --- | --- | --- |
| Body copy, status and helper text | `SwirlText` / native Qt Quick Text | Shared binding follows live family, design weight, original size and display context. |
| Page titles and large titles | Existing `SwirlText`, including the shared animated hero title | Existing point/pixel sizes and weights stay in their components. Role annotations identify titles without new size tiers. |
| Navigation and sidebar | `SwirlNavigationItem` and `SwirlText` | Selected and unselected weights remain distinct; navigation role carries their existing semantics. |
| Buttons and segments | `SwirlButton`, `SwirlSegmentedControl`, `SwirlText` | Buttons retain Medium by default. An explicit button weight now reaches the actual label instead of being overridden by an unconditional Medium. |
| Table headers, cells and list rows | `SwirlDataTable`, `SwirlListRow`, `SwirlText` | Existing header/cell sizes, clipping, elision and number animations remain unchanged. |
| Card data and counters | `SwirlMetricCard`, Activity values and existing counter text | Data role preserves the existing larger size/weight choices; no width-axis compression is introduced. |
| Search and single-line input | `SwirlSearchField`, `SwirlTextField` / native TextInput | Shared binding on the control font; Qt's placeholder/selection machinery remains intact. |
| Multi-line input and selectable text | 18 application `SwirlTextArea` instances / native TextEdit | Replaces 18 repeated inline bindings with one base component, including diagnostics, licence, rule editor, process list and import text. |
| Code/configuration viewers | `SwirlTextArea` or `SwirlText` with explicit `Cascadia Code` | The explicit monospace family is retained and resolved against its own metadata; private CJK axes are not copied to it. |
| ComboBox selected value and options | `SwirlComboBox` and native `SwirlText` content | Control and text content both resolve their actual font; popup options keep their existing own weight and size. |
| Context and gateway menus | Existing custom `MenuItem` content using `SwirlText` | Menu text uses the same policy in its own popup window. |
| Dialogs | `SwirlDialog`, native `SwirlText` headers/content | The existing default Basic header of the discard confirmation also gets its own binding, respecting its explicit bold weight. |
| Tooltips | 12 local `SwirlToolTip` instances using the Basic style | Each tooltip resolves its own font and window context. The Basic popup, padding, placement rules and transitions remain inherited; existing trigger text, delay and visibility conditions are retained. |
| Checkboxes and radio buttons | Existing custom `SwirlText` content | Check state animations and existing label metrics are unchanged. |
| Font family list | Existing `SwirlText` family samples | Each sample retains its explicitly selected family and resolves that family's metadata. |
| Font settings preview | `VariableFontPreview` | Shared preview binding selects automatic per-size/per-weight axes or the separately retained manual overrides. The native raster preview implementation remains separate from normal text. |

The source audit contains 92 production QML files, 384 `SwirlText` definitions or
instantiations, 18 multi-line base-component usages and 12 local tooltip usages.
The only raw `Text` definition is `SwirlText`; the only raw `TextArea` definition
is `SwirlTextArea`. The two raw `TextField` definitions are the shared field and
search controls. Inline `Label` types in DNS and Activity inherit `SwirlText`.
These are source counts, not claims about how many runtime instances were
visually checked. There are no production `ToolTip.*` attached-property usages.

## Automatic and advanced manual controls

The settings page adds one existing-style toggle labelled “手动调整”. Automatic
mode hides the advanced slider/numeric rows and their reset-all button; the rows
and saved values still exist. Manual mode exposes the same discovered axes,
sliders, numeric input/validation and individual default buttons. Toggling
changes the preview mode first. “应用到整个界面” confirms the current preview,
and “恢复已应用配置” retains its existing discard-preview function. Turning manual
mode off restores the automatic strategy without erasing saved manual values.
Manual axis coordinates, including `wght`, are exact user overrides; automatic
mode restores each component's requested design weight. Finishing an axis input
after hiding manual controls cannot re-enable manual mode, and an input begun
for another family is not submitted to the newly selected font.
Only `textEdited` marks a numeric input for submission. Merely focusing and
leaving the four-decimal display preserves a saved coordinate's full precision.

The family list, import flow, existing font sizes, margins, controls, page caches,
window shapes and application animations are preserved. The first preview line
now represents a title's design weight in automatic mode; the remaining sample
lines represent body weight. The existing sample text is unchanged.

## Verification boundaries

- All 92 production QML files parsed successfully using the Qt 6.10.3
  `qmlformat` parser. Formatting was not written back to the files.
- `FontQmlChecks.h` loads the real Theme and actual font controls. Only unrelated
  application services and decorative icons are replaced by test doubles.
  It checks live automatic/manual switching, draft-versus-applied isolation,
  family replacement, preserved title/button/style weights, point versus pixel
  font units, a 144 logical-DPI probe, native rendering and full hinting, cached
  object identity and the absence of font changes from movement/opacity.
- The display-context test checks one observer per window, no notification for
  an unchanged DPR event and destruction with each of 12 temporary windows.
- Test execution status belongs to the associated CI/test report. The existence
  of these tests is not a claim that an unexecuted Windows test passed.

Windows-owned file dialogs, system menus, IME candidate windows and any native
platform UI retain the OS's typography. Swirl does not replace Windows UI fonts.
Rich text can explicitly choose its own face/style, and fallback glyphs are
shaped by Qt's fallback engine using the appropriate fallback font. This system
does not invent verified per-glyph optical corrections for missing glyphs.

Public automation fonts test axis/control mechanics, not the visual quality of
the user's private PingFang collection. Physical-screen screenshots, fractional
Windows scaling, mixed-DPI monitor moves, private-font raster tolerance 2 and
240 Hz frame delivery still require the existing Windows acceptance workflow.
The threshold, raster tests and animations are not reduced by this integration.

## Primary references inspected

- [Qt 6.10.3 font value implementation](https://github.com/qt/qtdeclarative/blob/v6.10.3/src/quick/util/qquickvaluetypes.cpp): original font units versus QML computed getters.
- [Qt 6.10.3 QWindow API](https://github.com/qt/qtbase/blob/v6.10.3/src/gui/kernel/qwindow.h): `devicePixelRatio()` is a C++ method, not a QML property.
- [Qt 6.10 QScreen](https://doc.qt.io/qt-6.10/qscreen.html): logical DPI for font unit conversion and preference for the actual window DPR.
- [Qt Binding](https://doc.qt.io/qt-6/qml-qtqml-binding.html): value-type subproperty binding and the existing delayed binding semantics.
- [Qt 6.10.3 Basic ToolTip](https://github.com/qt/qtdeclarative/blob/v6.10.3/src/quickcontrols/basic/ToolTip.qml) and [Basic Dialog](https://github.com/qt/qtdeclarative/blob/v6.10.3/src/quickcontrols/basic/Dialog.qml): style-owned text font inheritance and bold dialog headers.
- [KDE Kirigami Heading](https://github.com/KDE/kirigami/blob/master/src/controls/Heading.qml): mature separation of semantic roles and explicit design weights from general font selection. No source was copied; Swirl's existing metrics and controls remain its own.
