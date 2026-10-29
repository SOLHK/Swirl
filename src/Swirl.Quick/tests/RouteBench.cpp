#include "RouteBench.h"
#include "SwirlBuildIdentity.h"
#include "app/WindowsBackdrop.h"
#include <QDir>
#include <QElapsedTimer>
#include <QEventLoop>
#include <QFileInfo>
#include <QGuiApplication>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJSValue>
#include <QMap>
#include <QMetaMethod>
#include <QMetaProperty>
#include <QMutex>
#include <QMutexLocker>
#include <QPointer>
#include <QQmlContext>
#include <QQmlEngine>
#include <QQmlError>
#include <QQmlExpression>
#include <QQmlIncubationController>
#include <QQuickItem>
#include <QQuickWindow>
#include <QSaveFile>
#include <QScreen>
#include <QSGRendererInterface>
#include <QTest>
#include <QThread>
#include <QTimer>
#include <QUuid>
#include <QVector>
#include <memory>
#include <vector>

namespace {
constexpr qsizetype FrameCapacity=120000, EventCapacity=12000, SnapshotCapacity=120000, WarningCapacity=256;
struct GuiSnapshot {
    quint64 seq=0, shadowBuilds=0;
    qint64 ns=0;
    QString phase, route, activeRoute;
    bool moving=false, pending=false, pendingLoader=false, travel=false, commit=false, exposed=false, active=false, shadowActive=false;
    int width=0,height=0,cache=0,incubatingObjects=-1;
    qreal dpr=0;
};
struct Frame { quint64 seq=0; qint64 ns=0, previousNs=-1; GuiSnapshot gui,previousGui; };
struct RenderFrame {
    quint64 seq=0;
    qint64 begin=-1,syncBegin=-1,syncEnd=-1,renderBegin=-1,renderEnd=-1,present=-1,end=-1;
    GuiSnapshot gui;
};
struct Event {
    quint64 seq=0; qint64 ns=0,request=0;
    QString kind,phase,route; QSize requestedSize;
    GuiSnapshot gui;
};
struct Warning { qint64 ns=0; int type=0; QString message; bool truncated=false; };
struct State {
    QElapsedTimer clock;
    QMutex mutex;
    bool accepting=true;
    GuiSnapshot latest, previousFrameGui;
    qint64 lastFrameNs=-1,frameDropped=0,eventDropped=0,snapshotDropped=0,warningDropped=0,nonGuiSignals=0,renderDropped=0;
    quint64 frameCount=0,eventCount=0,snapshotCount=0;
    qint64 frameProbeTotalNs=0,frameProbeMaxNs=0,guiProbeTotalNs=0,guiProbeMaxNs=0;
    qint64 renderProbeTotalNs=0,renderProbeMaxNs=0;
    quint64 renderCount=0;
    RenderFrame currentRender;
    QVector<Frame> frames;
    QVector<RenderFrame> renderFrames;
    QVector<Event> events;
    QVector<GuiSnapshot> snapshots;
    QVector<Warning> warnings;
};
QMutex messageMutex;
std::shared_ptr<State> messageState;
QtMessageHandler previousMessageHandler=nullptr;
void recordMessage(QtMsgType type,const QMessageLogContext &context,const QString &message) {
    std::shared_ptr<State> state;
    QtMessageHandler previous;
    { QMutexLocker lock(&messageMutex); state=messageState; previous=previousMessageHandler; }
    if(state&&(type==QtWarningMsg||type==QtCriticalMsg||type==QtFatalMsg)) {
        QMutexLocker lock(&state->mutex);
        if(state->accepting) {
            if(state->warnings.size()<WarningCapacity)state->warnings.append({state->clock.nsecsElapsed(),int(type),message.left(4096),message.size()>4096});
            else ++state->warningDropped;
        }
    }
    if(previous)previous(type,context,message);
}
struct MessageScope {
    explicit MessageScope(const std::shared_ptr<State> &state) {
        QMutexLocker lock(&messageMutex);messageState=state;previousMessageHandler=qInstallMessageHandler(recordMessage);
    }
    ~MessageScope() {
        QMutexLocker lock(&messageMutex);qInstallMessageHandler(previousMessageHandler);messageState.reset();previousMessageHandler=nullptr;
    }
};
QObject *object(const QVariant &value) {
    return value.metaType()==QMetaType::fromType<QJSValue>()?value.value<QJSValue>().toQObject():qvariant_cast<QObject *>(value);
}
QJsonObject guiJson(const GuiSnapshot &s) {
    return {{"sample_seq",qint64(s.seq)},{"t_ns",s.ns},{"phase",s.phase},{"route_key",s.route},{"active_route",s.activeRoute},
        {"moving",s.moving},{"pending_grab",s.pending},{"pending_loader",s.pendingLoader},{"travel_running",s.travel},{"commit_running",s.commit},
        {"width",s.width},{"height",s.height},{"dpr",s.dpr},{"cache_count",s.cache},{"incubating_object_count",s.incubatingObjects},{"shadow_build_count",qint64(s.shadowBuilds)},
        {"exposed",s.exposed},{"active",s.active},{"compatibility_shadow",s.shadowActive}};
}
void waitForEvents(int ms) {
    QEventLoop loop;QTimer timer;timer.setTimerType(Qt::PreciseTimer);timer.setSingleShot(true);
    QObject::connect(&timer,&QTimer::timeout,&loop,&QEventLoop::quit);timer.start(ms);loop.exec();
}
}

