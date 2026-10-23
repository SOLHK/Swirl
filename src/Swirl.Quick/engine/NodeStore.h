#pragma once
#include "ProxyNode.h"
#include <QObject>
#include <QVariantList>
#include <QUrl>
#include <QHash>
#include <atomic>
#include <functional>
#include <memory>

struct NodeSubscription {
    QString id, name;
    QString formatHint="auto";
    // Preserve the existing full-profile behavior for old snapshots and callers.
    QString importScope="full-profile";
    QUrl url; // Token-bearing URL is DPAPI protected and never exposed to QML.
    int intervalMinutes=360;
    bool enabled=true;
    qint64 lastSuccess=0;
};

class NodeStore final : public QObject {
    Q_OBJECT
public:
    // The ciphertext and decrypted snapshot are both bounded. Individual
    // imported documents keep NodeImporter's smaller 4 MiB input limit.
    static constexpr qsizetype MaximumBytes = 32 * 1024 * 1024;
    explicit NodeStore(QString path = {}, QObject *parent = nullptr);
    ~NodeStore() override;
    QList<ProxyNode> nodes() const { return m_nodes; }
    QVariantList publicRows() const;
    QString selectedId() const { return m_selected; }
    QString error() const { return m_error; }
    QString filePath() const { return m_path; }
    bool saving() const { return m_saving; }
    bool saveNode(const QVariantMap &input);
    bool removeNode(const QString &id);
    bool select(const QString &id);
    QList<NodeSubscription> subscriptions() const { return m_subscriptions; }
    QVariantList publicSubscriptions() const;
    bool saveSubscription(const QString &id, const QString &name, const QUrl &url, int intervalMinutes, bool enabled,const QString &formatHint={},const QString &importScope={});
    static QStringList subscriptionFormats(){return {"auto","loon","shadowrocket","surge","quantumult-x","sing-box","xray-v2ray-json"};}
    static QStringList subscriptionScopes(){return {"full-profile","nodes-only"};}
    bool removeSubscription(const QString &id);
    // A prepared import is immutable outside this store. Names/parse IDs map to
    // the final stable UUIDs before any policy configuration is compiled.
    class ImportPlan {
    public:
        QList<ProxyNode> nodes() const { return m_nodes; }
        QHash<QString,QString> nameToId() const { return m_names; }
        QHash<QString,QString> importedToStoredIds() const { return m_ids; }
    private:
        friend class NodeStore;
        const NodeStore *m_owner=nullptr;
        quint64 m_revision=0;
        QList<ProxyNode> m_nodes;
        QList<NodeSubscription> m_sources;
        QString m_selected;
        QHash<QString,QString> m_names,m_ids;
    };
    bool prepareImport(const QList<ProxyNode> &incoming, const QString &sourceId, ImportPlan *plan);
    bool commitImport(const ImportPlan &plan, const QJsonObject &networkConfiguration = {});
    // Returns whether the immutable plan was queued. On rejection no callback
    // runs; on completion the callback runs on this store's owning thread.
    bool commitImportAsync(const ImportPlan &plan, const QJsonObject &networkConfiguration,
                           std::function<void(bool,const QString &)> completion);
    QJsonObject networkConfiguration() const { return m_networkConfiguration; }
    bool saveNetworkConfiguration(const QJsonObject &configuration);
    bool importNodes(QList<ProxyNode> incoming, const QString &sourceId = {});
    static bool allowedSubscriptionUrl(const QUrl &url);
signals:
    void changed();
    void selectionChanged();
private:
    bool write(const QList<ProxyNode> &nodes, const QString &selected, const QList<NodeSubscription> &subscriptions, const QJsonObject &networkConfiguration);
    bool allowMutation();
    void adoptSnapshot(const QList<ProxyNode> &nodes, const QString &selected, const QList<NodeSubscription> &subscriptions, const QJsonObject &networkConfiguration,const QByteArray &snapshotDigest);
    void load();
    QString m_path, m_selected, m_error;
    QList<ProxyNode> m_nodes;
    mutable QVariantList m_publicRows;
    QList<NodeSubscription> m_subscriptions;
    QJsonObject m_networkConfiguration;
    bool m_healthy = true;
    QByteArray m_snapshotDigest;
    bool m_legacySelection = true;
    bool m_saving = false;
    std::shared_ptr<std::atomic_bool> m_saveCancelled;
    quint64 m_revision=0;
};
