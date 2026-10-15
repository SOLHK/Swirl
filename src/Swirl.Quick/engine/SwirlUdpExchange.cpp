#include "SwirlUdpExchange.h"
#include <QNetworkDatagram>
#include <QNetworkProxy>
SwirlUdpExchange::SwirlUdpExchange(QObject *parent):QObject(parent){m_deadline.setSingleShot(true);connect(&m_deadline,&QTimer::timeout,this,[this]{complete({},"UdpTimeout");});}
bool SwirlUdpExchange::start(const QHostAddress &peer,quint16 port,const QByteArray &payload,int timeout){
    if(busy()||peer.isNull()||peer.isMulticast()||peer==QHostAddress::Broadcast||port==0||payload.size()>65507||timeout<50||timeout>30000)return false;
    auto socket=new QUdpSocket(this);socket->setProxy(QNetworkProxy::NoProxy);
    if(!socket->bind(peer.protocol()==QAbstractSocket::IPv6Protocol?QHostAddress::AnyIPv6:QHostAddress::AnyIPv4,0)){socket->deleteLater();return false;}
    m_socket=socket;m_peer=peer;m_port=port;m_sent=m_received=0;
    connect(socket,&QUdpSocket::readyRead,this,[this,socket]{
        // Bound work per event; a spoofed source cannot keep the deadline alive.
        for(int i=0;i<32&&m_socket==socket&&socket->hasPendingDatagrams();++i){auto d=socket->receiveDatagram(65507);if(d.senderAddress()==m_peer&&d.senderPort()==m_port){m_received=d.data().size();complete(d.data(),{});return;}}
    });
    connect(socket,&QUdpSocket::errorOccurred,this,[this,socket](auto){if(m_socket==socket)complete({},"UdpNetworkError");});
    m_deadline.start(timeout);const auto sent=socket->writeDatagram(payload,peer,port);if(sent<0){complete({},"UdpSendFailed");return false;}m_sent=sent;return true;
}
void SwirlUdpExchange::complete(const QByteArray &payload,const QString &error){if(!m_socket)return;auto socket=m_socket;m_socket=nullptr;m_deadline.stop();socket->disconnect(this);socket->close();socket->deleteLater();emit finished(payload,error);}
void SwirlUdpExchange::cancel(){if(m_socket)complete({},"UdpCancelled");}
