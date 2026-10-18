#pragma once
#include "NodeStore.h"
#include "NodeImporter.h"
#include <QNetworkAccessManager>
#include <QPointer>
#include <QTimer>
#include <QQueue>
#include <functional>

class QNetworkReply;
class NodeImportService final : public QObject {
    Q_OBJECT
    Q_PROPERTY(QVariantList providers READ providers NOTIFY changed)
    Q_PROPERTY(bool busy READ busy NOTIFY changed)
    Q_PROPERTY(QString message READ message NOTIFY changed)
public:
    explicit NodeImportService(NodeStore *store,QObject *parent=nullptr,
        std::function<qint64()> clock={}, int pollIntervalMs=60000);
    QVariantList providers() const;
    bool busy() const { return m_busy; }
    QString message() const { return m_message; }
    Q_INVOKABLE void importText(const QString &text);
    Q_INVOKABLE void importClipboard();
    Q_INVOKABLE void importFile(const QUrl &file);
    Q_INVOKABLE void importUrl(const QUrl &url);
    Q_INVOKABLE bool saveSubscription(const QString &id,const QString &name,const QUrl &url,int intervalMinutes,bool enabled,const QString &formatHint={});
    Q_INVOKABLE bool removeSubscription(const QString &id);
    Q_INVOKABLE void refreshSubscription(const QString &id);
    Q_INVOKABLE void refreshAll();
    void shutdown();
    using ApplyConfiguration = std::function<bool(const NodeImporter::Result &,const QString &,QString *)>;
    void setConfigurationApplier(ApplyConfiguration apply) { m_apply=std::move(apply); }
    void setDownloadProxy(int port) { m_proxyPort=port; }
signals:
    void changed();
    void nodesApplied();
private:
    void checkDue();
    void next();
    void download(const QUrl &url,int redirects=0);
    void parse(QByteArray bytes);
    void finish(const QString &error={});
    NodeStore *m_store;
    ApplyConfiguration m_apply;
    QNetworkAccessManager m_network;
    QPointer<QNetworkReply> m_reply;
    QTimer m_timer,m_deadline;
    QQueue<QString> m_queue;
    QHash<QString,QString> m_errors;
    QHash<QString,qint64> m_attempts;
    std::function<qint64()> m_clock;
    QString m_message,m_source,m_formatHint="auto";
    bool m_busy=false,m_shuttingDown=false;
    int m_proxyPort=0;
};
