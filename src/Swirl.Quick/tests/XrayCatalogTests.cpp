#include <QtTest>
#include <QFile>
#include <QJsonArray>
#include <QJsonDocument>
#include <QNetworkProxy>
#include <QPointer>
#include <QSettings>
#include <QSignalSpy>
#include <QStandardPaths>
#include <QTcpServer>
#include <QTcpSocket>
#include <QTemporaryDir>
#include <QTimer>
#include <QUuid>
#include "app/StoragePaths.h"
#include "engine/EngineController.h"
#include "engine/RustCoreEngine.h"
#include "LoopbackPortLease.h"

namespace {
ProxyNode legacyNode(quint16 port, const QString &name = QStringLiteral("catalog fixture")) {
    ProxyNode node;
    node.id = QUuid::createUuid().toString(QUuid::WithoutBraces);
    node.name = name;
    node.protocol = QStringLiteral("http");
    node.host = QStringLiteral("127.0.0.1");
    node.port = port;
    return node;
}

EngineStartOptions probeOptions(const ProxyNode &node) {
    EngineStartOptions options;
    options.nodes = {node};
    options.selectedNodeId = node.id;
    options.routingMode = QStringLiteral("global");
    // The Rust-only EngineStartOptions has no external executable setting.
    return options;
}

QUrl probeUrl() { return QUrl(QStringLiteral("http://127.0.0.1:9/catalog-probe")); }

QByteArray readFile(const QString &path) {
    QFile file(path);
    return file.open(QIODevice::ReadOnly) ? file.readAll() : QByteArray{};
}

QVariantMap editorInput(const ProxyNode &node) {
    return {{"name", node.name}, {"protocol", node.protocol}, {"host", node.host},
        {"port", node.port}, {"username", node.username}, {"password", node.password}};
}

QByteArray jsonDocument(const QString &tag = QStringLiteral("JSON 日本語 catalog")) {
    const QJsonObject outbound{{"tag", tag}, {"protocol", "http"},
        {"settings", QJsonObject{{"servers", QJsonArray{QJsonObject{
            {"address", "127.0.0.1"}, {"port", 9},
            {"users", QJsonArray{QJsonObject{{"user", "synthetic-catalog-user"},
                {"pass", "SYNTHETIC-CATALOG-SECRET"}}}}}}}}}};
    return QJsonDocument(QJsonObject{{"outbounds", QJsonArray{outbound}}}).toJson(QJsonDocument::Compact);
}

// A real loopback endpoint accepts the native Rust HTTP CONNECT request, then
// deliberately withholds or rejects it. No origin request succeeds here: the
// observations prove cancellation and immutable runtime ownership, not useful
// HTTP/HTTPS traffic or provider authentication.
class HeldConnectPeer final : public QTcpServer {
public:
    explicit HeldConnectPeer(bool rejectImmediately = false) : reject(rejectImmediately) {
        connect(this, &QTcpServer::newConnection, this, [this] {
            while (hasPendingConnections()) {
                auto *socket = nextPendingConnection();
                sockets.append(socket);
                connect(socket, &QTcpSocket::readyRead, this, [this, socket] {
                    if (socket->property("recorded").toBool()) { socket->readAll(); return; }
                    auto bytes = socket->property("headers").toByteArray() + socket->readAll();
                    if (bytes.size() > 16384) { socket->abort(); return; }
                    socket->setProperty("headers", bytes);
                    if (!bytes.contains("\r\n\r\n")) return;
                    socket->setProperty("recorded", true);
                    headers.append(bytes);
                    if (reject) reply(socket);
                });
                connect(socket, &QTcpSocket::disconnected, this, [this, socket] {
                    ++disconnections;
                    socket->deleteLater();
                });
            }
        });
    }
    void releaseAll() {
        for (const auto &socket : sockets) if (socket) reply(socket);
    }
    QList<QByteArray> headers;
    int disconnections = 0;
    bool reject = false;
private:
    static void reply(QTcpSocket *socket) {
        if (socket->state() != QAbstractSocket::ConnectedState) return;
        socket->write("HTTP/1.1 502 Fixture Rejection\r\nContent-Length: 0\r\nConnection: close\r\n\r\n");
        socket->disconnectFromHost();
    }
    QList<QPointer<QTcpSocket>> sockets;
};

#ifdef Q_OS_WIN
quint16 freeRuntimePort() {
    LoopbackPortLease ports;
    if (!ports.reserve()) {
        QTest::qFail(qPrintable(ports.errorString()), __FILE__, __LINE__);
        return 0;
    }
    return ports.proxyPort();
}

class SubscriptionFixture final : public QTcpServer {
public:
    SubscriptionFixture() {
        connect(this, &QTcpServer::newConnection, this, [this] {
            while (hasPendingConnections()) {
                auto *socket = nextPendingConnection();
                connect(socket, &QTcpSocket::disconnected, socket, &QObject::deleteLater);
                connect(socket, &QTcpSocket::readyRead, this, [this, socket] {
                    if (socket->property("replied").toBool()) { socket->readAll(); return; }
                    const auto bytes = socket->property("request").toByteArray() + socket->readAll();
                    if (bytes.size() > 16384) { socket->abort(); return; }
                    socket->setProperty("request", bytes);
                    if (!bytes.contains("\r\n\r\n")) return;
                    socket->setProperty("replied", true);
                    ++requests;
                    socket->write("HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\nContent-Length: "
                        + QByteArray::number(payload.size()) + "\r\n\r\n" + payload);
                    socket->disconnectFromHost();
                });
            }
        });
    }
    QUrl url() const { return QUrl(QStringLiteral("http://127.0.0.1:%1/catalog.json").arg(serverPort())); }
    void setNode(const QString &name, quint16 port, const QString &password) {
        const QJsonObject node{{"name", name}, {"type", "http"}, {"server", "127.0.0.1"},
            {"port", port}, {"username", "synthetic-provider-user"}, {"password", password}};
        payload = QJsonDocument(QJsonObject{{"proxies", QJsonArray{node}}}).toJson(QJsonDocument::Compact);
    }
    QByteArray payload;
    int requests = 0;
};
#endif
}

