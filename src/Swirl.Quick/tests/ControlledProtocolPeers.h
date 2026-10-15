#pragma once
#include "ControlledNetwork.h"
#include "engine/OwnedProcess.h"
#include <QTemporaryDir>
#include <QJsonDocument>
#include <QJsonArray>
#include <QJsonObject>
#include <QCoreApplication>
#include <QCryptographicHash>
#include <QNetworkProxy>
#include <QTest>

// Independent, pinned Mihomo listeners for protocol interoperability. Every
// accepted request exits through SocksPeer A, so origin replies identify it.
class ControlledProtocolPeers {
public:
    QTemporaryDir directory;
    OwnedProcess process;
    quint16 trojanPort=0,ssPort=0;
    const QString password="fixture-password-only";
    QByteArray fingerprint;
    QString failure;
    ~ControlledProtocolPeers(){process.kill();process.waitForFinished(3000);}
    static quint16 port(){QTcpServer listener;if(!listener.listen(QHostAddress::LocalHost,0))return 0;return listener.serverPort();}
    bool start(const ControlledNetwork &network,quint16 publicEgressPort=0){
        trojanPort=port();ssPort=port();while(ssPort==trojanPort)ssPort=port();
        fingerprint=network.certificate.digest(QCryptographicHash::Sha256).toHex();
        const auto root=QString::fromUtf8(SWIRL_FIXTURE_DIR);
        const auto certPath=directory.filePath("cert.pem"),keyPath=directory.filePath("key.pem");
        if(!QFile::copy(root+"/localhost-cert.pem",certPath)||!QFile::copy(root+"/localhost-key.pem",keyPath))return false;
        const QJsonArray listeners{
            QJsonObject{{"name","trojan-fixture"},{"type","trojan"},{"listen","127.0.0.1"},{"port",trojanPort},{"users",QJsonArray{QJsonObject{{"username","fixture"},{"password",password}}}},{"certificate",certPath},{"private-key",keyPath}},
            QJsonObject{{"name","ss-fixture"},{"type","shadowsocks"},{"listen","127.0.0.1"},{"port",ssPort},{"cipher","aes-128-gcm"},{"password",password}}
        };
        const QJsonObject config{{"mixed-port",0},{"allow-lan",false},{"mode","rule"},{"log-level","warning"},{"ipv6",false},{"dns",QJsonObject{{"enable",false}}},{"tun",QJsonObject{{"enable",false}}},{"listeners",listeners},
            {"proxies",QJsonArray{QJsonObject{{"name","fixture-egress"},{"type","socks5"},{"server","127.0.0.1"},{"port",publicEgressPort?publicEgressPort:network.a.serverPort()}}}},{"rules",QJsonArray{"MATCH,fixture-egress"}}};
        QFile file(directory.filePath("server.json"));if(!file.open(QIODevice::WriteOnly))return false;file.write(QJsonDocument(config).toJson());file.close();
        process.setProgram(QCoreApplication::applicationDirPath()+"/core/mihomo.exe");
        process.setArguments({"-d",directory.path(),"-f",file.fileName()});process.start();
        if(!process.waitForStarted(3000)){failure="Controlled protocol peer did not start";return false;}
        const bool ready=QTest::qWaitFor([&]{QTcpSocket socket;socket.setProxy(QNetworkProxy::NoProxy);socket.connectToHost(QHostAddress::LocalHost,trojanPort);return socket.waitForConnected(80);},8000);
        if(!ready)failure="Controlled protocol listeners unavailable: "+QString::fromUtf8(process.readAllStandardOutput()+process.readAllStandardError()).left(2048);return ready;
    }
};
