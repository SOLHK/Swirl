#pragma once
#include <QColor>
#include <QPointF>
#include <QQuickItem>
#include <QVector>
#include <QtQml/qqmlregistration.h>

// A finite, flat ribbon drawn directly in scene coordinates. The guide is
// authored by Swirl (absolute M/C commands), never supplied by a subscription.
class RibbonStroke final : public QQuickItem {
    Q_OBJECT
    QML_ELEMENT
    Q_PROPERTY(QString guide READ guide WRITE setGuide NOTIFY guideChanged)
    Q_PROPERTY(qreal trimStart READ trimStart WRITE setTrimStart NOTIFY trimStartChanged)
    Q_PROPERTY(qreal trimEnd READ trimEnd WRITE setTrimEnd NOTIFY trimEndChanged)
    Q_PROPERTY(qreal ribbonWidth READ ribbonWidth WRITE setRibbonWidth NOTIFY ribbonWidthChanged)
    Q_PROPERTY(QColor ink READ ink WRITE setInk NOTIFY inkChanged)
    Q_PROPERTY(qreal settlement READ settlement WRITE setSettlement NOTIFY settlementChanged)
    Q_PROPERTY(qreal broadening READ broadening WRITE setBroadening NOTIFY broadeningChanged)
public:
    explicit RibbonStroke(QQuickItem *parent = nullptr);
    QString guide() const { return m_guide; }
    qreal trimStart() const { return m_trimStart; }
    qreal trimEnd() const { return m_trimEnd; }
    qreal ribbonWidth() const { return m_ribbonWidth; }
    QColor ink() const { return m_ink; }
    qreal settlement() const { return m_settlement; }
    qreal broadening() const { return m_broadening; }
    void setGuide(const QString &value);
    void setTrimStart(qreal value);
    void setTrimEnd(qreal value);
    void setRibbonWidth(qreal value);
    void setInk(const QColor &value);
    void setSettlement(qreal value);
    void setBroadening(qreal value);
signals:
    void guideChanged();
    void trimStartChanged();
    void trimEndChanged();
    void ribbonWidthChanged();
    void inkChanged();
    void settlementChanged();
    void broadeningChanged();
protected:
    QSGNode *updatePaintNode(QSGNode *, UpdatePaintNodeData *) override;
    void itemChange(ItemChange, const ItemChangeData &) override;
private:
    void rebuildGuide();
    QPointF pointAt(qreal distance) const;
    QString m_guide;
    QVector<QPointF> m_points;
    QVector<qreal> m_lengths;
    qreal m_trimStart = 0;
    qreal m_trimEnd = 1;
    qreal m_ribbonWidth = 3.4;
    QColor m_ink = Qt::transparent;
    qreal m_settlement = 0;
    qreal m_broadening = 0;
};
