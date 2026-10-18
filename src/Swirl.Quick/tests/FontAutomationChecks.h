#pragma once

#include "FontAutomationRasterChecks.h"
#include "app/FontDisplayContext.h"
#include <QSignalSpy>

namespace {
void isolateFontSettings(const QTemporaryDir &directory)
{
    QSettings::setDefaultFormat(QSettings::IniFormat);
    QSettings::setPath(QSettings::IniFormat,QSettings::UserScope,directory.path());
    QSettings().clear();
}
}

void FontTests::automaticAxesRespectDesignAndDpi()
{
    const auto fixtures=qEnvironmentVariable("SWIRL_FONT_METADATA_FIXTURES");
    if(fixtures.isEmpty())QSKIP("Generated original multi-axis fonts not supplied");
    QTemporaryDir directory;isolateFontSettings(directory);
    FontManager manager(nullptr,directory.filePath("fonts"));
    QVERIFY(manager.automatic());QVERIFY(manager.previewAutomatic());
    const auto before=manager.currentFamily();
    QVERIFY2(manager.importFont(QUrl::fromLocalFile(fixtures+"/automation.ttf")),qPrintable(manager.error()));
    QCOMPARE(manager.currentFamily(),before);
    QCOMPARE(manager.previewFamily(),QStringLiteral("Swirl Automation Probe"));
    QVERIFY(manager.previewAutomatic());QCOMPARE(manager.previewAxes().size(),5);
    QVERIFY(manager.applyPreview());
    const auto family=manager.currentFamily();
    QVERIFY(!QGuiApplication::font().isVariableAxisSet(QFont::Tag("wght")));
    QVERIFY(!QGuiApplication::font().isVariableAxisSet(QFont::Tag("opsz")));
    const QStringList roles{"auxiliary","label","body","button","navigation","list","input","data","title","headline"};
    for(const auto &role:roles)for(const int weight:{300,400,500,600,700}){
        const auto axes=manager.resolvedAxes(family,weight,16,-1,96,1,role);
        QCOMPARE(axes.value("wght").toDouble(),double(weight));
        QCOMPARE(axes.value("opsz").toDouble(),12.0);
        QCOMPARE(axes.value("HGHT").toDouble(),250.0);
        QCOMPARE(axes.value("wdth").toDouble(),100.0);
        QCOMPARE(axes.value("TEST").toDouble(),0.0);
        for(const double dpr:{1.25,1.5,1.75,2.0})
            QCOMPARE(manager.resolvedAxes(family,weight,16,-1,96,dpr,role),axes);
    }
    QCOMPARE(manager.resolvedAxes(family,600,32,-1,96,2,"title").value("opsz").toDouble(),24.0);
    QCOMPARE(manager.resolvedAxes(family,400,16,-1,144,1.5,"body").value("opsz").toDouble(),8.0);
    QCOMPARE(manager.resolvedAxes(family,400,-1,19.5,144,2,"body").value("opsz").toDouble(),19.5);
    QFont pixelFont(family);pixelFont.setPixelSize(24);
    QCOMPARE(manager.resolvedAxesForFont(pixelFont,144,2,"body").value("opsz").toDouble(),12.0);
    QFont pointFont(family);pointFont.setPointSizeF(18);
    QCOMPARE(manager.resolvedAxesForFont(pointFont,144,2,"body").value("opsz").toDouble(),18.0);
    QVERIFY(manager.resolvedAxes(manager.defaultFamily(),400,16,-1,96,1,"body").isEmpty());
    QVERIFY(manager.resolvedAxes("Unavailable Font",400,16,-1,96,1,"body").isEmpty());
}

