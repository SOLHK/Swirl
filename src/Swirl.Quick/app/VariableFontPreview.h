#pragma once
#include <QQuickItem>
#include <QFont>
#include <QColor>
#include <QImage>
#ifdef SWIRL_UI_TESTS
#include <atomic>
#endif
#include <QtQml/qqmlregistration.h>

class PreviewPixelAlignment;

// Keep a single native raster texture per live preview instead of scene-graph glyph
// textures for the stream of variable-font coordinates. The font engine and
// OpenType axes are unchanged; this class never registers or instances a font.
class VariableFontPreview : public QQuickItem {
    Q_OBJECT
    QML_ELEMENT
    Q_PROPERTY(QString text READ text WRITE setText NOTIFY textChanged)
    Q_PROPERTY(QFont font READ font WRITE setFont NOTIFY fontChanged)
    Q_PROPERTY(QColor color READ color WRITE setColor NOTIFY colorChanged)
public:
    explicit VariableFontPreview(QQuickItem *parent=nullptr);
    QString text() const { return m_text; }
    QFont font() const { return m_font; }
    QColor color() const { return m_color; }
    void setText(const QString &text);
    void setFont(const QFont &font);
    void setColor(const QColor &color);
    QRectF boundingRect() const override;
#ifdef SWIRL_UI_TESTS
    void setMeasureRaster(bool enabled) { m_measureRaster=enabled; }
    qreal rasterDevicePixelRatio() const { return m_raster.devicePixelRatio(); }
    QSize rasterPixelSize() const { return m_raster.size(); }
#endif
signals:
    void textChanged();
    void fontChanged();
    void colorChanged();
#ifdef SWIRL_UI_TESTS
    void rasterMeasured(qint64 startedNs,qint64 finishedNs);
    void textureMeasured(qint64 startedNs,qint64 finishedNs);
#endif
protected:
    void geometryChange(const QRectF &next,const QRectF &previous) override;
    void itemChange(ItemChange change,const ItemChangeData &data) override;
    void updatePolish() override;
    QSGNode *updatePaintNode(QSGNode *node,UpdatePaintNodeData *) override;
private:
    void scheduleRaster();
    void connectAlignmentWindow();
    void observeScreen();
    void updateDisplayMetrics();
    void alignRaster();
    PreviewPixelAlignment *m_pixelAlignment=nullptr;
    QMetaObject::Connection m_alignmentConnection;
    QMetaObject::Connection m_screenConnection;
    QMetaObject::Connection m_logicalDpiConnection;
    qreal m_logicalDpiX=0, m_logicalDpiY=0;
    QImage m_metricsDevice{1,1,QImage::Format_ARGB32_Premultiplied};
    QString m_text;
    QFont m_font;
    QColor m_color=Qt::black;
    QImage m_raster;
    QPointF m_rasterOffset;
    bool m_rasterDirty=true;
    quint64 m_rasterRevision=0;
#ifdef SWIRL_UI_TESTS
    std::atomic_bool m_measureRaster{false};
#endif
};
