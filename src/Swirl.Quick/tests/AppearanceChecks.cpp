#include "AppearanceChecks.h"
#include <QQuickWindow>
#include <QQuickItem>
#include <QQuickItemGrabResult>
#include <QQmlContext>
#include <QQmlExpression>
#include <QQmlProperty>
#include <QTest>
#include <QSignalSpy>
#include <QSettings>
#include <QProcess>
#include <QCoreApplication>
#include <QGuiApplication>
#include <QImage>
#include <QColor>
#include <QQmlComponent>
#include <QQmlEngine>
#include <QFontMetricsF>
#include <QFontDatabase>
#include <QCursor>
#include <QElapsedTimer>
#include <QtMath>
#include <functional>

int runAppearanceChecks(QQuickWindow *window,bool restoreOnly) {
    if(!window)return 2;
    int failures=0;
    auto check=[&](bool ok,const char *name){qInfo()<<(ok?"PASS":"FAIL")<<name;if(!ok)++failures;};
    auto eval=[&](const QString &code){QQmlExpression e(qmlContext(window),window,code);auto value=e.evaluate();check(!e.hasError(),"appearance expression is valid");return value;};
    if(restoreOnly){check(eval("Theme.mode==='Dark' && Theme.dark && Theme.followSystemMotion").toBool(),"new process restores saved dark theme and explicit system-motion preference");return failures?2:0;}
    if(qEnvironmentVariableIsSet("SWIRL_EXPECTED_DPR"))
        check(qAbs(window->devicePixelRatio()-qEnvironmentVariable("SWIRL_EXPECTED_DPR").toDouble())<0.02,"native window uses the requested controlled DPR");
    {
        QQmlComponent component(qmlEngine(window));
        component.setData(R"QML(
import QtQuick
import QtQuick.Layouts
import SwirlQuick
Item {
    width:600;height:480;x:230;y:100;z:1000
    SwirlButton {objectName:"reviewButton";x:10;y:10;text:"规则分流 HTTPS 176"}
    SwirlIconButton {objectName:"reviewIcon";x:220;y:10;iconName:"plus";tooltip:"添加"}
    SwirlComboBox {objectName:"reviewCombo";x:270;y:10;model:["默认策略 SG 176 ms","自动测速"]}
    SwirlSegmentedControl {objectName:"reviewSegments";x:10;y:65;width:280;options:["全部 12","仅代理 8"]}
    SwirlText {objectName:"reviewFigures";x:310;y:75;tabularFigures:true;text:"176 ms · HTTPS 完整请求"}
    SubscriptionAction {objectName:"reviewAction";x:10;y:115;text:"更新全部";iconName:"refresh";solid:true}
    SwirlNavigationItem {objectName:"reviewNavigation";x:210;y:115;width:180;pageId:"external";title:"面板";iconName:"gauge"}
    PolicyGroupTypes {objectName:"reviewGroupTypes";x:0;y:170;width:590}
})QML",QUrl("qrc:/qt/qml/SwirlQuick/ControlsReviewFixture.qml"));
        auto *fixture=qobject_cast<QQuickItem *>(component.create(qmlContext(window)));
        check(fixture!=nullptr,"shared control review fixture loads");
        if(!fixture)qWarning()<<component.errors();
        if(fixture){
            fixture->setParentItem(window->contentItem());
            struct RestoreCursor { QPoint position=QCursor::pos(); ~RestoreCursor(){QCursor::setPos(position);} } restoreCursor;
            window->requestActivate();QTest::qWait(100);
            const auto surface=[](QQuickItem *control){return control?control->property("background").value<QQuickItem *>():nullptr;};
            const auto movePointer=[&](QPoint local,int settle=160){
                QCursor::setPos(window->mapToGlobal(local));
                QCoreApplication::processEvents();
                QTest::mouseMove(window,window->mapFromGlobal(QCursor::pos()));
                QTest::qWait(settle);
            };
            std::function<QQuickItem *(QQuickItem *,const QString &)> visualItem;
            visualItem=[&](QQuickItem *parent,const QString &name)->QQuickItem *{
                if(parent->objectName()==name)return parent;
                for(auto *child:parent->childItems())if(auto *match=visualItem(child,name))return match;
                return nullptr;
            };
            for(const auto &theme:QStringList{"Light","Dark"}){
                eval("Theme.mode='"+theme+"';Theme.reduceMotion=false;Theme.followSystemMotion=false;Theme.increaseContrast=false");QTest::qWait(160);
                for(const auto &name:QStringList{"reviewButton","reviewIcon","reviewCombo","reviewAction","reviewNavigation"}){
                    auto *control=fixture->findChild<QQuickItem *>(name);auto *paint=surface(control);
                    check(paint&&qAbs(paint->property("radius").toReal()-(name=="reviewNavigation"?eval("Theme.sidebarRowRadius").toReal():paint->height()/2))<0.01,"shared surfaces retain the requested capsule or navigation curve");
                    if(!control||!paint)continue;
                    const auto size=control->size();const auto position=control->position();
                    movePointer(QPoint(window->width()-20,90));
                    check(QTest::qWaitFor([&]{return !control->property("hovered").toBool();},1000),"native pointer leaves the shared control before its resting sample");
                    const auto normal=paint->property("color").value<QColor>();
                    const auto restingPixels=window->grabWindow();
                    bool intermediateHoverFrame=false;
                    qreal sampledHoverProgress=0;
                    qint64 sampledHoverMs=-1;
                    int hoveredFrames=0;
                    QElapsedTimer hoverClock;hoverClock.start();
                    // Observe rendered-frame preparation from before input: a fixed sleep can
                    // resume after a short animation has already finished on a busy runner.
                    const auto hoverSample=QObject::connect(window,&QQuickWindow::afterAnimating,fixture,[&]{
                        if(!control->property("hovered").toBool())return;
                        ++hoveredFrames;
                        const auto progress=paint->property("hoverProgress").toReal();
                        if(!intermediateHoverFrame&&paint->property("moving").toBool()&&progress>0&&progress<1){
                            intermediateHoverFrame=true;sampledHoverProgress=progress;sampledHoverMs=hoverClock.elapsed();
                        }
                    });
                    movePointer(control->mapToScene(QPointF(control->width()/2,control->height()/2)).toPoint(),0);
                    const bool sampledIntermediate=QTest::qWaitFor([&]{return intermediateHoverFrame;},1000);
                    QObject::disconnect(hoverSample);
                    qInfo()<<"CONTROL_HOVER_FRAME"<<theme<<name<<"progress"<<sampledHoverProgress<<"inputElapsedMs"<<sampledHoverMs<<"hoveredFrames"<<hoveredFrames;
                    check(sampledIntermediate,"real pointer starts an intermediate hover frame instead of jumping to its endpoint");
                    QTest::qWait(160);
                    qInfo()<<"CONTROL_HOVER"<<theme<<name<<control->property("hovered")<<normal<<paint->property("color")
                           <<"cursor"<<window->mapFromGlobal(QCursor::pos())<<"target"<<control->mapToScene(QPointF(control->width()/2,control->height()/2))<<"active"<<window->isActive();
                    check(QTest::qWaitFor([&]{return control->property("hovered").toBool()&&paint->property("color").value<QColor>()!=normal;},1000),"shared control hover visibly changes its surface");
                    check(!paint->findChild<QQuickItem *>("controlInteractionRim")&&QQmlProperty(paint,"border.width").read().toReal()==0,"hover feedback keeps ordinary controls free of outline strokes");
                    const auto hoveredPixels=window->grabWindow();
                    const qreal dpr=window->devicePixelRatio();
                    const auto rect=control->mapRectToScene(control->boundingRect());
                    const QRect pixelRect(qFloor(rect.x()*dpr),qFloor(rect.y()*dpr),qCeil(rect.width()*dpr),qCeil(rect.height()*dpr));
                    check(!restingPixels.isNull()&&!hoveredPixels.isNull()&&restingPixels.copy(pixelRect)!=hoveredPixels.copy(pixelRect),"hover feedback changes the actual rendered button pixels");
                    if(name!="reviewCombo")check(control->property("motionLift").toReal()<-.5,"hover gently lifts the button without relaying out its shell");
                    control->forceActiveFocus(Qt::TabFocusReason);QTest::qWait(160);
                    check(control->property("visualFocus").toBool()&&paint->property("focused").toBool(),"keyboard focus reaches the shared surface");
                    auto *focusFill=paint->findChild<QQuickItem *>("controlFocusFill");
                    check(focusFill&&focusFill->isVisible()&&focusFill->opacity()>.99&&QQmlProperty(focusFill,"border.width").read().toReal()==0&&QQmlProperty(paint,"border.width").read().toReal()==0,"keyboard focus fills the surface without adding a border");
                    const auto focusedPixels=window->grabWindow();
                    check(!focusedPixels.isNull()&&focusedPixels.copy(pixelRect)!=hoveredPixels.copy(pixelRect),"keyboard focus visibly tints the actual rendered button pixels");
                    if(name!="reviewCombo"){
                        const auto at=control->mapToScene(QPointF(control->width()/2,control->height()/2)).toPoint();
                        const auto hovered=paint->property("color").value<QColor>();
                        QTest::mousePress(window,Qt::LeftButton,Qt::NoModifier,at);QTest::qWait(40);
                        auto *content=control->property("contentItem").value<QQuickItem *>();
                        check(paint->scale()<.995&&content&&qAbs(content->scale()-paint->scale())<.001,"a short press contracts both the surface and its label within the first40ms");
                        QTest::qWait(100);
                        check(control->property("down").toBool()&&paint->property("color").value<QColor>()!=hovered,"shared button provides a distinct pressed surface");
                        check(QQmlProperty(paint,"border.width").read().toReal()==0,"press feedback does not introduce an outline stroke");
                        QTest::mouseRelease(window,Qt::LeftButton,Qt::NoModifier,at);
                        QTest::qWait(30);
                        check(paint->scale()<.999,"release continues from the pressed frame through a spring return");
                        check(QTest::qWaitFor([&]{return qAbs(paint->scale()-1)<.001;},1400),"released button springs back to its resting scale");
                    }
                    control->setEnabled(false);QTest::qWait(180);
                    const bool disabledSettled=!paint->property("controlEnabled").toBool()&&paint->opacity()<1&&paint->property("color").value<QColor>()==normal;
                    if(!disabledSettled)qInfo()<<"CONTROL_DISABLED"<<theme<<name<<"hovered"<<control->property("hovered")<<"down"<<control->property("down")<<"enabled"<<paint->property("controlEnabled")<<"opacity"<<paint->opacity()<<"normal"<<normal<<"actual"<<paint->property("color");
                    check(disabledSettled,"disabled surface retires hover and press feedback");
                    check(control->size()==size&&control->position()==position,"all button states retain shell geometry");
                    control->setEnabled(true);
                }
                for(const auto &strategy:QStringList{"manual","url_test","fallback","load_balance"}){
                    auto *control=visualItem(fixture,"createPolicyGroup-"+strategy);auto *paint=surface(control);
                    check(control&&paint,"strategy creation action uses its real card surface");
                    if(!control||!paint)continue;
                    const auto size=control->size();
                    movePointer(QPoint(window->width()-15,90));
                    check(QTest::qWaitFor([&]{return !control->property("hovered").toBool();},1000),"native pointer leaves the strategy card before its resting sample");
                    const auto normal=paint->property("color").value<QColor>();
                    const auto at=control->mapToScene(QPointF(control->width()/2,control->height()/2)).toPoint();
                    movePointer(at);
                    qInfo()<<"CARD_HOVER"<<theme<<strategy<<paint->property("hovered")<<normal<<paint->property("color")
                           <<"cursor"<<window->mapFromGlobal(QCursor::pos())<<"target"<<at<<"active"<<window->isActive();
                    check(QTest::qWaitFor([&]{return paint->property("hovered").toBool()&&paint->property("color").value<QColor>()!=normal;},1000),"strategy creation card brightens on hover");
                    control->forceActiveFocus(Qt::TabFocusReason);QTest::qWait(160);
                    check(paint->property("focused").toBool(),"strategy creation card has keyboard focus feedback");
                    QTest::mousePress(window,Qt::LeftButton,Qt::NoModifier,at);QTest::qWait(160);
                    check(control->property("down").toBool()&&paint->property("color").value<QColor>()!=normal&&paint->scale()<1,"strategy creation card has visible press and contact feedback");
                    QTest::mouseMove(window,QPoint(window->width()-15,90));QTest::mouseRelease(window,Qt::LeftButton,Qt::NoModifier,QPoint(window->width()-15,90));
                    control->setEnabled(false);QTest::qWait(180);
                    check(paint->opacity()<1&&!paint->property("hovered").toBool()&&control->size()==size,"disabled strategy card dims and retains its click geometry");
                    control->setEnabled(true);
                }
            }
            auto *figures=fixture->findChild<QQuickItem *>("reviewFigures");
            for(const auto &family:QStringList{eval("Theme.fontFamily").toString(),"Segoe UI","Microsoft YaHei UI"}){
                if(!QFontDatabase::families().contains(family))continue;
                QFont font=figures->property("font").value<QFont>();font.setFamily(family);figures->setProperty("font",font);QTest::qWait(40);
                font=figures->property("font").value<QFont>();const QFontMetricsF metrics(font);
                check((font.styleStrategy()&QFont::ContextFontMerging)&&(font.styleStrategy()&QFont::PreferTypoLineMetrics),"mixed-script text retains contextual fallback and typographic line metrics");
                check(qAbs(metrics.horizontalAdvance("111111")-metrics.horizontalAdvance("888888"))<0.05,"numeric glyph updates retain equal advances in bundled and Windows fonts");
                check(figures->baselineOffset()>0&&figures->baselineOffset()<=figures->height(),"mixed-script baseline remains inside measured text height");
            }
            delete fixture;
        }
    }
    eval("Theme.reduceMotion=false;AppState.navigate('settings')");
    check(QTest::qWaitFor([&]{return eval("pageLoader.item && !pageLoader.pendingGrab && !pageLoader.moving && pageLoader.activeLoader.routeId==='settings'").toBool();},3500),"general settings with appearance controls settles before input");
    std::function<QQuickItem *(QQuickItem *,const QString &)> find=[&](QQuickItem *item,const QString &name)->QQuickItem *{if(item->objectName()==name)return item;for(auto *child:item->childItems())if(auto *match=find(child,name))return match;return nullptr;};
    auto *picker=find(window->contentItem(),"themeModePicker");check(picker&&picker->isVisible()&&picker->isEnabled(),"theme picker is visible and enabled");
    if(picker){
        window->resize(800,672);QTest::qWait(150);
        auto select=[&](int index){
            window->requestActivate();
            const auto center=picker->mapToScene(QPointF(picker->width()/2,picker->height()/2));
            const bool inside=QRectF(QPointF(0,0),window->size()).contains(center);
            check(inside,"theme picker hit area stays inside the narrow viewport");
            if(!inside)return;
            QTest::mouseClick(window,Qt::LeftButton,Qt::NoModifier,center.toPoint());QTest::qWait(150);
            auto *popup=qvariant_cast<QObject *>(picker->property("popup"));
            check(popup && popup->property("visible").toBool(),"theme click opens the in-window popup");
            if(popup){
                auto *content=qvariant_cast<QQuickItem *>(popup->property("contentItem"));
                auto *choice=content?find(content,"swirlComboOption-"+QString::number(index)):nullptr;
                check(choice!=nullptr,"theme choice exists");
                if(choice)QTest::mouseClick(window,Qt::LeftButton,Qt::NoModifier,choice->mapToScene(QPointF(choice->width()/2,choice->height()/2)).toPoint());
                check(QTest::qWaitFor([&]{return !popup->property("visible").toBool();},1200),"theme selection releases the popup input grab");
            }
        };
        select(2);check(eval("Theme.mode==='Dark' && Theme.dark").toBool(),"pointer theme interaction applies dark palette");
        select(1);check(eval("Theme.mode==='Light' && !Theme.dark").toBool(),"pointer theme interaction applies light palette");
        select(0);check(eval("Theme.mode==='System' && Theme.dark===(Qt.styleHints.colorScheme===Qt.Dark)").toBool(),"system mode follows actual Qt color scheme");
        window->requestActivate();picker->forceActiveFocus();QTest::qWait(80);QTest::keyClick(window,Qt::Key_End);QTest::qWait(150);
        check(eval("Theme.mode==='Dark' && Theme.dark").toBool(),"keyboard theme selection updates palette");
        for(int round=0;round<3;++round){select(1);select(2);select(0);}
        auto *contrast=find(window->contentItem(),"increaseContrastToggle");
        if(contrast){
            const auto at=contrast->mapToScene(QPointF(contrast->width()/2,contrast->height()/2)).toPoint();
            const auto before=eval("Theme.increaseContrast").toBool();
            QTest::mouseClick(window,Qt::LeftButton,Qt::NoModifier,at);QTest::qWait(100);
            check(eval("Theme.increaseContrast").toBool()!=before,"switch remains clickable after repeated theme selections");
            QTest::mouseClick(window,Qt::LeftButton,Qt::NoModifier,at);
        } else check(false,"contrast switch exists");
        select(2);
    }
    check(eval("!scaledCanvas.layer.enabled").toBool(),"text canvas is not a resampled window texture");
    eval("Theme.followSystemMotion=true;Theme.appearanceSettings.sync()");QTest::qWait(250);
    QSettings settings;check(QTest::qWaitFor([&]{settings.sync();return settings.value("Appearance/savedMode").toString()=="Dark"&&settings.value("Appearance/savedFollowSystemMotion").toBool();},3000),"chosen theme and motion preference are persisted");
    QProcess child;child.start(QCoreApplication::applicationFilePath(),{"--appearance-restore-test","--preview-preserve-settings"});
    check(child.waitForFinished(15000)&&child.exitStatus()==QProcess::NormalExit&&child.exitCode()==0,"fresh application process confirms theme restoration");
    window->requestActivate();
    eval("Theme.transparency=true;Theme.increaseContrast=false;AppState.navigate('activity')");
    check(QTest::qWaitFor([&]{return eval("pageLoader.activeLoader.routeId==='activity' && !pageLoader.pendingGrab && !pageLoader.moving").toBool();},3500),"activity route settles");
    auto *pane=find(window->contentItem(),"sidebarFloatingBackground");
    check(pane!=nullptr,"sidebar pane exists");
    if(pane){
        // The sidebar samples decoration over the single shared window base.
        // Its opaque accessibility fallback uses that same canvas colour.
        check(pane->metaObject()->indexOfProperty("color")==-1,"sidebar container has no independent fill property");
        QTest::qWait(250);
        auto *glass=find(pane,"sidebarLiquidGlass");
        auto *workspace=qvariant_cast<QQuickItem *>(eval("appSceneBackdrop"));
        auto *source=qvariant_cast<QQuickItem *>(eval("appSceneBackdrop.decorationSource"));
        auto *shader=glass?glass->findChild<QObject *>("sidebarLiquidShader"):nullptr;
        check(glass && source && qvariant_cast<QQuickItem *>(glass->property("backdropSource"))==source,"sidebar glass samples the independent application backdrop");
        check(glass && glass->property("sampled").toBool() && glass->property("captureLive").toBool(),"transparent sidebar uses live sampled material");
        check(shader && shader->property("status").toInt()==0 && shader->property("log").toString().isEmpty(),"production sidebar material shader is compiled without errors");
        const auto capture=[&](QQuickItem *item){
            if(!item)return QImage{};
            auto result=item->grabToImage();if(!result)return QImage{};
            QSignalSpy ready(result.data(),&QQuickItemGrabResult::ready);window->update();
            if(result->image().isNull())ready.wait(2000);
            return result->image();
        };
        const auto interiorMatches=[](const QImage &image,const QColor &expected=QColor()){
            if(image.isNull())return false;
            // Item-local readback excludes navigation labels and avoids any
            // dependency on page layout or window/DPI sample coordinates.
            const QPointF samples[]={{0.25,0.25},{0.75,0.25},{0.5,0.5},{0.25,0.75},{0.75,0.75}};
            for(const auto &sample:samples){
                const auto actual=image.pixelColor(qRound(sample.x()*(image.width()-1)),qRound(sample.y()*(image.height()-1)));
                if(actual.alpha()!=255)return false;
                if(expected.isValid() && (qAbs(actual.red()-expected.red())>2 || qAbs(actual.green()-expected.green())>2 || qAbs(actual.blue()-expected.blue())>2))return false;
            }
            return true;
        };
        const auto matchesToken=[&](QQuickItem *item,const QString &token){
            const auto expected=eval(token).value<QColor>();
            return expected.isValid() && interiorMatches(capture(item),expected);
        };
        const auto darkMaterial=capture(glass);
        const auto transmitsBase=[](const QImage &image){return !image.isNull() && image.pixelColor(image.width()/2,image.height()/4).alpha()<3;};
        check(transmitsBase(darkMaterial),"dark sidebar leaves the shared window base visible");
        const auto before=window->grabWindow();
        QQmlComponent fixture(qmlEngine(window));
        fixture.setData("import QtQuick; Rectangle {width:600;height:900;color:'#D02A65'; Text {anchors.fill:parent;text:'RIGHT PAGE CONTENT';font.pixelSize:60;wrapMode:Text.Wrap}}",QUrl());
        auto *overlay=qobject_cast<QQuickItem *>(fixture.create());
        auto *mainArea=qvariant_cast<QQuickItem *>(eval("mainArea"));
        check(overlay && mainArea,"right-page regression fixture created");
        if(overlay && mainArea){
            overlay->setParentItem(mainArea);overlay->setZ(999);window->update();QTest::qWait(250);
            const auto after=window->grabWindow();
            const auto origin=pane->mapToScene(QPointF(pane->width()-18,120))*window->devicePixelRatio();
            const QRect strip(origin.toPoint(),QSize(4,qRound((pane->height()-240)*window->devicePixelRatio())));
            check(!before.isNull() && !after.isNull() && before.copy(strip)==after.copy(strip),"right-page text and color never get copied underneath sidebar navigation");
        }
        delete overlay;
        eval("Theme.mode='Light';Theme.reduceMotion=true");QTest::qWait(350);
        const auto lightMaterial=capture(glass);
        check(glass && glass->property("sampled").toBool() && glass->property("captureLive").toBool() && transmitsBase(lightMaterial),"light sidebar retains live decoration over the shared base");
        check(!darkMaterial.isNull() && !lightMaterial.isNull() && darkMaterial.size()==lightMaterial.size() && darkMaterial!=lightMaterial,"theme selection changes the rendered sidebar material");
        eval("Theme.increaseContrast=true");QTest::qWait(150);
        check(glass && !glass->property("sampled").toBool() && !glass->property("captureLive").toBool(),"increased contrast stops sidebar sampling");
        check(matchesToken(glass,"Theme.canvas"),"increased contrast renders the shared opaque canvas token");
        eval("Theme.increaseContrast=false;Theme.transparency=false");QTest::qWait(150);
        check(glass && !glass->property("sampled").toBool() && !glass->property("captureLive").toBool(),"opaque fallback stops sidebar sampling");
        check(matchesToken(glass,"Theme.canvas"),"opaque sidebar fallback uses the shared canvas token");
        QQuickItem *workspaceBase=nullptr;
        if(workspace)for(auto *child:workspace->childItems())if(child->property("tintOpacity").isValid()){workspaceBase=child;break;}
        check(matchesToken(workspaceBase,"Theme.canvas"),"opaque workspace base uses the same canvas token as the sidebar");
        check(source && source->isVisible() && interiorMatches(capture(workspace)),"opaque workspace retains the global wing above its fully opaque base");
        eval("Theme.transparency=true");QTest::qWait(150);
        check(glass && glass->property("sampled").toBool() && glass->property("captureLive").toBool(),"restoring transparency resumes sidebar sampling");
    }
    auto *proxy=find(window->contentItem(),"proxyCapsule");
    if(proxy){
        // Appearance checks observe the real host but never click its network
        // switch. Motion checks inject a controller into this same control;
        // native setting mutations are tested only on disposable CI runners.
        const bool active=eval("engineController.proxyRequested || engineController.systemProxy.owned || engineController.processAlive").toBool();
        const bool pending=eval("engineController.systemProxyBusy").toBool();
        const bool stopping=eval("engineController.systemProxyStopping").toBool();
        check(proxy->property("proxyEnabled").toBool()==active,"master proxy control reflects Swirl runtime and owned settings");
        const auto action=stopping?QStringLiteral("正在关闭代理…"):pending?QStringLiteral("正在开启代理…"):proxy->property("proxyOwned").toBool()?QStringLiteral("系统代理 · 已开"):active?QStringLiteral("代理 · 仅内核"):eval("engineController.systemProxy.systemEnabled").toBool()?QStringLiteral("系统代理 · 外部"):QStringLiteral("系统代理 · 已关");
        check(proxy->property("label").toString()==action,"master proxy control presents the matching direct action");
    } else check(false,"system proxy switch exists");
    qInfo()<<"APPEARANCE_CHECKS failures"<<failures;return failures?2:0;
}
