#pragma once
#include "NodeStore.h"
#include "NodeImporter.h"
#include <QNetworkAccessManager>
#include <QNetworkProxy>
#include <QNetworkProxyQuery>
#include <QPointer>
#include <QSet>
#include <QTimer>
#include <QQueue>
#include <functional>
#include <optional>

class QNetworkReply;
class NodeImportService final : public QObject {
    Q_OBJECT
    Q_PROPERTY(QVariantList providers READ providers NOTIFY changed)
    Q_PROPERTY(bool busy READ busy NOTIFY changed)
    Q_PROPERTY(QString message READ message NOTIFY changed)
    Q_PROPERTY(bool hasPreview READ hasPreview NOTIFY changed)
    Q_PROPERTY(QVariantList preview READ preview NOTIFY changed)
    Q_PROPERTY(QStringList previewDiagnostics READ previewDiagnostics NOTIFY changed)
public:
    using SystemProxyResolver=std::function<QList<QNetworkProxy>(const QNetworkProxyQuery &)>;
    explicit NodeImportService(NodeStore *store,QObject *parent=nullptr,
        std::function<qint64()> clock={}, int pollIntervalMs=60000,SystemProxyResolver systemProxies={});
    QVariantList providers() const;
    bool busy() const { return m_busy; }
    QString message() const { return m_message; }
    bool hasPreview() const { return m_pending.has_value(); }
    QVariantList preview() const;
    QStringList previewDiagnostics() const { return m_pending ? m_pending->diagnostics : QStringList{}; }
    Q_INVOKABLE void confirmImport();
    Q_INVOKABLE void cancelImport();
    Q_INVOKABLE void importText(const QString &text);
    Q_INVOKABLE void importClipboard();
    Q_INVOKABLE void importFile(const QUrl &file);
    Q_INVOKABLE void importUrl(const QUrl &url);
    Q_INVOKABLE void importNodesOnlyText(const QString &text);
    Q_INVOKABLE void importNodesOnlyClipboard();
    Q_INVOKABLE void importNodesOnlyFile(const QUrl &file);
    Q_INVOKABLE void importNodesOnlyUrl(const QUrl &url);
    Q_INVOKABLE bool saveSubscription(const QString &id,const QString &name,const QUrl &url,int intervalMinutes,bool enabled,const QString &formatHint={},const QString &importScope={});
    Q_INVOKABLE bool removeSubscription(const QString &id);
    Q_INVOKABLE void refreshSubscription(const QString &id);
    Q_INVOKABLE bool cancelRefresh(const QString &id);
    Q_INVOKABLE void refreshAll();
    void shutdown();
    using ApplyConfiguration = std::function<bool(const NodeImporter::Result &,const QString &,bool,QString *)>;
    void setConfigurationApplier(ApplyConfiguration apply) { m_apply=std::move(apply); }
    using ApplyCompletion = std::function<void(bool,const QString &)>;
    using ApplyConfigurationAsync = std::function<bool(const NodeImporter::Result &,const QString &,bool,ApplyCompletion,QString *)>;
    void setAsyncConfigurationApplier(ApplyConfigurationAsync apply) { m_applyAsync=std::move(apply); }
    void setDownloadProxy(int port);
    void rememberOwnedProxyPort(int port);
signals:
    void changed();
    void nodesApplied();
private:
    void checkDue();
    void next();
    void download(const QUrl &url,int redirects=0);
    void startDownload(const QUrl &url,int redirects,const QList<QNetworkProxy> &proxies);
    void parseText(const QString &text,const QString &origin,bool nodesOnly);
    void startFile(const QUrl &file,bool nodesOnly);
    void startUrl(const QUrl &url,bool nodesOnly);
    void parse(QByteArray bytes);
    void parsed(NodeImporter::Result result);
    void apply(NodeImporter::Result result);
    void applied(const QString &format,qsizetype count,int incomplete);
    void finish(const QString &error={});
    NodeStore *m_store;
    ApplyConfiguration m_apply;
    ApplyConfigurationAsync m_applyAsync;
    QNetworkAccessManager m_network;
    QPointer<QNetworkReply> m_reply;
    QTimer m_timer,m_deadline;
    QQueue<QString> m_queue;
    QHash<QString,QString> m_errors;
    QSet<QString> m_cancelled;
    QHash<QString,qint64> m_attempts;
    std::function<qint64()> m_clock;
    SystemProxyResolver m_systemProxyResolver;
    QString m_message,m_source,m_formatHint="auto";
    QString m_importSource;
    std::optional<NodeImporter::Result> m_pending;
    bool m_previewRequested=false;
    bool m_nodesOnly=false;
    quint64 m_generation=0;
    bool m_busy=false,m_shuttingDown=false;
    bool m_downloadTimedOut=false;
    bool m_committing=false;
    int m_proxyPort=0;
    QSet<quint16> m_ownedProxyPorts;
};
