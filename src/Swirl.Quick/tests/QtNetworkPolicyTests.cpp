#include "engine/NodeImportService.h"
#include "network/HttpRequestPolicy.h"

#include <QFile>
#include <QNetworkReply>
#include <QNetworkProxy>
#include <QSignalSpy>
#include <QSslCertificate>
#include <QSslConfiguration>
#include <QSslKey>
#include <QSslServer>
#include <QSslSocket>
#include <QStandardPaths>
#include <QTcpServer>
#include <QTemporaryDir>
#include <QTest>

namespace {
const QByteArray subscription =
    "proxies:\n  - {name: HTTP1-Fixture, type: socks5, server: 127.0.0.1, port: 1080}\n";

// A real loopback TLS server offers h2 first. On h2 it records negotiation and
// closes safely; no malformed HTTP/2 or exploit payload is sent. Successful
// downloads must arrive as HTTP/1.1 and reach the production parser.
class Origin final : public QObject {
public:
    QTcpServer http;
    QSslServer https;
    QByteArray content = subscription, location;
    QList<QByteArray> protocols, requests;
    int status = 200, disconnected = 0;
    bool secure = false, hanging = false;

    explicit Origin(const QSslConfiguration &configuration) {
        https.setSslConfiguration(configuration);
        connect(&http, &QTcpServer::newConnection, this, [this] { accept(http, false); });
        connect(&https, &QTcpServer::pendingConnectionAvailable, this, [this] { accept(https, true); });
    }
    bool listen(bool tls = true) {
        secure = tls;
        return tls ? https.listen(QHostAddress::LocalHost, 0) : http.listen(QHostAddress::LocalHost, 0);
    }
    QUrl url() const {
        return QUrl(QStringLiteral("%1://%2:%3/subscription")
            .arg(secure ? "https" : "http", secure ? "localhost" : "127.0.0.1")
            .arg(secure ? https.serverPort() : http.serverPort()));
    }
private:
    void accept(QTcpServer &server, bool tls) {
        while (server.hasPendingConnections()) {
            auto *socket = server.nextPendingConnection();
            connect(socket, &QTcpSocket::disconnected, this, [this] { ++disconnected; });
            connect(socket, &QTcpSocket::disconnected, socket, &QObject::deleteLater);
            if (tls) {
                auto *ssl = qobject_cast<QSslSocket *>(socket);
                const auto protocol = ssl ? ssl->sslConfiguration().nextNegotiatedProtocol() : QByteArray("missing-tls");
                protocols.append(protocol);
                if (protocol == "h2") {
                    socket->disconnectFromHost();
                    continue;
                }
            }
            const auto read = [this, socket] {
                auto data = socket->property("request").toByteArray() + socket->readAll();
                socket->setProperty("request", data);
                if (!data.contains("\r\n\r\n") || socket->property("answered").toBool()) return;
                socket->setProperty("answered", true);
                requests.append(data.left(data.indexOf("\r\n\r\n") + 4));
                if (hanging) return;
                socket->write("HTTP/1.1 " + QByteArray::number(status) + " Fixture\r\n"
                    + (location.isEmpty() ? QByteArray() : "Location: " + location + "\r\n")
                    + "Content-Type: application/yaml\r\nContent-Length: " + QByteArray::number(content.size())
                    + "\r\nConnection: close\r\n\r\n" + content);
                socket->disconnectFromHost();
            };
            connect(socket, &QTcpSocket::readyRead, socket, read);
            if (socket->bytesAvailable()) read();
        }
    }
};

struct Download {
    QTemporaryDir directory;
    NodeStore store{directory.filePath("nodes.dpapi")};
    NodeImportService service{&store};
    QList<ProxyNode> parsed;
    int applied = 0;
    Download() {
        // Observe the real download-to-parser boundary through the existing
        // owner callback. Persistence remains covered by Windows ImportTests.
        service.setConfigurationApplier([this](const NodeImporter::Result &result, const QString &, QString *) {
            parsed = result.nodes;
            ++applied;
            return true;
        });
    }
    ~Download() { service.shutdown(); }
};
}

class QtNetworkPolicyTests final : public QObject {
    Q_OBJECT
    QSslConfiguration original, trusted, serverConfiguration;
    QByteArray previousH2c;
    bool hadH2c = false;

