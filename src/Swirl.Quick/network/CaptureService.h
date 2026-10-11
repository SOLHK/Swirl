#pragma once
#include <QObject>
#include <QTcpServer>
#include <QNetworkAccessManager>
#include <QVariantList>
#include <QUrl>
#include <QSet>
#include <memory>

class QTcpSocket;
class QNetworkReply;

// An opt-in loopback explicit HTTP proxy. It never changes system proxy
// settings, installs certificates, or claims to decrypt CONNECT payloads.
class CaptureService final : public QObject
{
    Q_OBJECT
    Q_PROPERTY(bool running READ running NOTIFY stateChanged)
    Q_PROPERTY(int port READ port NOTIFY stateChanged)
    Q_PROPERTY(int activeCount READ activeCount NOTIFY stateChanged)
    Q_PROPERTY(QString error READ error NOTIFY stateChanged)
    Q_PROPERTY(QVariantList sessions READ sessions NOTIFY sessionsChanged)
public:
    explicit CaptureService(QObject *parent=nullptr);
    ~CaptureService() override;
    bool running() const { return m_server.isListening(); }
    int port() const { return m_server.serverPort(); }
    int activeCount() const { return m_activeCount; }
    QString error() const { return m_error; }
    QVariantList sessions() const { return m_sessions; }
    Q_INVOKABLE bool start(int requestedPort=8899);
    Q_INVOKABLE void stop();
    Q_INVOKABLE void clear();
    Q_INVOKABLE bool exportHar(const QUrl &file);
signals:
    void stateChanged();
    void sessionsChanged();
private:
    struct Connection;
    void acceptClients();
    void consume(const std::shared_ptr<Connection> &c);
    void handle(const std::shared_ptr<Connection> &c);
    void fail(const std::shared_ptr<Connection> &c,int status,const QByteArray &message);
    void finishHttp(const std::shared_ptr<Connection> &c,QNetworkReply *reply);
    void update(const std::shared_ptr<Connection> &c);
    void setError(const QString &message);
    QTcpServer m_server;
    QNetworkAccessManager m_network;
    QVariantList m_sessions;
    QSet<QNetworkReply *> m_replies;
    quint64 m_nextId=1;
    int m_activeCount=0;
    QString m_error;
};
