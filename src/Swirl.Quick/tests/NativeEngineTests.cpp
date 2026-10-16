#include "engine/SwirlProxyEngine.h"
#include "engine/ThreadedEngine.h"
#include <future>
#include <atomic>
#include "engine/SwirlEngineManager.h"
#include "engine/SwirlProtocolRegistry.h"
#include "engine/SwirlUdpExchange.h"
#include "engine/TelemetryService.h"
#include "ControlledProtocolPeers.h"
#include <QNetworkAccessManager>
#include <QNetworkReply>
#include <QSignalSpy>
#include <QJsonDocument>
#include <QUuid>
#include <QNetworkDatagram>

class NativeEngineTests:public QObject {
    Q_OBJECT
    EngineStartOptions options(){EngineStartOptions o;o.proxyPort=ControlledProtocolPeers::port();o.controlPort=ControlledProtocolPeers::port();o.startupTimeoutMs=3000;o.routingMode="global";QFile f(QString::fromUtf8(SWIRL_TEST_MANIFEST));if(f.open(QIODevice::ReadOnly)){auto m=QJsonDocument::fromJson(f.readAll()).object();o.expectedSha256=m["executableSha256"].toString().toLatin1();o.expectedVersion=m["version"].toString();}o.executablePath=QCoreApplication::applicationDirPath()+"/core/mihomo.exe";return o;}
    ProxyNode node(quint16 port,QString protocol="socks5"){ProxyNode n;n.id=QUuid::createUuid().toString(QUuid::WithoutBraces);n.name="controlled-native";n.host="127.0.0.1";n.port=port;n.protocol=protocol;return n;}
    QByteArray fetch(const QUrl &url,const EngineStartOptions &o,bool socks=false){
        QNetworkAccessManager client;client.setProxy(QNetworkProxy(socks?QNetworkProxy::Socks5Proxy:QNetworkProxy::HttpProxy,"127.0.0.1",o.proxyPort,o.inboundUsername,o.inboundPassword));QNetworkRequest r(url);r.setTransferTimeout(8000);r.setRawHeader("Connection","close");r.setAttribute(QNetworkRequest::Http2AllowedAttribute,false);auto reply=client.get(r);QSignalSpy done(reply,&QNetworkReply::finished);if(!reply->isFinished()&&!done.wait(10000)){reply->abort();return "TIMEOUT";}if(reply->error()!=QNetworkReply::NoError)return "ERROR-"+QByteArray::number(reply->error());return reply->readAll();
    }
    QByteArray exchange(QTcpSocket &socket,const QByteArray &bytes,int minimum=1){socket.write(bytes);QByteArray result;QTest::qWaitFor([&]{result+=socket.readAll();return result.size()>=minimum||socket.state()==QAbstractSocket::UnconnectedState;},4000);return result;}
    QSslConfiguration original;
private slots:
    void threadedTunnelSurvivesUiStallAndIdle() {
        QThread peerThread;QObject peerContext;peerContext.moveToThread(&peerThread);peerThread.start();
        quint16 port=0;QTcpServer *server=nullptr;
        QMetaObject::invokeMethod(&peerContext,[&]{
            server=new QTcpServer(&peerContext);server->listen(QHostAddress::LocalHost);port=server->serverPort();
            connect(server,&QTcpServer::newConnection,server,[server]{while(auto *socket=server->nextPendingConnection()){
                connect(socket,&QTcpSocket::readyRead,socket,[socket]{socket->write(socket->readAll());});
                connect(socket,&QTcpSocket::disconnected,socket,&QObject::deleteLater);
            }});
        },Qt::BlockingQueuedConnection);
        ThreadedEngine engine;auto o=options();o.directSession=true;engine.start(o);
        const bool ready=QTest::qWaitFor([&]{return engine.status().state==ProxyEngine::State::Running;},5000);
        std::atomic<int> packets{0};
        const int seconds=qMax(4,qEnvironmentVariableIntValue("SWIRL_LONG_STREAM_SECONDS"));
        auto client=std::async(std::launch::async,[&]{
            if(!ready)return false;
            QTcpSocket socket;socket.setProxy(QNetworkProxy::NoProxy);socket.connectToHost(QHostAddress::LocalHost,o.proxyPort);
            if(!socket.waitForConnected(3000))return false;
            socket.write("CONNECT 127.0.0.1:"+QByteArray::number(port)+" HTTP/1.1\r\nHost: fixture\r\n\r\n");
            if(!socket.waitForReadyRead(3000)||!socket.readAll().startsWith("HTTP/1.1 200"))return false;
            QElapsedTimer clock;clock.start();bool idleDone=false;
            while(clock.elapsed()<seconds*1000){
                if(seconds>=1200&&!idleDone&&clock.elapsed()>2000){QThread::sleep(135);idleDone=true;}
                const QByteArray block(16384,char(packets.load()%127));socket.write(block);
                QByteArray received;QElapsedTimer deadline;deadline.start();
                while(received.size()<block.size()&&deadline.elapsed()<3000){
                    if(!socket.bytesAvailable()&&!socket.waitForReadyRead(1000))continue;
                    received+=socket.readAll();
                }
                if(received!=block)return false;
                ++packets;QThread::msleep(20);
            }
            socket.disconnectFromHost();return true;
        });
        QThread::msleep(1800); // Deliberately block the UI/test thread.
        const int duringStall=packets.load();
        while(client.wait_for(std::chrono::milliseconds(0))!=std::future_status::ready)QTest::qWait(20);
        const bool complete=client.get();engine.stop();
        const bool stopped=QTest::qWaitFor([&]{return engine.status().state==ProxyEngine::State::Stopped;},5000);
        QMetaObject::invokeMethod(&peerContext,[&]{delete server;peerContext.moveToThread(QCoreApplication::instance()->thread());},Qt::BlockingQueuedConnection);
        peerThread.quit();peerThread.wait();
        qInfo()<<"Threaded tunnel seconds"<<seconds<<"packets during UI stall"<<duringStall<<"total"<<packets.load();
        QVERIFY(ready);QVERIFY(duringStall>10);QVERIFY(complete);QVERIFY(stopped);
    }

