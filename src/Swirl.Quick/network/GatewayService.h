#pragma once
#include <QObject>
#include <QVariantMap>
#include <QUrl>
#include <QProcess>
#include <QTimer>
#include "DhcpServer.h"
class EngineController;
class GatewayService final : public QObject {
    Q_OBJECT
    Q_PROPERTY(bool running READ running NOTIFY changed)
    Q_PROPERTY(bool busy READ busy NOTIFY changed)
    Q_PROPERTY(bool configured READ configured NOTIFY changed)
    Q_PROPERTY(bool recoveryNeeded READ recoveryNeeded NOTIFY changed)
    Q_PROPERTY(QString error READ error NOTIFY changed)
    Q_PROPERTY(QVariantMap configuration READ configuration NOTIFY changed)
    Q_PROPERTY(QVariantList interfaces READ interfaces NOTIFY changed)
    Q_PROPERTY(QVariantList devices READ devices NOTIFY changed)
public:
    explicit GatewayService(EngineController *engine,QString path={},QObject *parent=nullptr);
    ~GatewayService() override;
    bool running() const {return m_forwarding&&m_dhcp.running();}
    bool busy() const {return m_phase!=Phase::Idle;}
    bool configured() const {return m_configured;}
    bool recoveryNeeded() const;
    QString error() const {return m_error;}
    QVariantMap configuration() const;
    QVariantList interfaces() const;
    QVariantList devices() const;
    Q_INVOKABLE bool configure(const QVariantMap &configuration);
    Q_INVOKABLE bool start();
    Q_INVOKABLE void stop();
    Q_INVOKABLE bool recover();
    Q_INVOKABLE bool exportClients(const QUrl &destination);
    Q_INVOKABLE bool importClients(const QUrl &source);
signals:
    void changed();
private:
    enum class Phase {Idle,WaitingTun,Starting,Stopping};
    void startForwarding();
    void runCleanup();
    void processFinished(int exitCode);
    bool saveConfiguration();
    void loadConfiguration();
    EngineController *m_engine=nullptr;
    QString m_path,m_journal,m_error;
    DhcpServer m_dhcp;
    DhcpServer::Config m_config;
    QProcess m_process;
    QTimer m_deadline;
    Phase m_phase=Phase::Idle;
    bool m_configured=false,m_forwarding=false,m_stopping=false;
};
