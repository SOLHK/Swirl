#include "VariableFontPreview.h"
#include <QQuickWindow>
#include <QPainter>
#include <QTextLayout>
#include <QTextOption>
#include <QtMath>
#include <QMatrix4x4>
#include <QGlyphRun>
#include <QSGSimpleTextureNode>
#include <QSGTexture>
#include <QScopedPointer>
#include <QGuiApplication>
#include <QScreen>
#include <rhi/qrhi.h>
#include <cmath>
#include <memory>
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

VariableFontPreview::VariableFontPreview(QQuickItem *parent) : QQuickItem(parent)
{
    setFlag(ItemHasContents,true);
    setAntialiasing(true);
    m_pixelAlignment=new PreviewPixelAlignment(this);
    auto transforms=transform();transforms.append(&transforms,m_pixelAlignment);
    // A newly registered or removed face can change an unchanged QFont's
    // result. Qt clears its engine cache; invalidate our retained texture too.
    connect(qGuiApp,&QGuiApplication::fontDatabaseChanged,this,[this]{
        // A retained QFont can still own a removed Windows/FreeType engine
        // after the database invalidates its public caches. Detach that engine
        // through public setters, preserving every requested font value and its
        // resolve mask. No fontChanged signal or layout-property churn is needed.
        QFont refreshed=m_font;
        refreshed.setFamilies({});
        refreshed.setFamilies(m_font.families());
        refreshed.setResolveMask(m_font.resolveMask());
        m_font=refreshed;
        scheduleRaster();
    });
    connectAlignmentWindow();
}
void VariableFontPreview::connectAlignmentWindow()
{
    QObject::disconnect(m_alignmentConnection);
    QObject::disconnect(m_screenConnection);
    if(window()){
        m_alignmentConnection=connect(window(),&QQuickWindow::afterAnimating,this,&VariableFontPreview::alignRaster);
        m_screenConnection=connect(window(),&QQuickWindow::screenChanged,this,&VariableFontPreview::observeScreen);
    }
    observeScreen();
    alignRaster();
}
void VariableFontPreview::observeScreen()
{
    QObject::disconnect(m_logicalDpiConnection);
    auto *screen=window()?window()->screen():QGuiApplication::primaryScreen();
    if(screen)m_logicalDpiConnection=connect(screen,&QScreen::logicalDotsPerInchChanged,
                                            this,&VariableFontPreview::updateDisplayMetrics);
    updateDisplayMetrics();
}
void VariableFontPreview::updateDisplayMetrics()
{
    const auto *screen=window()?window()->screen():QGuiApplication::primaryScreen();
    qreal x=screen?screen->logicalDotsPerInchX():96;
    qreal y=screen?screen->logicalDotsPerInchY():96;
    if(!std::isfinite(x)||x<=0)x=96;
    if(!std::isfinite(y)||y<=0)y=96;
    if(qFuzzyCompare(x,m_logicalDpiX)&&qFuzzyCompare(y,m_logicalDpiY))return;
    m_logicalDpiX=x;m_logicalDpiY=y;
    // QTextLayout's paint device controls point-size metrics. Keep the source
    // QFont unchanged and express logical DPI here; DPR is applied by the raster.
    m_metricsDevice.setDotsPerMeterX(qRound(x/0.0254));
    m_metricsDevice.setDotsPerMeterY(qRound(y/0.0254));
    scheduleRaster();
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
    if(m_rasterDirty)return;
    m_rasterDirty=true;
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
    // QQuickWindow also forces polish on unchanged screen notifications. Only
    // raster after one of our actual inputs (including resources) invalidates it.
    if(!m_rasterDirty)return;
    m_rasterDirty=false;
    if(width()<=0||m_text.isEmpty()){
        // A collapsed/cleared preview must release its old pixels and scene-graph
        // texture instead of retaining the last visible sample indefinitely.
        m_raster={};m_rasterOffset={};setImplicitHeight(0);++m_rasterRevision;update();
        return;
    }
    alignRaster();
#ifdef SWIRL_UI_TESTS
    const auto started=m_measureRaster?rasterClockNs():0;
#endif
    QTextLayout layout(m_text,m_font,&m_metricsDevice);QTextOption option;
    option.setWrapMode(QTextOption::WrapAtWordBoundaryOrAnywhere);layout.setTextOption(option);
    layout.beginLayout();qreal y=0;
    while(true){auto line=layout.createLine();if(!line.isValid())break;
        line.setLineWidth(width());line.setPosition(QPointF(0,y));y+=line.height();}
    layout.endLayout();setImplicitHeight(qCeil(y));
    const qreal dpr=window()?window()->effectiveDevicePixelRatio():1;
    QRectF ink=layout.boundingRect();
    for(const auto &run:layout.glyphRuns()){
        const auto raw=run.rawFont();const auto glyphs=run.glyphIndexes();const auto positions=run.positions();
        // A layout-supplied run rectangle can describe its line/selection box.
        // Union actual glyph extents as well, including overshoot above the ascent.
        ink=ink.united(run.boundingRect());
        for(qsizetype i=0;i<qMin(glyphs.size(),positions.size());++i)
            ink=ink.united(raw.boundingRect(glyphs[i]).translated(positions[i]));
    }
    // Keep native overhang and AA coverage without changing line spacing or advances.
    const int left=qFloor(qMin(0.,ink.left())*dpr)-2,top=qFloor(qMin(0.,ink.top())*dpr)-2;
    const int right=qCeil(qMax(width(),ink.right())*dpr)+2,bottom=qCeil(qMax(y,ink.bottom())*dpr)+2;
    m_rasterOffset=QPointF(left/dpr,top/dpr);
    const QSize pixelSize(qMax(1,right-left),qMax(1,bottom-top));
    QImage image=std::move(m_raster);
    if(image.size()!=pixelSize){
        image=QImage(pixelSize,QImage::Format_ARGB32_Premultiplied);
#ifdef SWIRL_UI_TESTS
        if(!image.isNull())++m_rasterAllocations;
#endif
    }else{
        // Uploads may still share the previous frame's data. Detach before paint
        // if necessary; never mutate a buffer queued on the render thread.
#ifdef SWIRL_UI_TESTS
        const auto *previousBits=image.constBits();
#endif
        image.detach();
#ifdef SWIRL_UI_TESTS
        if(image.constBits()!=previousBits)++m_rasterAllocations;
#endif
    }
    image.setDotsPerMeterX(m_metricsDevice.dotsPerMeterX());
    image.setDotsPerMeterY(m_metricsDevice.dotsPerMeterY());
    image.setDevicePixelRatio(dpr);image.fill(Qt::transparent);
    QPainter painter(&image);painter.setPen(m_color);painter.setRenderHint(QPainter::TextAntialiasing,true);
    painter.translate(-m_rasterOffset);layout.draw(&painter,QPointF());painter.end();
    m_raster=std::move(image);++m_rasterRevision;
    update();
#ifdef SWIRL_UI_TESTS
    if(started)emit rasterMeasured(started,rasterClockNs());
#endif
}
void VariableFontPreview::geometryChange(const QRectF &next,const QRectF &previous)
{
    QQuickItem::geometryChange(next,previous);
    if(next.width()!=previous.width())scheduleRaster();
    if(next.topLeft()!=previous.topLeft())alignRaster();
}
void VariableFontPreview::itemChange(ItemChange change,const ItemChangeData &data)
{
    QQuickItem::itemChange(change,data);
    if(change==ItemSceneChange&&m_pixelAlignment)connectAlignmentWindow();
    if(change==ItemDevicePixelRatioHasChanged||change==ItemSceneChange)scheduleRaster();
}
QRectF VariableFontPreview::boundingRect() const
{
    return QRectF(QPointF(),size()).united(QRectF(m_rasterOffset,m_raster.deviceIndependentSize()));
}
class PreviewTexture;
class PreviewTextureNode : public QSGSimpleTextureNode {
public:
    quint64 revision=0;
    QScopedPointer<QSGTexture> ownedTexture;
    PreviewTexture *reusableTexture=nullptr;
};

