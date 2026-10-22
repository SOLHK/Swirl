#pragma once

#include "app/FontAxisPolicy.h"
#include <QFont>
#include <QFontDatabase>
#include <QGlyphRun>
#include <QImage>
#include <QJsonArray>
#include <QJsonObject>
#include <QPainter>
#include <QRawFont>
#include <QTextLayout>
#include <cmath>

// Smoke checks for the generated, original fonts. These establish that Qt
// consumes real gvar coordinates and uses a fallback face; they are not a
// substitute for native Windows quality or frame-pacing acceptance tests.
namespace SwirlFontAutomationRaster {

inline QFont fontFor(const QString &family, const QVariantMap &values, int pixelSize)
{
    QFont font;
    font.setFamilies({family, QFontDatabase::systemFont(QFontDatabase::GeneralFont).family()});
    font.setStyleName(QString());
    font.clearVariableAxes();
    font.setPixelSize(pixelSize);
    font.setWeight(QFont::Normal);
    font.setHintingPreference(QFont::PreferFullHinting);
    font.setStyleStrategy(QFont::PreferAntialias);
    for (auto it = values.cbegin(); it != values.cend(); ++it) {
        if (const auto tag = QFont::Tag::fromString(it.key().toLatin1()))
            font.setVariableAxis(*tag, it.value().toFloat());
    }
    return font;
}

inline QImage render(const QString &family, const QVariantMap &values,
                     int pixelSize = 72, qreal dpr = 1,
                     const QString &text = QStringLiteral("AAA"))
{
    QImage image(QSize(int(std::ceil(400 * dpr)), int(std::ceil(180 * dpr))),
                 QImage::Format_ARGB32_Premultiplied);
    image.setDevicePixelRatio(dpr);
    image.fill(Qt::transparent);
    QPainter painter(&image);
    painter.setFont(fontFor(family, values, pixelSize));
    painter.setPen(Qt::black);
    painter.drawText(QPointF(24, 125), text);
    painter.end();
    return image;
}

inline bool containsInk(const QImage &image)
{
    for (int y = 0; y < image.height(); ++y) {
        const auto *row = reinterpret_cast<const QRgb *>(image.constScanLine(y));
        for (int x = 0; x < image.width(); ++x) {
            if (qAlpha(row[x]) != 0)
                return true;
        }
    }
    return false;
}

inline QStringList verifyVariableAxes(const QString &family, const QVariantList &metadata,
                                       QJsonArray *evidence = nullptr)
{
    QStringList failures;
    const auto defaults = FontAxisPolicy::normalized(metadata);
    for (const auto &entry : metadata) {
        const auto axis = entry.toMap();
        const auto tag = axis.value(QStringLiteral("tag")).toString();
        auto minimum = defaults;
        auto maximum = defaults;
        minimum[tag] = axis.value(QStringLiteral("minimum"));
        maximum[tag] = axis.value(QStringLiteral("maximum"));
        const auto low = render(family, minimum);
        const auto high = render(family, maximum);
        const bool ink = containsInk(low) && containsInk(high);
        const bool changed = low != high;
        if (!ink || !changed)
            failures.append(family + QStringLiteral(" / ") + tag);
        if (evidence) {
            evidence->append(QJsonObject{{"family", family}, {"axis", tag},
                {"minimum", minimum.value(tag).toDouble()}, {"maximum", maximum.value(tag).toDouble()},
                {"inkPresent", ink}, {"actualRasterChanged", changed}});
        }
    }
    return failures;
}

inline bool usesRealFallbackForB(const QString &family, const QVariantMap &values)
{
    const QFont font = fontFor(family, values, 48);
    const auto primary = QRawFont::fromFont(font);
    // The original fixtures deliberately contain A but not B. Do not count a
    // tofu/missing-glyph box as successful fallback merely because it has pixels.
    if (!primary.isValid() || primary.familyName() != family
        || primary.supportsCharacter(uint('B'))) {
        return false;
    }
    QTextLayout layout(QStringLiteral("B"), font);
    layout.beginLayout();
    auto line = layout.createLine();
    if (line.isValid())
        line.setLineWidth(200);
    layout.endLayout();
    for (const QGlyphRun &run : layout.glyphRuns()) {
        if (!run.rawFont().isValid() || run.rawFont().familyName() == family)
            continue;
        for (const quint32 glyph : run.glyphIndexes()) {
            if (glyph != 0)
                return true;
        }
    }
    return false;
}

} // namespace SwirlFontAutomationRaster
