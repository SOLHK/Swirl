#include "CaptureChecks.h"
#include "../network/CaptureService.h"
#include <QTest>
#include <QTcpSocket>
#include <QNetworkReply>
#include <QNetworkProxy>
#include <QPointer>
#include <QElapsedTimer>
#include <QTemporaryDir>
#include <QFile>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonArray>
#include <QUrlQuery>
#include <functional>

int runCaptureChecks(CaptureService *capture)
{
    int failures=0,checks=0;
    const auto check=[&](bool ok,const char *name){++checks;if(ok)qInfo()<<"PASS"<<name;else{++failures;qCritical()<<"FAIL"<<name;}};
    const auto until=[](const std::function<bool()> &predicate){QElapsedTimer t;t.start();while(!predicate() && t.elapsed()<4500)QTest::qWait(10);return predicate();};
    check(!capture->running(),"capture is opt-in at startup");
    check(!capture->start(-1),"invalid port rejected");
    check(capture->start(0) && capture->port()>0,"loopback ephemeral listener starts");
    const int proxyPort=capture->port();
    QTcpServer origin;origin.setProxy(QNetworkProxy::NoProxy);
    check(origin.listen(QHostAddress::LocalHost,0),"local HTTP fixture starts");
    bool postSeen=false,authSeen=false;
    QObject::connect(&origin,&QTcpServer::newConnection,&origin,[&]{
        while(origin.hasPendingConnections()){
            auto *socket=origin.nextPendingConnection();
            auto buffer=std::make_shared<QByteArray>();auto sent=std::make_shared<bool>(false);
            QObject::connect(socket,&QTcpSocket::disconnected,socket,&QObject::deleteLater);
            QObject::connect(socket,&QTcpSocket::readyRead,socket,[&,socket,buffer,sent]{
                if(*sent)return;*buffer+=socket->readAll();const auto end=buffer->indexOf("\r\n\r\n");if(end<0)return;
                qint64 length=0;for(auto line:buffer->left(end).split('\n'))if(line.toLower().startsWith("content-length:"))length=line.mid(line.indexOf(':')+1).trimmed().toLongLong();
                if(buffer->size()<end+4+length)return;
                *sent=true;authSeen=authSeen||buffer->contains("Bearer private-fixture-token");
                if(buffer->startsWith("GET /truncated ")){socket->write("HTTP/1.1 200 OK\r\nContent-Length: 99\r\nConnection: close\r\n\r\n{}");socket->disconnectFromHost();return;}
                const bool post=buffer->startsWith("POST ");postSeen=postSeen||post;
                const auto body=post?buffer->mid(end+4,length):QByteArray("{\"hello\":\"swirl\"}");
                socket->write("HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nSet-Cookie: session=private-cookie\r\nContent-Length: "+QByteArray::number(body.size())+"\r\nConnection: close\r\n\r\n"+body);socket->disconnectFromHost();
            });
        }
    });
    QNetworkAccessManager browser;browser.setProxy(QNetworkProxy(QNetworkProxy::HttpProxy,"127.0.0.1",proxyPort));
    const QUrl target(QString("http://127.0.0.1:%1/test?token=private-url-token").arg(origin.serverPort()));
    QNetworkRequest request(target);request.setRawHeader("Authorization","Bearer private-fixture-token");request.setRawHeader("Cookie","session=private-request-cookie");
    auto *get=browser.get(request);
    check(until([&]{return get->isFinished();}),"GET traverses actual capture proxy");
    const auto getBody=get->readAll();
    check(get->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt()==200 && getBody=="{\"hello\":\"swirl\"}","GET response reaches caller unchanged");
    check(authSeen,"authorization forwarded to intended origin");
    check(capture->sessions().size()==1,"GET creates one real session");
    auto row=capture->sessions().value(0).toMap();
    check(row["requestHeaders"].toString().contains("[已隐藏]") && !row["requestHeaders"].toString().contains("private-fixture-token"),"authentication hidden in captured metadata");
    check(!row["url"].toString().contains("private-url-token"),"URL token hidden in captured metadata");
    check(!row["responseHeaders"].toString().contains("private-cookie"),"response cookie hidden");
    check(row["responseBody"].toString().contains("hello") && row["downBytes"].toLongLong()==getBody.size(),"body preview and byte count come from actual response");
    get->deleteLater();
    request.setHeader(QNetworkRequest::ContentTypeHeader,"application/json");
    auto *post=browser.post(request,"{\"payload\":123}");
    check(until([&]{return post->isFinished();}),"POST traverses actual capture proxy");
    check(postSeen && post->readAll()=="{\"payload\":123}","POST request body forwarded and echoed");
    post->deleteLater();
    QNetworkRequest incomplete(QUrl(QString("http://127.0.0.1:%1/truncated").arg(origin.serverPort())));
    auto *partial=browser.get(incomplete);
    check(until([&]{return partial->isFinished();}),"premature EOF returns instead of hanging");
    check(partial->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt()==502 && capture->sessions().value(0).toMap()["statusCode"].toInt()==502,
          "incomplete 200 response is marked as capture error");
    partial->deleteLater();

    QTcpServer echo;echo.setProxy(QNetworkProxy::NoProxy);check(echo.listen(QHostAddress::LocalHost,0),"opaque tunnel fixture starts");
    QObject::connect(&echo,&QTcpServer::newConnection,&echo,[&]{auto *s=echo.nextPendingConnection();QObject::connect(s,&QTcpSocket::readyRead,s,[s]{s->write(s->readAll());});QObject::connect(s,&QTcpSocket::disconnected,s,&QObject::deleteLater);});
    QTcpSocket tunnel;tunnel.setProxy(QNetworkProxy::NoProxy);tunnel.connectToHost(QHostAddress::LocalHost,proxyPort);
    check(until([&]{return tunnel.state()==QAbstractSocket::ConnectedState;}),"tunnel client connects to loopback proxy");
    tunnel.write("CONNECT 127.0.0.1:"+QByteArray::number(echo.serverPort())+" HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n");
    QByteArray handshake;
    check(until([&]{handshake+=tunnel.readAll();return handshake.contains("\r\n\r\n");}) && handshake.startsWith("HTTP/1.1 200"),"CONNECT establishes real TCP tunnel");
    const QByteArray opaque=QByteArray::fromHex("1603010008737769726c00ff");tunnel.write(opaque);
    QByteArray echoed;check(until([&]{echoed+=tunnel.readAll();return echoed.size()>=opaque.size();}) && echoed==opaque,"opaque tunnel payload preserved byte-for-byte");
    until([&]{auto r=capture->sessions().value(0).toMap();return r["upBytes"].toLongLong()==opaque.size() && r["downBytes"].toLongLong()==opaque.size();});
    row=capture->sessions().value(0).toMap();
    check(row["tunnel"].toBool() && row["responseBody"].toString().contains("没有解密"),"tunnel does not claim TLS decryption");
    check(row["upBytes"].toLongLong()==opaque.size() && row["downBytes"].toLongLong()==opaque.size(),"tunnel byte counters are real");
    tunnel.disconnectFromHost();until([&]{return capture->activeCount()==0;});

    QTcpSocket bad;bad.setProxy(QNetworkProxy::NoProxy);bad.connectToHost(QHostAddress::LocalHost,proxyPort);until([&]{return bad.state()==QAbstractSocket::ConnectedState;});
    bad.write("POST http://127.0.0.1/ HTTP/1.1\r\nContent-Length: -1\r\n\r\n");QByteArray rejection;
    check(until([&]{rejection+=bad.readAll();return !rejection.isEmpty();}) && rejection.startsWith("HTTP/1.1 400"),"negative Content-Length rejected");
    QTcpSocket chunked;chunked.setProxy(QNetworkProxy::NoProxy);chunked.connectToHost(QHostAddress::LocalHost,proxyPort);until([&]{return chunked.state()==QAbstractSocket::ConnectedState;});
    chunked.write("POST http://127.0.0.1/ HTTP/1.1\r\nTransfer-Encoding: chunked\r\n\r\n0\r\n\r\n");QByteArray chunkedReply;
    check(until([&]{chunkedReply+=chunked.readAll();return !chunkedReply.isEmpty();}) && chunkedReply.startsWith("HTTP/1.1 501"),"unsupported chunked upload fails explicitly");
    QTcpSocket loop;loop.setProxy(QNetworkProxy::NoProxy);loop.connectToHost(QHostAddress::LocalHost,proxyPort);until([&]{return loop.state()==QAbstractSocket::ConnectedState;});
    loop.write("GET http://127.0.0.1:"+QByteArray::number(proxyPort)+"/ HTTP/1.1\r\nHost: localhost\r\n\r\n");QByteArray loopReply;
    check(until([&]{loopReply+=loop.readAll();return !loopReply.isEmpty();}) && loopReply.startsWith("HTTP/1.1 400"),"direct self-proxy loop rejected");
    QTemporaryDir dir;const auto filePath=dir.filePath("capture.har");
    check(capture->exportHar(QUrl::fromLocalFile(filePath)),"HAR export writes actual capture records");
    QFile file(filePath);check(file.open(QIODevice::ReadOnly),"exported HAR can be read");const auto bytes=file.readAll();const auto log=QJsonDocument::fromJson(bytes).object()["log"].toObject();
    check(log["version"]=="1.2" && log["entries"].toArray().size()==7,"HAR 1.2 includes requests tunnels and rejected requests");
    check(!bytes.contains("private-fixture-token") && !bytes.contains("private-cookie") && !bytes.contains("private-url-token"),"export preserves metadata redaction");
    capture->stop();check(!capture->running() && until([&]{return capture->activeCount()==0;}),"stop closes listener and live sessions");
    QTcpServer reclaimed;check(reclaimed.listen(QHostAddress::LocalHost,proxyPort),"stopped port can be reused");
    capture->clear();check(capture->sessions().isEmpty(),"capture history can be cleared");
    qInfo()<<"Capture integration checks:"<<checks<<"checks,"<<failures<<"failures";
    return failures?2:0;
}
