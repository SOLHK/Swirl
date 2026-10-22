#include <QtTest>
#include <QElapsedTimer>
#include <QFile>
#include <QJsonArray>
#include <QJsonDocument>
#include <QMutex>
#include <QMutexLocker>
#include <QPointer>
#include <QSignalSpy>
#include <QSslCertificate>
#include <QSslConfiguration>
#include <QSslKey>
#include <QSslServer>
#include <QSslSocket>
#include <QTcpServer>
#include <QTemporaryDir>
#include <QUrlQuery>
#include <functional>
#include <memory>
#include "engine/NodeImportService.h"

namespace {
const auto Token = QStringLiteral("SYNTHETIC-DOWNLOAD-TOKEN");
const auto Uuid = QStringLiteral("11111111-2222-4333-8444-555555555555");

QByteArray configuration(const QString &name = QStringLiteral("HTTPS 下载节点 日本語")) {
    const QJsonObject user{{"id", Uuid}, {"encryption", "none"}};
    const QJsonObject endpoint{{"address", "proxy.example.invalid"}, {"port", 443},
        {"users", QJsonArray{user}}};
    const QJsonObject outbound{{"protocol", "vless"}, {"tag", name},
        {"settings", QJsonObject{{"vnext", QJsonArray{endpoint}}}}};
    return QJsonDocument(QJsonObject{{"outbounds", QJsonArray{outbound}}}).toJson(QJsonDocument::Compact);
}

// Only the client trust store is changed, for this test process and scope.
// VerifyPeer remains enabled. VerifyNone below applies solely to the fixture
// server's optional client certificate request, not the download client.
class FixtureTrust final {
public:
    explicit FixtureTrust(bool trusted = true) : original(QSslConfiguration::defaultConfiguration()) {
        QFile certificateFile(QStringLiteral(SWIRL_FIXTURE_DIR "/localhost-cert.pem"));
        QFile keyFile(QStringLiteral(SWIRL_FIXTURE_DIR "/localhost-key.pem"));
        if (!certificateFile.open(QIODevice::ReadOnly) || !keyFile.open(QIODevice::ReadOnly)) return;
        certificate = QSslCertificate(certificateFile.readAll());
        key = QSslKey(keyFile.readAll(), QSsl::Rsa);
        if (certificate.isNull() || key.isNull()) return;
        auto client = original;
        auto authorities = client.caCertificates();
        authorities.removeAll(certificate);
        if (trusted) authorities.append(certificate);
        client.setCaCertificates(authorities);
        client.setPeerVerifyMode(QSslSocket::VerifyPeer);
        QSslConfiguration::setDefaultConfiguration(client);
        server = original;
        server.setLocalCertificate(certificate);
        server.setPrivateKey(key);
        server.setPeerVerifyMode(QSslSocket::VerifyNone);
        valid = true;
    }
    ~FixtureTrust() { QSslConfiguration::setDefaultConfiguration(original); }
    bool valid = false;
    QSslConfiguration server;
    QSslCertificate certificate;
private:
    QSslConfiguration original;
    QSslKey key;
};

// Real loopback TLS and HTTP. The request target is kept only in test memory;
// it is never emitted through Qt logging or exposed to the production model.
class HttpsFixture final : public QSslServer {
public:
    explicit HttpsFixture(const QSslConfiguration &configuration) {
        setSslConfiguration(configuration);
        setHandshakeTimeout(5000);
        connect(this, &QSslServer::startedEncryptionHandshake, this, [this](QSslSocket *) {
            ++handshakeStarts;
        });
        connect(this, &QTcpServer::pendingConnectionAvailable, this, [this] {
            while (hasPendingConnections()) {
                auto *socket = qobject_cast<QSslSocket *>(nextPendingConnection());
                if (!socket) continue;
                sockets.append(socket);
                auto request = std::make_shared<QByteArray>();
                auto handled = std::make_shared<bool>(false);
                const auto consume = [this, socket, request, handled] {
                    if (*handled) { socket->readAll(); return; }
                    request->append(socket->readAll());
                    if (request->size() > 16384) { socket->abort(); return; }
                    if (!request->contains("\r\n\r\n")) return;
                    *handled = true;
                    const auto line = request->left(request->indexOf("\r\n"));
                    const auto pieces = line.split(' ');
                    const auto target = pieces.size() > 1 ? pieces.at(1) : QByteArray{};
                    ++requests;
                    targets.append(target);
                    if (respond) respond(socket, target);
                };
                connect(socket, &QSslSocket::readyRead, this, consume);
                connect(socket, &QSslSocket::disconnected, this, [this, socket] {
                    ++disconnections;
                    socket->deleteLater();
                });
                consume();
            }
        });
    }
    ~HttpsFixture() override {
        close();
        for (const auto &socket : sockets) if (socket) {
            socket->disconnect(this);
            socket->abort();
        }
    }
    QUrl url(const QString &path = QStringLiteral("/config.json")) const {
        QUrl value;
        value.setScheme(QStringLiteral("https"));
        value.setHost(QStringLiteral("127.0.0.1"));
        value.setPort(serverPort());
        value.setPath(path);
        QUrlQuery query;
        query.addQueryItem(QStringLiteral("token"), Token);
        value.setQuery(query);
        return value;
    }
    static void reply(QSslSocket *socket, const QByteArray &body, int status = 200,
                      const QByteArray &location = {}) {
        QByteArray head = "HTTP/1.1 " + QByteArray::number(status) + " Fixture\r\n";
        head += "Content-Type: application/json\r\nCache-Control: no-store\r\nConnection: close\r\n";
        if (!location.isEmpty()) head += "Location: " + location + "\r\n";
        head += "Content-Length: " + QByteArray::number(body.size()) + "\r\n\r\n";
        socket->write(head);
        socket->write(body);
        socket->disconnectFromHost();
    }
    std::function<void(QSslSocket *, const QByteArray &)> respond;
    QList<QByteArray> targets;
    int requests = 0;
    int handshakeStarts = 0;
    int disconnections = 0;
private:
    QList<QPointer<QSslSocket>> sockets;
};

struct ImportFixture {
    QTemporaryDir directory;
    NodeStore store{directory.filePath(QStringLiteral("nodes.dpapi"))};
    NodeImportService service{&store};
    QSignalSpy applied{&service, &NodeImportService::nodesApplied};
    int commits = 0;
    bool manualSource = false;
    NodeImporter::Result committed;
    QStringList messages;
    ImportFixture() {
        // This observer checks the explicit confirmation boundary. Real DPAPI
        // persistence is tested separately by XrayImportTests/XrayStoreTests.
        service.setConfigurationApplier([this](const auto &result, const QString &source, QString *) {
            ++commits;
            manualSource = source.isEmpty();
            committed = result;
            return true;
        });
        QObject::connect(&service, &NodeImportService::changed, &service, [this] {
            messages.append(service.message());
        });
    }
    ~ImportFixture() { service.shutdown(); }
    QByteArray publicState() const {
        return messages.join('\n').toUtf8()
            + QJsonDocument::fromVariant(service.preview()).toJson(QJsonDocument::Compact)
            + QJsonDocument::fromVariant(service.providers()).toJson(QJsonDocument::Compact)
            + QJsonDocument::fromVariant(store.publicRows()).toJson(QJsonDocument::Compact);
    }
};

QMutex messageMutex;
QStringList loggedMessages;
QtMessageHandler previousMessageHandler = nullptr;
void captureMessage(QtMsgType type, const QMessageLogContext &context, const QString &message) {
    QtMessageHandler previous;
    {
        QMutexLocker lock(&messageMutex);
        loggedMessages.append(message);
        previous = previousMessageHandler;
    }
    if (previous) previous(type, context, message);
}
class LogCapture final {
public:
    LogCapture() {
        QMutexLocker lock(&messageMutex);
        loggedMessages.clear();
        previousMessageHandler = qInstallMessageHandler(captureMessage);
    }
    ~LogCapture() { qInstallMessageHandler(previousMessageHandler); }
    QString text() const {
        QMutexLocker lock(&messageMutex);
        return loggedMessages.join('\n');
    }
};
}

