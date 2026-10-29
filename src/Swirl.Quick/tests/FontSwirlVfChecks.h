#pragma once
#include "app/FontFileInspection.h"
#include <QFontInfo>
#include <QSaveFile>

void FontTests::fontInspectionRejectsUnsupportedAndInvalidVariations()
{
    const auto fixtures=qEnvironmentVariable("SWIRL_FONT_METADATA_FIXTURES");
    if(fixtures.isEmpty())QSKIP("Original metadata fixtures not supplied");
    QTemporaryDir directory;
    QSettings::setDefaultFormat(QSettings::IniFormat);
    QSettings::setPath(QSettings::IniFormat,QSettings::UserScope,directory.path());QSettings().clear();
    FontManager manager(nullptr,directory.filePath("fonts"));
    const auto active=manager.currentFamily(),draft=manager.previewFamily();
    for(const auto &name:{"hvgl-only.ttf","avar-duplicate.ttf","avar-unanchored.ttf","avar-nonmonotonic.ttf"}){
        QFile file(fixtures+"/"+name);QVERIFY(file.open(QIODevice::ReadOnly));
        const auto inspection=SwirlFontFile::inspect(file);
        QVERIFY2(!inspection.valid(),name);
        QCOMPARE(inspection.hvfOnly,QByteArray(name)=="hvgl-only.ttf");
        QVERIFY(!manager.importFont(QUrl::fromLocalFile(file.fileName())));
        QVERIFY(!manager.error().isEmpty());
        QCOMPARE(manager.currentFamily(),active);QCOMPARE(manager.previewFamily(),draft);
    }
    QVERIFY(QDir(directory.filePath("fonts")).entryList(QDir::Files).isEmpty());
    QFile emptyMaps(fixtures+"/avar-empty.ttf");QVERIFY(emptyMaps.open(QIODevice::ReadOnly));
    QVERIFY(SwirlFontFile::inspect(emptyMaps).valid()); // legal identity maps
    QVERIFY(manager.importFont(QUrl::fromLocalFile(emptyMaps.fileName())));
    const auto localSource=qEnvironmentVariable("SWIRL_TEST_SOURCE_HVF");
    if(!localSource.isEmpty()){
        QFile original(localSource);QVERIFY(original.open(QIODevice::ReadOnly));
        const auto inspection=SwirlFontFile::inspect(original);
        QVERIFY(!inspection.valid());QVERIFY(inspection.hvfOnly);
        QCryptographicHash hash(QCryptographicHash::Sha256);QVERIFY(original.seek(0));QVERIFY(hash.addData(&original));
        qInfo()<<"Optional original HVF input rejected before engine registration; faces="<<inspection.faces.size()
               <<"bytes="<<original.size()<<"sha256="<<hash.result().toHex();
        QVERIFY(!manager.importFont(QUrl::fromLocalFile(original.fileName())));
        QCOMPARE(manager.currentFamily(),active);
    }
}

void FontTests::startupRejectsUnsupportedFontAndCorruptCache()
{
    const auto fixtures=qEnvironmentVariable("SWIRL_FONT_METADATA_FIXTURES");
    if(fixtures.isEmpty())QSKIP("Original metadata fixtures not supplied");
    QTemporaryDir directory;
    QSettings::setDefaultFormat(QSettings::IniFormat);
    QSettings::setPath(QSettings::IniFormat,QSettings::UserScope,directory.path());QSettings().clear();
    const auto fonts=directory.filePath("fonts");QVERIFY(QDir().mkpath(fonts));
    const auto unsupported=fonts+"/Swirl-VF.ttc";
    QVERIFY(QFile::copy(fixtures+"/hvgl-only.ttf",unsupported));
    {
        FontManager manager(nullptr,fonts);
        QVERIFY(manager.importedFamilies().isEmpty());
        QVERIFY(manager.defaultFamily().contains("HarmonyOS"));
        QVERIFY(manager.error().contains("HVGL"));
        QVERIFY(QFileInfo::exists(unsupported));
    }
    QVERIFY(QFile::remove(unsupported));
    QString cached;
    {
        FontManager manager(nullptr,fonts);
        QSignalSpy initialRegistration(qGuiApp,&QGuiApplication::fontDatabaseChanged);
        QVERIFY(manager.importFont(QUrl::fromLocalFile(fixtures+"/automation.ttf")));
        QCOMPARE(initialRegistration.size(),1); // register the saved copy once
        QCoreApplication::processEvents();
        QSignalSpy registered(qGuiApp,&QGuiApplication::fontDatabaseChanged);
        QVERIFY(manager.importFont(QUrl::fromLocalFile(fixtures+"/automation.ttf")));
        QCOMPARE(registered.size(),0); // identical import never registers twice
        const auto copies=QDir(fonts).entryList(QDir::Files);QCOMPARE(copies.size(),1);
        cached=fonts+"/"+copies.first();
    }
    // Replace the inode atomically: never truncate a file an engine may map.
    QFile replacement(fixtures+"/automation-other.ttf");QVERIFY(replacement.open(QIODevice::ReadOnly));
    QSaveFile changed(cached);QVERIFY(changed.open(QIODevice::WriteOnly));
    const auto bytes=replacement.readAll();QCOMPARE(changed.write(bytes),bytes.size());QVERIFY(changed.commit());
    FontManager restarted(nullptr,fonts);
    QVERIFY(restarted.importedFamilies().isEmpty());
    QVERIFY(restarted.error().contains("SHA-256"));
}