void FontTests::manualProfilesAndAutomaticRestore()
{
    const auto fixtures=qEnvironmentVariable("SWIRL_FONT_METADATA_FIXTURES");
    if(fixtures.isEmpty())QSKIP("Generated original multi-axis fonts not supplied");
    QTemporaryDir directory;isolateFontSettings(directory);
    const QString first="Swirl Automation Probe",second="Swirl Other Probe";
    {
        FontManager manager(nullptr,directory.filePath("fonts"));
        QVERIFY(manager.importFont(QUrl::fromLocalFile(fixtures+"/automation.ttf")));
        QVERIFY(manager.applyPreview());
        QVERIFY(!manager.setPreviewAxis("fake",1));QVERIFY(manager.previewAutomatic());
        QVERIFY(!manager.setPreviewAxis("wght",std::numeric_limits<double>::quiet_NaN()));
        QVERIFY(manager.previewAutomatic());
        QVERIFY(manager.setPreviewAxis("wght",623.5));
        QVERIFY(manager.setPreviewAxis("wdth",113.25));
        QVERIFY(manager.setPreviewAxis("HGHT",700.75));
        QVERIFY(!manager.previewAutomatic());QVERIFY(manager.automatic());
        QVERIFY(manager.applyPreview());QVERIFY(!manager.automatic());
        QCOMPARE(manager.variableAxesFor(first,400).value("wght").toDouble(),623.5);
        QCOMPARE(manager.variableAxesFor(first,700).value("wght").toDouble(),623.5);
        const auto manual=manager.previewValues();
        manager.setPreviewAutomatic(true);
        QCOMPARE(manager.previewValues(),manual);
        QCOMPARE(manager.previewResolvedAxes(400,16,-1,96,2,"body").value("wght").toDouble(),400.0);
        manager.setPreviewAutomatic(false);QCOMPARE(manager.previewValues(),manual);
        QVERIFY(manager.importFont(QUrl::fromLocalFile(fixtures+"/automation-other.ttf")));
        QCOMPARE(manager.previewFamily(),second);QVERIFY(manager.previewAutomatic());
        QCOMPARE(manager.previewValues().value("wdth").toDouble(),95.0);
        QCOMPARE(manager.previewValues().value("HGHT").toDouble(),500.0);
        QVERIFY(manager.setPreviewAxis("wght",704.25));QVERIFY(manager.applyPreview());
        QVERIFY(manager.selectFamily(first));QVERIFY(!manager.automatic());
        QCOMPARE(manager.previewValues(),manual);
        manager.setPreviewAutomatic(true);QVERIFY(manager.applyPreview());
        QVERIFY(manager.automatic());QVERIFY(manager.previewAutomatic());
        QVERIFY(manager.setPreviewAxis("wght",744.75)); // unconfirmed manual draft
        QTest::qWait(220);
    }
    {
        FontManager restarted(nullptr,directory.filePath("fonts"));
        QCOMPARE(restarted.currentFamily(),first);QVERIFY(restarted.automatic());
        QVERIFY(!restarted.previewAutomatic());
        QCOMPARE(restarted.previewValues().value("wght").toDouble(),744.75);
        QCOMPARE(restarted.variableAxesFor(first,400).value("wght").toDouble(),400.0);
        restarted.discardPreview();QVERIFY(restarted.previewAutomatic());
        QCOMPARE(restarted.previewValues().value("wght").toDouble(),623.5);
        QVERIFY(restarted.selectFamily(second));QVERIFY(!restarted.automatic());
        QCOMPARE(restarted.variableAxesFor(second,400).value("wght").toDouble(),704.25);
        restarted.reset();QVERIFY(restarted.automatic());
        QCOMPARE(restarted.currentFamily(),restarted.defaultFamily());
        QVERIFY(restarted.selectFamily(second));
        QCOMPARE(restarted.previewValues().value("wght").toDouble(),704.25);
    }
}