// QSGTexture's documented QRhi upload hook keeps the native texture alive while
// coordinates change. Unlike createTextureFromImage on every frame, same-sized
// samples do not repeatedly retire GPU resources and their staging allocations.
// All methods and destruction run on the scene-graph thread. QRhi belongs to the
// window; this node owns only its texture and one latest pending image.
class PreviewTexture final : public QSGTexture {
public:
    bool setImage(QRhi *rhi,const QImage &image,bool &allocated)
    {
        const int limit=rhi->resourceLimit(QRhi::TextureSizeMax);
        if(image.width()>limit||image.height()>limit)return false;
        const bool bgra=Q_BYTE_ORDER==Q_LITTLE_ENDIAN&&rhi->isTextureFormatSupported(QRhiTexture::BGRA8);
        const auto format=bgra?QRhiTexture::BGRA8:QRhiTexture::RGBA8;
        if(!m_texture||m_rhi!=rhi||m_texture->pixelSize()!=image.size()){
            std::unique_ptr<QRhiTexture> texture(rhi->newTexture(format,image.size()));
            if(!texture->create())return false;
            m_texture=std::move(texture);m_rhi=rhi;allocated=true;
        }
        m_pendingImage=bgra?image:image.convertToFormat(QImage::Format_RGBA8888_Premultiplied);
        return true;
    }
    qint64 comparisonKey() const override {return qint64(quintptr(m_texture.get()));}
    QSize textureSize() const override {return m_texture?m_texture->pixelSize():QSize();}
    bool hasAlphaChannel() const override {return true;}
    bool hasMipmaps() const override {return false;}
    QRhiTexture *rhiTexture() const override {return m_texture.get();}
    void commitTextureOperations(QRhi *rhi,QRhiResourceUpdateBatch *updates) override
    {
        if(rhi!=m_rhi||!m_texture||m_pendingImage.isNull())return;
        updates->uploadTexture(m_texture.get(),m_pendingImage);
        m_pendingImage={};
    }
private:
    QRhi *m_rhi=nullptr;
    std::unique_ptr<QRhiTexture> m_texture;
    QImage m_pendingImage;
};
QSGNode *VariableFontPreview::updatePaintNode(QSGNode *oldNode,UpdatePaintNodeData *)
{
    if(m_raster.isNull()||!window()){delete oldNode;return nullptr;}
    auto *node=static_cast<PreviewTextureNode *>(oldNode);
    if(!node)node=new PreviewTextureNode;
#ifdef SWIRL_UI_TESTS
    const auto started=m_measureRaster?rasterClockNs():0;
#endif
    if(node->revision!=m_rasterRevision){
        QSGTexture *texture=nullptr;PreviewTexture *reusable=nullptr;bool allocated=false;
        if(auto *rhi=window()->rhi()){
            reusable=node->reusableTexture?node->reusableTexture:new PreviewTexture;
            if(reusable->setImage(rhi,m_raster,allocated))texture=reusable;
            else{if(reusable!=node->reusableTexture)delete reusable;reusable=nullptr;}
        }
        // The software scene graph has no QRhi. Preserve its native image path;
        // also retain Qt's existing size-limit/allocation handling as a fallback.
        if(!texture){texture=window()->createTextureFromImage(m_raster);allocated=texture!=nullptr;}
        if(!texture){delete node;return nullptr;}
        node->setTexture(texture);
        if(node->ownedTexture.data()!=texture)node->ownedTexture.reset(texture);
        node->reusableTexture=reusable;node->revision=m_rasterRevision;
#ifdef SWIRL_UI_TESTS
        if(allocated)++m_textureAllocations;
#endif
    }
    // Physical image dimensions determine the quad. Never fit a rounded texture
    // back into the logical line box; that would resample at fractional DPRs.
    node->setRect(QRectF(m_rasterOffset,m_raster.deviceIndependentSize()));
    node->setFiltering(QSGTexture::Linear);
#ifdef SWIRL_UI_TESTS
    if(started)emit textureMeasured(started,rasterClockNs());
#endif
    return node;
}
