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
#include <QSslServer>
#include <QSslConfiguration>
#include <QSslSocket>
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
                const auto body=buffer->startsWith("GET /large ")?QByteArray(3*1024*1024,'x'):post?buffer->mid(end+4,length):QByteArray("{\"hello\":\"swirl\"}");
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
    reclaimed.close();
    check(capture->start(0),"rewrite fixture listener starts");
    browser.setProxy(QNetworkProxy(QNetworkProxy::HttpProxy,"127.0.0.1",capture->port()));
    check(!capture->saveRewriteRule({{"kind","header"},{"pattern",".*"},{"name","X-Test"},{"replacement","bad\r\nInjected: yes"}}),"rewrite rejects header injection");
    check(capture->saveRewriteRule({{"kind","mock"},{"pattern","^http://fixture.invalid/mock$"},{"replacement","{\"mock\":true}"},{"status",201}}),"mock rule validates and saves");
    capture->setRewriteEnabled(true);
    auto *mock=browser.get(QNetworkRequest(QUrl("http://fixture.invalid/mock")));
    check(until([&]{return mock->isFinished();})&&mock->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt()==201&&mock->readAll()=="{\"mock\":true}","mock returns a real response without origin DNS or network access");mock->deleteLater();
    capture->removeRewriteRule(capture->rewriteRules().first().toMap().value("id").toString());
    check(capture->saveRewriteRule({{"kind","redirect"},{"pattern","^http://fixture.invalid/redirect$"},{"replacement","https://example.test/destination"},{"status",307}}),"redirect rule saves");
    QNetworkRequest redirectRequest(QUrl("http://fixture.invalid/redirect"));redirectRequest.setAttribute(QNetworkRequest::RedirectPolicyAttribute,QNetworkRequest::ManualRedirectPolicy);
    auto *redirect=browser.get(redirectRequest);
    check(until([&]{return redirect->isFinished();})&&redirect->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt()==307&&redirect->rawHeader("Location")=="https://example.test/destination","redirect status and Location reach caller");redirect->deleteLater();
    capture->removeRewriteRule(capture->rewriteRules().first().toMap().value("id").toString());
    check(capture->saveRewriteRule({{"kind","body"},{"pattern",".*"},{"search","hello"},{"replacement","changed"},{"direction","response"}}),"body rewrite saves");
    auto *changed=browser.get(QNetworkRequest(QUrl(QStringLiteral("http://127.0.0.1:%1/body").arg(origin.serverPort()))));
    check(until([&]{return changed->isFinished();})&&changed->readAll().contains("changed"),"response body rewrite reaches caller with updated content length");changed->deleteLater();
    capture->removeRewriteRule(capture->rewriteRules().first().toMap().value("id").toString());
    check(capture->saveRewriteRule({{"kind","header"},{"pattern",".*"},{"name","X-Swirl-Test"},{"replacement","actual"},{"direction","response"}}),"response header rewrite saves");
    auto *headerReply=browser.get(QNetworkRequest(QUrl(QStringLiteral("http://127.0.0.1:%1/header").arg(origin.serverPort()))));
    check(until([&]{return headerReply->isFinished();})&&headerReply->rawHeader("X-Swirl-Test")=="actual","response header rewrite reaches caller");headerReply->deleteLater();
    capture->removeRewriteRule(capture->rewriteRules().first().toMap().value("id").toString());
    check(capture->saveRewriteRule({{"kind","forward"},{"listenPort",0},{"targetHost","127.0.0.1"},{"targetPort",int(echo.serverPort())}}),"TCP port forward rule saves");
    const auto forwardPorts=capture->forwardingPorts();
    check(!forwardPorts.isEmpty()&&forwardPorts.first().toInt()>0,"TCP port forwarding owns an actual loopback listener");
    QTcpSocket forwarded;forwarded.setProxy(QNetworkProxy::NoProxy);forwarded.connectToHost(QHostAddress::LocalHost,quint16(forwardPorts.first().toInt()));
    check(until([&]{return forwarded.state()==QAbstractSocket::ConnectedState;}),"TCP forward client connects");
    forwarded.write("forward-real-bytes");forwarded.flush();QByteArray forwardedBytes;
    check(until([&]{forwardedBytes+=forwarded.readAll();return forwardedBytes.contains("forward-real-bytes");}),"TCP forwarding preserves data across the real socket pair");forwarded.abort();
    capture->removeRewriteRule(capture->rewriteRules().first().toMap().value("id").toString());capture->setRewriteEnabled(false);
    auto *large=browser.get(QNetworkRequest(QUrl(QStringLiteral("http://127.0.0.1:%1/large").arg(origin.serverPort()))));
    check(until([&]{return large->isFinished();})&&large->error()==QNetworkReply::NoError&&large->readAll()==QByteArray(3*1024*1024,'x'),"large HTTP response streams beyond the capture buffer limit");large->deleteLater();
    const auto largeRecord=capture->sessions().first().toMap();check(largeRecord.value("downBytes").toLongLong()==3*1024*1024&&QByteArray::fromBase64(largeRecord.value("responseBase64").toByteArray()).size()<=64*1024,"large response keeps exact byte count and a bounded HAR body preview");
    auto *tls=capture->tls();
    const auto hostsPath=dir.filePath("hosts-before-ca.dpapi");
    {TlsCertificateService hosts(hostsPath);check(hosts.addHostname("*.before-ca.test"),"MitM hostname can be saved before generating CA");}
    {TlsCertificateService hosts(hostsPath);check(!hosts.ready()&&hosts.matchesHost("www.before-ca.test"),"MitM hostnames survive restart before CA exists");}
    check(tls->generate()&&tls->ready(),"Windows creates a real CA with an encrypted private-key store");
    if(!tls->ready())qInfo()<<"CA_GENERATION_ERROR"<<tls->error();
    check(!tls->enabled(),"CA generation does not automatically enable TLS interception");
    tls->setHostnames({"*.example.test","-private.example.test"});check(tls->matchesHost("public.example.test")&&!tls->matchesHost("private.example.test"),"explicit MitM exclusions take priority over wildcard inclusion");
    check(!tls->addHostname("bad host")&&!tls->hostnames().contains("bad host"),"invalid MitM hostname does not enter the active list");
    const auto identity=tls->identityFor("localhost");
    check(!identity.certificate.isNull()&&!identity.key.isNull(),"host certificate and usable RSA key are signed by the local CA");
    const QUrl fixture=QUrl::fromLocalFile(QStringLiteral(SWIRL_FIXTURE_DIR)+"/test-ca.p12");
    const auto originalFingerprint=tls->fingerprint();
    check(!tls->importPkcs12(fixture,"wrong-password")&&tls->fingerprint()==originalFingerprint,"wrong PKCS #12 password leaves existing CA intact");
    check(tls->importPkcs12(fixture,"swirl-test-only")&&tls->ready(),"password-protected RSA CA imports through Windows encrypted key store");
    const auto importedIdentity=tls->identityFor("fixture.test");
    check(!importedIdentity.key.isNull()&&!importedIdentity.certificate.isNull(),"imported CA signs usable host certificates");
    QTemporaryDir certificateStore;const auto certificatePath=certificateStore.filePath("ca.dpapi");
    {TlsCertificateService persisted(certificatePath);check(persisted.importPkcs12(fixture,"swirl-test-only"),"CA can be persisted without installing system trust");persisted.setHostnames({"*.fixture.test"});}
    {TlsCertificateService restored(certificatePath);restored.setEnabled(true);check(restored.ready()&&restored.shouldIntercept("api.fixture.test")&&!restored.identityFor("api.fixture.test").key.isNull(),"DPAPI reload preserves CA private key and hostname scope");}
    // Use the currently selected CA after the import tests.
    const auto handshakeIdentity=tls->identityFor("localhost");
    const auto originalSsl=QSslConfiguration::defaultConfiguration();auto trustedSsl=originalSsl;trustedSsl.addCaCertificate(tls->certificate());QSslConfiguration::setDefaultConfiguration(trustedSsl);
    QSslServer secureOrigin;auto serverSsl=trustedSsl;serverSsl.setLocalCertificateChain({handshakeIdentity.certificate,tls->certificate()});serverSsl.setPrivateKey(handshakeIdentity.key);serverSsl.setPeerVerifyMode(QSslSocket::VerifyNone);serverSsl.setAllowedNextProtocols({QByteArray("http/1.1")});secureOrigin.setSslConfiguration(serverSsl);
    check(secureOrigin.listen(QHostAddress::LocalHost,0),"isolated TLS origin starts without installing a certificate into Windows");
    QObject::connect(&secureOrigin,&QSslServer::pendingConnectionAvailable,&secureOrigin,[&]{while(secureOrigin.hasPendingConnections()){auto *socket=secureOrigin.nextPendingConnection();QObject::connect(socket,&QTcpSocket::readyRead,socket,[socket]{const auto data=socket->readAll();if(!data.contains("\r\n\r\n"))return;const QByteArray body=data.contains(" /h2-large ")?QByteArray(3*1024*1024,'h'):QByteArray("{\"tls\":\"cleartext\"}");socket->write("HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\nContent-Length: "+QByteArray::number(body.size())+"\r\n\r\n"+body);socket->disconnectFromHost();});QObject::connect(socket,&QTcpSocket::disconnected,socket,&QObject::deleteLater);}});
    tls->setHostnames({"localhost"});tls->setEnabled(true);
    QNetworkRequest secureRequest(QUrl(QStringLiteral("https://localhost:%1/decrypted").arg(secureOrigin.serverPort())));secureRequest.setSslConfiguration(trustedSsl);secureRequest.setAttribute(QNetworkRequest::Http2AllowedAttribute,false);
    auto *secure=browser.get(secureRequest);
    check(until([&]{return secure->isFinished();})&&secure->error()==QNetworkReply::NoError&&secure->readAll().contains("cleartext"),"trusted HTTPS request traverses real local MITM and verified TLS origin");
    const auto decrypted=capture->sessions().value(0).toMap();
    check(decrypted.value("tlsDecrypted").toBool()&&decrypted.value("responseBody").toString().contains("cleartext"),"HTTPS body capture is actual decrypted content");secure->deleteLater();
    QNetworkRequest excludedRequest(QUrl(QStringLiteral("https://127.0.0.1:%1/excluded").arg(secureOrigin.serverPort())));auto excludedSsl=trustedSsl;excludedSsl.setPeerVerifyMode(QSslSocket::VerifyNone);excludedRequest.setSslConfiguration(excludedSsl);excludedRequest.setAttribute(QNetworkRequest::Http2AllowedAttribute,false);
    auto *excluded=browser.get(excludedRequest);
    check(until([&]{return excluded->isFinished();})&&excluded->readAll().contains("cleartext"),"non-whitelisted TLS host remains an opaque tunnel");
    const auto opaqueCapture=capture->sessions().value(0).toMap();check(opaqueCapture.value("tunnel").toBool()&&!opaqueCapture.value("tlsDecrypted").toBool(),"TLS hostname list prevents unrelated decryption");excluded->deleteLater();
    tls->setHttp2Enabled(true);browser.clearConnectionCache();
    QNetworkRequest h2Request(QUrl(QStringLiteral("https://localhost:%1/h2").arg(secureOrigin.serverPort())));h2Request.setSslConfiguration(trustedSsl);h2Request.setAttribute(QNetworkRequest::Http2AllowedAttribute,true);
    tls->setEnabled(false);capture->setAutoMitmEnabled(true);
    auto *warm=browser.get(h2Request);
    check(until([&]{return warm->isFinished();})&&warm->error()==QNetworkReply::NoError&&warm->attribute(QNetworkRequest::Http2WasUsedAttribute).toBool(),"capture MITM override works independently of the master TLS switch");warm->deleteLater();capture->clear();
    QList<QNetworkReply *> multiplexed;for(int i=0;i<3;++i)multiplexed.append(browser.get(h2Request));
    bool h2Passed=true;for(auto *reply:multiplexed){h2Passed=until([&]{return reply->isFinished();})&&reply->error()==QNetworkReply::NoError&&reply->attribute(QNetworkRequest::Http2WasUsedAttribute).toBool()&&reply->readAll().contains("cleartext")&&h2Passed;if(reply->error()!=QNetworkReply::NoError)qInfo()<<"H2_REPLY_ERROR"<<reply->errorString();reply->deleteLater();}
    check(h2Passed,"nghttp2 negotiates HTTP/2 and captures concurrent real TLS streams");
    QSet<QString> connectionIds;QSet<int> streamIds;for(const auto &entry:capture->sessions()){const auto record=entry.toMap();connectionIds.insert(record.value("connectionId").toString());streamIds.insert(record.value("http2StreamId").toInt());}
    check(connectionIds.size()==1&&streamIds.size()==3&&!streamIds.contains(0),"three HTTP/2 streams share one actual TLS connection");
    const auto h2Record=capture->sessions().value(0).toMap();check(h2Record.value("httpVersion")=="HTTP/2"&&h2Record.value("tlsDecrypted").toBool(),"HTTP/2 capture records the negotiated protocol and plaintext");
    check(capture->saveRewriteRule({{"kind","mock"},{"pattern","/h2-mock$"},{"replacement","{\"h2mock\":true}"}}),"HTTP/2 mock rule saves");capture->setRewriteEnabled(true);
    auto mockUrl=h2Request.url();mockUrl.setPath("/h2-mock");h2Request.setUrl(mockUrl);auto *h2Mock=browser.get(h2Request);
    check(until([&]{return h2Mock->isFinished();})&&h2Mock->error()==QNetworkReply::NoError&&h2Mock->attribute(QNetworkRequest::Http2WasUsedAttribute).toBool()&&h2Mock->readAll().contains("h2mock"),"HTTP/2 mock response uses real HEADERS and DATA frames");h2Mock->deleteLater();
    auto largeH2Url=h2Request.url();largeH2Url.setPath("/h2-large");h2Request.setUrl(largeH2Url);auto *largeH2=browser.get(h2Request);
    check(until([&]{return largeH2->isFinished();})&&largeH2->error()==QNetworkReply::NoError&&largeH2->attribute(QNetworkRequest::Http2WasUsedAttribute).toBool()&&largeH2->readAll()==QByteArray(3*1024*1024,'h'),"large HTTP/2 response honors native flow control without capture buffer truncation");largeH2->deleteLater();
    capture->removeRewriteRule(capture->rewriteRules().first().toMap().value("id").toString());capture->setRewriteEnabled(false);tls->setHttp2Enabled(false);
    tls->setEnabled(false);QSslConfiguration::setDefaultConfiguration(originalSsl);
    capture->stop();capture->clear();capture->setLimits(0,0,1);capture->setFilter("nonmatching-filter");
    check(capture->start(0),"bounded capture listener starts");browser.setProxy(QNetworkProxy(QNetworkProxy::HttpProxy,"127.0.0.1",capture->port()));
    auto *bounded=browser.get(QNetworkRequest(QUrl(QStringLiteral("http://127.0.0.1:%1/bounded").arg(origin.serverPort()))));
    check(until([&]{return bounded->isFinished();})&&bounded->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt()==200,"last request drains before automatic capture stop");bounded->deleteLater();
    check(until([&]{return !capture->running();}),"request limiter closes the actual listener");
    check(capture->sessions().isEmpty(),"filtered requests still count toward the capture limiter");
    capture->stop();capture->setLimits(0,0,0);capture->setFilter("");capture->clear();
    qInfo()<<"Capture integration checks:"<<checks<<"checks,"<<failures<<"failures";
    return failures?2:0;
}