    void verifyHttp1(const Origin &origin, int count = 1) {
        QCOMPARE(origin.requests.size(), count);
        for (const auto &protocol : origin.protocols) {
            QVERIFY2(protocol.isEmpty() || protocol == "http/1.1", protocol.constData());
        }
        for (const auto &request : origin.requests) {
            QCOMPARE(request.left(request.indexOf("\r\n")), QByteArray("GET /subscription HTTP/1.1"));
            QVERIFY(!request.toLower().contains("upgrade: h2c"));
            QVERIFY(!request.toLower().contains("http2-settings:"));
        }
    }
    void verifyParsed(const Download &download) {
        QCOMPARE(download.applied, 1);
        QCOMPARE(download.parsed.size(), 1);
        QCOMPARE(download.parsed.first().name, QStringLiteral("HTTP1-Fixture"));
        QCOMPARE(download.parsed.first().protocol, QStringLiteral("socks5"));
        QCOMPARE(download.parsed.first().port, quint16(1080));
        QVERIFY(download.store.nodes().isEmpty());
        QVERIFY(!QFile::exists(download.store.filePath()));
    }
private slots:
    void initTestCase() {
        QStandardPaths::setTestModeEnabled(true);
        QVERIFY2(QSslSocket::supportsSsl(), "A working TLS backend is required, not skipped");
        qInfo() << "Qt" << qVersion() << "TLS backend" << QSslSocket::activeBackend()
                << QSslSocket::sslLibraryVersionString();
        QFile certFile(QStringLiteral(SWIRL_FIXTURE_DIR "/localhost-cert.pem"));
        QFile keyFile(QStringLiteral(SWIRL_FIXTURE_DIR "/localhost-key.pem"));
        QVERIFY(certFile.open(QIODevice::ReadOnly));
        QVERIFY(keyFile.open(QIODevice::ReadOnly));
        const QSslCertificate certificate(certFile.readAll());
        const QSslKey key(keyFile.readAll(), QSsl::Rsa);
        QVERIFY(!certificate.isNull());
        QVERIFY(!key.isNull());
        original = QSslConfiguration::defaultConfiguration();
        trusted = original;
        trusted.addCaCertificate(certificate);
        serverConfiguration = original;
        serverConfiguration.setLocalCertificate(certificate);
        serverConfiguration.setPrivateKey(key);
        serverConfiguration.setPeerVerifyMode(QSslSocket::VerifyNone); // No client certificate is required.
        serverConfiguration.setAllowedNextProtocols({QByteArray("h2"), QByteArray("http/1.1")});
        hadH2c = qEnvironmentVariableIsSet("QT_NETWORK_H2C_ALLOWED");
        previousH2c = qgetenv("QT_NETWORK_H2C_ALLOWED");
        qputenv("QT_NETWORK_H2C_ALLOWED", "1");
    }
    void init() { QSslConfiguration::setDefaultConfiguration(trusted); }
    void cleanup() { QSslConfiguration::setDefaultConfiguration(original); }
    void cleanupTestCase() {
        if (hadH2c) qputenv("QT_NETWORK_H2C_ALLOWED", previousH2c);
        else qunsetenv("QT_NETWORK_H2C_ALLOWED");
    }

    void unprotectedClientNegotiatesHttp2PositiveControl() {
        Origin origin(serverConfiguration);
        QVERIFY(origin.listen());
        QNetworkAccessManager manager;
        manager.setProxy(QNetworkProxy::NoProxy);
        QNetworkRequest request(origin.url());
        request.setTransferTimeout(3000);
        auto *reply = manager.get(request);
        QSignalSpy finished(reply, &QNetworkReply::finished);
        QTRY_VERIFY_WITH_TIMEOUT(origin.protocols.contains("h2"), 5000);
        QTRY_COMPARE_WITH_TIMEOUT(finished.count(), 1, 5000);
        QCOMPARE(origin.requests.size(), 0);
        reply->deleteLater();
    }

