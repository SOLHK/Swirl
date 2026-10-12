#include "engine/MihomoAdapter.h"
#include "engine/NodeStore.h"
#include "ControlledNetwork.h"
#include <QCoreApplication>
#include <QJsonDocument>
#include <QJsonObject>
#include <QNetworkAccessManager>
#include <QNetworkProxy>
#include <QNetworkReply>
#include <QSignalSpy>
#include <QTemporaryDir>
#include <QTest>
#include <QUuid>

static quint16 freePort(){QTcpServer server;server.listen(QHostAddress::LocalHost,0);return server.serverPort();}
static ProxyNode node(QString name,quint16 port){ProxyNode n;n.id=QUuid::createUuid().toString(QUuid::WithoutBraces);n.name=name;n.protocol="socks5";n.host="127.0.0.1";n.port=port;return n;}
class NodeTests:public QObject {
    Q_OBJECT
    EngineStartOptions options() {
        QFile file(QString::fromUtf8(SWIRL_TEST_MANIFEST));if(!file.open(QIODevice::ReadOnly))return {};const auto m=QJsonDocument::fromJson(file.readAll()).object();
        EngineStartOptions options;options.executablePath=QCoreApplication::applicationDirPath()+"/core/mihomo.exe";
        options.expectedSha256=m.value("executableSha256").toString().toLatin1();options.expectedVersion=m.value("version").toString();
        options.controlPort=freePort();options.proxyPort=freePort();options.startupTimeoutMs=15000;options.healthIntervalMs=500;return options;
    }
    QByteArray fetch(ControlledNetwork &net,quint16 proxyPort,bool tls=false) {
        QNetworkAccessManager client;client.setProxy(QNetworkProxy(QNetworkProxy::HttpProxy,"127.0.0.1",proxyPort));
        QNetworkRequest request(net.url(tls));request.setAttribute(QNetworkRequest::Http2AllowedAttribute,false);request.setRawHeader("Connection","close");
        if(tls){auto ssl=QSslConfiguration::defaultConfiguration();ssl.addCaCertificate(net.certificate);request.setSslConfiguration(ssl);}
        auto *reply=client.get(request);QSignalSpy done(reply,&QNetworkReply::finished);
        if(!done.wait(8000)){qInfo()<<"FIXTURE_TIMEOUT relays"<<net.a.forwarded<<net.b.forwarded<<"origins"<<net.httpRequests<<net.httpsRequests<<"sslBackend"<<QSslSocket::activeBackend();reply->abort();return "REQUEST_TIMEOUT";}
        const auto body=reply->readAll();const int code=reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();
        if(reply->error()!=QNetworkReply::NoError || code!=200){qInfo()<<"FIXTURE_REQUEST_FAILURE HTTP"<<code<<"relays"<<net.a.forwarded<<net.b.forwarded<<"origins"<<net.httpRequests<<net.httpsRequests;return QByteArray("REQUEST_ERROR_")+QByteArray::number(reply->error());}
        return body;
    }
private slots:
    void oversizedStorePreservesPreviousFile() {
        QTemporaryDir temp;const auto path=temp.filePath("nodes.dat");NodeStore store(path);
        auto n=node("large",1080);n.protocol="ss";n.cipher="aes-128-gcm";n.password=QString(4096,QChar(1));
        auto input=n.publicInfo();input.remove("id");input.insert("password",n.password);
        QByteArray previous;int accepted=0;
        for(int i=0;i<100;++i) {
            if(!store.saveNode(input))break;
            ++accepted;QFile file(path);QVERIFY(file.open(QIODevice::ReadOnly));previous=file.readAll();
        }
        QVERIFY(accepted>0 && accepted<100);QVERIFY(previous.size()<=1024*1024);
        QFile file(path);QVERIFY(file.open(QIODevice::ReadOnly));QCOMPARE(file.readAll(),previous);
        NodeStore reloaded(path);QCOMPARE(reloaded.nodes().size(),accepted);QVERIFY(reloaded.error().isEmpty());
    }
    void encryptedPersistence() {
        QTemporaryDir temp;QVERIFY(temp.isValid());const auto path=temp.filePath("nodes.dat");
        NodeStore store(path);
        auto n=node("保存的节点",1080);n.username="test-user";n.password="fixture-private-secret";
        auto input=n.publicInfo();input.remove("id");input.insert("username",n.username);input.insert("password",n.password);
        QVERIFY(store.saveNode(input));QCOMPARE(store.nodes().size(),1);const auto id=store.nodes().first().id;
        QFile encrypted(path);QVERIFY(encrypted.open(QIODevice::ReadOnly));const auto bytes=encrypted.readAll();encrypted.close();
        QVERIFY(!bytes.contains(n.password.toUtf8()));QVERIFY(!bytes.contains(n.username.toUtf8()));QVERIFY(!bytes.contains(n.name.toUtf8()));
        QVERIFY(!store.publicRows().first().toMap().contains("password"));QVERIFY(!store.publicRows().first().toMap().contains("username"));
        QVERIFY(store.select(id));NodeStore loaded(path);QCOMPARE(loaded.selectedId(),id);QCOMPARE(loaded.nodes().first().password,n.password);
        auto edit=loaded.publicRows().first().toMap();edit.insert("name","修改后的节点");QVERIFY(loaded.saveNode(edit));QCOMPARE(loaded.nodes().first().password,n.password);
        NodeStore reloaded(path);QCOMPARE(reloaded.nodes().first().name,QString("修改后的节点"));QVERIFY(reloaded.removeNode(id));QVERIFY(reloaded.nodes().isEmpty());
        QVERIFY(encrypted.open(QIODevice::WriteOnly));encrypted.write("SWIRLNODE1\ncorrupted");encrypted.close();
        NodeStore corrupted(path);QVERIFY(!corrupted.error().isEmpty());QVERIFY(!corrupted.saveNode(input));
        QVERIFY(encrypted.open(QIODevice::ReadOnly));QCOMPARE(encrypted.readAll(),QByteArray("SWIRLNODE1\ncorrupted"));
    }
    void invalidParameters() {
        auto n=node("valid",1080);QVERIFY(ProxyNode::validate(n).isEmpty());
        n.host="http://user:secret@host";QVERIFY(!ProxyNode::validate(n).isEmpty());n.host="127.0.0.1";
        n.port=0;QVERIFY(!ProxyNode::validate(n).isEmpty());n.port=1080;
        n.protocol="vless";QVERIFY(!ProxyNode::validate(n).isEmpty());n.protocol="socks5";
        n.username="user";QVERIFY(!ProxyNode::validate(n).isEmpty());n.password="secret";QVERIFY(ProxyNode::validate(n).isEmpty());
        n.protocol="ss";n.cipher="invalid";QVERIFY(!ProxyNode::validate(n).isEmpty());n.cipher="aes-128-gcm";QVERIFY(ProxyNode::validate(n).isEmpty());
        n.protocol="trojan";n.serverName="bad server";QVERIFY(!ProxyNode::validate(n).isEmpty());
    }
    void realHttpHttpsAndSwitch() {
        ControlledNetwork net;QVERIFY(net.start());auto config=options();
        auto a=node("A",net.a.serverPort()),b=node("B",net.b.serverPort());b.username=QString::fromUtf8(net.b.username);b.password=QString::fromUtf8(net.b.password);
        config.nodes={a,b};config.selectedNodeId=a.id;
        MihomoAdapter engine;engine.start(config);
        QTRY_COMPARE_WITH_TIMEOUT(engine.status().state,ProxyEngine::State::Running,16000);
        QCOMPARE(engine.status().nodeHealth,ProxyEngine::NodeHealth::Unknown);QCOMPARE(engine.status().requestState,ProxyEngine::RequestState::NotTested);
        QVERIFY(!engine.configurationSummary().contains(b.password));QCOMPARE(fetch(net,config.proxyPort),QByteArray("exit-A"));
        QCOMPARE(fetch(net,config.proxyPort,true),QByteArray("exit-A"));QVERIFY(net.a.forwarded>=2);QCOMPARE(net.b.forwarded,0);QVERIFY(net.httpsRequests>0);
        engine.probeNode(net.url());QTRY_VERIFY_WITH_TIMEOUT(!engine.status().nodeBusy,8000);
        QCOMPARE(engine.status().nodeHealth,ProxyEngine::NodeHealth::Available);QCOMPARE(engine.status().requestState,ProxyEngine::RequestState::Succeeded);
        const auto pid=engine.status().processId;
        for(int i=0;i<6;++i){const bool toB=i%2==0;const auto id=toB?b.id:a.id;engine.selectNode(id);
            QTRY_VERIFY_WITH_TIMEOUT(!engine.status().nodeBusy,5000);QCOMPARE(engine.status().selectedNodeId,id);QCOMPARE(engine.status().processId,pid);
            QCOMPARE(engine.status().requestState,ProxyEngine::RequestState::NotTested);
            QCOMPARE(fetch(net,config.proxyPort,i%2==0),toB?QByteArray("exit-B"):QByteArray("exit-A"));}
        QVERIFY(net.b.forwarded>=3);QVERIFY(net.httpRequests>0);
        net.a.reject=true;engine.probeNode(net.url());QTRY_VERIFY_WITH_TIMEOUT(!engine.status().nodeBusy,8000);
        QCOMPARE(engine.status().nodeHealth,ProxyEngine::NodeHealth::Unavailable);QCOMPARE(engine.status().requestState,ProxyEngine::RequestState::NotTested);
        QVERIFY(engine.status().processAlive);QVERIFY(engine.status().apiHealthy);
        net.a.reject=false;engine.probeNode(net.url());QTRY_VERIFY_WITH_TIMEOUT(!engine.status().nodeBusy,8000);
        QCOMPARE(engine.status().requestState,ProxyEngine::RequestState::Succeeded);
        engine.stop();QTRY_COMPARE_WITH_TIMEOUT(engine.status().state,ProxyEngine::State::Stopped,4000);
        QTcpServer reuse;QVERIFY(reuse.listen(QHostAddress::LocalHost,config.proxyPort));reuse.close();
        for(int i=0;i<3;++i){engine.start(config);QTRY_COMPARE_WITH_TIMEOUT(engine.status().state,ProxyEngine::State::Running,16000);
            QCOMPARE(fetch(net,config.proxyPort),QByteArray("exit-A"));engine.stop();QTRY_COMPARE_WITH_TIMEOUT(engine.status().state,ProxyEngine::State::Stopped,4000);}
        qInfo()<<"CONTROLLED_CHAIN HTTP HTTPS exit-A/exit-B verified;"<<net.a.forwarded<<"A relays,"<<net.b.forwarded<<"B relays; no remote environment claimed";
    }
    void protocolConfigurationAndPortConflict() {
        auto config=options();QTcpServer occupied;QVERIFY(occupied.listen(QHostAddress::LocalHost,0));
        auto n=node("S",1080);config.nodes={n};config.selectedNodeId=n.id;config.proxyPort=occupied.serverPort();
        MihomoAdapter engine;engine.start(config);QCOMPARE(engine.status().error,ProxyEngine::Error::PortConflict);QVERIFY(!engine.status().processAlive);
        for(const auto &protocol: {QString("ss"),QString("trojan")}){
            config.proxyPort=freePort();n.protocol=protocol;n.password="fixture-secret-'\\\n";n.cipher="aes-128-gcm";n.serverName="localhost";config.nodes={n};
            engine.start(config);QTRY_COMPARE_WITH_TIMEOUT(engine.status().state,ProxyEngine::State::Running,16000);
            QVERIFY(!engine.configurationSummary().contains("fixture-secret"));
            engine.stop();QTRY_COMPARE_WITH_TIMEOUT(engine.status().state,ProxyEngine::State::Stopped,4000);
        }
    }
};
QTEST_GUILESS_MAIN(NodeTests)
#include "NodeTests.moc"
