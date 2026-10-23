#include <QQuickWindow>
#include <QQuickItem>
#include <QQmlExpression>
#include <QQmlContext>
#include <QTest>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QFile>
#include <QFileInfo>
#include <QDir>
#include <QElapsedTimer>
#include <QTimer>
#include <QEventLoop>
#include "app/NodeViewModel.h"
#ifdef Q_OS_WIN
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <psapi.h>
#endif

int runU2Checks(QQuickWindow *window, const QString &output) {
    QJsonArray checks, samples;
    int failures=0;
    const QString phase=qEnvironmentVariable("SWIRL_U2_CHECKS");
    const auto eval=[&](const QString &code){QQmlExpression e(qmlContext(window),window,code);auto value=e.evaluate();if(e.hasError()){qWarning()<<e.error();++failures;}return value;};
    const auto check=[&](const QString &name,bool passed){checks.append(QJsonObject{{"name",name},{"passed",passed}});if(!passed)++failures;};
    const auto wait=[](int ms){QEventLoop loop;QTimer::singleShot(ms,&loop,&QEventLoop::quit);loop.exec();};
    const auto sample=[&](const QString &name){
        QJsonObject row{{"scenario",name},{"objects",window->findChildren<QObject *>().size()},{"cachedPages",eval("pageLoader.cachedPageCount").toInt()}};
#ifdef Q_OS_WIN
        PROCESS_MEMORY_COUNTERS_EX m{};m.cb=sizeof(m);
        if(GetProcessMemoryInfo(GetCurrentProcess(),reinterpret_cast<PROCESS_MEMORY_COUNTERS *>(&m),sizeof(m))){row["workingSetBytes"]=double(m.WorkingSetSize);row["privateBytes"]=double(m.PrivateUsage);}
        FILETIME created,exited,kernel,user;
        if(GetProcessTimes(GetCurrentProcess(),&created,&exited,&kernel,&user))row["cpuMilliseconds"]=double((quint64(kernel.dwHighDateTime)<<32|kernel.dwLowDateTime)+(quint64(user.dwHighDateTime)<<32|user.dwLowDateTime))/10000.0;
#endif
        samples.append(row);
    };
    const auto navigate=[&](const QString &route){eval("AppState.navigate('"+route+"')");QElapsedTimer t;t.start();wait(25);while(eval("pageLoader.pendingGrab || pageLoader.moving || !pageLoader.item || !pageLoader.activeLoader || pageLoader.activeLoader.routeId!==pageLoader.routeKey").toBool()&&t.elapsed()<5000)wait(10);check("loaded-"+route,t.elapsed()<5000);};
    window->requestActivate();wait(250);
    const QSize initial=window->size();
    const double sidebar=eval("window.actualSidebarWidth").toDouble();
    sample("cold");
    if(phase=="navigation"){
        navigate("activity");QTest::keyClick(window,Qt::Key_Escape);wait(250);
        check("primary-escape-keeps-window",window->isVisible()&&eval("AppState.currentPage").toString()=="activity");
        for(const auto &route:{"traffic","connections","toolbox","processes","gateway","logs"}){
            eval(QString("AppState.openDetail('%1')").arg(route));wait(500);QTest::keyClick(window,Qt::Key_Escape);wait(500);
            check(QString("activity-escape-")+route,eval("AppState.currentPage").toString()=="activity");
        }
        eval("AppState.openDetail('traffic')");wait(400);eval("AppState.openDetail('connections')");wait(400);
        QTest::keyClick(window,Qt::Key_Escape);wait(400);check("nested-first-escape",eval("AppState.currentPage").toString()=="traffic");
        QTest::keyClick(window,Qt::Key_Escape);wait(400);check("nested-second-escape",eval("AppState.currentPage").toString()=="activity");
        navigate("featurehub");navigate("proxies");
        auto *combo=window->findChild<QQuickItem *>("nodeSortOrder");
        if(combo){auto *popup=combo->property("popup").value<QObject *>();QMetaObject::invokeMethod(popup,"open");wait(250);QTest::keyClick(window,Qt::Key_Escape);wait(300);check("popup-first-escape",!popup->property("visible").toBool()&&eval("AppState.currentPage").toString()=="proxies");}
        else check("sort-popup-present",false);
        auto *search=window->findChild<QQuickItem *>("nodeSearchField");if(search)search->forceActiveFocus();
        QTest::keyClick(window,Qt::Key_Escape);wait(450);check("focused-input-back",eval("AppState.currentPage").toString()=="featurehub");
        check("escape-keeps-geometry",window->size()==initial);
        QFile f(output);if(!f.open(QIODevice::WriteOnly))return 2;f.write(QJsonDocument(QJsonObject{{"checks",checks},{"failures",failures}}).toJson());return failures?1:0;
    }
    if(phase=="detail"){
        navigate("proxies");
        auto *model=window->findChild<NodeViewModel *>("nodeViewModel");
        if(!model||!model->controller())return 2;
        auto *controller=model->controller();
        check("save-isolated-detail-node",controller->saveNode({{"name","详情验证 · 日本 Tokyo"},{"protocol","socks5"},{"host","127.0.0.1"},{"port",9}}));
        wait(100);const auto before=window->grabWindow();eval("pageLoader.item.selectRow(engineController.nodes[0])");
        auto *hero=window->findChild<QQuickItem *>("nodeHero");
        for(int i=0;i<40;++i){wait(50);if(hero)samples.append(QJsonObject{{"ms",(i+1)*50},{"reveal",hero->property("reveal").toDouble()},{"moving",hero->property("moving").toBool()},{"width",hero->property("cardWidth").toDouble()},{"height",hero->property("cardHeight").toDouble()}});}
        check("detail-fully-revealed",hero&&!hero->property("moving").toBool()&&hero->property("reveal").toDouble()>0.99);
        auto *body=window->findChild<QQuickItem *>("nodeDetailBody");
        check("detail-body-visible",body&&body->isVisible()&&body->opacity()>0.99&&body->width()>100&&body->height()>100);
        auto *scrim=window->findChild<QQuickItem *>("nodeDetailScrim");const auto after=window->grabWindow();
        check("rounded-scrim",scrim&&scrim->property("radius").toDouble()==eval("Theme.cardRadius").toDouble());
        if(scrim&&!before.isNull()&&!after.isNull())for(const auto &p:{QPointF(2,2),QPointF(scrim->width()-3,2),QPointF(2,scrim->height()-3),QPointF(scrim->width()-3,scrim->height()-3)}){
            const auto pixel=(scrim->mapToScene(p)*window->devicePixelRatio()).toPoint();
            check("scrim-corner-preserves-background",before.rect().contains(pixel)&&after.rect().contains(pixel)&&before.pixelColor(pixel)==after.pixelColor(pixel));
        }
        window->grabWindow().save(QFileInfo(output).absolutePath()+"/detail.png");
        QFile f(output);if(!f.open(QIODevice::WriteOnly))return 2;f.write(QJsonDocument(QJsonObject{{"checks",checks},{"samples",samples},{"failures",failures}}).toJson());return failures?1:0;
    }
    const auto routes=QJsonDocument::fromJson(eval("JSON.stringify(AppState.allPageIds.concat(['activity','settings','proxies','featurehub']))").toString().toUtf8()).array();
    for(const auto &route:routes){
        if(route.toString()=="external")continue;
        navigate(route.toString());
        check("geometry-"+route.toString(),window->size()==initial);
        check("sidebar-"+route.toString(),eval("window.actualSidebarWidth").toDouble()==sidebar);
    }
    window->resize(initial+QSize(90,40));const auto resized=window->size();
    for(const auto &route:{"activity","featurehub","settings","proxies","overview","activity"}){navigate(route);check(QString("manual-geometry-")+route,window->size()==resized);}
    window->resize(initial);navigate("activity");
    if(phase!="baseline"&&phase!="A"){
        check("window-radius-14",eval("Theme.windowRadius").toDouble()==14);
        check("sidebar-radius-14",eval("sidebar.children[0].radius").toDouble()==14);
        window->grabWindow().save(QFileInfo(output).absolutePath()+"/corners-"+QString::number(window->devicePixelRatio())+".png");
    }
    sample("all-pages-warm");
    if(phase=="C"||phase=="D"||phase=="E"){
        navigate("proxies");
        auto *model=window->findChild<NodeViewModel *>("nodeViewModel");
        check("native-node-model",model!=nullptr);
        if(model){
            auto *controller=model->controller();model->setController(nullptr);
            for(const int count:{419,5000}){
                QVariantList rows;for(int i=0;i<count;++i)rows.append(QVariantMap{{"id",QString::number(i)},{"name",QString("日本 Tokyo · 长节点名称性能样本 %1").arg(i)},{"protocol",i%2?"vless":"ss"},{"host","node.example.test"},{"regionName","日本"},{"regionCode","JP"},{"status","未测试"},{"latency","—"}});
                QElapsedTimer load;load.start();model->updateRows(rows);wait(100);
                check(QString("nodes-%1").arg(count),model->rowCount()==count);
                const auto rendered=eval("pageLoader.item.children.length").toInt();
                Q_UNUSED(rendered);
                auto *table=window->findChild<QQuickItem *>("realNodeTable");
                check(QString("virtualized-%1").arg(count),table&&table->property("renderedRows").toInt()<100);
                samples.append(QJsonObject{{"scenario",QString("nodes-%1").arg(count)},{"loadAndSettleMs",double(load.elapsed())},{"renderedRows",table?table->property("renderedRows").toInt():-1}});
                model->setQuery("VLESS");wait(120);check("protocol-search",model->rowCount()==count/2);
                model->setQuery("不存在");check("empty-search",model->rowCount()==0);model->setQuery("");wait(100);
                if(count==419)window->grabWindow().save(QFileInfo(output).absolutePath()+"/nodes-419.png");
            }
            model->setController(controller);
        }
        navigate("activity");
    }
    qint64 maxGap=0;QElapsedTimer heartbeat;heartbeat.start();QTimer ticker;ticker.setInterval(16);
    QObject::connect(&ticker,&QTimer::timeout,&ticker,[&]{maxGap=qMax(maxGap,heartbeat.restart());});ticker.start();
    for(int i=0;i<100;++i){navigate(i%2?"activity":"featurehub");if(i%20==19)sample(QString("switch-%1").arg(i+1));}
    bool ok=false;const int soak=qEnvironmentVariableIntValue("SWIRL_U2_SOAK_SECONDS",&ok);
    if(ok)for(int i=0;i<soak;++i){wait(1000);if(i%60==59)sample(QString("soak-%1").arg(i+1));}
    ticker.stop();sample("final");
    QFile file(output);QDir().mkpath(QFileInfo(output).absolutePath());if(!file.open(QIODevice::WriteOnly))return 2;
    file.write(QJsonDocument(QJsonObject{{"phase",phase},{"checks",checks},{"failures",failures},{"samples",samples},{"maxEventLoopGapMs",double(maxGap)},{"logicalWidth",initial.width()},{"logicalHeight",initial.height()},{"dpr",window->devicePixelRatio()},{"note","Isolated test storage; real Qt event loop. Synthetic node data, when used, is not networking acceptance. DPI factor is process-local, not a change to Windows display settings."}}).toJson());
    return failures?1:0;
}
