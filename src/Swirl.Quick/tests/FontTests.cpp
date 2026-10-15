#include "app/FontManager.h"
#include "app/FontRendering.h"
#include <QTest>
#include <QTemporaryDir>
#include <QSettings>
#include <QGuiApplication>
#include <QFont>
#include <QFontDatabase>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QQuickWindow>
#include <QQmlEngine>
#include <QQmlComponent>
#include <QQmlContext>
class FontTests : public QObject {
    Q_OBJECT
private slots:
    void initTestCase(){QCoreApplication::setOrganizationName("SwirlFontTests");QCoreApplication::setApplicationName("Fonts");}
    void defaultSelectionAndPersistence(){
        QTemporaryDir directory;
        QSettings::setDefaultFormat(QSettings::IniFormat);
        QSettings::setPath(QSettings::IniFormat,QSettings::UserScope,directory.path());
        QSettings().clear();
        FontManager manager(nullptr,directory.filePath("fonts"));
        const auto installed=QFontDatabase::families();
        QVERIFY(manager.defaultFamily().contains("HarmonyOS"));
        QCOMPARE(manager.currentFamily(),manager.defaultFamily());
        QCOMPARE(QGuiApplication::font().family(),manager.defaultFamily());
        QCOMPARE(QGuiApplication::font().weight(),QFont::Medium);
        QCOMPARE(QGuiApplication::font().hintingPreference(),QFont::PreferFullHinting);
        QVERIFY(QGuiApplication::font().styleStrategy() & QFont::PreferAntialias);
        QVERIFY(manager.licenseText().contains("Copyright 2021 Huawei Device Co., Ltd."));
        const auto harmony=installed.filter("HarmonyOS",Qt::CaseInsensitive);
        QVERIFY(!harmony.isEmpty());
        QVERIFY(QFontDatabase::styles(harmony.first()).size()>=3);
        auto alternative=manager.families();alternative.removeAll(manager.defaultFamily());
        QVERIFY(!alternative.isEmpty());
        QVERIFY(manager.selectFamily(alternative.first()));
        QCOMPARE(QGuiApplication::font().hintingPreference(),QFont::PreferFullHinting);
        QVERIFY(QGuiApplication::font().styleStrategy() & QFont::PreferAntialias);
        FontManager restarted(nullptr,directory.filePath("fonts"));
        QCOMPARE(restarted.currentFamily(),alternative.first());
        QVERIFY(!manager.selectFamily("Swirl missing font fixture"));
        QCOMPARE(manager.currentFamily(),alternative.first());
        QFile invalid(directory.filePath("invalid.ttf"));QVERIFY(invalid.open(QIODevice::WriteOnly));invalid.write("not a font");invalid.close();
        QVERIFY(!manager.importFont(QUrl::fromLocalFile(invalid.fileName())));
        QVERIFY(!manager.importFont(QUrl("https://example.invalid/font.ttf")));
        QCOMPARE(manager.currentFamily(),alternative.first());
        QVERIFY(QDir(directory.filePath("fonts")).entryList(QDir::Files).isEmpty());
        manager.reset();QCOMPARE(manager.currentFamily(),manager.defaultFamily());
        QSettings().setValue("Fonts/family","Swirl missing font fixture");
        FontManager unavailable(nullptr,directory.filePath("fonts"));
        QCOMPARE(unavailable.currentFamily(),manager.defaultFamily());
    }
    void importKeepsOriginalFile(){
        QTemporaryDir directory;
        QSettings::setPath(QSettings::IniFormat,QSettings::UserScope,directory.path());
        QSettings().clear();
        FontManager manager(nullptr,directory.filePath("fonts"));
        QFile source(":/swirl/fonts/HarmonyOS_Sans_SC_Regular.ttf");QVERIFY(source.open(QIODevice::ReadOnly));const auto original=source.readAll();
        QFile input(directory.filePath("font.ttf"));QVERIFY(input.open(QIODevice::WriteOnly));QCOMPARE(input.write(original),original.size());input.close();
        QVERIFY2(manager.importFont(QUrl::fromLocalFile(input.fileName())),qPrintable(manager.error()));
        const auto copies=QDir(directory.filePath("fonts")).entryList(QDir::Files);QCOMPARE(copies.size(),1);
        QFile saved(directory.filePath("fonts/"+copies.first()));QVERIFY(saved.open(QIODevice::ReadOnly));QCOMPARE(saved.readAll(),original);
        QVERIFY(QFile::remove(input.fileName()));
        FontManager restarted(nullptr,directory.filePath("fonts"));QCOMPARE(restarted.currentFamily(),manager.currentFamily());
    }
    void importOptionalPingFangUiCollection(){
        const auto sourcePath=qEnvironmentVariable("SWIRL_TEST_TTC");
        if(sourcePath.isEmpty())QSKIP("Set SWIRL_TEST_TTC to test a local PingFang UI collection");
        QTemporaryDir directory;
        QVERIFY(directory.isValid());
        QSettings::setPath(QSettings::IniFormat,QSettings::UserScope,directory.path());
        QSettings().clear();
        FontManager manager(nullptr,directory.filePath("fonts"));
        const auto automaticFamily=manager.defaultFamily();
        QFile source(sourcePath);
        QVERIFY(source.exists());
        QVERIFY2(manager.importFont(QUrl::fromLocalFile(sourcePath)),qPrintable(manager.error()));
        QCOMPARE(manager.defaultFamily(),automaticFamily);
        QCOMPARE(manager.currentFamily(),QStringLiteral("PingFang UI SC"));
        QVERIFY(manager.selectFamily(QStringLiteral("苹方UI-简")));
        QCOMPARE(manager.currentFamily(),QStringLiteral("PingFang UI SC"));
        QVERIFY(!manager.families().contains(QStringLiteral("PingFang UI SC Thin")));
        QCOMPARE(manager.variableAxesFor(manager.currentFamily(),400).value("wght").toInt(),500);
        QCOMPARE(manager.variableAxesFor(manager.currentFamily(),600).value("wght").toInt(),600);
        QCOMPARE(manager.variableAxesFor(manager.currentFamily(),400).value("wdth").toInt(),100);
        QVERIFY(manager.variableAxesFor(manager.defaultFamily(),400).isEmpty());
        QCOMPARE(QGuiApplication::font().hintingPreference(),QFont::PreferFullHinting);
        QVERIFY(QGuiApplication::font().styleStrategy() & QFont::PreferAntialias);
        const auto copies=QDir(directory.filePath("fonts")).entryList({"*.ttc"},QDir::Files);
        QCOMPARE(copies.size(),1);
        QCOMPARE(QFileInfo(directory.filePath("fonts/"+copies.first())).size(),source.size());
        FontManager restarted(nullptr,directory.filePath("fonts"));
        QCOMPARE(restarted.currentFamily(),QStringLiteral("PingFang UI SC"));
        QCOMPARE(restarted.defaultFamily(),automaticFamily);
        restarted.reset();
        QCOMPARE(restarted.currentFamily(),automaticFamily);
    }
    void nativeGlyphsHaveNoColourFringes(){
        if(QGuiApplication::platformName()!=QStringLiteral("windows"))QSKIP("Requires the native Windows platform");
        QTemporaryDir directory;
        QSettings::setDefaultFormat(QSettings::IniFormat);
        QSettings::setPath(QSettings::IniFormat,QSettings::UserScope,directory.path());
        FontManager manager(nullptr,directory.filePath("fonts"));
        QStringList fontFiles{QString()};
        const auto ttc=qEnvironmentVariable("SWIRL_TEST_TTC");
        if(!ttc.isEmpty())fontFiles.append(ttc);
        for(const auto &file:fontFiles){
            if(!file.isEmpty())QVERIFY(manager.importFont(QUrl::fromLocalFile(file)));
            QQmlEngine engine;
            engine.rootContext()->setContextProperty("fixtureFamily",manager.currentFamily());
            QQmlComponent component(&engine);
            component.setData(R"(
import QtQuick
Window { width:500; height:80; color:"white"; visible:true
 Text { x:0.5; y:0.5; text:"连接让世界更近 Swirl 0123456789"; color:"black";
        font.family:fixtureFamily; font.pixelSize:13; font.weight:Font.Medium;
        font.hintingPreference:Font.PreferFullHinting; renderType:Text.NativeRendering }
})",QUrl());
            QScopedPointer<QObject> root(component.create());
            QVERIFY2(root,qPrintable(component.errorString()));
            auto *window=qobject_cast<QQuickWindow *>(root.data());
            QVERIFY(window);
            // The test executable is launched hidden by the Windows runner.
            // Explicitly show this isolated fixture after the startup show.
            window->hide();window->show();
            QVERIFY(QTest::qWaitForWindowExposed(window));
            QImage image;QTRY_VERIFY(!(image=window->grabWindow()).isNull());
            int ink=0,coloured=0;
            for(int y=0;y<image.height();++y)for(int x=0;x<image.width();++x){
                const auto rgb=image.pixel(x,y);
                if(qRed(rgb)<240||qGreen(rgb)<240||qBlue(rgb)<240)++ink;
                if(qAbs(qRed(rgb)-qGreen(rgb))>2||qAbs(qGreen(rgb)-qBlue(rgb))>2)++coloured;
            }
            QVERIFY2(ink>500,"Fixture did not draw enough text");
            QVERIFY2(coloured==0,qPrintable(QString("%1: %2 coloured edge pixels").arg(manager.currentFamily()).arg(coloured)));
        }
    }
};
int main(int argc,char **argv){
    configureSwirlFontRendering();
    QGuiApplication::setHighDpiScaleFactorRoundingPolicy(Qt::HighDpiScaleFactorRoundingPolicy::PassThrough);
    QGuiApplication app(argc,argv);FontTests tests;return QTest::qExec(&tests,argc,argv);
}
#include "FontTests.moc"
