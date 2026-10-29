#pragma once
#include <QObject>
#include <QPointer>
#include <QSslSocket>
#include <QTimer>
#include <QUrl>
#include <QVariantList>

// Opt-in diagnostic client. Production forwarding remains in Rust Core: this class
// never sits in front of application tunnels or imposes a session idle timer.
class ConnectionDiagnostics final : public QObject {
    Q_OBJECT
    Q_PROPERTY(bool busy READ busy NOTIFY changed)
    Q_PROPERTY(QString stateText READ stateText NOTIFY changed)
    Q_PROPERTY(QVariantList entries READ entries NOTIFY changed)
    Q_PROPERTY(QString report READ report NOTIFY changed)
public:
    explicit ConnectionDiagnostics(QObject *parent=nullptr);
    bool busy() const {return m_busy;}
    QString stateText() const {return m_state;}
    QVariantList entries() const {return m_entries;}
    QString report() const;
    void setProxyPort(int port){m_port=port;}
    void noteEvent(const QString &category,const QString &message);
    Q_INVOKABLE void run(const QUrl &url);
    Q_INVOKABLE void cancel();
    Q_INVOKABLE void clear();
    Q_INVOKABLE QString saveReport();
signals:
    void changed();
private:
    enum class Phase { Port,Connect,Tls,Http,WebSocket,Observe };
    void consume();
    void consumeWebSocket();
    void sendControlFrame(quint8 opcode,const QByteArray &payload);
    void sendRequest();
    void finish(const QString &message,const QString &category);
    void resetSocket();
    QVariantList m_entries;
    QPointer<QSslSocket> m_socket;
    QTimer m_deadline,m_observation;
    QUrl m_url;
    QByteArray m_buffer,m_wsKey,m_pingToken,m_controlPayload;
    quint64 m_frameRemaining=0;
    int m_frameOpcode=-1;
    bool m_fragmented=false,m_pongReceived=false;
    QString m_state=QStringLiteral("尚未诊断");
    int m_port=0;
    bool m_busy=false;
    Phase m_phase=Phase::Port;
};
