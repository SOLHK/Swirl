#pragma once
#include "ProxyNode.h"
#include <QObject>
#include <QVariantList>

class NodeStore final : public QObject {
    Q_OBJECT
public:
    explicit NodeStore(QString path = {}, QObject *parent = nullptr);
    QList<ProxyNode> nodes() const { return m_nodes; }
    QVariantList publicRows() const;
    QString selectedId() const { return m_selected; }
    QString error() const { return m_error; }
    QString filePath() const { return m_path; }
    bool saveNode(const QVariantMap &input);
    bool removeNode(const QString &id);
    bool select(const QString &id);
signals:
    void changed();
private:
    bool write(const QList<ProxyNode> &nodes, const QString &selected);
    void load();
    QString m_path, m_selected, m_error;
    QList<ProxyNode> m_nodes;
    bool m_healthy = true;
};
