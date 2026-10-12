#pragma once
#include "ProxyEngine.h"
#include "OwnedProcess.h"
#include <QElapsedTimer>
#include <QNetworkAccessManager>
#include <QPointer>
#include <QTcpServer>
#include <QTemporaryDir>
#include <QTimer>
#include <QFile>
#include <memory>

class QNetworkReply;
class MihomoAdapter final : public ProxyEngine {
    Q_OBJECT
public:
    explicit MihomoAdapter(QObject *parent = nullptr);
    ~MihomoAdapter() override;
    void start(const EngineStartOptions &options) override;
    void stop() override;
    void refresh() override;
    void selectNode(const QString &id) override;
    void probeNode(const QUrl &url) override;
    void setRoutingMode(const QString &mode) override;
    Status status() const override;
    QString configurationSummary() const override;
    QVariantList routingRules() const override;
private:
    enum class Stage { Version, ValidateConfig, Engine };
    void launch(Stage stage);
    void processFinished(int code, QProcess::ExitStatus exitStatus);
    void publish();
    void fail(Error error, const QString &message);
    void cancelRequest();
    void request(bool version);
    void readConnections();
    void apiFailure(Error error, const QString &message);
    bool prepareConfiguration();
    bool reserveControlPort();
    bool reservePort(QTcpServer &server, quint16 port);
    void cancelNodeRequests();
    void nodeFailure(const QString &message);
    bool lockAndVerifyExecutable();
    void unlockExecutable();
    OwnedProcess m_process;
    QNetworkAccessManager m_network;
    QPointer<QNetworkReply> m_reply;
    QTcpServer m_reservation;
    QTcpServer m_proxyReservation;
    QNetworkAccessManager m_probeNetwork;
    QPointer<QNetworkReply> m_nodeReply, m_probeReply;
    QPointer<QNetworkReply> m_modeReply;
    QPointer<QNetworkReply> m_connectionsReply;
    quint64 m_nodeGeneration = 0;
    QTimer m_poll, m_deadline, m_killTimer;
    QElapsedTimer m_uptime;
    EngineStartOptions m_options;
    Status m_status;
    Stage m_stage = Stage::Version;
    QByteArray m_secret, m_output;
    QString m_generatedConfig;
    std::unique_ptr<QTemporaryDir> m_directory;
    std::unique_ptr<QFile> m_executable;
    void *m_executableHandle = nullptr;
    quint64 m_generation = 0;
    bool m_failureExit = false;
    bool m_selectionPending = false;
};
