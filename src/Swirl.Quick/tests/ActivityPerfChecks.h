#pragma once
#include <array>
#include <vector>
#include <QDateTime>

static int runActivityPerfChecks(QQuickWindow *window,const QString &output) {
    struct Frame {qint64 ns=0;double progress=0;int phase=-1,cycle=-1,kind=0,destination=-1,visibility=0;bool moving=false,opened=false,active=false,exposed=false,visible=false;};
    struct Resources {double cpuMs=0;quint64 privateBytes=0,workingSet=0;};
    struct Clocks {double weaveProgress=-1,weaveRelease=-1;int registryActive=-1;bool weavePresent=false,weaveMoving=false,weaveActive=false,weavePresentationActive=false;std::array<double,5> cardLift{};std::array<bool,5> cardPresent{},cardHovered{},cardFocused{};};
    struct Phase {QString name; qint64 start=0,end=0;Resources before,after;Clocks clocksBefore,clocksAfter;int updatesBefore=0,updatesAfter=0,realUpdatesBefore=0,realUpdatesAfter=0;bool dataPulseActive=false;std::array<int,4> rowsBefore{},rowsAfter{},syncBefore{},syncAfter{};};
    struct Update {qint64 start=0,ingestStart=0,end=0,uploadTotal=0,downloadTotal=0;int phase=-1,revisionBefore=0,revisionAfter=0;bool fixtureChanged=false;};
    struct Scroll {qint64 ns=0;double before=0,requested=0,after=0,progress=0,bodyOpacity=0,effectiveOpacity=0;QRectF visibleRect;int phase=-1;bool moving=false,opened=false,returning=false,presented=false,pulseActive=false;};
    const int rowCount=qEnvironmentVariableIsSet("SWIRL_ACTIVITY_PERF_ROWS")?qEnvironmentVariableIntValue("SWIRL_ACTIVITY_PERF_ROWS"):600;
    if(rowCount!=600&&rowCount!=2000)return 2;
    QJsonArray checks;int failures=0;
    const auto check=[&](const QString &name,bool passed){checks.append(QJsonObject{{"name",name},{"passed",passed}});if(!passed)++failures;qInfo()<<"ACTIVITY_PERF_CHECK"<<name<<passed;};
    const auto eval=[&](QObject *scope,const QString &code){QQmlExpression expression(qmlContext(scope),scope,code);auto result=expression.evaluate();if(expression.hasError()){qWarning()<<expression.error();check("expression: "+expression.error().toString(),false);}return result;};
    const auto resources=[](){Resources value;
#ifdef Q_OS_WIN
        FILETIME created,exited,kernel,user;GetProcessTimes(GetCurrentProcess(),&created,&exited,&kernel,&user);ULARGE_INTEGER k{},u{};k.LowPart=kernel.dwLowDateTime;k.HighPart=kernel.dwHighDateTime;u.LowPart=user.dwLowDateTime;u.HighPart=user.dwHighDateTime;value.cpuMs=double(k.QuadPart+u.QuadPart)/10000.0;
        PROCESS_MEMORY_COUNTERS_EX memory{};memory.cb=sizeof(memory);if(GetProcessMemoryInfo(GetCurrentProcess(),reinterpret_cast<PROCESS_MEMORY_COUNTERS *>(&memory),sizeof(memory))){value.privateBytes=memory.PrivateUsage;value.workingSet=memory.WorkingSetSize;}
#endif
        return value;
    };
    auto *controller=qobject_cast<EngineController *>(qmlContext(window)->contextProperty("engineController").value<QObject *>());
    auto *policy=qobject_cast<MotionPolicy *>(qmlContext(window)->contextProperty("motionPolicy").value<QObject *>());
    if(!controller||!policy)return 2;
    const auto proxyBefore=SystemProxySession::snapshot();
    policy->setSystemReducedMotionOverrideForTest(0);
    struct RestorePolicy {MotionPolicy *policy;~RestorePolicy(){policy->setSystemReducedMotionOverrideForTest(-1);}} restore{policy};
    eval(window,"Theme.mode='Light';Theme.reduceMotion=false;Theme.followSystemMotion=false;SwirlMotion.speed=1;AppState.navigate('activity')");
    window->resize(1100,760);window->requestActivate();activityWait(550);
    auto *transition=activityVisual(window->contentItem(),"activityDetailTransition");
    if(!transition)return 2;
    QObject *clock=nullptr;for(auto *candidate:transition->findChildren<QObject *>(QString(),Qt::FindDirectChildrenOnly))if(candidate->metaObject()->indexOfProperty("retargeting")>=0){clock=candidate;break;}
    auto *telemetry=controller->telemetry();
    QString initialMeasurement;
    ProxyEngine::Status fixture;fixture.processAlive=true;fixture.apiHealthy=true;fixture.processId=1;fixture.sessionId="activity-perf-controlled";
    const auto initialTime=QDateTime::currentMSecsSinceEpoch();fixture.connectionsAt=fixture.trafficAt=initialTime;
    for(int row=0;row<rowCount;++row){const qint64 up=1024+row*17,down=4096+row*37;fixture.uploadTotal+=up;fixture.downloadTotal+=down;
        fixture.connections.append(QVariantMap{{"id",QString("perf-%1").arg(row,4,10,QChar('0'))},{"host",QString("source-%1.example.test").arg(row,4,10,QChar('0'))},{"process",QString("perf-%1.exe").arg(row%160,3,10,QChar('0'))},{"sourceIp",QString("192.0.2.%1").arg(row%64+1)},{"ip","198.51.100.8"},{"port",443},{"sourcePort",30000+row},{"protocol",row%2?"tcp":"udp"},{"category",row%2?"proxy":"direct"},{"policy",row%2?"controlled-proxy":"DIRECT"},{"uploadBytes",up},{"downloadBytes",down},{"time",QDateTime::fromMSecsSinceEpoch(initialTime).toString(Qt::ISODateWithMs)}});
    }
    telemetry->ingest(fixture);initialMeasurement=telemetry->measurementState();activityWait(350);
    const auto invoke=[&](QObject *object,const QString &code){return eval(object,code);};
    const auto open=[&](int index){
        auto *card=activityVisual(window->contentItem(),activityDetailCards[index]);
        qmlEngine(window)->rootContext()->setContextProperty("activityPerfOrigin",card);
        eval(window,QString("pageLoader.item.openCard(activityPerfOrigin,'%1','%1')").arg(activityDetailKeys[index]));
        check("opens-"+activityDetailKeys[index],transition->property("opened").toBool()&&transition->property("detailKey").toString()==activityDetailKeys[index]);
        return QTest::qWaitFor([&]{return !transition->property("moving").toBool()&&transition->property("progress").toDouble()==1;},2500);
    };
    const auto close=[&]{QMetaObject::invokeMethod(transition,"closeDetail");return QTest::qWaitFor([&]{return !transition->property("moving").toBool()&&transition->property("progress").toDouble()==0;},2500);};
    for(int index=0;index<4;++index){check("warm-open-settles-"+QString::number(index),open(index));activityWait(80);check("warm-return-settles-"+QString::number(index),close());}
    fixture.connectionsAt=fixture.trafficAt=QDateTime::currentMSecsSinceEpoch();telemetry->ingest(fixture);activityWait(350);
    const QStringList tableNames={"activitySourcesTable","connectionTable","activityTransferHistoryTable","trafficRankingTable"};
    std::array<QQuickItem *,4> tables{};std::array<int,4> rowChanges{},projections{};
    std::vector<std::unique_ptr<RouteBenchSignalTap>> taps;
    for(int index=0;index<4;++index){
        tables[index]=activityVisual(window->contentItem(),tableNames[index]);check("table-present-"+tableNames[index],tables[index]!=nullptr);
        if(!tables[index])continue;
        auto rowsTap=std::make_unique<RouteBenchSignalTap>();rowsTap->callback=[&,index]{++rowChanges[index];};QQmlProperty(tables[index],"rows").connectNotifySignal(rowsTap.get(),SLOT(record()));taps.push_back(std::move(rowsTap));
        for(auto *model:tables[index]->findChildren<QObject *>())if(model->metaObject()->indexOfSignal("synced()")>=0){auto tap=std::make_unique<RouteBenchSignalTap>();tap->callback=[&,index]{++projections[index];};QObject::connect(model,SIGNAL(synced()),tap.get(),SLOT(record()));taps.push_back(std::move(tap));break;}
    }
    check("real-model-retains-all-connections",telemetry->connections().size()==rowCount);
    auto *scrollViewport=tables[1]?activityVisual(tables[1],"tableRowsViewport"):nullptr;
    auto *detailBody=qvariant_cast<QQuickItem *>(transition->property("bodyItem"));
    check("scroll-observation-uses-real-detail-viewport",scrollViewport&&detailBody);
    auto *weave=activityVisual(window->contentItem(),"activityCloudKnotWeave");
    auto *registry=eval(window,"SwirlTransitionRegistry").value<QObject *>();
    const QStringList cardNames={"activityStatusCard","activityTrafficCard","activitySourcesCard","activityDiagnosticCard","activityConnectionsCard"};
    std::array<QQuickItem *,5> cards{};bool allCardsPresent=true;for(int index=0;index<int(cards.size());++index){cards[index]=activityVisual(window->contentItem(),cardNames[index]);allCardsPresent=allCardsPresent&&cards[index];}
    check("phase-clock-observation-uses-real-weave-and-registry",weave&&registry);
    check("phase-clock-observation-uses-all-five-activity-cards",allCardsPresent);
    const auto clockSnapshot=[&]{Clocks value;value.weavePresent=weave!=nullptr;
        if(weave){value.weaveProgress=weave->property("progress").toDouble();value.weaveRelease=weave->property("release").toDouble();value.weaveMoving=weave->property("moving").toBool();value.weaveActive=weave->property("active").toBool();value.weavePresentationActive=weave->property("presentationActive").toBool();}
        if(registry)value.registryActive=registry->property("activeCount").toInt();
        for(int index=0;index<int(cards.size());++index)if(auto *card=cards[index]){value.cardPresent[index]=true;value.cardLift[index]=card->property("lift").toDouble();value.cardHovered[index]=card->property("hovered").toBool();value.cardFocused[index]=card->property("focused").toBool();}
        return value;};
    const auto warmedClocks=clockSnapshot();
    check("inactive-overview-has-no-same-endpoint-weave-animation",warmedClocks.weavePresent&&!warmedClocks.weaveActive
        &&warmedClocks.weaveProgress==0&&warmedClocks.weaveRelease==1&&!warmedClocks.weaveMoving);
    std::vector<Frame> frames(20000);size_t frameCount=0;bool frameOverflow=false;int currentPhase=-1,currentCycle=-1;
    std::array<Phase,12> phases;int phaseCount=0;
    std::array<double,128> ingestTimes{},prepareTimes{};std::array<Update,128> updateSamples{};int updateCount=0,realUpdateCount=0,heartbeatCount=0;bool updateOverflow=false;
    std::array<Scroll,128> scrollSamples{};size_t scrollCount=0;bool scrollOverflow=false,returningWithScroll=false;
    QElapsedTimer elapsed;elapsed.start();bool timedOut=false;
    const auto sample=[&](int kind){if(frameCount>=frames.size()){frameOverflow=true;return;}auto &frame=frames[frameCount++];frame.ns=elapsed.nsecsElapsed();frame.phase=currentPhase;frame.cycle=currentCycle;frame.kind=kind;frame.progress=transition->property("progress").toDouble();frame.moving=transition->property("moving").toBool();frame.opened=transition->property("opened").toBool();frame.destination=clock?int(clock->property("destination").toDouble()):-1;frame.active=window->isActive();frame.exposed=window->isExposed();frame.visible=window->isVisible();frame.visibility=int(window->visibility());};
    {
    // A local receiver removes queued frame deliveries before the later reentry
    // checks and before any of the captured measurement storage is destroyed.
    QObject measurementContext;
    QTimer watchdog;watchdog.setSingleShot(true);QObject::connect(&watchdog,&QTimer::timeout,&measurementContext,[&]{timedOut=true;qApp->exit(5);});watchdog.start(45000);
    const auto frameConnection=QObject::connect(window,&QQuickWindow::frameSwapped,&measurementContext,[&]{sample(0);},Qt::QueuedConnection);
    QTimer pulse;pulse.setTimerType(Qt::PreciseTimer);pulse.setInterval(500);
    QObject::connect(&pulse,&QTimer::timeout,&measurementContext,[&]{
        if(updateCount>=int(ingestTimes.size())){updateOverflow=true;return;}
        auto &observation=updateSamples[updateCount];observation.start=elapsed.nsecsElapsed();observation.phase=currentPhase;
        const auto uploadBefore=fixture.uploadTotal,downloadBefore=fixture.downloadTotal;
        QElapsedTimer preparation;preparation.start();
        if(updateCount%3!=2){
            for(int row=0;row<rowCount;++row){auto value=fixture.connections[row].toMap();const qint64 up=64+row%7,down=256+row%11;value["uploadBytes"]=value.value("uploadBytes").toLongLong()+up;value["downloadBytes"]=value.value("downloadBytes").toLongLong()+down;fixture.uploadTotal+=up;fixture.downloadTotal+=down;fixture.connections[row]=value;}
            fixture.connectionsAt=fixture.trafficAt=QDateTime::currentMSecsSinceEpoch();fixture.uploadRate=rowCount*134;fixture.downloadRate=rowCount*522;
        }else ++heartbeatCount;
        prepareTimes[updateCount]=preparation.nsecsElapsed()/1000000.0;
        observation.uploadTotal=fixture.uploadTotal;observation.downloadTotal=fixture.downloadTotal;
        observation.fixtureChanged=fixture.uploadTotal>uploadBefore&&fixture.downloadTotal>downloadBefore;
        observation.revisionBefore=telemetry->revision();observation.ingestStart=elapsed.nsecsElapsed();
        QElapsedTimer ingestion;ingestion.start();telemetry->ingest(fixture);ingestTimes[updateCount]=ingestion.nsecsElapsed()/1000000.0;
        observation.end=elapsed.nsecsElapsed();observation.revisionAfter=telemetry->revision();
        if(observation.fixtureChanged&&observation.revisionAfter>observation.revisionBefore)++realUpdateCount;
        ++updateCount;
    });
    const auto phase=[&](const QString &name,int duration,const std::function<void()> &work=std::function<void()>()){
        if(timedOut)return;
        auto &result=phases[phaseCount];currentPhase=phaseCount++;result.name=name;result.clocksBefore=clockSnapshot();result.start=elapsed.nsecsElapsed();result.before=resources();result.updatesBefore=updateCount;result.realUpdatesBefore=realUpdateCount;result.dataPulseActive=pulse.isActive();result.rowsBefore=rowChanges;result.syncBefore=projections;sample(1);
        if(work)work();else activityWait(duration);
        sample(2);result.after=resources();result.end=elapsed.nsecsElapsed();result.updatesAfter=updateCount;result.realUpdatesAfter=realUpdateCount;result.rowsAfter=rowChanges;result.syncAfter=projections;result.clocksAfter=clockSnapshot();
    };
    phase("quiet-home-cached",2500);
    pulse.start();phase("home-live-cached-details-hidden",3500);
    open(0);activityWait(100);phase("sources-visible-live",3000);close();
    open(3);activityWait(100);phase("connections-visible-live",3000);
    QTimer scroll;scroll.setTimerType(Qt::PreciseTimer);scroll.setInterval(80);int scrollTick=0;
    QObject::connect(&scroll,&QTimer::timeout,&measurementContext,[&]{
        if(!tables[1]||!scrollViewport||!detailBody)return;
        if(scrollCount>=scrollSamples.size()){scrollOverflow=true;return;}
        auto &observation=scrollSamples[scrollCount++];observation.ns=elapsed.nsecsElapsed();observation.phase=currentPhase;
        observation.before=tables[1]->property("scrollPosition").toDouble();observation.progress=transition->property("progress").toDouble();
        observation.moving=transition->property("moving").toBool();observation.opened=transition->property("opened").toBool();
        observation.returning=returningWithScroll;observation.pulseActive=pulse.isActive();observation.bodyOpacity=detailBody->opacity();
        observation.visibleRect=scrollViewport->mapRectToItem(window->contentItem(),QRectF(QPointF(),scrollViewport->size()));
        observation.effectiveOpacity=1;bool inDetailBody=false,visible=true;
        for(auto *item=scrollViewport;item;item=item->parentItem()){
            inDetailBody=inDetailBody||item==detailBody;visible=visible&&item->isVisible();observation.effectiveOpacity*=item->opacity();
            if(item->clip())observation.visibleRect=observation.visibleRect.intersected(item->mapRectToItem(window->contentItem(),QRectF(QPointF(),item->size())));
        }
        observation.visibleRect=observation.visibleRect.intersected(QRectF(QPointF(),window->size()));
        observation.presented=inDetailBody&&visible&&window->isVisible()&&window->isExposed()
            &&observation.effectiveOpacity>0&&observation.visibleRect.width()>0&&observation.visibleRect.height()>0;
        const double first=scrollViewport->property("originY").toDouble();
        const double last=first+qMax(0.0,scrollViewport->property("contentHeight").toDouble()-scrollViewport->height());
        observation.requested=qBound(first,observation.before+((scrollTick++/18)%2?-80:80),last);
        // Details remain live and clipped during travel. Model projection and
        // new input are deliberately paused; do not scroll a hidden viewport.
        if(observation.presented)tables[1]->setProperty("scrollPosition",observation.requested);
        observation.after=tables[1]->property("scrollPosition").toDouble();
    });
    scroll.start();const int scrollPhase=phaseCount;phase("connections-scroll-live",3500);
    check("scroll-live-phase-ingests-real-updates",scrollPhase<phaseCount&&phases[scrollPhase].realUpdatesAfter>phases[scrollPhase].realUpdatesBefore);
    bool scrollReturnSettled=false,returnPulseActive=false;
    // This is the existing close, now measured while the same scroll timer is
    // still running. A 300ms return need not receive a 500ms data pulse.
    phase("connections-scroll-return-live",0,[&]{returningWithScroll=true;returnPulseActive=pulse.isActive();scrollReturnSettled=close();returnPulseActive=returnPulseActive&&pulse.isActive();returningWithScroll=false;});
    scroll.stop();check("scroll-return-settles",scrollReturnSettled);check("live-data-pulse-remains-active-during-scroll-return",returnPulseActive);
    phase("shared-card-animation-live",0,[&]{for(int cycle=0;cycle<8&&!timedOut;++cycle){currentCycle=cycle;sample(3);check("measured-open-settles-"+QString::number(cycle),open(cycle%4));sample(4);activityWait(80);sample(5);check("measured-return-settles-"+QString::number(cycle),close());sample(6);activityWait(80);}currentCycle=-1;});
    phase("home-live-after-animation-details-hidden",4000);
    pulse.stop();phase("quiet-home-after-live",2500);
    QObject::disconnect(frameConnection);watchdog.stop();
    }
    const auto finalResources=resources();
    bool chronologicalUpdates=updateCount>0,allUpdatesPublished=true,expectedFixtureChanges=true;
    qint64 previousUpdate=-1;
    for(int index=0;index<updateCount;++index){const auto &value=updateSamples[index];chronologicalUpdates=chronologicalUpdates&&value.start>previousUpdate&&value.ingestStart>=value.start&&value.end>=value.ingestStart;previousUpdate=value.start;allUpdatesPublished=allUpdatesPublished&&value.revisionAfter>value.revisionBefore;expectedFixtureChanges=expectedFixtureChanges&&value.fixtureChanged==(index%3!=2);}
    check("real-update-and-identical-heartbeat-ingestions-occur",realUpdateCount>0&&heartbeatCount>0&&allUpdatesPublished&&expectedFixtureChanges);
    check("update-observations-have-monotonic-ingestion-timestamps",chronologicalUpdates);
    for(int index=0;index<phaseCount;++index){const auto &value=phases[index];if(value.dataPulseActive&&value.name!="connections-scroll-return-live")check("real-updates-observed-in-"+value.name,value.realUpdatesAfter>value.realUpdatesBefore);}
    int visibleScrollSteps=0,returnScrollSteps=0;double visibleScrollDistance=0,returnScrollDistance=0;bool returnScrollPulseActive=true;
    for(size_t index=0;index<scrollCount;++index){const auto &value=scrollSamples[index];const double distance=qAbs(value.after-value.before);if(value.presented&&distance>0){++visibleScrollSteps;visibleScrollDistance+=distance;if(value.returning&&value.moving&&!value.opened){++returnScrollSteps;returnScrollDistance+=distance;returnScrollPulseActive=returnScrollPulseActive&&value.pulseActive;}}}
    check("live-visible-connection-viewport-actually-scrolls",visibleScrollSteps>0&&visibleScrollDistance>0);
    check("visible-scrolling-overlaps-return-animation-with-live-data-pulse",returnScrollSteps>0&&returnScrollDistance>0&&returnScrollPulseActive);
    // The five-card page reads its native telemetry directly. Verify the
    // service and the visible fact instead of the removed page-level alias.
    auto *connectionsCard=activityVisual(window->contentItem(),"activityConnectionsCard");
    QQuickItem *deviceFact=nullptr;int deviceFacts=0;
    if(connectionsCard)for(auto *candidate:connectionsCard->findChildren<QObject *>()){
        if(candidate->property("caption").toString()==QStringLiteral("非本机来源")){
            deviceFact=qobject_cast<QQuickItem *>(candidate);++deviceFacts;
        }
    }
    check("home-device-count-preserved",telemetry->activeDevices()==64&&deviceFacts==1&&deviceFact
        &&deviceFact->isVisible()&&deviceFact->opacity()>0&&deviceFact->property("value").isValid()
        &&deviceFact->property("value").toString()==QStringLiteral("64"));
    open(0);activityWait(350);
    auto *sourcePage=tables[0]?tables[0]->parent():nullptr;while(sourcePage&&sourcePage->metaObject()->indexOfProperty("sourceRows")<0)sourcePage=sourcePage->parent();
    double sourceTotal=0;for(const auto &value:telemetry->ranking("apps",0,0))sourceTotal+=value.toMap().value("total").toDouble();
    check("reentry-displays-complete-latest-source-values",sourcePage&&qAbs(invoke(sourcePage,"sourceRows.reduce((sum,row)=>sum+row.total,0)").toDouble()-sourceTotal)<0.01);close();
    open(3);activityWait(350);
    auto *connectionPage=tables[1]?tables[1]->parent():nullptr;while(connectionPage&&connectionPage->metaObject()->indexOfProperty("connectionRows")<0)connectionPage=connectionPage->parent();
    check("reentry-displays-latest-connection-values",connectionPage&&invoke(connectionPage,"connectionRows.find(row=>row.id==='perf-0000').downloadBytes").toLongLong()==fixture.connections.first().toMap().value("downloadBytes").toLongLong());close();
    const auto finalConnections=telemetry->connections();qint64 actualFirstDownload=-1;
    for(const auto &value:finalConnections){const auto record=value.toMap();if(record.value("id").toString()=="perf-0000"){actualFirstDownload=record.value("downloadBytes").toLongLong();break;}}
    check("real-telemetry-record-advanced-through-every-changing-pulse",realUpdateCount>0&&actualFirstDownload==4096+qint64(realUpdateCount)*256);
    check("all-real-connection-records-preserved",finalConnections.size()==rowCount);
    check("no-proxy-setting-mutation",SystemProxySession::snapshot()==proxyBefore);
    check("automatic-network-measurement-did-not-run",telemetry->measurementState()==initialMeasurement);
    check("bounded-session-completed",!timedOut);
    check("all-frame-and-update-records-fit-fixed-buffers",!frameOverflow&&!updateOverflow&&!scrollOverflow);
    QJsonArray phaseJson,rawFrames,updates,scrollObservations;
    const auto resourceJson=[](const Resources &value){return QJsonObject{{"cpuMs",value.cpuMs},{"privateBytes",qint64(value.privateBytes)},{"workingSetBytes",qint64(value.workingSet)}};};
    const auto clockJson=[&](const Clocks &value){QJsonArray cardStates;for(int index=0;index<int(cards.size());++index)cardStates.append(QJsonObject{{"name",cardNames[index]},{"present",value.cardPresent[index]},{"lift",value.cardLift[index]},{"hovered",value.cardHovered[index]},{"focused",value.cardFocused[index]}});
        return QJsonObject{{"weavePresent",value.weavePresent},{"weaveProgress",value.weaveProgress},{"weaveRelease",value.weaveRelease},{"weaveMoving",value.weaveMoving},{"weaveActive",value.weaveActive},{"weavePresentationActive",value.weavePresentationActive},{"registryActive",value.registryActive},{"cards",cardStates}};};
    for(int index=0;index<phaseCount;++index){const auto &value=phases[index];QJsonArray changes,syncs;for(int table=0;table<4;++table){changes.append(value.rowsAfter[table]-value.rowsBefore[table]);syncs.append(value.syncAfter[table]-value.syncBefore[table]);}const double wall=(value.end-value.start)/1000000.0,cpu=value.after.cpuMs-value.before.cpuMs;
        phaseJson.append(QJsonObject{{"name",value.name},{"startMs",value.start/1000000.0},{"endMs",value.end/1000000.0},{"wallMs",wall},{"processCpuMs",cpu},{"oneCoreCpuPercent",wall>0?cpu/wall*100:0},{"before",resourceJson(value.before)},{"after",resourceJson(value.after)},{"clocksBefore",clockJson(value.clocksBefore)},{"clocksAfter",clockJson(value.clocksAfter)},{"modelUpdates",value.updatesAfter-value.updatesBefore},{"realUpdates",value.realUpdatesAfter-value.realUpdatesBefore},{"dataPulseActive",value.dataPulseActive},{"rowsNotifications",changes},{"modelProjectionSignals",syncs}});}
    for(size_t index=0;index<frameCount;++index){const auto &frame=frames[index];rawFrames.append(QJsonObject{{"timeMs",frame.ns/1000000.0},{"phase",frame.phase},{"cycle",frame.cycle},{"kind",frame.kind},{"progress",frame.progress},{"moving",frame.moving},{"opened",frame.opened},{"destination",frame.destination},{"active",frame.active},{"exposed",frame.exposed},{"visible",frame.visible},{"visibility",frame.visibility}});}
    for(int index=0;index<updateCount;++index){const auto &value=updateSamples[index];updates.append(QJsonObject{{"index",index},{"timeMs",value.start/1000000.0},{"ingestStartMs",value.ingestStart/1000000.0},{"ingestEndMs",value.end/1000000.0},{"phase",value.phase},{"prepareMs",prepareTimes[index]},{"ingestMs",ingestTimes[index]},{"identicalHeartbeat",index%3==2},{"fixtureChanged",value.fixtureChanged},{"uploadTotal",value.uploadTotal},{"downloadTotal",value.downloadTotal},{"revisionBefore",value.revisionBefore},{"revisionAfter",value.revisionAfter}});}
    for(size_t index=0;index<scrollCount;++index){const auto &value=scrollSamples[index];scrollObservations.append(QJsonObject{{"timeMs",value.ns/1000000.0},{"phase",value.phase},{"before",value.before},{"requested",value.requested},{"after",value.after},{"progress",value.progress},{"moving",value.moving},{"opened",value.opened},{"returning",value.returning},{"bodyOpacity",value.bodyOpacity},{"effectiveOpacity",value.effectiveOpacity},{"visibleRect",QJsonObject{{"x",value.visibleRect.x()},{"y",value.visibleRect.y()},{"width",value.visibleRect.width()},{"height",value.visibleRect.height()}}},{"visibleInWindow",value.presented},{"dataPulseActive",value.pulseActive}});}
    QJsonObject scrolling{{"visibleSteps",visibleScrollSteps},{"visibleDistance",visibleScrollDistance},{"returnVisibleSteps",returnScrollSteps},{"returnVisibleDistance",returnScrollDistance},{"observations",scrollObservations}};
    QJsonObject report{{"rows",rowCount},{"checks",checks},{"failures",failures},{"qt",qVersion()},{"renderer",int(window->rendererInterface()->graphicsApi())},{"dpr",window->devicePixelRatio()},{"refreshHz",window->screen()?window->screen()->refreshRate():0},{"phases",phaseJson},{"frames",rawFrames},{"updates",updates},{"realUpdates",realUpdateCount},{"identicalHeartbeats",heartbeatCount},{"scrolling",scrolling},{"tableNames",QJsonArray::fromStringList(tableNames)},{"finalResources",resourceJson(finalResources)},{"methods",QJsonArray{"Same deterministic authenticated-adapter-shaped records enter the actual isolated TelemetryService, without starting a proxy or network engine.","500ms pulses alternate two real byte/timestamp changes with one identical heartbeat. Fixture preparation and ingestion durations, monotonic observation timestamps and actual service revisions are recorded separately.","Frame completion callbacks capture GUI-side motion/exposure context; they are not exact render-time or hardware-presentation observations. Every observed frame/event remains in the raw record.","Quiet/static phases and active transitions must be analyzed separately, retaining boundaries and inactive/exposure changes.","The existing connection-detail return runs with the scroll and data timers still active. Scroll observations require a live list viewport with positive effective opacity and a positive intersection through every ancestor clip and the native window; hidden lists are not scrolled. These are GUI-state observations, not hardware-presentation measurements.","Detail model projection and new input intentionally pause during transition. Continued visible scrolling does not require a model refresh or a 500ms data pulse inside the shorter return animation; real ingestion is asserted in the preceding sustained live phase.","Frame, update and scroll storage is fixed and initialized before measurement. JSON serialization and screenshots are excluded from timing. Model row notifications/projection signals are counted without per-event allocation.","CPU is process user+kernel time, expressed as a percentage of one CPU core; private commit and working set are separate. Finite measurements are not unlimited leak proof."}}};
    QDir().mkpath(QFileInfo(output).absolutePath());QFile file(output);if(!file.open(QIODevice::WriteOnly))return 2;file.write(QJsonDocument(report).toJson());
    qInfo()<<"ACTIVITY_PERF_RESULT"<<rowCount<<failures<<"updates"<<updateCount<<"frames"<<frameCount;return failures?1:0;
}
