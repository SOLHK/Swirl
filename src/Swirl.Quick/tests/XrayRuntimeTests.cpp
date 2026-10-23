#include <QtTest>
#include <QCoreApplication>
#include <QDir>
#include <QElapsedTimer>
#include <QFile>
#include <QFileInfo>
#include <QJsonArray>
#include <QJsonDocument>
#include <QMetaMethod>
#include <QNetworkAccessManager>
#include <QNetworkProxy>
#include <QNetworkReply>
#include <QProcess>
#include <QProcessEnvironment>
#include <QSaveFile>
#include <QScopeGuard>
#include <QSignalSpy>
#include <QSslCertificate>
#include <QSslConfiguration>
#include <QSslError>
#include <QSslSocket>
#include <QTcpServer>
#include <QTemporaryDir>
#include <QUuid>
#include "engine/NodeImportService.h"
#include "engine/RustCoreEngine.h"
#include "engine/XrayJsonBridge.h"

namespace {
QJsonObject realityOutbound() {
    const QJsonObject user{{"id", "00112233-4455-6677-8899-aabbccddeeff"},
        {"encryption", "none"}, {"flow", "xtls-rprx-vision"}};
    const QJsonObject server{{"address", "127.0.0.1"}, {"port", 9}, {"users", QJsonArray{user}}};
    const QJsonObject reality{{"serverName", "camouflage.invalid"}, {"fingerprint", "chrome"},
        {"publicKey", "CQkJCQkJCQkJCQkJCQkJCQkJCQkJCQkJCQkJCQkJCQk"}, {"shortId", "a1B2"}};
    return {{"tag", "JSON REALITY 测试"}, {"protocol", "vless"},
        {"settings", QJsonObject{{"vnext", QJsonArray{server}}}},
        {"streamSettings", QJsonObject{{"network", "tcp"}, {"security", "reality"},
            {"realitySettings", reality}}}};
}

QByteArray document(const QJsonObject &outbound) {
    return QJsonDocument(QJsonObject{{"outbounds", QJsonArray{outbound}}}).toJson(QJsonDocument::Compact);
}

EngineStartOptions options(const QList<ProxyNode> &nodes, quint16 port = 17898) {
    EngineStartOptions result;
    result.nodes = nodes;
    if (!nodes.isEmpty()) result.selectedNodeId = nodes.first().id;
    result.proxyPort = port;
    result.routingMode = QStringLiteral("global");
    result.startupTimeoutMs = 5000;
    // R1 removes the external executable option entirely. The actual runtime
    // identity and process ID assertions below remain mandatory.
    return result;
}

bool sameValues(const ProxyNode &a, const ProxyNode &b) {
    // Compare credential-bearing values without printing them on assertion
    // failure. Exact source bytes cover fields a converter does not yet know.
    return a.id == b.id && a.name == b.name && a.protocol == b.protocol &&
        a.host == b.host && a.port == b.port && a.username == b.username &&
        a.password == b.password && a.cipher == b.cipher && a.serverName == b.serverName &&
        a.parameters == b.parameters && a.originalConfiguration == b.originalConfiguration &&
        a.sourceDocument == b.sourceDocument && a.sourceNodeIndex == b.sourceNodeIndex &&
        a.sourceFingerprint == b.sourceFingerprint &&
        a.sourceFormat == b.sourceFormat && a.sourceId == b.sourceId && a.importSource == b.importSource &&
        a.transportType == b.transportType && a.securityType == b.securityType &&
        a.parameterState == b.parameterState && a.conversionIssues == b.conversionIssues;
}

QJsonObject httpRequest(const QUrl &url, quint16 proxyPort, const QByteArray &expected) {
    QNetworkAccessManager client;
    client.setProxy(QNetworkProxy(QNetworkProxy::HttpProxy, "127.0.0.1", proxyPort));
    QNetworkRequest request(url);
    request.setRawHeader("Connection", "close");
    request.setAttribute(QNetworkRequest::Http2AllowedAttribute, false);
    request.setAttribute(QNetworkRequest::RedirectPolicyAttribute, QNetworkRequest::ManualRedirectPolicy);
    request.setTransferTimeout(5000);
    auto *reply = client.get(request);
    reply->setReadBufferSize(65537);
    QByteArray body;
    const auto drain = [&] {
        body += reply->readAll();
        if (body.size() > 65536) reply->abort();
        return reply->isFinished();
    };
    const bool completed = QTest::qWaitFor(drain, 6000);
    if (!completed) reply->abort();
    body += reply->readAll();
    const int status = reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();
    return {{"status", status}, {"body_verified", completed &&
        reply->error() == QNetworkReply::NoError && status == 200 && body == expected}};
}

QJsonObject httpsRequest(const QUrl &url, quint16 proxyPort,
                         const QList<QSslCertificate> &certificates, const QByteArray &expected) {
    QJsonObject report{{"status", 0}, {"body_verified", false}, {"certificate_verified", false},
        {"close_notify_sent", false}, {"close_notify_received", false}};
    QSslSocket socket;
    socket.setReadBufferSize(65537);
    socket.setProxy(QNetworkProxy(QNetworkProxy::HttpProxy, "127.0.0.1", proxyPort));
    auto tls = QSslConfiguration::defaultConfiguration();
    tls.setCaCertificates(certificates);
    tls.setPeerVerifyMode(QSslSocket::VerifyPeer);
    tls.setAllowedNextProtocols({QByteArray("http/1.1")});
    socket.setSslConfiguration(tls);
    bool verificationError = false;
    QObject::connect(&socket, &QSslSocket::sslErrors, &socket,
        [&](const QList<QSslError> &) { verificationError = true; });
    QObject::connect(&socket, &QSslSocket::alertSent, &socket,
        [&](QSsl::AlertLevel, QSsl::AlertType type, const QString &) {
            if (type == QSsl::AlertType::CloseNotify) report["close_notify_sent"] = true;
        });
    QObject::connect(&socket, &QSslSocket::alertReceived, &socket,
        [&](QSsl::AlertLevel, QSsl::AlertType type, const QString &) {
            if (type == QSsl::AlertType::CloseNotify) report["close_notify_received"] = true;
        });
    QElapsedTimer timer;
    timer.start();
    const auto wait = [&](const auto &predicate) {
        const int remaining = 15000 - int(timer.elapsed());
        return remaining > 0 && QTest::qWaitFor(predicate, remaining);
    };
    socket.connectToHostEncrypted(url.host(), quint16(url.port(443)));
    if (!wait([&] { return socket.isEncrypted() || socket.state() == QAbstractSocket::UnconnectedState; })) return report;
    const bool verified = socket.isEncrypted() && !verificationError &&
        !socket.peerCertificate().isNull() && socket.sslHandshakeErrors().isEmpty();
    report["certificate_verified"] = verified;
    if (!verified) return report;
    const auto request = "GET " + url.path(QUrl::FullyEncoded).toUtf8() +
        " HTTP/1.1\r\nHost: " + url.host().toUtf8() + ':' + QByteArray::number(url.port(443)) +
        "\r\nConnection: close\r\nAccept-Encoding: identity\r\n\r\n";
    if (socket.write(request) != request.size()) return report;
    QByteArray response;
    qsizetype separator = -1;
    if (!wait([&] {
        response += socket.readAll();
        separator = response.indexOf("\r\n\r\n");
        return response.size() > 65536 || separator >= 0 || socket.state() == QAbstractSocket::UnconnectedState;
    })) return report;
    if (separator < 0 || response.size() > 65536 || !response.startsWith("HTTP/1.1 200 ")) return report;
    bool lengthSeen = false;
    const auto headers = response.left(separator).split('\n');
    for (qsizetype i = 1; i < headers.size(); ++i) {
        const auto field = headers[i].trimmed();
        const auto colon = field.indexOf(':');
        if (colon <= 0) return report;
        const auto name = field.left(colon).toLower(), value = field.mid(colon + 1).trimmed();
        if (name == "transfer-encoding" || (name == "content-encoding" && value != "identity")) return report;
        if (name == "content-length") {
            bool ok = false;
            const auto length = value.toLongLong(&ok);
            if (lengthSeen || !ok || length != expected.size()) return report;
            lengthSeen = true;
        }
    }
    if (!lengthSeen || !wait([&] {
        response += socket.readAll();
        return response.size() > 65536 || response.size() >= separator + 4 + expected.size() ||
            socket.state() == QAbstractSocket::UnconnectedState;
    })) return report;
    if (response.size() > 65536 || response.mid(separator + 4) != expected || verificationError) return report;
    // Connection: close lets the independent HTTP origin initiate TLS
    // shutdown. Flush pending encrypted control records while keeping the
    // read side open until the peer's alert and TCP EOF are processed.
    if (!wait([&] {
        if (socket.state() == QAbstractSocket::ConnectedState) socket.flush();
        return socket.state() == QAbstractSocket::UnconnectedState;
    })) return report;
    response += socket.readAll();
    if (response.mid(separator + 4) != expected || verificationError) return report;
    report["status"] = 200;
    report["body_verified"] = true;
    return report;
}

QJsonObject independentBusinessRequests(const QJsonObject &fixture, quint16 proxyPort) {
    // Only the test traffic client is a process. The selected proxy core stays
    // in this Qt process and its exact imported outbound is not sent here.
    const auto python = qEnvironmentVariable("SWIRL_XRAY_PYTHON");
    if (!QFileInfo(python).isAbsolute() || !QFileInfo(python).isFile()) return {};
    QTemporaryDir directory(QDir::tempPath() + "/Swirl traffic 客户端-XXXXXX");
    if (!directory.isValid()) return {};
    QJsonObject clientFixture{{"schema", 1}};
    for (const auto &key : {"http_url", "https_url", "ca_pem", "expected_body"})
        clientFixture[key] = fixture[key];
    const auto fixturePath = directory.filePath("traffic-client.json");
    QSaveFile input(fixturePath);
    const auto bytes = QJsonDocument(clientFixture).toJson(QJsonDocument::Compact);
    if (!input.open(QIODevice::WriteOnly) || input.write(bytes) != bytes.size() || !input.commit()) return {};
    QProcess client;
    auto environment = QProcessEnvironment::systemEnvironment();
    for (const auto &key : environment.keys())
        if (key.startsWith("SWIRL_")) environment.remove(key);
    client.setProcessEnvironment(environment);
    client.setProgram(python);
    client.setArguments({QStringLiteral(SWIRL_SOURCE_ROOT "/tools/tests/test_xray_qt_import.py"),
        "--traffic-client", "--client-fixture", fixturePath, "--proxy-port", QString::number(proxyPort)});
    client.start();
    QByteArray output;
    qsizetype errorBytes = 0;
    bool oversized = false;
    const bool completed = QTest::qWaitFor([&] {
        output += client.readAllStandardOutput();
        errorBytes += client.readAllStandardError().size();
        oversized = output.size() > 65536 || errorBytes > 65536;
        return oversized || client.state() == QProcess::NotRunning;
    }, 30000);
    if (!completed || oversized) {
        client.kill(); client.waitForFinished(1000);
        return {};
    }
    output += client.readAllStandardOutput();
    if (output.size() > 65536 || client.exitStatus() != QProcess::NormalExit || client.exitCode() != 0) return {};
    QJsonParseError error;
    const auto response = QJsonDocument::fromJson(output, &error);
    if (error.error != QJsonParseError::NoError || !response.isObject()) return {};
    const auto result = response.object();
    if (result["schema"] != QJsonValue(1) || result["client"] != QJsonValue("python-stdlib-ssl")) return {};
    return result;
}
}

