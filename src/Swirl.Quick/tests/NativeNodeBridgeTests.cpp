#include <QtTest>
#include <QJsonArray>
#include <QJsonDocument>
#include <QNetworkAccessManager>
#include <QNetworkProxy>
#include <QNetworkReply>
#include <QTcpServer>
#include "ControlledNetwork.h"
#include "engine/NativeNodeBridge.h"
#include "engine/NodeImporter.h"
#include "engine/RustCoreEngine.h"

namespace {
const QString Id = QStringLiteral("00112233-4455-6677-8899-aabbccddeeff");
QByteArray vmessUri(QJsonObject value) {
    return "vmess://" + QJsonDocument(value).toJson(QJsonDocument::Compact).toBase64();
}
QJsonObject vmess() {
    return {{"v","2"},{"ps","VMess fixture"},{"add","127.0.0.1"},{"port","443"},
        {"id",Id},{"aid","0"},{"scy","auto"},{"net","tcp"}};
}
QByteArray clash(QJsonObject raw) {
    return QJsonDocument(QJsonObject{{"proxies",QJsonArray{raw}}}).toJson(QJsonDocument::Compact);
}
EngineStartOptions options(const QList<ProxyNode> &nodes,quint16 port) {
    EngineStartOptions result; result.nodes=nodes; result.selectedNodeId=nodes.first().id;
    result.proxyPort=port; result.routingMode="global"; return result;
}
}

class NativeNodeBridgeTests final:public QObject {
    Q_OBJECT
private slots:
    void uriAndClashCandidates_data() {
        QTest::addColumn<QByteArray>("source"); QTest::addColumn<QString>("kind");
        QTest::newRow("vmess-uri")<<vmessUri(vmess())<<QString("vmess");
        auto ws=vmess(); ws["net"]="ws"; ws["tls"]="tls"; ws["sni"]="tls.invalid";
        ws["path"]="/fixture"; ws["host"]="front.invalid"; ws["alpn"]="http/1.1";
        QTest::newRow("vmess-ws-uri")<<vmessUri(ws)<<QString("vmess");
        QTest::newRow("hysteria2-uri")<<QByteArray("hysteria2://synthetic-user:synthetic-password@127.0.0.1:443?sni=quic.invalid&alpn=h3&obfs=salamander&obfs-password=synthetic-obfs&up=20&down=80#hy2")<<QString("hysteria2");
        QTest::newRow("tuic-uri")<<("tuic://"+Id.toUtf8()+":synthetic-password@127.0.0.1:443?sni=quic.invalid&alpn=h3&udp_relay_mode=quic&congestion_control=bbr#tuic")<<QString("tuic");
        QTest::newRow("vless-udp-uri")<<("vless://"+Id.toUtf8()+"@127.0.0.1:443?security=none&udp=1#vless")<<QString("vless");
        QTest::newRow("trojan-udp-uri")<<QByteArray("trojan://synthetic-password@127.0.0.1:443?sni=tls.invalid&udp=1#trojan")<<QString("trojan");
        QTest::newRow("vless-grpc-uri")<<("vless://"+Id.toUtf8()+"@127.0.0.1:443?security=tls&sni=tls.invalid&type=grpc&serviceName=fixture&alpn=h2#grpc")<<QString("vless");
        QTest::newRow("vless-http2-uri")<<("vless://"+Id.toUtf8()+"@127.0.0.1:443?security=tls&sni=tls.invalid&type=h2&host=front.invalid&path=%2Ffixture&alpn=h2#h2")<<QString("vless");
        QTest::newRow("vless-httpupgrade-uri")<<("vless://"+Id.toUtf8()+"@127.0.0.1:443?security=tls&sni=tls.invalid&type=httpupgrade&host=front.invalid&path=%2Ffixture#upgrade")<<QString("vless");
        QTest::newRow("vmess-clash")<<clash({{"name","vmess"},{"type","vmess"},{"server","127.0.0.1"},{"port",443},{"uuid",Id},{"alterId",0},{"cipher","aes-128-gcm"}})<<QString("vmess");
        QTest::newRow("hysteria2-clash-yaml")<<QByteArray("proxies:\n  - name: hy2\n    type: hysteria2\n    server: 127.0.0.1\n    port: 443\n    password: synthetic-password\n    sni: quic.invalid\n    udp: false\n")<<QString("hysteria2");
        QTest::newRow("tuic-clash")<<clash({{"name","tuic"},{"type","tuic"},{"server","127.0.0.1"},{"port",443},{"uuid",Id},{"password","synthetic-password"},{"alpn",QJsonArray{"h3"}}})<<QString("tuic");
        QTest::newRow("vless-xhttp-clash")<<clash({{"name","xhttp"},{"type","vless"},{"server","127.0.0.1"},{"port",443},{"uuid",Id},{"tls",true},{"sni","tls.invalid"},{"network","xhttp"},
            {"xhttp-opts",QJsonObject{{"mode","stream-one"},{"host","front.invalid"},{"path","/fixture"}}}})<<QString("vless");
    }

