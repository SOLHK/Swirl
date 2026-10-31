#include "LanProxySession.h"
#include <QFutureWatcher>
#include <QPromise>
#include <QRegularExpression>
#include <QThreadPool>
#include <QUuid>
#ifdef Q_OS_WIN
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <winsock2.h>
#include <windows.h>
#include <iphlpapi.h>
#endif

namespace {
class NativeLanBackend final : public LanProxySession::Backend {
public:
    LanFirewall::Result prepare(const QString &path,const QJsonObject &config) override {return LanFirewall::prepare(path,config);}
    LanFirewall::Result verify(const QJsonObject &record) override {return LanFirewall::verify(record);}
    LanFirewall::Result recover(const QString &path,const QString &session,bool dead) override {return LanFirewall::recover(path,session,dead);}
    bool journalExists(const QString &path) const override {return LanFirewall::journalExists(path);}
};
}

LanProxySession::LanProxySession(ProxyEngine *engine, QString journal, QObject *parent, std::shared_ptr<Backend> backend)
    : QObject(parent), m_engine(engine), m_backend(backend?std::move(backend):std::make_shared<NativeLanBackend>()), m_journal(journal.isEmpty() ? LanFirewall::journalPath() : std::move(journal)) {
#ifdef Q_OS_WIN
    m_nativeMonitoring = dynamic_cast<NativeLanBackend *>(m_backend.get()) != nullptr;
    if (m_nativeMonitoring) {
        HANDLE notification = nullptr;
        const auto code = NotifyUnicastIpAddressChange(AF_UNSPEC,
            [](PVOID context, PMIB_UNICASTIPADDRESS_ROW, MIB_NOTIFICATION_TYPE) {
                auto *session = static_cast<LanProxySession *>(context);
                QMetaObject::invokeMethod(session, [session] {
                    if (session->m_phase == Phase::Idle || session->m_phase == Phase::Cleaning) return;
                    session->m_error = QStringLiteral("本机接口地址发生变化，已请求关闭 LAN 监听；请确认接口后重新开启。");
                    session->stop();
                }, Qt::QueuedConnection);
            }, this, FALSE, &notification);
        if (code == NO_ERROR) m_networkNotification = notification;
    }
#endif
    connect(engine, &ProxyEngine::lanCommandFinished, this, &LanProxySession::commandFinished);
    connect(engine, &ProxyEngine::statusChanged, this, &LanProxySession::statusChanged);
    m_startDeadline.setSingleShot(true);
    connect(&m_startDeadline, &QTimer::timeout, this, [this] {
        if (m_phase != Phase::WaitingCore) return;
        m_configuration = {}; m_phase = Phase::Idle;
        m_error = QStringLiteral("Rust Core 未在时限内就绪，LAN 监听未启动。"); emit changed();
    });
    m_commandDeadline.setParent(this);
    m_commandDeadline.setSingleShot(true);
    m_commandDeadline.setObjectName(QStringLiteral("lanCommandDeadline"));
    connect(&m_commandDeadline, &QTimer::timeout, this, [this] {
        if (m_phase == Phase::Starting) {
            m_error = QStringLiteral("LAN 启动回执超时，已请求停止；监听状态仍需 Rust 确认。");
            m_stopRequested = true; m_phase = Phase::Stopping;
            sendCommand("lan_stop"); emit changed();
        } else if (m_phase == Phase::Stopping) {
            m_error = QStringLiteral("LAN 停止回执超时，已撤销自有防火墙放行；监听关闭尚未确认。");
            m_request.clear(); cleanup();
        }
    });
    m_verify.setInterval(5000);
    connect(&m_verify, &QTimer::timeout, this, [this] {
        if (m_phase != Phase::Running || m_verifying || m_record.isEmpty()) return;
        m_verifying = true;
        const auto record = m_record;
        work([record,backend=m_backend] { return backend->verify(record); }, [this, record](const auto &result) {
            m_verifying = false;
            if (m_record.value("session") != record.value("session") || m_phase != Phase::Running) return;
            if (!result.ok) { m_error = result.error; stop(); }
        });
    });
}