class XrayRuntimeTests final : public QObject {
    Q_OBJECT
private slots:
    void sourceReplayRejectsForgedRuntimeCache() {
        const auto parsed = XrayJsonBridge::parse(document(realityOutbound()));
        QVERIFY(parsed);
        QCOMPARE(parsed.nodes.size(), 1);
        auto node = parsed.nodes.first();
        QVERIFY(node.nativeExecutable);
        QJsonObject expected;
        QVERIFY(XrayJsonBridge::executableOutbound(node, &expected).isEmpty());
        node.nativeExecutable = false;
        node.nativeOutbound = {{"type", "direct"}};
        node.protocol = "http";
        node.host = "forged.invalid";
        node.port = 1;
        node.parameters = {{"skip-cert-verify", true}};
        node.originalConfiguration = {{"protocol", "freedom"}};
        node.conversionIssues = {"forged-cache-error"};
        node.runtimeIssues = {"forged-capability"};
        QJsonObject config;
        QVERIFY(RustCoreEngine::configuration(options({node}), &config).isEmpty());
        const auto outbound = config["nodes"].toArray().first().toObject()["outbound"].toObject();
        QVERIFY(outbound == expected);
        QCOMPARE(outbound["type"], QJsonValue("vless"));
        QCOMPARE(outbound["flow"], QJsonValue("xtls-rprx-vision"));
        QVERIFY(!outbound["reality"].toObject().isEmpty());
        QVERIFY(outbound["tls"].isNull() || outbound["tls"].isUndefined());
    }