void FontTests::localSwirlCollectionUsesPhysicalFaces()
{
    const auto fixtures=qEnvironmentVariable("SWIRL_FONT_METADATA_FIXTURES");
    if(fixtures.isEmpty())QSKIP("Original metadata fixtures not supplied");
    QTemporaryDir directory;
    QSettings::setDefaultFormat(QSettings::IniFormat);
    QSettings::setPath(QSettings::IniFormat,QSettings::UserScope,directory.path());QSettings().clear();
    const auto fonts=directory.filePath("fonts");QVERIFY(QDir().mkpath(fonts));
    QVERIFY(QFile::copy(fixtures+"/swirl-vf-probe.ttc",fonts+"/Swirl-VF.ttc"));
    FontManager manager(nullptr,fonts);
    QCOMPARE(manager.currentFamily(),QStringLiteral("Swirl VF UI Text SC"));
    QCOMPARE(manager.defaultFamily(),manager.currentFamily());
    QCOMPARE(manager.importedFamilies().size(),3);
    const QStringList names{"Swirl VF UI Text SC","Swirl VF UI Text TC","Swirl VF Watch UI Text SC"};
    const QList<double> defaults{501,499,500};
    for(qsizetype index=0;index<names.size();++index){
        QVERIFY(manager.choosePreviewFamily(names[index]));QVERIFY(manager.applyPreview());
        QVERIFY(manager.automatic());
        QCOMPARE(manager.previewAxes().size(),3);
        QCOMPARE(manager.previewValues().value("wght").toDouble(),defaults[index]);
        QCOMPARE(manager.previewValues().value("WDTH").toDouble(),500.0);
        QCOMPARE(manager.previewValues().value("HGHT").toDouble(),500.0);
        QVERIFY(!manager.previewValues().contains("wdth"));
        QFont font(names[index]);font.setPixelSize(24);font.setStyleName(QString());font.clearVariableAxes();
        const auto identity=manager.sourceIdentityForFont(font);
        QVERIFY2(identity.value("familyMatched").toBool(),qPrintable(names[index]));
        QVERIFY2(identity.value("matchesSource").toBool(),qPrintable(names[index]));
        QVERIFY2(identity.value("axisMetadataMatchesSource").toBool(),qPrintable(names[index]));
        QCOMPARE(identity.value("engineAxes").toList().size(),3);
        QCOMPARE(identity.value("faceIndex").toInt(),index);
        QCOMPARE(identity.value("sourceFaceCount").toInt(),3);
        QCOMPARE(identity.value("sourceSha256").toString().size(),64);
        const auto sourceAxes=identity.value("sourceAxes").toList();QCOMPARE(sourceAxes.size(),3);
        QVERIFY(sourceAxes[0].toMap().value("hidden").toBool());
        QVERIFY(sourceAxes[2].toMap().value("hidden").toBool());
        QCOMPARE(manager.variableAxesFor(names[index],900).value("wght").toDouble(),index==2?600.0:900.0);
        const auto fitted=manager.fittedText(font,"AAAAAAAAAAAAAAAA",96,1,"button",10,-1);
        // WDTH coordinates are custom units, never percentages or Qt stretch.
        QCOMPARE(fitted.value("axes").toMap().value("WDTH").toDouble(),500.0);
        QVERIFY(!fitted.value("fitted").toBool());
    }
    // Explicit selection survives restart; local discovery does not force SC.
    FontManager restarted(nullptr,fonts);
    QCOMPARE(restarted.currentFamily(),names.last());
}

