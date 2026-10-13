#include <QtTest>
#include <QTcpServer>
#include <QTcpSocket>
#include <QJsonArray>
#include "network/NetworkDiagnostics.h"


class NetworkDiagnosticTests : public QObject {
    Q_OBJECT
private slots:
    void classification() {
        using N=QNetworkReply;
        QCOMPARE(NetworkDiagnostics::classify(N::NoError,false,204,{}),QStringLiteral("检测成功"));
        QCOMPARE(NetworkDiagnostics::classify(N::NoError,false,302,{}),QStringLiteral("HTTP 响应不符合预期"));
        QCOMPARE(NetworkDiagnostics::classify(N::NoError,false,200,"login"),QStringLiteral("HTTP 响应不符合预期"));
        QCOMPARE(NetworkDiagnostics::classify(N::HostNotFoundError,false,0,{}),QStringLiteral("DNS 错误"));
        QCOMPARE(NetworkDiagnostics::classify(N::SslHandshakeFailedError,false,0,{}),QStringLiteral("TLS 错误"));
        QCOMPARE(NetworkDiagnostics::classify(N::ConnectionRefusedError,false,0,{}),QStringLiteral("TCP 连接失败"));
        QCOMPARE(NetworkDiagnostics::classify(N::ProxyConnectionRefusedError,false,0,{}),QStringLiteral("代理链路异常"));
        QCOMPARE(NetworkDiagnostics::classify(N::OperationCanceledError,true,0,{}),QStringLiteral("探测超时"));
    }
    void fallbackAndProxyIsolation() {
        QTcpServer server;QVERIFY(server.listen(QHostAddress::LocalHost));
        int requests=0;
        connect(&server,&QTcpServer::newConnection,&server,[&]{
            while(server.hasPendingConnections()){
                auto *socket=server.nextPendingConnection();
                connect(socket,&QTcpSocket::readyRead,socket,[socket,&requests]{
                    auto data=socket->property("request").toByteArray()+socket->readAll();socket->setProperty("request",data);
                    if(!data.contains("\r\n\r\n") || socket->property("sent").toBool())return;
                    socket->setProperty("sent",true);++requests;
                    socket->write(data.contains("/bad")?"HTTP/1.1 200 OK\r\nContent-Length: 5\r\nConnection: close\r\n\r\nlogin":"HTTP/1.1 204 No Content\r\nConnection: close\r\n\r\n");
                    socket->disconnectFromHost();
                });
                connect(socket,&QTcpSocket::disconnected,socket,&QObject::deleteLater);
            }
        });
        NetworkDiagnostics diagnostics;
        const QString base=QStringLiteral("http://127.0.0.1:%1").arg(server.serverPort());
        diagnostics.setEndpoints({QUrl(base+"/bad"),QUrl(base+"/ok")});diagnostics.setTimeout(500);
        QTcpServer proxy;QVERIFY(proxy.listen(QHostAddress::LocalHost));
        connect(&proxy,&QTcpServer::newConnection,&proxy,[&]{while(proxy.hasPendingConnections()){
            auto *socket=proxy.nextPendingConnection();
            connect(socket,&QTcpSocket::readyRead,socket,[socket]{socket->readAll();socket->write("HTTP/1.1 407 Proxy Authentication Required\r\nProxy-Authenticate: Basic realm=fixture\r\nContent-Length: 0\r\nConnection: close\r\n\r\n");socket->disconnectFromHost();});
            connect(socket,&QTcpSocket::disconnected,socket,&QObject::deleteLater);
        }});
        diagnostics.setProxyPort(proxy.serverPort());diagnostics.start();
        QTRY_VERIFY_WITH_TIMEOUT(!diagnostics.busy(),4000);
        QCOMPARE(diagnostics.directResult().value("state").toString(),QStringLiteral("检测成功"));
        QVERIFY(diagnostics.directResult().value("latency").toLongLong()>=0);
        QCOMPARE(diagnostics.proxyResult().value("state").toString(),QStringLiteral("代理链路异常"));
        QCOMPARE(diagnostics.currentResult(),diagnostics.proxyResult());
        QCOMPARE(requests,2);QVERIFY(diagnostics.log().size()>=4);
        diagnostics.setProxyPort(0);QCOMPARE(diagnostics.currentResult(),diagnostics.directResult());
    }
    void timeoutCancelAndRestart() {
        QTcpServer server;QVERIFY(server.listen(QHostAddress::LocalHost));
        NetworkDiagnostics diagnostics;diagnostics.setTimeout(80);
        diagnostics.setEndpoints({QUrl(QStringLiteral("http://127.0.0.1:%1/hang").arg(server.serverPort()))});
        diagnostics.start();QTRY_VERIFY_WITH_TIMEOUT(!diagnostics.busy(),2000);
        QCOMPARE(diagnostics.directResult().value("state").toString(),QStringLiteral("探测超时"));
        QCOMPARE(diagnostics.directResult().value("latency").toInt(),-1);
        diagnostics.start();QVERIFY(diagnostics.busy());diagnostics.cancel();
        QCOMPARE(diagnostics.directResult().value("state").toString(),QStringLiteral("已取消"));
        QTest::qWait(150);QVERIFY(!diagnostics.busy());
        QCOMPARE(diagnostics.directResult().value("state").toString(),QStringLiteral("已取消"));
    }

};
QTEST_GUILESS_MAIN(NetworkDiagnosticTests)
#include "NetworkDiagnosticTests.moc"
