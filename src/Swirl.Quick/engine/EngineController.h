#pragma once
#include "ProxyEngine.h"
#include "NodeStore.h"
#include <memory>

// QML sees only Swirl's generic business facade. Engine implementations are injected in C++.
class EngineController final : public QObject {
    Q_OBJECT
    Q_PROPERTY(QString executablePath READ executablePath WRITE setExecutablePath NOTIFY optionsChanged)
    Q_PROPERTY(int controlPort READ controlPort WRITE setControlPort NOTIFY optionsChanged)
    Q_PROPERTY(QString expectedVersion READ expectedVersion CONSTANT)
    Q_PROPERTY(QString expectedSha256 READ expectedSha256 CONSTANT)
    Q_PROPERTY(QString stateText READ stateText NOTIFY statusChanged)
    Q_PROPERTY(QString error READ error NOTIFY statusChanged)
    Q_PROPERTY(QString errorCode READ errorCode NOTIFY statusChanged)
    Q_PROPERTY(bool processAlive READ processAlive NOTIFY statusChanged)
    Q_PROPERTY(bool apiHealthy READ apiHealthy NOTIFY statusChanged)
    Q_PROPERTY(bool busy READ busy NOTIFY statusChanged)
    Q_PROPERTY(bool canStart READ canStart NOTIFY statusChanged)
    Q_PROPERTY(QString version READ version NOTIFY statusChanged)
    Q_PROPERTY(QString processId READ processId NOTIFY statusChanged)
    Q_PROPERTY(qint64 uptimeSeconds READ uptimeSeconds NOTIFY statusChanged)
    Q_PROPERTY(QString configPath READ configPath NOTIFY statusChanged)
    Q_PROPERTY(QString configurationSummary READ configurationSummary NOTIFY statusChanged)
    Q_PROPERTY(QString controlEndpoint READ controlEndpoint NOTIFY statusChanged)
    Q_PROPERTY(QVariantList nodes READ nodes NOTIFY nodesChanged)
    Q_PROPERTY(QString selectedNodeId READ selectedNodeId NOTIFY nodesChanged)
    Q_PROPERTY(QString selectedNodeName READ selectedNodeName NOTIFY nodesChanged)
    Q_PROPERTY(QString activeNodeId READ activeNodeId NOTIFY statusChanged)
    Q_PROPERTY(QString nodeStateText READ nodeStateText NOTIFY statusChanged)
    Q_PROPERTY(QString requestStateText READ requestStateText NOTIFY statusChanged)
    Q_PROPERTY(QString nodeError READ nodeError NOTIFY nodesChanged)
    Q_PROPERTY(bool nodeBusy READ nodeBusy NOTIFY statusChanged)
    Q_PROPERTY(bool requestSucceeded READ requestSucceeded NOTIFY statusChanged)
    Q_PROPERTY(int proxyPort READ proxyPort WRITE setProxyPort NOTIFY optionsChanged)
    Q_PROPERTY(int activeProxyPort READ activeProxyPort NOTIFY statusChanged)
public:
    explicit EngineController(std::unique_ptr<ProxyEngine> engine, QObject *parent = nullptr, QString storePath = {});
    QString executablePath() const { return m_options.executablePath; }
    int controlPort() const { return m_options.controlPort; }
    void setExecutablePath(const QString &path);
    void setControlPort(int port);
    QString expectedVersion() const { return m_options.expectedVersion; }
    QString expectedSha256() const { return QString::fromLatin1(m_options.expectedSha256); }
    QString stateText() const;
    QString error() const { return m_engine->status().message; }
    QString errorCode() const;
    bool processAlive() const { return m_engine->status().processAlive; }
    bool apiHealthy() const { return m_engine->status().apiHealthy; }
    bool busy() const;
    bool canStart() const { return !busy() && !processAlive(); }
    QString version() const { return m_engine->status().version; }
    QString processId() const { return QString::number(m_engine->status().processId); }
    qint64 uptimeSeconds() const { return m_engine->status().uptimeSeconds; }
    QString configPath() const { return m_engine->status().configPath; }
    QString configurationSummary() const { return m_engine->configurationSummary(); }
    QString controlEndpoint() const { return m_engine->status().controlEndpoint; }
    Q_INVOKABLE void start();
    Q_INVOKABLE void stop();
    Q_INVOKABLE void refresh();
    QVariantList nodes() const;
    QString selectedNodeId() const { return m_store.selectedId(); }
    QString selectedNodeName() const;
    QString activeNodeId() const { return m_engine->status().selectedNodeId; }
    QString nodeStateText() const;
    QString requestStateText() const;
    QString nodeError() const { return !m_nodeError.isEmpty()?m_nodeError:m_store.error(); }
    bool nodeBusy() const { return m_engine->status().nodeBusy || busy() || m_restartPending; }
    bool requestSucceeded() const { return m_engine->status().requestState==ProxyEngine::RequestState::Succeeded; }
    int proxyPort() const { return m_options.proxyPort; }
    int activeProxyPort() const { return m_engine->status().proxyPort; }
    void setProxyPort(int port);
    Q_INVOKABLE bool saveNode(const QVariantMap &input);
    Q_INVOKABLE bool deleteNode(const QString &id);
    Q_INVOKABLE bool chooseNode(const QString &id);
    Q_INVOKABLE void connectNode(const QString &id);
    Q_INVOKABLE void testNode(const QUrl &url);
    Q_INVOKABLE void disconnectNode();
signals:
    void statusChanged();
    void optionsChanged();
    void nodesChanged();
private:
    std::unique_ptr<ProxyEngine> m_engine;
    EngineStartOptions m_options;
    NodeStore m_store;
    QString m_nodeError;
    bool m_restartPending=false;
};