    void invalidSourceCannotBePromotedByCachedFlags() {
        const auto parsed = XrayJsonBridge::parse(document(realityOutbound()));
        QVERIFY(parsed && parsed.nodes.size() == 1);
        QList<ProxyNode> invalid;
        auto node = parsed.nodes.first();
        node.sourceDocument = R"({"outbounds":[],"outbounds":[],"password":"SYNTHETIC-SECRET"})";
        invalid.append(node);
        node = parsed.nodes.first(); node.sourceNodeIndex = 99; invalid.append(node);
        node = parsed.nodes.first(); node.sourceDocument.clear(); invalid.append(node);
        for (bool invalidUuid : {false, true}) {
            auto raw = realityOutbound();
            auto settings = raw["settings"].toObject();
            auto servers = settings["vnext"].toArray(); auto server = servers.first().toObject();
            if (invalidUuid) {
                auto users = server["users"].toArray(); auto user = users.first().toObject();
                user["id"] = "SYNTHETIC-SECRET-invalid-uuid-value";
                users[0] = user; server["users"] = users;
            } else server["port"] = 0;
            servers[0] = server; settings["vnext"] = servers; raw["settings"] = settings;
            node = parsed.nodes.first(); node.sourceDocument = document(raw); invalid.append(node);
        }
        for (const auto &network : {"grpc", "http", "httpupgrade", "xhttp", "unsupported-transport"}) {
            auto raw = realityOutbound();
            auto stream = raw["streamSettings"].toObject(); stream["network"] = network;
            raw["streamSettings"] = stream;
            node = parsed.nodes.first(); node.sourceDocument = document(raw); invalid.append(node);
        }
        auto raw = realityOutbound();
        auto stream = raw["streamSettings"].toObject();
        auto reality = stream["realitySettings"].toObject(); reality["future-secret-field"] = "SYNTHETIC-SECRET";
        stream["realitySettings"] = reality; raw["streamSettings"] = stream;
        node = parsed.nodes.first(); node.sourceDocument = document(raw); invalid.append(node);
        for (auto candidate : invalid) {
            candidate.nativeExecutable = true;
            candidate.nativeOutbound = {{"type", "direct"}};
            candidate.conversionIssues.clear(); candidate.runtimeIssues.clear();
            QJsonObject output{{"unchanged", true}};
            const auto error = RustCoreEngine::configuration(options({candidate}), &output);
            QVERIFY(!error.isEmpty());
            QVERIFY(!error.contains("SYNTHETIC-SECRET"));
            QVERIFY(output == QJsonObject({{"unchanged", true}}));
        }
    }

