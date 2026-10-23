#include "engine/NodeImportService.h"
#include "network/HttpRequestPolicy.h"

#include <QFile>
#include <QElapsedTimer>
#include <QJsonDocument>
#include <QJsonObject>
#include <QNetworkReply>
#include <QNetworkProxy>
#include <QProcess>
#include <QSignalSpy>
#include <QSslCertificate>
#include <QSslConfiguration>
#include <QSslError>
#include <QSslSocket>
#include <QStandardPaths>
#include <QTcpServer>
#include <QTemporaryDir>
#include <QTest>

namespace {
const QByteArray subscription =
    "proxies:\n  - {name: HTTP1-Fixture, type: socks5, server: 127.0.0.1, port: 1080}\n";

void reportClientTlsErrors(QNetworkReply *reply) {
    QObject::connect(reply, &QNetworkReply::sslErrors, reply, [](const QList<QSslError> &errors) {
        for (const auto &error : errors) qWarning() << "Native Qt TLS client:" << error.errorString();
    });
}

// The independent TLS peer offers h2 first and reports actual ALPN/request
// bytes. Qt retains its native client backend (including Secure Transport,
// which cannot provide server-side ALPN itself). No HTTP/2 payload is sent.
class Origin final : public QObject {
public:
    QTcpServer http;
    QProcess tlsProcess;
    QByteArray content = subscription, location;
    QList<QByteArray> protocols, requests;
    QStringList errors;
    int status = 200, disconnected = 0;
    bool secure = false, hanging = false, redirectOnce = false;

    explicit Origin(QString directory) : certificateDirectory(std::move(directory)) {
        connect(&http, &QTcpServer::newConnection, this, [this] { accept(); });
        connect(&tlsProcess, &QProcess::readyReadStandardOutput, this, [this] { events(); });
        connect(&tlsProcess, &QProcess::readyReadStandardError, this, [this] {
            diagnostics += tlsProcess.readAllStandardError();
        });
        connect(&tlsProcess, &QProcess::finished, this, [this](int code, QProcess::ExitStatus exit) {
            if (code != 0 || exit != QProcess::NormalExit)
                qWarning() << "Independent TLS fixture exited" << code << exit << error();
        });
    }
    ~Origin() override {
        if (tlsProcess.state() != QProcess::NotRunning) {
            send({{"command", "quit"}});
            tlsProcess.closeWriteChannel();
            if (!tlsProcess.waitForFinished(1000)) {
                tlsProcess.kill();
                tlsProcess.waitForFinished(1000);
            }
        }
    }
    bool listen(bool tls = true) {
        secure = tls;
        if (!tls) return http.listen(QHostAddress::LocalHost, 0);
        tlsProcess.start(QStringLiteral(SWIRL_TEST_PYTHON),
            {QStringLiteral(SWIRL_TLS_FIXTURE_SCRIPT), "--serve", certificateDirectory});
        if (!tlsProcess.waitForStarted(10000)) return false;
        QElapsedTimer timer;
        timer.start();
        while (!tlsPort && tlsProcess.state() != QProcess::NotRunning && timer.elapsed() < 10000) {
            tlsProcess.waitForReadyRead(100);
            events();
        }
        return tlsPort > 0;
    }
    QString error() const {
        return errors.join("; ") + " " + QString::fromUtf8(diagnostics) + " " + tlsProcess.errorString();
    }
    QUrl url() const {
        return QUrl(QStringLiteral("%1://%2:%3/subscription")
            .arg(secure ? "https" : "http", secure ? "localhost" : "127.0.0.1")
            .arg(secure ? tlsPort : http.serverPort()));
    }
private:
    QString certificateDirectory;
    QByteArray eventBuffer, diagnostics;
    int tlsPort = 0;

