#pragma once
#include "app/FontWidthFit.h"
#include <QTextLayout>

namespace {
QFont widthResultFont(const QFont &requested, const QVariantMap &result)
{
    auto font=requested;
    font.clearVariableAxes();
    const auto axes=result.value("axes").toMap();
    for(auto it=axes.cbegin();it!=axes.cend();++it)
        if(auto tag=QFont::Tag::fromString(it.key().toLatin1()))font.setVariableAxis(*tag,it.value().toFloat());
    return font;
}

double widthLayoutAdvance(const QFont &font,const QString &text,double dpi)
{
    QImage device(1,1,QImage::Format_ARGB32_Premultiplied);
    device.setDotsPerMeterX(qRound(dpi/.0254));device.setDotsPerMeterY(qRound(dpi/.0254));
    QTextLayout layout(text,font,&device);
    QTextOption option;option.setWrapMode(QTextOption::NoWrap);option.setUseDesignMetrics(false);
    layout.setTextOption(option);
    layout.beginLayout();auto line=layout.createLine();
    if(line.isValid())line.setLineWidth(1e9);
    layout.endLayout();
    return line.isValid()?line.horizontalAdvance():0.;
}
}
void FontTests::automaticWidthUsesRealAdvances()
{
    const auto fixtures=qEnvironmentVariable("SWIRL_FONT_METADATA_FIXTURES");
    if(fixtures.isEmpty())QSKIP("Original public width fixture required");
    QTemporaryDir directory;QSettings::setDefaultFormat(QSettings::IniFormat);
    QSettings::setPath(QSettings::IniFormat,QSettings::UserScope,directory.path());QSettings().clear();
    FontManager manager(nullptr,directory.filePath("fonts"));
    QVERIFY2(manager.importFont(QUrl::fromLocalFile(fixtures+"/automation-width.otc")),qPrintable(manager.error()));
    QVERIFY(manager.applyPreview());
    QFont font(manager.currentFamily());font.setPixelSize(20);font.setWeight(QFont::DemiBold);
    const auto fit=[&](double space,double previous=100.,const QString &role="button"){
        return manager.fittedText(font,"AAAAAAAA",96,1.5,role,space,previous);
    };
    const double natural=fit(1000).value("naturalWidth").toDouble();QVERIFY(natural>50);
    const auto roomy=fit(natural+10);QCOMPARE(roomy.value("axes").toMap().value("wdth").toDouble(),100.);
    const auto tight=fit(natural-12);QVERIFY(tight.value("fitted").toBool());
    const auto axes=tight.value("axes").toMap();const double width=axes.value("wdth").toDouble();
    QVERIFY(width>=90&&width<100);QCOMPARE(axes.value("wght").toDouble(),600.);
    QCOMPARE(tight.value("naturalWidth").toDouble(),natural);QCOMPARE(font.pixelSize(),20);
    QFont compressed=font;compressed.setVariableAxis(QFont::Tag("wdth"),float(width));
    QVERIFY(QFontMetricsF(compressed).horizontalAdvance("AAAAAAAA")<natural-1);
    // More samples must never select an illegal axis coordinate or allow
    // disproportionate advance compression.
    for(const double space:{natural-4,natural-12,natural-24,natural*.5}){
        const auto outcome=fit(space);
        const double coordinate=outcome.value("axes").toMap().value("wdth").toDouble();
        QVERIFY(coordinate>=90.&&coordinate<=100.);
        if(outcome.value("fitted").toBool()){
            QFont candidate=font;
            candidate.setVariableAxis(QFont::Tag("wght"),600.f);
            candidate.setVariableAxis(QFont::Tag("wdth"),float(coordinate));
            const double actual=QFontMetricsF(candidate).horizontalAdvance("AAAAAAAA");
            QVERIFY(actual>=natural*.85-1.);
            QVERIFY(actual<natural);
        }
    }
    const auto stable=fit(natural-12+.2,width);QCOMPARE(stable.value("axes").toMap(),axes);
    QCOMPARE(fit(natural+10,width).value("axes").toMap().value("wdth").toDouble(),100.);
    QCOMPARE(fit(natural-12,100,"body").value("axes").toMap().value("wdth").toDouble(),100.);
    QCOMPARE(fit(natural-12,100,"data").value("axes").toMap().value("wdth").toDouble(),100.);
    QCOMPARE(fit(-1).value("axes").toMap().value("wdth").toDouble(),100.);
    QVERIFY(manager.setPreviewAxis("wdth",107.25));QVERIFY(manager.applyPreview());
    QCOMPARE(fit(natural-12).value("axes").toMap().value("wdth").toDouble(),107.25);
    manager.setPreviewAutomatic(true);QVERIFY(manager.applyPreview());
    QVERIFY(manager.importFont(QUrl::fromLocalFile(fixtures+"/automation.ttf")));QVERIFY(manager.applyPreview());
    font.setFamily(manager.currentFamily());
    // This fixture changes outlines while keeping the advance invariant.
    const auto invariant=fit(1);QVERIFY(!invariant.value("fitted").toBool());
    QCOMPARE(invariant.value("axes").toMap().value("wdth").toDouble(),100.);
    QVERIFY(manager.selectFamily(manager.defaultFamily()));font.setFamily(manager.currentFamily());
    QVERIFY(!fit(1).value("axes").toMap().contains("wdth"));
}

