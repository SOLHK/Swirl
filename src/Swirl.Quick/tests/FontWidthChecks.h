#pragma once
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
