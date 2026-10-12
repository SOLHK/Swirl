// Test-only controlled process. This executable is never shipped in the installer.
#include <QCoreApplication>
#include <QFile>
#include <QJsonDocument>
#include <QJsonObject>
#include <QRegularExpression>
#include <QTcpServer>
#include <QTcpSocket>
#include <QTimer>
#include <cstdio>

int main(int argc, char **argv) {
    QCoreApplication app(argc, argv);
    const auto args = app.arguments();
    const auto mode = qEnvironmentVariable("SWIRL_FIXTURE_MODE");
    if (args.contains("--idle")) return app.exec();
    if (args.contains("-v")) {
        if (mode == "hang-version") return app.exec();
        std::puts("Mihomo Meta vfixture test fixture"); return 0;
    }
    if (args.contains("-t")) return mode == "config-error" ? 7 : 0;
    if (mode == "start-exit") return 9;
    const int configIndex = args.indexOf("-f");
    if (configIndex < 0 || configIndex + 1 >= args.size()) return 3;
    QFile config(args.at(configIndex + 1));
    if (!config.open(QIODevice::ReadOnly)) return 4;
    const auto content = QString::fromUtf8(config.readAll());
    const auto port = QRegularExpression("127\\.0\\.0\\.1:(\\d+)").match(content).captured(1).toUShort();
    const auto secret = QRegularExpression("secret: '([^']+)'").match(content).captured(1).toLatin1();
    if (mode == "no-api") return app.exec();
    QTcpServer server;
    if (!server.listen(QHostAddress::LocalHost, port)) return 5;
    QObject::connect(&server, &QTcpServer::newConnection, &app, [&] {
        while (server.hasPendingConnections()) {
            auto *socket = server.nextPendingConnection();
            QObject::connect(socket, &QTcpSocket::disconnected, socket, &QObject::deleteLater);
            QObject::connect(socket, &QTcpSocket::readyRead, socket, [&, socket] {
                auto request = socket->property("request").toByteArray() + socket->readAll();
                socket->setProperty("request", request);
                if (!request.contains("\r\n\r\n")) return;
                QString activeMode = mode;
                QFile control(qEnvironmentVariable("SWIRL_FIXTURE_CONTROL"));
                if (control.open(QIODevice::ReadOnly)) activeMode = QString::fromUtf8(control.readAll());
                if (activeMode == "timeout") return;
                const bool authenticated = request.contains("Authorization: Bearer " + secret + "\r\n");
                int status = authenticated && activeMode != "auth" ? 200 : 401;
                QByteArray body;
                if (status == 401) body = "{}";
                else if (activeMode == "bad-json") body = "{invalid";
                else if (activeMode == "oversize") body = QByteArray(100000, 'x');
                else if (request.startsWith("GET /version "))
                    body = activeMode == "wrong-version" ? "{\"version\":\"wrong\",\"meta\":true}" : "{\"version\":\"vfixture\",\"meta\":true}";
                else if (request.startsWith("GET /configs ")) {
                    QJsonObject object{{"mode", "direct"}, {"allow-lan", false},
                        {"port", 0}, {"socks-port", 0}, {"mixed-port", 0}, {"redir-port", 0}, {"tproxy-port", 0},
                        {"tun", QJsonObject{{"enable", activeMode == "unsafe"}}}};
                    body = QJsonDocument(object).toJson(QJsonDocument::Compact);
                } else { status = 404; body = "{}"; }
                socket->write("HTTP/1.1 " + QByteArray::number(status) + " Result\r\nContent-Type: application/json\r\nContent-Length: "
                    + QByteArray::number(body.size()) + "\r\nConnection: close\r\n\r\n" + body);
                socket->disconnectFromHost();
            });
        }
    });
    return app.exec();
}
