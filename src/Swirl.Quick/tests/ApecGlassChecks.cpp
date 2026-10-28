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
#include <functional>

int runApecGlassChecks(QQuickWindow *window,const QString &output) {
    QJsonArray checks;int failures=0;
    const auto check=[&](const char *name,bool passed){checks.append(QJsonObject{{"name",name},{"passed",passed}});if(!passed)++failures;qInfo()<<"APEC_GLASS_CHECK"<<name<<passed;};
    const auto eval=[&](const QString &code){QQmlExpression expression(qmlContext(window),window,code);auto value=expression.evaluate();if(expression.hasError()){qWarning()<<expression.error();check("qml-expression",false);}return value;};
    std::function<QQuickItem *(QQuickItem *,const QString &)> findVisual;
    findVisual=[&](QQuickItem *root,const QString &name)->QQuickItem *{
        if(!root)return nullptr;
        if(root->objectName()==name)return root;
        for(auto *child:root->childItems())if(auto *found=findVisual(child,name))return found;
        return nullptr;
    };
    check("gpu-backend",window->rendererInterface()->graphicsApi()!=QSGRendererInterface::Software);
    bool expectedDprSet=false;
    const auto expectedDpr=qEnvironmentVariable("SWIRL_EXPECTED_DPR").toDouble(&expectedDprSet);
    if(expectedDprSet)check("requested-device-pixel-ratio",qAbs(window->devicePixelRatio()-expectedDpr)<0.01);
    eval("Theme.mode='Light';Theme.transparency=true;Theme.increaseContrast=false;Theme.reduceMotion=true;AppState.navigate('activity')");
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
    auto *footprint=scene?scene->findChild<QQuickItem *>("apecWingFootprint"):nullptr;
    auto *wingVisual=scene?scene->findChild<QQuickItem *>("apecWingVisual"):nullptr;
    check("flat-wing-vector-loaded",footprint && wingVisual && findVisual(scene,"apecFlatWingPaths"));
    for(const QSize size:{QSize(760,672),QSize(914,672),QSize(1100,760)}) {
        window->resize(size);QTest::qWait(50);
        check("single-wing-spans-window-diagonally-with-fixed-aspect",footprint
            && footprint->width()>scene->width()
            && qAbs(footprint->height()/footprint->width()-0.625)<0.001
            && footprint->y()<scene->height()/4
            && footprint->x()<0
            && qAbs(footprint->x()+footprint->width()-scene->width()+20)<0.1
            && qAbs(footprint->y()+footprint->height()-scene->height()-8)<0.1);
        const auto transmitted=grab(productionGlass);
        qint64 featherPixels=0;
        for(int y=transmitted.height()*3/4;y<transmitted.height()-8;++y)
            for(int x=8;x<transmitted.width()-8;++x) {
                const auto pixel=transmitted.pixelColor(x,y);
                if(pixel.alpha()>30 && pixel.hsvSaturation()>25)++featherPixels;
            }
        check("production-wing-remains-visible-through-lower-glass",featherPixels>transmitted.width()*transmitted.height()/200);
    }
    check("sidebar-retains-floating-inset-and-14dp-contour",eval("sidebar.glassSurface.x===Theme.shellInset && sidebar.glassSurface.y===Theme.shellInset && sidebar.glassSurface.radius===14").toBool());
    check("neutral-light-canvas-and-card-palette",eval("Theme.canvas.toString()==='#f7f7f8' && Theme.surface.toString()==='#ffffff' && Theme.border.toString()==='#e0e0e3'").toBool());
    if(decoration){
        auto decorated=grab(scene);
        decoration->setVisible(false);QTest::qWait(35);auto plain=grab(scene);
        qint64 rightSideChanges=0;
        if(!decorated.isNull() && decorated.size()==plain.size())
            for(int y=0;y<plain.height();++y)for(int x=plain.width()/2;x<plain.width();++x)
                if(decorated.pixelColor(x,y)!=plain.pixelColor(x,y))++rightSideChanges;
        check("wing-decoration-reaches-uncovered-right-workspace",rightSideChanges>100);
        const auto withoutWing=window->grabWindow();
        decoration->setVisible(true);QTest::qWait(35);
        const auto withWing=window->grabWindow();
        for(const auto *name:{"activityStatusCard","activityTrafficCard","activitySourcesCard"}) {
            auto *card=window->findChild<QQuickItem *>(name);
            check("production-opaque-card-found",card!=nullptr);
            if(card){
                const auto dpr=window->devicePixelRatio();
                const auto origin=card->mapToScene(QPointF(16,16))*dpr;
                const QRect interior(qRound(origin.x()),qRound(origin.y()),qRound((card->width()-32)*dpr),qRound((card->height()-32)*dpr));
                check("production-card-pixels-independent-of-wing",!withoutWing.isNull() && !withWing.isNull()
                    && withoutWing.copy(interior)==withWing.copy(interior));
            }
        }
        decoration->setVisible(false);QTest::qWait(35);
        QQmlComponent cardComponent(qmlEngine(window));
        cardComponent.setData("import QtQuick; import SwirlQuick; SwirlGlassPanel {width:240;height:160}",QUrl("qrc:/qt/qml/SwirlQuick/WingCardFixture.qml"));
        std::unique_ptr<QObject> cardOwner(cardComponent.create(qmlContext(window)));
        auto *card=qobject_cast<QQuickItem *>(cardOwner.get());
        if(card){
            card->setParentItem(scene);
            card->setPosition(QPointF(footprint->x()+footprint->width()/2-120,scene->height()-170));
            const auto before=grab(card);
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
            check("source-colours-transmitted-without-pigment-wash",right.red()>left.red()+100 && left.blue()>left.red()+60 && left.hsvSaturation()>170);
            const auto stripe=sample(initial,2,140),besideStripe=sample(initial,20,140);
            check("fine-source-stripe-remains-recognizable",stripe.lightness()>besideStripe.lightness()+40);
            check("blur-mixes-source-boundary",edge.red()>left.red()+8 && edge.red()<right.red()-8);
            eval("apecGlass.source.color='#BD334F'");QTest::qWait(100);auto changed=capture();changed.save(directory+"/glass-source-red.png");
            check("live-source-change-reaches-material",!changed.isNull() && sample(changed,100,140).red()>left.red()+35);
            eval("apecGlass.glass.refraction=0");QTest::qWait(60);auto unrefracted=capture();
            check("edge-refraction-changes-sampled-pixels",!changed.isNull() && !unrefracted.isNull() && difference(changed,unrefracted)>100);
            eval("apecGlass.glass.interaction=1;apecGlass.glass.lightPoint=Qt.point(0,0)");QTest::qWait(60);auto lit=capture();
            check("interaction-drives-directional-rim",!lit.isNull() && difference(lit,unrefracted)>100);
            eval("apecGlass.glass.lightPoint=Qt.point(1,0.5)");QTest::qWait(60);auto rightLit=capture();
            if(!rightLit.isNull() && rightLit.size()==unrefracted.size()){
                const QRect rightRim(rightLit.width()-12,rightLit.height()/3,12,rightLit.height()/3);
                const QRect leftRim(0,rightLit.height()/3,12,rightLit.height()/3);
                const auto rightChange=difference(rightLit.copy(rightRim),unrefracted.copy(rightRim));
                const auto leftChange=difference(rightLit.copy(leftRim),unrefracted.copy(leftRim));
                check("right-edge-glint-stays-local",rightChange>100 && leftChange<rightChange/10);
            }else check("right-edge-glint-readback",false);
            eval("apecGlass.source.color='#40BD334F'");QTest::qWait(60);auto translucent=capture();
            check("glass-preserves-transmitted-alpha",!translucent.isNull() && qAbs(sample(translucent,100,140).alpha()-64)<=2);
            eval("apecGlass.source.color='#BD334F'");
        }
        const auto size=eval("apecGlass.glass.captureSize").toSizeF();
        const auto scale=qMin(2.0,window->devicePixelRatio());
        check("capture-bounded-to-panel-at-native-dpr",size.width()<=qCeil(440*scale) && size.height()<=qCeil(320*scale) && size.width()>0 && size.height()>0);
        eval("apecGlass.glass.visible=false");QTest::qWait(30);check("hidden-capture-stopped",!eval("apecGlass.glass.captureLive").toBool());
        eval("apecGlass.glass.visible=true;Theme.transparency=false");QTest::qWait(60);
        check("opaque-fallback-releases-sample",eval("!apecGlass.glass.sampled && !apecGlass.glass.captureLive").toBool());
        const auto opaque=capture();
        const auto canvasColor=eval("Theme.canvas").value<QColor>();
        check("opaque-fallback-pixels",!opaque.isNull() && sample(opaque,100,140)==canvasColor && sample(opaque,300,140)==canvasColor && canvasColor.alpha()==255);
        eval("Theme.transparency=true;Theme.increaseContrast=true");QTest::qWait(60);
        check("high-contrast-fallback",eval("!apecGlass.glass.sampled && !apecGlass.glass.captureLive").toBool());
        eval("Theme.increaseContrast=false;Theme.mode='Dark'");QTest::qWait(100);auto dark=capture();
        check("dark-material-readback",!dark.isNull());if(!dark.isNull())dark.save(directory+"/glass-dark.png");
        qmlEngine(window)->rootContext()->setContextProperty("apecGlass",static_cast<QObject *>(nullptr));
    }
    eval("Theme.mode='Light';Theme.transparency=true;Theme.reduceMotion=false;Theme.followSystemMotion=false");
    QQmlComponent entryComponent(qmlEngine(window));
    entryComponent.setData("import QtQuick; import SwirlQuick; SwirlWorkspaceBackdrop {width:914;height:672;visible:false;glassSampled:true}",QUrl("qrc:/qt/qml/SwirlQuick/NativeWingEntryFixture.qml"));
    std::unique_ptr<QObject> entryOwner(entryComponent.createWithInitialProperties({{"targetWindow",QVariant::fromValue(window)}},qmlContext(window)));
    auto *entry=qobject_cast<QQuickItem *>(entryOwner.get());
    check("native-opening-fixture-loaded",entry!=nullptr);
    if(entry){
        entry->setParentItem(window->contentItem());entry->setZ(120);
        entry->setProperty("glassSurface",QVariant::fromValue(window->findChild<QQuickItem *>("sidebarFloatingBackground")));
        QTest::qWait(180);
        check("hidden-opening-waits-for-visible-frame",!entry->property("entranceConsumed").toBool() && entry->property("progress").toDouble()==0);
        entry->setVisible(true);window->update();
        check("visible-frame-starts-opening",QTest::qWaitFor([&]{return entry->property("entering").toBool();},1500));
        QTest::qWait(120);
        const auto early=grab(entry);QTest::qWait(800);const auto middle=grab(entry);
        check("native-opening-frames-progress",!early.isNull() && !middle.isNull() && early!=middle && entry->property("entering").toBool());
        check("native-opening-completes",QTest::qWaitFor([&]{return !entry->property("entering").toBool();},3000));
        const auto settled=grab(entry);QTest::qWait(80);const auto resting=grab(entry);
        check("native-wing-is-pixel-static-at-rest",!settled.isNull() && settled==resting);
        early.save(directory+"/wing-entry-early.png");middle.save(directory+"/wing-entry-middle.png");settled.save(directory+"/wing-entry-settled.png");
        entry->setVisible(false);QTest::qWait(35);
        entry->setVisible(true);QTest::qWait(35);
        check("native-return-does-not-replay-opening",!entry->property("entering").toBool() && grab(entry)==settled);
    }
    owner.reset();entryOwner.reset();
    QQmlComponent featherComponent(qmlEngine(window));
    featherComponent.setData("import QtQuick; import SwirlQuick; SwirlWingAnimation {width:320;height:160}",QUrl("qrc:/qt/qml/SwirlQuick/FeatherSequenceFixture.qml"));
    std::unique_ptr<QObject> featherOwner(featherComponent.create(qmlContext(window)));
    auto *feathers=qobject_cast<QQuickItem *>(featherOwner.get());
    check("independent-feather-fixture-loads",feathers!=nullptr);
    if(feathers){
        feathers->setParentItem(window->contentItem());feathers->setZ(120);
        const auto reveal=[&](int index){auto *feather=findVisual(feathers,QStringLiteral("wingFeather%1").arg(index));return feather?feather->property("reveal").toDouble():-1.;};
        feathers->setProperty("progress",0.12);QTest::qWait(40);const auto first=grab(feathers);
        check("first-feather-grows-before-other-feathers",reveal(0)>0 && reveal(0)<1 && reveal(1)==0 && reveal(2)==0 && reveal(3)==0);
        feathers->setProperty("progress",0.38);QTest::qWait(40);const auto second=grab(feathers);
        check("second-feather-grows-before-third",reveal(0)>reveal(1) && reveal(1)>0 && reveal(2)==0 && reveal(3)==0);
        check("independent-feather-frames-render-differently",!first.isNull() && !second.isNull() && first!=second);
        feathers->setProperty("progress",1.0);QTest::qWait(40);const auto full=grab(feathers);
        check("all-feathers-complete",reveal(0)==1 && reveal(1)==1 && reveal(2)==1 && reveal(3)==1);
        feathers->setProperty("progress",0.55);QTest::qWait(40);
        check("closing-retires-last-feather-first",reveal(0)==1 && reveal(1)>reveal(2) && reveal(2)>0 && reveal(3)==0);
        feathers->setProperty("progress",0.12);QTest::qWait(40);
        check("closing-leaves-only-first-feather",reveal(0)>0 && reveal(1)==0 && reveal(2)==0 && reveal(3)==0);
        feathers->setProperty("progress",0.0);QTest::qWait(40);
        check("closed-wing-fully-hidden",!feathers->isVisible() && reveal(0)==0 && reveal(1)==0 && reveal(2)==0 && reveal(3)==0);
        first.save(directory+"/small-wing-first.png");second.save(directory+"/small-wing-second.png");full.save(directory+"/small-wing-full.png");
    }
    featherOwner.reset();
    eval("Theme.reduceMotion=true;Theme.followSystemMotion=false");
    for(const QString theme:{QStringLiteral("Light"),QStringLiteral("Dark")}){
        eval(QStringLiteral("Theme.mode='%1'").arg(theme));
        const auto canvasColor=eval("Theme.canvas").value<QColor>();
        check("canvas-has-no-blue-cast",qMax(canvasColor.red(),qMax(canvasColor.green(),canvasColor.blue()))-qMin(canvasColor.red(),qMin(canvasColor.green(),canvasColor.blue()))<=2);
        if(theme=="Dark")check("dark-canvas-is-near-black",canvasColor.lightness()<24);
        for(const QString route:{QStringLiteral("activity"),QStringLiteral("overview"),QStringLiteral("featurehub"),QStringLiteral("policies")}){
            eval(QStringLiteral("AppState.navigate('%1')").arg(route));
            check("page-settles-before-visual-capture",QTest::qWaitFor([&]{return eval(QStringLiteral("AppState.currentPage==='%1' && pageLoader.item!==null && !pageLoader.moving && !pageLoader.pendingGrab && !SwirlMotion.busy").arg(route)).toBool();},4000));
            QTest::qWait(80);
            check("global-wing-stays-complete-across-pages-and-themes",eval("appSceneBackdrop.progress===1 && !appSceneBackdrop.entering && appSceneBackdrop.decorationSource.visible").toBool());
            const auto image=window->grabWindow();
            check("settled-native-page-capture-saved",!image.isNull() && image.save(directory+QStringLiteral("/final-%1-%2.png").arg(theme.toLower(),route)));
            if(route=="activity"){
                for(const char *name:{"activityProxyWing","diagnosticProxyWing"}){
                    auto *smallWing=window->findChild<QQuickItem *>(name);
                    check("stopped-production-proxy-wing-is-empty",smallWing && smallWing->property("progress").toDouble()==0);
                }
            }
            if(route=="featurehub"){
                auto *general=window->findChild<QQuickItem *>("settings-settings");
                auto *dns=window->findChild<QQuickItem *>("settings-dns");
                const auto surface=[](QQuickItem *entry){return entry?qobject_cast<QQuickItem *>(entry->property("background").value<QObject *>()):nullptr;};
                auto *generalSurface=surface(general),*dnsSurface=surface(dns);
                if(general && generalSurface){
                    const auto top=general->mapToScene(QPointF(general->width()/2,0)).toPoint();
                    const QPoint outside(top.x(),qMax(1,top.y()-12));
                    QTest::mouseMove(window,outside);
                    check("settings-card-hover-starts-from-rest",QTest::qWaitFor([&]{return !general->property("hovered").toBool() && generalSurface->property("color")==eval("Theme.independentCard");},1000));
                    check("settings-general-and-dns-share-card-material",dnsSurface && generalSurface->property("color")==dnsSurface->property("color"));
                    const auto resting=generalSurface->property("color");
                    const auto center=general->mapToScene(QPointF(general->width()/2,general->height()/2)).toPoint();
                    QTest::mouseMove(window,center);
                    check("settings-card-hover-has-visible-feedback",QTest::qWaitFor([&]{return general->property("hovered").toBool() && generalSurface->property("color")!=resting && generalSurface->property("color")==eval("Theme.cardHover");},1000));
                    QTest::mousePress(window,Qt::LeftButton,Qt::NoModifier,center);QTest::qWait(30);
                    check("settings-card-press-uses-shared-feedback",generalSurface->property("color")==eval("Theme.cardPressed"));
                    QTest::mouseMove(window,outside);
                    QTest::mouseRelease(window,Qt::LeftButton,Qt::NoModifier,outside);QTest::qWait(30);
                }else check("settings-general-and-dns-share-card-material",false);
            }
        }
    }
    QFile file(output);if(!file.open(QIODevice::WriteOnly))return 2;
    file.write(QJsonDocument(QJsonObject{{"checks",checks},{"failures",failures},{"qtVersion",qVersion()},{"devicePixelRatio",window->devicePixelRatio()},{"graphicsApi",int(window->rendererInterface()->graphicsApi())},{"scope","Native app-source pixel readback and controlled DPR; not desktop sampling, physical refresh, mixed-monitor DPI or private-network acceptance"}}).toJson());
    return failures?1:0;
}
