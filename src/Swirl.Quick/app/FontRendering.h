#pragma once
#include <QByteArray>
#include <QtGlobal>

// Must run before QGuiApplication constructs the Windows platform plugin.
inline void configureSwirlFontRendering()
{
#ifdef Q_OS_WIN
    // NativeRendering's DirectWrite LCD masks showed coloured, uneven stems
    // at fractional DPI. Qt's FreeType engine supplies grayscale glyph masks
    // while retaining native glyph rendering, hinting and per-screen DPI.
    // Explicit diagnostic/CI platform overrides remain available.
    auto platform = qgetenv("QT_QPA_PLATFORM");
    if (platform.isEmpty() || platform == "windows") {
        qputenv("QT_QPA_PLATFORM", "windows:fontengine=freetype");
    } else if (platform.startsWith("windows:") && !platform.contains(';') && !platform.contains("fontengine=")) {
        platform += ",fontengine=freetype";
        qputenv("QT_QPA_PLATFORM", platform);
    }
#endif
}
