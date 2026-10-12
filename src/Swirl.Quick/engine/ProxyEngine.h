#pragma once
#include <QObject>
#include <QString>

// Swirl-owned contract. No Mihomo JSON or transport objects cross this boundary.
struct EngineStartOptions {
    QString executablePath;
    QByteArray expectedSha256;
    QString expectedVersion;
    quint16 controlPort = 9097;
    int startupTimeoutMs = 10000;
    int requestTimeoutMs = 1000;
    int healthIntervalMs = 2000;
};

class ProxyEngine : public QObject {
    Q_OBJECT
public:
    enum class State { Stopped, Validating, Starting, Running, Degraded, Stopping, Failed };
    Q_ENUM(State)
    enum class Error { None, InvalidOptions, MissingExecutable, IntegrityMismatch,
        ConfigurationFailed, PortConflict, ProcessStartFailed, StartupTimeout,
        UnexpectedExit, ApiUnavailable, AuthenticationFailed, InvalidResponse,
        OwnershipFailed };
    Q_ENUM(Error)
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
    };
    using QObject::QObject;
    virtual ~ProxyEngine() = default;
    virtual void start(const EngineStartOptions &options) = 0;
    virtual void stop() = 0;
    virtual void refresh() = 0;
    virtual Status status() const = 0;
    virtual QString configurationSummary() const = 0;
signals:
    void statusChanged();
};
