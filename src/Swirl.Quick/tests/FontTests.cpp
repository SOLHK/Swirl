#include "app/FontManager.h"
#include "app/VariableFontPreview.h"
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
#include <QRawFont>
#include <QPainter>
#include <QFontMetricsF>
#include <QCryptographicHash>
#include <QElapsedTimer>
#include <QJsonDocument>
#include <QJsonArray>
#include <QJsonObject>
#include <QScreen>
#include <QProcess>
#include <QProcessEnvironment>
#include <limits>
#include <QPointer>
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
        QVERIFY(manager.applyPreview());
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
        QVERIFY(manager.applyPreview());
        QCOMPARE(manager.defaultFamily(),automaticFamily);
        QCOMPARE(manager.currentFamily(),QStringLiteral("PingFang UI SC"));
        QVERIFY(manager.selectFamily(QStringLiteral("苹方UI-简")));
        QCOMPARE(manager.currentFamily(),QStringLiteral("PingFang UI SC"));
        QVERIFY(!manager.families().contains(QStringLiteral("PingFang UI SC Thin")));
        // Automatic mode must preserve the existing body/title weight hierarchy.
        QVERIFY(manager.automatic());
        QCOMPARE(manager.variableAxesFor(manager.currentFamily(),400).value("wght").toInt(),400);
        QCOMPARE(manager.variableAxesFor(manager.currentFamily(),600).value("wght").toInt(),600);
        QCOMPARE(manager.variableAxesFor(manager.currentFamily(),400).value("wdth").toInt(),100);
        // Retain V1's exact-coordinate contract as an explicit manual check.
        manager.setPreviewAutomatic(false);QVERIFY(manager.applyPreview());
        QCOMPARE(manager.variableAxesFor(manager.currentFamily(),400).value("wght").toInt(),500);
        QCOMPARE(manager.variableAxesFor(manager.currentFamily(),600).value("wght").toInt(),500);
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
    void optionalVariableAxesAndLivePreview();
    void optionalRestartRead();
    void optionalRenderMatrix();
    void optionalNativePointSizes();
    void optionalMetadataReplacement();
    void malformedImportPreservesState();
    void optionalPaintedPreviewAxes();
    void optionalRasterQualityMatrix();
    void optionalCffImport();
    void automaticAxesRespectDesignAndDpi();
    void manualProfilesAndAutomaticRestore();
    void automaticProfilesRestartAcrossProcess();
    void legacyAxisSettingsArePreserved();
    void automaticAxesProduceRealGlyphsAndFallback();
    void fontCachesAreBoundedAndStable();
    void displayContextHasBoundedLifecycle();
    void qmlLiveAutomaticFonts();
    void fontDisplayContextLifetime();
    void previewFontResourcesInvalidateRaster();
    void previewWindowMetricsAndIdleStability();
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
            if(!file.isEmpty()){QVERIFY(manager.importFont(QUrl::fromLocalFile(file)));QVERIFY(manager.applyPreview());}
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
void FontTests::optionalVariableAxesAndLivePreview(){
        const auto ttc=qEnvironmentVariable("SWIRL_TEST_TTC");
        if(ttc.isEmpty())QSKIP("Local-only variable font fixture not supplied");
        QTemporaryDir directory;
        QSettings::setDefaultFormat(QSettings::IniFormat);
        QSettings::setPath(QSettings::IniFormat,QSettings::UserScope,directory.path());
        QSettings().clear();
        FontManager manager(nullptr,directory.filePath("fonts"));
        const auto active=manager.currentFamily();
        QVERIFY(manager.importFont(QUrl::fromLocalFile(ttc)));
        QCOMPARE(manager.currentFamily(),active); // import/drag never silently apply
        QCOMPARE(manager.previewFamily(),QStringLiteral("PingFang UI SC"));
        QCOMPARE(manager.importedFamilies().size(),5);
        const auto defaults=manager.previewValues();
        QCOMPARE(defaults.value("wght").toInt(),500);
        QCOMPARE(defaults.value("wdth").toInt(),100);
        QCOMPARE(defaults.value("HGHT").toInt(),500);
        for(const auto &family:manager.importedFamilies()){
            QVERIFY(manager.choosePreviewFamily(family));
            QCOMPARE(manager.previewAxes().size(),3); // includes hidden axes
            QCOMPARE(manager.previewValues(),defaults);
        }
        QVERIFY(manager.choosePreviewFamily("PingFang UI SC"));
        QVERIFY(!manager.setPreviewAxis("fake",1));
        QVERIFY(!manager.setPreviewAxis("HGHT",0));
        QVERIFY(!manager.setPreviewAxis("HGHT",std::numeric_limits<double>::quiet_NaN()));
        QCOMPARE(manager.previewValues(),defaults);
        // A live QML Text consumes the actual OpenType axis. No transforms or static instances.
        QQmlEngine engine;engine.rootContext()->setContextProperty("fixture",&manager);
        QQmlComponent component(&engine);
        component.setData(R"(
import QtQuick
Window { width:850; height:230; color:"white"; visible:true
 Text { objectName:"preview"; x:16; y:16; color:"black";
 text:"苹方字体显示效果测试\nThe quick brown fox jumps over the lazy dog.\n0123456789\n@ # ¥ % &";
 font.family:fixture.previewFamily; font.pixelSize:25; font.styleName:"";
 font.variableAxes:fixture.previewValues; font.hintingPreference:Font.PreferFullHinting;
 renderType:Text.NativeRendering }
})",QUrl());
        QScopedPointer<QObject> root(component.create());
        QVERIFY2(root,qPrintable(component.errorString()));
        auto *window=qobject_cast<QQuickWindow *>(root.data());QVERIFY(window);
        window->hide();window->show();QVERIFY(QTest::qWaitForWindowExposed(window));
        auto *preview=root->findChild<QObject *>("preview");QVERIFY(preview);
        QImage before;QTRY_VERIFY(!(before=window->grabWindow()).isNull());
        const auto output=qEnvironmentVariable("SWIRL_FONT_EVIDENCE");
        if(!output.isEmpty()){QDir().mkpath(output);QVERIFY(before.save(output+"/original-default-live.png"));}
        QVERIFY(manager.setPreviewAxis("HGHT",1000));
        QTRY_COMPARE(preview->property("font").value<QFont>().variableAxisValue(QFont::Tag("HGHT")),1000);
        QImage after;QTRY_VERIFY(!(after=window->grabWindow()).isNull()&&after!=before);
        if(!output.isEmpty())QVERIFY(after.save(output+"/original-HGHT1000-live.png"));
        QCOMPARE(manager.currentFamily(),active);
        QVERIFY(manager.setPreviewAxis("wdth",113.25));
        QVERIFY(manager.setPreviewAxis("wght",623.5));
        QVERIFY(manager.applyPreview());
        QCOMPARE(QGuiApplication::font().variableAxisValue(QFont::Tag("HGHT")),1000);
        QCOMPARE(manager.variableAxesFor(manager.currentFamily(),400).value("wdth").toDouble(),113.25);
        // A second same-family apply must invalidate QML dependents.
        const int revision=manager.configurationRevision();
        QVERIFY(manager.setPreviewAxis("HGHT",250));QVERIFY(manager.applyPreview());
        QVERIFY(manager.configurationRevision()>revision);
        QVERIFY(manager.setPreviewAxis("HGHT",750)); // unconfirmed draft also survives restart
        QTest::qWait(250);
        QProcess child;auto environment=QProcessEnvironment::systemEnvironment();
        environment.insert("SWIRL_FONT_RESTORE_ROOT",directory.path());child.setProcessEnvironment(environment);
        child.start(QCoreApplication::applicationFilePath(),{"optionalRestartRead"});
        QVERIFY(child.waitForFinished(15000));
        QCOMPARE(child.exitStatus(),QProcess::NormalExit);
        QVERIFY2(child.exitCode()==0,child.readAllStandardOutput().constData());
        manager.discardPreview();QCOMPARE(manager.previewValues().value("HGHT").toInt(),250);
        manager.resetPreviewAxes();QCOMPARE(manager.previewValues(),defaults);
        QVERIFY(manager.importFont(QUrl::fromLocalFile(ttc)));
        QCOMPARE(QDir(directory.filePath("fonts")).entryList(QDir::Files).size(),1);
        QVERIFY(manager.choosePreviewFamily("PingFang UI TC"));
        QVERIFY(manager.setPreviewAxis("HGHT",811));
        QVERIFY(manager.setPreviewAxis("wght",628.5));
        QVERIFY(manager.setPreviewAxis("wdth",91.25));
        const auto collectionDraft=manager.previewValues();
        QVERIFY(manager.importFont(QUrl::fromLocalFile(ttc)));
        QCOMPARE(manager.previewFamily(),QStringLiteral("PingFang UI TC"));
        QCOMPARE(manager.previewValues(),collectionDraft);
        // A different collection stages its deterministic preferred family;
        // the active confirmed profile is unchanged until explicit Apply.
        const auto confirmedFamily=manager.currentFamily();
        QFile otherSource(":/swirl/fonts/HarmonyOS_Sans_SC_Regular.ttf");QVERIFY(otherSource.open(QIODevice::ReadOnly));
        QFile otherInput(directory.filePath("other.ttf"));QVERIFY(otherInput.open(QIODevice::WriteOnly));otherInput.write(otherSource.readAll());otherInput.close();
        QVERIFY(manager.importFont(QUrl::fromLocalFile(otherInput.fileName())));
        QCOMPARE(manager.previewFamily(),manager.defaultFamily());
        QCOMPARE(manager.currentFamily(),confirmedFamily);
        QVERIFY(manager.importFont(QUrl::fromLocalFile(ttc)));
        QCOMPARE(manager.previewFamily(),QStringLiteral("PingFang UI SC"));
        QCOMPARE(manager.currentFamily(),confirmedFamily);
    }