    void uriAndClashCandidates() {
        QFETCH(QByteArray,source); QFETCH(QString,kind);
        const auto parsed=NodeImporter::parse(source); QVERIFY2(parsed,qPrintable(parsed.error)); QCOMPARE(parsed.nodes.size(),1);
        const auto &node=parsed.nodes.first(); const auto original=node.originalConfiguration;
        QJsonObject outbound; const auto failure=NativeNodeBridge::executableOutbound(node,&outbound);
        QVERIFY2(failure.isEmpty(),qPrintable(failure)); QCOMPARE(outbound.value("type").toString(),kind);
        QVERIFY(node.originalConfiguration==original); QVERIFY(!original.isEmpty());
        if(kind=="vless"||kind=="vmess"||kind=="tuic")QVERIFY(outbound.value("uuid")==QJsonValue(Id));
        if(kind=="hysteria2"&&source.startsWith("hysteria2:")){
            QVERIFY(outbound.value("password")==QJsonValue("synthetic-user:synthetic-password"));
            QCOMPARE(outbound.value("up_mbps").toInt(),20); QCOMPARE(outbound.value("down_mbps").toInt(),80);
        }
        QTcpServer available; QVERIFY(available.listen(QHostAddress::LocalHost)); const auto port=available.serverPort(); available.close();
        const auto startOptions=options(parsed.nodes,port); QJsonObject config;
        QVERIFY2(RustCoreEngine::configuration(startOptions,&config).isEmpty(),"Native candidate must enter the product configuration");
        QVERIFY(config.value("nodes").toArray().first().toObject().value("outbound").toObject()==outbound);
        RustCoreEngine engine; engine.start(startOptions);
        QTRY_VERIFY_WITH_TIMEOUT(engine.status().apiHealthy,5000);
        QCOMPARE(engine.status().engineKind,QString("rust"));
        // Listener startup is level 2 evidence; no request to the synthetic
        // remote endpoint is made or reported as protocol interoperability.
        engine.stop(); QTRY_VERIFY_WITH_TIMEOUT(!engine.status().processAlive,5000);
        QVERIFY(available.listen(QHostAddress::LocalHost,port));
    }

    void malformedSourceScalarsAndAliasesNeverBecomeExecutableDefaults() {
        const QList<QPair<QString,QJsonValue>> malformed{{"aid",true},{"aid",1.5},{"aid","not-a-number"},{"v",3},{"scy",false},{"tls",QJsonObject{}},{"tls","reality"},{"sni",QJsonValue::Null},{"alpn",QJsonArray{"h2"}}};
        for(const auto &entry:malformed){auto raw=vmess();raw[entry.first]=entry.second;const auto result=NodeImporter::parse(vmessUri(raw));QVERIFY(!result);}
        const QList<QByteArray> malformedUris{
            "hy2://synthetic-password@127.0.0.1:443?sni=one.invalid&peer=two.invalid",
            "hy2://bad%ZZ@127.0.0.1:443",
            "hy2://bad%FF@127.0.0.1:443",
            "tuic://"+Id.toUtf8()+":synthetic-password@127.0.0.1:443/not-defined?alpn=h3",
            "tuic://"+Id.toUtf8()+":synthetic-password@127.0.0.1:443?alpn=h3&congestion_control=bbr&congestion-control=cubic",
            "tuic://"+Id.toUtf8()+":synthetic-password@127.0.0.1:443?alpn=h3&allow_insecure=true&insecure=false"};
        for(const auto &source:malformedUris)QVERIFY(!NodeImporter::parse(source));
    }

