#pragma once
#include <QObject>
#include <QString>
#include <QUrl>
#include <QVariantList>
#include <QJsonObject>
#include "ProxyNode.h"
#ifdef SWIRL_PRIVATE_UI_QUOTA
#include <memory>
class PrivateUiQuotaSession;
// An immutable trust attachment issued only after the paired private grant and
// owned fixture proof. It is not an imported/persisted DNS configuration field.
class PrivateUiDnsTrust final {
public:
    QString apply(QJsonObject *) const;
    bool snapshot(QJsonObject *) const;
    QString bindingDigest() const;
private:
    friend class PrivateUiQuotaSession;
    PrivateUiDnsTrust(QString endpoint,QByteArray ca,QJsonObject binding,QString source)
        :m_endpoint(std::move(endpoint)),m_ca(std::move(ca)),m_binding(std::move(binding)),m_source(std::move(source)){}
    const QString m_endpoint;
    const QByteArray m_ca;
    const QJsonObject m_binding;
    const QString m_source;
};
#endif

// Swirl-owned UI/control contract; forwarding belongs exclusively to Rust.
struct EngineStartOptions {
    int startupTimeoutMs = 10000;
    int requestTimeoutMs = 1000;
    int healthIntervalMs = 2000;
    QList<ProxyNode> nodes;
    QString selectedNodeId;
    bool directSession = false;
    bool meteredNetwork = false;
    QStringList meteredAllowlist;
    quint16 proxyPort = 7898;
    // Internal node-test capability only, never loaded from user settings or
    // subscriptions. Rust atomically binds loopback port zero for these workers.
    bool internalProbeListener = false;
    // Internal request capability derived from the live TUN owner, never a
    // persisted/imported setting. It changes only isolated probe sockets.
    bool internalProbePhysicalEgress = false;
    // Internal node-test capability: an isolated sweep engine maps every
    // requested node so probe_nodes can dial each one. The live session still
    // maps only its selected route and policy-group members.
    bool probeAllNodes = false;
    QString routingMode = QStringLiteral("rule");
    // Production uses verified, bundled China domain/IP MRS providers. The
    // controlled transport fixtures intentionally retain MATCH-only routing.
    bool smartRouting = false;
    // Manually configured native rules reserve private destinations for DIRECT.
    bool nativePrivateRouting = false;
    QString rulesDirectory;
    bool tunEnabled=false;
    bool gatewayForwarding=false;
    bool allowLan=false;
    QString lanUsername,lanPassword;
    QString lanBindAddress = QStringLiteral("127.0.0.1");
    QVariantMap lanConfiguration;
    bool lanSkipLocalAuthentication = true;
    QVariantMap dnsConfig;
#ifdef SWIRL_PRIVATE_UI_QUOTA
    std::shared_ptr<const PrivateUiDnsTrust> privateUiDnsTrust;
#endif
    QStringList customRules;
    QVariantList customGroups;
    QString inboundUsername,inboundPassword;
    QJsonObject policyDocument;
    QString configurationStoreId,configurationRevision,configurationDigest,configurationRequestId;
};