void FontTests::optionalRestartRead(){
        const auto directory=qEnvironmentVariable("SWIRL_FONT_RESTORE_ROOT");
        if(directory.isEmpty())QSKIP("Only run as the independent restoration child");
        QSettings::setDefaultFormat(QSettings::IniFormat);
        QSettings::setPath(QSettings::IniFormat,QSettings::UserScope,directory);
        FontManager manager(nullptr,directory+"/fonts");
        QCOMPARE(manager.currentFamily(),QStringLiteral("PingFang UI SC"));
        QCOMPARE(manager.variableAxesFor(manager.currentFamily(),400).value("HGHT").toInt(),250);
        QCOMPARE(manager.previewValues().value("HGHT").toInt(),750);
        QCOMPARE(manager.previewValues().value("wdth").toDouble(),113.25);
        QCOMPARE(manager.previewValues().value("wght").toDouble(),623.5);
    }
void FontTests::optionalRenderMatrix(){
        const auto ttc=qEnvironmentVariable("SWIRL_TEST_TTC");
        const auto output=qEnvironmentVariable("SWIRL_FONT_EVIDENCE");
        if(ttc.isEmpty()||output.isEmpty())QSKIP("Local-only matrix requires fixture and evidence directory");
        QTemporaryDir directory;
        QSettings::setDefaultFormat(QSettings::IniFormat);
        QSettings::setPath(QSettings::IniFormat,QSettings::UserScope,directory.path());QSettings().clear();
        FontManager manager(nullptr,directory.filePath("fonts"));QVERIFY(manager.importFont(QUrl::fromLocalFile(ttc)));
        QDir().mkpath(output);
        QJsonObject report{{"platform",QGuiApplication::platformName()},{"qpa",QString::fromUtf8(qgetenv("QT_QPA_PLATFORM"))},
            {"qt",qVersion()},{"scaleKind","QImage devicePixelRatio simulation; not a system scale change"}};
        QJsonArray screens;
        for(const auto *screen:QGuiApplication::screens())screens.append(QJsonObject{
            {"name",screen->name()},{"width",screen->geometry().width()},{"height",screen->geometry().height()},
            {"devicePixelRatio",screen->devicePixelRatio()},{"logicalDpi",screen->logicalDotsPerInch()},
            {"physicalDpi",screen->physicalDotsPerInch()},{"refreshRate",screen->refreshRate()}});
        report.insert("screens",screens);
        const QString sample=QStringLiteral("苹方字体显示效果测试\nThe quick brown fox jumps over the lazy dog.\n0123456789\n@ # ¥ % &");
        auto fontFor=[&](const QString &family,const QVariantMap &values,int points){
            QFont font(family);font.setPointSize(points);font.setStyleName(QString());font.setHintingPreference(QFont::PreferFullHinting);
            for(auto it=values.cbegin();it!=values.cend();++it)if(auto tag=QFont::Tag::fromString(it.key().toLatin1()))font.setVariableAxis(*tag,it.value().toFloat());
            return font;
        };
        auto render=[&](const QFont &font,qreal scale){
            QImage image(QSize(800*scale,180*scale),QImage::Format_ARGB32_Premultiplied);image.setDevicePixelRatio(scale);
            image.setDotsPerMeterX(qRound(96/0.0254));image.setDotsPerMeterY(qRound(96/0.0254));image.fill(Qt::white);
            QPainter painter(&image);painter.setPen(Qt::black);painter.setFont(font);
            painter.drawText(QRectF(16,12,768,156),Qt::AlignLeft|Qt::AlignTop,sample);painter.end();return image;
        };
        const auto defaults=manager.previewValues();
        QJsonArray axisChecks;
        for(const auto &family:manager.importedFamilies()){
            QVERIFY(manager.choosePreviewFamily(family));
            for(const auto &entry:manager.previewAxes()){
                const auto axis=entry.toMap();const auto tag=axis.value("tag").toString();
                auto low=defaults,high=defaults;low[tag]=axis["minimum"];high[tag]=axis["maximum"];
                const auto lowFont=fontFor(family,low,16),highFont=fontFor(family,high,16);
                const auto lowRaw=QRawFont::fromFont(lowFont),highRaw=QRawFont::fromFont(highFont);
                QVERIFY(lowRaw.isValid()&&highRaw.isValid());
                const auto a=render(lowFont,1),b=render(highFont,1);
                QVERIFY2(a!=b,qPrintable(family+" axis "+tag+" did not affect actual raster output"));
                const bool metrics=QFontMetricsF(lowFont).height()==QFontMetricsF(highFont).height();
                axisChecks.append(QJsonObject{{"family",family},{"axis",tag},{"rasterChanged",true},{"lineHeightStable",metrics},
                    {"lowFamily",lowRaw.familyName()},{"highFamily",highRaw.familyName()}});
            }
        }
        report.insert("axes",axisChecks);QJsonArray cases;
        QElapsedTimer timer;timer.start();int count=0;
        for(const int points:{9,10,11,12,13,14,16})for(const qreal scale:{1.,1.25,1.5,1.75,2.}){
            for(const double wght:{100.,500.,900.})for(const double wdth:{80.,100.,120.})for(const double hght:{1.,500.,1000.}){
                const QVariantMap values{{"wght",wght},{"wdth",wdth},{"HGHT",hght}};
                const auto font=fontFor("PingFang UI SC",values,points);QElapsedTimer sampleTimer;sampleTimer.start();
                const auto image=render(font,scale);const auto elapsed=sampleTimer.nsecsElapsed();
                const auto hash=QCryptographicHash::hash(QByteArrayView(reinterpret_cast<const char *>(image.constBits()),image.sizeInBytes()),QCryptographicHash::Sha256).toHex();
                int ink=0,borderInk=0;
                for(int y=0;y<image.height();++y)for(int x=0;x<image.width();++x)if(qGray(image.pixel(x,y))<240){++ink;if(x==0||y==0||x==image.width()-1||y==image.height()-1)++borderInk;}
                QVERIFY(ink>0);QVERIFY(borderInk==0);
                cases.append(QJsonObject{{"points",points},{"scale",scale},{"wght",wght},{"wdth",wdth},{"HGHT",hght},
                    {"sha256",QString::fromLatin1(hash)},{"rasterMs",elapsed/1000000.0},{"inkPixels",ink},{"borderInk",borderInk},
                    {"lineHeight",QFontMetricsF(font).height()}});
                if(wght==500&&wdth==100&&hght==500)QVERIFY(image.save(output+QString("/original-%1pt-%2pct-simulated.png").arg(points).arg(qRound(scale*100))));
                ++count;
            }
        }
        report.insert("samples",cases);report.insert("count",count);report.insert("elapsedMs",double(timer.elapsed()));
        QFile file(output+"/matrix.json");QVERIFY(file.open(QIODevice::WriteOnly));file.write(QJsonDocument(report).toJson());
        qInfo()<<"Render matrix"<<count<<"samples in"<<timer.elapsed()<<"ms; simulated DPI, local font fixture";
    }

