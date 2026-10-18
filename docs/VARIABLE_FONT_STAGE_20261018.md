# Variable font stage (2026-10-18)

Swirl's existing font settings now enumerate OpenType axes through Qt 6.9+ QFontInfo, including custom/hidden axes such as HGHT. Import stages a preview, sliders and numeric values update QML font.variableAxes, and Apply saves the confirmed profile and updates all Theme text bindings. A separate automatically saved draft survives restart. Static TTF/OTF and TTC families continue to work. No font transformation, static instancing, metric rewriting, or change to the default rendering engine is involved.

Metadata is cached by family (bounded to 64); slider positions do not allocate an application-owned font cache or re-register font files. Duplicate imports reuse the existing registration. Window/page structure and animation code remain unchanged. Configured axis coordinates apply exactly to the selected family throughout the UI; existing pixel-size hierarchy remains intact.

Local validation on Windows 11 / Qt 6.10.3: five regional TTC families, three axes, direct glyph raster differences, QML live HGHT, fractional numeric input, explicit Apply, independent-process restoration of confirmed and draft values, repeated-import preservation, and selected-font text bindings on overview/proxies/capture. Local-only tests require SWIRL_TEST_TTC and do not upload or redistribute fonts. The opt-in --font-ui-test runs within the existing isolated preview mode.

The active display mode reports 2560x1600 at 150% and 120 Hz. Read-only EnumDisplaySettingsW also lists 2560x1600 at 240 Hz; 120 Hz is the active value, not the panel maximum. The reason for the current mode is not established. No refresh-rate setting was changed. The implementation has no fixed 120 Hz frame cap, but measured frame intervals exceed the 4.17 ms budget in some updates; physical 240 Hz acceptance is pending. Native Qt window captures cover 9/10/11/12/13/14/16 pt and 15 default/boundary/corner configurations. Each separate FreeType/native DirectWrite comparison also covers 945 QImage simulated-DPI cases (five DPRs x seven sizes x 27 axis combinations); these are not system-scale changes. All tested axis-boundary line heights were stable. The 1,440-update same-coordinate stress test retained its page and reached a memory plateau around 500 MiB, after substantial initial cache growth; this is not a bound for every possible coordinate or a claim of constant 120 fps.

Font outlines, metrics, glyph coverage and interpolation tables were not edited. There is no modified font offered as an improvement without visual evidence. Physical-screen clarity, actual Windows scale switching and cross-monitor migration remain untested. The current session lacks a callable native computer-use API; raw Qt test output is not a physical-screen or ToDesk quality proof. No system font installation, registry/display changes, installed Swirl replacement, or proxy changes were made.

Primary references reviewed before independent implementation:
- https://doc.qt.io/qt-6.10/qfont.html#setVariableAxis
- https://doc.qt.io/qt-6/qml-font.html#variableAxes-prop
- https://github.com/qt/qtbase/blob/6.10/src/plugins/platforms/windows/qwindowsintegration.cpp (native, freetype and GDI backend selection; separate engines)
- https://github.com/fonttools/fonttools/blob/main/Lib/fontTools/varLib/interpolatable.py (OpenType variation structure; no code copied)

This font work has its own acceptance list and does not change the proxy-core 10.83% acceptance figure. The predecessor 2228ec2 Windows CI failure in DNS peer TCP bind (WinError 10013) is outside this change; do not interpret an unrelated network-fixture failure as a font pass or silently remove its test.

Focused existing CTest gate: swirl-font-selection and swirl-all-pages passed (2/2). Local final FreeType font suite passed 8/8; native DirectWrite live-axis/restoration/point-size check passed 4/4. The isolated font UI harness passed all checks, including exact current-family axis propagation on three pages.