    void policyOverridesExplicitHttp2AndDirectOptions() {
        Origin origin(serverConfiguration);
        QVERIFY(origin.listen());
        QNetworkAccessManager manager;
        manager.setProxy(QNetworkProxy::NoProxy);
        QNetworkRequest request(origin.url());
        request.setAttribute(QNetworkRequest::Http2AllowedAttribute, true);
        request.setAttribute(QNetworkRequest::Http2DirectAttribute, true);
        request.setAttribute(QNetworkRequest::Http2CleartextAllowedAttribute, true);
        SwirlNetwork::applyHttp1OnlyPolicy(request);
        request.setTransferTimeout(3000);
        auto *reply = manager.get(request);
        QSignalSpy finished(reply, &QNetworkReply::finished);
        QTRY_COMPARE_WITH_TIMEOUT(finished.count(), 1, 5000);
        QCOMPARE(reply->error(), QNetworkReply::NoError);
        QCOMPARE(reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt(), 200);
        QVERIFY(!reply->attribute(QNetworkRequest::Http2WasUsedAttribute).toBool());
        QCOMPARE(reply->readAll(), subscription);
        verifyHttp1(origin);
        reply->deleteLater();
    }

    void subscriptionHttpsDownloadsAndParsesOverHttp1() {
        Origin origin(serverConfiguration);
        QVERIFY(origin.listen());
        Download download;
        QVERIFY(download.directory.isValid());
        download.service.importUrl(origin.url());
        QTRY_VERIFY_WITH_TIMEOUT(!download.service.busy(), 5000);
        verifyParsed(download);
        QCOMPARE(origin.protocols.size(), 1);
        verifyHttp1(origin);
    }

    void subscriptionHttpsRedirectsStayOnHttp1() {
        Origin first(serverConfiguration), second(serverConfiguration);
        QVERIFY(first.listen());
        QVERIFY(second.listen());
        first.status = 302;
        first.location = second.url().toEncoded();
        Download download;
        download.service.importUrl(first.url());
        QTRY_VERIFY_WITH_TIMEOUT(!download.service.busy(), 5000);
        verifyParsed(download);
        QCOMPARE(first.protocols.size(), 1);
        QCOMPARE(second.protocols.size(), 1);
        verifyHttp1(first);
        verifyHttp1(second);
    }

    void cleartextSubscriptionIgnoresH2cEnvironment() {
        QCOMPARE(qgetenv("QT_NETWORK_H2C_ALLOWED"), QByteArray("1"));
        Origin origin(serverConfiguration);
        QVERIFY(origin.listen(false));
        Download download;
        download.service.importUrl(origin.url());
        QTRY_VERIFY_WITH_TIMEOUT(!download.service.busy(), 5000);
        verifyParsed(download);
        verifyHttp1(origin);
    }

    void subscriptionStillRejectsUntrustedTls() {
        QSslConfiguration::setDefaultConfiguration(original);
        Origin origin(serverConfiguration);
        QVERIFY(origin.listen());
        Download download;
        download.service.importUrl(origin.url());
        QTRY_VERIFY_WITH_TIMEOUT(!download.service.busy(), 5000);
        QCOMPARE(download.applied, 0);
        QVERIFY(download.store.nodes().isEmpty());
        QVERIFY(origin.requests.isEmpty());
        QVERIFY(download.service.message().contains(QStringLiteral("下载失败")));
    }

    void subscriptionStillRejectsHttpsDowngrade() {
        Origin first(serverConfiguration), plain(serverConfiguration);
        QVERIFY(first.listen());
        QVERIFY(plain.listen(false));
        first.status = 302;
        first.location = plain.url().toEncoded();
        Download download;
        download.service.importUrl(first.url());
        QTRY_VERIFY_WITH_TIMEOUT(!download.service.busy(), 5000);
        QCOMPARE(download.applied, 0);
        QVERIFY(download.store.nodes().isEmpty());
        QVERIFY(download.service.message().contains(QStringLiteral("降级")));
        verifyHttp1(first);
        QVERIFY(plain.requests.isEmpty());
    }

    void shutdownCancelsHangingHttp1Download() {
        Origin origin(serverConfiguration);
        origin.hanging = true;
        QVERIFY(origin.listen());
        Download download;
        QSignalSpy applied(&download.service, &NodeImportService::nodesApplied);
        download.service.importUrl(origin.url());
        QTRY_COMPARE_WITH_TIMEOUT(origin.requests.size(), 1, 5000);
        QVERIFY(download.service.busy());
        download.service.shutdown();
        QVERIFY(!download.service.busy());
        QTRY_COMPARE_WITH_TIMEOUT(origin.disconnected, 1, 5000);
        QCOMPARE(download.applied, 0);
        QCOMPARE(applied.count(), 0);
        verifyHttp1(origin);
    }
};

QTEST_GUILESS_MAIN(QtNetworkPolicyTests)
#include "QtNetworkPolicyTests.moc"
