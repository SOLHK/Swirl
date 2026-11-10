#include "engine/NodeImportService.h"
#include "engine/RustCoreLibrary.h"
#include "network/HttpRequestPolicy.h"

#include <QFile>
#include <QCryptographicHash>
#include <QDateTime>
#include <QElapsedTimer>
#include <QEventLoop>
#include <QHostInfo>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QNetworkAccessManager>
#include <QNetworkReply>
#include <QNetworkProxy>
#include <QPointer>
#include <QProcess>
#include <QRegularExpression>
#include <QSignalSpy>
#include <QSslCertificate>
#include <QSslConfiguration>
#include <QSslError>
#include <QSslSocket>
#include <QStandardPaths>
#include <QTcpServer>
#include <QTemporaryDir>
#include <QTest>
#include <QTextStream>
#include <functional>
#include <atomic>

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
        const auto localhost = QHostInfo::fromName(QStringLiteral("localhost"));
        QJsonArray addresses;
        for (const auto &address : localhost.addresses()) addresses.append(address.toString());
        evidence.insert("localhostResolution", QJsonObject{{"addresses", addresses},
            {"error", int(localhost.error())}, {"errorString", localhost.errorString()}});
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
        // Scope teardown follows the original assertions. Preserve the actual
        // accepted loopback family on success as well as on a failure path.
        if (secure && tlsPort)
            qInfo().noquote() << "TLS_FIXTURE_SUMMARY" << QJsonDocument(evidence()).toJson(QJsonDocument::Compact);
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
#ifdef Q_OS_WIN
// Independent, test-only authenticated CONNECT peer. TLS stays end-to-end
// between the real downloader and the existing Python TLS origin.
class DownloadConnectProxy final : public QTcpServer {
public:
    const quint16 targetPort;
    int authenticated=0,challenged=0,rejected=0;
    QList<QPointer<QTcpSocket>> clients;
    explicit DownloadConnectProxy(quint16 port):targetPort(port) {
        connect(this,&QTcpServer::newConnection,this,[this]{while(hasPendingConnections()){
            auto *client=nextPendingConnection();clients.append(client);
            connect(client,&QTcpSocket::disconnected,client,&QObject::deleteLater);
            connect(client,&QTcpSocket::readyRead,client,[this,client]{
                if(client->property("tunnel").toBool())return;
                auto bytes=client->property("headers").toByteArray()+client->readAll();
                client->setProperty("headers",bytes);
                if(bytes.size()>16384){++rejected;client->abort();return;}
                if(!bytes.contains("\r\n\r\n"))return;
                const auto expected="CONNECT localhost:"+QByteArray::number(targetPort)+" HTTP/1.1\r\n";
                if(!bytes.startsWith(expected)){++rejected;client->abort();return;}
                QByteArray authorization;
                for(const auto &line:bytes.split('\n'))if(line.toLower().startsWith("proxy-authorization:"))authorization=line.mid(line.indexOf(':')+1).trimmed();
                if(authorization!="Basic "+QByteArray("fixture-user:fixture-password").toBase64()){
                    ++challenged;client->write("HTTP/1.1 407 Proxy Authentication Required\r\nProxy-Authenticate: Basic realm=\"fixture\"\r\nContent-Length: 0\r\nConnection: close\r\n\r\n");client->disconnectFromHost();return;
                }
                client->setProperty("tunnel",true);++authenticated;
                auto *upstream=new QTcpSocket(client);
                connect(upstream,&QTcpSocket::connected,client,[client]{client->write("HTTP/1.1 200 Connection Established\r\n\r\n");});
                connect(client,&QTcpSocket::readyRead,upstream,[client,upstream]{upstream->write(client->readAll());});
                connect(upstream,&QTcpSocket::readyRead,client,[client,upstream]{client->write(upstream->readAll());});
                connect(client,&QTcpSocket::disconnected,upstream,&QTcpSocket::abort);
                connect(upstream,&QTcpSocket::disconnected,client,&QTcpSocket::disconnectFromHost);
                connect(upstream,&QTcpSocket::errorOccurred,client,[client](QAbstractSocket::SocketError error){if(error!=QAbstractSocket::RemoteHostClosedError)client->abort();});
                upstream->connectToHost(QHostAddress::LocalHost,targetPort);
            });
        }});
    }
    void stop(){close();for(const auto &client:std::as_const(clients))if(client)client->abort();}
};
#endif
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
#ifdef Q_OS_WIN
    void physicalDownloadUsesAuthenticatedConnectAndNativeTls_data() {
        QTest::addColumn<QString>("scenario");
        for(const auto &name:{"success","untrusted-certificate","forbidden","redirect","legacy-negotiation"})
            QTest::newRow(name)<<QString::fromLatin1(name);
    }
    void physicalDownloadUsesAuthenticatedConnectAndNativeTls() {
        QFETCH(QString,scenario);
        if(scenario=="untrusted-certificate")QSslConfiguration::setDefaultConfiguration(original);
        Origin origin(certificateDirectory.path());
        if(scenario=="forbidden")origin.status=403;
        if(scenario=="legacy-negotiation")origin.status=400;
        if(scenario=="redirect"){origin.status=302;origin.redirectOnce=true;origin.location="/final?sig=FIXTURE%252F%26";}
        QVERIFY2(origin.listen(),qPrintable(origin.error()));
        DownloadConnectProxy proxy(quint16(origin.url().port()));QVERIFY(proxy.listen(QHostAddress::LocalHost,0));
        const auto proxyPort=proxy.serverPort(),targetPort=quint16(origin.url().port());
        struct Calls{std::atomic<int> starts=0,stops=0,system=0;std::atomic<bool> invalid=false;};
        const auto calls=std::make_shared<Calls>();
        const QPointer<DownloadConnectProxy> proxyGuard(&proxy);
        auto command=[calls,proxyGuard,proxyPort,targetPort](const QJsonObject &input)->QJsonObject {
            if(input.value("op")=="stop"){
                if(input.size()!=2||input.value("handle").toInteger()!=91)calls->invalid=true;
                ++calls->stops;QMetaObject::invokeMethod(QCoreApplication::instance(),[proxyGuard]{if(proxyGuard)proxyGuard->stop();},Qt::QueuedConnection);return {{"ok",true}};
            }
            if(input.size()!=3||input.value("op")!="start"||input.value("host")!="localhost"||input.value("port").toInt()!=targetPort)calls->invalid=true;
            ++calls->starts;return {{"ok",true},{"handle",91},{"port",proxyPort},{"username","fixture-user"},{"password","fixture-password"}};
        };
        QTemporaryDir directory;NodeStore store(directory.filePath("nodes.dpapi"));
        NodeImportService service(&store,nullptr,{},60000,[calls](const QNetworkProxyQuery &){++calls->system;return QList<QNetworkProxy>{QNetworkProxy(QNetworkProxy::NoProxy)};},command);
        int applied=0;QList<ProxyNode> parsed;
        const FailureDiagnostics diagnostics([&]{return QJsonObject{{"origin",origin.evidence()},
            {"serviceMessage",service.message().left(1024)},{"starts",calls->starts.load()},
            {"stops",calls->stops.load()},{"authenticated",proxy.authenticated},
            {"challenged",proxy.challenged},{"rejected",proxy.rejected},{"applied",applied}};});
        service.setConfigurationApplier([&](const NodeImporter::Result &result,const QString &,bool,QString *){++applied;parsed=result.nodes;return true;});
        const auto url=QUrl::fromEncoded("https://localhost:"+QByteArray::number(targetPort)+"/signed%2Fpath?token=FIXTURE%2B%2F%3D&sig=a%252Fb%26c&duplicate=one&duplicate=two");
        QVERIFY(service.saveSubscription({},"Physical TLS",url,360,false,"auto","nodes-only","physical"));
        service.refreshSubscription(store.subscriptions().first().id);
        QTRY_VERIFY_WITH_TIMEOUT(!service.busy(),8000);QTRY_COMPARE_WITH_TIMEOUT(calls->stops.load(),1,3000);
        QTRY_VERIFY_WITH_TIMEOUT(!proxy.isListening(),3000);
        QCOMPARE(calls->starts.load(),1);QCOMPARE(calls->system.load(),0);QVERIFY(!calls->invalid.load());QCOMPARE(proxy.rejected,0);QVERIFY(proxy.authenticated>=1);
        QCOMPARE(store.subscriptions().first().url.toEncoded(),url.toEncoded());
        const bool success=scenario=="success"||scenario=="redirect";
        QCOMPARE(applied,success?1:0);
        if(success){QCOMPARE(parsed.size(),1);QCOMPARE(parsed.first().name,QStringLiteral("HTTP1-Fixture"));}
        if(scenario=="untrusted-certificate"){
            QVERIFY(service.message().contains(QStringLiteral("TLS 校验或握手失败")));QCOMPARE(origin.requests.size(),0);
        }else{
            const int count=scenario=="redirect"||scenario=="legacy-negotiation"?2:1;
            QCOMPARE(origin.requests.size(),count);
            const auto first="GET "+url.toEncoded(QUrl::RemoveScheme|QUrl::RemoveAuthority)+" HTTP/1.1\r\n";
            QVERIFY(origin.requests.first().startsWith(first));
            for(const auto &protocol:origin.protocols)QVERIFY(protocol.isEmpty()||protocol=="http/1.1");
            if(scenario=="forbidden")QVERIFY(service.message().contains("HTTP 403"));
            if(scenario=="legacy-negotiation")QVERIFY(origin.requests.last().contains("Clash.Meta/1.19.32 Swirl/1.0"));
        }
        QVERIFY(!service.message().contains("FIXTURE%"));QVERIFY(!service.message().contains("fixture-password"));
    }
