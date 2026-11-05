#pragma once

#include "LanFirewall.h"
#include "../engine/ProxyEngine.h"
#include <QObject>
#include <QTimer>
#include <atomic>
#include <functional>
#include <memory>

// Coordinates a single optional LAN ingress on the existing Rust runtime.
// Starting/stopping it never changes WinINET, TUN, DNS, nodes or route policy.
class LanProxySession final : public QObject {
    Q_OBJECT
public:
    class Backend {
    public:
        virtual ~Backend() = default;
        virtual LanFirewall::Result prepare(const QString &, const QJsonObject &) = 0;
        virtual LanFirewall::Result verify(const QJsonObject &) = 0;
        virtual LanFirewall::Result recover(const QString &, const QString &, bool) = 0;
        virtual bool journalExists(const QString &) const = 0;
    };
    // Constructor-only injection is for isolated lifecycle/fault tests. The
    // product controller always uses the native Windows backend.
    explicit LanProxySession(ProxyEngine *engine, QString journal = {}, QObject *parent = nullptr,
                             std::shared_ptr<Backend> backend = {});
    ~LanProxySession() override;
    bool start(const QJsonObject &configuration);
    bool stop();
    bool recover();
    bool busy() const { return m_phase != Phase::Idle && m_phase != Phase::Running; }
    QString error() const { return m_error; }
    bool recoveryNeeded() const { return m_backend->journalExists(m_journal); }
    QString phase() const;
signals:
    void changed();
private:
    enum class Phase { Idle, WaitingCore, Preparing, Starting, Running, Stopping, Cleaning };
    void beginPreparation();
    void cleanup(bool deadOwner = false);
    void sendCommand(const QString &op, const QJsonObject &config = {});
    void commandFinished(const QString &request, const QJsonObject &response);
    void statusChanged();
    void work(std::function<LanFirewall::Result()> operation,
              std::function<void(const LanFirewall::Result &)> completion);
    ProxyEngine *m_engine;
    std::shared_ptr<Backend> m_backend;
    QString m_journal, m_error, m_request;
    QJsonObject m_configuration, m_record;
    Phase m_phase = Phase::Idle;
    bool m_stopRequested = false, m_verifying = false;
    bool m_nativeMonitoring = false;
    void *m_networkNotification = nullptr;
    QTimer m_startDeadline, m_commandDeadline, m_verify;
    std::shared_ptr<std::atomic_bool> m_destroyed = std::make_shared<std::atomic_bool>(false);
};
