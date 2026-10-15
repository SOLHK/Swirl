#pragma once
#include <atomic>
#include <rhi/qrhi.h>
#include "engine/EngineController.h"
#include "ControlledNetwork.h"
#include <QNetworkAccessManager>
#include <QNetworkReply>
#include <QNetworkProxy>
static int recordInteractionSequence(QQuickWindow *window,const QString &directory) {
    QDir().mkpath(directory);
    auto eval=[&](const QString &code){QQmlExpression e(qmlContext(window),window,code);return e.evaluate();};
    auto wait=[](int ms){QEventLoop loop;QTimer::singleShot(ms,&loop,&QEventLoop::quit);loop.exec();};
    std::function<QQuickItem *(QQuickItem *,const QString &)> find=[&](QQuickItem *item,const QString &name)->QQuickItem *{if(item->objectName()==name)return item;for(auto *child:item->childItems())if(auto *found=find(child,name))return found;return nullptr;};
    window->resize(1100,760);window->show();eval("Theme.mode='Light';Theme.reduceMotion=false;AppState.navigate('activity')");wait(500);
    auto *source=find(window->contentItem(),"activityUpload");if(!source)return 2;
    qmlEngine(window)->rootContext()->setContextProperty("motionRecordingSource",source);
    int failures=0;QJsonArray timestamps;QElapsedTimer captureClock;captureClock.start();
    for(int frame=0;frame<120;++frame){
        if(frame==5||frame==20)eval("SwirlMotion.navigateFrom(motionRecordingSource,'traffic','uploadRate')");
        if(frame==9||frame==40)eval("SwirlMotion.returnToHub(null)");
        if(frame==55||frame==63)eval("proxyPanel.toggle()");
        if(frame==59||frame==82)eval("proxyPanel.requestDismiss()");
        if(frame>=90&&frame<112&&frame%2==0){const QStringList routes={"overview","processes","gateway","policies","rules","capture","tls","rewrite","featurehub","activity","overview"};eval("AppState.navigate('"+routes[(frame-90)/2]+"')");}
        wait(33);
        timestamps.append(captureClock.nsecsElapsed()/1e6);
        if(!window->grabWindow().save(directory+QString("/%1.png").arg(frame,4,10,QChar('0'))))++failures;
    }
    QFile timing(directory+"/timestamps.json");if(timing.open(QIODevice::WriteOnly))timing.write(QJsonDocument(timestamps).toJson());
    return failures?1:0;
}
// Invoked only inside the existing isolated --motion-test application.
static int runScrollBench(QQuickWindow *window, const QString &output) {
    auto eval=[&](const QString &code){QQmlExpression e(qmlContext(window),window,code);return e.evaluate();};
    auto wait=[](int ms){QEventLoop loop;QTimer::singleShot(ms,&loop,&QEventLoop::quit);loop.exec();};
    window->resize(914,672);window->show();
    eval("Theme.reduceMotion=false;Theme.mode='Light';AppState.navigate('activity')");wait(700);
    const bool live=qEnvironmentVariableIsSet("SWIRL_SCROLL_LIVE");
    auto *controller=qobject_cast<EngineController *>(qmlEngine(window)->rootContext()->contextProperty("engineController").value<QObject *>());
    ControlledNetwork peers;QNetworkAccessManager client;QTimer traffic;int successfulRequests=0;
    if(live){
        if(!controller||!peers.start())return 3;
        const auto freePort=[](){QTcpServer server;server.listen(QHostAddress::LocalHost);return server.serverPort();};
        controller->setProxyPort(freePort());controller->setControlPort(freePort());controller->setRoutingMode("global");
        if(!controller->saveNode({{"name","Loopback scroll acceptance"},{"protocol","socks5"},{"host","127.0.0.1"},{"port",peers.a.serverPort()}}))return 4;
        controller->connectNode(controller->nodes().last().toMap().value("id").toString());
        for(int i=0;i<100&&!controller->connected();++i)wait(50);
        if(!controller->connected()){controller->disconnectNode();return 5;}
        client.setProxy(QNetworkProxy(QNetworkProxy::HttpProxy,"127.0.0.1",controller->activeProxyPort()));
        QObject::connect(&traffic,&QTimer::timeout,&client,[&]{QNetworkRequest request(peers.url());request.setTransferTimeout(2000);request.setRawHeader("Connection","close");auto *reply=client.get(request);QObject::connect(reply,&QNetworkReply::finished,&client,[&,reply]{if(reply->error()==QNetworkReply::NoError&&reply->readAll()=="exit-A")++successfulRequests;reply->deleteLater();});});
        traffic.start(100);wait(1500);
    }
    QElapsedTimer timer;timer.start();QMutex mutex;
    QList<double> frames,sync,render,dispatch; qint64 last=0,syncStart=0,renderStart=0;
    QByteArray deviceName;bool threaded=false;
    const auto now=[&]{return timer.nsecsElapsed();};
    const auto a=QObject::connect(window,&QQuickWindow::frameSwapped,window,[&]{QMutexLocker lock(&mutex);auto t=now();if(last)frames.append((t-last)/1e6);last=t;},Qt::DirectConnection);
    const auto b=QObject::connect(window,&QQuickWindow::beforeSynchronizing,window,[&]{syncStart=now();},Qt::DirectConnection);
    const auto c=QObject::connect(window,&QQuickWindow::afterSynchronizing,window,[&]{QMutexLocker lock(&mutex);sync.append((now()-syncStart)/1e6);},Qt::DirectConnection);
    const auto d=QObject::connect(window,&QQuickWindow::beforeRendering,window,[&]{renderStart=now();},Qt::DirectConnection);
    const auto e=QObject::connect(window,&QQuickWindow::afterRendering,window,[&]{QMutexLocker lock(&mutex);render.append((now()-renderStart)/1e6);if(deviceName.isEmpty()&&window->rhi())deviceName=window->rhi()->driverInfo().deviceName;threaded=QThread::currentThread()!=window->thread();},Qt::DirectConnection);
    std::function<QQuickItem *(QQuickItem *)> findScroll=[&](QQuickItem *root)->QQuickItem *{if(root->property("contentY").isValid()&&root->property("contentHeight").toDouble()>root->height())return root;for(auto *child:root->childItems())if(auto *found=findScroll(child))return found;return nullptr;};
    auto *scroll=findScroll(qvariant_cast<QQuickItem *>(eval("pageLoader.item")));
    double minY=1e9,maxY=-1e9;
    QTimer input;input.setTimerType(Qt::PreciseTimer);input.setInterval(16);int tick=0;
    QObject::connect(&input,&QTimer::timeout,window,[&]{
        const QPointF p(window->width()*0.65,window->height()*0.65);
        const int delta=(tick++/40)%2?8:-8;
        QWheelEvent wheel(p,window->mapToGlobal(p.toPoint()),QPoint(0,delta),QPoint(0,delta>0?120:-120),Qt::NoButton,Qt::NoModifier,Qt::ScrollUpdate,false);
        const auto start=now();QCoreApplication::sendEvent(window,&wheel);dispatch.append((now()-start)/1e6);
        if(scroll){const auto y=scroll->property("contentY").toDouble();minY=qMin(minY,y);maxY=qMax(maxY,y);}
        window->update(); // Continuous render workload, including time spent at boundaries.
    });
    input.start();wait(30000);input.stop();
    for(auto connection:{a,b,c,d,e})QObject::disconnect(connection);
    const auto stats=[](QList<double> values){std::sort(values.begin(),values.end());QJsonArray raw;for(auto v:values)raw.append(v);return QJsonObject{{"count",values.size()},{"p50",values.isEmpty()?0:values[values.size()/2]},{"p95",values.isEmpty()?0:values[qMin(values.size()-1,qsizetype(values.size()*.95))]},{"p99",values.isEmpty()?0:values[qMin(values.size()-1,qsizetype(values.size()*.99))]},{"max",values.isEmpty()?0:values.last()},{"over16_67",std::count_if(values.begin(),values.end(),[](double v){return v>16.67;})},{"over33_33",std::count_if(values.begin(),values.end(),[](double v){return v>33.33;})},{"samplesMs",raw}};};
    QMutexLocker lock(&mutex);
    QJsonObject report{{"qt",qVersion()},{"graphicsApi",int(window->rendererInterface()->graphicsApi())},{"width",window->width()},{"height",window->height()},{"dpr",window->devicePixelRatio()},{"refreshHz",window->screen()->refreshRate()},{"frameIntervals",stats(frames)},{"syncCpu",stats(sync)},{"renderSubmissionCpu",stats(render)},{"inputDispatchGui",stats(dispatch)},{"dataCondition","isolated disconnected store; actual telemetry stale timer; no fabricated network samples"},{"limitations","frameSwapped is not presentation timing; render CPU is not GPU time; no connected traffic acceptance"}};
    report["minContentY"]=minY;report["maxContentY"]=maxY;report["continuousUpdateRequested"]=true;
    report["gpu"]=QString::fromUtf8(deviceName);report["threadedRenderLoop"]=threaded;
    if(live){report["dataCondition"]="real HTTP over loopback SOCKS5 through production engine; isolated node store; system proxy unchanged";report["successfulRequests"]=successfulRequests;report["forwardedRequests"]=peers.a.forwarded;report["telemetrySampled"]=controller->telemetry()->sampled();report["measuredTotalBytes"]=controller->telemetry()->summary().value("total").toDouble();}
    QDir().mkpath(QFileInfo(output).absolutePath());QFile file(output);if(!file.open(QIODevice::WriteOnly))return 2;file.write(QJsonDocument(report).toJson());
    window->grabWindow().save(QFileInfo(output).absolutePath()+"/activity.png");
    const bool liveVerified=!live||(successfulRequests>=100&&peers.a.forwarded>=100&&controller->telemetry()->sampled()&&controller->telemetry()->summary().value("total").toDouble()>0);
    if(live){traffic.stop();controller->disconnectNode();}
    return frames.isEmpty()||!liveVerified?1:0;
}
