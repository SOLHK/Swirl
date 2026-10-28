#include <QQuickWindow>
#include <QQuickItem>
#include <QQuickItemGrabResult>
#include <QQmlEngine>
#include <QQmlContext>
#include <QQmlComponent>
#include <QQmlExpression>
#include <QTest>
#include <QSignalSpy>
#include <QJsonDocument>
#include <QJsonArray>
#include <QJsonObject>
#include <QFile>
#include <QFileInfo>
#include <QDir>
#include <QSGRendererInterface>
#include <memory>

int runApecGlassChecks(QQuickWindow *window,const QString &output) {
    QJsonArray checks;int failures=0;
    const auto check=[&](const char *name,bool passed){checks.append(QJsonObject{{"name",name},{"passed",passed}});if(!passed)++failures;qInfo()<<"APEC_GLASS_CHECK"<<name<<passed;};
    const auto eval=[&](const QString &code){QQmlExpression expression(qmlContext(window),window,code);auto value=expression.evaluate();if(expression.hasError()){qWarning()<<expression.error();check("qml-expression",false);}return value;};
    check("gpu-backend",window->rendererInterface()->graphicsApi()!=QSGRendererInterface::Software);
    eval("Theme.mode='Light';Theme.transparency=true;Theme.increaseContrast=false;Theme.reduceMotion=true");
    window->resize(1100,760);window->requestActivate();QTest::qWait(200);
    auto *productionShader=window->findChild<QObject *>("sidebarLiquidShader");
    // Check the first real application instance. Qt 6.12's global shader-info
    // cache bypasses prepareShaderCode on later instances, leaving their
    // manager's status at Uncompiled despite successful native rendering.
    check("native-shader-compiled",productionShader && productionShader->property("status").toInt()==0 && productionShader->property("log").toString().isEmpty());
    auto *scene=qvariant_cast<QQuickItem *>(eval("appSceneBackdrop"));
    auto *decoration=scene?scene->findChild<QQuickItem *>("workspaceWingDecoration"):nullptr;
    const auto grab=[&](QQuickItem *item){
        if(!item)return QImage{};
        auto result=item->grabToImage();if(!result)return QImage{};
        QSignalSpy ready(result.data(),&QQuickItemGrabResult::ready);window->update();
        if(result->image().isNull())ready.wait(2000);
        return result->image();
    };
    auto *productionGlass=window->findChild<QQuickItem *>("sidebarLiquidGlass");
    const auto clearGlass=grab(productionGlass);
    check("sidebar-preserves-shared-window-base",!clearGlass.isNull() && clearGlass.pixelColor(clearGlass.width()/2,clearGlass.height()/4).alpha()<3);
    check("wing-decoration-spans-workspace",decoration && decoration->width()==scene->width() && decoration->height()==scene->height());
    if(decoration){
        auto decorated=grab(scene);
        decoration->setVisible(false);QTest::qWait(35);auto plain=grab(scene);
        qint64 rightSideChanges=0;
        if(!decorated.isNull() && decorated.size()==plain.size())
            for(int y=0;y<plain.height();++y)for(int x=plain.width()/2;x<plain.width();++x)
                if(decorated.pixelColor(x,y)!=plain.pixelColor(x,y))++rightSideChanges;
        check("wing-decoration-reaches-uncovered-right-workspace",rightSideChanges>100);
        QQmlComponent cardComponent(qmlEngine(window));
        cardComponent.setData("import QtQuick; import SwirlQuick; SwirlGlassPanel {x:280;y:180;width:240;height:160}",QUrl("qrc:/qt/qml/SwirlQuick/WingCardFixture.qml"));
        std::unique_ptr<QObject> cardOwner(cardComponent.create(qmlContext(window)));
        auto *card=qobject_cast<QQuickItem *>(cardOwner.get());
        if(card){
            card->setParentItem(scene);const auto before=grab(card);
            decoration->setVisible(true);QTest::qWait(35);const auto after=grab(card);
            check("opaque-card-occludes-workspace-wings",!before.isNull() && before==after && after.pixelColor(after.width()/2,after.height()/2).alpha()==255);
        }else check("opaque-card-fixture",false);
        decoration->setVisible(true);
    }
    QQmlComponent component(qmlEngine(window));
    component.setData(R"QML(
import QtQuick
import SwirlQuick
Item {
 id:fixture;x:240;y:120;width:440;height:320;z:110
 property alias source:scene
 property alias glass:glass
 Rectangle {
  id:scene;width:440;height:320;color:"#164C85"
  Rectangle {x:220;width:220;height:320;color:"#F1C888"}
  Rectangle {x:17;y:0;width:9;height:320;color:"#FFFFFF"}
  Rectangle {x:410;y:0;width:8;height:320;color:"#182A40"}
 }
 SwirlLiquidGlass {id:glass;x:20;y:20;width:400;height:280;backdropSource:scene;cornerRadius:20}
})QML",QUrl("qrc:/qt/qml/SwirlQuick/ApecGlassFixture.qml"));
    std::unique_ptr<QObject> owner(component.create(qmlContext(window)));
    auto *fixture=qobject_cast<QQuickItem *>(owner.get());
    if(!fixture){qWarning()<<component.errors();check("fixture-load",false);}
    const auto directory=QFileInfo(output).absolutePath();QDir().mkpath(directory);
    if(fixture){
        fixture->setParentItem(window->contentItem());
        qmlEngine(window)->rootContext()->setContextProperty("apecGlass",fixture);
        QTest::qWait(180);
        auto *glass=qvariant_cast<QQuickItem *>(fixture->property("glass"));
        if(!glass)glass=qobject_cast<QQuickItem *>(fixture->property("glass").value<QObject *>());
        check("fixture-load",glass!=nullptr);
        const auto capture=[&](){
            if(!glass)return QImage{};
            auto result=glass->grabToImage();if(!result)return QImage{};
            QSignalSpy ready(result.data(),&QQuickItemGrabResult::ready);window->update();
            if(result->image().isNull())ready.wait(2000);
            return result->image();
        };
        const auto sample=[](const QImage &image,qreal x,qreal y){return image.pixelColor(qBound(0,qRound(x*image.width()/400.),image.width()-1),qBound(0,qRound(y*image.height()/280.),image.height()-1));};
        const auto difference=[](const QImage &a,const QImage &b){qint64 value=0;if(a.size()!=b.size())return qint64(-1);for(int y=0;y<a.height();++y)for(int x=0;x<a.width();++x){const auto p=a.pixelColor(x,y),q=b.pixelColor(x,y);value+=qAbs(p.red()-q.red())+qAbs(p.green()-q.green())+qAbs(p.blue()-q.blue());}return value;};
        auto initial=capture();
        auto *shader=glass?glass->findChild<QObject *>("sidebarLiquidShader"):nullptr;
        qInfo()<<"APEC_GLASS_SHADER_STATUS"<<(shader?shader->property("status"):QVariant())<<(shader?shader->property("log"):QVariant())<<"early-binding"<<glass->property("shaderStatus");
        check("cached-fixture-shader-has-no-error",shader && shader->property("status").toInt()!=2 && shader->property("log").toString().isEmpty());
        check("native-readback",!initial.isNull());
        if(!initial.isNull()){
            initial.save(directory+"/glass-source-blue.png");
            check("rounded-clip-transparent-corner",initial.pixelColor(0,0).alpha()<8);
            const auto left=sample(initial,100,140),right=sample(initial,300,140),edge=sample(initial,200,140);
            check("source-colours-transmitted",right.red()>left.red()+30 && left.blue()>left.red());
            check("blur-mixes-source-boundary",edge.red()>left.red()+8 && edge.red()<right.red()-8);
            eval("apecGlass.source.color='#BD334F'");QTest::qWait(100);auto changed=capture();changed.save(directory+"/glass-source-red.png");
            check("live-source-change-reaches-material",!changed.isNull() && sample(changed,100,140).red()>left.red()+35);
            eval("apecGlass.glass.refraction=0");QTest::qWait(60);auto unrefracted=capture();
            check("edge-refraction-changes-sampled-pixels",!changed.isNull() && !unrefracted.isNull() && difference(changed,unrefracted)>100);
            eval("apecGlass.glass.interaction=1;apecGlass.glass.lightPoint=Qt.point(0,0)");QTest::qWait(60);auto lit=capture();
            check("interaction-drives-directional-rim",!lit.isNull() && difference(lit,unrefracted)>100);
            eval("apecGlass.source.color='#40BD334F'");QTest::qWait(60);auto translucent=capture();
            check("glass-preserves-transmitted-alpha",!translucent.isNull() && qAbs(sample(translucent,100,140).alpha()-64)<=2);
            eval("apecGlass.source.color='#BD334F'");
        }
        const auto size=eval("apecGlass.glass.captureSize").toSizeF();
        check("capture-bounded-to-panel",size.width()<=440 && size.height()<=320 && size.width()>0 && size.height()>0);
        eval("apecGlass.glass.visible=false");QTest::qWait(30);check("hidden-capture-stopped",!eval("apecGlass.glass.captureLive").toBool());
        eval("apecGlass.glass.visible=true;Theme.transparency=false");QTest::qWait(60);
        check("opaque-fallback-releases-sample",eval("!apecGlass.glass.sampled && !apecGlass.glass.captureLive").toBool());
        const auto opaque=capture();
        check("opaque-fallback-pixels",!opaque.isNull() && sample(opaque,100,140).red()>245 && sample(opaque,300,140).red()>245 && sample(opaque,100,140).alpha()==255);
        eval("Theme.transparency=true;Theme.increaseContrast=true");QTest::qWait(60);
        check("high-contrast-fallback",eval("!apecGlass.glass.sampled && !apecGlass.glass.captureLive").toBool());
        eval("Theme.increaseContrast=false;Theme.mode='Dark'");QTest::qWait(100);auto dark=capture();
        check("dark-material-readback",!dark.isNull());if(!dark.isNull())dark.save(directory+"/glass-dark.png");
        qmlEngine(window)->rootContext()->setContextProperty("apecGlass",static_cast<QObject *>(nullptr));
    }
    QFile file(output);if(!file.open(QIODevice::WriteOnly))return 2;
    file.write(QJsonDocument(QJsonObject{{"checks",checks},{"failures",failures},{"qtVersion",qVersion()},{"graphicsApi",int(window->rendererInterface()->graphicsApi())},{"scope","Native app-source pixel readback; not desktop sampling, physical refresh, DPI or private-network acceptance"}}).toJson());
    return failures?1:0;
}
