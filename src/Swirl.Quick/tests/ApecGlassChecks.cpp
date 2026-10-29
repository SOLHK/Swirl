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
#include <QElapsedTimer>
#include <QTimer>
#include <memory>
#include <functional>
#include <cmath>

int runApecGlassChecks(QQuickWindow *window,const QString &output) {
    QJsonArray checks;QJsonObject openingFailureDiagnostics;int failures=0;
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
    // The pane only paints its rim. Comparing the composited parent scene is
    // essential: a standalone clear pane must not contain copied wing pixels.
    const auto distanceToContour=[](const QPointF &point,const QSizeF &size,qreal radius){
        const auto r=qMin(radius,qMin(size.width(),size.height())/2);
        const auto x=qAbs(point.x()-size.width()/2)-size.width()/2+r;
        const auto y=qAbs(point.y()-size.height()/2)-size.height()/2+r;
        return std::pow(std::pow(qMax(x,0.0),2.5)+std::pow(qMax(y,0.0),2.5),0.4)
            +qMin(qMax(x,y),0.0)-r;
    };
    const auto clearInterior=[&](const QImage &withGlass,const QImage &withoutGlass,QQuickItem *glass,QQuickItem *parent){
        if(withGlass.isNull() || withGlass.size()!=withoutGlass.size() || !glass || !parent)return false;
        const auto dpr=qreal(withGlass.width())/parent->width();
        const auto origin=glass->mapToItem(parent,QPointF());
        qint64 samples=0;
        for(int y=0;y<withGlass.height();++y)for(int x=0;x<withGlass.width();++x){
            const QPointF local((x+0.5)/dpr-origin.x(),(y+0.5)/dpr-origin.y());
            if(distanceToContour(local,glass->size(),glass->property("cornerRadius").toDouble())>=-3/dpr)continue;
            ++samples;
            if(withGlass.pixel(x,y)!=withoutGlass.pixel(x,y)){
                qWarning()<<"APEC_CLEAR_INTERIOR_PIXEL_CHANGED"<<x<<y<<withGlass.pixelColor(x,y)<<withoutGlass.pixelColor(x,y);
                return false;
            }
        }
        return samples>1000;
    };
    const auto transparentInterior=[&](const QImage &image,QQuickItem *glass){
        if(image.isNull() || !glass)return false;
        const auto dpr=qreal(image.width())/glass->width();qint64 samples=0;
        for(int y=0;y<image.height();++y)for(int x=0;x<image.width();++x){
            if(distanceToContour(QPointF((x+0.5)/dpr,(y+0.5)/dpr),glass->size(),glass->property("cornerRadius").toDouble())>=-3/dpr)continue;
            ++samples;if(image.pixelColor(x,y).alpha()!=0)return false;
        }
        return samples>1000;
    };
    const auto noCapturedSource=[](QQuickItem *glass){
        if(!glass || glass->property("sampled").toBool() || glass->property("captureLive").toBool())return false;
        for(auto *child:glass->findChildren<QObject *>()){
            const QByteArray type=child->metaObject()->className();
            if(type.contains("ShaderEffectSource") || type.contains("Blur") || type.contains("MultiEffect"))return false;
        }
        return true;
    };
    auto *productionGlass=window->findChild<QQuickItem *>("sidebarLiquidGlass");
    auto *productionSurface=window->findChild<QQuickItem *>("sidebarFloatingBackground");
    const auto clearGlass=grab(productionGlass);
    check("sidebar-material-interior-is-exactly-transparent",transparentInterior(clearGlass,productionGlass));
    check("sidebar-has-no-blur-or-scene-capture",noCapturedSource(productionGlass));
    auto *productionShadow=window->findChild<QQuickItem *>("sidebarExteriorShadow");
    const auto shadow=grab(productionShadow);qint64 shadowPixels=0,interiorShadowPixels=0;
    if(!shadow.isNull() && productionShadow && productionGlass){
        const auto dpr=qreal(shadow.width())/productionShadow->width();
        const auto padding=productionShadow->property("padding").toDouble();
        for(int y=0;y<shadow.height();++y)for(int x=0;x<shadow.width();++x){
            const auto alpha=shadow.pixelColor(x,y).alpha();
            const auto distance=distanceToContour(QPointF((x+0.5)/dpr-padding,(y+0.5)/dpr-padding),productionGlass->size(),productionGlass->property("cornerRadius").toDouble());
            if(distance<-3/dpr && alpha!=0)++interiorShadowPixels;
            if(distance>3/dpr && alpha!=0)++shadowPixels;
        }
    }
    check("floating-shadow-is-present-exclusively-outside-pane",shadowPixels>100 && interiorShadowPixels==0);
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
        const auto withGlass=window->grabWindow();
        if(productionSurface)productionSurface->setVisible(false);
        QTest::qWait(35);const auto withoutGlass=window->grabWindow();
        if(productionSurface)productionSurface->setVisible(true);
        QTest::qWait(35);
        check("production-wing-and-foreground-are-pixel-identical-through-pane",clearInterior(withGlass,withoutGlass,productionGlass,window->contentItem()));
    }
    check("sidebar-retains-floating-inset-size-and-24dp-contour",eval("sidebar.glassSurface.x===Theme.shellInset && sidebar.glassSurface.y===Theme.shellInset && sidebar.glassSurface.width===sidebar.width-2*Theme.shellInset && sidebar.glassSurface.height===sidebar.height-2*Theme.shellInset && sidebar.glassSurface.radius===Theme.sidebarRadius && Theme.sidebarRadius===Theme.dp(24)").toBool());
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
  Rectangle {x:104;y:0;width:1;height:320;color:"#78A9FA"}
  Rectangle {x:410;y:0;width:8;height:320;color:"#182A40"}
 }
 SwirlLiquidGlass {id:glass;x:20;y:20;width:400;height:280;backdropSource:scene;cornerRadius:Theme.sidebarRadius}
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
        auto *shader=glass?glass->findChild<QObject *>("sidebarLiquidShader"):nullptr;
        check("cached-fixture-shader-has-no-error",shader && shader->property("status").toInt()!=2 && shader->property("log").toString().isEmpty());
        check("fixture-never-captures-or-blurs-source",noCapturedSource(glass));
        check("fixture-and-parent-do-not-fade-foreground",glass && glass->opacity()==1 && fixture->opacity()==1);
        const auto composedWithoutGlass=[&]{
            if(glass)glass->setVisible(false);
            QTest::qWait(35);auto image=grab(fixture);
            if(glass)glass->setVisible(true);
            QTest::qWait(35);return image;
        };
        const auto rimOnlyChanges=[&](const QImage &a,const QImage &b){
            if(a.isNull() || a.size()!=b.size() || !glass)return false;
            const auto dpr=qreal(a.width())/glass->width();qint64 changed=0;
            for(int y=0;y<a.height();++y)for(int x=0;x<a.width();++x){
                if(a.pixel(x,y)==b.pixel(x,y))continue;
                ++changed;
                const auto distance=distanceToContour(QPointF((x+0.5)/dpr,(y+0.5)/dpr),glass->size(),glass->property("cornerRadius").toDouble());
                if(distance<-3/dpr || distance>1/dpr)return false;
            }
            return changed>10;
        };
        const auto difference=[](const QImage &a,const QImage &b){
            if(a.isNull() || a.size()!=b.size())return qint64(-1);
            qint64 value=0;
            for(int y=0;y<a.height();++y)for(int x=0;x<a.width();++x){
                const auto p=a.pixelColor(x,y),q=b.pixelColor(x,y);
                value+=qAbs(p.red()-q.red())+qAbs(p.green()-q.green())+qAbs(p.blue()-q.blue())+qAbs(p.alpha()-q.alpha());
            }
            return value;
        };
        QImage lightRim;
        for(const QString theme:{QStringLiteral("Light"),QStringLiteral("Dark")}){
            eval(QStringLiteral("Theme.mode='%1';apecGlass.glass.interaction=0;apecGlass.source.color='#164C85'").arg(theme));
            QTest::qWait(60);const auto initial=grab(glass);
            const auto combined=grab(fixture),plain=composedWithoutGlass();
            check("native-clear-material-readback",!initial.isNull());
            check("standalone-pane-has-no-interior-pigment-or-copied-scene",transparentInterior(initial,glass));
            check("composed-colours-hard-boundary-and-fine-stripes-stay-exact",clearInterior(combined,plain,glass,fixture));
            check("rounded-clip-transparent-corner",!initial.isNull() && initial.pixelColor(0,0).alpha()==0);
            initial.save(directory+QStringLiteral("/glass-%1-rim.png").arg(theme.toLower()));
            combined.save(directory+QStringLiteral("/glass-%1-composed.png").arg(theme.toLower()));

            eval("apecGlass.source.color='#BD334F'");QTest::qWait(35);
            const auto changed=grab(fixture),changedPlain=composedWithoutGlass();
            check("live-parent-change-remains-unfiltered-through-pane",clearInterior(changed,changedPlain,glass,fixture) && difference(combined,changed)>1000);
            check("material-never-copies-changing-parent-pixels",initial==grab(glass));
            eval("apecGlass.source.color='#40BD334F'");QTest::qWait(35);
            const auto translucent=grab(fixture),translucentPlain=composedWithoutGlass();
            const auto sourcePixel=translucentPlain.isNull()?QColor():translucentPlain.pixelColor(qRound(translucentPlain.width()*100.0/440),qRound(translucentPlain.height()/2.0));
            check("composed-parent-alpha-preserved-exactly",sourcePixel.alpha()==64 && clearInterior(translucent,translucentPlain,glass,fixture));

            eval("apecGlass.glass.interaction=1;apecGlass.glass.lightPoint=Qt.point(1,0.5)");QTest::qWait(35);
            const auto lit=grab(glass);
            check("interaction-changes-only-the-rim",rimOnlyChanges(initial,lit));
            if(!lit.isNull() && lit.size()==initial.size()){
                const QRect rightRim(lit.width()-12,lit.height()/3,12,lit.height()/3);
                const QRect leftRim(0,lit.height()/3,12,lit.height()/3);
                const auto rightChange=difference(lit.copy(rightRim),initial.copy(rightRim));
                const auto leftChange=difference(lit.copy(leftRim),initial.copy(leftRim));
                check("right-edge-glint-stays-local",rightChange>100 && leftChange==0);
            }else check("right-edge-glint-readback",false);
            check("interaction-keeps-interior-exactly-transparent",transparentInterior(lit,glass));
            if(theme=="Light")lightRim=initial;
            else if(!initial.isNull() && initial.size()==lightRim.size()){
                qint64 lightAlpha=0,darkAlpha=0;int lightPeak=0,darkPeak=0;
                for(int y=0;y<initial.height();++y)for(int x=0;x<initial.width();++x){
                    const auto light=lightRim.pixelColor(x,y).alpha(),dark=initial.pixelColor(x,y).alpha();
                    lightAlpha+=light;darkAlpha+=dark;lightPeak=qMax(lightPeak,light);darkPeak=qMax(darkPeak,dark);
                }
                check("dark-rim-avoids-continuous-bright-bevel",darkAlpha>0 && darkAlpha<lightAlpha*0.4 && darkPeak<lightPeak*0.5);
            }else check("dark-and-light-rim-readback",false);
        }
        eval("apecGlass.glass.visible=false");QTest::qWait(30);
        check("hidden-pane-does-not-capture",noCapturedSource(glass));
        eval("apecGlass.glass.visible=true;Theme.transparency=false");QTest::qWait(35);
        check("transparency-preference-does-not-add-sidebar-fill",noCapturedSource(glass) && transparentInterior(grab(glass),glass));
        eval("Theme.transparency=true;Theme.increaseContrast=true");QTest::qWait(35);
        check("high-contrast-outline-keeps-clear-interior",noCapturedSource(glass) && transparentInterior(grab(glass),glass));
        const auto contrastComposed=grab(fixture),contrastPlain=composedWithoutGlass();
        check("high-contrast-outline-does-not-wash-parent-scene",clearInterior(contrastComposed,contrastPlain,glass,fixture));
        eval("Theme.increaseContrast=false");
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
        QElapsedTimer openingClock;openingClock.start();QJsonArray openingSamples;int presentedFrames=0;
        QObject openingContext;
        const auto frameConnection=QObject::connect(window,&QQuickWindow::frameSwapped,&openingContext,[&]{++presentedFrames;});
        QObject *entranceClock=nullptr;
        for(auto *candidate:entry->findChildren<QObject *>())if(candidate->property("duration").isValid()&&candidate->property("property").toString()=="progress"){entranceClock=candidate;break;}
        const auto sampleOpening=[&](const QString &phase){openingSamples.append(QJsonObject{
            {"phase",phase},{"elapsedMs",openingClock.elapsed()},{"presentedFrames",presentedFrames},
            {"progress",entry->property("progress").toDouble()},{"entering",entry->property("entering").toBool()},
            {"presenting",entry->property("presenting").toBool()},{"entranceConsumed",entry->property("entranceConsumed").toBool()},
            {"firstFramePresented",entry->property("firstFramePresented").toBool()},
            {"animationClockFound",entranceClock!=nullptr},{"animationPaused",entranceClock&&entranceClock->property("paused").toBool()},
            {"animationDurationMs",entranceClock?entranceClock->property("duration").toInt():-1},
            {"windowVisible",window->isVisible()},{"windowVisibility",int(window->visibility())},
            {"windowExposed",window->isExposed()},{"windowActive",window->isActive()}});};
        QTimer openingObserver;openingObserver.setInterval(40);
        QObject::connect(&openingObserver,&QTimer::timeout,window,[&]{sampleOpening("observed");});openingObserver.start();sampleOpening("before-show");
        entry->setVisible(true);window->update();
        check("visible-frame-starts-opening",QTest::qWaitFor([&]{return entry->property("entering").toBool();},1500));
        QTest::qWait(120);
        const auto early=grab(entry);sampleOpening("early-capture");QTest::qWait(800);const auto middle=grab(entry);sampleOpening("middle-capture");
        check("native-opening-frames-progress",!early.isNull() && !middle.isNull() && early!=middle && entry->property("entering").toBool());
        const bool openingCompletes=QTest::qWaitFor([&]{return !entry->property("entering").toBool();},3000);
        sampleOpening("completion-deadline");check("native-opening-completes",openingCompletes);
        const auto settled=grab(entry);QTest::qWait(80);const auto resting=grab(entry);
        const bool staticAtRest=!settled.isNull()&&settled==resting;
        check("native-wing-is-pixel-static-at-rest",staticAtRest);
        early.save(directory+"/wing-entry-early.png");middle.save(directory+"/wing-entry-middle.png");settled.save(directory+"/wing-entry-settled.png");
        entry->setVisible(false);QTest::qWait(35);
        entry->setVisible(true);QTest::qWait(35);
        const bool returnDoesNotReplay=!entry->property("entering").toBool()&&grab(entry)==settled;
        check("native-return-does-not-replay-opening",returnDoesNotReplay);
        openingObserver.stop();sampleOpening("return-capture");QObject::disconnect(frameConnection);
        if(!openingCompletes||!staticAtRest||!returnDoesNotReplay){
            const auto capturePath=directory+"/wing-entry-failure-window.png";
            const bool captureSaved=window->grabWindow().save(capturePath);
            openingFailureDiagnostics={{"nominalDurationMs",eval("SwirlMotion.ms(2100)").toInt()},{"motionSpeed",eval("SwirlMotion.speed").toDouble()},
                {"windowCaptureSaved",captureSaved},{"windowCapture",capturePath},{"samples",openingSamples}};
            qInfo()<<"APEC_WING_OPENING_FAILURE"<<QJsonDocument(openingFailureDiagnostics).toJson(QJsonDocument::Compact);
        }
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
            check("page-settles-before-visual-capture",QTest::qWaitFor([&]{return eval(QStringLiteral("AppState.currentPage==='%1' && pageLoader.item!==null && pageLoader.activeLoader && pageLoader.activeLoader.routeId==='%1' && !pageLoader.moving && !pageLoader.pendingGrab && !SwirlMotion.busy").arg(route)).toBool();},4000));
            QTest::qWait(80);
            check("global-wing-stays-complete-across-pages-and-themes",eval("appSceneBackdrop.progress===1 && !appSceneBackdrop.entering && appSceneBackdrop.decorationSource.visible").toBool());
            const auto image=window->grabWindow();
            check("settled-native-page-capture-saved",!image.isNull() && image.save(directory+QStringLiteral("/final-%1-%2.png").arg(theme.toLower(),route)));
            if(route=="activity"){
                for(const char *name:{"activityCloudKnotWeave","diagnosticProxyWing"}){
                    auto *smallWing=window->findChild<QQuickItem *>(name);
                    check("stopped-production-proxy-art-is-empty",smallWing && smallWing->property("progress").toDouble()==0);
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
    file.write(QJsonDocument(QJsonObject{{"checks",checks},{"failures",failures},{"openingFailureDiagnostics",openingFailureDiagnostics},{"qtVersion",qVersion()},{"devicePixelRatio",window->devicePixelRatio()},{"graphicsApi",int(window->rendererInterface()->graphicsApi())},{"scope","Native app-source pixel readback and controlled DPR; not desktop sampling, physical refresh, mixed-monitor DPI or private-network acceptance"}}).toJson());
    return failures?1:0;
}
