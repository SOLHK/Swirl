#include "SvgIconProvider.h"
#include <QFile>
#include <QSvgRenderer>
#include <QPainter>
#include <QColor>
QImage SvgIconProvider::requestImage(const QString &id, QSize *size, const QSize &requested)
{
    const auto parts=id.split('/');
    const QString name=parts.value(0);
    if (name.contains("..") || name.contains('\\')) return {};
    QFile file(QStringLiteral(":/swirl/icons/ui/")+name+QStringLiteral(".svg"));
    if (!file.open(QIODevice::ReadOnly)) return {};
    QByteArray svg=file.readAll();
    const QColor tint("#"+parts.value(1));
    if (tint.isValid()) {
        svg.replace("#17181B",tint.name(QColor::HexRgb).toUtf8());
        svg.replace("#212121",tint.name(QColor::HexRgb).toUtf8());
    }
    const QSize dimensions=requested.isValid()?requested:QSize(24,24);
    QImage image(dimensions,QImage::Format_ARGB32_Premultiplied);
    image.fill(Qt::transparent);
    QSvgRenderer renderer(svg);
    QPainter painter(&image);
    if (tint.isValid()) painter.setOpacity(tint.alphaF());
    renderer.render(&painter);
    if (size) *size=dimensions;
    return image;
}
