#include <QtTest>
#include <QFile>
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
    void unsupportedTransportRemainsData() {
        for (const auto &transport : {"grpc", "http", "httpupgrade", "xhttp"}) {
            auto input = vless();
            input["streamSettings"] = QJsonObject{{"network", transport}, {"security", "tls"},
                {"tlsSettings", QJsonObject{{"serverName", "tls.example.invalid"}}}};
            const auto result = NodeImporter::parse(json(input));
            QVERIFY2(result, qPrintable(result.error));
            QVERIFY(!result.nodes.first().nativeExecutable);
            QCOMPARE(result.nodes.first().originalConfiguration.value("outbound").toObject(), input);
            QCOMPARE(result.nodes.first().securityType, QStringLiteral("tls"));
            QVERIFY(!result.nodes.first().runtimeIssues.isEmpty());
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
};
QTEST_MAIN(XrayImportTests)
#include "XrayImportTests.moc"
