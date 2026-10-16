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
    QString routingMode=QRegularExpression("(?:^|\\n)mode: ([a-z]+)").match(content).captured(1);
    const auto mixedPort=QRegularExpression("mixed-port: ([0-9]+)").match(content).captured(1).toInt();
    QTcpServer mixedListener;
    if(mixedPort>0 && mode!="no-mixed-listener") {
        if(!mixedListener.listen(QHostAddress::LocalHost,quint16(mixedPort)))return 6;
        QObject::connect(&mixedListener,&QTcpServer::newConnection,&app,[&]{
            while(auto *socket=mixedListener.nextPendingConnection()) {
                QObject::connect(socket,&QTcpSocket::disconnected,socket,&QObject::deleteLater);
                QObject::connect(socket,&QTcpSocket::readyRead,socket,[socket]{socket->write(socket->readAll());});
            }
        });
    }
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
                if (request.startsWith("PATCH /configs ") && status!=401) {
                    const auto length=QRegularExpression("(?i)Content-Length: ([0-9]+)").match(QString::fromLatin1(request)).captured(1).toInt();
                    const auto offset=request.indexOf("\r\n\r\n")+4;
                    if(request.size()-offset<length)return;
                    if(activeMode=="patch-reject"){status=500;body="{}";}
                    else {
                        routingMode=QJsonDocument::fromJson(request.mid(offset,length)).object().value("mode").toString();
                        if(activeMode=="patch-apply-drop"){socket->abort();return;}
                        status=204;
                    }
                }
                else if (status == 401) body = "{}";
                else if (activeMode == "bad-json") body = "{invalid";
                else if (activeMode == "oversize") body = QByteArray(100000, 'x');
                else if (request.startsWith("GET /version "))
                    body = activeMode == "wrong-version" ? "{\"version\":\"wrong\",\"meta\":true}" : "{\"version\":\"vfixture\",\"meta\":true}";
                else if (request.startsWith("GET /logs?") && activeMode=="login-tls-eof") {
                    body=QJsonDocument(QJsonObject{{"type","warning"},{"payload","[TCP] dial NODE-DNS-TLS (match RuleSet/PRIVATE-RULE) 192.168.1.1:5678 --> auth.openai.com:443 error: TLS handshake EOF via https://user:PRIVATE-SECRET@private-node.invalid/path"}}).toJson(QJsonDocument::Compact)+"\n";
                }
                else if (request.startsWith("GET /configs ")) {
                    QJsonObject object{{"mode", routingMode}, {"allow-lan", false},
                        {"port", 0}, {"socks-port", 0}, {"mixed-port", mixedPort}, {"redir-port", 0}, {"tproxy-port", 0},
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
