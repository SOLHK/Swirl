#pragma once
#include <QObject>
#include <QString>
#include <QUrl>
#include <QVariantList>
#include "ProxyNode.h"

// Swirl-owned contract. No Mihomo JSON or transport objects cross this boundary.
struct EngineStartOptions {
    bool preferCompatibility=false;
    QString executablePath;
    QByteArray expectedSha256;
    QString expectedVersion;
    quint16 controlPort = 9097;
    bool autoControlPort = false;
    int startupTimeoutMs = 10000;
    int requestTimeoutMs = 1000;
    int healthIntervalMs = 2000;
    QList<ProxyNode> nodes;
    QString selectedNodeId;
    bool directSession = false;
    bool meteredNetwork = false;
    QStringList meteredAllowlist;
    quint16 proxyPort = 7898;
    QString routingMode = QStringLiteral("rule");
    // Production uses verified, bundled China domain/IP MRS providers. The
    // controlled transport fixtures intentionally retain MATCH-only routing.
    bool smartRouting = false;
    QString rulesDirectory;
    bool tunEnabled=false;
    bool gatewayForwarding=false;
    bool allowLan=false;
    QString lanUsername,lanPassword;
    QString lanBindAddress = QStringLiteral("*");
    bool lanSkipLocalAuthentication = true;
    QVariantMap dnsConfig;
    QStringList customRules;
    QVariantList customGroups;
    QString inboundUsername,inboundPassword;
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
        QString engineName="Mihomo 兼容",engineKind="compatibility",sessionId,engineReason;
        QString mode;
        QString executablePath;
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
    };
    using QObject::QObject;
    virtual ~ProxyEngine() = default;
    virtual void start(const EngineStartOptions &options) = 0;
    virtual void stop() = 0;
    virtual void refresh() = 0;
    virtual void selectNode(const QString &id) = 0;
    virtual void probeNode(const QUrl &url) = 0;
    virtual void setRoutingMode(const QString &mode) { Q_UNUSED(mode); }
    virtual Status status() const = 0;
    virtual QString configurationSummary() const = 0;
    virtual QVariantList routingRules() const { return {}; }
signals:
    void statusChanged();
    void diagnostic(const QString &module,const QString &code,const QString &message);
};
