#pragma once
#include "ProxyNode.h"
#include <QObject>
#include <QVariantList>
#include <QUrl>

struct NodeSubscription {
    QString id, name;
    QString formatHint="auto";
    QUrl url; // Token-bearing URL is DPAPI protected and never exposed to QML.
    int intervalMinutes=360;
    bool enabled=true;
    qint64 lastSuccess=0;
};

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
    QList<NodeSubscription> subscriptions() const { return m_subscriptions; }
    QVariantList publicSubscriptions() const;
    bool saveSubscription(const QString &id, const QString &name, const QUrl &url, int intervalMinutes, bool enabled,const QString &formatHint={});
    static QStringList subscriptionFormats(){return {"auto","loon","shadowrocket","surge","quantumult-x","sing-box"};}
    bool removeSubscription(const QString &id);
    bool importNodes(QList<ProxyNode> incoming, const QString &sourceId = {});
    static bool allowedSubscriptionUrl(const QUrl &url);
signals:
    void changed();
    void selectionChanged();
private:
    bool write(const QList<ProxyNode> &nodes, const QString &selected, const QList<NodeSubscription> &subscriptions);
    void load();
    QString m_path, m_selected, m_error;
    QList<ProxyNode> m_nodes;
    mutable QVariantList m_publicRows;
    QList<NodeSubscription> m_subscriptions;
    bool m_healthy = true;
};
