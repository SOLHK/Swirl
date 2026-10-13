#include <QtTest>
#include <QTemporaryDir>
#include <QFile>
#include <QJsonDocument>
#include "engine/SystemProxy.h"
#ifdef Q_OS_WIN
#include <windows.h>
#include <wininet.h>
#endif
class FakeProxy final : public SystemProxyBackend {
public:
    SystemProxyState state{5,"old:7897","localhost","https://example.invalid/proxy.pac"};
    bool failWrite=false;
    bool read(SystemProxyState &s,QString &) override {s=state;return true;}
    bool write(const SystemProxyState &s,QString &error) override {if(failWrite){error="write failed";return false;}state=s;return true;}
};
class SystemProxyTests final : public QObject {
    Q_OBJECT
private slots:
    void restoresExactSettings() {
        auto backend=std::make_unique<FakeProxy>();auto *fake=backend.get();const auto original=fake->state;
        SystemProxy proxy(false,nullptr,std::move(backend));
        QVERIFY(proxy.enable(7898));QVERIFY(proxy.enabled());QCOMPARE(fake->state.server,"127.0.0.1:7898");QCOMPARE(fake->state.flags,3u);QVERIFY(fake->state.pac.isEmpty());
        QVERIFY(proxy.disable());QVERIFY(fake->state==original);QVERIFY(!proxy.enabled());
    }
    void preservesExternalChanges() {
        auto backend=std::make_unique<FakeProxy>();auto *fake=backend.get();SystemProxy proxy(false,nullptr,std::move(backend));
        QVERIFY(proxy.enable(7898));fake->state.server="another-client:9999";const auto changed=fake->state;
        proxy.refresh();QVERIFY(!proxy.enabled());QVERIFY(!proxy.error().isEmpty());
        QVERIFY(proxy.disable());QVERIFY(fake->state==changed);
    }
    void failedWriteAndInvalidPort() {
        auto backend=std::make_unique<FakeProxy>();auto *fake=backend.get();const auto original=fake->state;SystemProxy proxy(false,nullptr,std::move(backend));
        QVERIFY(!proxy.enable(0));QVERIFY(!proxy.error().isEmpty());fake->failWrite=true;
        QVERIFY(!proxy.enable(7898));QVERIFY(!proxy.enabled());QVERIFY(fake->state==original);
    }
    void failedRestoreKeepsRecoveryJournal() {
        QTemporaryDir dir;const auto journal=dir.filePath("lease.json");
        auto backend=std::make_unique<FakeProxy>();auto *fake=backend.get();const auto original=fake->state;
        SystemProxy proxy(false,nullptr,std::move(backend),journal);
        QVERIFY(proxy.enable(7898));fake->failWrite=true;
        QVERIFY(!proxy.disable());QVERIFY(QFile::exists(journal));
        fake->failWrite=false;QVERIFY(proxy.disable());QVERIFY(fake->state==original);QVERIFY(!QFile::exists(journal));
    }
    void restoresAfterCrash() {
        QTemporaryDir dir;const auto journal=dir.filePath("lease.json");
        const SystemProxyState before{5,"old:7897","localhost","https://example.invalid/proxy.pac"};
        const SystemProxyState applied{3,"127.0.0.1:7898","<local>",{}};
        QFile file(journal);QVERIFY(file.open(QIODevice::WriteOnly));file.write(QJsonDocument(QJsonObject{{"before",before.json()},{"applied",applied.json()}}).toJson());file.close();
        auto backend=std::make_unique<FakeProxy>();auto *fake=backend.get();fake->state=applied;
        SystemProxy proxy(false,nullptr,std::move(backend),journal);
        QVERIFY(fake->state==before);QVERIFY(!QFile::exists(journal));
    }
    void concurrentLease() {
        QTemporaryDir dir;const auto journal=dir.filePath("lease.json");
        SystemProxy first(false,nullptr,std::make_unique<FakeProxy>(),journal);
        SystemProxy second(false,nullptr,std::make_unique<FakeProxy>(),journal);
        QVERIFY(first.enable(7898));QVERIFY(!second.enable(7899));QVERIFY(!second.error().isEmpty());QVERIFY(first.disable());QVERIFY(second.enable(7899));
    }
    void nativeInternetRequest() {
#ifdef Q_OS_WIN
        if(qEnvironmentVariableIntValue("SWIRL_NATIVE_PROXY_TEST")!=1)QSKIP("Explicit opt-in: temporarily set and restore real WinINet settings");
        QTemporaryDir dir;
        SystemProxy proxy(true,nullptr,{},dir.filePath("native-lease.json"));
        QVERIFY2(proxy.enable(qEnvironmentVariableIntValue("SWIRL_NATIVE_PROXY_PORT")),qPrintable(proxy.error()));
        HINTERNET internet=InternetOpenW(L"Swirl native proxy verification",INTERNET_OPEN_TYPE_PRECONFIG,nullptr,nullptr,0);
        QVERIFY(internet);DWORD timeout=6000;
        InternetSetOptionW(internet,INTERNET_OPTION_CONNECT_TIMEOUT,&timeout,sizeof(timeout));
        InternetSetOptionW(internet,INTERNET_OPTION_RECEIVE_TIMEOUT,&timeout,sizeof(timeout));
        HINTERNET request=InternetOpenUrlW(internet,L"https://www.gstatic.com/generate_204",nullptr,0,INTERNET_FLAG_RELOAD|INTERNET_FLAG_NO_CACHE_WRITE|INTERNET_FLAG_NO_AUTO_REDIRECT,0);
        DWORD status=0,bytes=sizeof(status);
        const bool queried=request && HttpQueryInfoW(request,HTTP_QUERY_STATUS_CODE|HTTP_QUERY_FLAG_NUMBER,&status,&bytes,nullptr);
        if(request)InternetCloseHandle(request);InternetCloseHandle(internet);
        const auto restored=proxy.disable();
        QVERIFY2(restored,qPrintable(proxy.error()));QVERIFY(queried);QCOMPARE(status,204ul);
#else
        QSKIP("Windows only");
#endif
    }
};
QTEST_GUILESS_MAIN(SystemProxyTests)
#include "SystemProxyTests.moc"