void FontTests::optionalNativePointSizes()
{
    const auto ttc=qEnvironmentVariable("SWIRL_TEST_TTC"),output=qEnvironmentVariable("SWIRL_FONT_EVIDENCE");
    if(ttc.isEmpty()||output.isEmpty()||QGuiApplication::platformName()!="windows")QSKIP("Local Windows font fixture required");
    QTemporaryDir directory;QSettings::setDefaultFormat(QSettings::IniFormat);
    QSettings::setPath(QSettings::IniFormat,QSettings::UserScope,directory.path());QSettings().clear();
    FontManager manager(nullptr,directory.filePath("fonts"));QVERIFY(manager.importFont(QUrl::fromLocalFile(ttc)));
    QQmlEngine engine;engine.rootContext()->setContextProperty("fixture",&manager);QQmlComponent component(&engine);
    component.setData(R"qml(
import QtQuick
Window { width:1000; height:880; visible:true; color:"white"
 Column { x:16; y:12; spacing:8
  Repeater { model:[9,10,11,12,13,14,16]
   delegate:Text { required property int modelData; text:modelData+" pt · 苹方字体显示效果测试\nThe quick brown fox jumps over the lazy dog.\n0123456789  @ # ¥ % &";
    color:"black"; font.family:fixture.previewFamily; font.pointSize:modelData;
    font.variableAxes:fixture.previewValues; font.hintingPreference:Font.PreferFullHinting; renderType:Text.NativeRendering }
  }
 }
})qml",QUrl());
    QScopedPointer<QObject> root(component.create());QVERIFY2(root,qPrintable(component.errorString()));
    auto *window=qobject_cast<QQuickWindow *>(root.data());QVERIFY(window);window->hide();window->show();QVERIFY(QTest::qWaitForWindowExposed(window));
    QDir().mkpath(output);QJsonArray cases;QList<QVariantMap> coordinates{manager.previewValues()};
    for(const auto &entry:manager.previewAxes()){
        const auto axis=entry.toMap();for(const auto &bound:{"minimum","maximum"}){auto values=manager.previewValues();values[axis["tag"].toString()]=axis[bound];coordinates.append(values);}
    }
    for(double w:{100.,900.})for(double d:{80.,120.})for(double h:{1.,1000.})coordinates.append({{"wght",w},{"wdth",d},{"HGHT",h}});
    int index=0;
    for(const auto &values:coordinates){
        for(auto it=values.cbegin();it!=values.cend();++it)QVERIFY(manager.setPreviewAxis(it.key(),it.value().toDouble()));
        QTest::qWait(45);QImage image;QTRY_VERIFY(!(image=window->grabWindow()).isNull());
        const auto name=QString("/native-9-16pt-case-%1.png").arg(index++);QVERIFY(image.save(output+name));
        cases.append(QJsonObject{{"file",name.mid(1)},{"axes",QJsonObject::fromVariantMap(values)}});
    }
    QFile file(output+"/native-point-sizes.json");QVERIFY(file.open(QIODevice::WriteOnly));
    file.write(QJsonDocument(QJsonObject{{"dpr",window->devicePixelRatio()},{"qpa",QString::fromUtf8(qgetenv("QT_QPA_PLATFORM"))},{"cases",cases},
        {"kind","unprocessed Qt window renders at current display DPR; physical appearance not observed"}}).toJson());
}