    void importedListenersAndRulesCannotChangeLocalOptions() {
        const auto bytes = QJsonDocument(QJsonObject{
            {"outbounds", QJsonArray{realityOutbound()}},
            {"inbounds", QJsonArray{QJsonObject{{"protocol", "socks"}, {"listen", "0.0.0.0"}, {"port", 34567}}}},
            {"routing", QJsonObject{{"rules", QJsonArray{QJsonObject{{"outboundTag", "arbitrary"}}}}}},
            {"log", QJsonObject{{"access", "must-not-write-this-file"}}}}).toJson();
        const auto parsed = XrayJsonBridge::parse(bytes);
        QVERIFY(parsed && parsed.nodes.size() == 1);
        auto settings = options(parsed.nodes, 18123);
        settings.inboundUsername = "local-user";
        settings.inboundPassword = "local-password";
        QJsonObject output;
        QVERIFY(RustCoreEngine::configuration(settings, &output).isEmpty());
        QCOMPARE(output["listen"], QJsonValue("127.0.0.1:18123"));
        QVERIFY(output["rules"].toArray().isEmpty());
        QVERIFY(output["selectors"].toArray().isEmpty());
        QVERIFY(!output.contains("inbounds") && !output.contains("log"));
        QVERIFY(output["inbound_auth"].toObject() == QJsonObject({{"username", "local-user"}, {"password", "local-password"}}));
    }