class XrayCatalogTests final : public QObject {
    Q_OBJECT
    QTemporaryDir settingsDirectory;

    static void verifyEmptyResults(const NodeTestService &service) {
        QVERIFY(service.results().isEmpty());
        QCOMPARE(service.total(), 0);
        QCOMPARE(service.completed(), 0);
        QCOMPARE(service.succeeded(), 0);
        QCOMPARE(service.failed(), 0);
    }

private slots:
    void initTestCase() {
        QStandardPaths::setTestModeEnabled(true);
        SwirlPaths::initializeTestStorage();
        QVERIFY(settingsDirectory.isValid());
        QCoreApplication::setOrganizationName(QStringLiteral("SwirlCatalogTests"));
        QCoreApplication::setApplicationName(QStringLiteral("XrayCatalog"));
        QSettings::setDefaultFormat(QSettings::IniFormat);
        QSettings::setPath(QSettings::IniFormat, QSettings::UserScope, settingsDirectory.path());
        QNetworkProxy::setApplicationProxy(QNetworkProxy::NoProxy);
    }

    void init() {
        QSettings settings;
        settings.clear();
        settings.setValue(QStringLiteral("Proxy/routingMode"), QStringLiteral("global"));
        settings.setValue(QStringLiteral("Proxy/preferCompatibility"), false);
        settings.sync();
        QCOMPARE(settings.status(), QSettings::NoError);
    }

    void completedNativeProbeInvalidationClearsCounters() {
        HeldConnectPeer peer(true);
        QVERIFY(peer.listen(QHostAddress::LocalHost, 0));
        const auto node = legacyNode(peer.serverPort());
        NodeTestService service;
        service.start(probeOptions(node), {node.id}, probeUrl());
        QTRY_COMPARE_WITH_TIMEOUT(peer.headers.size(), 1, 5000);
        QVERIFY(peer.headers.first().startsWith("CONNECT "));
        QTRY_COMPARE_WITH_TIMEOUT(service.completed(), 1, 10000);
        QTRY_VERIFY_WITH_TIMEOUT(!service.busy(), 5000);
        QCOMPARE(service.total(), 1);
        QCOMPARE(service.failed(), 1);
        QCOMPARE(service.succeeded(), 0);
        QCOMPARE(service.result(node.id).value("engineKind").toString(), QStringLiteral("rust"));
        QVERIFY(!service.result(node.id).value("success").toBool());
        service.invalidateResults();
        verifyEmptyResults(service);
        QVERIFY(!service.busy());
        QVERIFY(service.message().contains(QStringLiteral("旧测试结果已清除")));
    }

