#include "SvgIconProvider.h"
#include <QFile>
#include <QSvgRenderer>
#include <QPainter>
#include <QColor>
#include <QQueue>
#include <QBitArray>
QImage SvgIconProvider::requestImage(const QString &id, QSize *size, const QSize &requested)
{
    const auto parts=id.split('/');
    const QString name=parts.value(0);
    if (name.contains("..") || name.contains('\\')) return {};
    if(name.startsWith("reference-")) {
        // Reference icons were cropped from the light screenshot. Remove only
        // the connected pale surround at render time; enclosed white details
        // and the original asset files remain intact for both render backends.
        QImage original(QStringLiteral(":/swirl/icons/ui/")+name+QStringLiteral(".png"));
        if(original.isNull())return {};
        auto image=original.convertToFormat(QImage::Format_ARGB32);
        const auto background=image.pixelColor(0,0);
        const int width=image.width(),height=image.height();
        QBitArray visited(width*height);QQueue<QPoint> pending;
        const auto append=[&](int x,int y){if(x>=0 && y>=0 && x<width && y<height && !visited.testBit(y*width+x)){visited.setBit(y*width+x);pending.enqueue({x,y});}};
        for(int x=0;x<width;++x){append(x,0);append(x,height-1);}
        for(int y=0;y<height;++y){append(0,y);append(width-1,y);}
        while(!pending.isEmpty()) {
            const auto p=pending.dequeue();const auto color=image.pixelColor(p);
            if(qAbs(color.red()-background.red())>3 || qAbs(color.green()-background.green())>3 || qAbs(color.blue()-background.blue())>3)continue;
            image.setPixelColor(p,Qt::transparent);
            append(p.x()-1,p.y());append(p.x()+1,p.y());append(p.x(),p.y()-1);append(p.x(),p.y()+1);
        }
        if(requested.isValid())image=image.scaled(requested,Qt::KeepAspectRatio,Qt::SmoothTransformation);
        if(size)*size=image.size();
        return image;
    }
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