    void invalidSelectionAndStartPreserveSafety() {
        const auto parsed = XrayJsonBridge::parse(document(realityOutbound()));
        QVERIFY(parsed && parsed.nodes.size() == 1);
        auto invalid = parsed.nodes.first();
        invalid.id = QUuid::createUuid().toString(QUuid::WithoutBraces);
        invalid.sourceNodeIndex = 99;
        invalid.nativeExecutable = true; invalid.nativeOutbound = {{"type", "direct"}};
        QTcpServer reservation; reservation.setProxy(QNetworkProxy::NoProxy);
        QVERIFY(reservation.listen(QHostAddress::LocalHost));
        const auto port = reservation.serverPort(); reservation.close();
        RustCoreEngine engine;
        auto settings = options({invalid}, port);
        engine.start(settings);
        QCOMPARE(engine.status().state, ProxyEngine::State::Failed);
        QCOMPARE(engine.status().error, ProxyEngine::Error::InvalidOptions);
        QVERIFY(!engine.status().processAlive && !engine.status().apiHealthy);
        QVERIFY(engine.status().controlEndpoint.isEmpty());
        settings = options({parsed.nodes.first(), invalid}, port);
        engine.start(settings);
        QVERIFY(engine.status().processAlive && engine.status().apiHealthy);
        QCOMPARE(engine.status().engineKind, QString("rust"));
        QCOMPARE(engine.status().processId, QCoreApplication::applicationPid());
        QVERIFY(engine.status().controlEndpoint.startsWith("in-process://SwirlRust/"));
        const auto selected = engine.status().selectedNodeId;
        engine.selectNode(invalid.id);
        QCOMPARE(engine.status().selectedNodeId, selected);
        QVERIFY(engine.status().apiHealthy);
        engine.selectNode("missing-source-node");
        QCOMPARE(engine.status().selectedNodeId, selected);
        QVERIFY(engine.status().apiHealthy);
        engine.stop();
        QVERIFY(!engine.status().processAlive && !engine.status().apiHealthy);
        QVERIFY(reservation.listen(QHostAddress::LocalHost, port));
    }

    void rustStartPortConflictIsReported() {
        const auto parsed = XrayJsonBridge::parse(document(realityOutbound()));
        QVERIFY(parsed && parsed.nodes.size() == 1);
        QTcpServer occupied; occupied.setProxy(QNetworkProxy::NoProxy);
        QVERIFY(occupied.listen(QHostAddress::LocalHost));
        RustCoreEngine engine;
        engine.start(options(parsed.nodes, occupied.serverPort()));
        QCOMPARE(engine.status().state, ProxyEngine::State::Failed);
        QCOMPARE(engine.status().error, ProxyEngine::Error::ConfigurationFailed);
        QVERIFY(!engine.status().processAlive && !engine.status().apiHealthy);
        QVERIFY(occupied.isListening());
        QVERIFY(engine.status().controlEndpoint.isEmpty());
        engine.stop();
    }

