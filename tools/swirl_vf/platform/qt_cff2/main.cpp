// Authored CFF2 control probe only. This does not accept SwirlVF.ttc.
// Run with FONT.ttc and an isolated output directory; software captures do not
// establish physical high-DPI, Chinese coverage or final-font acceptance.
#include <QGuiApplication>
#include <QFontDatabase>
#include <QFontInfo>
#include <QRawFont>
#include <QPainter>
#include <QPainterPath>
#include <QJsonDocument>
#include <QJsonArray>
#include <QJsonObject>
#include <QFile>
#include <QDir>
#include <QCryptographicHash>
#include <QQmlEngine>
#include <QQmlComponent>
#include <QQuickWindow>
#include <QThread>
#include <cstdio>
#include <memory>
int main(int argc,char**argv) {
    QGuiApplication app(argc,argv);
    if(argc!=3)return 2;
    QDir out(QString::fromUtf8(argv[2]));QDir().mkpath(out.path());
    QFile input(QString::fromUtf8(argv[1]));if(!input.open(QIODevice::ReadOnly))return 3;
    const auto bytes=input.readAll();const int id=QFontDatabase::addApplicationFontFromData(bytes);
    QJsonObject report{{"qt",qVersion()},{"qpa",QGuiApplication::platformName()},
        {"font_sha256",QString::fromLatin1(QCryptographicHash::hash(bytes,QCryptographicHash::Sha256).toHex())},
        {"scope","authored CFF2; QPainter/QML software captures, not physical DPI or final Swirl acceptance"}};
    const auto families=QFontDatabase::applicationFontFamilies(id);QJsonArray rows;bool ok=id>=0&&families.size()==2;
    for(qsizetype fi=0;fi<families.size();++fi){
        QFont base(families[fi]);base.setPixelSize(80);base.setStyleName({});base.clearVariableAxes();
        for(const auto &tag:{"WDTH","wght","HGHT"}){
            QByteArray previous;
            for(int side=0;side<2;++side){
                QFont font=base;font.setVariableAxis(QFont::Tag("WDTH"),500);
                font.setVariableAxis(QFont::Tag("wght"),400);font.setVariableAxis(QFont::Tag("HGHT"),500);
                font.setVariableAxis(*QFont::Tag::fromString(QByteArray(tag)),side?(QByteArray(tag)=="wght"?900:1000):(QByteArray(tag)=="wght"?100:1));
                QRawFont raw=QRawFont::fromFont(font);const auto gids=raw.glyphIndexesForString("A");
                QPainterPath path=gids.isEmpty()?QPainterPath():raw.pathForGlyph(gids[0]);QByteArray coordinates;
                for(int i=0;i<path.elementCount();++i){auto e=path.elementAt(i);coordinates+=QByteArray::number(e.x,'g',17)+","+QByteArray::number(e.y,'g',17)+";";}
                bool identity=raw.isValid()&&raw.familyName()==families[fi]&&!raw.fontTable("CFF2").isEmpty()&&gids.size()==1&&gids[0]==2;
                bool changed=side==0||coordinates!=previous;ok &=identity&&changed&&!path.isEmpty()&&QFontInfo(font).variableAxes().size()==3;previous=coordinates;
                QJsonArray rasters;
                for(double dpr:{1.,1.25,1.5,1.75,2.}){
                    QImage image(QSize(400*dpr,160*dpr),QImage::Format_ARGB32_Premultiplied);image.setDevicePixelRatio(dpr);image.fill(Qt::white);
                    QPainter painter(&image);painter.setPen(Qt::black);painter.setFont(font);painter.drawText(QPointF(20,110),"A A");painter.end();
                    auto name=QString("face%1-%2-%3-%4.png").arg(fi).arg(tag).arg(side).arg(dpr);
                    ok &=image.save(out.filePath(name));rasters.append(name);
                }
                rows.append(QJsonObject{{"family",families[fi]},{"axis",tag},{"side",side},{"identity",identity},{"axis_changes_path",changed},{"path_elements",path.elementCount()},{"rasters",rasters}});
            }
        }
        QQmlEngine engine;QQmlComponent component(&engine);int warnings=0;
        QObject::connect(&engine,&QQmlEngine::warnings,[&](const QList<QQmlError>& errors){warnings+=errors.size();});
        component.setData("import QtQuick\nWindow { id: root; width: 400; height: 180; visible: true; color: 'white'; required property font probeFont; Text { objectName: 'probeText'; x: 20; y: 20; text: 'A A'; font: root.probeFont; color: 'black' } }",QUrl());
        std::unique_ptr<QObject> object(component.createWithInitialProperties({{"probeFont",base}}));auto window=qobject_cast<QQuickWindow*>(object.get());
        if(!window){ok=false;continue;}
        auto text=window->findChild<QObject*>("probeText");
        ok &=text&&text->property("font").value<QFont>().family()==families[fi]&&warnings==0;
        for(int i=0;i<20;++i){app.processEvents();QThread::msleep(10);}
        auto image=window->grabWindow();ok &=!image.isNull()&&image.save(out.filePath(QString("qml-face%1.png").arg(fi)));window->close();
    }
    report["status"]=ok?"PASS_AUTHORED_QT_SCOPE":"FAIL";report["rows"]=rows;
    QFile file(out.filePath("result.json"));if(!file.open(QIODevice::WriteOnly))return 4;file.write(QJsonDocument(report).toJson());
    QFontDatabase::removeApplicationFont(id);std::printf("%s\n",ok?"PASS_AUTHORED_QT_SCOPE":"FAIL");return ok?0:1;
}
