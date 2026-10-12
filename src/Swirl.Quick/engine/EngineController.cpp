#include "EngineController.h"
#include <QCoreApplication>
#include <QFile>
#include <QJsonDocument>
#include <QJsonObject>
#include <QMetaEnum>

EngineController::EngineController(std::unique_ptr<ProxyEngine> engine, QObject *parent)
    : QObject(parent), m_engine(std::move(engine)) {
    QFile manifest(QStringLiteral(":/engine/mihomo-manifest.json"));
    if (manifest.open(QIODevice::ReadOnly)) {
        const auto object = QJsonDocument::fromJson(manifest.readAll()).object();
        m_options.expectedSha256 = object.value(QStringLiteral("executableSha256")).toString().toLatin1();
        m_options.expectedVersion = object.value(QStringLiteral("version")).toString();
    }
    m_options.executablePath = QCoreApplication::applicationDirPath() + QStringLiteral("/core/mihomo.exe");
    connect(m_engine.get(), &ProxyEngine::statusChanged, this, &EngineController::statusChanged);
    connect(QCoreApplication::instance(), &QCoreApplication::aboutToQuit, m_engine.get(), &ProxyEngine::stop);
}
void EngineController::setExecutablePath(const QString &path) {
    if (!canStart() || m_options.executablePath == path) return;
    m_options.executablePath = path; emit optionsChanged();
}
void EngineController::setControlPort(int port) {
    if (!canStart() || port < 1 || port > 65535 || m_options.controlPort == port) return;
    m_options.controlPort = quint16(port); emit optionsChanged();
}
QString EngineController::stateText() const {
    switch (m_engine->status().state) {
    case ProxyEngine::State::Stopped: return QStringLiteral("已停止");
    case ProxyEngine::State::Validating: return QStringLiteral("正在校验");
    case ProxyEngine::State::Starting: return QStringLiteral("正在启动 · 等待认证 API");
    case ProxyEngine::State::Running: return QStringLiteral("进程运行 · 控制接口健康");
    case ProxyEngine::State::Degraded: return QStringLiteral("进程运行 · 控制接口异常");
    case ProxyEngine::State::Stopping: return QStringLiteral("正在停止");
    case ProxyEngine::State::Failed: return QStringLiteral("引擎异常");
    }
    return {};
}
QString EngineController::errorCode() const {
    return QString::fromLatin1(QMetaEnum::fromType<ProxyEngine::Error>().valueToKey(int(m_engine->status().error)));
}
bool EngineController::busy() const {
    const auto state = m_engine->status().state;
    return state == ProxyEngine::State::Validating || state == ProxyEngine::State::Starting || state == ProxyEngine::State::Stopping;
}
void EngineController::start() { if (canStart()) m_engine->start(m_options); }
void EngineController::stop() { m_engine->stop(); }
void EngineController::refresh() { m_engine->refresh(); }