void FontTests::customAxesChangeRealGlyphsAtMixedCoordinates()
{
    const auto fixtures=qEnvironmentVariable("SWIRL_FONT_METADATA_FIXTURES");
    if(fixtures.isEmpty())QSKIP("Original metadata fixtures not supplied");
    QTemporaryDir directory;
    QSettings::setDefaultFormat(QSettings::IniFormat);
    QSettings::setPath(QSettings::IniFormat,QSettings::UserScope,directory.path());QSettings().clear();
    FontManager manager(nullptr,directory.filePath("fonts"));
    QVERIFY(manager.importFont(QUrl::fromLocalFile(fixtures+"/custom-width-sc.ttf")));
    QVERIFY(manager.applyPreview());
    QCOMPARE(QFontInfo(QFont(manager.currentFamily())).variableAxes().size(),3);
    QFont fractional(manager.currentFamily());
    fractional.setVariableAxis(QFont::Tag("wght"),623.25f);
    QCOMPARE(fractional.variableAxisValue(QFont::Tag("wght")),623.25f);
    auto outline=[&](double width,double weight,double height){
        QFont font(manager.currentFamily());font.setPixelSize(128);font.setStyleName(QString());font.clearVariableAxes();
        font.setVariableAxis(QFont::Tag("WDTH"),float(width));
        font.setVariableAxis(QFont::Tag("wght"),float(weight));
        font.setVariableAxis(QFont::Tag("HGHT"),float(height));
        const auto raw=QRawFont::fromFont(font);
        const auto glyphs=raw.glyphIndexesForString("A");
        return glyphs.isEmpty()?QPainterPath():raw.pathForGlyph(glyphs.first());
    };
    for(double width:{1.0,267.25,500.0,746.5,1000.0})
        for(double weight:{100.0,350.5,501.0,623.25,900.0}){
            const auto low=outline(width,weight,1),high=outline(width,weight,1000);
            QVERIFY(!low.isEmpty());QVERIFY(!high.isEmpty());QVERIFY(low!=high);
            QCOMPARE(low.elementCount(),high.elementCount());
            const auto interior=outline(width,weight,713.25);
            QVERIFY(interior!=low);QVERIFY(interior!=high);
            QVERIFY(interior.boundingRect().height()>low.boundingRect().height());
            QVERIFY(interior.boundingRect().height()<high.boundingRect().height());
        }
    for(double height:{1.0,333.25,500.0,1000.0}){
        QVERIFY(outline(1,623.25,height)!=outline(1000,623.25,height));
        QVERIFY(outline(746.5,100,height)!=outline(746.5,900,height));
        // Distinct fractional positions, separated beyond a design-unit
        // rounding quantum. A 0.5 step in this tiny fixture can legitimately
        // produce the same FreeType path; that is not an axis-storage failure.
        QVERIFY(outline(746.5,623.25,height)!=outline(746.5,653.75,height));
    }
}

