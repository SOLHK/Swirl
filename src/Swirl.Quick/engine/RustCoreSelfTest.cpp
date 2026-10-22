#include "RustCoreSelfTest.h"
#include "RustCoreEngine.h"
#include "RustCoreLibrary.h"
#include <QCoreApplication>
#include <QElapsedTimer>
#include <QEventLoop>
#include <QJsonDocument>
#include <QNetworkAccessManager>
#include <QNetworkProxy>
#include <QNetworkReply>
#include <QNetworkRequest>
#include <QSaveFile>
#include <QTcpServer>
#include <QTcpSocket>
#include <QThread>
#include <functional>

namespace {
bool awaitCondition(const std::function<bool()> &condition, int timeoutMs = 4000)
{
    QElapsedTimer elapsed;
    elapsed.start();
    while (!condition() && elapsed.elapsed() < timeoutMs) {
        QCoreApplication::processEvents(QEventLoop::AllEvents, 10);
        QThread::msleep(1);
    }
    return condition();
}
}

int runRustCoreSelfTest(const QString &reportPath)
{
    QJsonObject report{{"schema", 1}, {"success", false},
                       {"scope", "packaged-executable-loopback"},
                       {"private_subscription_tested", false}};
    const auto finish = [&](const QString &failure, int code) {
        report["failure"] = failure;
        report["success"] = code == 0;
        QSaveFile output(reportPath);
        const auto bytes = QJsonDocument(report).toJson(QJsonDocument::Indented);
        if (!output.open(QIODevice::WriteOnly) || output.write(bytes) != bytes.size()
            || !output.commit()) return 74;
        return code;
    };
    RustCoreLibrary library;
    const bool loaded = library.load();
    report["library"] = library.diagnostics();
    if (!loaded) return finish("RustLibraryLoadFailed", 20);

    QTcpServer origin;
    origin.setProxy(QNetworkProxy::NoProxy);
    if (!origin.listen(QHostAddress::LocalHost, 0)) return finish("OriginBindFailed", 21);
    int originRequests = 0;
    QObject::connect(&origin, &QTcpServer::newConnection, &origin, [&] {
        while (auto *socket = origin.nextPendingConnection()) {
            QObject::connect(socket, &QTcpSocket::disconnected, socket, &QObject::deleteLater);
            QObject::connect(socket, &QTcpSocket::readyRead, socket, [&, socket] {
                auto input = socket->property("request").toByteArray() + socket->readAll();
                if (input.size() > 16384) { socket->abort(); return; }
                socket->setProperty("request", input);
                if (!input.contains("\r\n\r\n") || socket->property("answered").toBool()) return;
                socket->setProperty("answered", true);
                if (!input.startsWith("GET /r1-self-test HTTP/1.1\r\n")) { socket->abort(); return; }
                ++originRequests;
                socket->write("HTTP/1.1 200 OK\r\nContent-Length: 13\r\nConnection: close\r\n\r\nrust-core-ok\n");
                socket->disconnectFromHost();
            });
        }
    });
    QTcpServer reservation;
    reservation.setProxy(QNetworkProxy::NoProxy);
    if (!reservation.listen(QHostAddress::LocalHost, 0)) return finish("PortReservationFailed", 22);
    const auto port = reservation.serverPort();
    reservation.close();
    EngineStartOptions options;
    options.proxyPort = port;
    options.routingMode = "direct";
    options.directSession = true;
    options.smartRouting = false;
    RustCoreEngine engine;
    engine.start(options);
    report["listener_port"] = int(port);
    report["core_started"] = engine.status().state == ProxyEngine::State::Running;
    if (engine.status().state != ProxyEngine::State::Running) {
        report["core_error"] = engine.status().message;
        return finish("RustStartFailed", 23);
    }
    const QUrl url(QString("http://127.0.0.1:%1/r1-self-test").arg(origin.serverPort()));
    const auto request = [&](QNetworkProxy::ProxyType type) {
        QNetworkAccessManager client;
        client.setProxy(QNetworkProxy(type, "127.0.0.1", port));
        QNetworkRequest input(url);
        input.setTransferTimeout(4000);
        input.setRawHeader("Connection", "close");
        auto *reply = client.get(input);
        if (!awaitCondition([&] { return reply->isFinished(); }, 4500)) return false;
        return reply->error() == QNetworkReply::NoError
            && reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt() == 200
            && reply->readAll() == "rust-core-ok\n";
    };
    const bool http = request(QNetworkProxy::HttpProxy);
    const bool socks = request(QNetworkProxy::Socks5Proxy);
    report["http_response_verified"] = http;
    report["socks5_response_verified"] = socks;
    QTcpSocket tunnel;
    tunnel.setProxy(QNetworkProxy::NoProxy);
    tunnel.connectToHost(QHostAddress::LocalHost, port);
    bool connect = awaitCondition([&] { return tunnel.state() == QAbstractSocket::ConnectedState; });
    QByteArray reply;
    if (connect) {
        const auto authority = QByteArray("127.0.0.1:") + QByteArray::number(origin.serverPort());
        tunnel.write("CONNECT " + authority + " HTTP/1.1\r\nHost: " + authority + "\r\n\r\n");
        connect = awaitCondition([&] { reply += tunnel.readAll(); return reply.contains("\r\n\r\n"); })
            && reply.startsWith("HTTP/1.1 200 ");
        if (connect) {
            reply.clear();
            tunnel.write("GET /r1-self-test HTTP/1.1\r\nHost: " + authority + "\r\nConnection: close\r\n\r\n");
            connect = awaitCondition([&] { reply += tunnel.readAll(); return reply.endsWith("rust-core-ok\n"); })
                && reply.startsWith("HTTP/1.1 200 OK\r\n");
        }
    }
    tunnel.abort();
    report["connect_response_verified"] = connect;
    report["origin_requests"] = originRequests;
    engine.refresh();
    report["upload_bytes"] = engine.status().uploadTotal;
    report["download_bytes"] = engine.status().downloadTotal;
    const bool traffic = engine.status().uploadTotal > 0 && engine.status().downloadTotal > 0;
    engine.stop();
    QTcpServer released;
    released.setProxy(QNetworkProxy::NoProxy);
    const bool cleanup = released.listen(QHostAddress::LocalHost, port);
    report["listener_released"] = cleanup;
    return finish(http && socks && connect && traffic && cleanup && originRequests == 3
                      ? QString() : "ProxyRoundtripFailed",
                  http && socks && connect && traffic && cleanup && originRequests == 3 ? 0 : 24);
}
