#include "MotionChecks.h"
#include <QQuickWindow>
#include <QQuickItem>
#include <QQuickItemGrabResult>
#include <QQmlExpression>
#include <QQmlContext>
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
#include <QQmlEngine>
#ifdef Q_OS_WIN
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <psapi.h>
#endif

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
int runMotionChecks(QQuickWindow *window, const QString &output) {
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
        if(e.hasError()){qWarning()<<e.error();++failures;}
        return value;
    };
    auto *host=window->findChild<QQuickItem *>("pageLoader");
    if(!host)return 1;
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
    check("initial-page-present",item()!=nullptr);
    route("featurehub");
    auto *hub=item();
    check("hub-loaded",hub!=nullptr);
    auto *search=hub?hub->findChild<QObject *>("moduleSearch"):nullptr;
    if(search)search->setProperty("text","http");
    route("settings");route("featurehub");
    check("page-instance-preserved",item()==hub);
    check("editable-state-preserved",search&&search->property("text").toString()=="http");
    if(search)search->setProperty("text","");wait(80);
    auto *hubScroll=findVisual(qobject_cast<QQuickItem *>(hub),"motion-hub-scroll");
    auto *flick=hubScroll?qvariant_cast<QObject *>(hubScroll->property("contentItem")):nullptr;
    if(flick)flick->setProperty("contentY",240);
    wait(80);const double scrollBefore=flick?flick->property("contentY").toDouble():-1;
    route("settings");route("featurehub");
    check("scroll-state-preserved",flick && scrollBefore>0 && qAbs(flick->property("contentY").toDouble()-scrollBefore)<0.1);
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
    route("proxies");
    auto *combo=proxy?proxy->findChild<QObject *>("proxyRegionCombo"):nullptr;
    auto *popup=combo?qvariant_cast<QObject *>(combo->property("popup")):nullptr;
    if(popup) {
        auto *comboItem=qobject_cast<QQuickItem *>(combo);
        const auto comboPoint=comboItem->mapToScene(QPointF(comboItem->width()/2,comboItem->height()/2)).toPoint();
        QTest::mouseClick(window,Qt::LeftButton,Qt::NoModifier,comboPoint);waitOpen(popup);
        check("dropdown-opens",popup->property("opened").toBool());
        QTest::keyClick(window,Qt::Key_Escape);wait(400);
        check("dropdown-escape",!popup->property("visible").toBool());
    } else check("dropdown-present",false);
    auto *button=window->findChild<QQuickItem *>("nav-settings");
    if(button) {
        const auto p=button->mapToScene(QPointF(button->width()/2,button->height()/2)).toPoint();
        for(int i=0;i<8;++i){QTest::mousePress(window,Qt::LeftButton,Qt::NoModifier,p);wait(22);QTest::mouseRelease(window,Qt::LeftButton,Qt::NoModifier,p);wait(15);}
        wait(1400);settle();
        check("rapid-button-release-restores-scale",qAbs(button->property("motionScale").toDouble()-1)<0.001);
        check("button-hit-area-unchanged",button->scale()==1);
    } else check("navigation-button-present",false);
    QList<double> intervals;QList<double> warmIntervals;bool warmPhase=false;bool measuring=true;QMutex frameMutex;
    QElapsedTimer clock;clock.start();qint64 last=0;
    auto connection=QObject::connect(window,&QQuickWindow::frameSwapped,window,[&] {
        const qint64 now=clock.nsecsElapsed();
        QMutexLocker lock(&frameMutex);
        const double delta=double(now-last)/1000000.0;
        if(!measuring)return;
        if(last && delta<100){intervals<<delta;if(warmPhase)warmIntervals<<delta;}
        last=now;
    },Qt::DirectConnection);
    const QStringList stress={"overview","settings","proxies","featurehub","capture","connections","rules","logs"};
    for(int i=0;i<40;++i) {
        eval("AppState.navigate('"+stress[i%stress.size()]+"')");
        wait(23);
        if(i%7==0)window->resize(900+i*2,650+i);
        check("rapid-switch-has-live-page-"+QString::number(i),item()!=nullptr);
    }
    check("rapid-switch-settles",settle(3500));
    check("latest-route-wins",qvariant_cast<QObject *>(host->property("activeLoader"))->property("routeId").toString()==stress[39%stress.size()]);
    // Warm transitions measure steady animation rather than initial QML creation.
    window->resize(1100,760);
    {QMutexLocker lock(&frameMutex);warmPhase=true;last=0;}
    for(int i=0;i<8;++i)route(stress[i]);
    {QMutexLocker lock(&frameMutex);measuring=false;}
    QObject::disconnect(connection);
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
    eval("SwirlMotion.shared=null");
    // Exercise the real card and its asynchronous scene-graph capture.
    if(search){search->setProperty("text",QString::fromUtf8("系统代理"));wait(80);}
    auto *card=findVisual(qobject_cast<QQuickItem *>(item()),"motion-feature-card");
    check("shared-element-source-present",card!=nullptr);
    if(card) {
        const auto p=card->mapToScene(QPointF(card->width()/2,card->height()/2)).toPoint();
        QTest::mouseClick(window,Qt::LeftButton,Qt::NoModifier,p);
        wait(120);check("shared-card-navigates",eval("AppState.currentPage!=='featurehub'").toBool());
        check("shared-transition-settles",settle(3500));
        check("shared-texture-released",eval("pageLoader.heroData===null").toBool());
        auto *detail=findVisual(qobject_cast<QQuickItem *>(item()),"motion-detail");
        check("shared-element-target-present",detail!=nullptr);
        if(detail) {
            QQmlExpression reverse(qmlContext(detail),detail,"SwirlMotion.returnToHub(this)");reverse.evaluate();
            wait(100);settle(3500);
            check("shared-reverse-restores-hub",eval("AppState.currentPage==='featurehub'").toBool());
            check("shared-reverse-preserves-page",item()==hub);
            auto *source=findVisual(qobject_cast<QQuickItem *>(item()),"motion-feature-card");
            if(source) {
                const auto point=source->mapToScene(QPointF(source->width()/2,source->height()/2)).toPoint();
                QTest::mouseClick(window,Qt::LeftButton,Qt::NoModifier,point);wait(100);settle(3500);
                QTest::keyClick(window,Qt::Key_Left,Qt::AltModifier);wait(100);settle(3500);
                check("history-shared-return",eval("AppState.currentPage==='featurehub'").toBool() && item()==hub);
            }
        }
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
    int idleFrames=0;
    auto idleConnection=QObject::connect(window,&QQuickWindow::frameSwapped,window,[&]{++idleFrames;});
    wait(650);QObject::disconnect(idleConnection);
    check("idle-no-animation-loop",idleFrames<=4);
    std::sort(intervals.begin(),intervals.end());
    std::sort(warmIntervals.begin(),warmIntervals.end());
    QJsonObject performance{{"renderer",int(window->rendererInterface()->graphicsApi())},
        {"refreshHz",window->screen()?window->screen()->refreshRate():0},
        {"systemReducedMotion",reduced},{"frames",intervals.size()},
        {"medianFrameMs",intervals.isEmpty()?0:intervals[intervals.size()/2]},
        {"p95FrameMs",intervals.isEmpty()?0:intervals[qMin(intervals.size()-1,qsizetype(intervals.size()*0.95))]},
        {"warmFrames",warmIntervals.size()},
        {"warmMedianFrameMs",warmIntervals.isEmpty()?0:warmIntervals[warmIntervals.size()/2]},
        {"warmP95FrameMs",warmIntervals.isEmpty()?0:warmIntervals[qMin(warmIntervals.size()-1,qsizetype(warmIntervals.size()*0.95))]},
        {"complexMotion",eval("motionPolicy.complexMotion").toBool()},
        {"activeGrabs",eval("motionPolicy.activeGrabCount").toInt()},
        {"cachedPages",host->property("cachedPageCount").toInt()},
        {"memoryBytes",memory()},{"revisitGrowthBytes",growth},{"idleFrames",idleFrames}};
    QJsonObject report{{"checks",checks},{"failures",failures},{"performance",performance}};
    if(!output.isEmpty()) {
        QDir().mkpath(QFileInfo(output).absolutePath());QFile file(output);
        if(!file.open(QIODevice::WriteOnly))return 1;
        file.write(QJsonDocument(report).toJson());
    }
    qInfo()<<"MOTION_RESULT"<<failures<<performance;
    return failures?1:0;
}
