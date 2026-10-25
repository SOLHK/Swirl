#include "MotionChecks.h"
#include "app/MotionPolicy.h"
#include <QQuickWindow>
#include <QQuickItem>
#include <QQuickItemGrabResult>
#include <QQmlExpression>
#include <QQmlContext>
#include <QQmlComponent>
#include "engine/SystemProxySession.h"
#include <memory>
#include <QTest>
#include <QSignalSpy>
#include <QDir>
#include <QImage>
#include <QJsonArray>
#include <QJsonObject>
#include <QJsonDocument>
#include <QFile>
#include <QDebug>
#include <QElapsedTimer>
#include <QEventLoop>
#include <QTimer>
#include <QSGRendererInterface>
#include <QScreen>
#include <QWheelEvent>
#include <algorithm>
#include <functional>
#include <QMutex>
#include <QMutexLocker>
#include <QPointer>
#include <QThread>
#include <QPainter>
#include <QQmlEngine>
#ifdef Q_OS_WIN
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <psapi.h>
#endif

int runViewportChecks(QQuickWindow *window,const QString &directory) {
    QDir().mkpath(directory);QJsonArray checks;int failures=0;
    auto eval=[&](const QString &code){QQmlExpression e(qmlContext(window),window,code);return e.evaluate();};
    eval("Theme.reduceMotion=true;Theme.transparency=false");
    window->setProperty("swirlViewportTest",true);
    const auto dpr=window->devicePixelRatio();
    for(const auto pixels:{QSize(1920,1080),QSize(2560,1440),QSize(3840,2160)}) {
        window->resize(qRound(pixels.width()/dpr),qRound(pixels.height()/dpr));
        for(const auto theme:{QString("Light"),QString("Dark")}) {
            eval("Theme.mode='"+theme+"'");
            for(const auto route:{QString("featurehub"),QString("overview"),QString("subscriptions")}) {
                eval("AppState.navigate('"+route+"')");QTest::qWait(180);window->update();QTest::qWait(80);
                const auto shot=window->grabWindow();
                const auto name=QString("%1-%2-%3.png").arg(pixels.width()).arg(theme.toLower(),route);
                const bool valid=!shot.isNull() && qAbs(shot.width()-pixels.width())<=2 && qAbs(shot.height()-pixels.height())<=2 && shot.save(directory+"/"+name) && eval("pageLoader.item!==null").toBool();
                checks.append(QJsonObject{{"file",name},{"valid",valid},{"physicalWidth",shot.width()},{"physicalHeight",shot.height()},{"dpr",dpr}});
                if(!valid)++failures;
            }
        }
    }
    QFile report(directory+"/viewports.json");if(!report.open(QIODevice::WriteOnly))return 2;report.write(QJsonDocument(QJsonObject{{"checks",checks},{"failures",failures},{"note","GPU UI render at requested physical viewport sizes; OS desktop resolution was not changed"}}).toJson());
    qInfo()<<"VIEWPORT_CHECKS"<<checks.size()<<"failures"<<failures<<"DPR"<<dpr;
    return failures?1:0;
}

int runMotionDemo(QQuickWindow *window,const QString &directory) {
    QDir().mkpath(directory);
    const auto eval=[&](const QString &code){QQmlExpression e(qmlContext(window),window,code);e.evaluate();};
    std::function<QQuickItem *(QQuickItem *,const QString &)> find;
    find=[&](QQuickItem *root,const QString &name)->QQuickItem *{if(root->objectName()==name)return root;for(auto *child:root->childItems())if(auto *match=find(child,name))return match;return nullptr;};
    const auto point=[&](QQuickWindow *owner,const QString &name){auto *control=find(owner->contentItem(),name);return control?control->mapToScene(QPointF(control->width()/2,control->height()/2)).toPoint():QPoint(-10,-10);};
    window->resize(1100,860);window->requestActivate();
    eval("Theme.reduceMotion=false;Theme.transparency=false;Theme.mode='Light';AppState.navigate('featurehub')");
    QTest::qWait(450);
    int failures=0;
    for(int frame=0;frame<80;++frame) {
        if(frame==0)QTest::mouseMove(window,point(window,"settings-subscriptions"));
        if(frame==5)QTest::mousePress(window,Qt::LeftButton,Qt::NoModifier,point(window,"settings-subscriptions"));
        if(frame==8)QTest::mouseRelease(window,Qt::LeftButton,Qt::NoModifier,point(window,"settings-subscriptions"));
        if(frame==25)QTest::mousePress(window,Qt::LeftButton,Qt::NoModifier,point(window,"addSubscription"));
        if(frame==28)QTest::mouseRelease(window,Qt::LeftButton,Qt::NoModifier,point(window,"addSubscription"));
        if(frame==48)QTest::keyClick(window,Qt::Key_Escape);
        if(frame==60)QTest::keyClick(window,Qt::Key_Escape);
        if(frame==65)QTest::mouseClick(window,Qt::LeftButton,Qt::NoModifier,point(window,"nav-overview"));
        QTest::qWait(40);
        auto image=window->grabWindow();
        if(!image.scaledToWidth(825,Qt::SmoothTransformation).save(directory+QString("/%1.png").arg(frame,3,10,QChar('0'))))++failures;
    }
    return failures?1:0;
}

