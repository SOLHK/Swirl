#include "app/FontManager.h"
#include <QTest>
#include <QTemporaryDir>
#include <QSettings>
#include <QGuiApplication>
#include <QFontDatabase>
#include <QDir>
#include <QFile>
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
        QVERIFY(manager.defaultFamily().contains("HarmonyOS"));
        QCOMPARE(manager.currentFamily(),manager.defaultFamily());
        QCOMPARE(QGuiApplication::font().family(),manager.defaultFamily());
        QVERIFY(manager.licenseText().contains("Copyright 2021 Huawei Device Co., Ltd."));
        QVERIFY(QFontDatabase::styles(manager.defaultFamily()).size()>=3);
        auto alternative=manager.families();alternative.removeAll(manager.defaultFamily());
        QVERIFY(!alternative.isEmpty());
        QVERIFY(manager.selectFamily(alternative.first()));
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
};
QTEST_MAIN(FontTests)
#include "FontTests.moc"
