#pragma once
#include <QObject>
#include <QTcpServer>
#include <QNetworkAccessManager>
#include <QVariantList>
#include <QUrl>
#include <QSet>
#include <QTimer>
#include <QSslSocket>
#include "TlsCertificateService.h"

class CaptureListener final : public QTcpServer {
protected:
    void incomingConnection(qintptr descriptor) override {
        auto *socket=new QSslSocket(this);
        if(socket->setSocketDescriptor(descriptor))addPendingConnection(socket);else socket->deleteLater();
    }
};
#include <memory>

class QTcpSocket;
class QNetworkReply;

// Opt-in loopback HTTP proxy, with opaque CONNECT or explicitly scoped TLS
// interception. EngineController owns system-proxy integration; CA trust
// installation remains an explicit TlsCertificateService action.
class CaptureService final : public QObject
{
    Q_OBJECT
    Q_PROPERTY(bool autoMitmEnabled READ autoMitmEnabled WRITE setAutoMitmEnabled NOTIFY stateChanged)
    Q_PROPERTY(bool running READ running NOTIFY stateChanged)
    Q_PROPERTY(int port READ port NOTIFY stateChanged)
    Q_PROPERTY(int activeCount READ activeCount NOTIFY stateChanged)
    Q_PROPERTY(QString error READ error NOTIFY stateChanged)
    Q_PROPERTY(QVariantList sessions READ sessions NOTIFY sessionsChanged)
    Q_PROPERTY(TlsCertificateService* tls READ tls CONSTANT)
    Q_PROPERTY(int upstreamProxyPort READ upstreamProxyPort WRITE setUpstreamProxyPort NOTIFY stateChanged)
    Q_PROPERTY(bool rewriteEnabled READ rewriteEnabled WRITE setRewriteEnabled NOTIFY rulesChanged)
    Q_PROPERTY(QVariantList rewriteRules READ rewriteRules NOTIFY rulesChanged)
    Q_PROPERTY(QString filter READ filter WRITE setFilter NOTIFY stateChanged)
    Q_PROPERTY(QVariantMap forwardingPorts READ forwardingPorts NOTIFY rulesChanged)
public:
    explicit CaptureService(QObject *parent=nullptr,QString tlsPath={});
    ~CaptureService() override;
    bool autoMitmEnabled() const { return m_autoMitmEnabled; }
    void setAutoMitmEnabled(bool enabled);
    bool running() const { return m_server.isListening(); }
    int port() const { return m_server.serverPort(); }
    int activeCount() const { return m_activeCount; }
    QString error() const { return m_error; }
    QVariantList sessions() const { return m_sessions; }
    TlsCertificateService *tls() { return &m_tls; }
    int upstreamProxyPort() const { return m_upstreamProxyPort; }
    void setUpstreamProxyPort(int port);
    bool rewriteEnabled() const { return m_rewriteEnabled; }
    QVariantList rewriteRules() const { return m_rules; }
    QString filter() const { return m_filter; }
    QVariantMap forwardingPorts() const { return m_forwardPorts; }
    void setFilter(const QString &filter);
    void setRewriteEnabled(bool enabled);
    Q_INVOKABLE bool saveRewriteRule(const QVariantMap &rule);
    Q_INVOKABLE bool removeRewriteRule(const QString &id);
    Q_INVOKABLE void setLimits(int minutes,int megabytes,int requests);
    Q_INVOKABLE bool start(int requestedPort=8899);
    Q_INVOKABLE void stop();
    Q_INVOKABLE void clear();
    Q_INVOKABLE bool exportHar(const QUrl &file);
signals:
    void rulesChanged();
    void stateChanged();
    void sessionsChanged();
private:
    struct Connection;
    void acceptClients();
    void consume(const std::shared_ptr<Connection> &c);
    void handle(const std::shared_ptr<Connection> &c);
    void fail(const std::shared_ptr<Connection> &c,int status,const QByteArray &message);
    bool beginResponseStream(const std::shared_ptr<Connection> &c,QNetworkReply *reply);
    void pumpResponseStream(const std::shared_ptr<Connection> &c,QNetworkReply *reply);
    void finishHttp(const std::shared_ptr<Connection> &c,QNetworkReply *reply);
    void update(const std::shared_ptr<Connection> &c);
    void setError(const QString &message);
    void checkLimits();
    bool persistRules();
    void synchronizeForwarders();
    QList<QTcpServer *> m_forwardServers;
    QVariantMap m_forwardPorts;
    void localResponse(const std::shared_ptr<Connection> &c,int status,const QByteArray &body,const QByteArray &type,const QByteArray &location={});
    bool m_rewriteEnabled=false;
    QVariantList m_rules;
    QString m_filter;
    QTimer m_captureDeadline;
    int m_minutes=0,m_megabytes=0,m_requestLimit=0;
    bool m_limitPending=false,m_autoMitmEnabled=true;
    quint64 m_captureRequests=0;
    qint64 m_captureBytes=0;
    quint64 m_captureFirstId=1;
    TlsCertificateService m_tls;
    int m_upstreamProxyPort=0;
    CaptureListener m_server;
    QNetworkAccessManager m_network;
    QVariantList m_sessions;
    QSet<QNetworkReply *> m_replies;
    quint64 m_nextId=1;
    int m_activeCount=0;
    QString m_error;
};
