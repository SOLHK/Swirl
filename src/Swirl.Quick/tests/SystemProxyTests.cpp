#include "engine/SystemProxySession.h"
#include <QCoreApplication>
#include <QTest>
#include <QTemporaryDir>
#include <QTcpServer>
#include <QProcess>
#include <QFile>
#include <QJsonDocument>

class ProxyTests : public QObject {
    Q_OBJECT
private slots:
    void currentUserRecovery() {
        const auto original=SystemProxySession::snapshot();QVERIFY(!original.isEmpty());
        // Restore the user's real settings even when an assertion terminates a
        // test early. These tests never touch WinHTTP, DNS, route or VPN state.
        struct Restore {QJsonObject value;~Restore(){SystemProxySession::apply(value);}} restore{original};
        QTemporaryDir temp;QVERIFY(temp.isValid());
        QTcpServer server;QVERIFY(server.listen(QHostAddress::LocalHost,0));
        const auto journal=temp.filePath("proxy.dpapi");
        SystemProxySession proxy(nullptr,journal);
        QVERIFY2(proxy.enable(server.serverPort(),QCoreApplication::applicationPid()),qPrintable(proxy.error()));
        QVERIFY(proxy.enabled());QVERIFY(proxy.owned());
        QFile encrypted(journal);QVERIFY(encrypted.open(QIODevice::ReadOnly));
        QVERIFY(!encrypted.readAll().contains("127.0.0.1"));encrypted.close();
        QVERIFY(proxy.disable());QCOMPARE(SystemProxySession::snapshot(),original);
        QVERIFY(proxy.enable(server.serverPort(),QCoreApplication::applicationPid()));
        auto external=original;external.insert("server","127.0.0.1:65001");external.insert("flags",3);
        QVERIFY(SystemProxySession::apply(external));
        QVERIFY(proxy.disable());QCOMPARE(SystemProxySession::snapshot(),external);
        QVERIFY(SystemProxySession::apply(original));
        QVERIFY(!proxy.enable(0,0));QCOMPARE(SystemProxySession::snapshot(),original);
    }
    void abruptOwnerExit() {
        const auto original=SystemProxySession::snapshot();QVERIFY(!original.isEmpty());
        struct Restore {QJsonObject value;~Restore(){SystemProxySession::apply(value);}} restore{original};
        QTemporaryDir temp;QVERIFY(temp.isValid());
        QProcess child;child.setProgram(QCoreApplication::applicationFilePath());
        child.setArguments({"--crash-fixture",temp.filePath("proxy.dpapi")});
        child.start();QVERIFY(child.waitForStarted(3000));
        QVERIFY(child.waitForReadyRead(5000));QCOMPARE(child.readAllStandardOutput().trimmed(),QByteArray("enabled"));
        QVERIFY(SystemProxySession::snapshot()!=original);
        child.kill();QVERIFY(child.waitForFinished(3000));
        QTRY_COMPARE_WITH_TIMEOUT(SystemProxySession::snapshot(),original,5000);
        QTRY_VERIFY_WITH_TIMEOUT(!QFile::exists(temp.filePath("proxy.dpapi")),5000);
    }
    void abruptEngineExit() {
        const auto original=SystemProxySession::snapshot();QVERIFY(!original.isEmpty());
        struct Restore {QJsonObject value;~Restore(){SystemProxySession::apply(value);}} restore{original};
        QTemporaryDir temp;QTcpServer listener;QVERIFY(listener.listen(QHostAddress::LocalHost,0));
        QProcess engine;engine.setProgram(QCoreApplication::applicationFilePath());engine.setArguments({"--engine-fixture"});
        engine.start();QVERIFY(engine.waitForStarted(3000));
        SystemProxySession proxy(nullptr,temp.filePath("engine-proxy.dpapi"));
        QVERIFY(proxy.enable(listener.serverPort(),engine.processId()));
        engine.kill();QVERIFY(engine.waitForFinished(3000));
        QTRY_COMPARE_WITH_TIMEOUT(SystemProxySession::snapshot(),original,5000);
        proxy.refresh();QVERIFY(!proxy.owned());QVERIFY(!proxy.enabled());
    }
};
int main(int argc,char **argv) {
    QCoreApplication app(argc,argv);app.setApplicationName("SwirlProxyTests");app.setOrganizationName("SOLHK");
    if(app.arguments().contains("--engine-fixture"))return app.exec();
    if(app.arguments().contains("--crash-fixture")) {
        QTcpServer server;if(!server.listen(QHostAddress::LocalHost,0))return 2;
        SystemProxySession proxy(nullptr,app.arguments().last());
        if(!proxy.enable(server.serverPort(),app.applicationPid()))return 3;
        std::fputs("enabled\n",stdout);std::fflush(stdout);return app.exec();
    }
    ProxyTests tests;return QTest::qExec(&tests,argc,argv);
}
#include "SystemProxyTests.moc"
