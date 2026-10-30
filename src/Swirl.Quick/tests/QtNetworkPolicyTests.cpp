#include "engine/NodeImportService.h"
#include "network/HttpRequestPolicy.h"

#include <QFile>
#include <QCryptographicHash>
#include <QDateTime>
#include <QElapsedTimer>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QNetworkAccessManager>
#include <QNetworkReply>
#include <QNetworkProxy>
#include <QPointer>
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
#include <functional>

namespace {
const QByteArray subscription =
    "proxies:\n  - {name: HTTP1-Fixture, type: socks5, server: 127.0.0.1, port: 1080}\n";

void reportClientTlsErrors(QNetworkReply *reply, const QSslCertificate &fixtureCa) {
    QObject::connect(reply, &QNetworkReply::sslErrors, reply, [reply, fixtureCa](const QList<QSslError> &errors) {
        const auto actual = reply->sslConfiguration();
        qWarning() << "Native Qt TLS trust:" << "configuredCAcount" << actual.caCertificates().size()
                   << "fixtureCApresent" << actual.caCertificates().contains(fixtureCa);
        for (qsizetype i = 0; i < qMin<qsizetype>(4, errors.size()); ++i)
            qWarning() << "Native Qt TLS client:" << int(errors[i].error()) << errors[i].errorString().left(256);
    });
}

QJsonObject replyEvidence(QNetworkReply *reply, const QSslCertificate &fixtureCa) {
    if (!reply) return {{"available", false}};
    const auto configuration = reply->sslConfiguration();
    const auto peer = configuration.peerCertificate();
    const auto proxy = reply->manager()->proxy();
    return {{"available", true}, {"error", int(reply->error())},
        {"errorString", reply->errorString().left(1024)},
        {"requestUrl", reply->request().url().toString(QUrl::FullyEncoded)},
        {"replyUrl", reply->url().toString(QUrl::FullyEncoded)},
        {"finished", reply->isFinished()},
        {"httpStatus", reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt()},
        {"encrypted", reply->attribute(QNetworkRequest::ConnectionEncryptedAttribute).toBool()},
        {"proxyType", int(proxy.type())}, {"proxyHost", proxy.hostName()},
        {"configuredCAcount", int(configuration.caCertificates().size())},
        {"fixtureCApresent", configuration.caCertificates().contains(fixtureCa)},
        {"peerVerifyMode", int(configuration.peerVerifyMode())},
        {"configuredProtocol", int(configuration.protocol())},
        {"sessionProtocol", int(configuration.sessionProtocol())},
        {"peerCertificatePresent", !peer.isNull()},
        {"peerNotBeforeUtc", peer.effectiveDate().toUTC().toString(Qt::ISODateWithMs)},
        {"peerNotAfterUtc", peer.expiryDate().toUTC().toString(Qt::ISODateWithMs)}};
}

// Declared after the observed client/server objects in each test, so assertion
// returns record their still-live state without any extra request, wait or retry.
class FailureDiagnostics final {
public:
    explicit FailureDiagnostics(std::function<QJsonObject()> snapshot) : snapshot(std::move(snapshot)) {}
    ~FailureDiagnostics() {
        if (!QTest::currentTestFailed()) return;
        auto evidence = snapshot();
        evidence.insert("test", QString::fromLatin1(QTest::currentTestFunction()));
        evidence.insert("observedUtc", QDateTime::currentDateTimeUtc().toString(Qt::ISODateWithMs));
        evidence.insert("qt", QString::fromLatin1(qVersion()));
        evidence.insert("tlsBackend", QSslSocket::activeBackend());
        evidence.insert("tlsLibrary", QSslSocket::sslLibraryVersionString());
        qWarning().noquote() << "HTTP_POLICY_FAILURE" << QJsonDocument(evidence).toJson(QJsonDocument::Compact);
    }
private:
    std::function<QJsonObject()> snapshot;
};

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
    QJsonObject evidence() const {
        QJsonArray negotiated;
        for (const auto &protocol : protocols) negotiated.append(QString::fromLatin1(protocol));
        return {{"url", url().toString(QUrl::FullyEncoded)}, {"ready", readyEvent},
            {"acceptedConnections", acceptedConnections}, {"acceptEvents", acceptEvents},
            {"protocols", negotiated}, {"requests", int(requests.size())}, {"disconnected", disconnected},
            {"errors", QJsonArray::fromStringList(errors)}, {"lastErrorEvent", lastErrorEvent},
            {"processState", int(tlsProcess.state())}, {"processError", int(tlsProcess.error())},
            {"processErrorString", tlsProcess.errorString().left(512)},
            {"serverStderr", QString::fromUtf8(diagnostics).left(2048)},
            {"partialEvent", QString::fromUtf8(eventBuffer).left(1024)}};
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
    int acceptedConnections = 0;
    QJsonObject readyEvent, lastErrorEvent;
    QJsonArray acceptEvents;

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
            if (type == "ready") { tlsPort = event.value("port").toInt(); readyEvent = event; }
            else if (type == "accepted") {
                ++acceptedConnections;
                if (acceptEvents.size() < 16) acceptEvents.append(event);
            }
            else if (type == "protocol") protocols.append(event.value("value").toString().toLatin1());
            else if (type == "request") {
                requests.append(QByteArray::fromBase64(event.value("headers").toString().toLatin1()));
                send({{"id", event.value("id")}, {"status", status}, {"hanging", hanging},
                    {"location", QString::fromLatin1(location)}, {"body", QString::fromLatin1(content.toBase64())}});
                if (redirectOnce) { status = 200; location.clear(); redirectOnce = false; }
            } else if (type == "disconnected") ++disconnected;
            else if (type == "error") {
                lastErrorEvent = event;
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
        service.setConfigurationApplier([this](const NodeImporter::Result &result, const QString &, bool, QString *) {
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
    QSslCertificate fixtureCa;
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
        if (download.applied != 1)
            qWarning() << "Fixture download did not reach parser:" << download.service.message().left(512);
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
        const auto prepared = prepare.readAllStandardOutput().trimmed();
        const auto metadata = QJsonDocument::fromJson(prepared).object();
        QCOMPARE(metadata.value("event").toString(), QStringLiteral("prepared"));
        QCOMPARE(metadata.value("chain_certificates").toInt(), 2);
        qInfo().noquote() << "Independent TLS fixture" << prepared;
        QFile certFile(certificateDirectory.filePath("ca.pem"));
        QVERIFY(certFile.open(QIODevice::ReadOnly));
        const auto certificates = QSslCertificate::fromData(certFile.readAll());
        QCOMPARE(certificates.size(), 1);
        fixtureCa = certificates.first();
        QVERIFY(!fixtureCa.isNull());
        const auto fingerprint = fixtureCa.digest(QCryptographicHash::Sha256).toHex();
        QCOMPARE(metadata.value("ca_sha256").toString(), QString::fromLatin1(fingerprint));
        QFile chainFile(certificateDirectory.filePath("leaf-chain.pem"));
        QVERIFY(chainFile.open(QIODevice::ReadOnly));
        const auto chain = QSslCertificate::fromData(chainFile.readAll());
        QCOMPARE(chain.size(), 2);
        QCOMPARE(chain.last(), fixtureCa);
        QVERIFY(chain.first() != fixtureCa);
        original = QSslConfiguration::defaultConfiguration();
        trusted = original;
        // A synthetic positive control trusts exactly its generated CA, independent
        // of host roots. The original configuration remains the negative control.
        trusted.setCaCertificates({fixtureCa});
        QCOMPARE(trusted.caCertificates(), QList<QSslCertificate>{fixtureCa});
        QVERIFY(trusted.peerVerifyMode() != QSslSocket::VerifyNone);
        qInfo() << "Fixture TLS anchor SHA256" << fingerprint << "configuredCAcount" << trusted.caCertificates().size();
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
        reportClientTlsErrors(reply, fixtureCa);
        const QPointer<QNetworkReply> observedReply(reply);
        const FailureDiagnostics diagnostics([&] {
            return QJsonObject{{"origin", origin.evidence()}, {"client", replyEvidence(observedReply.data(), fixtureCa)}};
        });
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
        reportClientTlsErrors(reply, fixtureCa);
        const QPointer<QNetworkReply> observedReply(reply);
        const FailureDiagnostics diagnostics([&] {
            return QJsonObject{{"origin", origin.evidence()}, {"client", replyEvidence(observedReply.data(), fixtureCa)}};
        });
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
        const FailureDiagnostics diagnostics([&] {
            return QJsonObject{{"origin", origin.evidence()}, {"applied", download.applied},
                {"serviceMessage", download.service.message().left(1024)}};
        });
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
        const FailureDiagnostics diagnostics([&] {
            return QJsonObject{{"origin", origin.evidence()}, {"applied", download.applied},
                {"serviceMessage", download.service.message().left(1024)}};
        });
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
        const FailureDiagnostics diagnostics([&] {
            return QJsonObject{{"firstOrigin", first.evidence()}, {"secondOrigin", second.evidence()},
                {"applied", download.applied}, {"serviceMessage", download.service.message().left(1024)}};
        });
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
        const FailureDiagnostics diagnostics([&] {
            return QJsonObject{{"origin", origin.evidence()}, {"applied", download.applied},
                {"serviceMessage", download.service.message().left(1024)}};
        });
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
        const FailureDiagnostics diagnostics([&] {
            return QJsonObject{{"origin", origin.evidence()}, {"applied", download.applied},
                {"serviceMessage", download.service.message().left(1024)}};
        });
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
        const FailureDiagnostics diagnostics([&] {
            return QJsonObject{{"firstOrigin", first.evidence()}, {"plainOrigin", plain.evidence()},
                {"applied", download.applied}, {"serviceMessage", download.service.message().left(1024)}};
        });
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
        const FailureDiagnostics diagnostics([&] {
            return QJsonObject{{"origin", origin.evidence()}, {"applied", download.applied},
                {"serviceMessage", download.service.message().left(1024)}};
        });
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
