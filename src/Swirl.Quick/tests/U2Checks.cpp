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
