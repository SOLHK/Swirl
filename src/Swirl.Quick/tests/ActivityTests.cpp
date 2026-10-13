#include <QtTest>
#include <QTcpServer>
#include <QTcpSocket>
#include <QJsonArray>
#include "network/NetworkDiagnostics.h"
#include "engine/ActivityTelemetry.h"

class ActivityTests : public QObject {
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
    void telemetry() {
        ActivityTelemetry data;
        QJsonObject connection{{"id","one"},{"upload",100},{"download",200},{"chains",QJsonArray{"DIRECT"}},
            {"metadata",QJsonObject{{"process","test.exe"},{"sourceIP","127.0.0.1"},{"host","example.test"},{"network","tcp"}}}};
        QJsonObject input{{"uploadTotal",100},{"downloadTotal",200},{"connections",QJsonArray{connection}}};
        const auto time=QDateTime(QDate(2026,10,13),QTime(12,0)).toMSecsSinceEpoch();
        QVERIFY(data.ingest(input,time));QVERIFY(!data.snapshot().value("sampled").toBool());
        input["uploadTotal"]=300;input["downloadTotal"]=600;connection["upload"]=300;connection["download"]=600;input["connections"]=QJsonArray{connection};
        QVERIFY(data.ingest(input,time+2000));const auto snap=data.snapshot();
        QCOMPARE(snap.value("up").toDouble(),100.0);QCOMPARE(snap.value("down").toDouble(),200.0);
        QCOMPARE(snap.value("today").toLongLong(),600);QCOMPARE(snap.value("direct").toLongLong(),600);
        QCOMPARE(snap.value("processes").toInt(),1);QCOMPARE(snap.value("clients").toList().first().toMap().value("name").toString(),QStringLiteral("test.exe"));
        QVERIFY(!data.ingest(QJsonObject{},time+3000));
        input["connections"]=QJsonValue::Null;
        QVERIFY(data.ingest(input,time+3000));
        QVERIFY(data.snapshot().value("connections").toList().isEmpty());
        input["uploadTotal"]=0;input["downloadTotal"]=0;input["connections"]=QJsonArray{};
        QVERIFY(data.ingest(input,time+4000));QVERIFY(!data.snapshot().value("sampled").toBool());
        QVERIFY(data.snapshot().value("upHistory").toList().isEmpty());
        QCOMPARE(data.snapshot().value("today").toLongLong(),600);
        data.reset();QVERIFY(data.snapshot().isEmpty());
    }
};
QTEST_GUILESS_MAIN(ActivityTests)
#include "ActivityTests.moc"
