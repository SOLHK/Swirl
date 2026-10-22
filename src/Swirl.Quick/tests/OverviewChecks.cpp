#include "OverviewChecks.h"
#include <QQuickWindow>
#include <QQuickItem>
#include <QGuiApplication>
#include <QScreen>
#include <QQmlContext>
#include <QQmlExpression>
#include <QElapsedTimer>
#include <QTest>
#include <QDebug>
#include <QDir>
#include <QTcpServer>
#include <functional>

int runOverviewChecks(QQuickWindow *window) {
    int failures=0,checks=0;
    const auto check=[&](bool ok,const char *name){++checks;if(ok)qInfo()<<"PASS"<<name;else {++failures;qCritical()<<"FAIL"<<name;}};
    if(!window)return 1;window->resize(914,672);window->show();window->requestActivate();QTest::qWait(150);
    const auto state=[&](const QString &code){QQmlExpression expression(qmlContext(window),window,code);const auto result=expression.evaluate();if(expression.hasError())qCritical()<<expression.error();return result;};
    const auto wait=[&](const std::function<bool()> &condition){QElapsedTimer timer;timer.start();while(!condition()&&timer.elapsed()<3500)QTest::qWait(20);return condition();};
    std::function<QQuickItem *(QQuickItem *,const QString &)> find;
    find=[&](QQuickItem *parent,const QString &name)->QQuickItem *{if(parent->objectName()==name&&parent->isVisible())return parent;for(auto *child:parent->childItems())if(auto *result=find(child,name))return result;return nullptr;};
    const auto item=[&](const char *name,QQuickWindow *target=nullptr){return find((target?target:window)->contentItem(),QString::fromLatin1(name));};
    const auto settled=[&]{wait([&]{return !state("pageLoader.moving || pageLoader.pendingGrab").toBool();});};
    const auto click=[&](const char *name,QQuickWindow *target=nullptr){auto *control=item(name,target);if(!control){check(false,"native input target exists");return false;}auto *w=target?target:window;QTest::mouseClick(w,Qt::LeftButton,Qt::NoModifier,control->mapToScene(QPointF(control->width()/2,control->height()/2)).toPoint());QTest::qWait(80);settled();return true;};
    const auto type=[&](const char *name,const QString &text,QQuickWindow *target=nullptr){auto *control=item(name,target);if(!control){check(false,"editable input exists");return;}control->forceActiveFocus();auto *w=target?target:window;QTest::keyClick(w,Qt::Key_A,Qt::ControlModifier);for(const auto character:text)QTest::keyClick(w,character.toLatin1());QTest::qWait(50);};
    const auto ownsPopup=[&](QObject *popup,QQuickWindow *expected){auto *visual=popup?qobject_cast<QQuickItem *>(popup->property("parent").value<QObject *>()):nullptr;return visual&&visual->window()==expected;};
    check(state("AppState.measuredDown===0 && AppState.measuredUp===0 && !engineController.processAlive").toBool(),"initial traffic and core state come from the stopped engine");
    for(const auto *route:{"activity","overview","processes","gateway","policies","rules","capture","tls","rewrite","featurehub"}){
        const auto control=QString("nav-")+route;click(control.toUtf8().constData());
        check(wait([&]{return state(QString("AppState.currentPage === '%1' && pageLoader.item !== null").arg(route)).toBool();}),"sidebar mouse input loads its real page");
    }
    click("nav-rules");click("addRoutingRule");type("rulePattern","example.test");click("saveRoutingRule");
    check(state("engineController.routingRules.some(r=>r.pattern==='example.test' && r.policy==='DIRECT')").toBool(),"rule editor mouse and keyboard input persists a real rule");
    type("rulesSearch","example.test");check(state("pageLoader.item.displayRules.length===1").toBool(),"rules search filters saved rules");
    check(wait([&]{return state("dismissals.count===0").toBool();}),"rule dialog releases its modal shield before table input");
    if(auto *table=item("rulesTable")){QTest::mouseClick(window,Qt::LeftButton,Qt::NoModifier,table->mapToScene(QPointF(60,39)).toPoint());QTest::qWait(50);}else check(false,"rules table exists");
    click("removeRoutingRule");check(state("!engineController.routingRules.some(r=>r.pattern==='example.test')").toBool(),"selected custom rule can be removed by its editor action");
    click("nav-capture");
    // The user's capture service may already own the normal UI port. This
    // isolated fixture exercises the same toggle on its own ephemeral port.
    QTcpServer reservation;const bool reserved=reservation.listen(QHostAddress::LocalHost,0);const auto capturePort=reservation.serverPort();reservation.close();
    check(reserved,"capture fixture obtains its own loopback port");
    state(QString("pageLoader.item.listenerPort=%1").arg(capturePort));click("captureToggle");
    check(state(QString("captureProvider.running && captureProvider.port===%1").arg(capturePort)).toBool(),"capture toggle starts the actual loopback listener");
    click("captureToggle");check(state("!captureProvider.running").toBool(),"capture toggle closes the listener");
    click("nav-tls");click("certificateAction-0");check(wait([&]{return state("captureProvider.tls.ready").toBool();}),"certificate action generates an actual protected local CA");
    check(state("!captureProvider.tls.enabled && !captureProvider.tls.trusted").toBool(),"CA generation keeps interception and system trust opt-in");
    click("tlsToggle");check(state("captureProvider.tls.enabled").toBool(),"TLS control enables interception after certificate creation");click("tlsToggle");
    click("nav-featurehub");click("settings-dns");
    const auto nativeHandle=window->winId();
    check(state("AppState.currentPage==='dns' && pageLoader.item!==null").toBool(),"DNS opens inside the main navigation host");
    const auto originalSize=window->size();window->resize(window->minimumWidth(),window->minimumHeight());QTest::qWait(80);
    auto *apply=item("applyDns");check(apply&&apply->mapToScene(QPointF(0,0)).y()+apply->height()<=window->height(),"DNS Apply remains visible at the minimum main viewport");
    window->resize(originalSize);QTest::qWait(80);click("dnsMode-2");type("dnsServerAddress","127.0.0.1");click("applyDns");
    check(state("AppState.currentPage==='featurehub' && engineController.dnsConfiguration.mode===2 && engineController.dnsConfiguration.servers==='127.0.0.1'").toBool(),"DNS Apply validates, persists and returns to the settings hub");
    click("settings-dns");type("dnsServerAddress","192.0.2.53");click("cancelDns");
    check(state("AppState.currentPage==='featurehub' && engineController.dnsConfiguration.servers==='127.0.0.1'").toBool(),"DNS Cancel returns without applying draft edits");
    click("settings-subscriptions");
    check(state("AppState.currentPage==='subscriptions'").toBool(),"More opens the complete subscription manager in the main window");
    click("addSubscription");QTest::qWait(300);
    if(auto *popup=window->findChild<QObject *>("subscriptionDialog"))
        check(ownsPopup(popup,window)&&popup->property("ownerWindow").value<QObject *>()==window&&item("subscriptionName"),"subscription form belongs to the original main overlay");
    else check(false,"subscription dialog exists");
    QTest::keyClick(window,Qt::Key_Escape);QTest::qWait(350);
    check(state("AppState.currentPage==='subscriptions' && dismissals.count===0").toBool(),"one Escape closes only the subscription form and preserves its page");
    click("addSubscription");QTest::qWait(300);type("subscriptionName","Unsaved fixture");
    QTest::keyClick(window,Qt::Key_1,Qt::ControlModifier);QTest::qWait(50);
    check(state("AppState.currentPage==='subscriptions'").toBool(),"navigation shortcuts cannot bypass a modal draft");
    QTest::keyClick(window,Qt::Key_Escape);QTest::qWait(300);
    check(state("AppState.currentPage==='subscriptions' && dismissals.count===2").toBool(),"dirty subscription form asks before discarding");
    if(auto *popup=window->findChild<QObject *>("subscriptionDialog"))check(ownsPopup(popup->findChild<QObject *>("discardChangesPrompt"),window),"nested discard prompt keeps the main overlay owner");
    QTest::keyClick(window,Qt::Key_Escape);QTest::qWait(300);
    check(state("dismissals.count===1").toBool(),"Escape cancels discard confirmation and preserves the edited form");
    QTest::keyClick(window,Qt::Key_Escape);QTest::qWait(300);click("discardChangesConfirm");QTest::qWait(350);
    QTest::keyClick(window,Qt::Key_Escape);settled();
    check(state("AppState.currentPage==='featurehub'").toBool()&&window->isVisible(),"next Escape returns to the hub while the main window stays open");
    click("settings-subscriptions");click("addSubscription");QTest::qWait(300);
    check(ownsPopup(window->findChild<QObject *>("subscriptionDialog"),window)&&item("subscriptionName"),"cached form retains its main overlay after back and reopen");
    QTest::keyClick(window,Qt::Key_Escape);QTest::qWait(350);QTest::keyClick(window,Qt::Key_Escape);settled();
    check(state("AppState.currentPage==='featurehub'").toBool(),"cached form and its page dismiss independently after reopening");
    QTest::keyClick(window,Qt::Key_Escape);QTest::qWait(100);check(window->isVisible(),"Escape on the hub never exits Swirl");
    window->requestActivate();click("nav-external");QQuickWindow *dashboard=nullptr;for(auto *candidate:QGuiApplication::allWindows())if(candidate->objectName()=="dashboardWindow")dashboard=qobject_cast<QQuickWindow *>(candidate);
    check(dashboard&&dashboard->isVisible()&&dashboard->width()==1300,"Panel opens the independent native request window");
    if(dashboard){check(item("windowCloseButton",dashboard)&&item("windowMinimizeButton",dashboard)&&item("windowMaximizeButton",dashboard),"request panel has all three window controls");click("windowCloseButton",dashboard);check(!dashboard->isVisible()&&window->isVisible(),"panel red button closes only the panel");}
    for(const auto *route:{"settings","fonts","profiles","dns","modules","scripts","subscriptions","proxies"}){
        state(QString("window.openSettings('%1')").arg(route));QTest::qWait(80);settled();
        auto *page=qobject_cast<QQuickItem *>(state("pageLoader.item").value<QObject *>());
        check(page&&page->window()==window&&window->winId()==nativeHandle&&item("windowCloseButton")&&item("windowMinimizeButton")&&item("windowMaximizeButton"),"every settings route uses the original main shell and its controls");
        if(QString::fromLatin1(route)=="settings"){
            state("pageLoader.item.section='关于 Swirl'");QTest::qWait(80);
            const auto *brand=item("brandVector");check(brand&&brand->isVisible()&&brand->width()>=104,"About retains the enlarged brand mark inside the settings page");
        }
        const auto qaDirectory=qEnvironmentVariable("SWIRL_UI_QA_DIRECTORY");
        if(!qaDirectory.isEmpty()){QDir().mkpath(qaDirectory);check(window->grabWindow().save(qaDirectory+"/"+route+".png"),"embedded page render saved for visual review");}
        click("settingsBackButton");check(state("AppState.currentPage==='featurehub'").toBool()&&window->isVisible(),"back returns from each settings route without closing the shell");
    }
    settled();check(state("dismissals.count===0").toBool(),"completed settings return releases its modal layer before global shortcuts");
    window->requestActivate();QTest::keyClick(window,Qt::Key_K,Qt::ControlModifier);QTest::qWait(100);type("pageSearch","DNS");QTest::keyClick(window,Qt::Key_Return);settled();
    check(state("AppState.currentPage==='dns'").toBool(),"Ctrl+K searches and navigates from actual keyboard input");
    state("AppState.navigate('scripts')");QTest::qWait(50);settled();click("scriptAddButton");type("localScriptName","UI script");type("localScriptSource","function main(input){return {sum:input.a+input.b};}");type("localScriptInput","{\"a\":20,\"b\":22}");click("localScriptSave");
    check(state("extensionsProvider.scripts.length===1").toBool(),"script editor persists actual local JavaScript");click("localScriptRun");
    check(wait([&]{return state("!extensionsProvider.busy && extensionsProvider.output.length>0").toBool();})&&state("JSON.parse(extensionsProvider.output).result.sum===42").toBool(),"Evaluate runs the saved script with real JSON input in its separate process");
    qInfo()<<"Reference interaction checks:"<<checks<<"checks,"<<failures<<"failures";return failures?2:0;
}