void FontTests::automaticProfilesRestartAcrossProcess()
{
    const QString first="Swirl Automation Probe",second="Swirl Other Probe";
    const auto childRoot=qEnvironmentVariable("SWIRL_FONT_AUTOMATION_CHILD_ROOT");
    if(!childRoot.isEmpty()){
        // The child starts with a fresh QApplication/font database and loads
        // the saved original font copies and settings, not parent memory.
        QSettings::setDefaultFormat(QSettings::IniFormat);
        QSettings::setPath(QSettings::IniFormat,QSettings::UserScope,childRoot);
        FontManager restarted(nullptr,childRoot+"/fonts");
        QCOMPARE(restarted.currentFamily(),first);QVERIFY(restarted.automatic());
        QCOMPARE(restarted.previewFamily(),first);QVERIFY(!restarted.previewAutomatic());
        QCOMPARE(restarted.previewValues().value("wght").toDouble(),733.75);
        QCOMPARE(restarted.variableAxesFor(first,400).value("wght").toDouble(),400.0);
        restarted.discardPreview();QVERIFY(restarted.previewAutomatic());
        QCOMPARE(restarted.previewValues().value("wght").toDouble(),631.25);
        QCOMPARE(restarted.previewValues().value("HGHT").toDouble(),700.5);
        restarted.setPreviewAutomatic(false);
        QCOMPARE(restarted.previewResolvedAxes(400,16,-1,96,1,"body").value("wght").toDouble(),631.25);
        QVERIFY(restarted.selectFamily(second));QVERIFY(!restarted.automatic());
        QCOMPARE(restarted.variableAxesFor(second,400).value("wght").toDouble(),715.5);
        qInfo("Restored automatic selection, unconfirmed manual draft and per-family values in a separate process.");
        return;
    }
    const auto fixtures=qEnvironmentVariable("SWIRL_FONT_METADATA_FIXTURES");
    if(fixtures.isEmpty())QSKIP("Generated original multi-axis fonts not supplied");
    QTemporaryDir directory;isolateFontSettings(directory);
    {
        FontManager manager(nullptr,directory.filePath("fonts"));
        QVERIFY(manager.importFont(QUrl::fromLocalFile(fixtures+"/automation.ttf")));
        QVERIFY(manager.setPreviewAxis("wght",631.25));
        QVERIFY(manager.setPreviewAxis("HGHT",700.5));QVERIFY(manager.applyPreview());
        QVERIFY(manager.importFont(QUrl::fromLocalFile(fixtures+"/automation-other.ttf")));
        QVERIFY(manager.setPreviewAxis("wght",715.5));QVERIFY(manager.applyPreview());
        QVERIFY(manager.selectFamily(first));manager.setPreviewAutomatic(true);
        QVERIFY(manager.applyPreview());QVERIFY(manager.setPreviewAxis("wght",733.75));
        // Destructor flushes the pending draft, exercising an immediate close.
    }
    QProcess child;
    auto environment=QProcessEnvironment::systemEnvironment();
    environment.insert("SWIRL_FONT_AUTOMATION_CHILD_ROOT",directory.path());
    child.setProcessEnvironment(environment);
    child.setProcessChannelMode(QProcess::MergedChannels);
    child.start(QCoreApplication::applicationFilePath(),{"automaticProfilesRestartAcrossProcess"});
    QVERIFY2(child.waitForStarted(5000),qPrintable(child.errorString()));
    const bool finished=child.waitForFinished(10000);
    if(!finished){child.kill();child.waitForFinished(1000);}
    const auto output=child.readAll();
    QVERIFY2(finished,output.constData());
    QCOMPARE(child.exitStatus(),QProcess::NormalExit);
    QVERIFY2(child.exitCode()==0,output.constData());
    QVERIFY2(output.contains("Restored automatic selection"),output.constData());
}

void FontTests::legacyAxisSettingsArePreserved()
{
    const auto fixtures=qEnvironmentVariable("SWIRL_FONT_METADATA_FIXTURES");
    if(fixtures.isEmpty())QSKIP("Generated original multi-axis fonts not supplied");
    QTemporaryDir directory;isolateFontSettings(directory);
    const auto storage=directory.filePath("fonts");QVERIFY(QDir().mkpath(storage));
    QVERIFY(QFile::copy(fixtures+"/automation.ttf",storage+"/original.ttf"));
    const QString family="Swirl Automation Probe";
    const QVariantMap active{{"wght",611.75},{"wdth",109.125},{"HGHT",731.25},{"TEST",1.25}};
    auto draft=active;draft["wght"]=721.5;
    QSettings settings;
    settings.setValue("Fonts/family",family);settings.setValue("Fonts/axes",active);
    settings.setValue("Fonts/previewFamily",family);settings.setValue("Fonts/previewAxes",draft);
    settings.sync();
    FontManager manager(nullptr,storage);
    QCOMPARE(manager.currentFamily(),family);QVERIFY(!manager.automatic());QVERIFY(!manager.previewAutomatic());
    QCOMPARE(manager.variableAxesFor(family,400).value("wght").toDouble(),611.75);
    QCOMPARE(manager.previewValues().value("wght").toDouble(),721.5);
    QCOMPARE(QSettings().value("Fonts/axes").toMap(),active);
    const auto backup=QSettings().value("Fonts/legacyV1").toMap();
    QCOMPARE(backup.value("axes").toMap(),active);QCOMPARE(backup.value("previewAxes").toMap(),draft);
    QCOMPARE(QSettings().value("Fonts/schemaVersion").toInt(),2);
    manager.setPreviewAutomatic(true);QVERIFY(manager.applyPreview());
    QCOMPARE(manager.variableAxesFor(family,600).value("wght").toDouble(),600.0);
    QCOMPARE(QSettings().value("Fonts/legacyV1").toMap(),backup);
    manager.setPreviewAutomatic(false);
    QCOMPARE(manager.previewValues().value("wght").toDouble(),721.5);
}

