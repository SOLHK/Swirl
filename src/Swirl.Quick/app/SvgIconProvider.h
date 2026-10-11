#pragma once
#include <QQuickImageProvider>
// Recolors monochrome SVG strokes before vector rendering at the requested
// physical size. Brand SVGs never enter this provider and remain unchanged.
class SvgIconProvider final : public QQuickImageProvider {
public:
    SvgIconProvider() : QQuickImageProvider(QQuickImageProvider::Image) {}
    QImage requestImage(const QString &, QSize *, const QSize &) override;
};
