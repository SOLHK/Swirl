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
#include <functional>

int runOverviewChecks(QQuickWindow *window) {
    int failures=0,checks=0;
    const auto check=[&](bool ok,const char *name){++checks;if(ok)qInfo()<<"PASS"<<name;else {++failures;qCritical()<<"FAIL"<<name;}};
    if(!window)return 1;window->resize(914,672);window->show();window->requestActivate();QTest::qWait(150);
    const auto state=[&](const QString &code){QQmlExpression expression(qmlContext(window),window,code);const auto result=expression.evaluate();if(expression.hasError())qCritical()<<expression.error();return result;};
    const auto wait=[&](const std::function<bool()> &condition){QElapsedTimer timer;timer.start();while(!condition()&&timer.elapsed()<3500)QTest::qWait(20);return condition();};
    std::function<QQuickItem *(QQuickItem *,const QString &)> find;
    find=[&](QQuickItem *parent,const QString &name)->QQuickItem *{if(parent->objectName()==name)return parent;for(auto *child:parent->childItems())if(auto *result=find(child,name))return result;return nullptr;};
    const auto item=[&](const char *name,QQuickWindow *target=nullptr){return find((target?target:window)->contentItem(),QString::fromLatin1(name));};
    const auto settled=[&]{wait([&]{return !state("pageLoader.moving || pageLoader.pendingGrab").toBool();});};
    const auto click=[&](const char *name,QQuickWindow *target=nullptr){auto *control=item(name,target);if(!control){check(false,"native input target exists");return false;}auto *w=target?target:window;QTest::mouseClick(w,Qt::LeftButton,Qt::NoModifier,control->mapToScene(QPointF(control->width()/2,control->height()/2)).toPoint());QTest::qWait(80);settled();return true;};
    const auto type=[&](const char *name,const QString &text,QQuickWindow *target=nullptr){auto *control=item(name,target);if(!control){check(false,"editable input exists");return;}control->forceActiveFocus();auto *w=target?target:window;QTest::keyClick(w,Qt::Key_A,Qt::ControlModifier);for(const auto character:text)QTest::keyClick(w,character.toLatin1());QTest::qWait(50);};
    check(state("AppState.measuredDown===0 && AppState.measuredUp===0 && !engineController.processAlive").toBool(),"initial traffic and core state come from the stopped engine");
    for(const auto *route:{"activity","overview","processes","gateway","policies","rules","capture","tls","rewrite","featurehub"}){
        const auto control=QString("nav-")+route;click(control.toUtf8().constData());
        check(wait([&]{return state(QString("AppState.currentPage === '%1' && pageLoader.item !== null").arg(route)).toBool();}),"sidebar mouse input loads its real page");
    }
    click("nav-rules");click("addRoutingRule");type("rulePattern","example.test");click("saveRoutingRule");
    check(state("engineController.routingRules.some(r=>r.pattern==='example.test' && r.policy==='DIRECT')").toBool(),"rule editor mouse and keyboard input persists a real rule");
    type("rulesSearch","example.test");check(state("pageLoader.item.displayRules.length===1").toBool(),"rules search filters saved rules");
    if(auto *table=item("rulesTable")){QTest::mouseClick(window,Qt::LeftButton,Qt::NoModifier,table->mapToScene(QPointF(60,39)).toPoint());QTest::qWait(50);}else check(false,"rules table exists");
    click("removeRoutingRule");check(state("!engineController.routingRules.some(r=>r.pattern==='example.test')").toBool(),"selected custom rule can be removed by its editor action");
    click("nav-capture");click("captureToggle");check(state("captureProvider.running && captureProvider.port===8899").toBool(),"capture toggle starts the actual loopback listener");
    click("captureToggle");check(state("!captureProvider.running").toBool(),"capture toggle closes the listener");
    click("nav-tls");click("certificateAction-0");check(wait([&]{return state("captureProvider.tls.ready").toBool();}),"certificate action generates an actual protected local CA");
    check(state("!captureProvider.tls.enabled && !captureProvider.tls.trusted").toBool(),"CA generation keeps interception and system trust opt-in");
    click("tlsToggle");check(state("captureProvider.tls.enabled").toBool(),"TLS control enables interception after certificate creation");click("tlsToggle");
    click("nav-featurehub");click("settings-dns");
    QQuickWindow *sheet=nullptr;for(auto *candidate:QGuiApplication::allWindows())if(candidate->objectName()=="settingsSheet")sheet=qobject_cast<QQuickWindow *>(candidate);
    check(sheet&&sheet->isVisible()&&sheet->width()==qMin(900,sheet->screen()->availableGeometry().width())&&sheet->height()==qMin(790,sheet->screen()->availableGeometry().height()),"DNS opens a separate native sheet with room for its title bar");
    if(sheet){const auto originalHeight=sheet->height();sheet->resize(900,500);QTest::qWait(50);auto *apply=item("applyDns",sheet);check(apply&&apply->mapToScene(QPointF(0,0)).y()+apply->height()<=sheet->height(),"DNS Apply remains visible on a short native viewport");sheet->resize(900,originalHeight);QTest::qWait(50);click("dnsMode-2",sheet);type("dnsServerAddress","127.0.0.1",sheet);click("applyDns",sheet);
        check(!sheet->isVisible()&&state("engineController.dnsConfiguration.mode===2 && engineController.dnsConfiguration.servers==='127.0.0.1'").toBool(),"DNS Apply validates, persists and closes the native sheet");
        window->requestActivate();click("settings-dns");type("dnsServerAddress","192.0.2.53",sheet);click("cancelDns",sheet);
        check(!sheet->isVisible()&&state("engineController.dnsConfiguration.servers==='127.0.0.1'").toBool(),"DNS Cancel closes the sheet without applying draft edits");}
    window->requestActivate();click("nav-external");QQuickWindow *dashboard=nullptr;for(auto *candidate:QGuiApplication::allWindows())if(candidate->objectName()=="dashboardWindow")dashboard=qobject_cast<QQuickWindow *>(candidate);
    check(dashboard&&dashboard->isVisible()&&dashboard->width()==1300,"Panel opens the independent native request window");
    if(dashboard){check(item("windowCloseButton",dashboard)&&item("windowMinimizeButton",dashboard)&&item("windowMaximizeButton",dashboard),"request panel has all three window controls");click("windowCloseButton",dashboard);check(!dashboard->isVisible()&&window->isVisible(),"panel red button closes only the panel");}
    if(sheet){
        for(const auto *route:{"profiles","appearance","license","dns","modules","scripts"}){
            state(QString("window.openSettings('%1')").arg(route));QTest::qWait(100);
            check(sheet->isVisible()&&item("windowCloseButton",sheet)&&item("windowMinimizeButton",sheet)&&item("windowMaximizeButton",sheet),"every secondary route has visible window controls");
            check(state("settingsLoader.y>=settingsTitleBar.height").toBool(),"secondary page starts below the title bar");
            if(QString::fromLatin1(route)=="license"){
                const auto *brand=item("brandVector",sheet);check(brand&&brand->isVisible()&&brand->width()>=104,"About page displays the enlarged brand mark after reopening Appearance");
            }
            const auto qaDirectory=qEnvironmentVariable("SWIRL_UI_QA_DIRECTORY");
            if(!qaDirectory.isEmpty()){QDir().mkpath(qaDirectory);check(sheet->grabWindow().save(qaDirectory+"/"+route+".png"),"secondary window render saved for visual review");}
            click("windowCloseButton",sheet);check(!sheet->isVisible()&&window->isVisible(),"secondary red button closes only its window");
        }
        state("window.openSettings('profiles')");QTest::qWait(100);click("windowMaximizeButton",sheet);check(sheet->visibility()==QWindow::Maximized,"secondary green button maximizes");
        click("windowMaximizeButton",sheet);check(sheet->visibility()==QWindow::Windowed,"secondary green button restores");
        click("windowMinimizeButton",sheet);check(sheet->visibility()==QWindow::Minimized,"secondary yellow button minimizes");
        sheet->showNormal();sheet->requestActivate();QTest::qWait(100);QTest::keyClick(sheet,Qt::Key_Escape);QTest::qWait(100);check(!sheet->isVisible()&&window->isVisible(),"Escape dismisses the secondary window");
    }
    window->requestActivate();QTest::keyClick(window,Qt::Key_K,Qt::ControlModifier);QTest::qWait(100);type("pageSearch","DNS");QTest::keyClick(window,Qt::Key_Return);settled();
    check(state("AppState.currentPage==='dns'").toBool(),"Ctrl+K searches and navigates from actual keyboard input");
    state("AppState.navigate('scripts')");QTest::qWait(50);settled();click("scriptAddButton");type("localScriptName","UI script");type("localScriptSource","function main(input){return {sum:input.a+input.b};}");type("localScriptInput","{\"a\":20,\"b\":22}");click("localScriptSave");
    check(state("extensionsProvider.scripts.length===1").toBool(),"script editor persists actual local JavaScript");click("localScriptRun");
    check(wait([&]{return state("!extensionsProvider.busy && extensionsProvider.output.length>0").toBool();})&&state("JSON.parse(extensionsProvider.output).result.sum===42").toBool(),"Evaluate runs the saved script with real JSON input in its separate process");
    qInfo()<<"Reference interaction checks:"<<checks<<"checks,"<<failures<<"failures";return failures?2:0;
}
