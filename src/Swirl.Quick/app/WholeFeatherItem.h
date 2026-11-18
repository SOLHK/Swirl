#pragma once
#include <QColor>
#include <QPointF>
#include <QQuickItem>
#include <QVector>
#include <QtQml/qqmlregistration.h>

// One complete closed feather. Flight uses ordinary Item transforms; only the
// final bend interpolates between two cached outlines in this item's coordinates.
class WholeFeatherItem : public QQuickItem {
    Q_OBJECT
    QML_ELEMENT
    Q_PROPERTY(QString sourcePath READ sourcePath WRITE setSourcePath NOTIFY sourcePathChanged)
    Q_PROPERTY(QPointF sourceRoot READ sourceRoot WRITE setSourceRoot NOTIFY sourceRootChanged)
    Q_PROPERTY(QPointF sourceTip READ sourceTip WRITE setSourceTip NOTIFY sourceTipChanged)
    Q_PROPERTY(QString targetPath READ targetPath WRITE setTargetPath NOTIFY targetPathChanged)
    Q_PROPERTY(QPointF targetRoot READ targetRoot WRITE setTargetRoot NOTIFY targetRootChanged)
    Q_PROPERTY(QPointF targetTip READ targetTip WRITE setTargetTip NOTIFY targetTipChanged)
    Q_PROPERTY(qreal morphProgress READ morphProgress WRITE setMorphProgress NOTIFY morphProgressChanged)
    Q_PROPERTY(QColor ink READ ink WRITE setInk NOTIFY inkChanged)
public:
    explicit WholeFeatherItem(QQuickItem *parent = nullptr);
    QString sourcePath() const { return m_sourcePath; }
    QPointF sourceRoot() const { return m_sourceRoot; }
    QPointF sourceTip() const { return m_sourceTip; }
    QString targetPath() const { return m_targetPath; }
    QPointF targetRoot() const { return m_targetRoot; }
    QPointF targetTip() const { return m_targetTip; }
    qreal morphProgress() const { return m_morphProgress; }
    QColor ink() const { return m_ink; }
    void setSourcePath(const QString &value);
    void setSourceRoot(const QPointF &value);
    void setSourceTip(const QPointF &value);
    void setTargetPath(const QString &value);
    void setTargetRoot(const QPointF &value);
    void setTargetTip(const QPointF &value);
    void setMorphProgress(qreal value);
    void setInk(const QColor &value);
signals:
    void sourcePathChanged();
    void sourceRootChanged();
    void sourceTipChanged();
    void targetPathChanged();
    void targetRootChanged();
    void targetTipChanged();
    void morphProgressChanged();
    void inkChanged();
protected:
    QSGNode *updatePaintNode(QSGNode *old, UpdatePaintNodeData *) override;
    void itemChange(ItemChange change, const ItemChangeData &data) override;
private:
    QString m_sourcePath, m_targetPath;
    QPointF m_sourceRoot, m_sourceTip, m_targetRoot, m_targetTip;
    qreal m_morphProgress = 0;
    QColor m_ink = Qt::transparent;
    bool m_sourceDirty = true, m_targetDirty = true;
    QVector<QPointF> m_sourceFirst, m_sourceSecond, m_targetFirst, m_targetSecond;
};