    void retainedUnmappedAndConflictingParametersBlockActivation() {
        const QList<QByteArray> sources{
            "vless://"+Id.toUtf8()+"@127.0.0.1:443?security=tls&sni=tls.invalid&type=grpc&host=authority.invalid&serviceName=fixture#authority",
            "hy2://synthetic-password@127.0.0.1:443?alpn=h3,,#alpn",
            "tuic://"+Id.toUtf8()+":synthetic-password@127.0.0.1:443?alpn=h3,#alpn",
            clash({{"name","vmess"},{"type","vmess"},{"server","127.0.0.1"},{"port",443},{"uuid",Id},{"future-option",true}}),
            clash({{"name","hy2"},{"type","hysteria2"},{"server","127.0.0.1"},{"port",443},{"password","synthetic-password"},{"insecure",true}})};
        for(const auto &source:sources){
            const auto result=NodeImporter::parse(source); QVERIFY2(result,qPrintable(result.error));
            QJsonObject output; QVERIFY(!NativeNodeBridge::executableOutbound(result.nodes.first(),&output).isEmpty()); QVERIFY(output.isEmpty());
        }
        auto result=NodeImporter::parse("http://127.0.0.1:8080#http"); QVERIFY(result);
        auto node=result.nodes.first(); node.parameters["password"]="hidden-override";
        QJsonObject output; QVERIFY(!NativeNodeBridge::executableOutbound(node,&output).isEmpty());
        node=result.nodes.first(); node.parameters["sni"]="hidden.invalid";
        QVERIFY(!NativeNodeBridge::executableOutbound(node,&output).isEmpty());
    }

    void importedSocksNodesCarryRealTrafficSwitchAndRejectWrongCredentials() {
        ControlledNetwork network; QVERIFY(network.start());
        const auto a="socks5://127.0.0.1:"+QByteArray::number(network.a.serverPort())+"#fixture-A";
        const auto b="socks5://test-user:fixture-secret-only@127.0.0.1:"+QByteArray::number(network.b.serverPort())+"#fixture-B";
        auto imported=NodeImporter::parse(a+'\n'+b); QVERIFY2(imported,qPrintable(imported.error)); QCOMPARE(imported.nodes.size(),2);
        QTcpServer available; QVERIFY(available.listen(QHostAddress::LocalHost)); const auto port=available.serverPort(); available.close();
        RustCoreEngine engine; engine.start(options(imported.nodes,port)); QTRY_VERIFY_WITH_TIMEOUT(engine.status().apiHealthy,5000);
        QNetworkAccessManager client; client.setProxy(QNetworkProxy(QNetworkProxy::HttpProxy,"127.0.0.1",port));
        for(int index=0;index<2;++index){
            if(index)engine.selectNode(imported.nodes[index].id);
            QTRY_COMPARE_WITH_TIMEOUT(engine.status().selectedNodeId,imported.nodes[index].id,5000);
            QNetworkRequest request(network.url()); request.setAttribute(QNetworkRequest::Http2AllowedAttribute,false); request.setTransferTimeout(5000);
            auto *reply=client.get(request); QTRY_VERIFY_WITH_TIMEOUT(reply->isFinished(),6000);
            QCOMPARE(reply->error(),QNetworkReply::NoError); QCOMPARE(reply->readAll(),index?QByteArray("exit-B"):QByteArray("exit-A")); reply->deleteLater();
        }
        QCOMPARE(network.a.forwarded,1); QCOMPARE(network.b.forwarded,1); QCOMPARE(network.httpRequestsByExit.value("DIRECT-BYPASS"),0);
        engine.stop(); QTRY_VERIFY_WITH_TIMEOUT(!engine.status().processAlive,5000);
        imported.nodes[1].password="synthetic-wrong-password";
        auto bad=options(imported.nodes,port); bad.selectedNodeId=imported.nodes[1].id; engine.start(bad);
        QTRY_VERIFY_WITH_TIMEOUT(engine.status().apiHealthy,5000);
        QNetworkRequest request(network.url()); request.setTransferTimeout(5000);
        auto *reply=client.get(request); QTRY_VERIFY_WITH_TIMEOUT(reply->isFinished(),6000);
        QVERIFY(reply->error()!=QNetworkReply::NoError); QCOMPARE(network.b.forwarded,1); QCOMPARE(network.httpRequestsByExit.value("DIRECT-BYPASS"),0);
        engine.stop(); QTRY_VERIFY_WITH_TIMEOUT(!engine.status().processAlive,5000); QVERIFY(available.listen(QHostAddress::LocalHost,port));
    }
};

QTEST_GUILESS_MAIN(NativeNodeBridgeTests)
#include "NativeNodeBridgeTests.moc"
