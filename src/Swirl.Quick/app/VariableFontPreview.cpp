#include "VariableFontPreview.h"
#include <QQuickWindow>
#include <QPainter>
#include <QTextLayout>
#include <QTextOption>
#include <QtMath>
#ifdef SWIRL_UI_TESTS
#include <chrono>
static qint64 rasterClockNs() { return std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now().time_since_epoch()).count(); }
#endif

VariableFontPreview::VariableFontPreview(QQuickItem *parent) : QQuickPaintedItem(parent)
{
    setAntialiasing(true);
}
void VariableFontPreview::scheduleRaster()
{
    // QQuickItem polish coalesces only rendering work; model axes stay exact and immediate.
    polish();update();
}
void VariableFontPreview::setText(const QString &text)
{
    if(m_text==text)return;m_text=text;emit textChanged();scheduleRaster();
}
void VariableFontPreview::setFont(const QFont &font)
{
    if(m_font==font)return;m_font=font;emit fontChanged();scheduleRaster();
}
void VariableFontPreview::setColor(const QColor &color)
{
    if(m_color==color)return;m_color=color;emit colorChanged();scheduleRaster();
}
void VariableFontPreview::updatePolish()
{
    if(width()<=0)return;
#ifdef SWIRL_UI_TESTS
    const auto started=m_measureRaster?rasterClockNs():0;
#endif
    QTextLayout layout(m_text,m_font);QTextOption option;
    option.setWrapMode(QTextOption::WrapAtWordBoundaryOrAnywhere);layout.setTextOption(option);
    layout.beginLayout();qreal y=0;
    while(true){auto line=layout.createLine();if(!line.isValid())break;
        line.setLineWidth(width());line.setPosition(QPointF(0,y));y+=line.height();}
    layout.endLayout();setImplicitHeight(qCeil(y));
    const qreal dpr=window()?window()->effectiveDevicePixelRatio():1;
    QImage image(QSize(qCeil(width()*dpr),qMax(1,qCeil(y*dpr))),QImage::Format_ARGB32_Premultiplied);
    image.setDevicePixelRatio(dpr);image.fill(Qt::transparent);
    QPainter painter(&image);painter.setPen(m_color);painter.setRenderHint(QPainter::TextAntialiasing,true);
    layout.draw(&painter,QPointF());painter.end();m_raster=std::move(image);
    update();
#ifdef SWIRL_UI_TESTS
    if(started)emit rasterMeasured(started,rasterClockNs());
#endif
}
void VariableFontPreview::geometryChange(const QRectF &next,const QRectF &previous)
{
    QQuickPaintedItem::geometryChange(next,previous);
    if(next.width()!=previous.width())scheduleRaster();
}
void VariableFontPreview::itemChange(ItemChange change,const ItemChangeData &data)
{
    QQuickPaintedItem::itemChange(change,data);
    if(change==ItemDevicePixelRatioHasChanged||change==ItemSceneChange)scheduleRaster();
}
void VariableFontPreview::paint(QPainter *painter)
{
    // One native raster at the current DPR, with no resampling or sharpening.
    // Keep only this frame's image; do not cache images or fonts by coordinate.
#ifdef SWIRL_UI_TESTS
    const auto started=m_measureRaster?rasterClockNs():0;
#endif
    painter->drawImage(QPointF(),m_raster);
#ifdef SWIRL_UI_TESTS
    if(started)emit paintMeasured(started,rasterClockNs());
#endif
}