    void invalidationCancelsQueuedNativeProbeStart() {
        HeldConnectPeer peer;
        QVERIFY(peer.listen(QHostAddress::LocalHost, 0));
        const auto node = legacyNode(peer.serverPort());
        NodeTestService service;
        service.start(probeOptions(node), {node.id}, probeUrl());
        const auto runners = service.findChildren<ProxyEngine *>();
        QCOMPARE(runners.size(), 1);
        QPointer<ProxyEngine> runner = runners.first();
        QCOMPARE(runner->status().engineKind, QStringLiteral("rust"));
        QCOMPARE(runner->status().state, ProxyEngine::State::Starting);
        QVERIFY(!runner->property("probeStarted").toBool());
        QCOMPARE(peer.headers.size(), 0);
        // R1 starts on a worker thread. Invalidate before consuming its first
        // snapshot: neither queued startup nor a late snapshot may issue I/O.
        service.invalidateResults();
        QTRY_VERIFY_WITH_TIMEOUT(runner.isNull(), 5000);
        QVERIFY(!service.busy());
        QCOMPARE(peer.headers.size(), 0);
        verifyEmptyResults(service);
    }

    void invalidationCancelsQueuedNativeProbeAfterStartup() {
        HeldConnectPeer peer;
        QVERIFY(peer.listen(QHostAddress::LocalHost, 0));
        const auto node = legacyNode(peer.serverPort());
        NodeTestService service;
        service.start(probeOptions(node), {node.id}, probeUrl());
        const auto runners = service.findChildren<ProxyEngine *>();
        QCOMPARE(runners.size(), 1);
        QPointer<ProxyEngine> runner = runners.first();
        bool cancelledAtReady = false;
        connect(runner, &ProxyEngine::statusChanged, &service, [&] {
            if (cancelledAtReady || !runner->status().apiHealthy) return;
            QVERIFY(runner->status().processAlive);
            QCOMPARE(runner->status().processId, QCoreApplication::applicationPid());
            QVERIFY(runner->property("probeStarted").toBool());
            QCOMPARE(peer.headers.size(), 0);
            cancelledAtReady = true;
            service.invalidateResults();
        });
        QTRY_VERIFY_WITH_TIMEOUT(cancelledAtReady && runner.isNull(), 5000);
        QVERIFY(!service.busy());
        QCOMPARE(peer.headers.size(), 0);
        verifyEmptyResults(service);
    }

    void invalidationCancelsRequestAndRejectsLateCompletion() {
        HeldConnectPeer oldPeer;
        HeldConnectPeer nextPeer(true);
        QVERIFY(oldPeer.listen(QHostAddress::LocalHost, 0));
        QVERIFY(nextPeer.listen(QHostAddress::LocalHost, 0));
        const auto oldNode = legacyNode(oldPeer.serverPort());
        const auto nextNode = legacyNode(nextPeer.serverPort());
        NodeTestService service;
        service.start(probeOptions(oldNode), {oldNode.id}, probeUrl());
        QTRY_COMPARE_WITH_TIMEOUT(oldPeer.headers.size(), 1, 5000);
        QVERIFY(service.busy());
        QCOMPARE(service.completed(), 0);
        const auto runners = service.findChildren<ProxyEngine *>();
        QCOMPARE(runners.size(), 1);
        QPointer<ProxyEngine> retired = runners.first();
        QCOMPARE(retired->status().engineKind, QStringLiteral("rust"));
        QVERIFY(retired->status().nodeBusy);
        QTimer::singleShot(0, &oldPeer, [&oldPeer] { oldPeer.releaseAll(); });
        service.invalidateResults();
        QTRY_VERIFY_WITH_TIMEOUT(!service.busy(), 5000);
        verifyEmptyResults(service);
        service.start(probeOptions(nextNode), {nextNode.id}, probeUrl());
        QTRY_COMPARE_WITH_TIMEOUT(nextPeer.headers.size(), 1, 5000);
        QTRY_COMPARE_WITH_TIMEOUT(service.completed(), 1, 10000);
        QTRY_VERIFY_WITH_TIMEOUT(!service.busy() && retired.isNull(), 5000);
        QTRY_COMPARE_WITH_TIMEOUT(oldPeer.disconnections, 1, 5000);
        QVERIFY(service.result(oldNode.id).isEmpty());
        QCOMPARE(service.results().size(), 1);
        QCOMPARE(service.total(), 1);
        QCOMPARE(service.failed(), 1);
        QCOMPARE(service.result(nextNode.id).value("engineKind").toString(), QStringLiteral("rust"));
    }

