#pragma once

#include <QGlyphRun>
#include <QImage>
#include <QJsonArray>
#include <QJsonObject>
#include <QTextLayout>
#include <QtMath>

namespace SwirlFontReference {

struct AlphaReference {
    QImage image;
    QPoint origin;
    int glyphCount=0;
    int nonEmptyOutlines=0;
    int nonEmptyOutlinesWithoutMask=0;
    int emptyMaps=0;
    int invalidMaps=0;
    int clippedMaps=0;
    int boundsSizeMismatches=0;
    int nonzeroCoveragePixels=0;
    int intermediateCoveragePixels=0;
    QJsonArray firstGlyphMetrics;
};

struct PixelComparison {
    int pixelsOverTolerance=0;
    int maxChannelDelta=0;
};

inline int maxChannelDeltaFromGray(QRgb pixel,int gray)
{
    return qMax(qAbs(qRed(pixel)-gray),qMax(qAbs(qGreen(pixel)-gray),qAbs(qBlue(pixel)-gray)));
}

// This coverage oracle uses QRawFont's per-glyph alpha-map API. It is not the
// pixel reference: it independently checks glyph availability, finite outline
// extents, coverage, and clipping without replaying QTextLayout::draw.
inline AlphaReference alphaReference(const QTextLayout &layout,qreal dpr)
{
    QRectF ink=layout.boundingRect();
    for(const auto &run:layout.glyphRuns()){
        const auto glyphs=run.glyphIndexes();
        const auto positions=run.positions();
        ink=ink.united(run.boundingRect());
        for(qsizetype i=0;i<qMin(glyphs.size(),positions.size());++i)
            ink=ink.united(run.rawFont().pathForGlyph(glyphs[i]).boundingRect().translated(positions[i]));
    }

    constexpr int coverageBorder=2;
    const int left=qFloor(qMin(0.,ink.left())*dpr)-coverageBorder;
    const int top=qFloor(qMin(0.,ink.top())*dpr)-coverageBorder;
    const int right=qCeil(ink.right()*dpr)+coverageBorder;
    const int bottom=qCeil(ink.bottom()*dpr)+coverageBorder;
    const QPoint origin(-left,-top);
    AlphaReference out{QImage(QSize(qMax(1,right-left),qMax(1,bottom-top)),QImage::Format_ARGB32_Premultiplied),origin};
    out.image.fill(Qt::transparent);

    QTransform device;
    device.scale(dpr,dpr);
    for(const auto &run:layout.glyphRuns()){
        const auto raw=run.rawFont();
        const auto glyphs=run.glyphIndexes();
        const auto positions=run.positions();
        for(qsizetype i=0;i<qMin(glyphs.size(),positions.size());++i){
            const auto glyph=glyphs[i];
            const auto outline=raw.pathForGlyph(glyph);
            if(outline.elementCount()>0)++out.nonEmptyOutlines;
            const auto mask=raw.alphaMapForGlyph(glyph,QRawFont::PixelAntialiasing,device);
            if(mask.isNull()){
                ++out.emptyMaps;
                if(outline.elementCount()>0)++out.nonEmptyOutlinesWithoutMask;
                continue;
            }
            if(mask.format()!=QImage::Format_Alpha8&&mask.format()!=QImage::Format_Indexed8){
                ++out.invalidMaps;
                continue;
            }
            ++out.glyphCount;
            const auto rawBounds=raw.boundingRect(glyph);
            const auto pathBounds=outline.boundingRect();
            if(out.firstGlyphMetrics.size()<8){
                int minValue=255,maxValue=0;
                for(int y=0;y<mask.height();++y)for(int x=0;x<mask.width();++x){
                    const int value=mask.constScanLine(y)[x];
                    minValue=qMin(minValue,value);maxValue=qMax(maxValue,value);
                }
                out.firstGlyphMetrics.append(QJsonObject{
                    {"glyph",int(glyph)},
                    {"position",QJsonArray{positions[i].x(),positions[i].y()}},
                    {"rawBounds",QJsonArray{rawBounds.x(),rawBounds.y(),rawBounds.width(),rawBounds.height()}},
                    {"pathBounds",QJsonArray{pathBounds.x(),pathBounds.y(),pathBounds.width(),pathBounds.height()}},
                    {"mapWidth",mask.width()},{"mapHeight",mask.height()},{"mapFormat",int(mask.format())},
                    {"mapMin",minValue},{"mapMax",maxValue}
                });
            }

            const QRectF bounds=device.mapRect(pathBounds.translated(positions[i]));
            const int x=origin.x()+qFloor(bounds.left());
            const int y=origin.y()+qFloor(bounds.top());
            if(qCeil(bounds.right())-qFloor(bounds.left())!=mask.width()
               ||qCeil(bounds.bottom())-qFloor(bounds.top())!=mask.height())
                ++out.boundsSizeMismatches;
            if(x<0||y<0||x+mask.width()>out.image.width()||y+mask.height()>out.image.height()){
                ++out.clippedMaps;
                continue;
            }

            for(int my=0;my<mask.height();++my){
                const auto *src=mask.constScanLine(my);
                auto *dst=reinterpret_cast<QRgb *>(out.image.scanLine(y+my));
                for(int mx=0;mx<mask.width();++mx){
                    const int foreground=src[mx];
                    if(foreground)++out.nonzeroCoveragePixels;
                    if(foreground>0&&foreground<255)++out.intermediateCoveragePixels;
                    if(!foreground)continue;
                    const int background=qAlpha(dst[x+mx]);
                    const int alpha=foreground+qRound(background*(255-foreground)/255.0);
                    dst[x+mx]=qRgba(0,0,0,alpha);
                }
            }
        }
    }
    return out;
}

inline PixelComparison compareWindowToReference(const QImage &windowImage,const QImage &reference,
                                                QPoint windowOrigin,QPoint referenceOrigin)
{
    PixelComparison result;
    for(int y=0;y<windowImage.height();++y){
        const int ry=y-windowOrigin.y()+referenceOrigin.y();
        for(int x=0;x<windowImage.width();++x){
            const int rx=x-windowOrigin.x()+referenceOrigin.x();
            const int gray=rx>=0&&ry>=0&&rx<reference.width()&&ry<reference.height()
                ?255-qAlpha(reference.pixel(rx,ry)):255;
            const int delta=maxChannelDeltaFromGray(windowImage.pixel(x,y),gray);
            if(delta>2)++result.pixelsOverTolerance;
            result.maxChannelDelta=qMax(result.maxChannelDelta,delta);
        }
    }
    return result;
}

} // namespace SwirlFontReference
