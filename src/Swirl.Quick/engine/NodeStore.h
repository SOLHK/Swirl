#pragma once
#include "ProxyNode.h"
#include <QObject>
#include <QVariantList>
#include <QUrl>
#include <QHash>
#include <atomic>
#include <functional>
#include <memory>
#include <optional>
class QLockFile;

struct NodeSubscription {
    QString id, name;
    QString formatHint="auto";
    // Legacy metadata only; automatic refresh always has nodes-only authority.
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
    static QStringList subscriptionFormats(){return {"auto","clash","loon","shadowrocket","surge","quantumult-x","sing-box","xray-v2ray-json"};}
    static QStringList subscriptionScopes(){return {"full-profile","nodes-only"};}
    bool removeSubscription(const QString &id);
    int legacyNodeCount() const;
    bool cleanLegacyNodes();
    // A prepared import is immutable outside this store. Names/parse IDs map to
    // the final stable UUIDs before any policy configuration is compiled.
    class ImportPlan {
    public:
        QList<ProxyNode> nodes() const { return m_nodes; }
        QHash<QString,QString> nameToId() const { return m_names; }
        QHash<QString,QString> importedToStoredIds() const { return m_ids; }
        QJsonObject retainedNetworkConfiguration() const { return m_network; }
        QStringList removedNodeIds() const { return m_removedIds; }
    private:
        friend class NodeStore;
        const NodeStore *m_owner=nullptr;
        quint64 m_revision=0;
        QList<ProxyNode> m_nodes;
        QList<NodeSubscription> m_sources;
        QString m_selected;
        QHash<QString,QString> m_names,m_ids;
        QJsonObject m_network;
        QStringList m_removedIds;
    };
    bool prepareImport(const QList<ProxyNode> &incoming, const QString &sourceId, ImportPlan *plan);
    bool prepareSaveNode(const QVariantMap &,ImportPlan *);
    bool prepareRemoveNode(const QString &,ImportPlan *);
    bool prepareSaveSubscription(const QString &id,const QString &name,const QUrl &,int intervalMinutes,bool enabled,const QString &formatHint,const QString &importScope,ImportPlan *);
    bool prepareRemoveSubscription(const QString &,ImportPlan *);
    bool prepareCleanLegacyNodes(ImportPlan *);
    bool commitImport(const ImportPlan &plan, const QJsonObject &networkConfiguration = {});
    // Returns whether the immutable plan was queued. On rejection no callback
    // runs; on completion the callback runs on this store's owning thread.
    bool commitImportAsync(const ImportPlan &plan, const QJsonObject &networkConfiguration,
                           std::function<void(bool,const QString &)> completion);
    QJsonObject networkConfiguration() const { return m_networkConfiguration; }
    bool saveNetworkConfiguration(const QJsonObject &configuration);
    bool importNodes(QList<ProxyNode> incoming, const QString &sourceId = {});
    static bool allowedSubscriptionUrl(const QUrl &url);
    bool configurationV2() const { return !m_configurationEnvelope.isEmpty(); }
    QString configurationStoreId() const { return m_configurationStoreId; }
    QString configurationRevision() const;
    QJsonObject configurationReceipt() const;
    QString issueConfigurationRevision();
    using SaveCompletion = std::function<void(bool,const QString &)>;
    bool saveConfigurationOffline(const QJsonObject &,const QString &requestId,const QString &revision,const QString &digest,SaveCompletion);
    bool beginConfigurationIntent(const QJsonObject &,const QString &requestId,const QString &revision,const QString &digest,SaveCompletion);
    bool saveCatalogOffline(const ImportPlan &,const QJsonObject &,const QString &requestId,const QString &revision,const QString &digest,SaveCompletion);
    bool beginCatalogIntent(const ImportPlan &,const QJsonObject &,const QString &requestId,const QString &revision,const QString &digest,SaveCompletion);
    bool configurationRecoveryPlan(ImportPlan *,QJsonObject *network);
    QJsonObject pendingConfigurationReceipt() const;
    bool recoverCatalogIntentOffline(const QString &validatedDigest,SaveCompletion);
    bool commitConfigurationIntent(SaveCompletion);
    bool abortConfigurationIntent(SaveCompletion);
    void releaseConfigurationLease();
    bool reserveConfigurationLease();
    bool configurationRecoveryRequired() const { return m_configurationRecoveryRequired; }
    bool configurationAvailable() const { return m_healthy&&!m_configurationRecoveryRequired&&m_configurationEnvelope.value("pending").toObject().value("operation").toString()!="revoke"; }
signals:
    void changed();
    void selectionChanged();
private:
    bool write(const QList<ProxyNode> &nodes, const QString &selected, const QList<NodeSubscription> &subscriptions, const QJsonObject &networkConfiguration,bool configurationMaintenance=false);
    bool allowMutation();
    bool legacyNode(const ProxyNode &node) const;
    void adoptSnapshot(const QList<ProxyNode> &nodes, const QString &selected, const QList<NodeSubscription> &subscriptions, const QJsonObject &networkConfiguration,const QByteArray &snapshotDigest);
    void load();
    bool acquireConfigurationLock();
    bool prepareCatalog(const QList<ProxyNode> &,const QString &,const QList<NodeSubscription> &,const QJsonObject &,ImportPlan *);
    bool decodeCatalogSnapshot(const QJsonObject &,ImportPlan *);
    bool scrubRevokedSources(ImportPlan *);
    bool persistConfigurationState(const QJsonObject &network,const QJsonObject &envelope,bool adopt,bool retainLease,SaveCompletion,const ImportPlan *catalog=nullptr,bool pendingCatalog=false);
    QJsonObject configurationEnvelope(const QString &requestId,const QString &revision,const QString &digest) const;
    QJsonObject m_configurationEnvelope;
    QString m_configurationStoreId;
    quint64 m_lastIssuedRevision=0;
    bool m_configurationLease=false,m_configurationRecoveryRequired=false;
    std::shared_ptr<QLockFile> m_configurationLock;
    std::optional<ImportPlan> m_catalogIntent;
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
