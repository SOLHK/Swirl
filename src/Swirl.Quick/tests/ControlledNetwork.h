#pragma once
#include <QTcpServer>
#include <QTcpSocket>
#include <QSslServer>
#include <QSslSocket>
#include <QSslCertificate>
#include <QSslKey>
#include <QSslConfiguration>
#include <QFile>
#include <QHash>
#include <QPointer>
#include <QUrl>
#include <QStringList>

// Test-only real TCP relay. It never accepts non-fixture destinations and does
// not decrypt or rewrite traffic. The origin tags replies by relay source port.
class SocksPeer : public QTcpServer {
public:
    QHash<quint16,QString> *exits;
    QString label;
    QByteArray username,password;
    QList<quint16> targetPorts;
    QStringList aliases;
    int forwarded=0;
    bool reject=false;
    SocksPeer(QHash<quint16,QString> *map,QString marker):exits(map),label(std::move(marker)) {
        QObject::connect(this,&QTcpServer::newConnection,this,[this]{
            while(hasPendingConnections()) {
                auto *client=nextPendingConnection();client->setProperty("stage",0);
                QObject::connect(client,&QTcpSocket::disconnected,client,&QObject::deleteLater);
                QObject::connect(client,&QTcpSocket::readyRead,client,[this,client]{consume(client);});
            }
        });
    }
    void consume(QTcpSocket *client) {
        if(client->property("stage").toInt()==3)return;
        auto buffer=client->property("buffer").toByteArray()+client->readAll();
        int stage=client->property("stage").toInt();
        if(stage==0) {
            if(buffer.size()<2)return client->setProperty("buffer",buffer),void();
            const int count=quint8(buffer[1]);if(buffer.size()<2+count)return client->setProperty("buffer",buffer),void();
            const char method=username.isEmpty()?0:2;
            if(buffer[0]!=5 || !buffer.mid(2,count).contains(method)){client->write(QByteArray::fromHex("05ff"));client->disconnectFromHost();return;}
            buffer.remove(0,2+count);client->write(QByteArray(1,char(5))+QByteArray(1,method));stage=method==2?1:2;
        }
        if(stage==1) {
            if(buffer.size()<2)return client->setProperty("buffer",buffer),client->setProperty("stage",stage),void();
            const int u=quint8(buffer[1]);if(buffer.size()<3+u)return client->setProperty("buffer",buffer),client->setProperty("stage",stage),void();
            const int p=quint8(buffer[2+u]);if(buffer.size()<3+u+p)return client->setProperty("buffer",buffer),client->setProperty("stage",stage),void();
            const bool valid=buffer[0]==1 && buffer.mid(2,u)==username && buffer.mid(3+u,p)==password;
            client->write(QByteArray(1,char(1))+QByteArray(1,char(valid?0:1)));
            if(!valid){client->disconnectFromHost();return;}
            buffer.remove(0,3+u+p);stage=2;
        }
        if(stage==2) {
            if(buffer.size()<4)return client->setProperty("buffer",buffer),client->setProperty("stage",stage),void();
            int offset=4;QString host;
            if(buffer[3]==1){if(buffer.size()<10)return client->setProperty("buffer",buffer),client->setProperty("stage",stage),void();host=QString("%1.%2.%3.%4").arg(quint8(buffer[4])).arg(quint8(buffer[5])).arg(quint8(buffer[6])).arg(quint8(buffer[7]));offset=8;}
            else if(buffer[3]==3){if(buffer.size()<5)return;const int len=quint8(buffer[4]);if(buffer.size()<7+len)return client->setProperty("buffer",buffer),client->setProperty("stage",stage),void();host=QString::fromLatin1(buffer.mid(5,len));offset=5+len;}
            else {client->abort();return;}
            const auto port=quint16(quint8(buffer[offset])*256+quint8(buffer[offset+1]));
            if(reject || buffer[1]!=1 || (host!="127.0.0.1" && host!="localhost" && !aliases.contains(host)) || !targetPorts.contains(port)){client->write(QByteArray::fromHex("050200017f0000010000"));client->disconnectFromHost();return;}
            buffer.remove(0,offset+2);stage=3;client->setProperty("upstreamPending",buffer);buffer.clear();
            auto *upstream=new QTcpSocket(client);
            QObject::connect(upstream,&QTcpSocket::connected,client,[this,client,upstream]{
                ++forwarded;exits->insert(upstream->localPort(),label);
                client->write(QByteArray::fromHex("050000017f0000010000"));
                upstream->write(client->property("upstreamPending").toByteArray());client->setProperty("upstreamPending",QByteArray());
            });
            QObject::connect(client,&QTcpSocket::readyRead,upstream,[client,upstream]{upstream->write(client->readAll());});
            QObject::connect(upstream,&QTcpSocket::readyRead,client,[client,upstream]{client->write(upstream->readAll());});
            QObject::connect(client,&QTcpSocket::disconnected,upstream,&QTcpSocket::abort);
            QObject::connect(upstream,&QTcpSocket::disconnected,client,&QTcpSocket::disconnectFromHost);
            QObject::connect(upstream,&QTcpSocket::errorOccurred,client,[client](QAbstractSocket::SocketError error){if(error!=QAbstractSocket::RemoteHostClosedError)client->abort();});
            upstream->connectToHost(aliases.contains(host)?QStringLiteral("127.0.0.1"):host,port);
        }
        client->setProperty("buffer",buffer);client->setProperty("stage",stage);
    }
};