void FontTests::optionalMetadataReplacement()
{
    const auto fixtures=qEnvironmentVariable("SWIRL_FONT_METADATA_FIXTURES");
    if(fixtures.isEmpty())QSKIP("Original synthetic metadata fixtures not supplied");
    const int staticId=QFontDatabase::addApplicationFont(fixtures+"/static.ttf");QVERIFY(staticId>=0);
    const auto family=QFontDatabase::applicationFontFamilies(staticId).first();
    QTemporaryDir directory;QSettings::setDefaultFormat(QSettings::IniFormat);
    QSettings::setPath(QSettings::IniFormat,QSettings::UserScope,directory.path());QSettings().clear();
    FontManager manager(nullptr,directory.filePath("fonts"));QVERIFY(manager.choosePreviewFamily(family));
    QVERIFY(manager.previewAxes().isEmpty());
    QQmlEngine engine;engine.rootContext()->setContextProperty("fixture",&manager);QQmlComponent component(&engine);
    component.setData("import QtQml\nQtObject { property int count: fixture.previewAxes.length; property real high: count ? fixture.previewAxes[0].maximum : -1 }",QUrl());
    QScopedPointer<QObject> model(component.create());QVERIFY(model);QCOMPARE(model->property("count").toInt(),0);
    // Remove the prior registration to make the selected physical face unambiguous.
    // The family name stays identical, exercising metadata notifications rather than name changes.
    QVERIFY(QFontDatabase::removeApplicationFont(staticId));
    QVERIFY(manager.importFont(QUrl::fromLocalFile(fixtures+"/variable.ttf")));
    QCOMPARE(manager.previewFamily(),family);QCOMPARE(manager.previewAxes().size(),1);
    QTRY_COMPARE(model->property("count").toInt(),1);
    QCOMPARE(manager.previewValues().value("HGHT").toInt(),500);
    QVERIFY(manager.setPreviewAxis("HGHT",800));
    for(int id=0;id<64;++id)if(QFontDatabase::applicationFontFamilies(id).contains(family))QFontDatabase::removeApplicationFont(id);
    QVERIFY(manager.importFont(QUrl::fromLocalFile(fixtures+"/range.ttf")));
    QCOMPARE(manager.previewFamily(),family);QTRY_COMPARE(model->property("high").toDouble(),600);
    QCOMPARE(manager.previewValues().value("HGHT").toInt(),600);
}