    void nativeProductChain() {
        QVERIFY(qEnvironmentVariableIsSet("SWIRL_XRAY_QT_FIXTURE"));
        const auto reportPath = qEnvironmentVariable("SWIRL_XRAY_QT_REPORT");
        QVERIFY(!reportPath.isEmpty() && QFileInfo(reportPath).isAbsolute());
        const auto fixturePath = qEnvironmentVariable("SWIRL_XRAY_QT_FIXTURE");
        QVERIFY(QFileInfo(fixturePath).absoluteFilePath() != QFileInfo(reportPath).absoluteFilePath());
        QJsonObject report{{"schema", 1}, {"file_preview", false}, {"parameters_preserved", false},
            {"persisted", false}, {"reloaded", false}, {"rust_core_started", false},
            {"in_process", false}, {"stopped", false}, {"listener_closed", false}};
#ifdef Q_OS_WIN
        report["pipeline"] = "windows-dpapi";
#else
        report["pipeline"] = "portable-import-runtime";
#endif
        const auto saveReport = [&] {
            QSaveFile file(reportPath); const auto bytes = QJsonDocument(report).toJson();
            return file.open(QIODevice::WriteOnly) && file.write(bytes) == bytes.size() && file.commit();
        };
        QFile input(fixturePath); QVERIFY(input.open(QIODevice::ReadOnly));
        QVERIFY(input.size() > 0 && input.size() <= 64 * 1024);
        QJsonParseError error;
        const auto fixtureDocument = QJsonDocument::fromJson(input.read(64 * 1024 + 1), &error);
        QVERIFY(error.error == QJsonParseError::NoError && fixtureDocument.isObject());
        const auto fixture = fixtureDocument.object();
        for (const auto &key : fixture.keys())
            QVERIFY((QStringList{"schema", "protocol", "configuration_path", "http_url", "https_url", "ca_pem", "expected_body", "client"}.contains(key)));
        QCOMPARE(fixture["schema"], QJsonValue(1));
        const auto profile = fixture["protocol"].toString();
        QVERIFY((QStringList{"http", "socks5", "ss", "vless", "vless-reality", "vmess", "trojan"}.contains(profile)));
        report["protocol"] = profile;
        const auto client = fixture["client"].toString();
        QVERIFY((QStringList{"python-stdlib-ssl", "qt-network"}.contains(client)));
        report["client"] = client;
        const auto expectedProtocol = profile == "vless-reality" ? QString("vless") : profile;
        const QUrl http(fixture["http_url"].toString(), QUrl::StrictMode);
        const QUrl https(fixture["https_url"].toString(), QUrl::StrictMode);
        QVERIFY(http.isValid() && http.scheme() == "http" && http.host() == "127.0.0.1" && http.path() == "/xray-http");
        QVERIFY(https.isValid() && https.scheme() == "https" && https.host() == "localhost" && https.path() == "/xray-https");
        for (const auto &url : {http, https})
            QVERIFY(url.port() > 0 && url.port() <= 65535 && url.userInfo().isEmpty() && !url.hasQuery() && !url.hasFragment());
        const auto certificates = QSslCertificate::fromData(fixture["ca_pem"].toString().toUtf8());
        QVERIFY(!certificates.isEmpty() && QSslSocket::supportsSsl());
        const auto expected = fixture["expected_body"].toString().toUtf8();
        QVERIFY(expected == QByteArray("product-origin-ok"));
        const auto configurationPath = fixture["configuration_path"].toString();
        QVERIFY(QFileInfo(configurationPath).isAbsolute());
        QVERIFY(QFileInfo(configurationPath).absoluteFilePath() != QFileInfo(reportPath).absoluteFilePath());
        const auto reportGuard = qScopeGuard([&] { saveReport(); });
        QVERIFY(saveReport());
        QFile source(configurationPath); QVERIFY(source.open(QIODevice::ReadOnly));
        QVERIFY(source.size() > 0 && source.size() <= NodeImporter::MaximumBytes);
        const auto original = source.read(NodeImporter::MaximumBytes + 1); source.close();
        QVERIFY(!original.isEmpty() && original.size() <= NodeImporter::MaximumBytes);
        QTemporaryDir directory; QVERIFY(directory.isValid());
        const auto storePath = directory.filePath("JSON-节点.dpapi");
        QList<ProxyNode> nodes;
        QString selected;
        {
            NodeStore store(storePath);
            NodeImportService importer(&store);
            QSignalSpy applied(&importer, &NodeImportService::nodesApplied);
            importer.importFile(QUrl::fromLocalFile(configurationPath));
            QTRY_VERIFY_WITH_TIMEOUT(!importer.busy(), 15000);
            QVERIFY(importer.hasPreview());
            QCOMPARE(importer.preview().size(), 1);
            QCOMPARE(importer.preview().first().toMap()["protocol"].toString(), expectedProtocol);
            QVERIFY(store.nodes().isEmpty());
            report["file_preview"] = true;
            importer.confirmImport();
            QTRY_VERIFY_WITH_TIMEOUT(!importer.busy(), 15000);
            QVERIFY(!importer.hasPreview());
#ifdef Q_OS_WIN
            QCOMPARE(applied.count(), 1);
            QCOMPARE(store.nodes().size(), 1);
            nodes = store.nodes(); selected = nodes.first().id;
            QVERIFY(store.select(selected));
            QFile encrypted(storePath); QVERIFY(encrypted.open(QIODevice::ReadOnly));
            auto ciphertext = encrypted.readAll();
            QVERIFY(ciphertext.startsWith("SWIRLNODE1\n") && !ciphertext.contains(original));
            const auto authentication = nodes.first().parameters["authentication"].toObject();
            for (const auto &key : {"id", "password", "pass"}) {
                const auto credential = authentication[key].toString().toUtf8();
                if (!credential.isEmpty()) QVERIFY(!ciphertext.contains(credential));
            }
            ciphertext.fill('\0'); report["persisted"] = true;
#else
            // The production store has no portable encryption backend. Verify
            // that confirmation fails closed, then exercise the separately
            // declared parse/runtime boundary without pretending to persist.
            QCOMPARE(applied.count(), 0);
            QVERIFY(store.nodes().isEmpty() && !store.error().isEmpty());
            QVERIFY(!QFile::exists(storePath));
            const auto parsed = NodeImporter::parse(original);
            QVERIFY(parsed && parsed.nodes.size() == 1);
            nodes = parsed.nodes; selected = nodes.first().id;
#endif
            QVERIFY(nodes.first().sourceDocument == original);
            QCOMPARE(nodes.first().sourceNodeIndex, 0);
            QCOMPARE(nodes.first().protocol, expectedProtocol);
        }
#ifdef Q_OS_WIN
        {
            NodeStore restored(storePath);
            QVERIFY(restored.error().isEmpty());
            QCOMPARE(restored.nodes().size(), 1);
            QCOMPARE(restored.selectedId(), selected);
            QVERIFY(sameValues(nodes.first(), restored.nodes().first()));
            nodes = restored.nodes(); report["reloaded"] = true;
        }
#else
        const auto replayed = NodeImporter::parse(original);
        QVERIFY(replayed && replayed.nodes.size() == 1);
        auto replay = replayed.nodes.first(); replay.id = nodes.first().id;
        QVERIFY(sameValues(nodes.first(), replay));
#endif
        report["parameters_preserved"] = true;
        report["selected_protocol"] = nodes.first().protocol;
        QJsonObject outbound;
        QVERIFY(XrayJsonBridge::executableOutbound(nodes.first(), &outbound).isEmpty());
        QTcpServer reservation; reservation.setProxy(QNetworkProxy::NoProxy);
        QVERIFY(reservation.listen(QHostAddress::LocalHost));
        const auto proxyPort = reservation.serverPort(); reservation.close();
        const auto settings = options(nodes, proxyPort);
        QJsonObject config;
        QVERIFY(RustCoreEngine::configuration(settings, &config).isEmpty());
        QVERIFY(config["nodes"].toArray().first().toObject()["outbound"].toObject() == outbound);
        QCOMPARE(config["listen"], QJsonValue(QString("127.0.0.1:%1").arg(proxyPort)));
        RustCoreEngine engine;
        const auto stop = qScopeGuard([&] { engine.stop(); });
        engine.start(settings);
        QTRY_VERIFY_WITH_TIMEOUT(engine.status().apiHealthy, 5000);
        QVERIFY(engine.status().processAlive && engine.status().state == ProxyEngine::State::Running);
        QCOMPARE(engine.status().selectedNodeId, selected);
        QCOMPARE(engine.status().engineKind, QString("rust"));
        QCOMPARE(engine.status().processId, QCoreApplication::applicationPid());
        QVERIFY(engine.status().controlEndpoint.startsWith("in-process://SwirlRust/"));
        report["rust_core_started"] = true; report["in_process"] = true;
        if (client == "python-stdlib-ssl") {
            const auto responses = independentBusinessRequests(fixture, proxyPort);
            QVERIFY(!responses.isEmpty());
            report["http"] = responses["http"];
            report["https"] = responses["https"];
            QVERIFY(report["https"].toObject()["tls_shutdown_verified"].toBool());
            QVERIFY(report["http"].toObject()["transport_closed"].toBool());
            QVERIFY(report["https"].toObject()["transport_closed"].toBool());
        } else {
            report["http"] = httpRequest(http, proxyPort, expected + ":/xray-http");
            report["https"] = httpsRequest(https, proxyPort, certificates, expected + ":/xray-https");
        }
        QVERIFY(report["http"].toObject()["body_verified"].toBool());
        QVERIFY(report["https"].toObject()["body_verified"].toBool());
        QVERIFY(report["https"].toObject()["certificate_verified"].toBool());
        const bool sessionsClosed = QTest::qWaitFor([&] {
            engine.refresh();
            if (engine.status().rustAccepted < 2) return false;
            for (const auto &value : engine.status().connections)
                if (!value.toMap()["closed"].toBool()) return false;
            return true;
        }, 5000);
        QJsonArray sessions;
        for (const auto &value : engine.status().connections) {
            const auto row = value.toMap();
            sessions.append(QJsonObject{{"port", row["port"].toInt()}, {"closed", row["closed"].toBool()},
                {"state", row["transportState"].toString()}, {"upload", row["uploadBytes"].toLongLong()},
                {"download", row["downloadBytes"].toLongLong()}});
        }
        report["runtime"] = QJsonObject{{"accepted", engine.status().rustAccepted},
            {"failed", engine.status().rustFailed}, {"last_error_stage", engine.status().rustLastErrorStage},
            {"upload", engine.status().uploadTotal}, {"download", engine.status().downloadTotal},
            {"sessions", sessions}};
        QVERIFY(sessionsClosed);
        QVERIFY(engine.status().rustAccepted >= 2);
        QCOMPARE(engine.status().rustFailed, qint64(0));
        QVERIFY(engine.status().uploadTotal > 0 && engine.status().downloadTotal > 0);
        engine.stop();
        QVERIFY(!engine.status().apiHealthy && !engine.status().processAlive);
        report["stopped"] = true;
        QVERIFY(reservation.listen(QHostAddress::LocalHost, proxyPort)); reservation.close();
        report["listener_closed"] = true;
        QVERIFY(source.open(QIODevice::ReadOnly));
        QVERIFY(source.read(NodeImporter::MaximumBytes + 1) == original);
        QVERIFY(saveReport());
    }
};