    void ambiguousPolicyNamesRejectWithoutMutation() {
        QTemporaryDir directory;
        QVERIFY(directory.isValid());
        const auto path = directory.filePath(QStringLiteral("catalog.dpapi"));
        EngineController controller(std::make_unique<RustCoreEngine>(), nullptr, path);
#ifdef Q_OS_WIN
        QVERIFY(controller.saveNode(editorInput(legacyNode(19001, QStringLiteral("saved node")))));
        QVERIFY(controller.chooseNode(controller.nodeCatalog().first().toMap().value("id").toString()));
#endif
        const auto oldCatalog = controller.nodeCatalog();
        const auto oldSelection = controller.selectedNodeId();
        const auto oldNetwork = QJsonObject::fromVariantMap(controller.networkConfigurationSnapshot());
        const auto oldFile = readFile(path);
        auto first = legacyNode(19002, QStringLiteral("ambiguous"));
        auto second = legacyNode(19003, first.name);
        const QVariantMap group{{"name", "Choice"}, {"type", "select"},
            {"proxies", QStringList{first.name}}};
        const QVariantMap network{{"groups", QVariantList{group}},
            {"rules", QStringList{QStringLiteral("MATCH,Choice")}}};
        QSignalSpy catalogChanged(&controller, &EngineController::nodeCatalogChanged);
        QVERIFY(!controller.importNodesAndConfiguration({first, second}, {}, network));
        QVERIFY(controller.networkConfigurationError().contains(QStringLiteral("歧义")));
        QCOMPARE(controller.nodeCatalog(), oldCatalog);
        QCOMPARE(controller.selectedNodeId(), oldSelection);
        QCOMPARE(QJsonObject::fromVariantMap(controller.networkConfigurationSnapshot()), oldNetwork);
        QVERIFY(readFile(path) == oldFile);
        QCOMPARE(catalogChanged.count(), 0);
        QVERIFY(!controller.processAlive());
        controller.shutdown();
    }

