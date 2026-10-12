#pragma once
#include "ProxyEngine.h"
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
public:
    explicit EngineController(std::unique_ptr<ProxyEngine> engine, QObject *parent = nullptr);
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
signals:
    void statusChanged();
    void optionsChanged();
private:
    std::unique_ptr<ProxyEngine> m_engine;
    EngineStartOptions m_options;
};
