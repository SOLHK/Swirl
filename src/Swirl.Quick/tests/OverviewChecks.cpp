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
#include <QJsonDocument>
#include <QJsonObject>
#include <QUrl>
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
    click("nav-rules");click("addRoutingRule");
    auto *ruleEditor=window->findChild<QObject *>("ruleEditor");
    check(wait([&]{return ruleEditor&&ruleEditor->property("opened").toBool();}),"rule editor completes its opening transition before input");
    auto *rulePolicy=item("rulePolicy");
    auto *saveRule=item("saveRoutingRule");
    check(rulePolicy&&rulePolicy->property("currentIndex").toInt()==-1&&saveRule&&!saveRule->isEnabled(),"new rule requires an explicit policy selection before saving");
    type("rulePattern","example.test");click("rulePolicy");
    auto *policyPopup=rulePolicy?qvariant_cast<QObject *>(rulePolicy->property("popup")):nullptr;
    check(wait([&]{return policyPopup&&policyPopup->property("opened").toBool();}),"rule policy menu opens through native mouse input");
    click("swirlComboOption-0");
    check(wait([&]{return rulePolicy&&rulePolicy->property("currentText").toString()=="DIRECT"&&policyPopup&&!policyPopup->property("visible").toBool();}),"DIRECT selection closes its menu before rule submission");
    check(saveRule&&saveRule->isEnabled(),"explicit policy and pattern enable rule submission");
    click("saveRoutingRule");
    check(wait([&]{return state("engineController.routingRules.some(r=>r.pattern==='example.test' && r.policy==='DIRECT') && !pageLoader.item.ruleSubmitting").toBool();}),"rule editor mouse and keyboard input persists a real rule");
    check(wait([&]{return ruleEditor&&!ruleEditor->property("visible").toBool()&&state("dismissals.count===0").toBool();}),"saved rule closes its editor after configuration completion");
    type("rulesSearch","example.test");check(state("pageLoader.item.displayRules.length===1").toBool(),"rules search filters saved rules");
    check(wait([&]{return state("dismissals.count===0").toBool();}),"rule dialog releases its modal shield before table input");
    if(auto *table=item("rulesTable")){QTest::mouseClick(window,Qt::LeftButton,Qt::NoModifier,table->mapToScene(QPointF(60,39)).toPoint());QTest::qWait(50);}else check(false,"rules table exists");
    click("removeRoutingRule");check(wait([&]{return state("!engineController.routingRules.some(r=>r.pattern==='example.test')").toBool();}),"selected custom rule can be removed by its editor action");
    click("nav-capture");
    // The user's capture service may already own the normal UI port. This
    // isolated fixture exercises the same toggle on its own ephemeral port.
    QTcpServer reservation;const bool reserved=reservation.listen(QHostAddress::LocalHost,0);const auto capturePort=reservation.serverPort();reservation.close();
    check(reserved,"capture fixture obtains its own loopback port");
    state(QString("pageLoader.item.listenerPort=%1").arg(capturePort));click("captureToggle");
    check(state(QString("captureProvider.running && captureProvider.port===%1").arg(capturePort)).toBool(),"capture toggle starts the actual loopback listener");
    check(item("captureStateFlow")&&item("captureStateFlow")->property("phase")=="succeeded","capture flow follows the actual listener state after native toggle input");
    click("captureToggle");check(state("!captureProvider.running").toBool(),"capture toggle closes the listener");
    click("nav-tls");click("certificateAction-0");check(wait([&]{return state("captureProvider.tls.ready").toBool();}),"certificate action generates an actual protected local CA");
    check(state("!captureProvider.tls.enabled && !captureProvider.tls.trusted").toBool(),"CA generation keeps interception and system trust opt-in");
    click("tlsToggle");check(state("captureProvider.tls.enabled").toBool(),"TLS control enables interception after certificate creation");
    check(item("tlsStateFlow")&&item("tlsStateFlow")->property("phase")=="succeeded","TLS flow follows actual interception state after native toggle input");click("tlsToggle");
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
    check(dashboard&&dashboard->isVisible()
          &&dashboard->width()==qRound(state("Theme.windowDefaultWidth").toReal())
          &&dashboard->height()==qRound(state("Theme.windowDefaultHeight").toReal()),
          "Panel opens the independent native request window at the approved UI dimensions");
    if(dashboard){check(item("windowCloseButton",dashboard)&&item("windowMinimizeButton",dashboard)&&item("windowMaximizeButton",dashboard),"request panel has all three window controls");click("windowCloseButton",dashboard);check(!dashboard->isVisible()&&window->isVisible(),"panel red button closes only the panel");}
    for(const auto *route:{"settings","fonts","profiles","dns","modules","scripts","subscriptions","proxies"}){
        state(QString("window.openSettings('%1')").arg(route));QTest::qWait(80);settled();
        auto *page=qobject_cast<QQuickItem *>(state("pageLoader.item").value<QObject *>());
        check(page&&page->window()==window&&window->winId()==nativeHandle&&item("windowCloseButton")&&item("windowMinimizeButton")&&item("windowMaximizeButton"),"every settings route uses the original main shell and its controls");
        if(QString::fromLatin1(route)=="settings"){
            state("pageLoader.item.section='关于 Swirl'");
            QJsonObject aboutObservation;
            QElapsedTimer aboutWait;aboutWait.start();
            const bool aboutBrandReady=wait([&]{
                aboutObservation=QJsonDocument::fromJson(state(QStringLiteral(
                    "JSON.stringify({route:AppState.currentPage,activeRoute:pageLoader.activeLoader?pageLoader.activeLoader.routeId:'',"
                    "loaderStatus:pageLoader.activeLoader?pageLoader.activeLoader.status:-1,loaderReady:Loader.Ready,imageReady:Image.Ready,"
                    "moving:pageLoader.moving,pending:pageLoader.pendingGrab,preparing:pageLoader.preparing,registry:SwirlTransitionRegistry.activeCount,"
                    "section:pageLoader.item?pageLoader.item.section:'',sectionReady:!!pageLoader.item&&typeof pageLoader.item.currentSectionReady==='function'&&pageLoader.item.currentSectionReady(),"
                    "uiScale:Theme.uiScale,compactBoundary:Theme.dp(520),compactSize:Theme.dp(64),regularSize:Theme.dp(76),"
                    "expectedSource:Theme.increaseContrast?(Theme.dark?'qrc:/swirl/icons/swirl_knot_mark_mono_dark.svg':'qrc:/swirl/icons/swirl_knot_mark_mono_light.svg')"
                    ":(Theme.dark?'qrc:/swirl/icons/swirl_knot_mark_dark.svg':'qrc:/swirl/icons/swirl_knot_mark_light.svg')})")).toString().toUtf8()).object();
                const bool samePage=page&&state("pageLoader.item").value<QObject *>()==page;
                auto *brand=samePage?find(page,QStringLiteral("brandVector")):nullptr;
                auto *mark=brand?brand->parentItem():nullptr;
                QQuickItem *pane=nullptr,*paneLoader=nullptr,*shell=nullptr;
                // Identify the loaded About pane through its own visual ancestry;
                // cached pages and the other windows also own brandVector images.
                for(auto *ancestor=mark;ancestor&&ancestor!=page;ancestor=ancestor->parentItem()){
                    if(!pane&&ancestor->property("settingsPage").value<QObject *>()==page
                        &&ancestor->property("viewportHeight").isValid()&&ancestor->property("compact").isValid())pane=ancestor;
                    if(pane&&!paneLoader&&ancestor->property("item").value<QObject *>()==pane
                        &&ancestor->property("status").isValid())paneLoader=ancestor;
                    if(paneLoader&&ancestor->property("modelData").toString()==QStringLiteral("关于 Swirl")
                        &&ancestor->property("selected").toBool())shell=ancestor;
                }
                const qreal viewportHeight=pane?pane->property("viewportHeight").toReal():0;
                const bool compact=viewportHeight>0&&viewportHeight<aboutObservation.value("compactBoundary").toDouble();
                const qreal expectedSize=aboutObservation.value(compact?"compactSize":"regularSize").toDouble();
                const bool paneReady=paneLoader&&paneLoader->property("active").toBool()
                    &&paneLoader->property("status").toInt()==aboutObservation.value("loaderReady").toInt();
                const bool imageReady=brand&&brand->property("status").toInt()==aboutObservation.value("imageReady").toInt();
                const auto source=brand?brand->property("source").toUrl().toString():QString();
                const QRectF brandRect=brand?brand->mapRectToScene(QRectF(0,0,brand->width(),brand->height())):QRectF();
                QRectF visibleRect=brandRect.intersected(QRectF(0,0,window->width(),window->height()));
                qreal opacity=1;
                for(auto *ancestor=brand;ancestor;ancestor=ancestor->parentItem()){
                    opacity*=ancestor->opacity();
                    if(ancestor->clip())visibleRect=visibleRect.intersected(ancestor->mapRectToScene(QRectF(0,0,ancestor->width(),ancestor->height())));
                }
                const bool fullyVisible=brand&&brand->isVisible()&&opacity>0&&!brandRect.isEmpty()&&visibleRect==brandRect;
                const bool exactSize=brand&&mark&&expectedSize>0&&brand->width()==expectedSize&&brand->height()==expectedSize
                    &&mark->width()==expectedSize&&mark->height()==expectedSize;
                aboutObservation.insert("samePage",samePage);
                aboutObservation.insert("pageInMainWindow",page&&page->window()==window);
                aboutObservation.insert("paneFound",pane!=nullptr);aboutObservation.insert("paneReady",paneReady);
                aboutObservation.insert("activeAboutShell",shell&&shell->property("ready").toBool()&&shell->isVisible());
                aboutObservation.insert("viewportHeight",viewportHeight);aboutObservation.insert("expectedCompact",compact);
                aboutObservation.insert("actualCompact",pane&&pane->property("compact").toBool());aboutObservation.insert("expectedSize",expectedSize);
                aboutObservation.insert("brandWidth",brand?brand->width():-1);aboutObservation.insert("brandHeight",brand?brand->height():-1);
                aboutObservation.insert("markWidth",mark?mark->width():-1);aboutObservation.insert("markHeight",mark?mark->height():-1);
                aboutObservation.insert("imageStatus",brand?brand->property("status").toInt():-1);aboutObservation.insert("source",source);
                aboutObservation.insert("brandInMainWindow",brand&&brand->window()==window);aboutObservation.insert("fullyVisible",fullyVisible);
                aboutObservation.insert("effectiveOpacity",opacity);
                return samePage&&page->window()==window&&aboutObservation.value("route").toString()=="settings"
                    &&aboutObservation.value("activeRoute").toString()=="settings"
                    &&aboutObservation.value("loaderStatus").toInt()==aboutObservation.value("loaderReady").toInt()
                    &&!aboutObservation.value("moving").toBool()&&!aboutObservation.value("pending").toBool()&&!aboutObservation.value("preparing").toBool()
                    &&aboutObservation.value("registry").toInt()==0&&aboutObservation.value("section").toString()==QStringLiteral("关于 Swirl")
                    &&aboutObservation.value("sectionReady").toBool()&&paneReady&&shell&&shell->property("ready").toBool()&&shell->isVisible()
                    &&pane->property("compact").toBool()==compact&&brand&&brand->window()==window&&imageReady
                    &&source==aboutObservation.value("expectedSource").toString()&&exactSize&&fullyVisible;
            });
            aboutObservation.insert("waitMs",aboutWait.elapsed());
            qInfo().noquote()<<"ABOUT_BRAND_GEOMETRY"<<QJsonDocument(aboutObservation).toJson(QJsonDocument::Compact);
            check(aboutBrandReady,"About retains the enlarged brand mark inside the settings page");
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