    void explicitCompatibilityPreferenceKeepsNetworkOptions() {
        EngineStartOptions o;o.routingMode="global";o.directSession=true;
        QVERIFY(SwirlProtocolRegistry::nativeSessionReason(o).isEmpty());
        o.preferCompatibility=true;
        QVERIFY(SwirlProtocolRegistry::nativeSessionReason(o).contains("用户选择"));
        QVERIFY(o.directSession);QCOMPARE(o.routingMode,QString("global"));
    }
    void websocketUpgradeAndExistingStreamSurviveNativeNodeSwitch() {
        // Compiled fixture only unless the user explicitly runs it. All peers
        // are loopback servers with fixture credentials; no subscriptions.
        ControlledNetwork net;QVERIFY(net.start());QTcpServer origin;QVERIFY(origin.listen(QHostAddress::LocalHost));
        net.a.targetPorts.append(origin.serverPort());net.b.targetPorts.append(origin.serverPort());
        connect(&origin,&QTcpServer::newConnection,&origin,[&origin]{while(origin.hasPendingConnections()){
            auto *peer=origin.nextPendingConnection();connect(peer,&QTcpSocket::disconnected,peer,&QObject::deleteLater);
            connect(peer,&QTcpSocket::readyRead,peer,[peer]{
                auto input=peer->readAll();
                if(peer->property("upgraded").toBool()){peer->write(input);return;}
                input=peer->property("request").toByteArray()+input;peer->setProperty("request",input);
                const auto end=input.indexOf("\r\n\r\n");if(end<0)return;
                if(!input.contains("Connection: Upgrade\r\n")||!input.contains("Upgrade: websocket\r\n")){peer->abort();return;}
                peer->setProperty("upgraded",true);
                peer->write("HTTP/1.1 101 Switching Protocols\r\nConnection: Upgrade\r\nUpgrade: websocket\r\n\r\n"+input.mid(end+4));
            });
        }});
        auto o=options();auto a=node(net.a.serverPort()),b=node(net.b.serverPort());b.username=QString::fromUtf8(net.b.username);b.password=QString::fromUtf8(net.b.password);o.nodes={a,b};o.selectedNodeId=a.id;
        SwirlEngineManager engine;engine.start(o);QCOMPARE(engine.status().engineKind,QString("native"));
        QTcpSocket client;client.setProxy(QNetworkProxy::NoProxy);client.connectToHost(QHostAddress::LocalHost,o.proxyPort);QTRY_COMPARE(client.state(),QAbstractSocket::ConnectedState);
        const auto url=QStringLiteral("http://127.0.0.1:%1/socket").arg(origin.serverPort()).toUtf8();
        const auto response=exchange(client,"GET "+url+" HTTP/1.1\r\nHost: fixture\r\nConnection: Upgrade\r\nUpgrade: websocket\r\nSec-WebSocket-Key: fixture\r\nSec-WebSocket-Version: 13\r\n\r\n");
        QVERIFY(response.startsWith("HTTP/1.1 101"));const auto session=engine.status().sessionId;const auto pid=engine.status().processId;
        QCOMPARE(exchange(client,"before-switch"),QByteArray("before-switch"));engine.selectNode(b.id);
        QCOMPARE(engine.status().selectedNodeId,b.id);QCOMPARE(engine.status().sessionId,session);QCOMPARE(engine.status().processId,pid);
        QCOMPARE(exchange(client,"after-switch"),QByteArray("after-switch"));QCOMPARE(fetch(net.url(),o),QByteArray("exit-B"));
        const QByteArray payload(1024*1024,'w');client.write(payload);QByteArray received;
        QTRY_COMPARE_WITH_TIMEOUT((received+=client.readAll()).size(),payload.size(),6000);QCOMPARE(received,payload);
        net.b.reject=true;QVERIFY(fetch(net.url(),o).startsWith("ERROR"));
        QCOMPARE(engine.status().engineKind,QString("native"));QCOMPARE(exchange(client,"after-new-request-failure"),QByteArray("after-new-request-failure"));
        client.abort();engine.stop();
    }
    void initTestCase(){original=QSslConfiguration::defaultConfiguration();QFile f(QString::fromUtf8(SWIRL_FIXTURE_DIR)+"/localhost-cert.pem");QVERIFY(f.open(QIODevice::ReadOnly));auto ssl=original;ssl.addCaCertificate(QSslCertificate(f.readAll()));QSslConfiguration::setDefaultConfiguration(ssl);}
    void cleanupTestCase(){QSslConfiguration::setDefaultConfiguration(original);}
    void nativePublicInternetThroughExplicitLocalEgress(){
        const auto port=qEnvironmentVariableIntValue("SWIRL_NATIVE_PUBLIC_PROXY_PORT");if(port<1||port>65535)QSKIP("Requires an explicitly configured existing local test egress");
        ControlledNetwork net;QVERIFY(net.start());ControlledProtocolPeers peers;QVERIFY2(peers.start(net,quint16(port)),qPrintable(peers.failure));
        for(const auto &protocol:QStringList{"http","socks5","trojan"}){
            auto o=options();auto n=node(protocol=="trojan"?peers.trojanPort:quint16(port),protocol);if(protocol=="trojan"){n.password=peers.password;n.serverName="localhost";}o.nodes={n};o.selectedNodeId=n.id;SwirlProxyEngine engine;engine.start(o);QCOMPARE(engine.status().engineKind,QString("native"));
            for(const auto &url:{QUrl("http://www.msftconnecttest.com/connecttest.txt"),QUrl("https://www.gstatic.com/generate_204")}){engine.probeNode(url);QTRY_COMPARE_WITH_TIMEOUT(engine.status().requestState,ProxyEngine::RequestState::Succeeded,15000);qInfo()<<"NATIVE_PUBLIC_INTERNET"<<protocol<<url.scheme()<<engine.status().responseCode<<"explicit local egress; independent localhost Trojan TLS listener when selected";}
            QVERIFY(engine.status().uploadTotal>0);QVERIFY(engine.status().downloadTotal>0);engine.stop();
        }
    }
    void directAndAuthenticatedSocksHttpHttps(){
        ControlledNetwork net;QVERIFY(net.start());auto o=options();o.directSession=true;SwirlProxyEngine engine;engine.start(o);QCOMPARE(engine.status().state,ProxyEngine::State::Running);QCOMPARE(engine.status().processId,QCoreApplication::applicationPid());QCOMPARE(engine.status().requestState,ProxyEngine::RequestState::NotTested);
        for(bool socks:{false,true})for(bool tls:{false,true})QCOMPARE(fetch(net.url(tls),o,socks),QByteArray("DIRECT-BYPASS"));QCOMPARE(net.a.forwarded,0);QVERIFY(engine.status().uploadTotal>0);QVERIFY(engine.status().downloadTotal>0);
        engine.stop();o.inboundUsername="fixture-user";o.inboundPassword="fixture-password";engine.start(o);for(bool socks:{false,true})for(bool tls:{false,true})QCOMPARE(fetch(net.url(tls),o,socks),QByteArray("DIRECT-BYPASS"));
        const int before=net.httpRequests;auto bad=o;bad.inboundPassword="wrong";QVERIFY(fetch(net.url(),bad).startsWith("ERROR"));QCOMPARE(net.httpRequests,before);QVERIFY(fetch(net.url(),bad,true).startsWith("ERROR"));QCOMPARE(net.httpRequests,before);
        engine.stop();QTcpServer reuse;QVERIFY(reuse.listen(QHostAddress::LocalHost,o.proxyPort));
    }
    void upstreamAuthSwitchAndNoDirectOnFailure(){
        ControlledNetwork net;QVERIFY(net.start());auto o=options();auto a=node(net.a.serverPort()),b=node(net.b.serverPort());b.username=QString::fromUtf8(net.b.username);b.password=QString::fromUtf8(net.b.password);o.nodes={a,b};o.selectedNodeId=a.id;SwirlProxyEngine engine;engine.start(o);
        for(bool tls:{false,true})QCOMPARE(fetch(net.url(tls),o),QByteArray("exit-A"));engine.selectNode(b.id);QCOMPARE(fetch(net.url(true),o,true),QByteArray("exit-B"));QVERIFY(net.a.forwarded>=2);QVERIFY(net.b.forwarded>=1);
        const auto requests=net.httpRequests;net.b.reject=true;QVERIFY(fetch(net.url(),o).startsWith("ERROR"));QCOMPARE(net.httpRequests,requests);net.b.reject=false;
        QTemporaryDir temp;TelemetryService telemetry(temp.filePath("history.json"),false);connect(&engine,&ProxyEngine::statusChanged,&telemetry,[&]{telemetry.ingest(engine.status());});
        engine.probeNode(net.url());QTRY_COMPARE_WITH_TIMEOUT(engine.status().requestState,ProxyEngine::RequestState::Succeeded,8000);QVERIFY(engine.status().downloadTotal>0);engine.refresh();QVERIFY(!telemetry.connections().isEmpty());engine.stop();
    }
    void httpUpstreamUsesConnectAndAuthentication(){
        ControlledNetwork net;QVERIFY(net.start());auto peerOptions=options();peerOptions.directSession=true;peerOptions.inboundUsername="http-user";peerOptions.inboundPassword="http-password";SwirlProxyEngine peer;peer.start(peerOptions);
        auto o=options();auto n=node(peerOptions.proxyPort,"http");n.username=peerOptions.inboundUsername;n.password=peerOptions.inboundPassword;o.nodes={n};o.selectedNodeId=n.id;SwirlProxyEngine engine;engine.start(o);
        for(bool tls:{false,true})QCOMPARE(fetch(net.url(tls),o),QByteArray("DIRECT-BYPASS"));QVERIFY(peer.status().uploadTotal>0);engine.stop();n.password="wrong";o.nodes={n};engine.start(o);const int before=net.httpRequests;QVERIFY(fetch(net.url(),o).startsWith("ERROR"));QCOMPARE(net.httpRequests,before);engine.stop();peer.stop();
    }
    void nativeTrojanInteroperatesWithPinnedIndependentServer(){
        ControlledNetwork net;QVERIFY(net.start());ControlledProtocolPeers peers;QVERIFY2(peers.start(net),qPrintable(peers.failure));auto o=options();auto n=node(peers.trojanPort,"trojan");n.password=peers.password;n.serverName="localhost";o.nodes={n};o.selectedNodeId=n.id;SwirlProxyEngine engine;engine.start(o);
        QCOMPARE(engine.status().engineKind,QString("native"));for(bool socks:{false,true})for(bool tls:{false,true})QCOMPARE(fetch(net.url(tls),o,socks),QByteArray("exit-A"));QVERIFY(net.a.forwarded>=4);engine.stop();
        n.serverName="invalid.fixture.test";o.nodes={n};engine.start(o);const int before=net.httpRequests;QVERIFY(fetch(net.url(),o).startsWith("ERROR"));QCOMPARE(net.httpRequests,before);engine.stop();
    }
    void fragmentedHandshakeRejectsMalformedAndUnsupportedCommands(){
        auto o=options();o.directSession=true;SwirlProxyEngine engine;engine.start(o);QTcpSocket s;s.setProxy(QNetworkProxy::NoProxy);s.connectToHost(QHostAddress::LocalHost,o.proxyPort);QTRY_COMPARE(s.state(),QAbstractSocket::ConnectedState);
        s.write(QByteArray::fromHex("05"));QTest::qWait(30);QCOMPARE(s.bytesAvailable(),0);QCOMPARE(exchange(s,QByteArray::fromHex("0100"),2),QByteArray::fromHex("0500"));
        const auto rejection=exchange(s,QByteArray::fromHex("050300017f0000010050"),10);QCOMPARE(rejection.size(),10);QCOMPARE(quint8(rejection[1]),quint8(7));s.abort();
        QTcpSocket http;http.setProxy(QNetworkProxy::NoProxy);http.connectToHost(QHostAddress::LocalHost,o.proxyPort);QTRY_COMPARE(http.state(),QAbstractSocket::ConnectedState);QVERIFY(exchange(http,"GET http://127.0.0.1:80/ HTTP/1.1\r\nHost: localhost\r\nContent-Length: 1\r\nContent-Length: 2\r\n\r\n").startsWith("HTTP/1.1 400"));engine.stop();
    }
    void deadlinesCancellationAndPortConflict(){
        QTcpServer blackhole;QVERIFY(blackhole.listen(QHostAddress::LocalHost,0));auto o=options();o.startupTimeoutMs=200;auto n=node(blackhole.serverPort());o.nodes={n};o.selectedNodeId=n.id;SwirlProxyEngine engine;engine.start(o);QVERIFY(fetch(QUrl("http://localhost:80/"),o).startsWith("ERROR"));engine.stop();
        QTcpServer occupied;QVERIFY(occupied.listen(QHostAddress::LocalHost,o.proxyPort));engine.start(o);QCOMPARE(engine.status().error,ProxyEngine::Error::PortConflict);occupied.close();engine.start(o);engine.probeNode(QUrl("http://localhost:80/"));engine.stop();QTest::qWait(300);QCOMPARE(engine.status().state,ProxyEngine::State::Stopped);QCOMPARE(engine.status().requestState,ProxyEngine::RequestState::NotTested);QVERIFY(occupied.listen(QHostAddress::LocalHost,o.proxyPort));
    }
    void capabilitySelectionAndSafeCompatibilityFallback(){
        ControlledNetwork net;QVERIFY(net.start());auto o=options();auto n=node(net.a.serverPort());o.nodes={n};o.selectedNodeId=n.id;SwirlEngineManager engine;engine.start(o);QCOMPARE(engine.status().engineKind,QString("native"));QCOMPARE(fetch(net.url(),o),QByteArray("exit-A"));engine.stop();
        o.smartRouting=true;o.routingMode="rule";QVERIFY(!SwirlProtocolRegistry::nativeSessionReason(o).isEmpty());o.smartRouting=false;
        n.parameters["udp"]=true;o.nodes={n};engine.start(o);QTRY_VERIFY_WITH_TIMEOUT(engine.status().apiHealthy,18000);QCOMPARE(engine.status().engineKind,QString("compatibility"));QCOMPARE(fetch(net.url(true),o),QByteArray("exit-A"));engine.stop();QTRY_COMPARE_WITH_TIMEOUT(engine.status().state,ProxyEngine::State::Stopped,4000);
        n.parameters={};o.nodes={n};net.a.reject=true;engine.start(o);const int before=net.httpRequests;QVERIFY(fetch(net.url(),o).startsWith("ERROR"));QTRY_COMPARE_WITH_TIMEOUT(engine.status().engineKind,QString("compatibility"),5000);QTRY_VERIFY_WITH_TIMEOUT(engine.status().apiHealthy,18000);QVERIFY(fetch(net.url(),o).startsWith("ERROR"));QCOMPARE(net.httpRequests,before);QCOMPARE(engine.status().selectedNodeId,n.id);QVERIFY(!engine.status().engineReason.isEmpty());engine.stop();QTRY_COMPARE_WITH_TIMEOUT(engine.status().state,ProxyEngine::State::Stopped,4000);
    }
    void nativeCapabilityRejectsAmbiguousTlsAndInboundFraming(){
        auto n=node(443,"http");n.parameters["tls"]="true";QVERIFY(!SwirlProtocolRegistry::nativeNodeReason(n).isEmpty());n.parameters={};n.parameters["sni"]="another.example.org";QVERIFY(!SwirlProtocolRegistry::nativeNodeReason(n).isEmpty());n.parameters={};n.parameters["alpn"]="h2";QVERIFY(!SwirlProtocolRegistry::nativeNodeReason(n).isEmpty());
        auto o=options();o.directSession=true;SwirlProxyEngine engine;engine.start(o);
        for(const auto &header:{QByteArray("Connection: content-length\r\nContent-Length: 1"),QByteArray("Content-Length: +1"),QByteArray("Transfer-Encoding: chunked"),QByteArray("Bad Header: value")}){
            QTcpSocket socket;socket.setProxy(QNetworkProxy::NoProxy);socket.connectToHost(QHostAddress::LocalHost,o.proxyPort);QTRY_COMPARE(socket.state(),QAbstractSocket::ConnectedState);const auto response=exchange(socket,"POST http://localhost:80/ HTTP/1.1\r\nHost: localhost\r\n"+header+"\r\n\r\nx");QVERIFY(response.startsWith("HTTP/1.1 400")||response.startsWith("HTTP/1.1 501"));
        }engine.stop();
    }
    void compatibilityRetainsInboundAuthentication(){
        ControlledNetwork net;QVERIFY(net.start());auto o=options();auto n=node(net.a.serverPort());n.parameters["udp"]=true;o.nodes={n};o.selectedNodeId=n.id;o.inboundUsername="required-local-user";o.inboundPassword="required-local-password";SwirlEngineManager engine;engine.start(o);QTRY_VERIFY_WITH_TIMEOUT(engine.status().apiHealthy,18000);QCOMPARE(engine.status().engineKind,QString("compatibility"));const int before=net.httpRequests;auto unauthenticated=o;unauthenticated.inboundUsername.clear();unauthenticated.inboundPassword.clear();QVERIFY(fetch(net.url(),unauthenticated).startsWith("ERROR"));QCOMPARE(net.httpRequests,before);QCOMPARE(fetch(net.url(),o),QByteArray("exit-A"));QCOMPARE(fetch(net.url(true),o,true),QByteArray("exit-A"));engine.probeNode(net.url());QTRY_COMPARE_WITH_TIMEOUT(engine.status().requestState,ProxyEngine::RequestState::Succeeded,10000);QVERIFY(!engine.configurationSummary().contains(o.inboundPassword));engine.stop();QTRY_COMPARE_WITH_TIMEOUT(engine.status().state,ProxyEngine::State::Stopped,4000);
    }
    void nativeUdpDatagramsTimeoutCancellationAndBounds(){
        for(const auto &address:{QHostAddress(QHostAddress::LocalHost),QHostAddress(QHostAddress::LocalHostIPv6)}){
            QUdpSocket peer;QVERIFY(peer.bind(address,0));connect(&peer,&QUdpSocket::readyRead,&peer,[&]{while(peer.hasPendingDatagrams()){auto d=peer.receiveDatagram();peer.writeDatagram(d.data(),d.senderAddress(),d.senderPort());}});
            SwirlUdpExchange exchange;QSignalSpy done(&exchange,&SwirlUdpExchange::finished);const QByteArray payload(8192,'u');QVERIFY(exchange.start(address,peer.localPort(),payload));QVERIFY(!exchange.start(address,peer.localPort(),payload));QTRY_COMPARE_WITH_TIMEOUT(done.size(),1,4000);QCOMPARE(done.first()[0].toByteArray(),payload);QCOMPARE(done.first()[1].toString(),QString());QCOMPARE(exchange.sentBytes(),qint64(payload.size()));QCOMPARE(exchange.receivedBytes(),qint64(payload.size()));QVERIFY(!exchange.busy());
        }
        QUdpSocket blackhole;QVERIFY(blackhole.bind(QHostAddress::LocalHost,0));SwirlUdpExchange exchange;QSignalSpy done(&exchange,&SwirlUdpExchange::finished);QVERIFY(!exchange.start(QHostAddress::LocalHost,blackhole.localPort(),QByteArray(65508,'x')));QVERIFY(exchange.start(QHostAddress::LocalHost,blackhole.localPort(),"timeout",100));QTRY_COMPARE_WITH_TIMEOUT(done.size(),1,2000);QCOMPARE(done.first()[1].toString(),QString("UdpTimeout"));QVERIFY(exchange.start(QHostAddress::LocalHost,blackhole.localPort(),"cancel"));exchange.cancel();QCOMPARE(done.size(),2);QCOMPARE(done.last()[1].toString(),QString("UdpCancelled"));QVERIFY(!exchange.busy());
    }
    void boundedStreamingPreservesLargeUploadDownloadAndFinalAccounting(){
        ControlledNetwork net;QVERIFY(net.start());QTcpServer origin;QVERIFY(origin.listen(QHostAddress::LocalHost,0));net.a.targetPorts.append(origin.serverPort());const QByteArray payload(1024*1024,'s'),download(2*1024*1024,'d');
        connect(&origin,&QTcpServer::newConnection,&origin,[&]{while(origin.hasPendingConnections()){auto socket=origin.nextPendingConnection();connect(socket,&QTcpSocket::disconnected,socket,&QObject::deleteLater);connect(socket,&QTcpSocket::readyRead,socket,[&,socket]{if(socket->property("replied").toBool())return;auto data=socket->property("request").toByteArray()+socket->readAll();socket->setProperty("request",data);const int end=data.indexOf("\r\n\r\n");if(end<0)return;const bool post=data.startsWith("POST ");if(post&&data.size()<end+4+payload.size())return;socket->setProperty("replied",true);const auto body=post?QCryptographicHash::hash(data.mid(end+4),QCryptographicHash::Sha256).toHex():download;socket->write("HTTP/1.1 200 OK\r\nContent-Length: "+QByteArray::number(body.size())+"\r\nConnection: close\r\n\r\n"+body);socket->disconnectFromHost();});}});
        auto o=options();auto n=node(net.a.serverPort());o.nodes={n};o.selectedNodeId=n.id;SwirlProxyEngine engine;engine.start(o);QTemporaryDir temp;TelemetryService telemetry(temp.filePath("history.json"),false);connect(&engine,&ProxyEngine::statusChanged,&telemetry,[&]{telemetry.ingest(engine.status());});
        QNetworkAccessManager client;client.setProxy(QNetworkProxy(QNetworkProxy::HttpProxy,"127.0.0.1",o.proxyPort));const QUrl url(QString("http://127.0.0.1:%1/large").arg(origin.serverPort()));QNetworkRequest request(url);request.setRawHeader("Connection","close");auto upload=client.post(request,payload);QTRY_VERIFY_WITH_TIMEOUT(upload->isFinished(),10000);QCOMPARE(upload->error(),QNetworkReply::NoError);QCOMPARE(upload->readAll(),QCryptographicHash::hash(payload,QCryptographicHash::Sha256).toHex());
        QCOMPARE(fetch(url,o),download);QTRY_VERIFY_WITH_TIMEOUT(engine.status().uploadTotal>=payload.size()&&engine.status().downloadTotal>=download.size(),4000);
        // The engine publishes completed connections on its next 250ms poll.
        // An old idle snapshot after the first request is not final accounting.
        QTRY_VERIFY_WITH_TIMEOUT(telemetry.activeConnections()==0&&telemetry.connections().size()>=2,4000);
        const auto accounted=[&]{qint64 total=0;for(const auto &row:telemetry.connections())total+=row.toMap().value("downloadBytes").toLongLong();return total;};
        QTRY_COMPARE_WITH_TIMEOUT(accounted(),engine.status().downloadTotal,4000);engine.stop();
    }
};
QTEST_GUILESS_MAIN(NativeEngineTests)
#include "NativeEngineTests.moc"
