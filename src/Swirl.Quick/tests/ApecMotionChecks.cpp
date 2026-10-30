#include "app/MotionPolicy.h"
#include <QQuickWindow>
#include <QQuickItem>
#include <QGuiApplication>
#include <QQmlEngine>
#include <QQmlContext>
#include <QQmlComponent>
#include <QQmlExpression>
#include <QQmlListReference>
#include <QQmlProperty>
#include <QTest>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonArray>
#include <QFile>
#include <QFileInfo>
#include <QLineF>
#include <QDebug>
#include <QDir>
#include <QEventLoop>
#include <QTimer>
#include <QSGRendererInterface>
#include <QColor>
#include <QTransform>
#include <QtMath>
#include <memory>
#include <functional>

int runApecMotionChecks(QQuickWindow *window,const QString &output) {
    QJsonArray checks;int failures=0;
    const auto check=[&](const char *name,bool passed){checks.append(QJsonObject{{"name",name},{"passed",passed}});if(!passed)++failures;qInfo()<<"APEC_MOTION_CHECK"<<name<<passed;};
    const auto wait=[](int ms){QEventLoop loop;QTimer timer;timer.setTimerType(Qt::PreciseTimer);timer.setSingleShot(true);QObject::connect(&timer,&QTimer::timeout,&loop,&QEventLoop::quit);timer.start(ms);loop.exec();};
    const auto keyboardWindow=[&](){
        for(auto *candidate:QGuiApplication::allWindows())if(candidate->isVisible() && candidate->flags().testFlag(Qt::Popup))if(auto *quick=qobject_cast<QQuickWindow *>(candidate))return quick;
        return window;
    };
    const auto eval=[&](const QString &source){QQmlExpression e(qmlContext(window),window,source);auto result=e.evaluate();if(e.hasError()){qWarning()<<e.error();check("qml-expression",false);}return result;};
    std::function<QQuickItem *(QQuickItem *,const QString &)> findVisual;
    findVisual=[&](QQuickItem *root,const QString &name)->QQuickItem *{if(root->objectName()==name)return root;for(auto *child:root->childItems())if(auto *found=findVisual(child,name))return found;return nullptr;};
    auto *policy=qobject_cast<MotionPolicy *>(qmlContext(window)->contextProperty("motionPolicy").value<QObject *>());
    if(!policy)return 2;
    policy->setSystemReducedMotionOverrideForTest(0);
    struct Restore {MotionPolicy *policy;~Restore(){policy->setSystemReducedMotionOverrideForTest(-1);}} restore{policy};
    eval("Theme.reduceMotion=false;Theme.followSystemMotion=true;Theme.transparency=false;AppState.navigate('activity')");
    window->resize(1100,760);window->requestActivate();wait(450);
    QQmlComponent component(qmlEngine(window));
    component.setData(R"QML(
import QtQuick
import QtQuick.Controls
import SwirlQuick
Item {
 id:fixture;objectName:"apecMotionFixture";x:220;y:110;width:600;height:400;z:100
 property alias arc:arc
 property alias flow:flow
 property alias feedback:feedback
 property alias menu:menu
 property alias dialog:dialog
 property alias combo:combo
 property alias checkBox:checkBox
 property alias guarded:guarded
 property alias miniHost:miniHost
 SwirlArcMotion {id:arc;targetX:0;targetY:0;duration:300;bend:12}
 SwirlFlow {id:flow;x:280;y:40;width:80;height:35}
 SwirlInteractionMotion {id:feedback}
 ReferenceCheckBox {id:checkBox;objectName:"apecCheckBox";x:280;y:110;width:180;text:"Check fixture"}
 SwirlButton {id:openButton;objectName:"apecOpenDialog";text:"Motion fixture";onClicked:dialog.open()}
 SwirlComboBox {id:combo;y:70;width:190;model:["First","Second","Third"]}
 SwirlContextMenu {id:menu;items:["One","Two"];handleItemsInternally:false}
 SwirlDialog {id:dialog;ownerItem:fixture;guardChanges:false;title:"Motion fixture";contentItem:Item{implicitHeight:80} footer:SwirlButton{text:"Save"}}
 SwirlDialog {id:guarded;ownerItem:fixture;title:"Guarded fixture";contentItem:SwirlTextField {objectName:"apecGuardedField";text:"Original";implicitHeight:40}}
 Component {id:miniA;Item{objectName:"miniPageA"}}
 Component {id:miniB;Item{objectName:"miniPageB"}}
 Component {id:miniC;Item{Repeater{model:240;Item{}}}}
 SwirlPageHost {
  id:miniHost;x:0;y:220;width:180;height:120;routeKey:"a"
  sourceComponent:routeKey==="a"?miniA:routeKey==="b"?miniB:miniC
  property bool interruptPreparation:false
  property bool interrupted:false
  property bool coldWasPending:false
  onPreparingChanged:if(interruptPreparation && preparing && routeKey==="b"){
   interruptPreparation=false;interrupted=true
   routeKey="c";requestRoute();coldWasPending=pendingLoader!==null
   routeKey="b";requestRoute()
  }
 }
})QML",QUrl("qrc:/qt/qml/SwirlQuick/ApecMotionFixture.qml"));
    std::unique_ptr<QObject> object(component.create(qmlContext(window)));
    if(!object){qWarning()<<component.errors();check("fixture-load",false);}
    auto *fixture=qobject_cast<QQuickItem *>(object.get());
    if(fixture){
        fixture->setParentItem(window->contentItem());
        qmlEngine(window)->rootContext()->setContextProperty("apecFixture",fixture);
        check("fixture-load",true);wait(40);
        eval("apecFixture.miniHost.routeKey='b'");wait(420);eval("apecFixture.miniHost.routeKey='a'");wait(420);
        eval("apecFixture.miniHost.interruptPreparation=true;apecFixture.miniHost.routeKey='b'");wait(550);
        check("prepare-retarget-fixture-exercises-cold-request",eval("apecFixture.miniHost.interrupted && apecFixture.miniHost.coldWasPending").toBool());
        check("prepare-retarget-returns-visible-enabled-final-route",eval("apecFixture.miniHost.activeLoader.routeId==='b' && !apecFixture.miniHost.pendingGrab && !apecFixture.miniHost.moving && apecFixture.miniHost.activeLoader.visible && apecFixture.miniHost.activeLoader.enabled && apecFixture.miniHost.activeLoader.opacity===1").toBool());
        eval("apecFixture.miniHost.visible=false");
        eval("apecFixture.arc.targetY=180;apecFixture.arc.retarget();apecFixture.arc.targetY=0;apecFixture.arc.retarget()");wait(340);
        check("same-turn-reversal-retires-old-destination",eval("!apecFixture.arc.moving && apecFixture.arc.position.y===0 && apecFixture.arc.destination.y===0").toBool());
        eval("apecFixture.arc.targetY=180;apecFixture.arc.retarget()");wait(100);
        const auto before=eval("apecFixture.arc.position").toPointF();
        const auto velocity=eval("apecFixture.arc.velocity").toPointF();
        check("navigation-has-lateral-arc",before.x()>1 && before.y()>0 && before.y()<180);
        eval("apecFixture.arc.targetY=320;apecFixture.arc.retarget()");
        const auto after=eval("apecFixture.arc.position").toPointF();
        const auto afterVelocity=eval("apecFixture.arc.velocity").toPointF();
        qInfo()<<"APEC_VELOCITY"<<velocity<<afterVelocity;
        check("retarget-position-continuity",QLineF(before,after).length()<0.01);
        check("retarget-velocity-continuity",QLineF(velocity,afterVelocity).length()<0.01);
        wait(50);const auto reverse=eval("apecFixture.arc.position").toPointF();
        eval("apecFixture.arc.targetY=0;apecFixture.arc.retarget()");
        check("reverse-position-continuity",QLineF(reverse,eval("apecFixture.arc.position").toPointF()).length()<0.01);
        wait(380);check("reverse-settles-exactly",eval("!apecFixture.arc.moving && Math.abs(apecFixture.arc.position.x)<.001 && Math.abs(apecFixture.arc.position.y)<.001").toBool());
        eval("apecFixture.arc.targetY=180;apecFixture.arc.retarget()");wait(70);
        const auto stationaryTarget=eval("apecFixture.arc.position").toPointF();
        eval("{const p=Qt.point(apecFixture.arc.position.x,apecFixture.arc.position.y);apecFixture.arc.targetX=p.x;apecFixture.arc.targetY=p.y;apecFixture.arc.retarget()}");wait(340);
        check("current-position-target-retires-old-destination",!eval("apecFixture.arc.moving").toBool() && QLineF(stationaryTarget,eval("apecFixture.arc.position").toPointF()).length()<.01);
        eval("apecFixture.arc.targetX=0;apecFixture.arc.targetY=0;apecFixture.arc.retarget()");wait(340);
        for(int i=0;i<14;++i){eval(QString("apecFixture.arc.targetY=%1;apecFixture.arc.retarget()").arg(i%2?250:30));wait(15);}
        wait(380);check("rapid-third-target-settles",eval("!apecFixture.arc.moving && Math.abs(apecFixture.arc.position.y-250)<.001").toBool());
        eval("apecFixture.arc.targetY=0;apecFixture.arc.retarget()");wait(40);eval("Theme.reduceMotion=true");
        check("reduce-motion-midflight-settles",eval("!apecFixture.arc.moving && apecFixture.arc.position.y===0").toBool());
        eval("Theme.reduceMotion=false;apecFixture.arc.targetY=120;apecFixture.arc.retarget()");wait(30);eval("apecFixture.arc.visible=false");
        check("hidden-arc-stops",eval("!apecFixture.arc.moving && apecFixture.arc.position.y===120").toBool());
        eval("apecFixture.arc.visible=true;apecFixture.flow.phase='pending'");wait(80);
        check("pending-flow-runs",eval("apecFixture.flow.moving && apecFixture.flow.clock>0").toBool());
        eval("apecFixture.flow.visible=false");wait(30);
        check("hidden-flow-stops",eval("!apecFixture.flow.moving").toBool());
        eval("apecFixture.flow.visible=true;apecFixture.flow.phase='succeeded'");wait(70);
        check("success-starts-one-shot",eval("apecFixture.flow.moving && apecFixture.flow.sweep>0 && apecFixture.flow.sweep<1").toBool());
        wait(550);check("success-settles-no-idle-clock",eval("!apecFixture.flow.moving && apecFixture.flow.sweep===1").toBool());
        eval("apecFixture.flow.phase='failed'");wait(30);check("failure-never-runs-success",eval("!apecFixture.flow.moving && apecFixture.flow.phase==='failed'").toBool());
        eval("Theme.reduceMotion=true;apecFixture.flow.phase='pending'");wait(30);check("reduced-pending-static-state",eval("apecFixture.flow.pending && !apecFixture.flow.moving").toBool());
        eval("Theme.reduceMotion=false;apecFixture.flow.phase='idle';apecFixture.feedback.focused=true");wait(210);
        check("keyboard-focus-visible",eval("apecFixture.feedback.focusAmount>.99 && apecFixture.feedback.light>.75").toBool());
        eval("apecFixture.feedback.pressed=true");wait(60);eval("apecFixture.feedback.pressed=false");wait(700);
        check("contact-release-settles",eval("Math.abs(apecFixture.feedback.contact)<.01").toBool());
        eval("apecFixture.feedback.pressed=true");wait(40);eval("apecFixture.feedback.pressed=false");wait(20);eval("Theme.reduceMotion=true");wait(20);
        check("midflight-reduced-contact-settles",eval("apecFixture.feedback.contact===0").toBool());eval("Theme.reduceMotion=false");
        auto *checkBox=fixture->findChild<QQuickItem *>("apecCheckBox");
        if(checkBox){
            QTest::mouseClick(window,Qt::LeftButton,Qt::NoModifier,checkBox->mapToScene(QPointF(8,checkBox->height()/2)).toPoint());wait(25);
            check("checkbox-input-starts-presentation",eval("apecFixture.checkBox.checked && apecFixture.checkBox.moving && apecFixture.checkBox.markOpacity<1").toBool());
            eval("Theme.reduceMotion=true");
            check("checkbox-midflight-reduced-settles",eval("!apecFixture.checkBox.moving && apecFixture.checkBox.markOpacity===1 && apecFixture.checkBox.markScale===1 && apecFixture.checkBox.shownColor===apecFixture.checkBox.targetColor").toBool());
            eval("Theme.reduceMotion=false;apecFixture.checkBox.checked=false");wait(25);eval("apecFixture.checkBox.visible=false");
            check("checkbox-hidden-settles",eval("!apecFixture.checkBox.moving && apecFixture.checkBox.markOpacity===0 && apecFixture.checkBox.markScale===0.65").toBool());
            eval("apecFixture.checkBox.visible=true");
        }else check("checkbox-fixture-present",false);
        auto *caption=findVisual(window->contentItem(),"windowMaximizeButton");
        if(caption){
            qmlEngine(window)->rootContext()->setContextProperty("apecCaption",caption);
            QTest::mouseMove(window,QPoint(400,400));wait(160);
            QTest::mouseMove(window,caption->mapToScene(QPointF(caption->width()/2,caption->height()/2)).toPoint());wait(20);
            check("caption-hover-animates",caption->property("moving").toBool());
            eval("Theme.reduceMotion=true");
            check("caption-midflight-reduced-settles",eval("!apecCaption.moving && apecCaption.shownColor===apecCaption.targetColor").toBool());
            eval("Theme.reduceMotion=false");QTest::mouseMove(window,QPoint(400,400));wait(20);caption->setVisible(false);
            check("caption-hidden-settles",eval("!apecCaption.moving && apecCaption.shownColor===apecCaption.targetColor").toBool());
            caption->setVisible(true);qmlEngine(window)->rootContext()->setContextProperty("apecCaption",static_cast<QObject *>(nullptr));
        }else check("caption-fixture-present",false);
        auto *closeCaption=findVisual(window->contentItem(),"windowCloseButton");
        auto *minCaption=findVisual(window->contentItem(),"windowMinimizeButton");
        auto *maxCaption=findVisual(window->contentItem(),"windowMaximizeButton");
        auto *closeSurface=findVisual(window->contentItem(),"captionSurface2");
        check("caption-controls-and-paint-surface-present",closeCaption && minCaption && maxCaption && closeSurface);
        if(closeCaption && minCaption && maxCaption && closeSurface){
            qmlEngine(window)->rootContext()->setContextProperty("apecCaption",closeCaption);
            const auto rect=[](QQuickItem *item){return QRectF(item->mapToScene(QPointF()),item->size());};
            const auto initialRect=rect(closeCaption);
            const auto minRect=rect(minCaption),maxRect=rect(maxCaption);
            check("caption-hit-regions-equal-and-evenly-spaced",minRect.size()==maxRect.size() && maxRect.size()==initialRect.size()
                && qAbs((maxRect.x()-minRect.x())-(initialRect.x()-maxRect.x()))<0.001);
            check("caption-rounded-paint-is-inset-from-hit-region",closeSurface->x()>0 && closeSurface->y()>0
                && closeSurface->width()<closeCaption->width() && closeSurface->height()<closeCaption->height()
                && qAbs(closeSurface->property("radius").toDouble()-closeSurface->height()/2)<0.001);
            const auto center=closeCaption->mapToScene(QPointF(closeCaption->width()/2,closeCaption->height()/2)).toPoint();
            const auto park=QPoint(400,400);
            const int settle=eval("SwirlMotion.hoverDuration").toInt()+80;
            QTest::mouseMove(window,park);wait(settle);
            const auto idleImage=window->grabWindow();
            QTest::mouseMove(window,center);wait(settle);
            const auto hoverImage=window->grabWindow();
            const qreal dpr=window->devicePixelRatio();
            const auto pixelAt=[&](const QImage &image,QPointF local){
                const auto point=closeSurface->mapToScene(local)*dpr;
                return image.isNull()?QColor():image.pixelColor(qRound(point.x()),qRound(point.y()));
            };
            const auto colorDistance=[](QColor a,QColor b){return qAbs(a.red()-b.red())+qAbs(a.green()-b.green())+qAbs(a.blue()-b.blue());};
            const QColor hoverColor=eval("Theme.windowCloseHover").value<QColor>();
            bool roundedCorners=!idleImage.isNull() && !hoverImage.isNull();
            const QList<QPointF> cornerPoints{{1,1},{closeSurface->width()-2,1},{1,closeSurface->height()-2},{closeSurface->width()-2,closeSurface->height()-2}};
            for(const auto &point:cornerPoints)roundedCorners=roundedCorners
                && colorDistance(pixelAt(hoverImage,point),pixelAt(idleImage,point))<8
                && colorDistance(pixelAt(hoverImage,point),hoverColor)>60;
            check("caption-hover-render-has-four-clear-rounded-corners",roundedCorners);
            check("caption-hover-render-has-muted-danger-fill",colorDistance(pixelAt(hoverImage,QPointF(closeSurface->width()/2,3)),hoverColor)<8);
            QRect whiteBounds;
            const auto surfaceCenter=closeSurface->mapToScene(QPointF(closeSurface->width()/2,closeSurface->height()/2))*dpr;
            const int iconExtent=qCeil(8*dpr);
            for(int y=qRound(surfaceCenter.y())-iconExtent;y<=qRound(surfaceCenter.y())+iconExtent;++y)
                for(int x=qRound(surfaceCenter.x())-iconExtent;x<=qRound(surfaceCenter.x())+iconExtent;++x){
                    const auto color=hoverImage.isNull()?QColor():hoverImage.pixelColor(x,y);
                    if(color.red()>235 && color.green()>235 && color.blue()>235)whiteBounds=whiteBounds.united(QRect(x,y,1,1));
                }
            check("caption-close-glyph-centered-in-rounded-fill",!whiteBounds.isEmpty()
                && QLineF(QPointF(whiteBounds.left()+whiteBounds.width()/2.0,whiteBounds.top()+whiteBounds.height()/2.0),surfaceCenter).length()<=1.5);
            QTest::mousePress(window,Qt::LeftButton,Qt::NoModifier,center);wait(settle);
            const auto pressedImage=window->grabWindow();
            check("caption-pressed-render-retains-rounded-danger-feedback",closeCaption->property("down").toBool()
                && colorDistance(pixelAt(pressedImage,QPointF(closeSurface->width()/2,3)),eval("Theme.windowClosePressed").value<QColor>())<8
                && colorDistance(pixelAt(pressedImage,QPointF(1,1)),pixelAt(idleImage,QPointF(1,1)))<8);
            QTest::mouseMove(window,park);QTest::mouseRelease(window,Qt::LeftButton,Qt::NoModifier,park);wait(settle);
            maxCaption->forceActiveFocus(Qt::TabFocusReason);
            QTest::keyClick(window,Qt::Key_Tab);wait(settle);
            const qreal focusBorderWidth=QQmlProperty(closeSurface,QStringLiteral("border.width")).read().toDouble();
            qInfo()<<"CAPTION_FOCUS"<<closeCaption->property("visualFocus")<<"activeFocus"<<closeCaption->hasActiveFocus()
                   <<"focusReason"<<closeCaption->property("focusReason")<<"borderWidth"<<focusBorderWidth;
            const auto focusImage=window->grabWindow();
            check("caption-keyboard-focus-tints-fill-without-outline",closeCaption->property("visualFocus").toBool()
                && focusBorderWidth==0 && !focusImage.isNull()
                && colorDistance(pixelAt(focusImage,QPointF(closeSurface->width()/2,3)),pixelAt(idleImage,QPointF(closeSurface->width()/2,3)))>5
                && colorDistance(pixelAt(focusImage,QPointF(1,1)),pixelAt(idleImage,QPointF(1,1)))<8);
            closeCaption->setEnabled(false);QTest::mouseMove(window,center);wait(settle);
            QTest::mouseClick(window,Qt::LeftButton,Qt::NoModifier,center);
            check("caption-disabled-has-no-hover-press-or-close",window->isVisible() && !closeCaption->property("down").toBool()
                && closeCaption->property("shownColor").value<QColor>().alpha()==0);
            closeCaption->setEnabled(true);QTest::mouseMove(window,park);wait(settle);
            check("caption-states-preserve-click-region",rect(closeCaption)==initialRect);
            const auto imageDir=QFileInfo(output).absolutePath();QDir().mkpath(imageDir);
            check("caption-state-captures-saved",idleImage.save(imageDir+"/caption-default.png")
                && hoverImage.save(imageDir+"/caption-hover.png") && pressedImage.save(imageDir+"/caption-pressed.png") && focusImage.save(imageDir+"/caption-focus.png"));
            qmlEngine(window)->rootContext()->setContextProperty("apecCaption",static_cast<QObject *>(nullptr));
        }
        eval("apecFixture.menu.showAt(apecFixture,50,150)");wait(40);
        check("menu-first-open-visible",eval("apecFixture.menu.visible && apecFixture.menu.count===2").toBool());
        qInfo()<<"APEC_MENU_INITIAL"<<eval("JSON.stringify({visible:apecFixture.menu.visible,count:apecFixture.menu.count,opacity:apecFixture.menu.opacity})");
        eval("apecFixture.menu.close()");wait(35);eval("apecFixture.menu.showAt(apecFixture,50,150)");wait(260);
        qInfo()<<"APEC_MENU"<<eval("JSON.stringify({opened:apecFixture.menu.opened,visible:apecFixture.menu.visible,opacity:apecFixture.menu.opacity,scale:apecFixture.menu.scale})");
        check("menu-interrupt-reopen",eval("apecFixture.menu.opened && apecFixture.menu.opacity>.99 && apecFixture.menu.scale===1").toBool());
        QTest::keyClick(keyboardWindow(),Qt::Key_Escape);wait(220);check("menu-escape-closes",eval("!apecFixture.menu.visible").toBool());
        eval("apecFixture.menu.showAt(apecFixture,50,150)");wait(230);check("menu-open-before-reduced-exit",eval("apecFixture.menu.opened").toBool());eval("apecFixture.menu.close()");wait(30);eval("Theme.reduceMotion=true");wait(20);
        check("midflight-reduced-menu-retires",eval("!apecFixture.menu.visible").toBool());eval("Theme.reduceMotion=false");
        auto *button=fixture->findChild<QQuickItem *>("apecOpenDialog");
        if(button){QTest::mouseClick(window,Qt::LeftButton,Qt::NoModifier,button->mapToScene(QPointF(button->width()/2,button->height()/2)).toPoint());wait(50);check("dialog-opens-from-input",eval("apecFixture.dialog.visible").toBool());QTest::keyClick(window,Qt::Key_Escape);wait(50);eval("apecFixture.dialog.open()");wait(350);check("dialog-interrupt-reopen",eval("apecFixture.dialog.opened && apecFixture.dialog.opacity>.99 && apecFixture.dialog.scale===1").toBool());QTest::keyClick(window,Qt::Key_Escape);wait(250);check("dialog-escape-and-focus",eval("!apecFixture.dialog.visible").toBool() && window->activeFocusItem()!=nullptr);}
        eval("apecFixture.dialog.open()");wait(50);
        const auto footerOffset=eval("apecFixture.dialog.footer.mapToItem(apecFixture.dialog.background,0,0)").toPointF();
        wait(70);
        check("dialog-footer-shares-surface-trajectory",QLineF(footerOffset,eval("apecFixture.dialog.footer.mapToItem(apecFixture.dialog.background,0,0)").toPointF()).length()<.01);
        eval("Theme.reduceMotion=true");wait(20);
        check("midflight-reduced-dialog-enter-completes",eval("apecFixture.dialog.opened && apecFixture.dialog.opacity===1").toBool());
        eval("Theme.reduceMotion=false;apecFixture.dialog.close()");wait(30);eval("Theme.reduceMotion=true");wait(20);
        check("midflight-reduced-dialog-exit-retires",eval("!apecFixture.dialog.visible && dismissals.count===0").toBool());eval("Theme.reduceMotion=false");
        eval("apecFixture.guarded.open()");wait(340);
        auto *guarded=qvariant_cast<QObject *>(fixture->property("guarded"));
        auto *discard=guarded?guarded->findChild<QObject *>("discardChangesPrompt"):nullptr;
        qmlEngine(window)->rootContext()->setContextProperty("apecDiscard",discard);
        eval("apecFixture.guarded.contentItem.forceActiveFocus();apecFixture.guarded.contentItem.text='Edited';apecFixture.guarded.requestDismiss()");wait(45);
        check("discard-opens-second-owned-layer",discard && discard->property("visible").toBool() && eval("dismissals.count===2").toBool());
        const auto discardOffset=eval("apecDiscard.header.mapToItem(apecDiscard.background,0,0)").toPointF();wait(50);
        check("discard-header-shares-surface-trajectory",QLineF(discardOffset,eval("apecDiscard.header.mapToItem(apecDiscard.background,0,0)").toPointF()).length()<.01);
        eval("Theme.reduceMotion=true");wait(15);
        check("discard-reduced-enter-finishes",eval("apecDiscard.opened && apecDiscard.opacity===1").toBool());
        eval("Theme.reduceMotion=false");QTest::keyClick(keyboardWindow(),Qt::Key_Escape);wait(25);eval("Theme.reduceMotion=true");wait(20);
        check("discard-reduced-exit-retains-editor",eval("!apecDiscard.visible && apecFixture.guarded.opened && dismissals.count===1 && apecFixture.guarded.contentItem.text==='Edited'").toBool());
        check("discard-cancel-restores-editor-focus",eval("apecFixture.guarded.contentItem.activeFocus").toBool());
        eval("Theme.reduceMotion=false;apecFixture.guarded.requestDismiss()");wait(320);
        auto *discardContent=discard?qvariant_cast<QQuickItem *>(discard->property("contentItem")):nullptr;
        auto *confirm=discardContent?findVisual(discardContent,"discardChangesConfirm"):nullptr;
        check("discard-confirm-control-present",confirm!=nullptr);
        if(confirm && confirm->window()){
            qInfo()<<"APEC_DISCARD_CONFIRM_INPUT"<<confirm->isVisible()<<confirm->isEnabled()<<confirm->size()<<confirm->mapToScene(QPointF(confirm->width()/2,confirm->height()/2));
            QTest::mouseClick(confirm->window(),Qt::LeftButton,Qt::NoModifier,confirm->mapToScene(QPointF(confirm->width()/2,confirm->height()/2)).toPoint());wait(260);
        }
        check("discard-confirm-releases-both-layers",eval("!apecDiscard.visible && !apecFixture.guarded.visible && dismissals.count===0").toBool());
        qInfo()<<"APEC_DISCARD_AFTER_CONFIRM"<<eval("JSON.stringify({promptVisible:apecDiscard.visible,parentVisible:apecFixture.guarded.visible,layers:dismissals.count})");
        eval("apecDiscard.close();apecFixture.guarded.close()");wait(250);
        eval("apecFixture.dialog.open()");wait(330);eval("apecFixture.dialog.close()");wait(25);eval("apecFixture.guarded.open()");wait(330);
        qInfo()<<"APEC_REPLACEMENT_FOCUS"<<eval("JSON.stringify({oldVisible:apecFixture.dialog.visible,opened:apecFixture.guarded.opened,activeFocus:apecFixture.guarded.activeFocus,contentFocus:apecFixture.guarded.contentItem.activeFocus,focus:window.activeFocusItem?window.activeFocusItem.toString():'none',layers:dismissals.count})");
        check("old-dialog-close-keeps-new-popup-focus",eval("!apecFixture.dialog.visible && apecFixture.guarded.opened && apecFixture.guarded.activeFocus && dismissals.count===1").toBool());
        eval("apecFixture.guarded.close()");wait(250);
        check("guarded-final-close-releases-layer",eval("dismissals.count===0").toBool());
        qmlEngine(window)->rootContext()->setContextProperty("apecDiscard",static_cast<QObject *>(nullptr));
        eval("apecFixture.combo.forceActiveFocus()");QTest::keyClick(window,Qt::Key_Space);wait(250);
        check("combo-keyboard-open",eval("apecFixture.combo.popup.opened").toBool());QTest::keyClick(keyboardWindow(),Qt::Key_Down);QTest::keyClick(keyboardWindow(),Qt::Key_Return);wait(250);
        qInfo()<<"APEC_COMBO"<<eval("JSON.stringify({index:apecFixture.combo.currentIndex,highlight:apecFixture.combo.highlightedIndex,visible:apecFixture.combo.popup.visible})");
        check("combo-keyboard-commit",eval("apecFixture.combo.currentIndex===1 && !apecFixture.combo.popup.visible").toBool());
        eval("apecFixture.combo.popup.close()");wait(200);
        eval("apecFixture.arc.targetY=260;apecFixture.arc.retarget();apecFixture.feedback.pressed=true");wait(25);
        window->showMinimized();wait(100);
        check("minimized-window-settles-presentation",eval("!apecFixture.arc.moving && apecFixture.arc.position.y===260 && !apecFixture.feedback.moving && apecFixture.feedback.contact===1").toBool());
        window->showNormal();window->requestActivate();wait(160);eval("apecFixture.feedback.pressed=false");
        fixture->setVisible(false);wait(50);
        auto *collapse=window->findChild<QQuickItem *>("sidebarCollapseButton");
        if(collapse){
            collapse->forceActiveFocus();QTest::keyClick(window,Qt::Key_Space);wait(100);
            const auto intermediate=eval("window.actualSidebarWidth").toDouble();
            check("sidebar-collapse-in-flight",eval("AppState.sidebarCollapsed").toBool() && intermediate>eval("Theme.sidebarCollapsedWidth").toDouble() && intermediate<eval("Theme.sidebarWidth").toDouble());
            QTest::keyClick(window,Qt::Key_Space);wait(450);
            qInfo()<<"APEC_COLLAPSE"<<eval("JSON.stringify({collapsed:AppState.sidebarCollapsed,width:window.actualSidebarWidth,full:Theme.sidebarWidth,focus:window.activeFocusItem?window.activeFocusItem.objectName:''})");
            check("sidebar-collapse-reversal",!eval("AppState.sidebarCollapsed").toBool() && qAbs(eval("window.actualSidebarWidth-Theme.sidebarWidth").toDouble())<.01);
        }else check("sidebar-collapse-control",false);
        eval("AppState.navigate('overview')");wait(65);
        auto *sidebarArc=window->findChild<QObject *>("sidebarArcMotion");
        check("production-sidebar-arc-active",sidebarArc && sidebarArc->property("moving").toBool());
        eval("AppState.navigate('policies')");wait(35);eval("AppState.navigate('activity')");wait(500);
        check("production-navigation-settles",sidebarArc && !sidebarArc->property("moving").toBool() && eval("pageLoader.item!==null && !pageLoader.moving && !pageLoader.pendingGrab").toBool());
        QTest::keyClick(window,Qt::Key_K,Qt::ControlModifier);wait(250);
        auto *search=window->findChild<QObject *>("navigationSearchPopup");
        check("global-search-keyboard-open",search && search->property("opened").toBool());
        QTest::keyClick(keyboardWindow(),Qt::Key_Escape);wait(200);
        check("global-search-escape-keeps-route",search && !search->property("visible").toBool() && eval("AppState.currentPage==='activity' && dismissals.count===0").toBool());
        check("all-transition-tokens-retired",eval("SwirlTransitionRegistry.activeCount===0").toBool());
        qmlEngine(window)->rootContext()->setContextProperty("apecFixture",static_cast<QObject *>(nullptr));
    }
    eval("Theme.reduceMotion=false;Theme.transparency=true;AppState.navigate('activity')");wait(80);
    auto *wing=window->findChild<QQuickItem *>("apecWingVisual");
    // The accepted whole-feather master puts transparency in each painted
    // gradient. Its container stays opaque; multiplying the retired global
    // wingOpacity here would incorrectly dim the current artwork a second time.
    const auto wingState=[&](QQuickItem *visual){
        QVariantList state;
        if(!visual)return state;
        state.append(visual->opacity());state.append(visual->scale());state.append(visual->rotation());
        state.append(visual->property("progress"));
        state.append(QVariant::fromValue(visual->itemTransform(window->contentItem(), nullptr)));
        for(int i=0;i<visual->property("featherCount").toInt();++i){
            auto *feather=findVisual(visual,"wingFeather"+QString::number(i));
            if(!feather)return QVariantList();
            state.append(feather->opacity());state.append(feather->property("reveal"));
            state.append(QVariant::fromValue(feather->itemTransform(visual, nullptr)));
        }
        return state;
    };
    const auto settledFeathers=[&](QQuickItem *visual){
        if(!visual||visual->property("progress").toDouble()!=1||visual->opacity()!=1)return false;
        const int count=visual->property("featherCount").toInt();
        if(count<=0)return false;
        for(int i=0;i<count;++i){
            auto *feather=findVisual(visual,"wingFeather"+QString::number(i));
            if(!feather||feather->property("reveal").toDouble()!=1||feather->opacity()!=1
                ||!feather->itemTransform(feather->parentItem(), nullptr).isIdentity())return false;
            int gradients=0;
            for(auto *object:feather->findChildren<QObject *>()){
                auto *gradient=object->property("fillGradient").value<QObject *>();
                if(!gradient)continue;
                ++gradients;
                const QQmlListReference stops(gradient,"stops");
                if(!stops.isReadable()||stops.count()<2)return false;
                for(qsizetype stop=0;stop<stops.count();++stop){
                    auto *entry=stops.at(stop);
                    const auto color=entry?entry->property("color").value<QColor>():QColor();
                    if(!color.isValid()||color.alphaF()<=0||color.alphaF()>=1)return false;
                }
            }
            if(gradients!=1)return false;
        }
        return true;
    };
    check("production-wing-entry-already-consumed",wing && eval("appSceneBackdrop.entranceConsumed").toBool());
    check("production-wing-settles-every-feather-with-painted-transparency",settledFeathers(wing));
    const auto restingWing=wingState(wing);
    eval("AppState.navigate('overview')");wait(35);
    check("wing-persists-off-home",wing && !eval("appSceneBackdrop.entering").toBool()
        && eval("appSceneBackdrop.progress===1").toBool()
        && !restingWing.isEmpty() && wingState(wing)==restingWing);
    eval("AppState.navigate('activity')");wait(80);
    check("wing-does-not-replay-on-navigation",wing && !eval("appSceneBackdrop.entering").toBool()
        && !restingWing.isEmpty() && wingState(wing)==restingWing);
    window->showMinimized();wait(40);
    check("wing-minimize-stops-render-motion",!eval("appSceneBackdrop.presenting").toBool() && !eval("appSceneBackdrop.entering").toBool());
    window->showNormal();wait(80);
    check("wing-does-not-replay-on-restore",!eval("appSceneBackdrop.entering").toBool() && wing && wing->scale()==1 && wing->rotation()==0);

    QQmlComponent entryComponent(qmlEngine(window));
    entryComponent.setData("import QtQuick; import SwirlQuick; SwirlWorkspaceBackdrop {width:914;height:672;visible:false}",QUrl("qrc:/qt/qml/SwirlQuick/WingEntryFixture.qml"));
    std::unique_ptr<QObject> entryOwner(entryComponent.createWithInitialProperties({{"targetWindow",QVariant::fromValue(window)}},qmlContext(window)));
    auto *entry=qobject_cast<QQuickItem *>(entryOwner.get());
    check("fresh-wing-fixture-load",entry!=nullptr);
    if(entry){
        entry->setParentItem(window->contentItem());
        qmlEngine(window)->rootContext()->setContextProperty("apecEntry",entry);
        check("fresh-wing-has-not-consumed-opening",!entry->property("entranceConsumed").toBool());
        wait(180);
        check("hidden-window-does-not-consume-wing-opening",!entry->property("entranceConsumed").toBool() && entry->property("progress").toDouble()==0);
        eval("apecEntry.visible=true");window->update();wait(260);
        check("first-opening-unfolds",entry->property("entering").toBool() && entry->property("entranceConsumed").toBool());
        auto *visual=entry->findChild<QQuickItem *>("apecWingVisual");
        eval("Theme.reduceMotion=true");wait(40);
        check("reduced-motion-settles-unfolding",visual && !entry->property("entering").toBool()
            && visual->scale()==1 && visual->rotation()==0 && visual->y()==0
            && settledFeathers(visual));
        eval("Theme.reduceMotion=false;apecEntry.visible=false");wait(40);
        eval("apecEntry.visible=true");wait(100);
        check("consumed-opening-stays-static-on-return",!entry->property("entering").toBool() && visual && visual->rotation()==0 && visual->scale()==1);
        qmlEngine(window)->rootContext()->setContextProperty("apecEntry",static_cast<QObject *>(nullptr));
    }
    eval("Theme.reduceMotion=true");
    const auto api=window->rendererInterface()->graphicsApi();
    QDir().mkpath(QFileInfo(output).absolutePath());QFile report(output);if(!report.open(QIODevice::WriteOnly))return 2;
    report.write(QJsonDocument(QJsonObject{{"checks",checks},{"failures",failures},{"qtVersion",qVersion()},{"graphicsApi",int(api)},{"scope","Actual application QML, controlled motion/input; not physical refresh or private-network acceptance"}}).toJson());
    return failures?1:0;
}