    void send(const QJsonObject &message) {
        tlsProcess.write(QJsonDocument(message).toJson(QJsonDocument::Compact) + '\n');
    }
    void events() {
        eventBuffer += tlsProcess.readAllStandardOutput();
        while (eventBuffer.contains('\n')) {
            const auto length = eventBuffer.indexOf('\n');
            QJsonParseError parseError;
            const auto event = QJsonDocument::fromJson(eventBuffer.left(length), &parseError).object();
            eventBuffer.remove(0, length + 1);
            if (parseError.error != QJsonParseError::NoError || event.isEmpty()) {
                errors.append("Invalid JSON from independent TLS fixture");
                continue;
            }
            const auto type = event.value("event").toString();
            if (type == "ready") tlsPort = event.value("port").toInt();
            else if (type == "protocol") protocols.append(event.value("value").toString().toLatin1());
            else if (type == "request") {
                requests.append(QByteArray::fromBase64(event.value("headers").toString().toLatin1()));
                send({{"id", event.value("id")}, {"status", status}, {"hanging", hanging},
                    {"location", QString::fromLatin1(location)}, {"body", QString::fromLatin1(content.toBase64())}});
                if (redirectOnce) { status = 200; location.clear(); redirectOnce = false; }
            } else if (type == "disconnected") ++disconnected;
            else if (type == "error") {
                errors.append(event.value("message").toString());
                qWarning() << "Independent TLS fixture:" << errors.last();
            } else errors.append("Unexpected event from independent TLS fixture");
        }
    }
    void accept() {
        while (http.hasPendingConnections()) {
            auto *socket = http.nextPendingConnection();
            connect(socket, &QTcpSocket::disconnected, this, [this] { ++disconnected; });
            connect(socket, &QTcpSocket::disconnected, socket, &QObject::deleteLater);
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
    QSslConfiguration original, trusted;
    QTemporaryDir certificateDirectory;
    QByteArray previousH2c;
    bool hadH2c = false;

    void verifyHttp1(const Origin &origin, int count = 1) {
        QVERIFY2(origin.errors.isEmpty(), qPrintable(origin.error()));
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
        QVERIFY(certificateDirectory.isValid());
        QProcess prepare;
        prepare.start(QStringLiteral(SWIRL_TEST_PYTHON),
            {QStringLiteral(SWIRL_TLS_FIXTURE_SCRIPT), "--prepare", certificateDirectory.path()});
        QVERIFY2(prepare.waitForStarted(10000), qPrintable(prepare.errorString()));
        QVERIFY2(prepare.waitForFinished(30000), qPrintable(prepare.errorString()));
        const auto diagnostics = prepare.readAllStandardError();
        QVERIFY2(prepare.exitStatus() == QProcess::NormalExit && prepare.exitCode() == 0, diagnostics.constData());
        qInfo().noquote() << "Independent TLS fixture" << prepare.readAllStandardOutput().trimmed();
        QFile certFile(certificateDirectory.filePath("ca.pem"));
        QVERIFY(certFile.open(QIODevice::ReadOnly));
        const QSslCertificate certificate(certFile.readAll());
        QVERIFY(!certificate.isNull());
        original = QSslConfiguration::defaultConfiguration();
        trusted = original;
        trusted.addCaCertificate(certificate);
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
        Origin origin(certificateDirectory.path());
        QVERIFY2(origin.listen(), qPrintable(origin.error()));
        QNetworkAccessManager manager;
        manager.setProxy(QNetworkProxy::NoProxy);
        QNetworkRequest request(origin.url());
        request.setTransferTimeout(3000);
        auto *reply = manager.get(request);
        reportClientTlsErrors(reply);
        QSignalSpy finished(reply, &QNetworkReply::finished);
        QTRY_VERIFY_WITH_TIMEOUT(origin.protocols.contains("h2"), 5000);
        QTRY_COMPARE_WITH_TIMEOUT(finished.count(), 1, 5000);
        QCOMPARE(origin.requests.size(), 0);
        reply->deleteLater();
    }

    void policyOverridesExplicitHttp2AndDirectOptions() {
        Origin origin(certificateDirectory.path());
        QVERIFY2(origin.listen(), qPrintable(origin.error()));
        QNetworkAccessManager manager;
        manager.setProxy(QNetworkProxy::NoProxy);
        QNetworkRequest request(origin.url());
        request.setAttribute(QNetworkRequest::Http2AllowedAttribute, true);
        request.setAttribute(QNetworkRequest::Http2DirectAttribute, true);
        request.setAttribute(QNetworkRequest::Http2CleartextAllowedAttribute, true);
        SwirlNetwork::applyHttp1OnlyPolicy(request);
        request.setTransferTimeout(3000);
        auto *reply = manager.get(request);
        reportClientTlsErrors(reply);
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
        Origin origin(certificateDirectory.path());
        QVERIFY2(origin.listen(), qPrintable(origin.error()));
        Download download;
        QVERIFY(download.directory.isValid());
        download.service.importUrl(origin.url());
        QTRY_VERIFY_WITH_TIMEOUT(!download.service.busy(), 5000);
        verifyParsed(download);
        QCOMPARE(origin.protocols.size(), 1);
        verifyHttp1(origin);
    }

    void subscriptionHttpsRedirectsStayOnHttp1() {
        Origin origin(certificateDirectory.path());
        QVERIFY2(origin.listen(), qPrintable(origin.error()));
        origin.status = 302;
        origin.location = origin.url().toEncoded();
        origin.redirectOnce = true;
        Download download;
        download.service.importUrl(origin.url());
        QTRY_VERIFY_WITH_TIMEOUT(!download.service.busy(), 5000);
        verifyParsed(download);
        QCOMPARE(origin.protocols.size(), 2);
        verifyHttp1(origin, 2);
    }

    void subscriptionCrossOriginRedirectIsRejectedBeforeTls() {
        Origin first(certificateDirectory.path()), second(certificateDirectory.path());
        QVERIFY2(first.listen(), qPrintable(first.error()));
        QVERIFY2(second.listen(), qPrintable(second.error()));
        first.status = 302;
        first.location = second.url().toEncoded();
        Download download;
        download.service.importUrl(first.url());
        QTRY_VERIFY_WITH_TIMEOUT(!download.service.busy(), 5000);
        QCOMPARE(download.applied, 0);
        QCOMPARE(first.protocols.size(), 1);
        verifyHttp1(first);
        QVERIFY(second.protocols.isEmpty());
        QVERIFY(second.requests.isEmpty());
        QVERIFY(download.service.message().contains(QStringLiteral("不属于同一来源")));
    }

    void cleartextSubscriptionIgnoresH2cEnvironment() {
        QCOMPARE(qgetenv("QT_NETWORK_H2C_ALLOWED"), QByteArray("1"));
        Origin origin(certificateDirectory.path());
        QVERIFY(origin.listen(false));
        Download download;
        download.service.importUrl(origin.url());
        QTRY_VERIFY_WITH_TIMEOUT(!download.service.busy(), 5000);
        verifyParsed(download);
        verifyHttp1(origin);
    }

    void subscriptionStillRejectsUntrustedTls() {
        QSslConfiguration::setDefaultConfiguration(original);
        Origin origin(certificateDirectory.path());
        QVERIFY2(origin.listen(), qPrintable(origin.error()));
        Download download;
        download.service.importUrl(origin.url());
        QTRY_VERIFY_WITH_TIMEOUT(!download.service.busy(), 5000);
        QCOMPARE(download.applied, 0);
        QVERIFY(download.store.nodes().isEmpty());
        QVERIFY(origin.requests.isEmpty());
        QVERIFY(download.service.message().contains(QStringLiteral("下载失败")));
    }

    void subscriptionStillRejectsHttpsDowngrade() {
        Origin first(certificateDirectory.path()), plain(certificateDirectory.path());
        QVERIFY2(first.listen(), qPrintable(first.error()));
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
        Origin origin(certificateDirectory.path());
        origin.hanging = true;
        QVERIFY2(origin.listen(), qPrintable(origin.error()));
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
