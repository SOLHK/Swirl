#pragma once
#include <QSvgRenderer>
#include <QImage>
#include <QPainter>

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
 // Native small frames get a half-pixel safe edge; larger frames use 2%.
 const qreal edge=qMax(0.5,size*0.02);const auto fit=content.size().scaled(size-2*edge,size-2*edge,Qt::KeepAspectRatio);
 QImage high(size*4,size*4,QImage::Format_ARGB32_Premultiplied);high.fill(Qt::transparent);
 {QPainter painter(&high);painter.scale(4,4);painter.setRenderHint(QPainter::Antialiasing);renderer.render(&painter,QRectF((size-fit.width())/2,(size-fit.height())/2,fit.width(),fit.height()));}
 renderer.setViewBox(original);
 return high.scaled(size,size,Qt::IgnoreAspectRatio,Qt::SmoothTransformation).convertToFormat(QImage::Format_ARGB32);
}