void FontTests::automaticAxesProduceRealGlyphsAndFallback()
{
    const auto fixtures=qEnvironmentVariable("SWIRL_FONT_METADATA_FIXTURES");
    if(fixtures.isEmpty())QSKIP("Generated original multi-axis fonts not supplied");
    QTemporaryDir directory;isolateFontSettings(directory);
    FontManager manager(nullptr,directory.filePath("fonts"));
    for(const auto &file:QStringList{"automation.ttf","automation-other.ttf"}){
        QVERIFY(manager.importFont(QUrl::fromLocalFile(fixtures+"/"+file)));QVERIFY(manager.applyPreview());
        const auto family=manager.currentFamily();
        const auto failures=SwirlFontAutomationRaster::verifyVariableAxes(family,manager.axesFor(family));
        QVERIFY2(failures.isEmpty(),qPrintable(failures.join(", ")));
        const auto axes=manager.resolvedAxes(family,600,24,-1,96,1,"body");
        QVERIFY(SwirlFontAutomationRaster::usesRealFallbackForB(family,axes));
        const auto small=manager.resolvedAxes(family,600,24,-1,96,1,"body");
        const auto large=manager.resolvedAxes(family,600,64,-1,96,1,"title");
        // Render both at the same pixel size to isolate real opsz variation.
        QVERIFY(SwirlFontAutomationRaster::render(family,small)!=SwirlFontAutomationRaster::render(family,large));
    }
}

void FontTests::fontCachesAreBoundedAndStable()
{
    const auto fixtures=qEnvironmentVariable("SWIRL_FONT_METADATA_FIXTURES");
    if(fixtures.isEmpty())QSKIP("Generated original multi-axis fonts not supplied");
    QTemporaryDir directory;isolateFontSettings(directory);
    FontManager manager(nullptr,directory.filePath("fonts"));
    QVERIFY(manager.importFont(QUrl::fromLocalFile(fixtures+"/automation.ttf")));QVERIFY(manager.applyPreview());
    QCoreApplication::processEvents();
    QSignalSpy changes(&manager,&FontManager::configurationChanged);
    const auto family=manager.currentFamily();
    const auto expected=manager.resolvedAxes(family,400,16,-1,96,1,"body");
    for(int i=0;i<1000;++i){
        QCOMPARE(manager.resolvedAxes(family,400,16,-1,96,1,"body"),expected);
        manager.resolvedAxes(family,400+(i%300),12+i*.01,-1,96,1+(i%5)*.25,"body");
    }
    for(const auto &catalogueFamily:manager.families())manager.axesFor(catalogueFamily);
    QVERIFY(manager.resolutionCacheSize()<=256);QVERIFY(manager.metadataCacheSize()<=64);
    QCOMPARE(changes.count(),0); // resolution never writes settings or invalidates UI
    QVERIFY(manager.setPreviewAxis("wght",688.5));QVERIFY(manager.applyPreview());
    QCOMPARE(manager.resolvedAxes(family,400,16,-1,96,1,"body").value("wght").toDouble(),688.5);
    manager.setPreviewAutomatic(true);QVERIFY(manager.applyPreview());
    QCOMPARE(manager.resolvedAxes(family,400,16,-1,96,1,"body"),expected);
}

void FontTests::displayContextHasBoundedLifecycle()
{
    QQuickWindow window;
    FontDisplayContext context(&window);
    QVERIFY(context.logicalDpi()>0);QVERIFY(context.devicePixelRatio()>0);
    QCOMPARE(context.devicePixelRatio(),window.devicePixelRatio());
    if(window.screen())QCOMPARE(context.logicalDpi(),window.screen()->logicalDotsPerInchY());
    QSignalSpy metrics(&context,&FontDisplayContext::metricsChanged);
    for(int i=0;i<100;++i){QEvent event(QEvent::DevicePixelRatioChange);QCoreApplication::sendEvent(&window,&event);}
    QCOMPARE(metrics.count(),0); // unchanged display events must not trigger fonts
    auto *temporary=new QQuickWindow;
    QPointer<FontDisplayContext> child=new FontDisplayContext(temporary);
    delete temporary;QVERIFY(child.isNull());
}