void FontTests::malformedImportPreservesState()
{
    QTemporaryDir directory;QSettings::setDefaultFormat(QSettings::IniFormat);
    QSettings::setPath(QSettings::IniFormat,QSettings::UserScope,directory.path());QSettings().clear();
    FontManager manager(nullptr,directory.filePath("fonts"));
    const auto active=manager.currentFamily(),draft=manager.previewFamily();const auto values=manager.previewValues();
    const QList<QByteArray> broken{
        QByteArray::fromHex("7474636600010000"), // TTC missing count/offsets
        QByteArray::fromHex("74746366000100000000000200000010"), // incomplete face directory
        QByteArray::fromHex("00010000000100000000000066766172000000000000001c0000001000010000001000020001001400000008"), // missing fvar axis record
        QByteArray::fromHex("0001000000010000000000006676617200000000fffffff000000010") // table outside file
    };
    int index=0;
    for(const auto &bytes:broken){
        QFile file(directory.filePath(QString("broken-%1.ttc").arg(index++)));QVERIFY(file.open(QIODevice::WriteOnly));
        QCOMPARE(file.write(bytes),bytes.size());file.close();QVERIFY(!manager.importFont(QUrl::fromLocalFile(file.fileName())));
        QCOMPARE(manager.currentFamily(),active);QCOMPARE(manager.previewFamily(),draft);QCOMPARE(manager.previewValues(),values);
    }
    QFile oversized(directory.filePath("oversized.ttf"));QVERIFY(oversized.open(QIODevice::WriteOnly));
    QVERIFY(oversized.resize(128LL*1024*1024+1));oversized.close();
    QVERIFY(!manager.importFont(QUrl::fromLocalFile(oversized.fileName())));
    QCOMPARE(manager.currentFamily(),active);QCOMPARE(manager.previewFamily(),draft);
    QVERIFY(QDir(directory.filePath("fonts")).entryList(QDir::Files).isEmpty());
}

