#include "engine/SystemProxySession.h"
#include <QCoreApplication>
#include <QTest>
#include <QTemporaryDir>
#include <QTcpServer>
#include <QProcess>
#include <QFile>
#include <QJsonDocument>
#include <QSettings>
#ifdef Q_OS_WIN
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <wincrypt.h>
#endif

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
        // WinINET's per-connection options and the legacy registry values are
        // separate stores. Native clients (including reqwest) read the latter.
        QSettings internet(QStringLiteral("HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Internet Settings"),QSettings::NativeFormat);
        internet.sync();
        QCOMPARE(internet.value("ProxyEnable").toInt(),1);
        QCOMPARE(internet.value("ProxyServer").toString(),QStringLiteral("127.0.0.1:%1").arg(server.serverPort()));
        QCOMPARE(internet.value("ProxyOverride").toString(),SystemProxySession::snapshot().value("bypass").toString());
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
    void registryOnlyExternalEdit() {
        const auto original=SystemProxySession::snapshot();QVERIFY(!original.isEmpty());
        struct Restore {QJsonObject value;~Restore(){SystemProxySession::apply(value);}} restore{original};
        QTemporaryDir temp;QTcpServer server;QVERIFY(server.listen(QHostAddress::LocalHost,0));
        const auto journal=temp.filePath("registry-proxy.dpapi");
        SystemProxySession proxy(nullptr,journal);QVERIFY(proxy.enable(server.serverPort(),QCoreApplication::applicationPid()));
        const auto nativeServer=SystemProxySession::snapshot().value("server");
        QSettings internet(QStringLiteral("HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Internet Settings"),QSettings::NativeFormat);
        internet.setValue("ProxyServer","127.0.0.1:65002");internet.sync();
        QCOMPARE(internet.status(),QSettings::NoError);
        const auto external=SystemProxySession::snapshot();QCOMPARE(external.value("server"),nativeServer);
        proxy.refresh();QVERIFY(!proxy.owned());QVERIFY(!proxy.enabled());
        QVERIFY(proxy.disable());QCOMPARE(SystemProxySession::snapshot(),external);
        QVERIFY(!QFile::exists(journal));
    }
    void restoreDistinctStoresAndAbsentValues() {
        const auto original=SystemProxySession::snapshot();QVERIFY(!original.isEmpty());
        struct Restore {QJsonObject value;~Restore(){SystemProxySession::apply(value);}} restore{original};
        QSettings internet(QStringLiteral("HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Internet Settings"),QSettings::NativeFormat);
        internet.setValue("ProxyServer","127.0.0.1:65003");
        internet.setValue("ProxyEnable",0);internet.remove("ProxyOverride");internet.remove("AutoConfigURL");internet.sync();
        const auto distinct=SystemProxySession::snapshot();
        QCOMPARE(distinct.value("registry").toObject().value("AutoConfigURL").toObject().value("present").toBool(),false);
        QTemporaryDir temp;QTcpServer server;QVERIFY(server.listen(QHostAddress::LocalHost,0));
        SystemProxySession proxy(nullptr,temp.filePath("distinct.dpapi"));
        QVERIFY(proxy.enable(server.serverPort(),QCoreApplication::applicationPid()));
        QVERIFY(proxy.disable());QCOMPARE(SystemProxySession::snapshot(),distinct);
    }
    void malformedRegistryDoesNotMutateSettings() {
        const auto original=SystemProxySession::snapshot();QVERIFY(!original.isEmpty());
        auto invalid=original;invalid.insert("server","127.0.0.1:65004");invalid.insert("registry",QJsonObject{});
        QString error;QVERIFY(!SystemProxySession::apply(invalid,&error));QVERIFY(!error.isEmpty());
        QCOMPARE(SystemProxySession::snapshot(),original);
    }
    void legacyJournalRecoveryPreservesRegistry() {
#ifdef Q_OS_WIN
        const auto original=SystemProxySession::snapshot();QVERIFY(!original.isEmpty());
        struct Restore {QJsonObject value;~Restore(){SystemProxySession::apply(value);}} restore{original};
        auto legacyOriginal=original;legacyOriginal.remove("registry");
        auto legacyApplied=legacyOriginal;legacyApplied.insert("server","127.0.0.1:65005");legacyApplied.insert("flags",3);
        QVERIFY(SystemProxySession::apply(legacyApplied));
        const auto registry=SystemProxySession::snapshot().value("registry");
        QJsonObject record{{"schema",1},{"original",legacyOriginal},{"applied",legacyApplied}};
        auto plain=QJsonDocument(record).toJson(QJsonDocument::Compact);QByteArray entropy("Swirl.SystemProxy.v1");
        DATA_BLOB input{DWORD(plain.size()),reinterpret_cast<BYTE *>(plain.data())};
        DATA_BLOB context{DWORD(entropy.size()),reinterpret_cast<BYTE *>(entropy.data())},encrypted{};
        QVERIFY(CryptProtectData(&input,L"legacy test",&context,nullptr,nullptr,CRYPTPROTECT_UI_FORBIDDEN,&encrypted));
        const QByteArray bytes(reinterpret_cast<const char *>(encrypted.pbData),encrypted.cbData);
        SecureZeroMemory(encrypted.pbData,encrypted.cbData);LocalFree(encrypted.pbData);
        QTemporaryDir temp;const auto journal=temp.filePath("legacy.dpapi");
        QFile file(journal);QVERIFY(file.open(QIODevice::WriteOnly));QCOMPARE(file.write(bytes),bytes.size());file.close();
        QVERIFY(SystemProxySession::recover(journal,nullptr,false));
        const auto restored=SystemProxySession::snapshot();
        QCOMPARE(restored.value("registry"),registry);QCOMPARE(restored,original);QVERIFY(!QFile::exists(journal));
#endif
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
