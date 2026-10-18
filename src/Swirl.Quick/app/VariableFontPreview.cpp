#include "VariableFontPreview.h"
#include <QQuickWindow>
#include <QPainter>
#include <QTextLayout>
#include <QTextOption>
#include <QtMath>
#include <QMatrix4x4>
#ifdef SWIRL_UI_TESTS
#include <chrono>
static qint64 rasterClockNs() { return std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now().time_since_epoch()).count(); }
#endif

// Adjust the rendered origin, never the layout geometry or glyph metrics.
// Keep filtering for transformed animation frames; snap only an unscaled surface.
class PreviewPixelAlignment : public QQuickTransform {
public:
    explicit PreviewPixelAlignment(QObject *parent):QQuickTransform(parent){}
    QPointF offset() const { return m_offset; }
    void setOffset(const QPointF &offset){if(m_offset==offset)return;m_offset=offset;update();}
    void applyTo(QMatrix4x4 *matrix) const override {matrix->translate(m_offset.x(),m_offset.y());}
private:
    QPointF m_offset;
};

VariableFontPreview::VariableFontPreview(QQuickItem *parent) : QQuickPaintedItem(parent)
{
    setAntialiasing(true);
    m_pixelAlignment=new PreviewPixelAlignment(this);
    auto transforms=transform();transforms.append(&transforms,m_pixelAlignment);
    connectAlignmentWindow();
}
void VariableFontPreview::connectAlignmentWindow()
{
    QObject::disconnect(m_alignmentConnection);
    if(window())m_alignmentConnection=connect(window(),&QQuickWindow::afterAnimating,this,&VariableFontPreview::alignRaster);
    alignRaster();
}
void VariableFontPreview::alignRaster()
{
    if(!m_pixelAlignment||!window())return;
    auto transforms=transform();
    if(scale()!=1||rotation()!=0||transforms.count(&transforms)!=1){m_pixelAlignment->setOffset({});return;}
    const auto origin=mapToScene(QPointF());
    const auto dx=mapToScene(QPointF(1,0))-origin,dy=mapToScene(QPointF(0,1))-origin;
    if(qAbs(dx.x()-1)>1e-5||qAbs(dx.y())>1e-5||qAbs(dy.x())>1e-5||qAbs(dy.y()-1)>1e-5){m_pixelAlignment->setOffset({});return;}
    // Read the unmodified parent/position, not our rounded transform output:
    // feeding float mapToScene output back into the offset would dirty idle frames.
    const auto base=parentItem()?parentItem()->mapToScene(position()):position();
    const auto dpr=window()->effectiveDevicePixelRatio();
    // mapToScene uses float matrices; stabilize half-pixel ties against roundoff.
    m_pixelAlignment->setOffset(QPointF(qFloor(base.x()*dpr+.50001)/dpr-base.x(),qFloor(base.y()*dpr+.50001)/dpr-base.y()));
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
    alignRaster();
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
    if(next.topLeft()!=previous.topLeft())alignRaster();
}
void VariableFontPreview::itemChange(ItemChange change,const ItemChangeData &data)
{
    QQuickPaintedItem::itemChange(change,data);
    if(change==ItemSceneChange&&m_pixelAlignment)connectAlignmentWindow();
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