class ProxyEngine : public QObject {
    Q_OBJECT
public:
    enum class State { Stopped, Validating, Starting, Running, Degraded, Stopping, Failed };
    Q_ENUM(State)
    enum class Error { None, InvalidOptions, MissingExecutable, IntegrityMismatch,
        ConfigurationFailed, PortConflict, ProcessStartFailed, StartupTimeout,
        UnexpectedExit, ApiUnavailable, AuthenticationFailed, InvalidResponse,
        OwnershipFailed, InvalidNode, SelectionFailed, ProxyRequestFailed };
    Q_ENUM(Error)
    enum class NodeHealth { Unknown, Checking, Available, Unavailable };
    enum class RequestState { NotTested, InProgress, Succeeded, Failed };
    struct Status {
        State state = State::Stopped;
        Error error = Error::None;
        QString message;
        bool processAlive = false;
        bool apiHealthy = false;
        qint64 processId = 0;
        qint64 uptimeSeconds = 0;
        QString version;
        QString engineName="Swirl Core Rust",engineKind="rust",sessionId,engineReason;
        QString mode;
        QString configPath;
        QString controlEndpoint;
        QString selectedNodeId;
        NodeHealth nodeHealth = NodeHealth::Unknown;
        RequestState requestState = RequestState::NotTested;
        bool nodeBusy = false;
        int proxyPort = 0;
        int latencyMs = -1;
        int responseCode = 0;
        QString nodeMessage;
        QString probeFailureStage;
        QString probeFailureCode;
        qint64 probeOutboundConnectMs=-1,probeOriginTlsMs=-1;
        quint64 probeRequestTag=0;
        QVariantList connections;
        qint64 connectionsAt = 0;
        qint64 trafficAt = 0;
        qint64 uploadTotal = 0;
        qint64 downloadTotal = 0;
        qint64 rustAccepted = 0;
        qint64 rustFailed = 0;
        QString rustLastErrorStage;
        double uploadRate = 0;
        double downloadRate = 0;
        QString telemetryError;
        bool routingBusy = false;
        bool gatewayForwarding=false;
        bool directSession=false;
        bool tunEnabled=false,allowLan=false;
        // Includes starting, degraded and restoring broker ownership. A false
        // healthy-TUN flag alone cannot prove that capture routes are absent.
        bool tunCapturePossible=false;
        bool tunRecoveryRequired=false;
        QJsonObject lan;
        QJsonObject configurationReceipt;
    };
    using QObject::QObject;
    virtual ~ProxyEngine() = default;
    virtual void start(const EngineStartOptions &options) = 0;
    virtual void stop() = 0;
    virtual void refresh() = 0;
    virtual void selectNode(const QString &id) = 0;
    virtual void probeNode(const QUrl &url) = 0;
    // The UI uses a request tag to distinguish periodic telemetry from a
    // concurrent user-selected URL. Zero identifies an ordinary manual probe.
    virtual void probeNodeTagged(const QUrl &url,quint64 tag) {
        Q_UNUSED(url);
        emit probeRequestRejected(tag,QStringLiteral("probe-unavailable"));
    }
    virtual void setRoutingMode(const QString &mode) { Q_UNUSED(mode); }
    // Concurrent per-node latency sweep. Engines that cannot batch return
    // false and the caller keeps its isolated-engine path.
    virtual bool probeNodes(const QStringList &ids,const QUrl &url,QString *error) {
        Q_UNUSED(ids);Q_UNUSED(url);
        if(error)*error=QStringLiteral("probe-batch-unavailable");
        return false;
    }
    virtual QJsonObject probeNodesStatus() { return {}; }
    virtual void cancelProbeNodes() {}
    virtual void configurationCommand(const QJsonObject &command) {
        emit configurationCommandFinished(command.value("request_id").toString(),QJsonObject{{"ok",false},{"code","UnsupportedCapability"},{"phase","prepare"}});
    }
    virtual void lanCommand(const QJsonObject &command) {
        emit lanCommandFinished(command.value("request_id").toString(), QJsonObject{{"ok",false},{"code","UnsupportedCapability"}});
    }
    virtual Status status() const = 0;
    virtual QString configurationSummary() const = 0;
    virtual QVariantList routingRules() const { return {}; }
    virtual QString probeFailureStage() const { return {}; }
    virtual qint64 probeOutboundConnectMs() const { return -1; }
    virtual qint64 probeOriginTlsMs() const { return -1; }
signals:
    void statusChanged();
    void diagnostic(const QString &module,const QString &code,const QString &message);
    void probeRequestRejected(quint64 tag,const QString &code);
    void lanCommandFinished(const QString &requestId,const QJsonObject &response);
    void configurationCommandFinished(const QString &requestId,const QJsonObject &response);
};