class XrayDownloadTests final : public QObject {
    Q_OBJECT
    static void verifyUnchanged(const ImportFixture &import) {
        QVERIFY(!import.service.busy());
        QVERIFY(!import.service.hasPreview());
        QCOMPARE(import.commits, 0);
        QCOMPARE(import.applied.count(), 0);
        QVERIFY(import.store.nodes().isEmpty());
        QVERIFY(import.store.selectedId().isEmpty());
        QVERIFY(!QFile::exists(import.store.filePath()));
        QVERIFY(!import.publicState().contains(Token.toUtf8()));
    }
private slots:
    void initTestCase() {
        QVERIFY2(QSslSocket::supportsSsl(), "Qt must provide a real TLS backend; these tests cannot be skipped");
        FixtureTrust trust;
        QVERIFY(trust.valid);
        QVERIFY(trust.certificate.effectiveDate() <= QDateTime::currentDateTimeUtc());
        QVERIFY(trust.certificate.expiryDate() > QDateTime::currentDateTimeUtc());
        QCOMPARE(QSslConfiguration::defaultConfiguration().peerVerifyMode(), QSslSocket::VerifyPeer);
    }
    void trustedHttpsUsesStrictRustPreviewAndExplicitConfirmation() {
        FixtureTrust trust; QVERIFY(trust.valid);
        HttpsFixture server(trust.server);
        const auto document = configuration();
        server.respond = [&](QSslSocket *socket, const auto &) { HttpsFixture::reply(socket, document); };
        QVERIFY(server.listen(QHostAddress::LocalHost, 0));
        ImportFixture import; QVERIFY(import.directory.isValid());
        import.service.importUrl(server.url());
        QTRY_VERIFY_WITH_TIMEOUT(import.service.hasPreview(), 10000);
        QCOMPARE(server.requests, 1);
        QVERIFY(server.handshakeStarts >= 1);
        QVERIFY(server.targets.first().contains(Token.toUtf8()));
        QCOMPARE(import.commits, 0);
        QCOMPARE(import.applied.count(), 0);
        QCOMPARE(import.service.preview().size(), 1);
        QVERIFY(import.store.nodes().isEmpty());
        QVERIFY(!import.publicState().contains(Token.toUtf8()));
        QVERIFY(!import.publicState().contains(Uuid.toUtf8()));
        QVERIFY(!import.service.message().contains(QStringLiteral("真实联网成功")));
        import.service.confirmImport();
        QCOMPARE(import.commits, 1);
        QCOMPARE(import.applied.count(), 1);
        QVERIFY(import.manualSource);
        QVERIFY(!import.service.hasPreview());
        QCOMPARE(import.committed.nodes.first().sourceDocument, document);
        QCOMPARE(import.committed.nodes.first().importSource, QStringLiteral("url"));
    }
    void untrustedCertificateFailsBeforeHttp() {
        FixtureTrust trust(false); QVERIFY(trust.valid);
        HttpsFixture server(trust.server);
        server.respond = [](QSslSocket *socket, const auto &) { HttpsFixture::reply(socket, configuration()); };
        QVERIFY(server.listen(QHostAddress::LocalHost, 0));
        ImportFixture import;
        import.service.importUrl(server.url());
        QTRY_VERIFY_WITH_TIMEOUT(!import.service.busy(), 10000);
        QVERIFY(server.handshakeStarts >= 1);
        QCOMPARE(server.requests, 0);
        QVERIFY(!import.service.message().isEmpty());
        verifyUnchanged(import);
    }
    void sameOriginRelativeRedirectPreservesAuthorizedRequest() {
        FixtureTrust trust; QVERIFY(trust.valid);
        HttpsFixture server(trust.server);
        server.respond = [](QSslSocket *socket, const QByteArray &target) {
            if (target.startsWith("/first?"))
                HttpsFixture::reply(socket, {}, 302, "/final?token=" + Token.toUtf8());
            else HttpsFixture::reply(socket, configuration());
        };
        QVERIFY(server.listen(QHostAddress::LocalHost, 0));
        ImportFixture import;
        import.service.importUrl(server.url(QStringLiteral("/first")));
        QTRY_VERIFY_WITH_TIMEOUT(import.service.hasPreview(), 10000);
        QCOMPARE(server.requests, 2);
        QVERIFY(server.targets.first().startsWith("/first?"));
        QVERIFY(server.targets.last().startsWith("/final?"));
        QCOMPARE(import.commits, 0);
        QVERIFY(!import.publicState().contains(Token.toUtf8()));
        import.service.cancelImport();
        verifyUnchanged(import);
    }
    void crossOriginPortReceivesNoRequestOrToken() {
        FixtureTrust trust; QVERIFY(trust.valid);
        HttpsFixture first(trust.server), target(trust.server);
        QVERIFY(first.listen(QHostAddress::LocalHost, 0));
        QVERIFY(target.listen(QHostAddress::LocalHost, 0));
        first.respond = [&](QSslSocket *socket, const auto &) {
            HttpsFixture::reply(socket, {}, 302, target.url().toEncoded());
        };
        target.respond = [](QSslSocket *socket, const auto &) { HttpsFixture::reply(socket, configuration()); };
        ImportFixture import;
        import.service.importUrl(first.url());
        QTRY_VERIFY_WITH_TIMEOUT(!import.service.busy(), 10000);
        QCOMPARE(first.requests, 1);
        QCOMPARE(target.requests, 0);
        QCOMPARE(target.handshakeStarts, 0);
        verifyUnchanged(import);
    }
    void crossOriginHostReceivesNoRequestOrToken() {
        FixtureTrust trust; QVERIFY(trust.valid);
        HttpsFixture server(trust.server);
        QVERIFY(server.listen(QHostAddress::LocalHost, 0));
        auto redirect = server.url(QStringLiteral("/other-host"));
        redirect.setHost(QStringLiteral("localhost"));
        int targetCalls = 0;
        server.respond = [&](QSslSocket *socket, const QByteArray &target) {
            if (target.startsWith("/other-host")) {
                ++targetCalls;
                HttpsFixture::reply(socket, configuration());
            } else HttpsFixture::reply(socket, {}, 302, redirect.toEncoded());
        };
        ImportFixture import;
        import.service.importUrl(server.url());
        QTRY_VERIFY_WITH_TIMEOUT(!import.service.busy(), 10000);
        QCOMPARE(server.requests, 1);
        QCOMPARE(targetCalls, 0);
        verifyUnchanged(import);
    }
    void redirectLoopIsBounded() {
        FixtureTrust trust; QVERIFY(trust.valid);
        HttpsFixture server(trust.server);
        server.respond = [](QSslSocket *socket, const auto &) {
            HttpsFixture::reply(socket, {}, 302, "/loop?token=" + Token.toUtf8());
        };
        QVERIFY(server.listen(QHostAddress::LocalHost, 0));
        ImportFixture import;
        import.service.importUrl(server.url());
        QTRY_VERIFY_WITH_TIMEOUT(!import.service.busy(), 10000);
        QCOMPARE(server.requests, 6); // Initial request plus at most five redirects.
        QVERIFY(import.service.message().contains(QStringLiteral("重定向")));
        verifyUnchanged(import);
    }
    void httpsDowngradeNeverConnectsToPlainHttp() {
        FixtureTrust trust; QVERIFY(trust.valid);
        HttpsFixture server(trust.server);
        QTcpServer plain;
        int plainConnections = 0;
        connect(&plain, &QTcpServer::newConnection, &plain, [&] {
            while (plain.hasPendingConnections()) {
                auto *socket = plain.nextPendingConnection();
                ++plainConnections;
                socket->abort();
                socket->deleteLater();
            }
        });
        QVERIFY(server.listen(QHostAddress::LocalHost, 0));
        QVERIFY(plain.listen(QHostAddress::LocalHost, 0));
        auto redirect = server.url(); redirect.setScheme(QStringLiteral("http")); redirect.setPort(plain.serverPort());
        server.respond = [&](QSslSocket *socket, const auto &) {
            HttpsFixture::reply(socket, {}, 302, redirect.toEncoded());
        };
        ImportFixture import;
        import.service.importUrl(server.url());
        QTRY_VERIFY_WITH_TIMEOUT(!import.service.busy(), 10000);
        QCOMPARE(server.requests, 1);
        QCOMPARE(plainConnections, 0);
        verifyUnchanged(import);
    }
    void localFileAndUserInfoUrlsAreRejected() {
        FixtureTrust trust; QVERIFY(trust.valid);
        HttpsFixture server(trust.server);
        server.respond = [](QSslSocket *socket, const auto &) { HttpsFixture::reply(socket, configuration()); };
        QVERIFY(server.listen(QHostAddress::LocalHost, 0));
        ImportFixture import;
        const auto path = import.directory.filePath(QStringLiteral("不得读取.json"));
        QFile file(path); QVERIFY(file.open(QIODevice::WriteOnly));
        const auto bytes = configuration(); QCOMPARE(file.write(bytes), bytes.size()); file.close();
        const auto fileUrl = QUrl::fromLocalFile(path);
        import.service.importUrl(fileUrl);
        QVERIFY(!import.service.busy());
        verifyUnchanged(import);
        auto credentials = server.url();
        credentials.setUserName(QStringLiteral("fixture-user"));
        credentials.setPassword(QStringLiteral("SYNTHETIC-URL-PASSWORD"));
        import.service.importUrl(credentials);
        QVERIFY(!import.service.busy());
        QCOMPARE(server.requests, 0);
        QVERIFY(!import.publicState().contains("SYNTHETIC-URL-PASSWORD"));
        verifyUnchanged(import);
        server.respond = [&](QSslSocket *socket, const auto &) {
            HttpsFixture::reply(socket, {}, 302, fileUrl.toEncoded());
        };
        import.service.importUrl(server.url());
        QTRY_VERIFY_WITH_TIMEOUT(!import.service.busy(), 10000);
        QCOMPARE(server.requests, 1);
        verifyUnchanged(import);
        QVERIFY(file.open(QIODevice::ReadOnly)); QCOMPARE(file.readAll(), bytes);
    }
    void oversizedChunkedBodyIsRejected() {
        FixtureTrust trust; QVERIFY(trust.valid);
        HttpsFixture server(trust.server);
        auto body = configuration(); body.append(NodeImporter::MaximumBytes + 1 - body.size(), ' ');
        server.respond = [&](QSslSocket *socket, const auto &) {
            socket->write("HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nTransfer-Encoding: chunked\r\nConnection: close\r\n\r\n");
            socket->write(QByteArray::number(body.size(), 16) + "\r\n");
            socket->write(body);
            socket->write("\r\n0\r\n\r\n");
            socket->disconnectFromHost();
        };
        QVERIFY(server.listen(QHostAddress::LocalHost, 0));
        ImportFixture import;
        import.service.importUrl(server.url());
        QTRY_VERIFY_WITH_TIMEOUT(!import.service.busy(), 10000);
        QCOMPARE(server.requests, 1);
        QVERIFY(import.service.message().contains(QStringLiteral("4 MiB")));
        verifyUnchanged(import);
    }
    void oversizedContentLengthIsRejectedBeforeBodyOrTimeout() {
        FixtureTrust trust; QVERIFY(trust.valid);
        HttpsFixture server(trust.server);
        server.respond = [](QSslSocket *socket, const auto &) {
            socket->write("HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: "
                + QByteArray::number(NodeImporter::MaximumBytes + 1) + "\r\nConnection: keep-alive\r\n\r\n");
            socket->flush(); // Intentionally no body or connection close.
        };
        QVERIFY(server.listen(QHostAddress::LocalHost, 0));
        ImportFixture import;
        import.service.importUrl(server.url());
        QTRY_VERIFY_WITH_TIMEOUT(!import.service.busy(), 5000);
        QCOMPARE(server.requests, 1);
        QVERIFY(import.service.message().contains(QStringLiteral("4 MiB")));
        QTRY_COMPARE_WITH_TIMEOUT(server.disconnections, 1, 5000);
        verifyUnchanged(import);
    }
    void truncatedDownloadDoesNotImportOtherwiseValidJson() {
        FixtureTrust trust; QVERIFY(trust.valid);
        HttpsFixture server(trust.server);
        const auto body = configuration();
        server.respond = [&](QSslSocket *socket, const auto &) {
            socket->write("HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: "
                + QByteArray::number(body.size() + 64) + "\r\nConnection: close\r\n\r\n");
            socket->write(body);
            socket->disconnectFromHost();
        };
        QVERIFY(server.listen(QHostAddress::LocalHost, 0));
        ImportFixture import;
        import.service.importUrl(server.url());
        QTRY_VERIFY_WITH_TIMEOUT(!import.service.busy(), 10000);
        QCOMPARE(server.requests, 1);
        verifyUnchanged(import);
    }
    void downloadedDuplicateKeysUseStrictRustRejection() {
        FixtureTrust trust; QVERIFY(trust.valid);
        HttpsFixture server(trust.server);
        server.respond = [](QSslSocket *socket, const auto &) {
            HttpsFixture::reply(socket, R"({"protocol":"vless","protocol":"vmess","settings":{"password":"SYNTHETIC-BODY-PASSWORD"}})");
        };
        QVERIFY(server.listen(QHostAddress::LocalHost, 0));
        ImportFixture import;
        import.service.importUrl(server.url());
        QTRY_VERIFY_WITH_TIMEOUT(!import.service.busy(), 10000);
        QCOMPARE(server.requests, 1);
        QVERIFY(import.service.message().contains(QStringLiteral("DuplicateJsonKey")));
        QVERIFY(!import.publicState().contains("SYNTHETIC-BODY-PASSWORD"));
        verifyUnchanged(import);
    }
    void cancellationClosesDownloadAndAllowsFreshPreview() {
        FixtureTrust trust; QVERIFY(trust.valid);
        HttpsFixture server(trust.server);
        const auto oldBody = configuration(QStringLiteral("Canceled old node"));
        const auto freshBody = configuration(QStringLiteral("Fresh node"));
        server.respond = [&](QSslSocket *socket, const QByteArray &target) {
            if (target.startsWith("/fresh?")) {
                HttpsFixture::reply(socket, freshBody);
            } else {
                socket->write("HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: "
                    + QByteArray::number(oldBody.size()) + "\r\nConnection: keep-alive\r\n\r\n");
                socket->write(oldBody.left(oldBody.size() / 2));
                socket->flush();
            }
        };
        QVERIFY(server.listen(QHostAddress::LocalHost, 0));
        ImportFixture import;
        import.service.importUrl(server.url(QStringLiteral("/slow")));
        QTRY_COMPARE_WITH_TIMEOUT(server.requests, 1, 10000);
        QVERIFY(import.service.busy());
        import.service.cancelImport();
        verifyUnchanged(import);
        QTRY_COMPARE_WITH_TIMEOUT(server.disconnections, 1, 5000);
        import.service.importUrl(server.url(QStringLiteral("/fresh")));
        QTRY_VERIFY_WITH_TIMEOUT(import.service.hasPreview(), 10000);
        QCOMPARE(server.requests, 2);
        QCOMPARE(import.service.preview().first().toMap().value("name").toString(), QStringLiteral("Fresh node"));
        import.service.confirmImport();
        QCOMPARE(import.commits, 1);
        QCOMPARE(import.committed.nodes.first().sourceDocument, freshBody);
        QCOMPARE(import.applied.count(), 1);
        QVERIFY(!import.publicState().contains(Token.toUtf8()));
    }
    void stalledServerReachesDownloadTimeout() {
        FixtureTrust trust; QVERIFY(trust.valid);
        HttpsFixture server(trust.server);
        server.respond = [](QSslSocket *, const auto &) { /* Keep TLS open without sending HTTP data. */ };
        QVERIFY(server.listen(QHostAddress::LocalHost, 0));
        ImportFixture import;
        QElapsedTimer timer; timer.start();
        import.service.importUrl(server.url());
        QTRY_COMPARE_WITH_TIMEOUT(server.requests, 1, 10000);
        QVERIFY(import.service.busy());
        QTRY_VERIFY_WITH_TIMEOUT(!import.service.busy(), 22000);
        QVERIFY(timer.elapsed() < 30000);
        QVERIFY(!import.service.message().isEmpty());
        verifyUnchanged(import);
    }
    void tokenBearingHttpFailureNeverReachesUiOrLogs() {
        LogCapture logs;
        FixtureTrust trust; QVERIFY(trust.valid);
        HttpsFixture server(trust.server);
        server.respond = [](QSslSocket *socket, const auto &) {
            HttpsFixture::reply(socket, Token.toUtf8() + " SYNTHETIC-ERROR-BODY-PASSWORD", 403);
        };
        QVERIFY(server.listen(QHostAddress::LocalHost, 0));
        ImportFixture import;
        import.service.importUrl(server.url(QStringLiteral("/private/") + Token));
        QTRY_VERIFY_WITH_TIMEOUT(!import.service.busy(), 10000);
        QCOMPARE(server.requests, 1);
        QVERIFY(import.service.message().contains(QStringLiteral("403")));
        QVERIFY(!import.publicState().contains("SYNTHETIC-ERROR-BODY-PASSWORD"));
        QVERIFY(!logs.text().contains(Token));
        QVERIFY(!logs.text().contains(QStringLiteral("SYNTHETIC-ERROR-BODY-PASSWORD")));
        verifyUnchanged(import);
    }
};
QTEST_GUILESS_MAIN(XrayDownloadTests)
#include "XrayDownloadTests.moc"
