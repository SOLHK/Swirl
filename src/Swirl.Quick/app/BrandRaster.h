#pragma once
#include <QSvgRenderer>
#include <QImage>
#include <QPainter>
#include <array>

// Include the taskbar's exact sizes at 100%, 125%, 150%, 175%, 200%, 250%, 300%
// and 400%, alongside title-bar, Start and Explorer sizes. Runtime QIcon and
// the packaged ICO must use the same frames.
inline constexpr std::array<int, 18> swirlBrandIconSizes{
    16, 20, 24, 28, 30, 32, 36, 40, 42, 48, 56, 60, 64, 72, 80, 96, 128, 256
};

// Preserve the canonical paths and aspect ratio. Remove only the SVG's
// transparent artboard padding, and use the same raster policy everywhere.
inline QImage swirlBrandRaster(QSvgRenderer &renderer,int size) {
 const auto original=renderer.viewBoxF();
 QImage scan(1024,1024,QImage::Format_ARGB32);scan.fill(Qt::transparent);
 {QPainter painter(&scan);renderer.render(&painter);}
 QRect bounds;for(int y=0;y<scan.height();++y)for(int x=0;x<scan.width();++x)if(qAlpha(scan.pixel(x,y))>0)bounds=bounds.united(QRect(x,y,1,1));
 QImage result(size,size,QImage::Format_ARGB32);result.fill(Qt::transparent);if(bounds.isEmpty())return result;
 const QRectF content(original.x()+bounds.x()*original.width()/1024,original.y()+bounds.y()*original.height()/1024,bounds.width()*original.width()/1024,bounds.height()*original.height()/1024);
 renderer.setViewBox(content);
 // The scan already encloses every antialiased path pixel. Fill the native
 // frame without adding a second inset; keep the entire wide mark proportional.
 const auto fit=content.size().scaled(size,size,Qt::KeepAspectRatio);
 QImage high(size*4,size*4,QImage::Format_ARGB32_Premultiplied);high.fill(Qt::transparent);
 {QPainter painter(&high);painter.scale(4,4);painter.setRenderHint(QPainter::Antialiasing);renderer.render(&painter,QRectF((size-fit.width())/2,(size-fit.height())/2,fit.width(),fit.height()));}
 renderer.setViewBox(original);
 return high.scaled(size,size,Qt::IgnoreAspectRatio,Qt::SmoothTransformation).convertToFormat(QImage::Format_ARGB32);
}