void FontTests::automaticWidthNonmonotonicFonts()
{
    const auto fixtures=qEnvironmentVariable("SWIRL_FONT_METADATA_FIXTURES");
    if(fixtures.isEmpty())QSKIP("Original public nonmonotonic width fixtures required");
    QTemporaryDir directory;isolateFontSettings(directory);
    FontManager manager(nullptr,directory.filePath("fonts"));
    const QString text="AAAAAAAA";
    const auto import=[&](const char *name){
        return manager.importFont(QUrl::fromLocalFile(fixtures+'/'+name))&&manager.applyPreview();
    };
    QVERIFY(import("automation-width-nonmonotonic.ttf"));
    QFont font(manager.currentFamily());font.setPixelSize(50);font.setWeight(QFont::DemiBold);
    const auto at=[&](double coordinate){
        QFont value=font;value.setVariableAxis(QFont::Tag("wght"),600.f);
        value.setVariableAxis(QFont::Tag("wdth"),float(coordinate));
        return widthLayoutAdvance(value,text,96);
    };
    const double natural=at(100),valley=at(99.1);
    QVERIFY(natural>200);QVERIFY(valley<natural-20);
    QVERIFY(qAbs(at(99)-natural)<.1);QVERIFY(qAbs(at(98.5)-natural)<.1);
    const double available=natural-20;
    const auto fit=manager.fittedText(font,text,96,1,"button",available,100);
    QVERIFY(fit.value("fitted").toBool());
    const double chosen=fit.value("axes").toMap().value("wdth").toDouble();
    QVERIFY(qAbs(chosen-99.1)<.001);
    const double actual=widthLayoutAdvance(widthResultFont(font,fit),text,96);
    QVERIFY(actual<=available-2);QVERIFY(actual>=natural*.85);
    // The old default-percent grid sees only 99 and 98.5 here. The production
    // solver must find the interior valley using this same real Qt font engine.
    const auto stale=manager.fittedText(font,text,96,1,"button",available,98.5);
    QCOMPARE(stale.value("axes"),fit.value("axes"));

    QVERIFY(import("automation-width-steep.ttf"));font.setFamily(manager.currentFamily());
    const double steepNatural=at(100),unsafe=at(90);
    QVERIFY(unsafe<steepNatural*.85);
    const auto safe=manager.fittedText(font,text,96,1,"button",unsafe,90);
    const double safeWidth=widthLayoutAdvance(widthResultFont(font,safe),text,96);
    QVERIFY(safeWidth>=steepNatural*.85);
    QVERIFY(safe.value("axes").toMap().value("wdth").toDouble()>90);
    // A safe partial improvement is allowed; residual overflow still elides.
    QVERIFY(safeWidth>unsafe);QCOMPARE(font.pixelSize(),50);

    QVERIFY(import("automation-width-asymmetric.ttf"));font.setFamily(manager.currentFamily());
    const double asymmetricNatural=at(100);
    const auto minimum=manager.fittedText(font,text,96,2,"label",1,100);
    QCOMPARE(minimum.value("axes").toMap().value("wdth").toDouble(),96.);
    QVERIFY(widthLayoutAdvance(widthResultFont(font,minimum),text,96)>=asymmetricNatural*.85);
    const auto restored=manager.fittedText(font,text,96,2,"label",asymmetricNatural+10,96);
    QCOMPARE(restored.value("axes").toMap().value("wdth").toDouble(),100.);
}

