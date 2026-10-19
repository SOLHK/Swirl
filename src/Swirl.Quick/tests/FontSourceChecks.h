#pragma once
#include "FontSourceIdentity.h"
#include <QXmlStreamReader>

void FontTests::optionalPhysicalFontIdentity(){
    const auto path=qEnvironmentVariable("SWIRL_TEST_TTC"),output=qEnvironmentVariable("SWIRL_FONT_EVIDENCE");
    if(path.isEmpty()||output.isEmpty())QSKIP("Local source font and evidence path required");
    const auto expected=SwirlFontSource::faces(path);QVERIFY(!expected.isEmpty());
    const auto restore=qEnvironmentVariable("SWIRL_FONT_IDENTITY_RESTART");
    if(!restore.isEmpty()){
        QSettings::setDefaultFormat(QSettings::IniFormat);
        QSettings::setPath(QSettings::IniFormat,QSettings::UserScope,restore);
        FontManager restarted(nullptr,restore+"/fonts");
        QCOMPARE(restarted.currentFamily(),QStringLiteral("PingFang UI SC"));QVERIFY(restarted.automatic());
        QFont font(restarted.currentFamily());const auto identity=SwirlFontSource::identity(QRawFont::fromFont(font),expected);
        QVERIFY(identity["matchesSource"].toBool());
        QFile file(output+"/physical-font-restart.json");QVERIFY(file.open(QIODevice::WriteOnly));file.write(QJsonDocument(identity).toJson());return;
    }
    QTemporaryDir directory;QSettings::setDefaultFormat(QSettings::IniFormat);
    QSettings::setPath(QSettings::IniFormat,QSettings::UserScope,directory.path());QSettings().clear();
    QJsonArray samples;
    {FontManager manager(nullptr,directory.filePath("fonts"));QVERIFY(manager.importFont(QUrl::fromLocalFile(path)));QVERIFY(manager.applyPreview());
    for(const auto &family:manager.importedFamilies())for(int weight:{400,500,600,700})for(float width:{90.f,100.f}){
        QFont font(family);font.setPixelSize(20);font.setWeight(QFont::Weight(weight));font.setVariableAxis(QFont::Tag("wght"),weight);font.setVariableAxis(QFont::Tag("wdth"),width);
        QTextLayout layout(QStringLiteral("中文 Swirl 0123456789"),font);layout.beginLayout();auto line=layout.createLine();line.setLineWidth(1000);layout.endLayout();
        for(const auto &run:layout.glyphRuns()){auto sample=SwirlFontSource::identity(run.rawFont(),expected);samples.append(sample);QVERIFY2(sample["matchesSource"].toBool(),qPrintable(family));}
    }}
    QProcess child;auto environment=QProcessEnvironment::systemEnvironment();environment.insert("SWIRL_FONT_IDENTITY_RESTART",directory.path());child.setProcessEnvironment(environment);
    const auto childReport=output+"/physical-font-restart.xml";
    child.start(QCoreApplication::applicationFilePath(),{"optionalPhysicalFontIdentity","-o",childReport+",xml"});
    QVERIFY(child.waitForStarted());QVERIFY(child.waitForFinished(30000));QCOMPARE(child.exitStatus(),QProcess::NormalExit);QCOMPARE(child.exitCode(),0);
    QFile childXml(childReport);QVERIFY(childXml.open(QIODevice::ReadOnly));QXmlStreamReader xml(&childXml);int passes=0;
    while(!xml.atEnd()){xml.readNext();if(xml.isStartElement()&&xml.name()==u"Incident"){QCOMPARE(xml.attributes().value("type"),QString("pass"));++passes;}}
    QVERIFY(!xml.hasError());QCOMPARE(passes,3);
    QFile file(output+"/physical-font-identity.json");QVERIFY(file.open(QIODevice::WriteOnly));file.write(QJsonDocument(QJsonObject{{"samples",samples},{"independentRestartPassed",true}}).toJson());
}
