#include "app/MotionPolicy.h"
#include <QQuickWindow>
#include <QQuickItem>
#include <QGuiApplication>
#include <QQmlEngine>
#include <QQmlContext>
#include <QQmlComponent>
#include <QQmlExpression>
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
#include <memory>

int runApecMotionChecks(QQuickWindow *window,const QString &output) {
    QJsonArray checks;int failures=0;
    const auto check=[&](const char *name,bool passed){checks.append(QJsonObject{{"name",name},{"passed",passed}});if(!passed)++failures;qInfo()<<"APEC_MOTION_CHECK"<<name<<passed;};
    const auto wait=[](int ms){QEventLoop loop;QTimer timer;timer.setTimerType(Qt::PreciseTimer);timer.setSingleShot(true);QObject::connect(&timer,&QTimer::timeout,&loop,&QEventLoop::quit);timer.start(ms);loop.exec();};
    const auto keyboardWindow=[&](){
        for(auto *candidate:QGuiApplication::allWindows())if(candidate->isVisible() && candidate->flags().testFlag(Qt::Popup))if(auto *quick=qobject_cast<QQuickWindow *>(candidate))return quick;
        return window;
    };
    const auto eval=[&](const QString &source){QQmlExpression e(qmlContext(window),window,source);auto result=e.evaluate();if(e.hasError()){qWarning()<<e.error();check("qml-expression",false);}return result;};
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
 SwirlArcMotion {id:arc;targetX:0;targetY:0;duration:300;bend:12}
 SwirlFlow {id:flow;x:280;y:40;width:80;height:35}
 SwirlInteractionMotion {id:feedback}
 SwirlButton {id:openButton;objectName:"apecOpenDialog";text:"Motion fixture";onClicked:dialog.open()}
 SwirlComboBox {id:combo;y:70;width:190;model:["First","Second","Third"]}
 SwirlContextMenu {id:menu;items:["One","Two"];handleItemsInternally:false}
 SwirlDialog {id:dialog;ownerItem:fixture;guardChanges:false;title:"Motion fixture";contentItem:Item{implicitHeight:80} footer:SwirlButton{text:"Save"}}
})QML",QUrl("qrc:/qt/qml/SwirlQuick/ApecMotionFixture.qml"));
    std::unique_ptr<QObject> object(component.create(qmlContext(window)));
    if(!object){qWarning()<<component.errors();check("fixture-load",false);}
    auto *fixture=qobject_cast<QQuickItem *>(object.get());
    if(fixture){
        fixture->setParentItem(window->contentItem());
        qmlEngine(window)->rootContext()->setContextProperty("apecFixture",fixture);
        check("fixture-load",true);wait(40);
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
        eval("apecFixture.combo.forceActiveFocus()");QTest::keyClick(window,Qt::Key_Space);wait(250);
        check("combo-keyboard-open",eval("apecFixture.combo.popup.opened").toBool());QTest::keyClick(keyboardWindow(),Qt::Key_Down);QTest::keyClick(keyboardWindow(),Qt::Key_Return);wait(250);
        qInfo()<<"APEC_COMBO"<<eval("JSON.stringify({index:apecFixture.combo.currentIndex,highlight:apecFixture.combo.highlightedIndex,visible:apecFixture.combo.popup.visible})");
        check("combo-keyboard-commit",eval("apecFixture.combo.currentIndex===1 && !apecFixture.combo.popup.visible").toBool());
        eval("apecFixture.combo.popup.close()");wait(200);
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
    const auto api=window->rendererInterface()->graphicsApi();
    QDir().mkpath(QFileInfo(output).absolutePath());QFile report(output);if(!report.open(QIODevice::WriteOnly))return 2;
    report.write(QJsonDocument(QJsonObject{{"checks",checks},{"failures",failures},{"qtVersion",qVersion()},{"graphicsApi",int(api)},{"scope","Actual application QML, controlled motion/input; not physical refresh or private-network acceptance"}}).toJson());
    return failures?1:0;
}
