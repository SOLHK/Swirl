#include "app/ExtensionService.h"
#include "engine/EngineController.h"
#include "engine/RustCoreEngine.h"
#include <QTest>
#include <QSettings>
#include <QStandardPaths>
#include "app/StoragePaths.h"
#include <QTemporaryDir>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonArray>
#include <QFile>
#include <QTcpServer>
#include <QTcpSocket>
#include <QNetworkAccessManager>
#include <QNetworkProxy>
#include <QNetworkReply>
#ifdef Q_OS_WIN
#include <windows.h>
#include <wincrypt.h>
#endif
class ExtensionTests:public QObject {
    Q_OBJECT
    static QUrl module(QTemporaryDir &temporary,QString name,QString ip){const auto path=temporary.filePath(name+".json");QFile file(path);file.open(QIODevice::WriteOnly);
        file.write(QJsonDocument(QJsonObject{{"schema",1},{"kind","swirl-module"},{"name",name},{"overrides",QJsonObject{{"dns",QJsonObject{{"mode",0},{"hosts",QJsonArray{QJsonObject{{"name","fixture.test"},{"value",ip}}}}}},{"rules",QJsonArray{"DOMAIN,fixture.test,DIRECT"}}}}}).toJson());file.close();return QUrl::fromLocalFile(path);}
private slots:
    void initTestCase(){QStandardPaths::setTestModeEnabled(true);SwirlPaths::initializeTestStorage();QSettings::setDefaultFormat(QSettings::IniFormat);QSettings::setPath(QSettings::IniFormat,QSettings::UserScope,SwirlPaths::writableLocation(QStandardPaths::AppConfigLocation));}
    void init(){QSettings().clear();}
    void interruptedConfigurationCommitRecovers(){
#ifdef Q_OS_WIN
        QTemporaryDir temporary;const auto path=temporary.filePath("extensions");EngineController engine(std::make_unique<RustCoreEngine>(),nullptr,temporary.filePath("nodes"));const auto base=engine.networkConfigurationSnapshot();
        {ExtensionService service(&engine,path);QVERIFY(service.saveProfile({},"Crash fixture","{\"rules\":[\"DOMAIN,fixture.test,REJECT\"]}","global"));QVERIFY(service.useProfile(service.profiles().first().toMap().value("id").toString()));QVERIFY(service.useProfile(""));}
        // Model a crash after the durable intent was saved but before the
        // network file was replaced while disabling the final module/profile.
        QVariantMap stale=base;stale["rules"]=QStringList{"DOMAIN,fixture.test,REJECT"};QVERIFY(engine.replaceNetworkConfiguration(stale));
        QFile file(path);QVERIFY(file.open(QIODevice::ReadOnly));auto encrypted=file.readAll().mid(10);file.close();DATA_BLOB input{DWORD(encrypted.size()),reinterpret_cast<BYTE *>(encrypted.data())},plain{};
        QVERIFY(CryptUnprotectData(&input,nullptr,nullptr,nullptr,nullptr,CRYPTPROTECT_UI_FORBIDDEN,&plain));auto object=QJsonDocument::fromJson(QByteArray(reinterpret_cast<const char *>(plain.pbData),plain.cbData)).object();SecureZeroMemory(plain.pbData,plain.cbData);LocalFree(plain.pbData);
        object["configurationPending"]=true;object["pendingConfiguration"]=QJsonObject::fromVariantMap(base);object["pendingMode"]="direct";auto bytes=QJsonDocument(object).toJson(QJsonDocument::Compact);input={DWORD(bytes.size()),reinterpret_cast<BYTE *>(bytes.data())};DATA_BLOB output{};
        QVERIFY(CryptProtectData(&input,L"fixture",nullptr,nullptr,nullptr,CRYPTPROTECT_UI_FORBIDDEN,&output));QVERIFY(file.open(QIODevice::WriteOnly|QIODevice::Truncate));file.write("SWIRLEXT1\n");file.write(reinterpret_cast<const char *>(output.pbData),output.cbData);file.close();LocalFree(output.pbData);
        ExtensionService restored(&engine,path);QVERIFY2(restored.error().isEmpty(),qPrintable(restored.error()));QCOMPARE(engine.networkConfigurationSnapshot(),base);QCOMPARE(engine.routingMode(),QString("direct"));QCOMPARE(restored.profileName(),QString("Default"));
        QVERIFY(engine.configureDns({{"mode",0}}));
#endif
    }
    void profilesValidatePersistAndRestore(){QTemporaryDir temporary;EngineController engine(std::make_unique<RustCoreEngine>(),nullptr,temporary.filePath("nodes"));ExtensionService service(&engine,temporary.filePath("extensions"));const auto base=engine.networkConfigurationSnapshot();
        QVERIFY(service.saveProfile({},"Local profile","{\"rules\":[\"DOMAIN,fixture.test,REJECT\"]}","rule"));const auto id=service.profiles().first().toMap().value("id").toString();QVERIFY(service.useProfile(id));QCOMPARE(service.profileName(),QString("Local profile"));QCOMPARE(engine.routingRules().first().toMap().value("policy").toString(),QString("REJECT"));QVERIFY(!service.removeProfile(id));
        const auto file=QUrl::fromLocalFile(temporary.filePath("profile.json"));QVERIFY(service.exportProfile(id,file));QVERIFY(service.importProfile(file));QCOMPARE(service.profiles().size(),2);QVERIFY(!service.saveProfile({},"Invalid","{\"rules\":[\"DOMAIN,fixture.test,missing\"]}","rule"));QCOMPARE(service.profiles().size(),2);
        QVERIFY(service.useProfile(""));QCOMPARE(engine.networkConfigurationSnapshot(),base);QCOMPARE(service.profileName(),QString("Default"));ExtensionService restored(&engine,temporary.filePath("extensions"));QCOMPARE(restored.profiles().size(),2);QVERIFY(service.removeProfile(id));}
    void scriptsRunInBoundedSeparateProcesses(){QTemporaryDir temporary;EngineController engine(std::make_unique<RustCoreEngine>(),nullptr,temporary.filePath("nodes"));ExtensionService service(&engine,temporary.filePath("extensions"));
        QVERIFY(service.saveScript({},"fixture","function main(input){console.log('real worker');return {number:input.number+1};}"));auto id=service.scripts().first().toMap().value("id").toString();
        QVERIFY(service.runScript(id,"{\"number\":2}"));QTRY_VERIFY_WITH_TIMEOUT(!service.busy(),7000);QVERIFY2(service.error().isEmpty(),qPrintable(service.error()));QVERIFY(service.output().contains("real worker"));QCOMPARE(QJsonDocument::fromJson(service.output().toUtf8()).object().value("result").toObject().value("number").toInt(),3);
        QVERIFY(service.saveScript(id,"fixture","function main(){throw new Error('fixture failure');}"));QVERIFY(service.runScript(id));QTRY_VERIFY_WITH_TIMEOUT(!service.busy(),7000);QVERIFY(service.error().contains("fixture failure"));
        QVERIFY(!service.saveScript({},"fixture","function main(){return 1;}"));QCOMPARE(service.scripts().size(),1);
        QVERIFY(service.saveScript(id,"fixture","function main(){throw 42;}"));QVERIFY(service.runScript(id));QTRY_VERIFY_WITH_TIMEOUT(!service.busy(),7000);QVERIFY(service.error().contains("42"));
        QVERIFY(service.saveScript(id,"fixture","function main(){while(true){}}"));QVERIFY(service.runScript(id));QTRY_VERIFY_WITH_TIMEOUT(!service.busy(),7000);QVERIFY(service.error().contains("5 秒"));
        QFile file(temporary.filePath("extensions"));QVERIFY(file.open(QIODevice::ReadOnly));QVERIFY(!file.readAll().contains("while(true)"));file.close();ExtensionService loaded(&engine,temporary.filePath("extensions"));QCOMPARE(loaded.scripts().size(),1);QVERIFY(loaded.scripts().first().toMap().value("source").toString().contains("while(true)"));}
    void modulePrecedenceAndBaseRestoration(){QTemporaryDir temporary;EngineController engine(std::make_unique<RustCoreEngine>(),nullptr,temporary.filePath("nodes"));const auto base=engine.networkConfigurationSnapshot();ExtensionService service(&engine,temporary.filePath("extensions"));
        QVERIFY(service.importModule(module(temporary,"A","127.0.0.1")));QVERIFY(service.importModule(module(temporary,"B","127.0.0.2")));const auto a=service.modules()[0].toMap().value("id").toString(),b=service.modules()[1].toMap().value("id").toString();
        QVERIFY(service.setModuleEnabled(a,true));QVERIFY(service.setModuleEnabled(b,true));QCOMPARE(engine.dnsConfiguration().value("hosts").toList().first().toMap().value("value").toString(),QString("127.0.0.2"));
        QVERIFY(!engine.configureDns({{"mode",0}}));QVERIFY(service.moveModule(b,-1));QCOMPARE(engine.dnsConfiguration().value("hosts").toList().first().toMap().value("value").toString(),QString("127.0.0.1"));
        QVERIFY(service.setModuleEnabled(a,false));QVERIFY(service.setModuleEnabled(b,false));QCOMPARE(engine.networkConfigurationSnapshot(),base);
        QVERIFY(!service.importModule(module(temporary,"invalid","not-an-ip")));QCOMPARE(service.modules().size(),2);QCOMPARE(engine.networkConfigurationSnapshot(),base);}
    void overlayReachesActualRust(){QTemporaryDir temporary;EngineController engine(std::make_unique<RustCoreEngine>(),nullptr,temporary.filePath("nodes"));ExtensionService service(&engine,temporary.filePath("extensions"));QVERIFY(service.importModule(module(temporary,"Local","127.0.0.1")));QVERIFY(service.setModuleEnabled(service.modules().first().toMap().value("id").toString(),true));
        QTcpServer control,proxy,origin;QVERIFY(control.listen(QHostAddress::LocalHost,0));QVERIFY(proxy.listen(QHostAddress::LocalHost,0));engine.setProxyPort(proxy.serverPort());control.close();proxy.close();QVERIFY(origin.listen(QHostAddress::LocalHost,0));
        connect(&origin,&QTcpServer::newConnection,&origin,[&]{auto *socket=origin.nextPendingConnection();connect(socket,&QTcpSocket::readyRead,socket,[socket]{socket->readAll();socket->write("HTTP/1.1 200 OK\r\nContent-Length: 13\r\nConnection: close\r\n\r\nmodule-direct");socket->disconnectFromHost();});connect(socket,&QTcpSocket::disconnected,socket,&QObject::deleteLater);});
        engine.setRoutingMode("direct");engine.connectNode("");QTRY_VERIFY_WITH_TIMEOUT(engine.apiHealthy(),18000);QNetworkAccessManager client;client.setProxy(QNetworkProxy(QNetworkProxy::HttpProxy,"127.0.0.1",engine.activeProxyPort()));auto *reply=client.get(QNetworkRequest(QUrl(QString("http://fixture.test:%1/").arg(origin.serverPort()))));QTRY_VERIFY_WITH_TIMEOUT(reply->isFinished(),7000);QCOMPARE(reply->error(),QNetworkReply::NoError);QCOMPARE(reply->readAll(),QByteArray("module-direct"));
        QVERIFY(!service.setModuleEnabled(service.modules().first().toMap().value("id").toString(),false));engine.stop();QTRY_VERIFY_WITH_TIMEOUT(engine.canStart(),4000);QVERIFY(service.setModuleEnabled(service.modules().first().toMap().value("id").toString(),false));}
    void corruptedStoreIsPreserved(){QTemporaryDir temporary;const auto path=temporary.filePath("broken");QFile file(path);QVERIFY(file.open(QIODevice::WriteOnly));file.write("broken-original");file.close();EngineController engine(std::make_unique<RustCoreEngine>(),nullptr,temporary.filePath("nodes"));ExtensionService service(&engine,path);QVERIFY(!service.saveScript({},"cannot-save","function main(){return 1;}"));QVERIFY(file.open(QIODevice::ReadOnly));QCOMPARE(file.readAll(),QByteArray("broken-original"));}
};
QTEST_GUILESS_MAIN(ExtensionTests)
#include "ExtensionTests.moc"