void FontTests::automaticWidthShaping()
{
    const auto fixtures=qEnvironmentVariable("SWIRL_FONT_METADATA_FIXTURES");
    if(fixtures.isEmpty())QSKIP("Original public width fixture required");
    QTemporaryDir directory;isolateFontSettings(directory);
    FontManager manager(nullptr,directory.filePath("fonts"));
    QVERIFY(manager.importFont(QUrl::fromLocalFile(fixtures+"/automation-width.ttf")));
    QVERIFY(manager.applyPreview());
    const QStringList texts{
        QStringLiteral("AAAAAAAA"),QStringLiteral("A"),
        QStringLiteral("AAAA 中文 012345，.!?"),QStringLiteral("AAAA fi ffi office"),
        QStringLiteral("AAAA e\u0301 A\u0308 o\u0327"),
        QStringLiteral("العربية لا سلام AAAA"),QStringLiteral("עברית 123 AAAA"),
        QStringLiteral("AAAA 中文 e\u0301 0123 ").repeated(32)
    };
    int combinations=0;
    for(const auto &text:texts)for(const int pixels:{12,20,36})for(const int weight:{400,700})
        for(const double dpi:{96.,144.}) {
        QFont font=QGuiApplication::font();font.setPixelSize(pixels);font.setWeight(QFont::Weight(weight));
        const QFont unchanged=font;
        const auto roomy=manager.fittedText(font,text,dpi,1,"label",1e8,100);
        const auto naturalFont=widthResultFont(font,roomy);
        const double natural=widthLayoutAdvance(naturalFont,text,dpi);
        QVERIFY2(natural>0,qPrintable(text));
        QVERIFY(qAbs(roomy.value("naturalWidth").toDouble()-natural)<.05);
        QCOMPARE(roomy.value("axes").toMap().value("wdth").toDouble(),100.);
        const auto tight=manager.fittedText(font,text,dpi,1,"label",natural*.90,100);
        const auto highDpr=manager.fittedText(font,text,dpi,2,"label",natural*.90,100);
        QCOMPARE(highDpr,tight); // DPR is a rendering scale, not a second font-size multiplier.
        const auto actualFont=widthResultFont(font,tight);
        const double actual=widthLayoutAdvance(actualFont,text,dpi);
        const auto coordinate=tight.value("axes").toMap().value("wdth").toDouble();
        QVERIFY(coordinate>=90&&coordinate<=100);
        QVERIFY(actual>=natural*.85);
        if(tight.value("fitted").toBool())QVERIFY(actual<natural-.5);
        QCOMPARE(actualFont.pixelSize(),pixels);QCOMPARE(actualFont.weight(),QFont::Weight(weight));
        QCOMPARE(font,unchanged);
        ++combinations;
    }
    // Preserve the original point unit and actual Qt device DPI as well.
    QFont points(manager.currentFamily());points.setPointSizeF(13.5);
    for(const double dpi:{96.,144.,192.}) {
        const auto result=manager.fittedText(points,"AAAAAAAA",dpi,2,"button",1e6,100);
        QVERIFY(qAbs(result.value("naturalWidth").toDouble()
            -widthLayoutAdvance(widthResultFont(points,result),"AAAAAAAA",dpi))<.05);
        QCOMPARE(points.pixelSize(),-1);QCOMPARE(points.pointSizeF(),13.5);
    }
    qInfo().noquote()<<"Width shaping: real QTextLayout comparisons="<<combinations
        <<"plus 3 point-size/DPI cases; mixed CJK/Latin, combining marks, Arabic, Hebrew and long labels.";
}