int main(int argc, char **argv) {
    QCoreApplication application(argc, argv);
    XrayRuntimeTests tests;
    auto arguments = application.arguments();
    if (!qEnvironmentVariableIsSet("SWIRL_XRAY_QT_FIXTURE")) {
        // Default CTest runs every independent safety slot without skips. The
        // external peer harness explicitly selects nativeProductChain; asking
        // for that slot without its fixture is a hard error, never a pass.
        QStringList independent;
        bool selected = false;
        const auto *meta = tests.metaObject();
        for (int index = meta->methodOffset(); index < meta->methodCount(); ++index) {
            const auto method = meta->method(index);
            if (method.methodType() != QMetaMethod::Slot || method.parameterCount() != 0) continue;
            const auto name = QString::fromLatin1(method.name());
            for (const auto &argument : arguments.mid(1)) {
                if (argument.section(':', 0, 0) != name) continue;
                if (name == "nativeProductChain") {
                    qCritical("nativeProductChain requires the independent SWIRL_XRAY_QT_FIXTURE");
                    return 2;
                }
                selected = true;
            }
            if (name != "nativeProductChain" && !QStringList{"init", "cleanup", "initTestCase", "cleanupTestCase"}.contains(name))
                independent.append(name);
        }
        if (!selected) arguments.append(independent);
    }
    return QTest::qExec(&tests, arguments);
}

#include "XrayRuntimeTests.moc"