void FontTests::physicalIdentityRejectsMissingAndChangedOutlineTables()
{
    const auto childRoot=qEnvironmentVariable("SWIRL_VF_STATIC_RESTART_ROOT");
    if(!childRoot.isEmpty()){
        QSettings::setDefaultFormat(QSettings::IniFormat);
        QSettings::setPath(QSettings::IniFormat,QSettings::UserScope,childRoot);
        QCOMPARE(QSettings().value("Fonts/family").toString(),QStringLiteral("Swirl VF UI Text SC"));
        FontManager restarted(nullptr,childRoot+"/fonts");
        const auto identity=restarted.sourceIdentityForFont(QFont("Swirl VF UI Text SC"));
        QVERIFY(identity.value("matchesSource").toBool());
        QVERIFY(identity.value("engineAxes").toList().isEmpty());
        QVERIFY(!identity.value("axisMetadataMatchesSource").toBool());
        QVERIFY(restarted.currentFamily()!=QStringLiteral("Swirl VF UI Text SC"));
        QCOMPARE(restarted.currentFamily(),restarted.defaultFamily());
        return;
    }
    const auto fixtures=qEnvironmentVariable("SWIRL_FONT_METADATA_FIXTURES");
    if(fixtures.isEmpty())QSKIP("Original metadata fixtures not supplied");
    QFile source(fixtures+"/custom-width-sc.ttf");QVERIFY(source.open(QIODevice::ReadOnly));
    const auto inspection=SwirlFontFile::inspect(source);QVERIFY(inspection.valid());
    const QRawFont original(source.fileName(),128);
    QCOMPARE(SwirlFontFile::matchingFace(original,source,inspection),0);
    for(const auto &name:{"custom-width-static-impostor.ttf","custom-width-outline-impostor.ttf"}){
        const QRawFont impostor(fixtures+"/"+name,128);QVERIFY(impostor.isValid());
        QCOMPARE(impostor.fontTable("name"),original.fontTable("name"));
        QCOMPARE(impostor.fontTable("cmap"),original.fontTable("cmap"));
        QCOMPARE(SwirlFontFile::matchingFace(impostor,source,inspection),-1);
    }
    // A renamed static file can match its own source bytes perfectly while
    // offering no variable axes. Source identity alone must not activate it.
    QTemporaryDir directory;
    QSettings::setDefaultFormat(QSettings::IniFormat);
    QSettings::setPath(QSettings::IniFormat,QSettings::UserScope,directory.path());QSettings().clear();
    {
        FontManager manager(nullptr,directory.filePath("fonts"));
        QVERIFY(manager.importFont(QUrl::fromLocalFile(fixtures+"/custom-width-static-impostor.ttf")));
        const auto identity=manager.sourceIdentityForFont(QFont("Swirl VF UI Text SC"));
        QVERIFY(identity.value("matchesSource").toBool());
        QVERIFY(identity.value("engineAxes").toList().isEmpty());
        QVERIFY(!identity.value("axisMetadataMatchesSource").toBool());
        const auto active=manager.currentFamily();
        QVERIFY(!manager.applyPreview());
        QCOMPARE(manager.currentFamily(),active);
    }
    // Restart uses a fresh Qt font database, not two live managers registering
    // identical family names in the same process. Flush before starting it.
    QSettings settings;settings.setValue("Fonts/family","Swirl VF UI Text SC");settings.sync();
    QProcess child;auto environment=QProcessEnvironment::systemEnvironment();
    environment.insert("SWIRL_VF_STATIC_RESTART_ROOT",directory.path());child.setProcessEnvironment(environment);
    const auto reportPath=directory.filePath("static-restart.xml");
    child.start(QCoreApplication::applicationFilePath(),
        {"physicalIdentityRejectsMissingAndChangedOutlineTables","-o",reportPath+",xml"});
    QVERIFY(child.waitForStarted(5000));
    const bool finished=child.waitForFinished(10000);
    if(!finished){child.kill();child.waitForFinished(1000);}
    QVERIFY(finished);QCOMPARE(child.exitStatus(),QProcess::NormalExit);
    QFile report(reportPath);QVERIFY(report.open(QIODevice::ReadOnly));
    const auto xmlBytes=report.readAll();QVERIFY2(child.exitCode()==0,xmlBytes.constData());
    QXmlStreamReader xml(xmlBytes);QMap<QString,QStringList> incidents;QString function;
    while(!xml.atEnd()){
        xml.readNext();if(!xml.isStartElement())continue;
        if(xml.name()==u"TestFunction")function=xml.attributes().value("name").toString();
        else if(xml.name()==u"Incident")incidents[function].append(xml.attributes().value("type").toString());
    }
    QVERIFY2(!xml.hasError(),qPrintable(xml.errorString()));
    const QMap<QString,QStringList> expected{{"initTestCase",{"pass"}},
        {"physicalIdentityRejectsMissingAndChangedOutlineTables",{"pass"}},{"cleanupTestCase",{"pass"}}};
    QVERIFY2(incidents==expected,xmlBytes.constData());
}