    void emptySelectionDoesNotStartDirect() {
        QTemporaryDir directory;
        QVERIFY(directory.isValid());
        auto native = std::make_unique<RustCoreEngine>();
        const auto *runtime = native.get();
        EngineController controller(std::move(native), nullptr, directory.filePath(QStringLiteral("catalog.dpapi")));
        QVERIFY(controller.selectedNodeId().isEmpty());
        controller.connectNode({});
        QVERIFY(!controller.processAlive());
        QVERIFY(!runtime->status().directSession);
        QVERIFY(!controller.requestSucceeded());
        QVERIFY(controller.nodeError().contains(QStringLiteral("未选择")));
        controller.shutdown();
    }

#ifndef Q_OS_WIN
    void unavailableEncryptionKeepsCatalogAndProbeResults() {
        QTemporaryDir directory;
        QVERIFY(directory.isValid());
        const auto path = directory.filePath(QStringLiteral("catalog.dpapi"));
        HeldConnectPeer peer(true);
        QVERIFY(peer.listen(QHostAddress::LocalHost, 0));
        EngineController controller(std::make_unique<RustCoreEngine>(), nullptr, path);
        const auto node = legacyNode(peer.serverPort());
        controller.tests()->start(probeOptions(node), {node.id}, probeUrl());
        QTRY_COMPARE_WITH_TIMEOUT(controller.tests()->completed(), 1, 10000);
        QTRY_VERIFY_WITH_TIMEOUT(!controller.tests()->busy(), 5000);
        const auto previousResults = controller.tests()->results();
        const auto oldNetwork = QJsonObject::fromVariantMap(controller.networkConfigurationSnapshot());
        QSignalSpy applied(controller.imports(), &NodeImportService::nodesApplied);
        QSignalSpy changed(&controller, &EngineController::nodeCatalogChanged);
        controller.imports()->importText(QString::fromUtf8(jsonDocument()));
        QTRY_VERIFY_WITH_TIMEOUT(!controller.imports()->busy(), 10000);
        QVERIFY(controller.imports()->hasPreview());
        QCOMPARE(controller.imports()->preview().size(), 1);
        QVERIFY(controller.nodeCatalog().isEmpty());
        controller.imports()->confirmImport();
        QVERIFY(controller.imports()->busy());
        QTRY_VERIFY_WITH_TIMEOUT(!controller.imports()->busy(), 10000);
        QVERIFY(controller.imports()->message().contains(QStringLiteral("DPAPI")));
        QVERIFY(controller.nodeCatalog().isEmpty());
        QVERIFY(controller.selectedNodeId().isEmpty());
        QCOMPARE(QJsonObject::fromVariantMap(controller.networkConfigurationSnapshot()), oldNetwork);
        QCOMPARE(controller.tests()->results(), previousResults);
        QCOMPARE(applied.count(), 0);
        QCOMPARE(changed.count(), 0);
        QVERIFY(!QFile::exists(path));
        QVERIFY(!QFile::exists(path + QStringLiteral(".selected")));
        QVERIFY(!controller.processAlive());
        controller.shutdown();
    }
#else
    void asyncJsonCommitInvalidatesCompletedAndRunningProbes() {
        QTemporaryDir directory;
        QVERIFY(directory.isValid());
        const auto path = directory.filePath(QStringLiteral("日本語 catalog.dpapi"));
        HeldConnectPeer peer(true);
        QVERIFY(peer.listen(QHostAddress::LocalHost, 0));
        EngineController controller(std::make_unique<RustCoreEngine>(), nullptr, path);
        QVERIFY(controller.saveNode(editorInput(legacyNode(peer.serverPort()))));
        const auto selected = controller.nodeCatalog().first().toMap().value("id").toString();
        QVERIFY(controller.chooseNode(selected));
        controller.testSelectedNode(selected, probeUrl());
        QTRY_COMPARE_WITH_TIMEOUT(controller.tests()->completed(), 1, 10000);
        QTRY_VERIFY_WITH_TIMEOUT(!controller.tests()->busy(), 5000);
        QVERIFY(controller.nodes().first().toMap().contains("testHttp"));
        QSignalSpy applied(controller.imports(), &NodeImportService::nodesApplied);
        const auto document = jsonDocument();
        controller.imports()->importText(QString::fromUtf8(document));
        QTRY_VERIFY_WITH_TIMEOUT(!controller.imports()->busy(), 10000);
        QVERIFY(controller.imports()->hasPreview());
        QCOMPARE(controller.nodeCatalog().size(), 1);
        QCOMPARE(controller.tests()->completed(), 1);
        controller.imports()->confirmImport();
        QVERIFY(controller.imports()->busy());
        QTRY_VERIFY_WITH_TIMEOUT(!controller.imports()->busy(), 10000);
        QCOMPARE(applied.count(), 1);
        QCOMPARE(controller.nodeCatalog().size(), 2);
        QCOMPARE(controller.selectedNodeId(), selected);
        verifyEmptyResults(*controller.tests());
        for (const auto &row : controller.nodes()) QVERIFY(!row.toMap().contains("testHttp"));
        const auto encrypted = readFile(path);
        QVERIFY(!encrypted.isEmpty());
        QVERIFY(!encrypted.contains("SYNTHETIC-CATALOG-SECRET"));
        QVERIFY(!encrypted.contains(document));
        NodeStore reloaded(path);
        QCOMPARE(reloaded.nodes().size(), 2);
        QCOMPARE(reloaded.selectedId(), selected);
        int restored = 0;
        for (const auto &node : reloaded.nodes()) if (node.isXray()) {
            QVERIFY(node.sourceDocument == document);
            // Replay restores typed credentials and the authoritative native
            // candidate without claiming a successful business connection.
            const auto outbound = node.originalConfiguration.value("outbound").toObject();
            const auto servers = outbound.value("settings").toObject().value("servers").toArray();
            QCOMPARE(servers.size(), 1);
            const auto users = servers.first().toObject().value("users").toArray();
            QCOMPARE(users.size(), 1);
            QVERIFY(users.first().toObject().value("pass").toString()
                == QStringLiteral("SYNTHETIC-CATALOG-SECRET"));
            QVERIFY(node.nativeExecutable);
            QCOMPARE(node.parameterState, QStringLiteral("valid"));
            QCOMPARE(node.nativeOutbound.value("type").toString(), QStringLiteral("http_connect"));
            QVERIFY(node.username == QStringLiteral("synthetic-catalog-user"));
            QVERIFY(node.password == QStringLiteral("SYNTHETIC-CATALOG-SECRET"));
            QVERIFY(node.nativeOutbound.value("auth").toObject().value("password").toString()
                == QStringLiteral("SYNTHETIC-CATALOG-SECRET"));
            QVERIFY(node.nativeOutbound.value("auth").toObject().value("username").toString() == node.username);
            QVERIFY(!node.publicInfo().value("networkVerified").toBool());
            ++restored;
        }
        QCOMPARE(restored, 1);

        peer.reject = false;
        controller.testSelectedNode(selected, probeUrl());
        QTRY_COMPARE_WITH_TIMEOUT(peer.headers.size(), 2, 5000);
        QVERIFY(controller.tests()->busy());
        controller.imports()->importText(QString::fromUtf8(jsonDocument(QStringLiteral("renamed source tag"))));
        QTRY_VERIFY_WITH_TIMEOUT(!controller.imports()->busy(), 10000);
        QVERIFY(controller.imports()->hasPreview());
        QTimer::singleShot(0, &peer, [&peer] { peer.releaseAll(); });
        controller.imports()->confirmImport();
        QTRY_VERIFY_WITH_TIMEOUT(!controller.imports()->busy() && !controller.tests()->busy(), 10000);
        QCOMPARE(applied.count(), 2);
        QCOMPARE(controller.nodeCatalog().size(), 2);
        QCOMPARE(controller.selectedNodeId(), selected);
        verifyEmptyResults(*controller.tests());
        QTRY_COMPARE_WITH_TIMEOUT(peer.disconnections, 2, 5000);
        for (const auto &row : controller.nodes()) QVERIFY(!row.toMap().contains("testHttp"));
        controller.shutdown();
    }

