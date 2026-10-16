#pragma once
#include <QQuickItem>
#include <QtQml/qqmlregistration.h>

// Four small destination-out quads feather the existing framebuffer in place.
// No window texture, text resampling, screenshot, or extra rendering process.
class WindowEdge : public QQuickItem {
 Q_OBJECT
 QML_ELEMENT
 Q_PROPERTY(qreal radius READ radius WRITE setRadius NOTIFY radiusChanged)
public:
 explicit WindowEdge(QQuickItem *parent=nullptr);
 qreal radius() const {return m_radius;}
 void setRadius(qreal value);
signals:
 void radiusChanged();
protected:
 QSGNode *updatePaintNode(QSGNode *,UpdatePaintNodeData *) override;
 void geometryChange(const QRectF &,const QRectF &) override;
 void itemChange(ItemChange,const ItemChangeData &) override;
private:
 qreal m_radius=0;
};