#endif
};

// Explicit manual acceptance only: the normal test suite never contacts a
// public origin. The two fixed public sites carry no subscription credentials.
static int physicalPublicHttps(const QUrl &url) {
    QStandardPaths::setTestModeEnabled(true);
    QTemporaryDir directory;NodeStore store(directory.filePath("nodes.dpapi"));NodeImportService service(&store);
    QElapsedTimer elapsed;elapsed.start();QEventLoop loop;QTimer deadline;deadline.setSingleShot(true);
    bool downloaded=false,applied=false,physicalRoute=false;int attempts=0,httpStatus=0,qtError=-1;
    service.setConfigurationApplier([&](const NodeImporter::Result &,const QString &,bool,QString *error){
        applied=true;*error=QStringLiteral("Public HTTPS acceptance never applies configuration");return false;
    });
    QObject::connect(&service,&NodeImportService::downloadDiagnostic,&loop,[&](const QString &event){
        ++attempts;
        physicalRoute=event.contains("route=physical-interface;");
        const auto status=QRegularExpression(QStringLiteral("http=(\\d+); qt=(\\d+)$")).match(event);
        if(status.hasMatch()){httpStatus=status.captured(1).toInt();qtError=status.captured(2).toInt();}
        downloaded=downloaded||(physicalRoute&&httpStatus==200&&qtError==0);
    });
    QObject::connect(&service,&NodeImportService::changed,&loop,[&]{if(!service.busy())loop.quit();});
    QObject::connect(&deadline,&QTimer::timeout,&loop,&QEventLoop::quit);
    const bool tlsVerification=QSslConfiguration::defaultConfiguration().peerVerifyMode()!=QSslSocket::VerifyNone;
    const bool saved=directory.isValid()&&tlsVerification&&service.saveSubscription({},"Fixed public HTTPS acceptance",
        url,360,false,"auto","nodes-only","physical");
    if(saved){service.refreshSubscription(store.subscriptions().first().id);if(service.busy()){deadline.start(35000);loop.exec();}}
    const bool finished=!service.busy();
    const bool htmlRejected=service.message().contains(QStringLiteral("格式不支持"))||service.message().contains(QStringLiteral("解析失败"));
    service.shutdown();
    const bool ok=saved&&downloaded&&finished&&htmlRejected&&!applied&&store.nodes().isEmpty();
    const auto libraryDiagnostic=RustCoreLibrary::instance().diagnostics();
    const QJsonObject result{{"schema",1},{"test","physical-public-https"},{"public_host",url.host()},
        {"passed",ok},{"download_http_200_qt_no_error",downloaded},{"tls_verification_enabled",tlsVerification},
        {"source_saved",saved},{"finished",finished},{"rust_library_ready",RustCoreLibrary::instance().isReady()},
        {"http_status",httpStatus},{"qt_error",qtError},{"physical_route_observed",physicalRoute},
        {"rust_library_code",libraryDiagnostic.value("code")},
        {"download_route_export_available",RustCoreLibrary::instance().downloadRoute()!=nullptr},
        {"non_subscription_rejected_by_parser",htmlRejected},{"configuration_applied",applied},{"attempts",attempts},
        {"elapsed_ms",elapsed.elapsed()},{"qt",QString::fromLatin1(qVersion())},{"tls_backend",QSslSocket::activeBackend()},
        {"source_sha",RustCoreLibrary::expectedSourceSha()},{"build_id",RustCoreLibrary::expectedBuildId()}};
    QTextStream(stdout)<<QJsonDocument(result).toJson(QJsonDocument::Compact)<<Qt::endl;
    return ok?0:1;
}
static bool physicalPublicTlsProbe(const QUrl &url,bool onceHead=false) {
    auto &library=RustCoreLibrary::instance();
    const auto call=[&library](const QJsonObject &input){
        if(!library.load()||!library.downloadRoute())return QJsonObject{};
        const auto command=library.downloadRoute();const auto request=QJsonDocument(input).toJson(QJsonDocument::Compact);
        QByteArray output(4096,'\0');
        const auto size=command(reinterpret_cast<const unsigned char *>(request.constData()),size_t(request.size()),
            reinterpret_cast<unsigned char *>(output.data()),size_t(output.size()));
        return size>0&&size<=output.size()?QJsonDocument::fromJson(output.first(size)).object():QJsonObject{};
    };
    const auto route=call({{"op",onceHead?"start_once":"start"},{"host",url.host()},{"port",443}});
    const auto handle=route.value("handle").toInteger();QJsonArray tlsErrors;
    int httpStatus=0,qtError=-1,peerChainLength=0;bool encrypted=false;
    QNetworkAccessManager manager;
    if(route.value("ok").toBool()&&handle>0){
        manager.setProxy(QNetworkProxy(QNetworkProxy::HttpProxy,QStringLiteral("127.0.0.1"),quint16(route.value("port").toInt()),
            route.value("username").toString(),route.value("password").toString()));
        QNetworkRequest request(url);SwirlNetwork::applyHttp1OnlyPolicy(request);
        request.setAttribute(QNetworkRequest::RedirectPolicyAttribute,QNetworkRequest::ManualRedirectPolicy);request.setTransferTimeout(15000);
        if(onceHead){request.setRawHeader("User-Agent","Swirl-Core-URLTest/1");request.setRawHeader("Accept","*/*");request.setRawHeader("Connection","close");}
        auto *reply=onceHead?manager.head(request):manager.get(request);reply->setReadBufferSize(64*1024);qint64 received=0;QEventLoop loop;QTimer timeout;timeout.setSingleShot(true);
        QObject::connect(reply,&QNetworkReply::sslErrors,&loop,[&](const QList<QSslError> &errors){for(const auto &error:errors)if(tlsErrors.size()<8)tlsErrors.append(int(error.error()));});
        QObject::connect(reply,&QNetworkReply::readyRead,&loop,[reply,&received]{received+=reply->readAll().size();if(received>NodeImporter::MaximumBytes)reply->abort();});
        QObject::connect(reply,&QNetworkReply::finished,&loop,&QEventLoop::quit);
        QObject::connect(&timeout,&QTimer::timeout,&loop,[reply,&loop]{reply->abort();loop.quit();});timeout.start(30000);loop.exec();
        httpStatus=reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();qtError=int(reply->error());
        encrypted=reply->attribute(QNetworkRequest::ConnectionEncryptedAttribute).toBool();peerChainLength=reply->sslConfiguration().peerCertificateChain().size();
        reply->deleteLater();manager.clearAccessCache();
    }
    const bool stopped=handle>0&&call({{"op","stop"},{"handle",handle}}).value("ok").toBool();
    const bool ok=httpStatus==200&&qtError==0&&tlsErrors.isEmpty()&&encrypted&&stopped;
    const QJsonObject result{{"schema",1},{"test",onceHead?"physical-public-head-once":"physical-public-qt-tls-probe"},{"public_host",url.host()},
        {"method",onceHead?"HEAD":"GET"},{"one_shot_upstream",onceHead},
        {"passed",ok},{"http_status",httpStatus},{"qt_error",qtError},{"tls_error_codes",tlsErrors},
        {"encrypted",encrypted},{"peer_chain_length",peerChainLength},{"route_stopped",stopped}};
    QTextStream(stdout)<<QJsonDocument(result).toJson(QJsonDocument::Compact)<<Qt::endl;return ok;
}
int main(int argc,char **argv) {
    QCoreApplication application(argc,argv);
    if(application.arguments().contains(QStringLiteral("--physical-public-head-once")))
        return application.arguments().size()==2&&physicalPublicTlsProbe(QUrl(QStringLiteral("https://www.cloudflare.com/robots.txt")),true)?0:1;
    if(application.arguments().contains(QStringLiteral("--physical-public-https"))){
        if(application.arguments().size()!=2)return 2;
        int result=0;
        for(const auto &url:{QUrl(QStringLiteral("https://example.com/")),QUrl(QStringLiteral("https://www.cloudflare.com/cdn-cgi/trace"))}){
            result|=physicalPublicHttps(url);if(!physicalPublicTlsProbe(url))result=1;
        }
        return result;
    }
    QtNetworkPolicyTests tests;return QTest::qExec(&tests,argc,argv);
}
#include "QtNetworkPolicyTests.moc"
