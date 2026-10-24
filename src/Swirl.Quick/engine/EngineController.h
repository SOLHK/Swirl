#pragma once
#include <QNetworkInterface>
#include <QPair>
#include "ProxyEngine.h"
#include "NodeStore.h"
#include "NodeImportService.h"
#include "SystemProxySession.h"
#include "TelemetryService.h"
#include "NodeTestService.h"
#include "ConnectionDiagnostics.h"
#include <memory>

// QML sees only Swirl's generic business facade. Engine implementations are injected in C++.
class EngineController final : public QObject {
    Q_OBJECT
    Q_PROPERTY(bool rustCoreBuild READ rustCoreBuild CONSTANT)
    Q_PROPERTY(QString stateText READ stateText NOTIFY statusChanged)
    Q_PROPERTY(QString error READ error NOTIFY statusChanged)
    Q_PROPERTY(QString errorCode READ errorCode NOTIFY statusChanged)
    Q_PROPERTY(bool processAlive READ processAlive NOTIFY statusChanged)
    Q_PROPERTY(bool apiHealthy READ apiHealthy NOTIFY statusChanged)
    Q_PROPERTY(bool busy READ busy NOTIFY statusChanged)
    Q_PROPERTY(bool canStart READ canStart NOTIFY statusChanged)
    Q_PROPERTY(QString version READ version NOTIFY statusChanged)
    Q_PROPERTY(QString engineName READ engineName NOTIFY statusChanged)
    Q_PROPERTY(QString engineKind READ engineKind NOTIFY statusChanged)
    Q_PROPERTY(QString engineIdentityLabel READ engineIdentityLabel NOTIFY statusChanged)
    Q_PROPERTY(QString engineReason READ engineReason NOTIFY statusChanged)
    Q_PROPERTY(QString processId READ processId NOTIFY statusChanged)
    Q_PROPERTY(qint64 uptimeSeconds READ uptimeSeconds NOTIFY statusChanged)
    Q_PROPERTY(QString configPath READ configPath NOTIFY statusChanged)
    Q_PROPERTY(QString configurationSummary READ configurationSummary NOTIFY statusChanged)
    Q_PROPERTY(QString controlEndpoint READ controlEndpoint NOTIFY statusChanged)
    Q_PROPERTY(QVariantList nodes READ nodes NOTIFY nodesChanged)
    Q_PROPERTY(QVariantList nodeCatalog READ nodeCatalog NOTIFY nodeCatalogChanged)
    Q_PROPERTY(QString selectedNodeId READ selectedNodeId NOTIFY selectionChanged)
    Q_PROPERTY(QString selectedNodeName READ selectedNodeName NOTIFY selectionChanged)
    Q_PROPERTY(bool connected READ connected NOTIFY statusChanged)
    Q_PROPERTY(QString activeNodeId READ activeNodeId NOTIFY statusChanged)
    Q_PROPERTY(QString nodeStateText READ nodeStateText NOTIFY statusChanged)
    Q_PROPERTY(QString requestStateText READ requestStateText NOTIFY statusChanged)
    Q_PROPERTY(QString nodeError READ nodeError NOTIFY selectionChanged)
    Q_PROPERTY(bool nodeBusy READ nodeBusy NOTIFY statusChanged)
    Q_PROPERTY(bool requestSucceeded READ requestSucceeded NOTIFY statusChanged)
    Q_PROPERTY(int proxyPort READ proxyPort WRITE setProxyPort NOTIFY optionsChanged)
    Q_PROPERTY(int activeProxyPort READ activeProxyPort NOTIFY statusChanged)
    Q_PROPERTY(NodeImportService* imports READ imports CONSTANT)
    Q_PROPERTY(QStringList supportedProtocols READ supportedProtocols CONSTANT)
    Q_PROPERTY(SystemProxySession* systemProxy READ systemProxy CONSTANT)
    Q_PROPERTY(bool systemProxyBusy READ systemProxyBusy NOTIFY statusChanged)
    Q_PROPERTY(QString routingMode READ routingMode NOTIFY statusChanged)
    Q_PROPERTY(QString routingError READ routingError NOTIFY statusChanged)
    Q_PROPERTY(bool routingBusy READ routingBusy NOTIFY statusChanged)
    Q_PROPERTY(QVariantList connections READ connections NOTIFY statusChanged)
    Q_PROPERTY(TelemetryService* telemetry READ telemetry CONSTANT)
    Q_PROPERTY(NodeTestService* tests READ tests CONSTANT)
    Q_PROPERTY(QVariantList routingRules READ routingRules NOTIFY statusChanged)
    Q_PROPERTY(bool meteredEnabled READ meteredEnabled NOTIFY statusChanged)
    Q_PROPERTY(QStringList meteredAllowlist READ meteredAllowlist NOTIFY optionsChanged)
    Q_PROPERTY(bool lanEnabled READ lanEnabled NOTIFY statusChanged)
    Q_PROPERTY(bool lanConfigured READ lanConfigured NOTIFY optionsChanged)
    Q_PROPERTY(QString lanUsername READ lanUsername NOTIFY optionsChanged)
    Q_PROPERTY(QStringList lanAddresses READ lanAddresses NOTIFY lanAddressesChanged)
    Q_PROPERTY(bool tunRequested READ tunRequested NOTIFY statusChanged)
    Q_PROPERTY(bool tunEnabled READ tunEnabled NOTIFY statusChanged)
    Q_PROPERTY(bool elevated READ elevated CONSTANT)
    Q_PROPERTY(QVariantMap dnsConfiguration READ dnsConfiguration NOTIFY optionsChanged)
    Q_PROPERTY(QVariantList policyGroups READ policyGroups NOTIFY optionsChanged)
    Q_PROPERTY(QString networkConfigurationError READ networkConfigurationError NOTIFY optionsChanged)
    Q_PROPERTY(ConnectionDiagnostics* diagnostics READ diagnostics CONSTANT)
    Q_PROPERTY(QString proxyEnvironmentAdvice READ proxyEnvironmentAdvice NOTIFY optionsChanged)
public:
    explicit EngineController(std::unique_ptr<ProxyEngine> engine, QObject *parent = nullptr, QString storePath = {},bool realAcceptance=false);
    bool rustCoreBuild() const {
        return true;
    }
    QString stateText() const;
    QString error() const { return m_engine->status().message; }
    QString errorCode() const;
    bool processAlive() const { return m_engine->status().processAlive; }
    bool apiHealthy() const { return m_engine->status().apiHealthy; }
    bool busy() const;
    bool canStart() const { return !m_shuttingDown && !busy() && !processAlive() && !m_imports.busy(); }
    QString version() const { return m_engine->status().version; }
    QString engineName() const { return m_engine->status().engineName; }
    QString engineKind() const { return m_engine->status().engineKind; }
    QString engineIdentityLabel() const;
    bool prepareRealAcceptance(); // Called only by the isolated runtime harness.
    QString engineReason() const { return m_engine->status().engineReason; }
    QString processId() const { return QString::number(m_engine->status().processId); }
    QPair<qint64,qint64> rustTrafficTotals() const {
        const auto status=m_engine->status();
        return status.engineKind==QStringLiteral("rust")
            ? QPair<qint64,qint64>{status.uploadTotal,status.downloadTotal}
            : QPair<qint64,qint64>{0,0};
    }
    qint64 rustAccepted() const { return m_engine->status().rustAccepted; }
    qint64 rustFailed() const { return m_engine->status().rustFailed; }
    QString rustLastErrorStage() const { return m_engine->status().rustLastErrorStage; }
    qint64 uptimeSeconds() const { return m_engine->status().uptimeSeconds; }
    QString configPath() const { return m_engine->status().configPath; }
    QString configurationSummary() const { return m_engine->configurationSummary(); }
    QString controlEndpoint() const { return m_engine->status().controlEndpoint; }
    Q_INVOKABLE void start();
    Q_INVOKABLE void stop();
    void shutdown();
    Q_INVOKABLE void refresh();
    QVariantList nodes() const;
    QVariantList nodeDiagnosticRows() const;
    QVariantList nodeCatalog() const { return m_store.publicRows(); }
    QString selectedNodeId() const { return m_store.selectedId(); }
    QString selectedNodeName() const;
    bool connected() const { const auto s=m_engine->status();return s.apiHealthy&&s.processAlive&&(!s.selectedNodeId.isEmpty()||s.directSession); }
    QString activeNodeId() const { return m_engine->status().selectedNodeId; }
    QString nodeStateText() const;
    QString requestStateText() const;
    QString nodeError() const { return !m_nodeError.isEmpty()?m_nodeError:m_store.error(); }
    bool nodeBusy() const { return m_engine->status().nodeBusy || busy() || m_restartPending || m_imports.busy() || !m_pendingSelection.isEmpty(); }
    NodeImportService *imports() { return &m_imports; }
    QStringList supportedProtocols() const { return ProxyNode::protocols(); }
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
    SystemProxySession *systemProxy() { return &m_systemProxy; }
    QString routingMode() const { return processAlive()?m_engine->status().mode:m_options.routingMode; }
    QString routingError() const { return m_routingError; }
    bool routingBusy() const { return m_engine->status().routingBusy; }
    QVariantList connections() const { return m_telemetry.connections(); }
    TelemetryService *telemetry() { return &m_telemetry; }
    NodeTestService *tests() { return &m_tests; }
    Q_INVOKABLE void testAllNodes(const QUrl &url);
    Q_INVOKABLE void testSelectedNode(const QString &id,const QUrl &url);
    QVariantList routingRules() const;
    QVariantMap dnsConfiguration() const { return m_options.dnsConfig; }
    QVariantList policyGroups() const { return m_options.customGroups; }
    QString networkConfigurationError() const { return m_networkError; }
    ConnectionDiagnostics *diagnostics() {return &m_diagnostics;}
    QString proxyEnvironmentAdvice() const;
    bool tunRequested() const { return m_options.tunEnabled; }
    Q_INVOKABLE void setCaptureProxyPort(int port);
    bool tunEnabled() const { return m_engine->status().tunEnabled&&apiHealthy()&&processAlive(); }
    bool elevated() const;
    bool meteredEnabled() const { return m_options.meteredNetwork && tunEnabled(); }
    QStringList meteredAllowlist() const { return m_options.meteredAllowlist; }
    Q_INVOKABLE bool setMeteredEnabled(bool enabled);
    Q_INVOKABLE bool configureMeteredAllowlist(const QStringList &processes);
    bool lanEnabled() const { return m_engine->status().allowLan && processAlive() && apiHealthy(); }
    bool lanConfigured() const { return !m_options.lanUsername.isEmpty() && !m_options.lanPassword.isEmpty(); }
    QString lanUsername() const { return m_options.lanUsername; }
    QStringList lanAddresses() const;
    QList<QNetworkInterface> networkInterfaces() const { return m_interfaces; }
    Q_INVOKABLE bool configureLan(const QString &username,const QString &password);
    Q_INVOKABLE bool setLanEnabled(bool enabled);
    bool gatewayForwardingReady() const { return tunEnabled() && m_engine->status().gatewayForwarding; }
    bool setGatewayForwarding(bool enabled);
    Q_INVOKABLE bool setTunEnabled(bool enabled);
    Q_INVOKABLE bool configureDns(const QVariantMap &configuration);
    Q_INVOKABLE QVariantMap networkConfigurationSnapshot() const;
    bool validateNetworkConfiguration(const QVariantMap &configuration,QVariantMap *canonical=nullptr,const QList<ProxyNode> *candidateNodes=nullptr);
    bool importNodesAndConfiguration(const QList<ProxyNode> &nodes,const QString &sourceId,const QVariantMap &configuration,const QJsonObject &original = {},const QString &sourceFormat = QStringLiteral("clash"));
    bool replaceNetworkConfiguration(const QVariantMap &configuration);
    void setModuleOverlayActive(bool active) { m_moduleOverlayActive=active; }
    Q_INVOKABLE bool saveRoutingRule(const QString &type,const QString &pattern,const QString &policy,int index=-1);
    Q_INVOKABLE bool removeRoutingRule(int index);
    Q_INVOKABLE bool savePolicyGroup(const QString &name,const QString &type,const QStringList &members);
    Q_INVOKABLE bool removePolicyGroup(const QString &name);
    Q_INVOKABLE void setRoutingMode(const QString &mode);
    Q_INVOKABLE void setSystemProxy(bool enabled);
    Q_INVOKABLE void toggleSystemProxy();
    bool systemProxyBusy() const { return m_proxyChecking||(m_proxyRequested&&busy()); }
signals:
    void lanAddressesChanged();
    void interfacesChanged();
    void nodeCatalogChanged();
    void selectionChanged();
    void diagnostic(const QString &module,const QString &code,const QString &message);
    void statusChanged();
    void optionsChanged();
    void nodesChanged();
private:
    QString nodeConnectionState(const QString &id) const;
    void refreshLanAddresses();
    QStringList m_lanAddresses;
    QList<QNetworkInterface> m_interfaces;
    bool m_lanScanPending=false;
    bool m_shuttingDown=false;
    bool m_ingestingEngineStatus=false;
    bool m_meteredPending=false,m_meteredOldTun=false;
    QString m_meteredOldMode;
    std::unique_ptr<ProxyEngine> m_engine;
    EngineStartOptions m_options;
    NodeStore m_store;
    NodeImportService m_imports;
    SystemProxySession m_systemProxy;
    TelemetryService m_telemetry;
    NodeTestService m_tests;
    ConnectionDiagnostics m_diagnostics;
    QString m_previousProxyState;
    QVariantList m_previousNodePresentation;
    ProxyEngine::State m_previousEngineState=ProxyEngine::State::Stopped;
    QJsonObject serializedNetworkConfiguration();
    bool saveNetworkConfiguration();
    bool commitRoutingConfiguration(const QStringList &rules,const QVariantList &groups);
    bool networkEditAllowed();
    void startConfiguredSession();
    QString m_networkError;
    QString m_routingError;
    int m_captureProxyPort=0;
    bool m_proxyRequested=false;
    bool m_proxyChecking=false;
    QString m_nodeError;
    QString m_pendingSelection,m_previousSelection;
    void rollbackPendingSelection(const QString &reason);
    bool m_tunBeforeGateway=false;
    bool m_tunBeforeMetered=false;
    QString m_modeBeforeMetered="rule";
    bool m_restartPending=false;
    bool m_connectionRequested=false;
    bool m_moduleOverlayActive=false;
    bool m_nativeDocumentRouting=false;
    bool m_smartRoutingEligible=false;
    void updateRoutingFlags();
};
