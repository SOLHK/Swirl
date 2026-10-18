#pragma once
#include <QQuickPaintedItem>
#include <QFont>
#include <QColor>
#include <QImage>
#include <QtQml/qqmlregistration.h>

// Keep a single painted surface per live preview instead of scene-graph glyph
// textures for the stream of variable-font coordinates. The font engine and
// OpenType axes are unchanged; this class never registers or instances a font.
class VariableFontPreview : public QQuickPaintedItem {
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
    void paint(QPainter *painter) override;
signals:
    void textChanged();
    void fontChanged();
    void colorChanged();
protected:
    void geometryChange(const QRectF &next,const QRectF &previous) override;
    void itemChange(ItemChange change,const ItemChangeData &data) override;
    void updatePolish() override;
private:
    void scheduleRaster();
    QString m_text;
    QFont m_font;
    QColor m_color=Qt::black;
    QImage m_raster;
};
