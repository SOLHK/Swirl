#pragma once
#include <QObject>
#include <QUdpSocket>
#include <QTimer>

// Bounded native UDP building block, not a SOCKS UDP Relay. Explicit endpoint,
// source checking and per-exchange lifetime prevent an open relay or stale reply.
class SwirlUdpExchange final:public QObject {
    Q_OBJECT
public:
    explicit SwirlUdpExchange(QObject *parent=nullptr);
    bool start(const QHostAddress &destination,quint16 port,const QByteArray &payload,int timeoutMs=3000);
    void cancel();
    bool busy()const{return m_socket!=nullptr;}
    qint64 sentBytes()const{return m_sent;}
    qint64 receivedBytes()const{return m_received;}
signals:
    void finished(const QByteArray &payload,const QString &error);
private:
    QUdpSocket *m_socket=nullptr;
    QTimer m_deadline;
    QHostAddress m_peer;
    quint16 m_port=0;
    qint64 m_sent=0,m_received=0;
    void complete(const QByteArray &,const QString &);
};