class ControlledNetwork {
public:
    QHash<quint16,QString> exits;
    QTcpServer http;
    QSslServer https;
    SocksPeer a{&exits,"exit-A"}, b{&exits,"exit-B"};
    QSslCertificate certificate;
    int httpRequests=0,httpsRequests=0;
    QHash<QString,int> httpRequestsByExit;
    bool start() {
        QFile cert(QString::fromUtf8(SWIRL_FIXTURE_DIR)+"/localhost-cert.pem"),key(QString::fromUtf8(SWIRL_FIXTURE_DIR)+"/localhost-key.pem");
        if(!cert.open(QIODevice::ReadOnly)||!key.open(QIODevice::ReadOnly))return false;
        certificate=QSslCertificate(cert.readAll());auto ssl=QSslConfiguration::defaultConfiguration();
        ssl.setLocalCertificate(certificate);ssl.setPrivateKey(QSslKey(key.readAll(),QSsl::Rsa));ssl.setPeerVerifyMode(QSslSocket::VerifyNone);ssl.setAllowedNextProtocols({QByteArray("http/1.1")});https.setSslConfiguration(ssl);
        if(!http.listen(QHostAddress::LocalHost,0)||!https.listen(QHostAddress::LocalHost,0)||!a.listen(QHostAddress::LocalHost,0)||!b.listen(QHostAddress::LocalHost,0))return false;
        a.targetPorts={http.serverPort(),https.serverPort()};b.targetPorts=a.targetPorts;
        b.username="test-user";b.password="fixture-secret-only";
        attach(http,false);attach(https,true);return true;
    }
    QUrl url(bool tls=false) const {return QUrl(QStringLiteral("%1://127.0.0.1:%2/check").arg(tls?"https":"http").arg(tls?https.serverPort():http.serverPort()));}
private:
    void attach(QTcpServer &server,bool tls) {
        QObject::connect(&server,&QTcpServer::pendingConnectionAvailable,&server,[this,&server,tls]{
            while(server.hasPendingConnections()){
                auto *socket=server.nextPendingConnection();
                QObject::connect(socket,&QTcpSocket::disconnected,socket,&QObject::deleteLater);
                const auto respond=[this,socket,tls]{
                    auto request=socket->property("headers").toByteArray()+socket->readAll();socket->setProperty("headers",request);
                    if(!request.contains("\r\n\r\n"))return;
                    if(tls)++httpsRequests;else ++httpRequests;
                    const auto exit=exits.value(socket->peerPort(),"DIRECT-BYPASS");
                    if(!tls)++httpRequestsByExit[exit];
                    const auto body=exit.toUtf8();
                    socket->write("HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nConnection: close\r\nContent-Length: "+QByteArray::number(body.size())+"\r\n\r\n"+body);
                    socket->disconnectFromHost();
                };
                QObject::connect(socket,&QTcpSocket::readyRead,socket,respond);
                if(socket->bytesAvailable()>0)respond();
            }
        });
    }
};