LanProxySession::~LanProxySession() {
#ifdef Q_OS_WIN
    // Cancel waits for outstanding native callbacks before this QObject dies.
    if (m_networkNotification) CancelMibChangeNotify2(m_networkNotification);
#endif
    m_destroyed->store(true);
    m_verify.stop(); m_startDeadline.stop(); m_commandDeadline.stop();
    // Destruction never terminates a network worker. The independent guard
    // owns crash cleanup; an in-flight preparation rolls back in its worker.
    if (!m_record.isEmpty()) {
        const auto path = m_journal, session = m_record.value("session").toString();
        QThreadPool::globalInstance()->start([path, session,backend=m_backend] { backend->recover(path, session, false); });
    }
}

QString LanProxySession::phase() const {
    switch (m_phase) {
    case Phase::Idle: return "idle";
    case Phase::WaitingCore: return "waiting_core";
    case Phase::Preparing: return "preparing_firewall";
    case Phase::Starting: return "starting_listener";
    case Phase::Running: return "running";
    case Phase::Stopping: return "stopping_listener";
    case Phase::Cleaning: return "restoring_firewall";
    }
    return "idle";
}

void LanProxySession::work(std::function<LanFirewall::Result()> operation,
                           std::function<void(const LanFirewall::Result &)> completion) {
    auto promise = std::make_shared<QPromise<LanFirewall::Result>>();
    auto *watcher = new QFutureWatcher<LanFirewall::Result>(this);
    connect(watcher, &QFutureWatcher<LanFirewall::Result>::finished, this, [watcher, completion] {
        const auto result = watcher->result(); watcher->deleteLater(); completion(result);
    });
    watcher->setFuture(promise->future());
    const auto destroyed = m_destroyed;
    const auto path = m_journal;const auto backend=m_backend;
    QThreadPool::globalInstance()->start([promise, operation = std::move(operation), destroyed, path,backend] {
        promise->start(); const auto result = operation();
        if (destroyed->load() && !result.record.isEmpty())
            backend->recover(path, result.record.value("session").toString(), false);
        promise->addResult(result); promise->finish();
    });
}

bool LanProxySession::start(const QJsonObject &configuration) {
    if (m_nativeMonitoring && !m_networkNotification) {
        m_error = QStringLiteral("无法监控本机地址变化，未开放 LAN 监听。"); emit changed(); return false;
    }
    if (busy() || m_engine->status().allowLan) { m_error = QStringLiteral("请先停止当前局域网代理再修改监听配置。"); emit changed(); return false; }
    if (recoveryNeeded()) { m_error = QStringLiteral("请先恢复上次 LAN 防火墙记录，再开启局域网代理。"); emit changed(); return false; }
    if (!LanFirewall::validateConfiguration(configuration, &m_configuration, &m_error)) { emit changed(); return false; }
    m_error.clear(); m_stopRequested = false;
    const auto state = m_engine->status();
    if (state.processAlive && state.apiHealthy) beginPreparation();
    else { m_phase = Phase::WaitingCore; m_startDeadline.start(15000); emit changed(); }
    return true;
}

void LanProxySession::beginPreparation() {
    m_startDeadline.stop(); m_phase = Phase::Preparing;
    const auto config = m_configuration; const auto path = m_journal;
    work([path, config,backend=m_backend] { return backend->prepare(path, config); }, [this](const auto &result) {
        m_record = result.record;
        if (!result.ok) { m_configuration = {}; m_phase = Phase::Idle; m_error = result.error; emit changed(); return; }
        if (m_stopRequested || !m_engine->status().apiHealthy) { m_configuration = {}; cleanup(); return; }
        m_phase = Phase::Starting;
        sendCommand("lan_start", result.config);
        m_configuration = {};
        emit changed();
    });
    emit changed();
}

void LanProxySession::sendCommand(const QString &op, const QJsonObject &config) {
    m_request = QUuid::createUuid().toString(QUuid::WithoutBraces);
    QJsonObject command{{"op", op}, {"request_id", m_request}};
    if (op == "lan_start") command.insert("config", config);
    m_commandDeadline.start(10000);
    m_engine->lanCommand(command);
}

