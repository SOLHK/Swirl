#include <QtTest>
#include <QFile>
#include <QClipboard>
#include <QJsonArray>
#include <QJsonDocument>
#include <QSignalSpy>
#include <QTemporaryDir>
#include "engine/NodeImportService.h"
#include "engine/XrayJsonBridge.h"

namespace {
QJsonObject vless(QString name = QStringLiteral("测试节点 🇸🇬")) {
    return {{"protocol", "vless"}, {"tag", name}, {"settings", QJsonObject{
        {"address", "example.invalid"}, {"port", 443},
        {"id", "11111111-2222-4333-8444-555555555555"}, {"encryption", "none"}}}};
}
QByteArray json(const QJsonObject &object) { return QJsonDocument(object).toJson(QJsonDocument::Compact); }
bool write(const QString &path, const QByteArray &bytes) {
    QFile file(path); return file.open(QIODevice::WriteOnly) && file.write(bytes) == bytes.size();
}
}

class XrayImportTests final : public QObject {
    Q_OBJECT
private slots:
    void strictEnvelopes() {
        const auto single = NodeImporter::parse(json(vless()));
        QVERIFY2(single, qPrintable(single.error));
        QCOMPARE(single.nodes.size(), 1);
        QCOMPARE(single.nodes.first().protocol, QStringLiteral("vless"));
        QCOMPARE(single.nodes.first().name, QStringLiteral("测试节点 🇸🇬"));
        const auto input = json(QJsonObject{{"inbounds", QJsonArray{QJsonObject{
            {"protocol", "socks"}, {"listen", "0.0.0.0"}, {"port", 45678}, {"settings", QJsonObject{}}}}},
            {"outbounds", QJsonArray{vless("one"), vless("two")}}, {"log", QJsonObject{{"loglevel", "debug"}}}});
        const auto full = NodeImporter::parse(input);
        QVERIFY2(full, qPrintable(full.error));
        QCOMPARE(full.nodes.size(), 2);
        QVERIFY(full.configuration.isEmpty());
        QVERIFY(full.executionConfiguration.isEmpty());
        QCOMPARE(full.nodes.first().sourceDocument, input);
        const auto array = NodeImporter::parse(QJsonDocument(QJsonArray{vless(), vless("second")}).toJson());
        QVERIFY2(array, qPrintable(array.error));
        QCOMPARE(array.nodes.size(), 2);
        const auto legacy = NodeImporter::parse(json(QJsonObject{{"outbound", vless()}, {"outboundDetour", QJsonArray{vless("second")}}}));
        QVERIFY2(legacy, qPrintable(legacy.error));
        QCOMPARE(legacy.nodes.size(), 2);
    }
    void duplicateKeysCannotBeNormalizedAway() {
        for (const auto &input : QList<QByteArray>{
            R"({"protocol":"vless","protocol":"vmess","settings":{}})",
            R"({"protocol":"vless","settings":{"id":"SYNTHETIC_SECRET","\u0069d":"other"}})",
            R"({"outbounds":[{"protocol":"vless","settings":{}}],"outbounds":[]})"}) {
            const auto result = NodeImporter::parse(input);
            QVERIFY(!result);
            QVERIFY(result.error.contains("DuplicateJsonKey"));
            QVERIFY(!result.error.contains("SYNTHETIC_SECRET"));
            QVERIFY(result.nodes.isEmpty());
        }
    }
    void parserIsSharedForWrappedJsonAndIndentedJson() {
        auto vmess = vless();vmess["protocol"] = "vmess";
        const auto wrapped = NodeImporter::parse(json(QJsonObject{{"outbounds", QJsonArray{vmess}}}).toBase64());
        QVERIFY2(wrapped, qPrintable(wrapped.error));
        QCOMPARE(wrapped.nodes.first().protocol, QStringLiteral("vmess"));
        const auto indented = NodeImporter::parse(QByteArray(500, ' ') + json(vless()));
        QVERIFY2(indented, qPrintable(indented.error));
    }
    void previewNeverReflectsCredentialNames() {
        QJsonArray outbounds{
            QJsonObject{{"protocol", "http"}, {"tag", "https://example.invalid/config?token=SYNTHETIC-TOKEN"}, {"settings", QJsonObject{{"address", "example.invalid"}, {"port", 8080}}}},
            QJsonObject{{"protocol", "unknown-protocol"}, {"tag", "SYNTHETIC-PASSWORD"}, {"settings", QJsonObject{{"password", "SYNTHETIC-PASSWORD"}}}},
            vless("SYNTHETIC-PASSWORD")};
        const auto result = NodeImporter::parse(QJsonDocument(outbounds).toJson());
        QVERIFY2(result, qPrintable(result.error));
        for (const auto &node : result.nodes) {
            const auto publicText = QJsonDocument(QJsonObject::fromVariantMap(node.publicInfo())).toJson();
            QVERIFY(!publicText.contains("SYNTHETIC-TOKEN"));
            QVERIFY(!publicText.contains("SYNTHETIC-PASSWORD"));
        }
    }
    void credentialTagsRemainRedactedAfterDisplayNormalization() {
        const auto password = QStringLiteral("  SYNTHETIC_密碼") + QChar(0) + QStringLiteral("\t🌪  ");
        const QStringList tags{password, QStringLiteral("SYNTHETIC_密碼  🌪")};
        const QJsonObject server{{"address", "proxy.invalid"}, {"port", 443}, {"password", password}};
        QJsonArray outbounds;
        for (const auto &tag : tags) {
            outbounds.append(QJsonObject{{"protocol", "trojan"}, {"tag", tag},
                {"settings", QJsonObject{{"servers", QJsonArray{server}}}}});
        }
        const auto input = json(QJsonObject{{"outbounds", outbounds}});
        const auto result = NodeImporter::parse(input);
        QVERIFY2(result, qPrintable(result.error));
        QCOMPARE(result.nodes.size(), tags.size());
        for (qsizetype index = 0; index < result.nodes.size(); ++index) {
            const auto &node = result.nodes.at(index);
            // A failed assertion must not print the credential-bearing value.
            QVERIFY(node.name == QStringLiteral("JSON 节点 %1").arg(index + 1));
            QVERIFY(node.password == password);
            QVERIFY(node.parameters.value("authentication").toObject().value("password").toString() == password);
            QVERIFY(node.sourceDocument == input);
            QVERIFY(node.originalConfiguration.value("outbound") == outbounds.at(index));
            QVERIFY(node.originalConfiguration.value("outbound").toObject().value("tag").toString() == tags.at(index));
            const auto publicText = QJsonDocument(QJsonObject::fromVariantMap(node.publicInfo())).toJson();
            QVERIFY(!publicText.contains("SYNTHETIC_"));
        }
    }
    void syntaxAndParametersAreSeparate() {
        auto invalid = vless(); auto settings = invalid.value("settings").toObject();
        settings["id"] = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"; invalid["settings"] = settings;
        const auto parameter = NodeImporter::parse(json(invalid));
        QVERIFY2(parameter, qPrintable(parameter.error));
        QCOMPARE(parameter.nodes.first().parameterState, QStringLiteral("invalid"));
        QVERIFY(!parameter.nodes.first().nativeExecutable);
        settings["port"] = 65536; invalid["settings"] = settings;
        const auto port = NodeImporter::parse(json(invalid));
        QVERIFY(!port);
        QVERIFY(!NodeImporter::parse(R"({"protocol":"vless",})"));
        QVERIFY(!NodeImporter::parse(R"({"inbounds":[{"protocol":"socks","port":1080}]})"));
    }
    void supportedTransportsDoNotBypassUnsupportedMux() {
        for (const auto &transport : {"grpc", "http", "httpupgrade", "xhttp"}) {
            auto input = vless();
            QJsonObject stream{{"network", transport}, {"security", "tls"},
                {"tlsSettings", QJsonObject{{"serverName", "tls.example.invalid"},
                    {"alpn", QJsonArray{QString(transport) == "httpupgrade" ? "http/1.1" : "h2"}}}}};
            const QString key = QString(transport) == "http" ? "httpSettings" : QString(transport) + "Settings";
            QJsonObject options{{"path", "/synthetic"}, {"host", "front.example.invalid"}};
            if (QString(transport) == "grpc") options = {{"serviceName", "synthetic-service"}};
            if (QString(transport) == "http") options["host"] = QJsonArray{"front.example.invalid"};
            if (QString(transport) == "xhttp") options["mode"] = "stream-one";
            stream[key] = options; input["streamSettings"] = stream;
            const auto supported = NodeImporter::parse(json(input));
            QVERIFY2(supported, qPrintable(supported.error));
            QVERIFY(supported.nodes.first().nativeExecutable);
            const auto nativeTransport = supported.nodes.first().nativeOutbound.value("transport").toObject();
            QCOMPARE(nativeTransport.value("type").toString(), QString(transport) == "http" ? QString("http2") : QString(transport));
            const auto nativeOptions = nativeTransport.value("config").toObject();
            if (QString(transport) == "grpc") {
                QCOMPARE(nativeOptions.value("service_name").toString(), QString("synthetic-service"));
            } else {
                QCOMPARE(nativeOptions.value("host").toString(), QString("front.example.invalid"));
                QCOMPARE(nativeOptions.value("path").toString(), QString("/synthetic"));
            }
            if (QString(transport) == "xhttp") QCOMPARE(nativeOptions.value("mode").toString(), QString("stream-one"));
            QCOMPARE(supported.nodes.first().originalConfiguration.value("outbound").toObject(), input);
            QCOMPARE(supported.nodes.first().securityType, QStringLiteral("tls"));
            QVERIFY(!supported.nodes.first().publicInfo().value("networkVerified").toBool());
            input["mux"] = QJsonObject{{"enabled", true}};
            const auto blocked = NodeImporter::parse(json(input));
            QVERIFY2(blocked, qPrintable(blocked.error));
            QVERIFY(!blocked.nodes.first().nativeExecutable); QVERIFY(blocked.nodes.first().nativeOutbound.isEmpty());
            QVERIFY(!blocked.nodes.first().runtimeIssues.isEmpty());
            QCOMPARE(blocked.nodes.first().originalConfiguration.value("outbound").toObject(), input);
            input.remove("mux"); input["protocol"] = "vmess";
            auto auth = input.value("settings").toObject(); auth.remove("encryption");
            auth["alterId"] = 0; auth["security"] = "auto"; input["settings"] = auth;
            const auto vmess = NodeImporter::parse(json(input));
            QVERIFY2(vmess, qPrintable(vmess.error));
            QVERIFY(!vmess.nodes.first().nativeExecutable); QVERIFY(vmess.nodes.first().nativeOutbound.isEmpty());
            QVERIFY(vmess.nodes.first().runtimeIssues.join(' ').contains("TransportProtocolUnsupported"));
            QCOMPARE(vmess.nodes.first().originalConfiguration.value("outbound").toObject(), input);
        }
    }
    void allSixProtocolsKeepTheirNames() {
        QJsonArray outbounds;
        for (const auto &protocol : {"vless", "vmess", "trojan", "shadowsocks", "socks", "http"}) {
            auto node = vless(QString::fromLatin1(protocol)); node["protocol"] = protocol;
            outbounds.append(node);
        }
        const auto result = NodeImporter::parse(QJsonDocument(outbounds).toJson());
        QVERIFY2(result, qPrintable(result.error));
        QStringList protocols; for (const auto &node : result.nodes) protocols.append(node.protocol);
        QCOMPARE(protocols, (QStringList{"vless", "vmess", "trojan", "ss", "socks5", "http"}));
    }
    void allSixProtocolsExposeAuthoritativeNativeCandidates() {
        const QByteArray bytes = R"JSON({"outbounds":[
          {"protocol":"vless","settings":{"address":"vless.invalid","port":443,"id":"11111111-2222-4333-8444-555555555555","encryption":"none"}},
          {"protocol":"vmess","settings":{"address":"vmess.invalid","port":443,"id":"22222222-3333-4444-8555-666666666666","alterId":0,"security":"auto"}},
          {"protocol":"trojan","settings":{"address":"trojan.invalid","port":443,"password":"SYNTHETIC-TROJAN"},"streamSettings":{"network":"tcp","security":"tls","tlsSettings":{"serverName":"trojan.invalid"}}},
          {"protocol":"shadowsocks","settings":{"address":"ss.invalid","port":8388,"method":"aes-128-gcm","password":"SYNTHETIC-SS"}},
          {"protocol":"socks","settings":{"address":"socks.invalid","port":1080,"user":"synthetic-socks","pass":"SYNTHETIC-SOCKS"}},
          {"protocol":"http","settings":{"address":"http.invalid","port":8080,"user":"synthetic-http","pass":"SYNTHETIC-HTTP"}}
        ]})JSON";
        const auto parsed = NodeImporter::parse(bytes);
        QVERIFY2(parsed, qPrintable(parsed.error)); QCOMPARE(parsed.nodes.size(), 6); QCOMPARE(parsed.incompleteNodes, 0);
        const QStringList types{"vless", "vmess", "trojan", "shadowsocks", "socks5", "http_connect"};
        for (int i = 0; i < parsed.nodes.size(); ++i) {
            const auto &node = parsed.nodes[i];
            QCOMPARE(node.sourceNodeIndex, i); QCOMPARE(node.parameterState, QStringLiteral("valid"));
            QVERIFY(node.nativeExecutable); QVERIFY(node.runtimeIssues.isEmpty());
            QCOMPARE(node.nativeOutbound.value("type").toString(), types[i]);
            QVERIFY(node.sourceDocument == bytes);
            const auto row = node.publicInfo(); QVERIFY(row.value("nativeExecutable").toBool());
            QVERIFY(row.value("capability").toMap().value("native").toBool());
            QVERIFY(!row.value("networkVerified").toBool());
            QVERIFY(!QJsonDocument::fromVariant(row).toJson().contains("SYNTHETIC-"));
            auto forged = node; forged.nativeOutbound = {{"type", "direct"}}; forged.host = "forged.invalid";
            QJsonObject replayed; const auto error = XrayJsonBridge::executableOutbound(forged, &replayed);
            QVERIFY2(error.isEmpty(), qPrintable(error)); QVERIFY(replayed == node.nativeOutbound);
        }
    }
    void socksVersionsKeepValidatedDisplayAndDnsSemantics() {
        for (const auto &version : {"4", "4a", "4A", "5"}) {
            const bool socks5 = QString(version) == "5";
            QJsonObject user{{"user", "synthetic-user"}};
            if (socks5) user["pass"] = "SYNTHETIC-SOCKS-PASSWORD";
            const QJsonObject server{{"address", "proxy.invalid"}, {"port", 1080}, {"users", QJsonArray{user}}};
            QJsonObject input{{"protocol", "socks"}, {"settings", QJsonObject{{"version", version}, {"servers", QJsonArray{server}}}}};
            const auto parsed = NodeImporter::parse(json(input));
            QVERIFY2(parsed, qPrintable(parsed.error)); const auto &node = parsed.nodes.first();
            const QString protocol = socks5 ? "socks5" : QString(version) == "4" ? "socks4" : "socks4a";
            const QString label = socks5 ? "SOCKS5" : QString(version) == "4" ? "SOCKS4" : "SOCKS4a";
            QVERIFY(node.nativeExecutable); QCOMPARE(node.protocol, protocol);
            QCOMPARE(node.publicInfo().value("protocolLabel").toString(), label);
            QCOMPARE(node.nativeOutbound.value("type").toString(), socks5 ? QString("socks5") : QString("socks4"));
            if (!socks5) {
                QCOMPARE(node.nativeOutbound.value("remote_dns").toBool(), QString(version) != "4");
                QVERIFY(node.nativeOutbound.value("user_id").toString() == "synthetic-user");
            }
            input["mux"] = QJsonObject{{"enabled", true}};
            const auto blocked = NodeImporter::parse(json(input)); QVERIFY2(blocked, qPrintable(blocked.error));
            QCOMPARE(blocked.nodes.first().protocol, protocol);
            QCOMPARE(blocked.nodes.first().publicInfo().value("protocolLabel").toString(), label);
            QVERIFY(!blocked.nodes.first().nativeExecutable); QVERIFY(blocked.nodes.first().nativeOutbound.isEmpty());
        }
    }
    void expandedNativeCandidatesKeepServerAccountAndFilteredSourceIndices() {
        const QByteArray bytes = R"JSON({"outbounds":[
          {"protocol":"freedom","tag":"local"},
          {"protocol":"http","tag":"expanded","settings":{"servers":[
            {"address":"first.invalid","port":3128,"users":[{"user":"first","pass":"SYNTHETIC-FIRST"},{"user":"invalid:name","pass":"SYNTHETIC-BLOCKED"}]},
            {"address":"second.invalid","port":8080,"users":[{"user":"second","pass":"SYNTHETIC-SECOND"},{"user":"third","pass":"SYNTHETIC-THIRD"}]}]}},
          {"protocol":"vless","settings":{"address":"last.invalid","port":443,"id":"11111111-2222-4333-8444-555555555555","encryption":"none"}}
        ]})JSON";
        const auto parsed = NodeImporter::parse(bytes);
        QVERIFY2(parsed, qPrintable(parsed.error)); QCOMPARE(parsed.nodes.size(), 5); QCOMPARE(parsed.incompleteNodes, 1);
        const QStringList users{"first", "invalid:name", "second", "third"};
        const QStringList passwords{"SYNTHETIC-FIRST", "SYNTHETIC-BLOCKED", "SYNTHETIC-SECOND", "SYNTHETIC-THIRD"};
        for (int i = 0; i < parsed.nodes.size(); ++i) {
            const auto &node = parsed.nodes[i]; QCOMPARE(node.sourceNodeIndex, i + 1); QVERIFY(node.sourceDocument == bytes);
            const auto source = node.originalConfiguration.value("source").toObject();
            QCOMPARE(source.value("outbound_index").toInt(), i == 4 ? 2 : 1);
            if (i < 4) {
                QCOMPARE(source.value("server_index").toInt(-1), i / 2); QCOMPARE(source.value("user_index").toInt(-1), i % 2);
                QVERIFY(node.username == users[i]); QVERIFY(node.password == passwords[i]);
            }
            auto forged = node; forged.nativeExecutable = true; forged.nativeOutbound = {{"type", "direct"}};
            QJsonObject replayed; const auto error = XrayJsonBridge::executableOutbound(forged, &replayed);
            if (i == 1) {
                QCOMPARE(node.parameterState, QStringLiteral("invalid")); QVERIFY(!node.nativeExecutable);
                QVERIFY(node.nativeOutbound.isEmpty()); QVERIFY(!error.isEmpty()); QVERIFY(replayed.isEmpty()); continue;
            }
            QVERIFY(node.nativeExecutable); QVERIFY2(error.isEmpty(), qPrintable(error)); QVERIFY(replayed == node.nativeOutbound);
            if (i < 4) {
                QCOMPARE(replayed.value("type").toString(), QStringLiteral("http_connect"));
                QCOMPARE(replayed.value("host").toString(), i < 2 ? QString("first.invalid") : QString("second.invalid"));
                QCOMPARE(replayed.value("port").toInt(), i < 2 ? 3128 : 8080);
                QVERIFY(replayed.value("auth").toObject().value("username").toString() == users[i]);
                QVERIFY(replayed.value("auth").toObject().value("password").toString() == passwords[i]);
            } else QCOMPARE(replayed.value("type").toString(), QStringLiteral("vless"));
            QVERIFY(!node.publicInfo().value("networkVerified").toBool());
        }
    }
    void passwordGettersPreserveUnicodeNulAndCipherPrivately() {
        const auto password = QStringLiteral("  SYNTHETIC_密碼") + QChar(0) + QStringLiteral(" 🌪  ");
        const QStringList methods{QString(), QStringLiteral("aes-128-gcm"),
            QStringLiteral("aes-256-gcm"), QStringLiteral("chacha20-ietf-poly1305")};
        QJsonArray outbounds;
        for (qsizetype index = 0; index < methods.size(); ++index) {
            QJsonObject server{{"address", "proxy.invalid"}, {"port", 443},
                {"password", password}, {"level", 0}, {"email", "SYNTHETIC_EMAIL@example.invalid"}};
            if (!methods.at(index).isEmpty()) server["method"] = methods.at(index);
            QJsonObject outbound{{"protocol", index == 0 ? "trojan" : "shadowsocks"},
                {"tag", QStringLiteral("密码节点 🌪")}, {"settings", QJsonObject{{"servers", QJsonArray{server}}}}};
            if (index == 0) outbound["streamSettings"] = QJsonObject{{"network", "tcp"}, {"security", "tls"},
                {"tlsSettings", QJsonObject{{"serverName", "proxy.invalid"}}}};
            outbounds.append(outbound);
        }
        const auto input = QByteArray::fromHex("efbbbf") + " \n" + json(QJsonObject{{"outbounds", outbounds}}) + "\n";
        const auto result = NodeImporter::parse(input);
        QVERIFY2(result, qPrintable(result.error));
        QCOMPARE(result.nodes.size(), methods.size());
        QVERIFY(result.configuration.isEmpty());
        QVERIFY(result.executionConfiguration.isEmpty());
        for (qsizetype index = 0; index < result.nodes.size(); ++index) {
            const auto &node = result.nodes.at(index);
            QCOMPARE(node.protocol, index == 0 ? QStringLiteral("trojan") : QStringLiteral("ss"));
            QCOMPARE(node.sourceNodeIndex, index);
            // Credential-bearing comparisons must not print values on failure.
            QVERIFY(node.sourceDocument == input);
            QVERIFY(node.originalConfiguration.value("outbound") == outbounds.at(index));
            QVERIFY(node.password == password);
            QCOMPARE(node.cipher, methods.at(index));
            const auto authentication = node.parameters.value("authentication").toObject();
            QCOMPARE(authentication.value("kind").toString(), QStringLiteral("password"));
            QVERIFY(authentication.value("password").toString() == password);
            QCOMPARE(authentication.value("method").toString(), methods.at(index));
            QCOMPARE(authentication.value("level").toInt(-1), 0);
            QVERIFY(authentication.value("email").toString() == QStringLiteral("SYNTHETIC_EMAIL@example.invalid"));
            QCOMPARE(node.parameterState, QStringLiteral("valid"));
            QVERIFY(ProxyNode::validate(node).isEmpty());
            QVERIFY(node.nativeExecutable);
            QVERIFY(!node.nativeOutbound.isEmpty());
            QVERIFY(node.nativeOutbound.value("password").toString() == password);
            QVERIFY(node.runtimeIssues.isEmpty());
            const auto publicInfo = node.publicInfo();
            QCOMPARE(publicInfo.value("parameterState").toString(), QStringLiteral("valid"));
            QVERIFY(publicInfo.value("nativeExecutable").toBool());
            QVERIFY(!publicInfo.value("networkVerified").toBool());
            QVERIFY(publicInfo.value("capability").toMap().value("native").toBool());
            const auto publicText = QJsonDocument(QJsonObject::fromVariantMap(publicInfo)).toJson();
            QVERIFY(!publicText.contains("SYNTHETIC_"));
            QVERIFY(!publicInfo.contains("password"));
            QVERIFY(!publicInfo.contains("authentication"));
            QVERIFY(!publicInfo.contains("sourceDocument"));
            QVERIFY(!publicInfo.contains("originalConfiguration"));
        }
    }
    void localActionsAreNotRemoteNodes() {
        const auto result = NodeImporter::parse(QJsonDocument(QJsonArray{
            QJsonObject{{"protocol", "freedom"}}, vless(), QJsonObject{{"protocol", "blackhole"}}}).toJson());
        QVERIFY2(result, qPrintable(result.error));
        QCOMPARE(result.nodes.size(), 1);
        QCOMPARE(result.nodes.first().sourceNodeIndex, 1);
    }
    void existingClashJsonStillImports() {
        const auto result = NodeImporter::parse(R"({"proxies":[{"name":"existing","type":"socks5","server":"example.invalid","port":1080}]})");
        QVERIFY2(result, qPrintable(result.error));
        QCOMPARE(result.nodes.first().protocol, QStringLiteral("socks5"));
    }
    void filePreviewAndExplicitCommit() {
        QTemporaryDir directory; QVERIFY(directory.isValid());
        const auto path = directory.filePath(QStringLiteral("配置_日本語.json"));
        const auto bytes = json(vless()); QVERIFY(write(path, bytes));
        NodeStore store(directory.filePath("nodes.dpapi")); NodeImportService service(&store);
        int applies = 0; NodeImporter::Result committed;
        service.setConfigurationApplier([&](const auto &result, const QString &source, QString *) {
            ++applies; committed = result; return source.isEmpty();
        });
        service.importFile(QUrl::fromLocalFile(path));
        QTRY_VERIFY_WITH_TIMEOUT(service.hasPreview(), 10000);
        QCOMPARE(applies, 0); QVERIFY(store.nodes().isEmpty());
        QCOMPARE(service.preview().size(), 1);
        QVERIFY(!service.message().contains("真实联网成功"));
        service.confirmImport();
        QCOMPARE(applies, 1); QVERIFY(!service.hasPreview());
        QCOMPARE(committed.nodes.first().sourceDocument, bytes);
        QCOMPARE(committed.nodes.first().importSource, QStringLiteral("file"));
        QFile original(path); QVERIFY(original.open(QIODevice::ReadOnly)); QCOMPARE(original.readAll(), bytes);
        service.shutdown();
    }
    void fileCancelAndFailedCommitDoNotMutate() {
        QTemporaryDir directory; const auto path = directory.filePath("nodes.json"); QVERIFY(write(path, json(vless())));
        NodeStore store(directory.filePath("nodes.dpapi")); NodeImportService service(&store);
        int applies = 0;
        service.setConfigurationApplier([&](const auto &, const auto &, QString *error) {
            ++applies; *error = QStringLiteral("受控保存失败"); return false;
        });
        service.importFile(QUrl::fromLocalFile(path)); QTRY_VERIFY_WITH_TIMEOUT(service.hasPreview(), 10000);
        service.cancelImport(); QCOMPARE(applies, 0); QVERIFY(store.nodes().isEmpty());
        service.importFile(QUrl::fromLocalFile(path)); QTRY_VERIFY_WITH_TIMEOUT(service.hasPreview(), 10000);
        service.confirmImport(); QCOMPARE(applies, 1); QVERIFY(store.nodes().isEmpty());
        QVERIFY(service.message().contains(QStringLiteral("受控保存失败")));
        service.shutdown();
    }
    void fileLimitsAndNonLocalPaths() {
        QTemporaryDir directory; NodeStore store(directory.filePath("nodes.dpapi")); NodeImportService service(&store);
        const auto path = directory.filePath("large.json"); QFile large(path); QVERIFY(large.open(QIODevice::WriteOnly));
        QVERIFY(large.resize(NodeImporter::MaximumBytes + 1)); large.close();
        service.importFile(QUrl::fromLocalFile(path)); QTRY_VERIFY_WITH_TIMEOUT(!service.busy(), 10000);
        QVERIFY(!service.hasPreview()); QVERIFY(service.message().contains("4 MiB"));
        service.importFile(QUrl("https://example.invalid/config.json"));
        QVERIFY(!service.busy()); QVERIFY(!service.hasPreview());
        service.importFile(QUrl::fromLocalFile(directory.path())); QTRY_VERIFY_WITH_TIMEOUT(!service.busy(), 10000);
        QVERIFY(!service.hasPreview()); QVERIFY(store.nodes().isEmpty());
        service.shutdown();
    }
    void cancelInFlightFileDiscardsQueuedResult() {
        QTemporaryDir directory;const auto path=directory.filePath("cancel.json");QVERIFY(write(path,json(vless())));
        NodeStore store(directory.filePath("nodes.dpapi"));NodeImportService service(&store);int applies=0;
        service.setConfigurationApplier([&](const auto &,const auto &,QString *){++applies;return true;});
        service.importFile(QUrl::fromLocalFile(path));service.cancelImport();
        QVERIFY(!service.busy());QTest::qWait(100);
        QVERIFY(!service.hasPreview());QCOMPARE(applies,0);QVERIFY(store.nodes().isEmpty());service.shutdown();
    }
    void fileImportUsesRealEncryptedStore() {
        QTemporaryDir directory; const auto path = directory.filePath(QStringLiteral("本地节点.json"));
        const auto bytes = json(vless()); QVERIFY(write(path, bytes));
        const auto storePath = directory.filePath("nodes.dpapi"); QString savedId;
        {
            NodeStore store(storePath);NodeImportService service(&store);
            service.importFile(QUrl::fromLocalFile(path));QTRY_VERIFY_WITH_TIMEOUT(service.hasPreview(), 10000);
            service.confirmImport();
            QTRY_VERIFY_WITH_TIMEOUT(!service.busy(),10000);
#ifdef Q_OS_WIN
            QCOMPARE(store.nodes().size(), 1);savedId = store.nodes().first().id;
            QCOMPARE(store.nodes().first().sourceDocument, bytes);
            QVERIFY(store.select(savedId));
#else
            QVERIFY(store.nodes().isEmpty());QVERIFY(!QFile::exists(storePath));
            QVERIFY(service.message().contains(QStringLiteral("加密失败")));
#endif
            service.shutdown();
        }
#ifdef Q_OS_WIN
        NodeStore restored(storePath);QVERIFY2(restored.error().isEmpty(), qPrintable(restored.error()));
        QCOMPARE(restored.nodes().size(), 1);QCOMPARE(restored.selectedId(), savedId);
        QCOMPARE(restored.nodes().first().sourceDocument, bytes);
#endif
    }
    void textAndClipboardShareStrictPreview() {
        QTemporaryDir directory;NodeStore store(directory.filePath("nodes.dpapi"));NodeImportService service(&store);
        int applies=0;NodeImporter::Result committed;
        service.setConfigurationApplier([&](const auto &result,const auto &source,QString *) {
            ++applies;committed=result;return source.isEmpty();
        });
        const auto bytes=QJsonDocument(QJsonArray{vless(QStringLiteral("东京 🌏")),vless(QStringLiteral("香港"))}).toJson();
        service.importText(QString::fromUtf8(bytes));QTRY_VERIFY_WITH_TIMEOUT(service.hasPreview(),10000);
        QCOMPARE(service.preview().size(),2);QCOMPARE(applies,0);QVERIFY(store.nodes().isEmpty());
        service.confirmImport();QCOMPARE(applies,1);
        QCOMPARE(committed.nodes.first().sourceDocument,bytes);
        QCOMPARE(committed.nodes.first().name,QStringLiteral("东京 🌏"));
        QCOMPARE(committed.nodes.first().importSource,QStringLiteral("text"));
        const auto previous=QGuiApplication::clipboard()->text();
        QGuiApplication::clipboard()->setText(QString::fromUtf8(bytes));service.importClipboard();
        QGuiApplication::clipboard()->setText(previous);
        QTRY_VERIFY_WITH_TIMEOUT(service.hasPreview(),10000);QCOMPARE(applies,1);
        service.confirmImport();QCOMPARE(applies,2);
        QCOMPARE(committed.nodes.first().sourceDocument,bytes);
        QCOMPARE(committed.nodes.first().importSource,QStringLiteral("clipboard"));service.shutdown();
    }
    void textFailureAndCancellationNeverApply() {
        QTemporaryDir directory;NodeStore store(directory.filePath("nodes.dpapi"));NodeImportService service(&store);int applies=0;
        service.setConfigurationApplier([&](const auto &,const auto &,QString *){++applies;return true;});
        service.importText(QString::fromUtf8(json(vless())));service.cancelImport();QTest::qWait(100);
        QVERIFY(!service.hasPreview());QCOMPARE(applies,0);
        service.importText(QStringLiteral(R"({"protocol":"vless","settings":{"id":"SECRET-D2","id":"other"}})"));
        QTRY_VERIFY_WITH_TIMEOUT(!service.busy(),10000);QVERIFY(!service.hasPreview());
        QVERIFY(service.message().contains("DuplicateJsonKey"));QVERIFY(!service.message().contains("SECRET-D2"));
        service.importText(QString(NodeImporter::MaximumBytes+1,u' '));
        QVERIFY(!service.busy());QVERIFY(service.message().contains("4 MiB"));
        service.importText(QString(NodeImporter::MaximumBytes/2,u'中'));
        QTRY_VERIFY_WITH_TIMEOUT(!service.busy(),10000);QVERIFY(!service.hasPreview());
        QVERIFY(service.message().contains("4 MiB"));QCOMPARE(applies,0);QVERIFY(store.nodes().isEmpty());
        service.shutdown();
    }
    void repeatedTextKeepsRealStoreCatalog() {
        QTemporaryDir directory;const auto storePath=directory.filePath("nodes.dpapi");NodeStore store(storePath);NodeImportService service(&store);
        for(int pass=0;pass<2;++pass) {
            service.importText(QString::fromUtf8(json(vless())));QTRY_VERIFY_WITH_TIMEOUT(service.hasPreview(),10000);
            service.confirmImport();
            QTRY_VERIFY_WITH_TIMEOUT(!service.busy(),10000);
#ifdef Q_OS_WIN
            QCOMPARE(store.nodes().size(),1);
#else
            QVERIFY(store.nodes().isEmpty());QVERIFY(!QFile::exists(storePath));
#endif
        }
        service.importText(QStringLiteral("{\"protocol\":\"vless\",}"));QTRY_VERIFY_WITH_TIMEOUT(!service.busy(),10000);
#ifdef Q_OS_WIN
        QCOMPARE(store.nodes().size(),1);
#else
        QVERIFY(store.nodes().isEmpty());
#endif
        service.shutdown();
    }
    void publicModelSeparatesValidationCapabilityAndNetwork() {
        auto outbound=vless();auto settings=outbound.value("settings").toObject();
        settings["flow"]="xtls-rprx-vision";outbound["settings"]=settings;
        outbound["streamSettings"]=QJsonObject{{"network","ws"},{"security","reality"},
            {"wsSettings",QJsonObject{{"path","/private"},{"headers",QJsonObject{{"Host","web.example.invalid"}}}}},
            {"realitySettings",QJsonObject{{"publicKey","CQkJCQkJCQkJCQkJCQkJCQkJCQkJCQkJCQkJCQkJCQk"},{"shortId","a1b2"},
                {"spiderX","/secret-path"},{"serverName","tls.example.invalid"},{"fingerprint","rustls"}}}};
        const auto result=NodeImporter::parse(json(outbound));QVERIFY2(result,qPrintable(result.error));
        const auto &node=result.nodes.first();const auto row=node.publicInfo();
        QCOMPARE(row.value("protocolLabel").toString(),QStringLiteral("VLESS"));
        QCOMPARE(row.value("transportLabel").toString(),QStringLiteral("WebSocket"));
        QCOMPARE(row.value("securityLabel").toString(),QStringLiteral("REALITY"));
        QVERIFY(row.value("visionEnabled").toBool());QVERIFY(row.value("jsonParsed").toBool());
        QVERIFY(!row.value("nativeExecutable").toBool());QVERIFY(!row.value("networkVerified").toBool());
        QVERIFY(!row.value("unsupportedReason").toString().isEmpty());
        QVERIFY(row.value("configurationState").toString().contains(QStringLiteral("未验证业务流量")));
        QVERIFY(!row.value("capability").toMap().value("tested").toBool());
        QCOMPARE(node.originalConfiguration.value("outbound").toObject(),outbound);
        const auto publicBytes=QJsonDocument::fromVariant(row).toJson();
        QVERIFY(!publicBytes.contains("11111111-2222-4333-8444-555555555555"));
        QVERIFY(!publicBytes.contains("/secret-path"));QVERIFY(!publicBytes.contains("/private"));
        const QMap<QString,QString> labels{{"vmess","VMess"},{"trojan","Trojan"},{"shadowsocks","Shadowsocks"},{"socks","SOCKS5"},{"http","HTTP"}};
        for(auto it=labels.begin();it!=labels.end();++it) {
            auto input=vless();input["protocol"]=it.key();const auto parsed=NodeImporter::parse(json(input));QVERIFY(parsed);
            QCOMPARE(parsed.nodes.first().publicInfo().value("protocolLabel").toString(),it.value());
        }
    }
    void globalCredentialsCannotBecomeNodeLabels() {
        const auto input=json(QJsonObject{{"inbounds",QJsonArray{QJsonObject{{"protocol","socks"},{"port",1080},
            {"settings",QJsonObject{{"accounts",QJsonArray{QJsonObject{{"user","synthetic"},{"pass","SYNTHETIC-INBOUND-PASSWORD"}}}}}}}}},
            {"outbounds",QJsonArray{vless("SYNTHETIC-INBOUND-PASSWORD")}}});
        const auto parsed=NodeImporter::parse(input);QVERIFY2(parsed,qPrintable(parsed.error));
        const auto publicBytes=QJsonDocument::fromVariant(parsed.nodes.first().publicInfo()).toJson();
        QVERIFY(!publicBytes.contains("SYNTHETIC-INBOUND-PASSWORD"));
        QCOMPARE(parsed.nodes.first().sourceDocument,input);
    }
    void confirmedAsyncCommitKeepsServiceBusyUntilResult() {
        QTemporaryDir directory;NodeStore store(directory.filePath("nodes.dpapi"));NodeImportService service(&store);
        NodeImportService::ApplyCompletion complete;int requests=0;QSignalSpy applied(&service,&NodeImportService::nodesApplied);
        service.setAsyncConfigurationApplier([&](const auto &,const auto &,auto callback,QString *) {
            ++requests;complete=std::move(callback);return true;
        });
        service.importText(QString::fromUtf8(json(vless())));QTRY_VERIFY_WITH_TIMEOUT(service.hasPreview(),10000);
        service.confirmImport();QVERIFY(service.busy());QVERIFY(!service.hasPreview());QCOMPARE(requests,1);
        service.cancelImport();QVERIFY(service.busy()); // Confirmation already authorized the atomic write.
        service.importText(QString::fromUtf8(json(vless("other"))));QCOMPARE(requests,1);
        complete(false,QStringLiteral("受控原子写入失败"));
        QVERIFY(!service.busy());QCOMPARE(applied.count(),0);QVERIFY(store.nodes().isEmpty());
        QVERIFY(service.message().contains(QStringLiteral("受控原子写入失败")));
        service.importText(QString::fromUtf8(json(vless())));QTRY_VERIFY_WITH_TIMEOUT(service.hasPreview(),10000);
        service.confirmImport();QVERIFY(service.busy());complete(true,{});
        QVERIFY(!service.busy());QCOMPARE(applied.count(),1);service.shutdown();
    }
};
QTEST_MAIN(XrayImportTests)
#include "XrayImportTests.moc"