void FontTests::automaticWidthCacheAndResize()
{
    const auto fixtures=qEnvironmentVariable("SWIRL_FONT_METADATA_FIXTURES");
    if(fixtures.isEmpty())QSKIP("Original public width fixture required");
    QTemporaryDir directory;isolateFontSettings(directory);
    FontManager manager(nullptr,directory.filePath("fonts"));
    QVERIFY(manager.importFont(QUrl::fromLocalFile(fixtures+"/automation-width.ttf")));
    QVERIFY(manager.applyPreview());QCoreApplication::processEvents();
    QFont font=QGuiApplication::font();font.setPixelSize(24);
    const QString text="AAAAAAAA";
    const auto fit=[&](double available,double previous=100.,double dpr=1.){
        return manager.fittedText(font,text,96,dpr,"button",available,previous);
    };
    auto count=manager.textWidthMeasurementCount();
    const auto cold=fit(1);
    const auto coldMeasurements=manager.textWidthMeasurementCount()-count;
    QCOMPARE(coldMeasurements,quint64(FontWidthFit::sampleCount+1));
    const double natural=cold.value("naturalWidth").toDouble();
    auto previous=cold.value("axes").toMap().value("wdth").toDouble();
    count=manager.textWidthMeasurementCount();
    QVector<qint64> durations;durations.reserve(400);
    for(int i=0;i<400;++i) {
        // Sweep both directions across the fitting domain and exit margin.
        const int phase=i%100;
        const double available=natural*(.5+(phase<50?phase:100-phase)*.012);
        QElapsedTimer timer;timer.start();const auto result=fit(available,previous,(i%2)?2:1);
        durations.append(timer.nsecsElapsed());
        previous=result.value("axes").toMap().value("wdth").toDouble();
        QVERIFY(previous>=90&&previous<=100);
        const auto actual=widthLayoutAdvance(widthResultFont(font,result),text,96);
        QVERIFY(actual>=natural*.85);
        QCOMPARE(result.value("naturalWidth").toDouble(),natural);
    }
    QCOMPARE(manager.textWidthMeasurementCount(),count);
    QCOMPARE(manager.textWidthCacheSize(),FontWidthFit::sampleCount+1);
    std::sort(durations.begin(),durations.end());
    qInfo().noquote()<<"Width cache benchmark: Qt="<<qVersion()<<"platform="<<QGuiApplication::platformName()
        <<"coldRealMeasurements="<<coldMeasurements<<"warmResizeCalls=400 warmRealMeasurements=0"
        <<"medianUs="<<durations[200]/1000.<<"p95Us="<<durations[380]/1000.;

    // Different text, size, weight, features and spacing must not share widths.
    for(int i=0;i<8;++i) {
        auto changed=font;
        QString changedText=text;
        switch(i) {
        case 0: changedText+="A";break;
        case 1: changed.setPixelSize(31);break;
        case 2: changed.setWeight(QFont::Bold);break;
        case 3: changed.setLetterSpacing(QFont::AbsoluteSpacing,1.25);break;
        case 4: changed.setWordSpacing(2.5);changedText+=" A";break;
        case 5: changed.setItalic(true);break;
        case 6: changed.setFeature(QFont::Tag("kern"),0);break;
        case 7: changed.setFamily(manager.defaultFamily());break;
        }
        count=manager.textWidthMeasurementCount();
        const auto result=manager.fittedText(changed,changedText,96,1,"button",1e6,100);
        QVERIFY(manager.textWidthMeasurementCount()>count);
        QVERIFY(qAbs(result.value("naturalWidth").toDouble()
            -widthLayoutAdvance(widthResultFont(changed,result),changedText,96))<.05);
    }
    // Font database add/remove events invalidate cached measurements even if
    // the requested text and QFont values stay equal. Own only this external ID.
    const int id=QFontDatabase::addApplicationFont(fixtures+"/automation-width-nonmonotonic.ttf");
    QVERIFY(id>=0);QCOMPARE(manager.textWidthCacheSize(),0);
    QCoreApplication::processEvents();count=manager.textWidthMeasurementCount();
    fit(1);QVERIFY(manager.textWidthMeasurementCount()>count);
    QVERIFY(QFontDatabase::removeApplicationFont(id));QCOMPARE(manager.textWidthCacheSize(),0);
    QCoreApplication::processEvents();
    for(int i=0;i<350;++i) {
        manager.fittedText(font,text+QString::number(i),96,1,"button",1,100);
        QVERIFY(manager.textWidthCacheSize()<=256);
    }
    QVERIFY(manager.textWidthCacheSize()>0);
    qInfo()<<"Width cache remains <=256 entries after 350 distinct texts; add/remove invalidation checked. This is not an RSS leak measurement.";
}
