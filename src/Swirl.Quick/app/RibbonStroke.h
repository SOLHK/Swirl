#pragma once
#include <QColor>
#include <QPointF>
#include <QQuickItem>
#include <QVector>
#include <QtQml/qqmlregistration.h>

// A finite ribbon or feather vane drawn directly in scene coordinates. The guide is
// authored by Swirl (absolute M/C commands), never supplied by a subscription.
class RibbonStroke : public QQuickItem {
    Q_OBJECT
    QML_ELEMENT
    Q_PROPERTY(QString guide READ guide WRITE setGuide NOTIFY guideChanged)
    Q_PROPERTY(qreal trimStart READ trimStart WRITE setTrimStart NOTIFY trimStartChanged)
    Q_PROPERTY(qreal trimEnd READ trimEnd WRITE setTrimEnd NOTIFY trimEndChanged)
    Q_PROPERTY(qreal capStart READ capStart WRITE setCapStart NOTIFY capStartChanged)
    Q_PROPERTY(qreal capEnd READ capEnd WRITE setCapEnd NOTIFY capEndChanged)
    Q_PROPERTY(qreal ribbonWidth READ ribbonWidth WRITE setRibbonWidth NOTIFY ribbonWidthChanged)
    Q_PROPERTY(QColor ink READ ink WRITE setInk NOTIFY inkChanged)
    Q_PROPERTY(qreal settlement READ settlement WRITE setSettlement NOTIFY settlementChanged)
    Q_PROPERTY(qreal broadening READ broadening WRITE setBroadening NOTIFY broadeningChanged)
    Q_PROPERTY(qreal featherTexture READ featherTexture WRITE setFeatherTexture NOTIFY featherTextureChanged)
    Q_PROPERTY(qreal textureOrigin READ textureOrigin WRITE setTextureOrigin NOTIFY textureOriginChanged)
public:
    explicit RibbonStroke(QQuickItem *parent = nullptr);
    QString guide() const { return m_guide; }
    qreal trimStart() const { return m_trimStart; }
    qreal trimEnd() const { return m_trimEnd; }
    qreal capStart() const { return m_capStart; }
    qreal capEnd() const { return m_capEnd; }
    qreal ribbonWidth() const { return m_ribbonWidth; }
    QColor ink() const { return m_ink; }
    qreal settlement() const { return m_settlement; }
    qreal broadening() const { return m_broadening; }
    qreal featherTexture() const { return m_featherTexture; }
    qreal textureOrigin() const { return m_textureOrigin; }
    void setGuide(const QString &value);
    void setTrimStart(qreal value);
    void setTrimEnd(qreal value);
    void setCapStart(qreal value);
    void setCapEnd(qreal value);
    void setRibbonWidth(qreal value);
    void setInk(const QColor &value);
    void setSettlement(qreal value);
    void setBroadening(qreal value);
    void setFeatherTexture(qreal value);
    void setTextureOrigin(qreal value);
signals:
    void guideChanged();
    void trimStartChanged();
    void trimEndChanged();
    void capStartChanged();
    void capEndChanged();
    void ribbonWidthChanged();
    void inkChanged();
    void settlementChanged();
    void broadeningChanged();
    void featherTextureChanged();
    void textureOriginChanged();
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
    // Negative values use the visible trim. Overpasses share their whole
    // feather's cap range so local copies do not acquire false feather tips.
    qreal m_capStart = -1;
    qreal m_capEnd = -1;
    qreal m_ribbonWidth = 3.4;
    QColor m_ink = Qt::transparent;
    qreal m_settlement = 0;
    qreal m_broadening = 0;
    qreal m_featherTexture = 0;
    qreal m_textureOrigin = 0;
};