void LanProxySession::commandFinished(const QString &request, const QJsonObject &response) {
    if (request != m_request) return;
    m_commandDeadline.stop();
    m_request.clear();
    if (m_phase == Phase::Starting) {
        if (!response.value("ok").toBool() || !response.value("lan").toObject().value("running").toBool()) {
            const auto returnedCode = response.value("code").toString();
            const auto code=QRegularExpression("^[A-Za-z][A-Za-z0-9_]{0,63}$").match(returnedCode).hasMatch()?returnedCode:QStringLiteral("LanStartUnconfirmed");
            m_error = QStringLiteral("Rust 未确认 LAN 监听启动（%1），已请求恢复防火墙。").arg(code); cleanup(); return;
        }
        if (m_stopRequested) { m_phase = Phase::Stopping; sendCommand("lan_stop"); return; }
        m_phase = Phase::Running; m_verify.start(); emit changed(); return;
    }
    if (m_phase == Phase::Stopping) {
        if (!response.value("ok").toBool() || response.value("lan").toObject().value("running").toBool())
            m_error = QStringLiteral("Rust 未确认 LAN 监听已停止，已撤销自有防火墙放行；请检查内核状态。");
        cleanup();
    }
}

bool LanProxySession::stop() {
    m_stopRequested = true; m_verify.stop(); m_startDeadline.stop();
    if (m_phase == Phase::WaitingCore) { m_configuration = {}; m_phase = Phase::Idle; emit changed(); return true; }
    if (m_phase == Phase::Preparing || m_phase == Phase::Starting) { emit changed(); return true; }
    if (m_phase == Phase::Stopping || m_phase == Phase::Cleaning) return true;
    if (m_engine->status().allowLan) { m_phase = Phase::Stopping; sendCommand("lan_stop"); emit changed(); }
    else if (!m_record.isEmpty()) cleanup();
    else emit changed();
    return true;
}

void LanProxySession::cleanup(bool deadOwner) {
    if (m_phase == Phase::Cleaning) return;
    m_phase = Phase::Cleaning; m_verify.stop(); m_startDeadline.stop(); m_commandDeadline.stop();
    const auto path = m_journal, session = deadOwner ? QString() : m_record.value("session").toString();
    work([path, session, deadOwner,backend=m_backend] { return backend->recover(path, session, deadOwner); }, [this](const auto &result) {
        if (!result.ok) m_error = m_error.isEmpty() ? result.error : m_error + ' ' + result.error;
        else m_record = {};
        m_phase = Phase::Idle; emit changed();
    });
    emit changed();
}

bool LanProxySession::recover() {
    if (busy() || m_engine->status().allowLan) { m_error = QStringLiteral("请先停止局域网代理再恢复防火墙。"); emit changed(); return false; }
    m_error.clear(); cleanup(m_record.isEmpty()); return true;
}

void LanProxySession::statusChanged() {
    const auto state = m_engine->status();
    // The threaded wrapper intentionally discards replies from an older main
    // runtime epoch. A concurrent main-runtime stop may therefore suppress the
    // LAN start reply; its actual stopped status must still unwind our rules.
    if (state.state == ProxyEngine::State::Stopped && !state.processAlive) {
        if (m_phase == Phase::Preparing) { m_stopRequested = true; return; }
        if (m_phase == Phase::Starting || m_phase == Phase::Stopping) {
            m_request.clear(); m_configuration = {}; cleanup(); return;
        }
    }
    if (m_phase == Phase::WaitingCore) {
        if (state.processAlive && state.apiHealthy) beginPreparation();
        else if (state.state == ProxyEngine::State::Failed) { m_startDeadline.stop(); m_configuration = {}; m_phase = Phase::Idle; m_error = QStringLiteral("Rust Core 启动失败，LAN 监听未启动。"); emit changed(); }
    } else if (m_phase == Phase::Running) {
        if (!state.processAlive || !state.allowLan) { m_error = QStringLiteral("LAN 数据平面已停止，正在恢复自有防火墙规则。"); cleanup(); }
        else if (!state.apiHealthy || !state.lan.value("health_error").toString().isEmpty()) { m_error = QStringLiteral("LAN 状态不可确认，已请求停止监听。"); stop(); }
    }
}
