#pragma once
#include <QObject>
#include <QString>
#include <QUrl>
#include "ProxyNode.h"

// Swirl-owned contract. No Mihomo JSON or transport objects cross this boundary.
struct EngineStartOptions {
    QString executablePath;
    QByteArray expectedSha256;
    QString expectedVersion;
    quint16 controlPort = 9097;
    int startupTimeoutMs = 10000;
    int requestTimeoutMs = 1000;
    int healthIntervalMs = 2000;
    QList<ProxyNode> nodes;
    QString selectedNodeId;
    quint16 proxyPort = 7898;
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
    };
    using QObject::QObject;
    virtual ~ProxyEngine() = default;
    virtual void start(const EngineStartOptions &options) = 0;
    virtual void stop() = 0;
    virtual void refresh() = 0;
    virtual void selectNode(const QString &id) = 0;
    virtual void probeNode(const QUrl &url) = 0;
    virtual Status status() const = 0;
    virtual QString configurationSummary() const = 0;
signals:
    void statusChanged();
};