void FontTests::optionalPaintedPreviewAxes()
{
    const auto ttc=qEnvironmentVariable("SWIRL_TEST_TTC");if(ttc.isEmpty())QSKIP("Local font fixture required");
    QTemporaryDir directory;QSettings::setDefaultFormat(QSettings::IniFormat);QSettings::setPath(QSettings::IniFormat,QSettings::UserScope,directory.path());QSettings().clear();
    FontManager manager(nullptr,directory.filePath("fonts"));QVERIFY(manager.importFont(QUrl::fromLocalFile(ttc)));
    qmlRegisterType<VariableFontPreview>("FontTest",1,0,"VariableFontPreview");
    QQmlEngine engine;engine.rootContext()->setContextProperty("fixture",&manager);QQmlComponent component(&engine);
    component.setData(R"qml(
import QtQuick
import FontTest
Window { width:850; height:200; color:"white"; visible:true
 VariableFontPreview { objectName:"preview"; x:16; y:16; width:810; height:implicitHeight
 text:"苹方字体显示效果测试 The quick brown fox jumps over the lazy dog. 0123456789 @ # ¥ % &";
 font.family:fixture.previewFamily; font.pixelSize:25; font.styleName:"";
 font.variableAxes:fixture.previewValues; font.hintingPreference:Font.PreferFullHinting }
})qml",QUrl());
    QScopedPointer<QObject> root(component.create());QVERIFY2(root,qPrintable(component.errorString()));
    auto *window=qobject_cast<QQuickWindow *>(root.data());QVERIFY(window);window->hide();window->show();QVERIFY(QTest::qWaitForWindowExposed(window));
    auto *preview=root->findChild<VariableFontPreview *>("preview");QVERIFY(preview);
    QPointer<QObject> instance=preview;
    for(const auto &entry:manager.previewAxes()){
        const auto axis=entry.toMap();const auto tag=axis["tag"].toString();manager.resetPreviewAxes();
        QVERIFY(manager.setPreviewAxis(tag,axis["minimum"].toDouble()));QTest::qWait(40);const auto low=window->grabWindow();
        QVERIFY(manager.setPreviewAxis(tag,axis["maximum"].toDouble()));
        QTRY_COMPARE(preview->font().variableAxisValue(*QFont::Tag::fromString(tag.toLatin1())),axis["maximum"].toFloat());
        QImage high;QTRY_VERIFY(!(high=window->grabWindow()).isNull()&&high!=low);
        QVERIFY(instance&&instance==preview);QVERIFY(preview->implicitHeight()>0&&preview->implicitHeight()<180);
    }
}

