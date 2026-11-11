// Exercises the distributed QtNetwork DLL through its public API. The two
// malformed responses reproduce Qt's QTBUG-150779 cases without private test
// exports or unbounded allocation. No external address is contacted.
#include <QNetworkAccessManager>
#include <QNetworkProxy>
#include <QNetworkReply>
#include <QTcpServer>
#include <QTcpSocket>
#include <QElapsedTimer>
#include <QTest>

class HttpBounds final : public QObject {
    Q_OBJECT
private slots:
    void responseBounds_data() {
        QTest::addColumn<QByteArray>("response");
        QTest::addColumn<bool>("valid");
        QTest::newRow("valid-response") << QByteArray("HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nOK") << true;
        QTest::newRow("unterminated-status-line") << QByteArray("HTTP/1.1 200 ")+QByteArray(1024*1024,'a') << false;
        QTest::newRow("unterminated-header-block") << QByteArray("HTTP/1.1 200 OK\r\nX-Long: ")+QByteArray(1024*1024,'a') << false;
    }
    void responseBounds() {
        QFETCH(QByteArray,response);QFETCH(bool,valid);
        QTcpServer server;QVERIFY(server.listen(QHostAddress::LocalHost,0));
        connect(&server,&QTcpServer::newConnection,&server,[&]{
            while(server.hasPendingConnections()) {
                auto *socket=server.nextPendingConnection();
                connect(socket,&QTcpSocket::readyRead,socket,[socket,response]{
                    if(socket->property("sent").toBool()){socket->readAll();return;}
                    const auto request=socket->property("request").toByteArray()+socket->readAll();
                    socket->setProperty("request",request);
                    if(!request.contains("\r\n\r\n"))return;
                    socket->setProperty("sent",true);socket->write(response);
                    // Deliberately leave the peer open: EOF must not be what
                    // terminates an invalid response in the patched client.
                });
            }
        });
        QNetworkAccessManager manager;manager.setProxy(QNetworkProxy::NoProxy);
        QElapsedTimer elapsed;elapsed.start();
        auto *reply=manager.get(QNetworkRequest(QUrl(QString("http://127.0.0.1:%1/").arg(server.serverPort()))));
        const bool finishedNaturally=QTest::qWaitFor([&]{return reply->isFinished();},1500);
        const auto code=reply->error();const auto body=reply->readAll();
        if(!finishedNaturally)reply->abort();
        qInfo()<<"HTTP_BOUNDS"<<QTest::currentDataTag()<<"natural_finish"<<finishedNaturally<<"elapsed_ms"<<elapsed.elapsed()<<"error"<<code;
        QVERIFY2(finishedNaturally,"Qt must reject an impossible response before the peer ends it");
        if(valid){QCOMPARE(code,QNetworkReply::NoError);QCOMPARE(body,QByteArray("OK"));}
        else {QVERIFY(code!=QNetworkReply::NoError);QVERIFY(code!=QNetworkReply::OperationCanceledError);}
        reply->deleteLater();
    }
};
QTEST_GUILESS_MAIN(HttpBounds)
#include "main.moc"