int runRouteBench(QQuickWindow *window,const QString &output) {
    if(!window||output.isEmpty()||QFileInfo::exists(output))return 3;
    const QString scenario=qEnvironmentVariable("SWIRL_ROUTE_BENCH");
    bool roundsValid=true;
    const int rounds=qEnvironmentVariableIsSet("SWIRL_ROUTE_BENCH_ROUNDS")?qEnvironmentVariableIntValue("SWIRL_ROUTE_BENCH_ROUNDS",&roundsValid):40;
    const QString material=qEnvironmentVariable("SWIRL_ROUTE_BENCH_MATERIAL",QStringLiteral("opaque"));
    if(!QStringList{"routes","resize","mixed","first-visits"}.contains(scenario)||!roundsValid||rounds<1||rounds>400||!QStringList{"opaque","current","glass"}.contains(material))return 3;
    auto state=std::make_shared<State>();state->clock.start();state->frames.reserve(4096);state->events.reserve(1024);state->snapshots.reserve(4096);
    state->renderFrames.reserve(4096);
    MessageScope messages(state);
    QJsonArray checks;int failures=0,qmlWarnings=0;QString phase=QStringLiteral("setup");qint64 requestId=0;
    auto check=[&](const QString &name,bool passed){checks.append(QJsonObject{{"name",name},{"passed",passed}});if(!passed)++failures;qInfo()<<"ROUTE_BENCH_CHECK"<<name<<passed;};
    auto *host=window->findChild<QQuickItem *>("pageLoader");
    check("real-page-host-present",host!=nullptr);
    if(!host)return 2;
    auto *travel=host->findChild<QObject *>("pageTravel");auto *commit=host->findChild<QObject *>("pageCommit");
    auto *context=qmlContext(window);auto *engine=qmlEngine(window);
    check("qml-context-present",context&&engine);if(!context||!engine)return 2;
    auto *backdrop=context?qobject_cast<WindowsBackdrop *>(object(context->contextProperty("backdrop"))):nullptr;
    check("native-shadow-counter-present",backdrop!=nullptr);
    const QSize originalSize=window->size();const QString originalRoute=host->property("routeKey").toString();
    auto eval=[&](const QString &code){QQmlExpression expression(context,window,code);const auto value=expression.evaluate();if(expression.hasError()){check("qml-expression-valid",false);qWarning()<<expression.error();}return value;};
    const bool originalReduce=eval("Theme.reduceMotion").toBool(),originalFollow=eval("Theme.followSystemMotion").toBool();
    const bool originalTransparency=eval("Theme.transparency").toBool();const QString originalTheme=eval("Theme.mode").toString();const double originalSpeed=eval("SwirlMotion.speed").toDouble();
    const bool originalContrast=eval("Theme.increaseContrast").toBool();
    auto snapshot=[&] {
        const qint64 started=state->clock.nsecsElapsed();GuiSnapshot s;s.phase=phase;
        s.route=host->property("routeKey").toString();if(auto *active=object(host->property("activeLoader")))s.activeRoute=active->property("routeId").toString();
        s.moving=host->property("moving").toBool();s.pending=host->property("pendingGrab").toBool();s.pendingLoader=object(host->property("pendingLoader"))!=nullptr;
        s.travel=travel&&travel->property("running").toBool();s.commit=commit&&commit->property("running").toBool();
        s.width=window->width();s.height=window->height();s.dpr=window->devicePixelRatio();s.cache=host->property("cachedPageCount").toInt();
        if(QThread::currentThread()==engine->thread())
            if(auto *controller=engine->incubationController())s.incubatingObjects=controller->incubatingObjectCount();
        s.exposed=window->isExposed();s.active=window->isActive();s.shadowBuilds=backdrop?backdrop->compatibilityShadowBuildCount():0;s.shadowActive=backdrop&&backdrop->compatibilityShadow();s.ns=state->clock.nsecsElapsed();
        QMutexLocker lock(&state->mutex);s.seq=++state->snapshotCount;state->latest=s;
        if(state->snapshots.size()<SnapshotCapacity)state->snapshots.append(s);else ++state->snapshotDropped;
        const auto cost=state->clock.nsecsElapsed()-started;state->guiProbeTotalNs+=cost;state->guiProbeMaxNs=qMax(state->guiProbeMaxNs,cost);
        return s;
    };
    auto event=[&](const QString &kind,qint64 request=0,const QString &route=QString(),QSize size=QSize()) {
        const auto s=snapshot();QMutexLocker lock(&state->mutex);Event e{++state->eventCount,state->clock.nsecsElapsed(),request,kind,phase,route,size,s};
        if(state->events.size()<EventCapacity)state->events.append(e);else ++state->eventDropped;
    };
    QObject probeContext;
    const auto qmlConnection=QObject::connect(engine,&QQmlEngine::warnings,&probeContext,[&](const QList<QQmlError> &warnings){qmlWarnings+=warnings.size();});
    QTimer guiTimer;guiTimer.setTimerType(Qt::PreciseTimer);guiTimer.setInterval(4);
    QObject::connect(&guiTimer,&QTimer::timeout,&probeContext,[&]{snapshot();});
    const auto frameConnection=QObject::connect(window,&QQuickWindow::frameSwapped,&probeContext,[state] {
        const qint64 now=state->clock.nsecsElapsed();QMutexLocker lock(&state->mutex);if(!state->accepting)return;
        const Frame frame{++state->frameCount,now,state->lastFrameNs,state->latest,state->previousFrameGui};
        if(state->frames.size()<FrameCapacity)state->frames.append(frame);else ++state->frameDropped;
        state->lastFrameNs=now;state->previousFrameGui=state->latest;
        const auto cost=state->clock.nsecsElapsed()-now;state->frameProbeTotalNs+=cost;state->frameProbeMaxNs=qMax(state->frameProbeMaxNs,cost);
    },Qt::DirectConnection);
    // Render-thread signals only update native state. These are CPU brackets,
    // not GPU timings; in particular afterRendering precedes queue submission.
    const auto renderMark=[state](int stage) {
        const qint64 now=state->clock.nsecsElapsed();QMutexLocker lock(&state->mutex);if(!state->accepting)return;
        auto &frame=state->currentRender;
        if(stage==0){frame=RenderFrame{};frame.seq=++state->renderCount;frame.begin=now;frame.gui=state->latest;}
        else if(stage==1)frame.syncBegin=now;
        else if(stage==2)frame.syncEnd=now;
        else if(stage==3)frame.renderBegin=now;
        else if(stage==4)frame.renderEnd=now;
        else if(stage==5)frame.present=now;
        else if(stage==6){frame.end=now;if(state->renderFrames.size()<FrameCapacity)state->renderFrames.append(frame);else ++state->renderDropped;}
        const auto cost=state->clock.nsecsElapsed()-now;state->renderProbeTotalNs+=cost;state->renderProbeMaxNs=qMax(state->renderProbeMaxNs,cost);
    };
    const std::vector<QMetaObject::Connection> renderConnections={
        QObject::connect(window,&QQuickWindow::beforeFrameBegin,&probeContext,[renderMark]{renderMark(0);},Qt::DirectConnection),
        QObject::connect(window,&QQuickWindow::beforeSynchronizing,&probeContext,[renderMark]{renderMark(1);},Qt::DirectConnection),
        QObject::connect(window,&QQuickWindow::afterSynchronizing,&probeContext,[renderMark]{renderMark(2);},Qt::DirectConnection),
        QObject::connect(window,&QQuickWindow::beforeRendering,&probeContext,[renderMark]{renderMark(3);},Qt::DirectConnection),
        QObject::connect(window,&QQuickWindow::afterRendering,&probeContext,[renderMark]{renderMark(4);},Qt::DirectConnection),
        QObject::connect(window,&QQuickWindow::frameSwapped,&probeContext,[renderMark]{renderMark(5);},Qt::DirectConnection),
        QObject::connect(window,&QQuickWindow::afterFrameEnd,&probeContext,[renderMark]{renderMark(6);},Qt::DirectConnection)};
    std::vector<std::unique_ptr<RouteBenchSignalTap>> taps;
    QJsonArray subscribedSignals;
    QThread *const guiThread=QThread::currentThread();
    auto tap=[&](QObject *sender,const QByteArray &signature,const QString &kind) {
        const int signal=sender?sender->metaObject()->indexOfSignal(signature.constData()):-1;
        if(signal<0){subscribedSignals.append(QJsonObject{{"kind",kind},{"connected",false}});return;}
        auto receiver=std::make_unique<RouteBenchSignalTap>();
        receiver->callback=[&,kind]{if(QThread::currentThread()!=guiThread){QMutexLocker lock(&state->mutex);++state->nonGuiSignals;return;}event(kind);};
        const int slot=receiver->metaObject()->indexOfSlot("record()");
        const auto connection=QObject::connect(sender,sender->metaObject()->method(signal),receiver.get(),receiver->metaObject()->method(slot),Qt::DirectConnection);
        subscribedSignals.append(QJsonObject{{"kind",kind},{"connected",bool(connection)}});taps.push_back(std::move(receiver));
    };
    auto tapProperty=[&](QObject *sender,const char *property,const QString &kind){const int i=sender?sender->metaObject()->indexOfProperty(property):-1;if(i>=0&&sender->metaObject()->property(i).hasNotifySignal())tap(sender,sender->metaObject()->property(i).notifySignal().methodSignature(),kind);else subscribedSignals.append(QJsonObject{{"kind",kind},{"connected",false}});};
    tapProperty(host,"moving","host-moving-changed");tapProperty(host,"pendingGrab","host-pending-changed");tapProperty(host,"routeKey","host-route-changed");tapProperty(host,"activeLoader","host-active-loader-changed");
    tapProperty(travel,"running","page-travel-running-changed");tapProperty(commit,"running","page-commit-running-changed");tap(commit,"triggered()","page-commit-triggered");
    snapshot();guiTimer.start();
    auto settled=[&](const QString &route){const auto s=snapshot();return !s.moving&&!s.pending&&object(host->property("item"))&&s.route==route&&s.activeRoute==route;};
    auto settle=[&](const QString &route,int timeout=4000){const auto id=++requestId;event("settle-request",id,route);const qint64 deadline=state->clock.nsecsElapsed()+qint64(timeout)*1000000;while(!settled(route)&&state->clock.nsecsElapsed()<deadline)waitForEvents(4);const bool ok=settled(route);event("settle-return",id,route);check("settles-to-"+route,ok);return ok;};
    auto warmSettle=[&](const QString &route,int timeout=4000){
        const auto id=++requestId;event("settle-request",id,route);
        // Cold loading runs outside a new nested event loop. qWaitFor also
        // flushes posted/deferred-delete work; measured waits remain unchanged.
        const bool ok=QTest::qWaitFor([&]{return settled(route);},timeout);
        event("settle-return",id,route);check("settles-to-"+route,ok);return ok;
    };
    auto route=[&](const QString &target){const auto id=++requestId;event("route-request",id,target);eval("AppState.navigate('"+target+"')");event("route-return",id,target);};
    auto resize=[&](QSize size){const auto id=++requestId;event("resize-request",id,QString(),size);window->resize(size);event("resize-return",id,QString(),size);check("resize-request-updates-window",window->size()==size);};
    auto begin=[&](const QString &name){phase=name;event("phase-begin");};
    auto end=[&]{event("phase-end");};
    event("setup-begin");
    eval("Theme.reduceMotion=false;Theme.followSystemMotion=false;SwirlMotion.speed=1;AppState.toast=''");
    if(material=="opaque")eval("Theme.transparency=false;Theme.mode='Light'");
    else if(material=="glass")eval("Theme.transparency=true;Theme.increaseContrast=false;Theme.mode='Light'");
    check("animations-retained",!eval("SwirlMotion.reduced").toBool()&&host->property("animateRoutes").toBool());
    check("native-window-visible",window->isVisible()&&window->winId()!=0&&QGuiApplication::platformName()!="offscreen"&&QGuiApplication::platformName()!="minimal");
    resize(QSize(qMax(1100,window->minimumWidth()),qMax(760,window->minimumHeight())));waitForEvents(120);
    const QSize benchmarkSize=window->size();
    const QStringList routes=scenario=="routes"||scenario=="first-visits"
        ?QStringList{"overview","settings","proxies","policies","subscriptions","featurehub","capture","connections","rules","logs"}
        :QStringList{"overview","settings","proxies","featurehub","capture","connections","rules","logs"};
    const QStringList warmed=scenario=="resize"?QStringList{"overview"}:routes;
    QMap<QString,QPointer<QObject>> loaders,pages;
    auto cachedLoader=[&](const QString &name){const auto value=host->property("pages");return value.metaType()==QMetaType::fromType<QJSValue>()?value.value<QJSValue>().property(name).toQObject():object(value.toMap().value(name));};
    bool warmupCompleted=true;QString warmupFailedRoute;QStringList completedWarmRoutes;
    // This benchmark runs inside the test invocation on an inactive desktop.
    // Provide incubation opportunities only during fixture preparation. Stop
    // before measuring: idle scenes and terminal holds must not gain fake frames.
    QTimer warmupFrames;warmupFrames.setInterval(16);
    QObject::connect(&warmupFrames,&QTimer::timeout,window,&QQuickWindow::update);
    if(scenario=="first-visits")begin("first-visits");else warmupFrames.start();
    for(const auto &name:warmed){
        if(scenario=="first-visits")check("first-visit-cache-miss-"+name,cachedLoader(name)==nullptr);
        route(name);const bool ready=scenario=="first-visits"?settle(name):warmSettle(name);
        auto *loader=cachedLoader(name);loaders.insert(name,loader);pages.insert(name,loader?object(loader->property("item")):nullptr);
        const bool cached=loader&&pages.value(name);check("warm-cache-item-"+name,cached);
        if(!ready||!cached){warmupCompleted=false;warmupFailedRoute=name;event("warmup-failed",0,name);break;}
        completedWarmRoutes.append(name);
    }
    warmupFrames.stop();
    if(scenario=="first-visits")end();
    const int warmedCacheCount=host->property("cachedPageCount").toInt();
    const auto baselineGui=snapshot();event("setup-end");
    auto *glassShader=window->findChild<QQuickItem *>("sidebarLiquidShader");
    auto *glass=glassShader?glassShader->parentItem():nullptr;
    const bool glassSampled=glass&&glass->property("sampled").toBool();
    const bool glassCaptureLive=glass&&glass->property("captureLive").toBool();
    const int glassShaderStatus=glass?glass->property("shaderStatus").toInt():-1;
    if(material=="glass"){
        check("native-glass-sampled-and-live",glassSampled&&glassCaptureLive);
        // QQuickShaderEffect::Status: Compiled=0, Uncompiled=1, Error=2.
        check("native-glass-shader-compiled",glassShaderStatus==0);
        check("native-glass-renderer",window->rendererInterface()->graphicsApi()!=QSGRendererInterface::Software);
    }
    auto cacheCheck=[&]{check("cache-count-stays-warm",host->property("cachedPageCount").toInt()==warmedCacheCount);for(const auto &name:warmed){auto *loader=cachedLoader(name);check("cache-identity-"+name,loaders.value(name)&&pages.value(name)&&loader==loaders.value(name).data()&&object(loader->property("item"))==pages.value(name).data());}};
    if(!warmupCompleted) {
        event("measurement-skipped-after-warmup-failure",0,warmupFailedRoute);
    } else if(scenario=="first-visits") {
        begin("warm-visits");for(const auto &name:routes){route(name);settle(name);check("route-window-size-unchanged",window->size()==benchmarkSize);}end();cacheCheck();
    } else if(scenario=="routes") {
        begin("routes-rapid");for(int i=0;i<rounds;++i){route(routes[i%routes.size()]);waitForEvents(23);check("route-window-size-unchanged",window->size()==benchmarkSize);}settle(routes[(rounds-1)%routes.size()]);end();cacheCheck();
        begin("routes-settled");for(int i=0;i<rounds;++i){route(routes[i%routes.size()]);settle(routes[i%routes.size()]);check("route-window-size-unchanged",window->size()==benchmarkSize);}end();cacheCheck();
    } else if(scenario=="resize") {
        begin("resize");for(int i=0;i<rounds;++i){resize(QSize(qMax(window->minimumWidth(),900+i*2),qMax(window->minimumHeight(),650+i)));waitForEvents(23);check("resize-keeps-fixed-route",settled("overview"));}end();cacheCheck();
    } else {
        begin("mixed");for(int i=0;i<rounds;++i){route(routes[i%routes.size()]);waitForEvents(23);if(i%7==0)resize(QSize(qMax(window->minimumWidth(),900+i*2),qMax(window->minimumHeight(),650+i)));check("mixed-retains-live-page",object(host->property("item"))!=nullptr);}settle(routes[(rounds-1)%routes.size()]);end();cacheCheck();
    }
    const auto measuredEndGui=snapshot();phase="finish";event("finish-request");
    resize(originalSize);route(originalRoute);settle(originalRoute);
    eval(QString("Theme.reduceMotion=%1;Theme.followSystemMotion=%2;Theme.transparency=%3;SwirlMotion.speed=%4;Theme.mode=%5")
        .arg(originalReduce?"true":"false",originalFollow?"true":"false",originalTransparency?"true":"false").arg(originalSpeed).arg(QString::fromUtf8(QJsonDocument(QJsonArray{originalTheme}).toJson(QJsonDocument::Compact)).mid(1).chopped(1)));
    eval(QString("Theme.increaseContrast=%1").arg(originalContrast?"true":"false"));
    waitForEvents(250);event("finish-return");const auto finalGui=snapshot();guiTimer.stop();taps.clear();QObject::disconnect(qmlConnection);
    {QMutexLocker lock(&state->mutex);state->accepting=false;}QObject::disconnect(frameConnection);
    for(const auto &connection:renderConnections)QObject::disconnect(connection);
    check("frame-callbacks-observed",state->frameCount>0);check("no-probe-drops",!state->frameDropped&&!state->eventDropped&&!state->snapshotDropped&&!state->warningDropped&&!state->nonGuiSignals&&!state->renderDropped);
    check("no-qml-warnings-during-bench",qmlWarnings==0);check("no-qt-warnings-during-bench",state->warnings.isEmpty());
    QJsonArray frameJson,eventJson,snapshotJson,warningJson,renderJson;
    const auto timestamp=[](qint64 ns){return ns<0?QJsonValue(QJsonValue::Null):QJsonValue(ns);};
    for(const auto &f:state->renderFrames)renderJson.append(QJsonObject{{"seq",qint64(f.seq)},{"begin_ns",timestamp(f.begin)},{"sync_begin_ns",timestamp(f.syncBegin)},{"sync_end_ns",timestamp(f.syncEnd)},{"render_begin_ns",timestamp(f.renderBegin)},{"render_end_ns",timestamp(f.renderEnd)},{"present_queued_ns",timestamp(f.present)},{"end_ns",timestamp(f.end)},{"gui",guiJson(f.gui)}});
    for(const auto &s:state->snapshots)snapshotJson.append(guiJson(s));
    for(const auto &f:state->frames)frameJson.append(QJsonObject{{"seq",qint64(f.seq)},{"t_ns",f.ns},{"previous_t_ns",f.previousNs<0?QJsonValue(QJsonValue::Null):QJsonValue(f.previousNs)},{"delta_ns",f.previousNs<0?QJsonValue(QJsonValue::Null):QJsonValue(f.ns-f.previousNs)},{"gui",guiJson(f.gui)},{"previous_gui",f.previousNs<0?QJsonValue(QJsonValue::Null):QJsonValue(guiJson(f.previousGui))}});
    for(const auto &e:state->events)eventJson.append(QJsonObject{{"seq",qint64(e.seq)},{"t_ns",e.ns},{"kind",e.kind},{"phase",e.phase},{"request_id",e.request},{"route",e.route},{"requested_width",e.requestedSize.isValid()?QJsonValue(e.requestedSize.width()):QJsonValue(QJsonValue::Null)},{"requested_height",e.requestedSize.isValid()?QJsonValue(e.requestedSize.height()):QJsonValue(QJsonValue::Null)},{"gui",guiJson(e.gui)}});
    for(const auto &w:state->warnings)warningJson.append(QJsonObject{{"t_ns",w.ns},{"type",w.type},{"message",w.message},{"truncated",w.truncated}});
    const QString runId=qEnvironmentVariable("SWIRL_ROUTE_BENCH_RUN_ID",QUuid::createUuid().toString(QUuid::WithoutBraces));
    QJsonObject report{{"schema",3},{"source_sha",QStringLiteral(SWIRL_SOURCE_SHA)},{"scenario",scenario},{"rounds",rounds},{"run_id",runId},{"clock",QJsonObject{{"kind","QElapsedTimer"},{"is_monotonic",QElapsedTimer::isMonotonic()},{"unit","ns"}}},
        {"environment",QJsonObject{{"qt_version",qVersion()},{"renderer",int(window->rendererInterface()->graphicsApi())},{"platform",QGuiApplication::platformName()},{"dpr",baselineGui.dpr},{"refresh_hz",window->screen()?window->screen()->refreshRate():0},{"material",material},{"theme_mode",material=="opaque"?QStringLiteral("Light"):originalTheme},{"transparency",material=="opaque"?false:originalTransparency},{"initial_exposed",baselineGui.exposed},{"initial_active",baselineGui.active},{"profile_attached",qEnvironmentVariableIsSet("SWIRL_QML_PROFILE")},{"warmup_wait_kind","QTest::qWaitFor"},{"warmup_frame_pump_ms",16},{"qsg_render_loop",qEnvironmentVariable("QSG_RENDER_LOOP")},{"qsg_no_vsync",qEnvironmentVariable("QSG_NO_VSYNC")},{"qt_d3d_no_vblank_thread",qEnvironmentVariable("QT_D3D_NO_VBLANK_THREAD")},{"measured_wait_kind","QEventLoop::PreciseTimer"}}},
        {"window",QJsonObject{{"initial_width",originalSize.width()},{"initial_height",originalSize.height()},{"benchmark_width",benchmarkSize.width()},{"benchmark_height",benchmarkSize.height()},{"minimum_width",window->minimumWidth()},{"minimum_height",window->minimumHeight()},{"baseline_gui",guiJson(baselineGui)},{"measured_end_gui",guiJson(measuredEndGui)},{"final_gui",guiJson(finalGui)}}},
        {"cache",QJsonObject{{"warm_routes",QJsonArray::fromStringList(warmed)},{"completed_warm_routes",QJsonArray::fromStringList(completedWarmRoutes)},{"warmed_count",warmedCacheCount}}},{"signals",subscribedSignals},
        {"warmup",QJsonObject{{"completed",warmupCompleted},{"failed_route",warmupFailedRoute},{"timeout_ms",4000},{"measured_phases_skipped",!warmupCompleted}}},
        {"probes",QJsonObject{{"gui_sample_interval_ms",4},{"frame_capacity",qint64(FrameCapacity)},{"event_capacity",qint64(EventCapacity)},{"gui_snapshot_capacity",qint64(SnapshotCapacity)},{"warning_capacity",qint64(WarningCapacity)},
            {"frames_dropped",state->frameDropped},{"events_dropped",state->eventDropped},{"gui_snapshots_dropped",state->snapshotDropped},{"warnings_dropped",state->warningDropped},{"non_gui_signals_dropped",state->nonGuiSignals},{"frame_callbacks",qint64(state->frameCount)},{"gui_snapshot_count",qint64(state->snapshotCount)},
            {"render_callback_reads_qml",false},{"incubation_count_sampled_on_gui_thread",true},{"frame_probe_total_ns",state->frameProbeTotalNs},{"frame_probe_max_ns",state->frameProbeMaxNs},{"gui_probe_total_ns",state->guiProbeTotalNs},{"gui_probe_max_ns",state->guiProbeMaxNs}}},
        {"frames",frameJson},{"render_frames",renderJson},{"events",eventJson},{"gui_snapshots",snapshotJson},{"checks",checks},{"failures",failures},{"qml_warning_count",qmlWarnings},{"warnings",warningJson},{"expected_process_exit_code",failures?2:0},{"observed_process_exit_code",QJsonValue(QJsonValue::Null)},
        {"limitations",QJsonArray{"FrameSwapped is queued-for-presentation cadence, not GPU duration or input-to-photon latency.","GUI snapshots and signal observations bracket states; they do not prove exact interval causation or host.finish() body start/end.","Commit triggered observation may follow the existing QML handler; runningChanged/host changes are independent timestamped observations.","All frame gaps, including setup, static holds, phase crossings and finish, are retained without resetting the previous timestamp.","Warmup uses QTest::qWaitFor and a setup-only 16ms frame request; both stop before measured precise timer waits. Probe render-loop and VSync environment flags are recorded and must match across comparisons.","A failed warmup skips measurement phases but preserves setup/failure/restore records and emits a failing report.","Probe costs exclude Qt signal dispatch and final mutex unlock; snapshots and events add observer overhead.","Warning capture covers this function; the process wrapper must also inspect startup/shutdown diagnostics and confirm actual exit code.","Only isolated test storage and UI navigation/resize are used; no private source downloads or proxy/TUN/DNS mutations."}}};
    auto environment=report.value("environment").toObject();
    environment.insert("first_visit_natural_incubation",scenario=="first-visits");
    environment.insert("warmup_wait_kind",scenario=="first-visits"?"QEventLoop::PreciseTimer":"QTest::qWaitFor");
    environment.insert("warmup_frame_pump_ms",scenario=="first-visits"?0:16);
    environment.insert("transparency",material=="glass"?true:material=="opaque"?false:originalTransparency);
    environment.insert("theme_mode",material=="current"?originalTheme:QStringLiteral("Light"));
    environment.insert("glass_sampled",glassSampled);environment.insert("glass_capture_live",glassCaptureLive);environment.insert("glass_shader_status",glassShaderStatus);
    report.insert("environment",environment);
    auto probes=report.value("probes").toObject();
    probes.insert("render_frames_dropped",state->renderDropped);probes.insert("render_frame_count",qint64(state->renderFrames.size()));
    probes.insert("render_probe_total_ns",state->renderProbeTotalNs);probes.insert("render_probe_max_ns",state->renderProbeMaxNs);report.insert("probes",probes);
    auto limitations=report.value("limitations").toArray();
    limitations.append("Render signal timestamps bracket scene synchronization, command recording and submission on the CPU. They do not measure GPU execution or display presentation; missing stages remain null.");
    limitations.append("First-visits uses native precise event-loop waits with no setup frame pump or prior page warming. Other scenarios retain the original explicitly recorded prewarming protocol.");
    report.insert("limitations",limitations);
    QDir().mkpath(QFileInfo(output).absolutePath());QSaveFile file(output);if(!file.open(QIODevice::WriteOnly))return 3;
    const auto bytes=QJsonDocument(report).toJson();if(file.write(bytes)!=bytes.size()||!file.commit())return 3;
    qInfo()<<"ROUTE_BENCH_RESULT"<<scenario<<"checks"<<checks.size()<<"failures"<<failures<<"frames"<<state->frameCount<<"expected_exit"<<(failures?2:0);
    return failures?2:0;
}