void FontTests::optionalCffImport()
{
    const auto fixtures=qEnvironmentVariable("SWIRL_FONT_METADATA_FIXTURES");if(fixtures.isEmpty())QSKIP("Synthetic CFF fixture not supplied");
    QTemporaryDir directory;QSettings::setDefaultFormat(QSettings::IniFormat);QSettings::setPath(QSettings::IniFormat,QSettings::UserScope,directory.path());QSettings().clear();
    FontManager manager(nullptr,directory.filePath("fonts"));const auto active=manager.currentFamily();
    QVERIFY2(manager.importFont(QUrl::fromLocalFile(fixtures+"/cff.otf")),qPrintable(manager.error()));
    QCOMPARE(manager.currentFamily(),active);QCOMPARE(manager.previewFamily(),QStringLiteral("Swirl CFF Probe"));
    QVERIFY(manager.previewAxes().isEmpty());QVERIFY(manager.applyPreview());
    QFont font(manager.currentFamily());font.setPixelSize(24);const auto raw=QRawFont::fromFont(font);
    QVERIFY(raw.isValid());QCOMPARE(raw.familyName(),QStringLiteral("Swirl CFF Probe"));QVERIFY(raw.supportsCharacter(QChar('A')));
    QImage image(100,60,QImage::Format_ARGB32_Premultiplied);image.fill(Qt::white);
    QPainter painter(&image);painter.setPen(Qt::black);painter.setFont(font);painter.drawText(QPointF(10,40),"A");painter.end();
    int ink=0;for(int y=0;y<image.height();++y)for(int x=0;x<image.width();++x)if(qGray(image.pixel(x,y))<240)++ink;
    QVERIFY(ink>20);
}

#include "FontRasterQualityChecks.h"
#include "FontAutomationChecks.h"
#include "FontQmlChecks.h"
#include "FontPreviewInvalidationChecks.h"

int main(int argc,char **argv){
    configureSwirlFontRendering();
    QGuiApplication::setHighDpiScaleFactorRoundingPolicy(Qt::HighDpiScaleFactorRoundingPolicy::PassThrough);
    QGuiApplication app(argc,argv);FontTests tests;return QTest::qExec(&tests,argc,argv);
}
#include "FontTests.moc"