int runMotionVisualChecks(QQuickWindow *window, const QString &directory) {
    QDir().mkpath(directory);
    auto eval=[&](const QString &code) {
        QQmlExpression e(qmlContext(window),window,code);
        auto result=e.evaluate();
        if(e.hasError())qWarning()<<e.error();
        return result;
    };
    eval("Theme.reduceMotion=true; Theme.transparency=false; AppState.toast='' ");
    const auto pages=eval("AppState.allPageIds").toStringList();
    QStringList routes=pages;
    if(routes.isEmpty()) {
        const auto array=eval("JSON.stringify(AppState.allPageIds)").toString();
        for(const auto &v:QJsonDocument::fromJson(array.toUtf8()).array())routes<<v.toString();
    }
    routes.removeDuplicates();
    QJsonArray captures;
    int errors=0;
    for(const auto &size:{QSize(1100,760),QSize(800,600)}) {
      window->resize(size);
      for(const auto &theme:{QString("Light"),QString("Dark")}) {
        eval("Theme.mode='"+theme+"'");
        for(const auto &route:routes) {
            // Compare fresh route defaults. The original single Loader reused
            // FeatureModule/Workbench instances when consecutive routes shared
            // a Component, making old test snapshots depend on route ordering.
            eval("AppState.currentPage='external'");QTest::qWait(20);
            QTest::mouseMove(window,QPoint(-20,-20));
            eval("AppState.currentPage='"+route+"'; AppState.toast=''; AppState.recentEvents=[{time:'12:01',title:'已断开连接',tone:'neutral'},{time:'12:00',title:'连接到 新加坡 · 01 (Trojan)',tone:'accent'},{time:'12:00',title:'开始建立连接',tone:'success'},{time:'12:00',title:'订阅更新完成',tone:'success'},{time:'11:59',title:'切换到 自动选择',tone:'success'}]");
            QTest::qWait(140);
            std::function<void(QQuickItem *)> repaint=[](QQuickItem *){};
            repaint=[&](QQuickItem *item) {
                if(item->metaObject()->indexOfMethod("requestPaint()")>=0)QMetaObject::invokeMethod(item,"requestPaint");
                for(auto *child:item->childItems())repaint(child);
            };
            repaint(window->contentItem());
            window->update(); QTest::qWait(30);
            QImage image=window->grabWindow();
            if(image.isNull()) {
                auto grab=window->contentItem()->grabToImage();
                if(grab) {
                    QSignalSpy ready(grab.data(),&QQuickItemGrabResult::ready);
                    window->update(); ready.wait(2000); image=grab->image();
                }
            }
            const auto name=theme.toLower()+"-"+QString::number(size.width())+"-"+route+".png";
            const bool saved=!image.isNull()&&image.save(directory+"/"+name);
            if(!saved)++errors;
            captures<<QJsonObject{{"file",name},{"saved",saved},{"width",image.width()},{"height",image.height()}};
        }
      }
    }
    QFile file(directory+"/manifest.json");if(!file.open(QIODevice::WriteOnly))return 1;file.write(QJsonDocument(captures).toJson());
    qInfo()<<"MOTION_VISUAL_CAPTURES"<<captures.size()<<"errors"<<errors;
    return errors?1:0;
}
#include "ScrollBench.h"
#include "SixAChecks.h"
int runMotionChecks(QQuickWindow *window, const QString &output) {
    if(qEnvironmentVariableIsSet("SWIRL_U2_CHECKS")) {
        extern int runU2Checks(QQuickWindow *, const QString &);
        return runU2Checks(window,output);
    }
    if(qEnvironmentVariableIsSet("SWIRL_LIQUID_GLASS_CHECKS")) {
        extern int runLiquidGlassChecks(QQuickWindow *, const QString &);
        return runLiquidGlassChecks(window,output);
    }
    if(qEnvironmentVariableIsSet("SWIRL_6A_CHECKS"))return runSixAChecks(window,output);
    if(qEnvironmentVariableIsSet("SWIRL_RECORD_INTERACTIONS"))return recordInteractionSequence(window,output);
    if(qEnvironmentVariableIsSet("SWIRL_SCROLL_BENCH"))return runScrollBench(window,output);
    // Use the application's event dispatcher for timing. QTest::qWait polls
    // with sleeps, which can quantize Windows samples to 15.6 ms and prevent
    // the animation driver from receiving native high-refresh frame events.
    auto wait=[](int milliseconds) {
        QEventLoop loop;QTimer timer;timer.setTimerType(Qt::PreciseTimer);
        timer.setSingleShot(true);QObject::connect(&timer,&QTimer::timeout,&loop,&QEventLoop::quit);
        timer.start(milliseconds);loop.exec();
    };
    QJsonArray checks;
    int failures=0;
    auto check=[&](const QString &name,bool passed) {
        checks<<QJsonObject{{"name",name},{"passed",passed}};
        if(!passed)++failures;
        qInfo()<<"MOTION_CHECK"<<name<<passed;
    };
    auto eval=[&](const QString &code) {
        QQmlExpression e(qmlContext(window),window,code);
        auto value=e.evaluate();
        if(e.hasError()){qWarning()<<e.error();check("expression: "+e.error().toString(),false);}
        return value;
    };
    auto *host=window->findChild<QQuickItem *>("pageLoader");
    if(!host)return 1;
    auto *policy=qobject_cast<MotionPolicy *>(qmlContext(window)->contextProperty("motionPolicy").value<QObject *>());
    check("motion-policy-present",policy!=nullptr);
    if(!policy)return 1;
    const bool nativeSystemReducedMotion=policy->systemReducedMotion();
    // CI may legitimately disable client animations. Exercise the animated
    // branch deterministically in this test process, then check both reduced
    // paths independently. The production executable has no override API.
    policy->setSystemReducedMotionOverrideForTest(0);
    struct RestoreSystemMotionPolicy {
        MotionPolicy *policy;
        ~RestoreSystemMotionPolicy(){policy->setSystemReducedMotionOverrideForTest(-1);}
    } restoreSystemMotionPolicy{policy};
    auto item=[&] {return qvariant_cast<QObject *>(host->property("item"));};
    std::function<QQuickItem *(QQuickItem *,const QString &)> findVisual;
    findVisual=[&](QQuickItem *root,const QString &name)->QQuickItem * {
        if(!root)return nullptr;
        if(root->objectName()==name)return root;
        for(auto *child:root->childItems())if(auto *found=findVisual(child,name))return found;
        return nullptr;
    };
    auto waitOpen=[&](QObject *popup) {
        QElapsedTimer timer;timer.start();
        while(!popup->property("opened").toBool()&&timer.elapsed()<1800)wait(20);
    };
    auto settle=[&](int timeout=2500) {
        QElapsedTimer timer;timer.start();
        do {wait(20);} while((host->property("moving").toBool()||host->property("pendingGrab").toBool())&&timer.elapsed()<timeout);
        return !host->property("moving").toBool()&&!host->property("pendingGrab").toBool();
    };
    auto route=[&](const QString &id) {eval("AppState.navigate('"+id+"')");wait(25);return settle();};
    auto memory=[]()->qint64 {
#ifdef Q_OS_WIN
        PROCESS_MEMORY_COUNTERS counters{};
        if(GetProcessMemoryInfo(GetCurrentProcess(),&counters,sizeof(counters)))return qint64(counters.WorkingSetSize);
#endif
        return 0;
    };
    window->resize(1100,760);
    eval("Theme.reduceMotion=false;Theme.transparency=false;Theme.mode='Light';AppState.toast=''");
    wait(120);
    const bool reduced=eval("SwirlMotion.reduced").toBool();
    check("animated-test-policy-is-active",!reduced);
    check("initial-page-present",item()!=nullptr);
    auto *rewriteLoader=window->findChild<QObject *>("rewriteRulesLoader");
    check("rewrite-editor-is-lazy-at-startup",rewriteLoader&&!rewriteLoader->property("active").toBool()&&!qvariant_cast<QObject *>(rewriteLoader->property("item")));
    eval("window.openRewriteEditor('redirect','HTTP redirect rules')");
    QTest::keyClick(window,Qt::Key_Escape);
    const bool rewriteReady=rewriteLoader&&QTest::qWaitFor([&]{return rewriteLoader->property("status").toInt()==1;},5000);
    auto *rewriteEditor=rewriteReady?qvariant_cast<QObject *>(rewriteLoader->property("item")):nullptr;
    check("escape-cancels-pending-rewrite-opening",rewriteEditor&&QTest::qWaitFor([&]{return !rewriteEditor->property("visible").toBool();},2500)&&!rewriteLoader->property("wantOpen").toBool());
    eval("window.openRewriteEditor('header','HTTP header rules');window.openRewriteEditor('redirect','HTTP redirect rules')");
    check("rewrite-editor-opens-after-asynchronous-load",rewriteEditor&&QTest::qWaitFor([&]{return rewriteEditor->property("opened").toBool();},2500));
    check("rewrite-editor-last-request-wins",rewriteEditor&&rewriteEditor->property("kind")=="redirect"&&rewriteEditor->property("title")=="HTTP redirect rules");
    if(rewriteEditor){
        const auto previousSelection=rewriteEditor->property("chosen");
        rewriteEditor->setProperty("chosen","retained-selection-fixture");
        QMetaObject::invokeMethod(rewriteEditor,"close");
        check("rewrite-editor-releases-first-modal-grab",QTest::qWaitFor([&]{return !rewriteEditor->property("visible").toBool();},2500));
        eval("window.openRewriteEditor('redirect','HTTP redirect rules')");
        check("rewrite-editor-reuses-instance-and-local-state",qvariant_cast<QObject *>(rewriteLoader->property("item"))==rewriteEditor&&rewriteEditor->property("chosen")=="retained-selection-fixture"&&QTest::qWaitFor([&]{return rewriteEditor->property("opened").toBool();},2500));
        rewriteEditor->setProperty("chosen",previousSelection);
        QMetaObject::invokeMethod(rewriteEditor,"close");
        check("rewrite-editor-releases-reopened-modal-grab",QTest::qWaitFor([&]{return !rewriteEditor->property("visible").toBool();},2500));
    }
    QPointer<QObject> captureLoader=window->findChild<QObject *>("captureInspectorLoader");
    check("capture-inspector-is-lazy-at-startup",captureLoader&&!captureLoader->property("active").toBool()&&!qvariant_cast<QObject *>(captureLoader->property("item")));
    if(captureLoader){
        const QString captureRoute=eval("AppState.currentPage").toString();
        const int captureHistory=eval("AppState.historyIndex").toInt();
        const int dismissalsBeforeCapture=eval("dismissals.count").toInt();
        eval("window.openCaptureInspector()");
        check("capture-inspector-is-pending-before-escape",captureLoader&&captureLoader->property("status").toInt()==2&&captureLoader->property("wantOpen").toBool());
        QTest::keyClick(window,Qt::Key_Escape);
        check("capture-pending-escape-preserves-route",eval("AppState.currentPage").toString()==captureRoute&&eval("AppState.historyIndex").toInt()==captureHistory);
        check("capture-pending-escape-clears-admission",captureLoader&&!captureLoader->property("wantOpen").toBool());
        const bool captureReady=QTest::qWaitFor([&]{return captureLoader&&captureLoader->property("status").toInt()==1;},5000);
        QPointer<QObject> inspectorDialog=captureReady?qvariant_cast<QObject *>(captureLoader->property("item")):nullptr;
        check("capture-inspector-loads-asynchronously",captureReady&&inspectorDialog);
        check("capture-cancelled-load-does-not-open",inspectorDialog&&!inspectorDialog->property("visible").toBool()&&eval("dismissals.count").toInt()==dismissalsBeforeCapture);
        if(inspectorDialog){
            eval("window.openCaptureInspector()");
            check("capture-inspector-reopens-after-cancel",QTest::qWaitFor([&]{return inspectorDialog&&inspectorDialog->property("opened").toBool();},2500));
            check("capture-inspector-has-owned-modal-layer",eval("captureInspectorLoader.item.ownerWindow===window").toBool()&&eval("dismissals.count").toInt()==dismissalsBeforeCapture+1);
            auto *dialogContent=qvariant_cast<QQuickItem *>(inspectorDialog->property("contentItem"));
            std::function<QQuickItem *(QQuickItem *)> findInspectorPage;
            findInspectorPage=[&](QQuickItem *candidate)->QQuickItem *{
                if(!candidate)return nullptr;
                if(candidate->metaObject()->indexOfProperty("captureProvider")>=0
                    &&candidate->metaObject()->indexOfProperty("selectedId")>=0
                    &&candidate->metaObject()->indexOfProperty("query")>=0)return candidate;
                for(auto *child:candidate->childItems())if(auto *found=findInspectorPage(child))return found;
                return nullptr;
            };
            QPointer<QQuickItem> inspectorPage=findInspectorPage(dialogContent);
            check("capture-inspector-real-state-properties-present",inspectorPage!=nullptr);
            QVariant previousSelectedId,previousQuery;
            if(inspectorPage){
                previousSelectedId=inspectorPage->property("selectedId");previousQuery=inspectorPage->property("query");
                check("capture-inspector-state-can-be-edited",inspectorPage->setProperty("selectedId",QStringLiteral("retained-capture-session-fixture"))
                    &&inspectorPage->setProperty("query",QStringLiteral("retained capture filter")));
            }
            QMetaObject::invokeMethod(inspectorDialog,"close");
            check("capture-inspector-close-releases-modal-layer",QTest::qWaitFor([&]{return inspectorDialog&&!inspectorDialog->property("visible").toBool()&&eval("dismissals.count").toInt()==dismissalsBeforeCapture;},2500));
            eval("window.openCaptureInspector()");
            const bool reopened=QTest::qWaitFor([&]{return inspectorDialog&&inspectorDialog->property("opened").toBool();},2500);
            check("capture-inspector-retains-instance-and-state",reopened&&captureLoader&&inspectorPage
                &&qvariant_cast<QObject *>(captureLoader->property("item"))==inspectorDialog
                &&findInspectorPage(qvariant_cast<QQuickItem *>(inspectorDialog->property("contentItem")))==inspectorPage
                &&inspectorPage->property("selectedId").toString()==QStringLiteral("retained-capture-session-fixture")
                &&inspectorPage->property("query").toString()==QStringLiteral("retained capture filter"));
            if(inspectorPage){inspectorPage->setProperty("selectedId",previousSelectedId);inspectorPage->setProperty("query",previousQuery);}
            QTest::keyClick(window,Qt::Key_Escape);
            check("capture-inspector-escape-releases-reopened-modal-layer",QTest::qWaitFor([&]{return inspectorDialog&&!inspectorDialog->property("visible").toBool()&&eval("dismissals.count").toInt()==dismissalsBeforeCapture;},2500));
        }
    }
    route("featurehub");
    auto *hub=item();
    check("hub-loaded",hub!=nullptr);
    route("rules");auto *rulePage=item();auto *search=findVisual(qobject_cast<QQuickItem *>(rulePage),"rulesSearch");
    if(search)search->setProperty("text","http");route("settings");route("rules");
    check("page-instance-preserved",item()==rulePage);
    check("editable-state-preserved",search&&search->property("text").toString()=="http");
    if(search)search->setProperty("text","");
    route("dns");auto *dnsPage=item();auto *flick=findVisual(qobject_cast<QQuickItem *>(dnsPage),"motion-dns-scroll");
    if(flick)flick->setProperty("contentY",qMin(40.0,flick->property("contentHeight").toDouble()-flick->height()));
    wait(80);const double scrollBefore=flick?flick->property("contentY").toDouble():-1;
    route("settings");route("dns");
    qInfo()<<"MOTION_SCROLL"<<scrollBefore<<(flick?flick->property("contentY"):QVariant())<<(flick?flick->property("contentHeight"):QVariant())<<(flick?flick->height():-1);
    check("scroll-state-preserved",flick&&scrollBefore>0&&qAbs(flick->property("contentY").toDouble()-scrollBefore)<0.1);
    if(flick)flick->setProperty("contentY",0);
    route("proxies");
    auto *proxy=item();
    auto *dialog=proxy?proxy->findChild<QObject *>("proxyAddDialog"):nullptr;
    check("dialog-present",dialog!=nullptr);
    if(dialog) {
        QMetaObject::invokeMethod(dialog,"open");waitOpen(dialog);
        check("dialog-open",dialog->property("opened").toBool());
        QTest::keyClick(window,Qt::Key_Escape);wait(450);
        check("escape-closes-dialog",!dialog->property("visible").toBool());
        QMetaObject::invokeMethod(dialog,"open");wait(100);
        route("settings");wait(250);
        check("leaving-page-releases-modal",!dialog->property("visible").toBool());
    }
    route("gateway");
    auto *combo=findVisual(qobject_cast<QQuickItem *>(item()),"deviceSortPicker");
    auto *popup=combo?qvariant_cast<QObject *>(combo->property("popup")):nullptr;
    if(popup){const auto point=combo->mapToScene(QPointF(combo->width()/2,combo->height()/2)).toPoint();
        QTest::mouseClick(window,Qt::LeftButton,Qt::NoModifier,point);waitOpen(popup);qInfo()<<"MOTION_DROPDOWN"<<point<<combo->isEnabled()<<combo->isVisible()<<popup->property("visible")<<popup->property("opened")<<popup->property("scale")<<popup->property("opacity");check("dropdown-opens",popup->property("opened").toBool());
        QQuickWindow *popupWindow=window;for(auto *candidate:QGuiApplication::allWindows())if(candidate->isVisible()&&candidate->flags().testFlag(Qt::Popup))if(auto *quick=qobject_cast<QQuickWindow *>(candidate))popupWindow=quick;
        QTest::keyClick(popupWindow,Qt::Key_Escape);wait(400);check("dropdown-escape",!popup->property("visible").toBool());
    }else check("dropdown-present",false);
    auto *button=findVisual(window->contentItem(),"nav-overview");
    if(button) {
        const auto p=button->mapToScene(QPointF(button->width()/2,button->height()/2)).toPoint();
        for(int i=0;i<8;++i){QTest::mousePress(window,Qt::LeftButton,Qt::NoModifier,p);wait(22);QTest::mouseRelease(window,Qt::LeftButton,Qt::NoModifier,p);wait(15);}
        wait(1400);settle();
        check("rapid-button-release-restores-scale",qAbs(button->property("motionScale").toDouble()-1)<0.001);
        check("button-hit-area-unchanged",button->scale()==1);
        check("click-light-stops-after-release",button->property("clickLight").toDouble()==0);
        QTest::mouseClick(window,Qt::LeftButton,Qt::NoModifier,p);wait(60);
        auto *shader=button->findChild<QObject *>("clickLightShaderLoader");
        check("ordinary-click-has-no-light-overlay",shader==nullptr && button->property("clickLight").toDouble()==0);
        const auto beforeRoute=eval("AppState.currentPage").toString();
        QTest::mousePress(window,Qt::LeftButton,Qt::NoModifier,p);
        QTest::mouseMove(window,QPoint(window->width()-15,window->height()-15));
        QTest::mouseRelease(window,Qt::LeftButton,Qt::NoModifier,QPoint(window->width()-15,window->height()-15));wait(220);
        check("drag-away-cancels-activation",eval("AppState.currentPage").toString()==beforeRoute && !button->property("down").toBool());
        button->forceActiveFocus();QTest::keyClick(window,Qt::Key_Space);wait(250);
        check("keyboard-activation-keeps-stable-hit-area",button->scale()==1 && !button->property("down").toBool());

    } else check("navigation-button-present",false);
    auto *indicator=findVisual(window->contentItem(),"sidebarSelectionIndicator");
    check("one-sidebar-indicator-present",indicator!=nullptr);
    const QStringList sidebarRoutes={"activity","overview","processes","gateway","policies","rules","capture","tls","rewrite","featurehub"};
    for(int i=0;i<30;++i){
        auto *entry=findVisual(window->contentItem(),"nav-"+sidebarRoutes[(i%2?29-i:i)%sidebarRoutes.size()]);
        if(entry)QTest::mouseClick(window,Qt::LeftButton,Qt::NoModifier,entry->mapToScene(QPointF(entry->width()/2,entry->height()/2)).toPoint());
        wait(20);
        check("sidebar-single-owner-"+QString::number(i),indicator&&findVisual(window->contentItem(),"sidebarSelectionIndicator")==indicator);
    }
    settle();wait(300);
    check("sidebar-selection-reaches-last-click",eval("AppState.currentPage==='activity'").toBool());
    route("activity");
    auto *activity=qobject_cast<QQuickItem *>(item());
    auto *upload=findVisual(activity,"activityUpload");
    auto *activityScroll=findVisual(activity,"activityScroll");
    auto *connections=findVisual(activity,"activityConnections"),*total=findVisual(activity,"activityTotal");
    auto *diagnostic=findVisual(activity,"internetDiagnosticCard"),*trafficCard=findVisual(activity,"activityTrafficCard");
    auto *trafficFilter=findVisual(activity,"activityTrafficFilter"),*sourceFilter=findVisual(activity,"activitySourceFilter");
    auto *periodFilter=findVisual(activity,"activityPeriodFilter"),*trafficChart=findVisual(activity,"activityTrafficChart");
    check("activity-v7-two-cards-three-sections-present",activity&&activityScroll&&diagnostic&&trafficCard&&upload&&connections&&total);
    if(activity&&activityScroll&&diagnostic&&trafficCard&&upload&&connections&&total){
        const auto originalSize=window->size();
        const QSize normalSize(qRound(eval("Theme.dp(914)").toDouble()),qRound(eval("Theme.dp(672)").toDouble()));
        window->resize(normalSize);wait(250);
        const auto diagnosticAt=diagnostic->mapToItem(activity,0,0),trafficAt=trafficCard->mapToItem(activity,0,0);
        const auto uploadAt=upload->mapToItem(activity,0,0),connectionsAt=connections->mapToItem(activity,0,0),totalAt=total->mapToItem(activity,0,0);
        std::function<int(QQuickItem *)> panelCount=[&](QQuickItem *root){
            int count=root->property("independentCard").isValid()?1:0;
            for(auto *child:root->childItems())count+=panelCount(child);
            return count;
        };
        check("activity-v7-only-two-top-cards",panelCount(activity)==2&&diagnostic->isVisible()&&trafficCard->isVisible()
            &&diagnostic->parentItem()==trafficCard->parentItem()&&qAbs(diagnosticAt.y()-trafficAt.y())<2
            &&qAbs(diagnostic->height()-trafficCard->height())<2&&trafficAt.x()>=diagnosticAt.x()+diagnostic->width()
            &&diagnostic->width()/trafficCard->width()>0.8&&diagnostic->width()/trafficCard->width()<1.0);
        const auto unboxed=[](QQuickItem *section){return !section->property("color").isValid()&&!section->property("background").isValid();};
        check("activity-v7-three-unboxed-sections",upload->parentItem()==connections->parentItem()&&connections->parentItem()==total->parentItem()
            &&unboxed(upload)&&unboxed(connections)&&unboxed(total)
            &&uploadAt.y()>diagnosticAt.y()+diagnostic->height()&&qAbs(uploadAt.y()-connectionsAt.y())<2&&qAbs(uploadAt.y()-totalAt.y())<2
            &&uploadAt.x()+upload->width()<connectionsAt.x()&&connectionsAt.x()+connections->width()<totalAt.x());
        const double contentHeight=activityScroll->property("contentHeight").toDouble();
        const double sectionBottom=total->mapToItem(activityScroll,0,total->height()).y();
        qInfo()<<"ACTIVITY_V7_NORMAL_GEOMETRY"<<window->size()<<activityScroll->size()<<contentHeight
               <<diagnostic->size()<<trafficCard->size()<<upload->size()<<connections->size()<<total->size();
        check("activity-v7-normal-914x672-no-scroll",window->size()==normalSize&&eval("pageLoader.item.wide").toBool()
            &&contentHeight<=activityScroll->height()+1&&qAbs(activityScroll->property("contentY").toDouble())<1
            &&sectionBottom<=activityScroll->height()+1);
        const auto visibleControl=[&](QQuickItem *control){
            return control&&control->isVisible()&&control->isEnabled()&&control->width()>0&&control->height()>0
                &&control->mapToItem(activityScroll,0,0).y()>=-1
                &&control->mapToItem(activityScroll,0,control->height()).y()<=activityScroll->height()+1;
        };
        check("activity-v7-filters-visible",visibleControl(trafficFilter)&&visibleControl(sourceFilter)&&visibleControl(periodFilter)&&trafficChart&&trafficChart->isVisible());
        const auto clickSegment=[&](QQuickItem *control,int index,int count){
            const auto point=control->mapToScene(QPointF(control->width()*(index+0.5)/count,control->height()/2)).toPoint();
            QTest::mouseClick(window,Qt::LeftButton,Qt::NoModifier,point);wait(100);
        };
        if(visibleControl(trafficFilter)&&trafficChart){
            clickSegment(trafficFilter,1,2);
            check("activity-v7-proxy-filter-switches-chart",eval("pageLoader.item.trafficKind===1").toBool()
                &&trafficFilter->property("currentIndex").toInt()==1&&trafficChart->property("proxyOnly").toBool());
            clickSegment(trafficFilter,0,2);
            check("activity-v7-all-filter-restores-chart",eval("pageLoader.item.trafficKind===0").toBool()
                &&trafficFilter->property("currentIndex").toInt()==0&&!trafficChart->property("proxyOnly").toBool());
        }
        if(visibleControl(sourceFilter)){
            clickSegment(sourceFilter,1,3);
            check("activity-v7-domain-filter-switches-source",eval("pageLoader.item.rankingKind===1").toBool()&&sourceFilter->property("currentIndex").toInt()==1);
            clickSegment(sourceFilter,2,3);
            check("activity-v7-strategy-filter-switches-source",eval("pageLoader.item.rankingKind===2").toBool()&&sourceFilter->property("currentIndex").toInt()==2);
            clickSegment(sourceFilter,0,3);
            check("activity-v7-source-filter-restores-processes",eval("pageLoader.item.rankingKind===0").toBool()&&sourceFilter->property("currentIndex").toInt()==0);
        }
        if(visibleControl(periodFilter)){
            clickSegment(periodFilter,1,2);
            check("activity-v7-month-filter-switches-period",eval("pageLoader.item.period===1").toBool()&&periodFilter->property("currentIndex").toInt()==1);
            clickSegment(periodFilter,0,2);
            check("activity-v7-today-filter-restores-period",eval("pageLoader.item.period===0").toBool()&&periodFilter->property("currentIndex").toInt()==0);
        }
        window->resize(originalSize);wait(250);
    }
    const double activityScrollBefore=activityScroll?qMax(0.0,qMin(20.0,activityScroll->property("contentHeight").toDouble()-activityScroll->height())):0.0;
    if(activityScroll)activityScroll->setProperty("contentY",activityScrollBefore);
    if(upload){
        qmlEngine(window)->rootContext()->setContextProperty("motionTestOrigin",upload);
        eval("SwirlMotion.navigateFrom(motionTestOrigin,'traffic','uploadRate')");
        QElapsedTimer metricReady;metricReady.start();
        while(host->property("sourceSurface").value<QObject *>()!=upload&&metricReady.elapsed()<1500)wait(5);
        wait(35);
        check("metric-shares-matching-surface",host->property("heroData").isValid() && host->property("sourceSurface").value<QObject *>()==upload);
        const auto partial=host->property("progress").toDouble();
        eval("SwirlMotion.returnToHub(null)");wait(25);
        check("immediate-return-reverses-live-transition",item()==activity && partial>0 && partial<1 && host->property("moving").toBool());
        eval("SwirlMotion.navigateFrom(motionTestOrigin,'traffic','uploadRate')");wait(25);
        check("reopen-keeps-latest-route",eval("AppState.currentPage==='traffic'").toBool());
        settle();eval("SwirlMotion.returnToHub(null)");wait(25);settle();
        check("activity-return-preserves-scroll",item()==activity&&activityScroll&&qAbs(activityScroll->property("contentY").toDouble()-activityScrollBefore)<1);
        check("shared-surfaces-restored",!upload->property("surfaceHidden").toBool()&&host->property("sourceSurface").value<QObject *>()==nullptr);
    }
    route("activity");
    auto *capsule=findVisual(window->contentItem(),"proxyCapsule");
    if(capsule){
        const auto hostProxyBefore=SystemProxySession::snapshot();
        QQmlComponent component(qmlEngine(window));
        component.setData(R"(
            import QtQuick
            QtObject {
                property bool busy: false
                property bool systemProxyBusy: false
                property string routingError: ""
                property string error: ""
                property int calls: 0
                property bool reject: false
                property QtObject systemProxy: QtObject {
                    property bool systemEnabled: false
                    property string stateReadError: ""
                    property string error: ""
                }
                function toggleSystemProxy() {
                    calls++
                    if(reject) { routingError="test-operation-failed"; return }
                    systemProxy.systemEnabled=!systemProxy.systemEnabled
                }
            }
        )",QUrl());
        std::unique_ptr<QObject> fake(component.create());
        check("proxy-toggle-test-controller-created",fake!=nullptr);
        if(fake){
            const auto originalController=capsule->property("controller");
            check("proxy-toggle-test-controller-bound",capsule->setProperty("controller",QVariant::fromValue(fake.get())));
            const auto clickProxy=[&]{QTest::mouseClick(window,Qt::LeftButton,Qt::NoModifier,capsule->mapToScene(QPointF(capsule->width()/2,capsule->height()/2)).toPoint());wait(30);};
            check("proxy-off-offers-enable",capsule->property("label").toString()==QStringLiteral("开启系统代理"));
            clickProxy();
            check("proxy-enable-click-dispatches-once",fake->property("calls").toInt()==1);
            check("proxy-on-offers-disable",capsule->property("label").toString()==QStringLiteral("关闭系统代理"));
            check("proxy-enable-stays-on-activity",eval("AppState.currentPage==='activity'").toBool());
            clickProxy();
            check("proxy-disable-click-dispatches-once",fake->property("calls").toInt()==2);
            check("proxy-disabled-state-updates-action",capsule->property("label").toString()==QStringLiteral("开启系统代理"));
            fake->setProperty("systemProxyBusy",true);clickProxy();
            check("proxy-pending-cannot-repeat-request",fake->property("calls").toInt()==2&&!capsule->isEnabled());
            fake->setProperty("systemProxyBusy",false);
            auto *fakeProxy=fake->property("systemProxy").value<QObject *>();
            check("proxy-toggle-test-state-present",fakeProxy!=nullptr);
            if(fakeProxy)fakeProxy->setProperty("error",QStringLiteral("stale-owner-error"));
            fake->setProperty("reject",true);clickProxy();
            check("proxy-failure-keeps-observed-state",fake->property("calls").toInt()==3&&capsule->property("label").toString()==QStringLiteral("开启系统代理"));
            check("proxy-failure-visible",capsule->property("tone").toString()=="warning"&&capsule->property("detail").toString()=="test-operation-failed");
            check("proxy-disable-and-error-stay-on-activity",eval("AppState.currentPage==='activity'").toBool());
            check("proxy-toggle-controller-restored",capsule->setProperty("controller",originalController));
        }
        check("proxy-button-test-does-not-mutate-host-settings",SystemProxySession::snapshot()==hostProxyBefore);
    }
    QList<double> intervals;QList<double> warmIntervals;
    QJsonArray frameTimeline;
    QJsonObject frameProbe;
    const QStringList stress={"overview","settings","proxies","featurehub","capture","connections","rules","logs"};
    {
        struct FrameContext {
            QString route,activeRoute,phase,point;
            qint64 timestampNs=0;
            quint64 revision=0;
            bool moving=false,pending=false,valid=false;
        };
        struct FrameSample {
            qint64 timestampNs=0;
            double intervalMs=0;
            bool hasInterval=false,warm=false;
            FrameContext before,after;
        };
        constexpr qsizetype frameCapacity=20000;
        struct FrameProbeState {
            QMutex mutex;
            QElapsedTimer clock;
            QList<double> intervals,warmIntervals;
            QList<FrameSample> samples;
            FrameContext context,previousContext;
            bool warmPhase=false,measuring=true;
            qint64 last=0,callbackCount=0,droppedSamples=0,snapshotCount=0;
            qint64 callbackTotalNs=0,callbackMaxNs=0,snapshotTotalNs=0,snapshotMaxNs=0,maxSnapshotAgeNs=0;
        };
        const auto state=std::make_shared<FrameProbeState>();
        state->samples.reserve(frameCapacity);state->clock.start();
        QString phase=QStringLiteral("rapid-switch");
        // Context ownership keeps queued GUI callbacks from outliving the
        // stack state. Only this GUI callback reads QML; the render callback
        // consumes native state. An in-flight DirectConnection retains that
        // state even if disconnect returns before the callback has finished.
        auto captureContext=[state,host,window,&phase](const QString &point){
            Q_ASSERT(QThread::currentThread()==window->thread());
            const qint64 started=state->clock.nsecsElapsed();
            {QMutexLocker lock(&state->mutex);if(!state->measuring)return;}
            FrameContext next;
            next.route=host->property("routeKey").toString();
            if(auto *active=qvariant_cast<QObject *>(host->property("activeLoader")))next.activeRoute=active->property("routeId").toString();
            next.moving=host->property("moving").toBool();next.pending=host->property("pendingGrab").toBool();
            next.phase=phase;next.point=point;next.valid=true;next.timestampNs=state->clock.nsecsElapsed();
            QMutexLocker lock(&state->mutex);
            if(!state->measuring)return;
            next.revision=++state->snapshotCount;state->context=next;
            const qint64 cost=state->clock.nsecsElapsed()-started;
            state->snapshotTotalNs+=cost;state->snapshotMaxNs=qMax(state->snapshotMaxNs,cost);
        };
        QObject probeContext;
        captureContext(QStringLiteral("phase-start"));
        const auto beforeFrame=QObject::connect(window,&QQuickWindow::afterAnimating,&probeContext,[&]{captureContext(QStringLiteral("afterAnimating"));});
        const auto afterFrame=QObject::connect(window,&QQuickWindow::frameSwapped,&probeContext,[&]{captureContext(QStringLiteral("after-frame-queued"));},Qt::QueuedConnection);
        const auto connection=QObject::connect(window,&QQuickWindow::frameSwapped,&probeContext,[state] {
            const qint64 now=state->clock.nsecsElapsed();
            QMutexLocker lock(&state->mutex);
            if(!state->measuring)return;
            const double delta=double(now-state->last)/1000000.0;
            if(state->last){state->intervals<<delta;if(state->warmPhase)state->warmIntervals<<delta;}
            if(state->samples.size()<frameCapacity)state->samples.append({now,delta,state->last!=0,state->warmPhase,state->previousContext,state->context});
            else ++state->droppedSamples;
            state->previousContext=state->context;state->last=now;++state->callbackCount;
            if(state->context.valid)state->maxSnapshotAgeNs=qMax(state->maxSnapshotAgeNs,now-state->context.timestampNs);
            const qint64 cost=state->clock.nsecsElapsed()-now;
            state->callbackTotalNs+=cost;state->callbackMaxNs=qMax(state->callbackMaxNs,cost);
        },Qt::DirectConnection);
        for(int i=0;i<40;++i) {
            eval("AppState.navigate('"+stress[i%stress.size()]+"')");
            captureContext(QStringLiteral("route-request"));
            wait(23);
            if(i%7==0){window->resize(900+i*2,qMax(window->minimumHeight(),650+i));captureContext(QStringLiteral("resize-request"));}
            check("rapid-switch-has-live-page-"+QString::number(i),item()!=nullptr);
            check("rapid-switch-retains-visible-content-"+QString::number(i),eval("Object.keys(pageLoader.pages).reduce((sum,key)=>sum+(pageLoader.pages[key].visible?pageLoader.pages[key].opacity:0),0)>0.99").toBool());
        }
        check("rapid-switch-settles",settle(3500));
        check("latest-route-wins",qvariant_cast<QObject *>(host->property("activeLoader"))->property("routeId").toString()==stress[39%stress.size()]);
        // Preserve the original aggregate's warm reset and full interval set.
        window->resize(1100,760);
        phase=QStringLiteral("warm-route");
        {QMutexLocker lock(&state->mutex);state->warmPhase=true;state->last=0;state->previousContext=FrameContext{};}
        captureContext(QStringLiteral("phase-start"));
        for(int i=0;i<8;++i)route(stress[i]);
        QList<FrameSample> samples;
        {
            QMutexLocker lock(&state->mutex);
            state->measuring=false;
            intervals=state->intervals;warmIntervals=state->warmIntervals;samples=state->samples;
            frameProbe=QJsonObject{{"schema",1},{"capacity",qint64(frameCapacity)},{"samples",qint64(samples.size())},
                {"droppedSamples",state->droppedSamples},{"frameCallbacks",state->callbackCount},{"guiSnapshots",state->snapshotCount},
                {"callbackMeasuredTotalMs",double(state->callbackTotalNs)/1e6},{"callbackMeasuredMaxMs",double(state->callbackMaxNs)/1e6},
                {"guiSnapshotMeasuredTotalMs",double(state->snapshotTotalNs)/1e6},{"guiSnapshotMeasuredMaxMs",double(state->snapshotMaxNs)/1e6},
                {"maxSnapshotAgeMs",double(state->maxSnapshotAgeNs)/1e6},{"renderCallbackReadsQml",false},
                {"clockDomain","QElapsedTimer nanoseconds since stress probe start; not synchronized to QML trace clock"},
                {"attributionIsExact",false},{"limits",QJsonArray{
                    "Moving/pending are GUI snapshots around presentation, not complete activity histories between frames.",
                    "Inactive endpoints can hide work between snapshots; active endpoints do not prove every millisecond was animated.",
                    "Queued post-frame snapshots can lag; snapshot timestamps and revisions are retained.",
                    "Probe costs include snapshot reads, copies, list appends and mutex waits, but exclude Qt dispatch and final unlock.",
                    "The additional probe changes test overhead; compare matching instrumentation and workloads.",
                    "All original aggregate intervals, including long or inactive gaps, remain in performance totals."}}};
        }
        QObject::disconnect(connection);QObject::disconnect(beforeFrame);QObject::disconnect(afterFrame);
        const auto contextJson=[](const FrameContext &value){return QJsonObject{
            {"valid",value.valid},{"snapshotNs",value.timestampNs},{"revision",qint64(value.revision)},
            {"route",value.route},{"activeRoute",value.activeRoute},{"phase",value.phase},
            {"snapshotPoint",value.point},{"moving",value.moving},{"pending",value.pending}};};
        // JSON allocation and sorting occur after the timed probe is stopped.
        for(const auto &sample:samples){
            const bool beforeActive=sample.before.moving||sample.before.pending;
            const bool afterActive=sample.after.moving||sample.after.pending;
            const QString attribution=!sample.hasInterval||!sample.before.valid||!sample.after.valid?QStringLiteral("unclassified")
                :beforeActive&&afterActive?QStringLiteral("active-at-both-snapshots")
                :!beforeActive&&!afterActive?QStringLiteral("inactive-at-both-snapshots"):QStringLiteral("transition-boundary");
            frameTimeline.append(QJsonObject{{"timestampNs",sample.timestampNs},
                {"intervalMs",sample.hasInterval?QJsonValue(sample.intervalMs):QJsonValue(QJsonValue::Null)},
                {"warm",sample.warm},{"attribution",attribution},
                {"before",contextJson(sample.before)},{"after",contextJson(sample.after)}});
        }
    }
    // Warm the readback/driver pool at the same dimensions before checking
    // repeated growth. The earlier stress deliberately used varied sizes.
    for(int i=0;i<40;++i){eval("AppState.navigate('"+stress[i%stress.size()]+"')");wait(12);}
    settle(3500);
    qmlEngine(window)->collectGarbage();wait(150);
    auto before=memory();const int count=host->property("cachedPageCount").toInt();
    for(int i=0;i<40;++i){eval("AppState.navigate('"+stress[i%stress.size()]+"')");wait(12);}
    settle(3500);
    check("revisits-do-not-create-loaders",count>=stress.size() && host->property("cachedPageCount").toInt()==count);
    qmlEngine(window)->collectGarbage();wait(150);
    const auto growth=memory()-before;
    check("all-transient-grabs-released",eval("motionPolicy.activeGrabCount===0").toBool());
    check("revisit-memory-growth-below-24MiB",growth<24*1024*1024);
    route("featurehub");
    auto *card=findVisual(qobject_cast<QQuickItem *>(item()),"settings-dns");check("settings-tile-present",card!=nullptr);
    if(card){QTest::mouseClick(window,Qt::LeftButton,Qt::NoModifier,card->mapToScene(QPointF(card->width()/2,card->height()/2)).toPoint());settle(2000);
        check("settings-tile-opens-main-route",eval("AppState.currentPage==='dns' && pageLoader.item.Window.window===window").toBool());
        eval("window.closeSettings()");settle(2000);
        check("main-route-preserves-hub",item()==hub);window->requestActivate();
    }
    route("feature-system");
    auto *module=item();
    if(module) {
        QVariantList rows{QVariantMap{{"name","A"},{"value","1"}},QVariantMap{{"name","B"},{"value","2"}}};
        module->setProperty("records",rows);module->setProperty("tab",1);wait(250);
        auto *list=findVisual(qobject_cast<QQuickItem *>(module),"motion-record-list");
        check("incremental-record-insert",list && list->property("count").toInt()==2);
        std::reverse(rows.begin(),rows.end());module->setProperty("records",rows);wait(250);
        QQmlExpression order(qmlContext(list),list,"model.get(0).entry.name");
        check("incremental-record-reorder",list && list->property("count").toInt()==2 && order.evaluate().toString()=="B");
        rows.removeLast();module->setProperty("records",rows);wait(250);
        check("incremental-record-remove",list && list->property("count").toInt()==1);
    }
    eval("Theme.reduceMotion=true");
    route("settings");
    check("reduced-motion-immediate",!host->property("moving").toBool()&&host->property("progress").toDouble()==1);
    check("reduced-motion-no-global-transition",!eval("SwirlMotion.transitioning").toBool());
    eval("Theme.reduceMotion=false");
    policy->setSystemReducedMotionOverrideForTest(1);
    eval("Theme.followSystemMotion=false");
    check("application-full-motion-remains-enabled-with-reduced-system-policy",!eval("SwirlMotion.reduced").toBool()&&eval("SwirlMotion.expandDuration>0").toBool());
    eval("Theme.followSystemMotion=true");
    route("rules");
    check("system-reduced-motion-immediate",eval("SwirlMotion.reduced").toBool()&&!host->property("moving").toBool()&&host->property("progress").toDouble()==1);
    check("system-reduced-motion-no-global-transition",!eval("SwirlMotion.transitioning").toBool());
    eval("Theme.followSystemMotion=false");
    policy->setSystemReducedMotionOverrideForTest(0);
    eval("Theme.reduceMotion=true");
    check("application-reduced-motion-wins-over-animated-system-policy",eval("SwirlMotion.reduced").toBool());
    int idleFrames=0;
    auto idleConnection=QObject::connect(window,&QQuickWindow::frameSwapped,window,[&]{++idleFrames;});
    wait(650);QObject::disconnect(idleConnection);
    check("idle-no-animation-loop",idleFrames<=4);
    policy->setSystemReducedMotionOverrideForTest(-1);
    const bool systemPolicyRestored=policy->systemReducedMotion()==nativeSystemReducedMotion;
    check("system-motion-policy-restored",systemPolicyRestored);
    std::sort(intervals.begin(),intervals.end());
    std::sort(warmIntervals.begin(),warmIntervals.end());
    QJsonObject performance{{"renderer",int(window->rendererInterface()->graphicsApi())},
        {"qt",qVersion()},{"dpr",window->devicePixelRatio()},
        {"refreshHz",window->screen()?window->screen()->refreshRate():0},
        {"systemReducedMotion",nativeSystemReducedMotion},{"testSystemReducedMotionOverride",0},
        {"effectiveReducedMotionDuringAnimatedChecks",reduced},{"injectedSystemReducedPathTested",true},
        {"systemPolicyRestoreOnReturn",-1},{"systemPolicyRestored",systemPolicyRestored},{"frames",intervals.size()},
        {"medianFrameMs",intervals.isEmpty()?0:intervals[intervals.size()/2]},
        {"p95FrameMs",intervals.isEmpty()?0:intervals[qMin(intervals.size()-1,qsizetype(intervals.size()*0.95))]},
        {"p99FrameMs",intervals.isEmpty()?0:intervals[qMin(intervals.size()-1,qsizetype(intervals.size()*0.99))]},
        {"over60HzBudget",int(std::count_if(intervals.begin(),intervals.end(),[](double ms){return ms>1000.0/60;}))},
        {"over120HzBudget",int(std::count_if(intervals.begin(),intervals.end(),[](double ms){return ms>1000.0/120;}))},
        {"longFramesOver50Ms",int(std::count_if(intervals.begin(),intervals.end(),[](double ms){return ms>50;}))},
        {"warmFrames",warmIntervals.size()},
        {"warmMedianFrameMs",warmIntervals.isEmpty()?0:warmIntervals[warmIntervals.size()/2]},
        {"warmP95FrameMs",warmIntervals.isEmpty()?0:warmIntervals[qMin(warmIntervals.size()-1,qsizetype(warmIntervals.size()*0.95))]},
        {"complexMotion",eval("motionPolicy.complexMotion").toBool()},
        {"activeGrabs",eval("motionPolicy.activeGrabCount").toInt()},
        {"cachedPages",host->property("cachedPageCount").toInt()},
        {"memoryBytes",memory()},{"revisitGrowthBytes",growth},{"idleFrames",idleFrames}};
    QJsonObject report{{"checks",checks},{"failures",failures},{"performance",performance},
        {"frameTimeline",frameTimeline},{"frameProbe",frameProbe},
        {"diagnostics",QJsonDocument::fromJson(eval("JSON.stringify(systemProvider.logs())").toString().toUtf8()).array()}};
    if(!output.isEmpty()) {
        QDir().mkpath(QFileInfo(output).absolutePath());QFile file(output);
        if(!file.open(QIODevice::WriteOnly))return 1;
        file.write(QJsonDocument(report).toJson());
    }
    qInfo()<<"MOTION_RESULT"<<failures<<performance;
    return failures?1:0;
}