    void runningSubscriptionRefreshKeepsOwnedRuntimeSnapshot() {
        QTemporaryDir directory;
        QVERIFY(directory.isValid());
        const auto path = directory.filePath(QStringLiteral("catalog.dpapi"));
        HeldConnectPeer oldPeer, newPeer;
        SubscriptionFixture provider;
        QVERIFY(oldPeer.listen(QHostAddress::LocalHost, 0));
        QVERIFY(newPeer.listen(QHostAddress::LocalHost, 0));
        QVERIFY(provider.listen(QHostAddress::LocalHost, 0));
        provider.setNode(QStringLiteral("provider-node"), oldPeer.serverPort(), QStringLiteral("SYNTHETIC-OLD"));
        auto native = std::make_unique<RustCoreEngine>();
        auto *runtime = native.get();
        EngineController controller(std::move(native), nullptr, path);
        const auto listenerPort = freeRuntimePort();
        QVERIFY(listenerPort != 0);
        controller.setProxyPort(listenerPort);
        QVERIFY(controller.imports()->saveSubscription({}, QStringLiteral("controlled provider"), provider.url(), 360, false));
        const auto sourceId = controller.imports()->providers().first().toMap().value("id").toString();
        QSignalSpy applied(controller.imports(), &NodeImportService::nodesApplied);
        controller.imports()->refreshSubscription(sourceId);
        QTRY_VERIFY_WITH_TIMEOUT(!controller.imports()->busy(), 10000);
        QCOMPARE(applied.count(), 1);
        QCOMPARE(controller.nodeCatalog().size(), 1);
        const auto selected = controller.nodeCatalog().first().toMap().value("id").toString();
        controller.connectNode(selected);
        QTRY_VERIFY_WITH_TIMEOUT(controller.processAlive() && controller.apiHealthy(), 5000);
        QCOMPARE(runtime->status().processId, QCoreApplication::applicationPid());
        QCOMPARE(controller.activeNodeId(), selected);
        QCOMPARE(controller.activeProxyPort(), int(listenerPort));
        const auto session = runtime->status().sessionId;
        QVERIFY(!session.isEmpty());
        QVERIFY(!controller.requestSucceeded());

        provider.setNode(QStringLiteral("provider-node"), newPeer.serverPort(), QStringLiteral("SYNTHETIC-NEW"));
        controller.imports()->refreshSubscription(sourceId);
        QTRY_VERIFY_WITH_TIMEOUT(!controller.imports()->busy(), 10000);
        QCOMPARE(applied.count(), 2);
        QCOMPARE(controller.nodeCatalog().size(), 1);
        QCOMPARE(controller.nodeCatalog().first().toMap().value("port").toInt(), int(newPeer.serverPort()));
        QCOMPARE(controller.selectedNodeId(), selected);
        QCOMPARE(controller.activeNodeId(), selected);
        QCOMPARE(runtime->status().sessionId, session);
        QVERIFY(controller.nodeError().contains(QStringLiteral("启动时配置")));
        controller.testNode(probeUrl());
        QTRY_COMPARE_WITH_TIMEOUT(oldPeer.headers.size(), 1, 5000);
        QCOMPARE(newPeer.headers.size(), 0);
        const auto oldAuth = QByteArray("synthetic-provider-user:SYNTHETIC-OLD").toBase64();
        QVERIFY(oldPeer.headers.first().contains(oldAuth));
        oldPeer.releaseAll();
        QTRY_VERIFY_WITH_TIMEOUT(!controller.nodeBusy(), 10000);
        QVERIFY(!controller.requestSucceeded());

        provider.setNode(QStringLiteral("replacement-node"), newPeer.serverPort(), QStringLiteral("SYNTHETIC-REPLACEMENT"));
        controller.imports()->refreshSubscription(sourceId);
        QTRY_VERIFY_WITH_TIMEOUT(!controller.imports()->busy(), 10000);
        QCOMPARE(applied.count(), 3);
        QCOMPARE(controller.nodeCatalog().size(), 1);
        const auto replacement = controller.nodeCatalog().first().toMap().value("id").toString();
        QVERIFY(replacement != selected);
        QVERIFY(controller.selectedNodeId().isEmpty());
        QCOMPARE(controller.activeNodeId(), selected);
        QCOMPARE(runtime->status().sessionId, session);
        QVERIFY(controller.nodeError().contains(QStringLiteral("移除")));
        QVERIFY(controller.processAlive());
        QVERIFY(!controller.deleteNode(replacement));
        controller.testNode(probeUrl());
        QTRY_COMPARE_WITH_TIMEOUT(oldPeer.headers.size(), 2, 5000);
        QCOMPARE(newPeer.headers.size(), 0);
        QVERIFY(oldPeer.headers.last().contains(oldAuth));
        oldPeer.releaseAll();
        QTRY_VERIFY_WITH_TIMEOUT(!controller.nodeBusy(), 10000);
        controller.disconnectNode();
        QTRY_VERIFY_WITH_TIMEOUT(!controller.processAlive(), 5000);
        controller.connectNode({});
        QVERIFY(!controller.processAlive());
        QVERIFY(!runtime->status().directSession);
        QVERIFY(controller.nodeError().contains(QStringLiteral("未选择")));
        controller.connectNode(replacement);
        QTRY_VERIFY_WITH_TIMEOUT(controller.processAlive() && controller.apiHealthy(), 5000);
        QVERIFY(runtime->status().sessionId != session);
        QCOMPARE(controller.activeNodeId(), replacement);
        controller.testNode(probeUrl());
        QTRY_COMPARE_WITH_TIMEOUT(newPeer.headers.size(), 1, 5000);
        QCOMPARE(oldPeer.headers.size(), 2);
        QVERIFY(newPeer.headers.first().contains(QByteArray("synthetic-provider-user:SYNTHETIC-REPLACEMENT").toBase64()));
        newPeer.releaseAll();
        QTRY_VERIFY_WITH_TIMEOUT(!controller.nodeBusy(), 10000);
        QVERIFY(!controller.requestSucceeded());
        controller.shutdown();
        QVERIFY(!controller.processAlive());
        QTcpServer releasedListener;
        QVERIFY(releasedListener.listen(QHostAddress::LocalHost, listenerPort));
        NodeStore reloaded(path);
        QCOMPARE(reloaded.nodes().size(), 1);
        QCOMPARE(reloaded.selectedId(), replacement);
    }
#endif
};

QTEST_GUILESS_MAIN(XrayCatalogTests)
#include "XrayCatalogTests.moc"
