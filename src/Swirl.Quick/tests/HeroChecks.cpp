#include "HeroChecks.h"
#include "NavigationChecks.h"
#include "engine/EngineController.h"
#include "app/NodeViewModel.h"
#include "app/MotionPolicy.h"
#include <QQuickWindow>
#include <QQuickItem>
#include <QJSValue>
#include <QRegion>
#include <QQmlContext>
#include <QQmlExpression>
#include <QGuiApplication>
#include <QScreen>
#include <QTest>
#include <QEventLoop>
#include <QTimer>
#include <QElapsedTimer>
#include <QJsonObject>
#include <QJsonArray>
#include <QJsonDocument>
#include <QFile>
#include <QDir>
#include <QSet>
#include <QPainter>
#include <QCoreApplication>
#include <QCursor>
#include <QMutex>
#include <QMutexLocker>
#include <functional>
#include <algorithm>
#include <atomic>
#ifdef Q_OS_WIN
#include <windows.h>
#include <psapi.h>
#include <private/qrhid3d11_p.h>
#endif
static QJsonObject heroProcessResources(){
#ifdef Q_OS_WIN
 PROCESS_MEMORY_COUNTERS_EX memory{};memory.cb=sizeof(memory);GetProcessMemoryInfo(GetCurrentProcess(),reinterpret_cast<PROCESS_MEMORY_COUNTERS *>(&memory),sizeof(memory));
 FILETIME creation{},exit{},kernel{},user{};GetProcessTimes(GetCurrentProcess(),&creation,&exit,&kernel,&user);ULARGE_INTEGER k{},u{};k.LowPart=kernel.dwLowDateTime;k.HighPart=kernel.dwHighDateTime;u.LowPart=user.dwLowDateTime;u.HighPart=user.dwHighDateTime;
 return {{"privateBytes",double(memory.PrivateUsage)},{"workingSetBytes",double(memory.WorkingSetSize)},{"cpuMs",double(k.QuadPart+u.QuadPart)/10000},{"gdiHandles",int(GetGuiResources(GetCurrentProcess(),GR_GDIOBJECTS))},{"userHandles",int(GetGuiResources(GetCurrentProcess(),GR_USEROBJECTS))}};
#else
 return {};
#endif
}
int runHeroChecks(QQuickWindow *window,EngineController *controller,const QString &directory) {
 if(!window||!controller)return 3;QDir().mkpath(directory);
 auto wait=[](int milliseconds){QEventLoop loop;QTimer timer;timer.setTimerType(Qt::PreciseTimer);timer.setSingleShot(true);QObject::connect(&timer,&QTimer::timeout,&loop,&QEventLoop::quit);timer.start(milliseconds);loop.exec();};
 QJsonArray checks;int failures=0;QJsonArray nodeClickMs;QJsonArray settingsRetargetSamples;
 auto check=[&](bool value,const QString &name){checks.append(QJsonObject{{"name",name},{"passed",value}});if(!value)++failures;qInfo()<<"HERO_CHECK"<<name<<value;};
 auto eval=[&](const QString &code){QQmlExpression expression(qmlContext(window),window,code);auto result=expression.evaluate();if(expression.hasError()){++failures;qWarning()<<expression.error();}return result;};
 auto *policy=qobject_cast<MotionPolicy *>(qmlContext(window)->contextProperty("motionPolicy").value<QObject *>());
 if(!policy)return 3;
 const bool actualSystemReducedMotion=policy->systemReducedMotion();
 struct RestoreSystemMotion {MotionPolicy *policy;~RestoreSystemMotion(){policy->setSystemReducedMotionOverrideForTest(-1);}} restoreSystemMotion{policy};
 policy->setSystemReducedMotionOverrideForTest(0);
 qInfo()<<"HERO_MOTION_POLICY"<<"actualSystemReducedMotion"<<actualSystemReducedMotion<<"fixtureOverride"<<0;
 std::function<QQuickItem *(QQuickItem *,const QString &)> find;
 find=[&](QQuickItem *parent,const QString &name)->QQuickItem *{if(parent->objectName()==name&&parent->isVisible())return parent;for(auto child:parent->childItems())if(auto match=find(child,name))return match;return nullptr;};
 auto item=[&](const QString &name,QQuickWindow *owner=nullptr){return find((owner?owner:window)->contentItem(),name);};
 auto click=[&](const QString &name,QQuickWindow *owner=nullptr){auto control=item(name,owner);if(!control){check(false,"input exists: "+name);return;}QTest::mouseClick(owner?owner:window,Qt::LeftButton,Qt::NoModifier,control->mapToScene(QPointF(control->width()/2,control->height()/2)).toPoint());};
 auto route=[&](const QString &name){eval("AppState.navigate('"+name+"')");wait(350);};
 const bool recording=!QCoreApplication::arguments().contains("--hero-no-recording")&&!qEnvironmentVariableIsSet("SWIRL_QA_NO_RECORDING");
 auto snapshot=[&](const QString &name,QQuickWindow *sheet=nullptr){if(!recording)return true;auto image=window->grabWindow();QPainter painter(&image);if(sheet&&sheet->isVisible())painter.drawImage(sheet->position()-window->position(),sheet->grabWindow());painter.end();return image.save(directory+"/"+name+".png");};
 auto record=[&](const QString &name,QQuickWindow *sheet=nullptr){if(!recording)return;QDir().mkpath(directory+"/"+name);QElapsedTimer clock;clock.start();QJsonArray timestamps;for(int frame=0;frame<26;++frame){const auto file=QString("%1.png").arg(frame,3,10,QChar('0'));const auto start=clock.nsecsElapsed()/1000000.0;snapshot(name+"/"+file.chopped(4),sheet);timestamps.append(QJsonObject{{"file",file},{"captureStartMs",start},{"captureEndMs",clock.nsecsElapsed()/1000000.0}});wait(10);}QFile output(directory+"/"+name+"/frame-timestamps.json");if(output.open(QIODevice::WriteOnly))output.write(QJsonDocument(QJsonObject{{"frames",timestamps},{"durationMs",clock.nsecsElapsed()/1000000.0},{"method","Actual monotonic readback times; requested 10ms waits are not an assumed frame rate. Qt window readbacks do not capture the final DWM desktop contour."}}).toJson());};
 // Native pointer input must fit the actual monitor, including the smaller
 // Hyper-V desktop used by CI. Off-screen QTest presses can otherwise succeed
 // while the real cursor is clamped away from the same button's hover target.
 const auto available=window->screen()->availableGeometry();
 const QSize fixtureSize(qMax(window->minimumWidth(),qMin(1100,available.width())),qMax(window->minimumHeight(),qMin(850,available.height())));
 window->resize(fixtureSize);
 window->setPosition(available.topLeft()+QPoint(qMax(0,(available.width()-fixtureSize.width())/2),qMax(0,(available.height()-fixtureSize.height())/2)));
 window->show();window->requestActivate();
#ifdef Q_OS_WIN
 window->setFlag(Qt::WindowStaysOnTopHint,true);
 const HWND qaWindow=reinterpret_cast<HWND>(window->winId());
 SetWindowPos(qaWindow,HWND_TOPMOST,0,0,0,0,SWP_NOMOVE|SWP_NOSIZE|SWP_NOACTIVATE);
 struct RestoreQaStack {QQuickWindow *window;~RestoreQaStack(){window->setFlag(Qt::WindowStaysOnTopHint,false);}} restoreQaStack{window};
#endif
 eval("Theme.mode='Light';Theme.transparency=true;Theme.reduceMotion=false;SwirlMotion.speed=1;AppState.navigate('featurehub')");
 check(!eval("SwirlMotion.reduced").toBool(),"animated fixture resolves independently of the Windows accessibility preference");
 const QStringList settingsRoutes{"settings","dns","modules","profiles","scripts","subscriptions","proxies"};
 const QString hubStateScript=QStringLiteral("JSON.stringify({route:AppState.currentPage,activeRoute:pageLoader.activeLoader?pageLoader.activeLoader.routeId:'',hasItem:pageLoader.item!==null,moving:pageLoader.moving,pending:pageLoader.pendingGrab,preparing:pageLoader.preparing,registry:SwirlTransitionRegistry.activeCount,dismissals:dismissals.count})");
 const auto initialHubState=QJsonDocument::fromJson(eval(hubStateScript).toString().toUtf8()).object();
 QElapsedTimer hubReadiness;hubReadiness.start();
 // Cold pages incubate across frames. A fixed delay can observe the previous
 // page, then mistake its late navigation animation for the first card opening.
 const bool hubReady=QTest::qWaitFor([&]{
  if(!window->isExposed()||!eval("AppState.currentPage==='featurehub' && pageLoader.item && pageLoader.activeLoader && pageLoader.activeLoader.routeId==='featurehub' && !pageLoader.moving && !pageLoader.pendingGrab && SwirlTransitionRegistry.activeCount===0 && dismissals.count===0").toBool())return false;
  for(const auto &name:settingsRoutes){const auto *card=item("settings-"+name);if(!card||!card->isEnabled()||card->width()<=0||card->height()<=0)return false;}
  return true;
 },4000);
 QJsonArray hubCards;
 for(const auto &name:settingsRoutes){const auto *card=item("settings-"+name);hubCards.append(QJsonObject{{"route",name},{"visible",card!=nullptr},{"enabled",card&&card->isEnabled()},{"width",card?card->width():0},{"height",card?card->height():0}});}
 const QJsonObject hubReadyEvidence{{"initial",initialHubState},{"settled",QJsonDocument::fromJson(eval(hubStateScript).toString().toUtf8()).object()},{"elapsedMs",hubReadiness.elapsed()},{"ready",hubReady},{"cards",hubCards}};
 QFile hubEvidence(directory+"/featurehub-ready.json");if(!hubEvidence.open(QIODevice::WriteOnly))return 3;
 hubEvidence.write(QJsonDocument(hubReadyEvidence).toJson());hubEvidence.close();
 check(hubReady,"featurehub route and all seven cards settle before hero input");
 if(qApp->arguments().contains("--hero-material-only")){
  QJsonArray samples;
  QSet<QString> capturedPhases;
  int darkFrames=0;
  const QString stateScript=QStringLiteral(R"JS(JSON.stringify((function(){
   function describe(item){if(!item)return null;const p=item.mapToItem(window.contentItem,0,0);const c=item.color;return {name:item.objectName,x:p.x,y:p.y,width:item.width,height:item.height,visible:item.visible,opacity:item.opacity,surfaceHidden:item.surfaceHidden===true,color:c?{r:c.r,g:c.g,b:c.b,a:c.a}:null}}
   const h=pageLoader,hero=h.children.filter(item=>item.objectName==='pageHeroTitle')[0];return {route:AppState.currentPage,progress:h.position,moving:h.moving,preparing:h.preparing,surfaceKind:h.surfaceKind,heroData:h.heroData?{key:h.heroData.key,returning:h.heroData.returning,fromColor:h.heroData.fromColor,toColor:h.heroData.toColor}:null,source:describe(h.sourceSurface),target:describe(h.targetSurface),sourceTitle:describe(hero?hero.sourceItem:null),targetTitle:describe(hero?hero.targetItem:null),sharedTitle:describe(hero?hero.labelItem:null),morph:describe(h.children[0].children.filter(item=>item.objectName==='sharedSurface')[0]),layers:Object.keys(h.pages).map(key=>({route:key,visible:h.pages[key].visible,opacity:h.pages[key].opacity,z:h.pages[key].z})),registry:SwirlTransitionRegistry.activeCount,dismissals:dismissals.count}
  })()))JS");
  auto sampleMaterial=[&](const QString &phase){
   auto state=QJsonDocument::fromJson(eval(stateScript).toString().toUtf8()).object();
   auto *surface=item("sharedSurface");
   if(!surface)return;
   QElapsedTimer readback;readback.start();
   const auto frame=window->grabWindow().convertToFormat(QImage::Format_ARGB32);
   state["readbackMs"]=readback.nsecsElapsed()/1000000.0;
   state["phase"]=phase;
   state["frame"]=samples.size();
   if(!frame.isNull()&&state.value("progress").toDouble()>=0.5&&!capturedPhases.contains(phase)){
    const auto filename="material-"+phase+"-half.png";
    frame.save(directory+"/"+filename);state["image"]=filename;capturedPhases.insert(phase);
   }
   if(!frame.isNull()&&surface->width()>32&&surface->height()>32){
    QList<int> reds,greens,blues;
    for(int y=1;y<=5;++y)for(int x=1;x<=5;++x){
     const auto p=surface->mapToScene(QPointF(surface->width()*x/6,surface->height()*y/6))*window->devicePixelRatio();
     if(frame.rect().contains(p.toPoint())){const auto c=frame.pixelColor(p.toPoint());reds.append(c.red());greens.append(c.green());blues.append(c.blue());}
    }
    if(!reds.isEmpty()){
     std::sort(reds.begin(),reds.end());std::sort(greens.begin(),greens.end());std::sort(blues.begin(),blues.end());
     const int middle=reds.size()/2;
     state["backgroundMedianRgb"]=QJsonArray{reds[middle],greens[middle],blues[middle]};
     const bool dark=qMin(reds[middle],qMin(greens[middle],blues[middle]))<210;
     state["unexpectedDarkFrame"]=dark;
     if(dark){++darkFrames;frame.save(directory+QString("/material-dark-%1.png").arg(samples.size(),3,10,QChar('0')));}
    }
   }
   samples.append(state);
  };
  auto settled=[&]{return eval("pageLoader.item && !pageLoader.moving && !pageLoader.pendingGrab && pageLoader.activeLoader.routeId===AppState.currentPage").toBool();};
  auto observe=[&](const QString &phase,double until=1.0){
   QElapsedTimer timer;timer.start();bool started=false;
   do{wait(16);started|=eval("pageLoader.moving").toBool();sampleMaterial(phase);
    if(started&&(settled()||(until<1&&eval("pageLoader.position").toDouble()>=until)))return true;
   }while(timer.elapsed()<4500);
   return false;
  };
  auto pressCard=[&](const QString &name){
   auto *card=item("settings-"+name);check(card!=nullptr,"material fixture card is reachable: "+name);if(!card)return;
   const auto point=card->mapToScene(QPointF(card->width()/2,card->height()/2)).toPoint();
   QCursor::setPos(window->mapToGlobal(point));QTest::mouseMove(window,point);wait(130);
   QTest::mousePress(window,Qt::LeftButton,Qt::NoModifier,point);wait(70);QTest::mouseRelease(window,Qt::LeftButton,Qt::NoModifier,point);
  };
  eval("SwirlMotion.speed=0.5");
  for(const auto &name:settingsRoutes){
   pressCard(name);check(observe(name+"-open")&&settled()&&eval("AppState.currentPage==='"+name+"'").toBool(),"material fixture expansion settles: "+name);
   QTest::keyClick(window,Qt::Key_Escape);check(observe(name+"-close")&&settled()&&eval("AppState.currentPage==='featurehub'").toBool(),"material fixture Escape return settles: "+name);
  }
  for(const double phase:{0.15,0.55,0.95}){
   const auto key=QString::number(phase,'f',2);
   pressCard("profiles");check(observe("reverse-open-"+key,phase),"material reversal reaches its actual opening phase: "+key);
   QTest::keyClick(window,Qt::Key_Escape);check(observe("reverse-close-"+key,0.15),"material reversal reaches its actual closing phase: "+key);
   pressCard("profiles");check(observe("reverse-reopen-"+key)&&settled(),"material fixture reopens the live card: "+key);
   QTest::keyClick(window,Qt::Key_Escape);check(observe("reverse-settle-"+key)&&settled(),"material fixture final Escape settles: "+key);
  }
  pressCard("profiles");check(observe("third-route-open",0.55),"material third-route fixture reaches an intermediate frame");
  eval("window.openSettings('scripts')");check(observe("third-route-change")&&settled(),"material third-route retarget settles");
  QTest::keyClick(window,Qt::Key_Escape);QTest::qWait(1000);
  check(eval("Object.keys(pageLoader.pages).filter(key=>pageLoader.pages[key].visible).length===1 && SwirlTransitionRegistry.activeCount===0 && dismissals.count===0").toBool(),"material fixture releases all outgoing layers and transition tokens");
  check(!samples.isEmpty()&&darkFrames==0,"opening, Escape, reversal and third-route frames retain the light card material");
  eval("SwirlMotion.speed=1");
  QFile output(directory+"/material-transition-report.json");if(!output.open(QIODevice::WriteOnly))return 3;
  output.write(QJsonDocument(QJsonObject{{"samples",samples},{"darkFrames",darkFrames},{"checks",checks},{"failures",failures},{"scope","Native D3D11 rendered mid-transition RGB plus live shared-surface/color/layer state. Screenshot readbacks are diagnostic only, not presentation performance measurements."}}).toJson());
  return failures?2:0;
 }
 check(item("settings-proxies")&&item("settings-subscriptions")&&!item("settings-license"),"More has direct node/subscription entries and no paid license entry");
 QString yaml="proxies:\n";for(int i=0;i<180;++i)yaml+=QString("  - {name: 'Fixture node %1', type: socks5, server: 127.0.0.1, port: %2}\n").arg(i,3,10,QChar('0')).arg(10000+i);
 controller->imports()->importText(yaml);check(QTest::qWaitFor([&]{return !controller->imports()->busy();},8000)&&controller->nodes().size()==180,"180 synthetic node records imported by the real importer for rendering stress only");
 failures+=runNavigationChecks(window,controller,directory);
 // Synthetic metadata stays in the application's isolated DPAPI test store.
 // No fixture is connected and no measured network result is fabricated.
 check(controller->imports()->saveSubscription("","Animation fixture",QUrl("https://fixture.invalid/subscription"),360,false),"subscription metadata saved by the actual encrypted store");
 const auto subscriptionId=controller->imports()->providers().first().toMap().value("id").toString();
 route("subscriptions");auto card=item("subscriptionCard-"+subscriptionId);const double collapsed=card?card->height():0;
 click("expandSubscription-"+subscriptionId);wait(50);
 check(card&&card->height()>collapsed&&card->property("reveal").toDouble()>0,"subscription expands its actual boundary immediately");
 record("subscription-open");check(card&&card==item("subscriptionCard-"+subscriptionId)&&card->property("expanded").toBool(),"expanded subscription keeps the same delegate and stable ID");
 click("expandSubscription-"+subscriptionId);record("subscription-return");check(QTest::qWaitFor([&]{return card&&!card->property("moving").toBool()&&qAbs(card->height()-collapsed)<0.5;},1000),"subscription returns to its original boundary");
 for(int i=0;i<8;++i){click("expandSubscription-"+subscriptionId);wait(15);}wait(350);
 check(card&&card==item("subscriptionCard-"+subscriptionId)&&!card->property("moving").toBool(),"rapid subscription reversals settle without replacement or a stuck clock");
 eval("Theme.reduceMotion=true");click("expandSubscription-"+subscriptionId);check(card&&!card->property("moving").toBool()&&card->property("reveal").toDouble()==1,"reduced motion commits final geometry directly");eval("Theme.reduceMotion=false");
 route("proxies");auto table=item("realNodeTable");
 if(table)QMetaObject::invokeMethod(table,"scrollToBeginning");wait(35);
 auto *nodeModel=window->findChild<NodeViewModel *>("nodeViewModel");
 check(table&&nodeModel&&nodeModel->rowCount()==180,"node list exposes all 180 records");
 if(table&&nodeModel){
  auto *viewport=find(table,"tableRowsViewport");
  std::function<QQuickItem *(QQuickItem *,const QString &)> findNodeRow;
  findNodeRow=[&](QQuickItem *parent,const QString &id)->QQuickItem *{
   const auto value=parent->property("record");
   const auto record=value.metaType()==QMetaType::fromType<QJSValue>()?value.value<QJSValue>().toVariant().toMap():value.toMap();
   qreal opacity=1;for(auto *ancestor=parent;ancestor;ancestor=ancestor->parentItem())opacity*=ancestor->opacity();
   const QPointF center(qMin(70.0,parent->width()/2),parent->height()/2);
   if(record.value("rowKind")=="node"&&record.value("id")==id&&!parent->property("pooled").toBool()
       &&parent->isVisible()&&parent->isEnabled()&&opacity>0.95&&viewport&&viewport->contains(parent->mapToItem(viewport,center)))return parent;
   for(auto *child:parent->childItems())if(auto *found=findNodeRow(child,id))return found;
   return nullptr;
  };
  auto rowAt=[&](int index)->QQuickItem *{
   const auto id=nodeModel->get(index).value("id").toString();
   const auto displayRow=eval(QString("pageLoader.item.sectionIndexForNode('%1')").arg(id)).toInt();
   if(viewport)QMetaObject::invokeMethod(viewport,"positionViewAtIndex",Q_ARG(int,displayRow),Q_ARG(int,0));
   QQuickItem *row=nullptr;
   const bool ready=QTest::qWaitFor([&]{row=findNodeRow(table,id);return row!=nullptr;},2000);
   check(ready,"requested source-grouped node delegate is visible before input");
   return row;
  };
  const auto point=[](QQuickItem *row){return row->mapToScene(QPointF(qMin(70.0,row->width()/2),row->height()/2)).toPoint();};
  const auto configuredExit=controller->selectedNodeId(),runningExit=controller->activeNodeId();
  const auto firstNode=nodeModel->get(1);
  auto *firstRow=rowAt(1);
  if(firstRow)QTest::mouseClick(window,Qt::LeftButton,Qt::NoModifier,point(firstRow));
  check(eval("pageLoader.item.focusedId").toString()==firstNode.value("id").toString(),"single-click browsing focuses the requested real node");
  check(controller->selectedNodeId()==configuredExit&&controller->activeNodeId()==runningExit,"single-click browsing preserves configured and running exits");
  QElapsedTimer response;response.start();
  if(firstRow)QTest::mouseDClick(window,Qt::LeftButton,Qt::NoModifier,point(firstRow));
  const double dispatchMs=response.nsecsElapsed()/1000000.0;nodeClickMs.append(dispatchMs);
  auto hero=item("nodeHero");auto identity=item("nodeIdentitySurface");auto requestSurface=item("nodeRequestSurface");
  check(eval("pageLoader.item.selectedId").toString()==firstNode.value("id").toString()&&firstNode.value("name")=="Fixture node 001","node inspection reaches the actual double-clicked row");
  check(controller->selectedNodeId()==configuredExit&&controller->activeNodeId()==runningExit,"opening node details preserves configured and running exits");
  check(item("nodeDetailTitle")&&item("nodeDetailTitle")->property("text").toString()==firstNode.value("name").toString(),"detail title updates in the click handler without an animation wait");
  check(hero&&hero->property("moving").toBool()&&identity&&requestSurface&&identity->isVisible(),"node selection starts the restored boundary transition with mounted detail controls");
  check(dispatchMs<100,"180-node click dispatch completes within 100 ms");
  qInfo()<<"NODE_CLICK_DISPATCH_MS"<<dispatchMs;record("node-local");
  check(QTest::qWaitFor([&]{return hero&&!hero->property("moving").toBool()&&requestSurface&&requestSurface->isVisible()&&requestSurface->opacity()>0.99;},2000),"detail controls reach full opacity after the boundary transition");
  const auto identityRect=identity?QRectF(identity->position(),identity->size()):QRectF();
  double slowest=dispatchMs;
  QString lastInspectedName=firstNode.value("name").toString();
  for(int i=0;i<10&&hero;++i){
   // U2 details cover the list. Clicking old row coordinates while the detail
   // is open hits its Edit button, not another node. Exercise actual visible
   // controls and require the requested node on every return/select cycle.
   click("nodeReturnButton");
   check(!hero->property("opened").toBool(),"return action closes details before another row is clicked");
   check(QTest::qWaitFor([&]{return !hero->property("moving").toBool();},2000),"node list becomes available after return");
   auto *row=rowAt(i%6);const auto expected=nodeModel->get(i%6);
   response.restart();if(row)QTest::mouseDClick(window,Qt::LeftButton,Qt::NoModifier,point(row));
   const auto ms=response.nsecsElapsed()/1000000.0;nodeClickMs.append(ms);slowest=qMax(slowest,ms);
   check(eval("pageLoader.item.selectedId").toString()==expected.value("id").toString()&&expected.value("name")==QString("Fixture node %1").arg(i%6,3,10,QChar('0')),"repeated visible row input inspects the requested real node");
   check(controller->selectedNodeId()==configuredExit&&controller->activeNodeId()==runningExit,"repeated node inspection preserves configured and running exits");
   lastInspectedName=expected.value("name").toString();
   check(QTest::qWaitFor([&]{return !hero->property("moving").toBool();},2000),"repeated selection settles its boundary");
  }
  check(item("nodeDetailTitle")&&item("nodeDetailTitle")->property("text").toString()==lastInspectedName,"repeated selection keeps the latest clicked node");
  check(identity&&identity==item("nodeIdentitySurface")&&QRectF(identity->position(),identity->size())==identityRect,"repeated selection retains the same inspector and settled geometry");
  check(slowest<100,"all repeated node click dispatches complete within 100 ms");qInfo()<<"NODE_CLICK_MAX_MS"<<slowest;
  check(table->scale()==1&&eval("motionPolicy.activeGrabCount===0 && SwirlTransitionRegistry.activeCount===0").toBool(),"settled node selection retains no table textures or transient transition resources");
  click("nodeReturnButton");record("node-return");
  check(hero&&!hero->property("opened").toBool(),"return closes the inspector immediately");
  check(QTest::qWaitFor([&]{return hero&&!hero->property("moving").toBool();},2000),"node list returns before the final detail input");
  if(auto *row=rowAt(3))QTest::mouseDClick(window,Qt::LeftButton,Qt::NoModifier,point(row));wait(50);
  check(controller->selectedNodeId()==configuredExit&&controller->activeNodeId()==runningExit,"final detail input preserves configured and running exits");
 }
 snapshot("nodes-180");check(!controller->processAlive(),"rendering fixture selection never starts a proxy or fabricates a connection");
 if(auto *search=item("nodeSearchField")) {
  QElapsedTimer filter;filter.start();search->setProperty("text","179");const double filterMs=filter.nsecsElapsed()/1000000.0;
  check(QTest::qWaitFor([&]{return nodeModel&&nodeModel->rowCount()==1&&nodeModel->get(0).value("name")=="Fixture node 179";},1000),"debounced tail search prunes a large prefix and keeps the real node ID");
  check(filterMs<100,"180-node tail filter input dispatch completes within 100 ms");qInfo()<<"NODE_FILTER_DISPATCH_MS"<<filterMs;
  search->setProperty("text","");check(QTest::qWaitFor([&]{return nodeModel&&nodeModel->rowCount()==180;},1000),"clearing search restores the entire catalog");
 }
 route("featurehub");snapshot("more");route("activity");snapshot("activity");eval("Theme.mode='Dark'");snapshot("activity-dark");eval("Theme.mode='Light'");
 eval("window.openDashboard()");wait(350);QQuickWindow *panel=nullptr;for(auto candidate:QGuiApplication::allWindows())if(candidate->objectName()=="dashboardWindow")panel=qobject_cast<QQuickWindow *>(candidate);
 check(panel&&panel->isVisible(),"real network panel opens in its native window");
 if(panel){
  auto page=find(panel->contentItem(),"dashboardPage"),tabs=find(panel->contentItem(),"dashboardTabs"),clear=find(panel->contentItem(),"dashboardClear");
  check(page&&tabs&&clear,"network panel keeps tabs, real data surface and scoped actions");
  if(page&&tabs&&clear){for(int i=0;i<6;++i){QTest::mouseClick(panel,Qt::LeftButton,Qt::NoModifier,tabs->mapToScene(QPointF((i+0.5)*tabs->width()/6,tabs->height()/2)).toPoint());wait(50);check(page->property("tabIndex").toInt()==i&&clear->isEnabled()==(i==0||i==5),QString("panel tab %1 switches and clearing is scoped correctly").arg(i));}}
  if(recording){panel->grabWindow().save(directory+"/panel-logs.png");if(tabs){QTest::mouseClick(panel,Qt::LeftButton,Qt::NoModifier,tabs->mapToScene(QPointF(2.5*tabs->width()/6,tabs->height()/2)).toPoint());wait(80);}auto surface=panel->grabWindow();surface.save(directory+"/panel-dns.png");check(eval("panelBackdrop.nativeCorners").toBool() || !panel->mask().isEmpty(),"panel contour is owned by DWM or the shared compatibility mask; raw Qt alpha is not the final desktop contour");}
  panel->hide();window->requestActivate();
 }
 // Passive native frame delivery measurements exclude all screenshot readback.
 auto qpcMs=[]()->double {
#ifdef Q_OS_WIN
  LARGE_INTEGER frequency,counter;QueryPerformanceFrequency(&frequency);QueryPerformanceCounter(&counter);return double(counter.QuadPart)*1000/frequency.QuadPart;
#else
  return 0;
#endif
 };
 const double performanceStart=qpcMs();QJsonArray animationWindows,refreshPhases;
 QList<double> intervals;QMutex mutex;QElapsedTimer elapsed;elapsed.start();qint64 previous=0;
 struct Presentation {double qpcMs;quint32 count,refresh,sync;double syncQpcMs;int hz;};
 QList<Presentation> presentations;std::atomic_int presentationHz{qRound(window->screen()->refreshRate())};quint32 previousPresent=0;int statisticsErrors=0;
 auto frameConnection=QObject::connect(window,&QQuickWindow::frameSwapped,window,[&]{const auto now=elapsed.nsecsElapsed();QMutexLocker guard(&mutex);if(previous){const double ms=(now-previous)/1000000.0;if(ms<100)intervals.append(ms);}previous=now;
#ifdef Q_OS_WIN
  if(window->rendererInterface()->graphicsApi()==QSGRendererInterface::Direct3D11){
   auto chain=static_cast<QD3D11SwapChain *>(window->rendererInterface()->getResource(window,QSGRendererInterface::RhiSwapchainResource));
   DXGI_FRAME_STATISTICS stats{};
   if(chain&&chain->swapChain&&SUCCEEDED(chain->swapChain->GetFrameStatistics(&stats))&&stats.PresentCount&&stats.SyncQPCTime.QuadPart){
    if(stats.PresentCount!=previousPresent){LARGE_INTEGER frequency;QueryPerformanceFrequency(&frequency);const auto syncMs=double(stats.SyncQPCTime.QuadPart)*1000/frequency.QuadPart;const int hz=presentationHz.load();
     presentations.append({syncMs+qint32(stats.PresentRefreshCount-stats.SyncRefreshCount)*1000.0/qMax(1,hz),stats.PresentCount,stats.PresentRefreshCount,stats.SyncRefreshCount,syncMs,hz});previousPresent=stats.PresentCount;}
   }else ++statisticsErrors;
  }
#endif
 },Qt::DirectConnection);
 const bool sweep=qApp->arguments().contains("--hero-refresh-sweep");
 auto resources=[]()->QJsonObject {
#ifdef Q_OS_WIN
  PROCESS_MEMORY_COUNTERS_EX memory{};memory.cb=sizeof(memory);GetProcessMemoryInfo(GetCurrentProcess(),reinterpret_cast<PROCESS_MEMORY_COUNTERS *>(&memory),sizeof(memory));
  FILETIME creation{},exit{},kernel{},user{};GetProcessTimes(GetCurrentProcess(),&creation,&exit,&kernel,&user);ULARGE_INTEGER k{},u{};k.LowPart=kernel.dwLowDateTime;k.HighPart=kernel.dwHighDateTime;u.LowPart=user.dwLowDateTime;u.HighPart=user.dwHighDateTime;
  return {{"privateBytes",double(memory.PrivateUsage)},{"workingSetBytes",double(memory.WorkingSetSize)},{"cpuMs",double(k.QuadPart+u.QuadPart)/10000},{"gdiHandles",int(GetGuiResources(GetCurrentProcess(),GR_GDIOBJECTS))},{"userHandles",int(GetGuiResources(GetCurrentProcess(),GR_USEROBJECTS))}};
#else
  return {};
#endif
 };
 const auto resourceBefore=resources();
#ifdef Q_OS_WIN
 MONITORINFOEXW display{};display.cbSize=sizeof(display);GetMonitorInfoW(MonitorFromWindow(reinterpret_cast<HWND>(window->winId()),MONITOR_DEFAULTTONEAREST),&display);
 DEVMODEW original{};original.dmSize=sizeof(original);EnumDisplaySettingsW(display.szDevice,ENUM_CURRENT_SETTINGS,&original);
 struct RestoreDisplay {LPCWSTR device;DEVMODEW mode;bool enabled;~RestoreDisplay(){if(enabled)ChangeDisplaySettingsExW(device,&mode,nullptr,0,nullptr);}} restoreDisplay{display.szDevice,original,sweep};
#endif
 for(int hz:sweep?QList<int>{60,120,144,165,240}:QList<int>{0}){
#ifdef Q_OS_WIN
  if(hz){DEVMODEW requested=original;requested.dmFields=DM_DISPLAYFREQUENCY;requested.dmDisplayFrequency=hz;
   const auto tested=ChangeDisplaySettingsExW(display.szDevice,&requested,nullptr,CDS_TEST,nullptr);
   if(tested!=DISP_CHANGE_SUCCESSFUL){refreshPhases.append(QJsonObject{{"requestedHz",hz},{"available",false},{"displayTestResult",int(tested)}});continue;}
   const auto changed=ChangeDisplaySettingsExW(display.szDevice,&requested,nullptr,0,nullptr);
   check(changed==DISP_CHANGE_SUCCESSFUL,QString("actual display mode changed to %1 Hz").arg(hz));if(changed!=DISP_CHANGE_SUCCESSFUL)continue;wait(1800);
   DEVMODEW actual{};actual.dmSize=sizeof(actual);EnumDisplaySettingsW(display.szDevice,ENUM_CURRENT_SETTINGS,&actual);
   if(int(actual.dmDisplayFrequency)!=hz){refreshPhases.append(QJsonObject{{"requestedHz",hz},{"available",false},{"actualHz",int(actual.dmDisplayFrequency)}});ChangeDisplaySettingsExW(display.szDevice,&original,nullptr,0,nullptr);continue;}
   window->showNormal();window->requestActivate();SetWindowPos(qaWindow,HWND_TOPMOST,0,0,0,0,SWP_NOMOVE|SWP_NOSIZE|SWP_NOACTIVATE);window->update();wait(350);
   check(window->isExposed(),QString("native test window is exposed at %1 Hz").arg(hz));
  }
#endif
  const auto phaseStart=qpcMs();
  presentationHz=hz?hz:qRound(window->screen()->refreshRate());
  const int phaseCycles=sweep?(qApp->arguments().contains("--hero-performance-quick")?24:180):30;
  for(int i=0;i<phaseCycles;++i){
   const auto pageStart=qpcMs();route(i%2?"proxies":"subscriptions");
   animationWindows.append(QJsonObject{{"startQpcMs",pageStart},{"endQpcMs",pageStart+eval("SwirlMotion.pageDuration").toDouble()},{"kind","page"},{"requestedHz",hz}});
   if(i%2==0){const auto cardStart=qpcMs();click("expandSubscription-"+subscriptionId);animationWindows.append(QJsonObject{{"startQpcMs",cardStart},{"endQpcMs",cardStart+eval("SwirlMotion.dialogDuration").toDouble()},{"kind","subscription"},{"requestedHz",hz}});}
   wait(260);
  }
  refreshPhases.append(QJsonObject{{"requestedHz",hz},{"available",true},{"qtRefreshHz",window->screen()->refreshRate()},{"startQpcMs",phaseStart},{"endQpcMs",qpcMs()},{"resources",resources()}});
 }
 const double performanceEnd=qpcMs();
 QObject::disconnect(frameConnection);std::sort(intervals.begin(),intervals.end());double mean=0;for(double ms:intervals)mean+=ms;if(!intervals.isEmpty())mean/=intervals.size();
 QJsonArray displaySamples;for(const auto &frame:presentations)displaySamples.append(QJsonObject{{"displayQpcMs",frame.qpcMs},{"presentCount",int(frame.count)},{"presentRefreshCount",int(frame.refresh)},{"syncRefreshCount",int(frame.sync)},{"syncQpcMs",frame.syncQpcMs},{"hz",frame.hz}});
 QJsonObject background;
 if(sweep){const auto before=resources();window->showMinimized();wait(60000);const auto after=resources();background={{"durationMs",60000},{"cpuMs",after.value("cpuMs").toDouble()-before.value("cpuMs").toDouble()},{"before",before},{"after",after}};window->showNormal();wait(350);}
 check(eval("motionPolicy.activeGrabCount===0 && SwirlTransitionRegistry.activeCount===0").toBool(),"all transition resources are idle after repeated use");
 policy->setSystemReducedMotionOverrideForTest(-1);
 check(policy->systemReducedMotion()==actualSystemReducedMotion,"hero fixture restores the actual Windows accessibility policy");
 QFile report(directory+"/hero-report.json");if(!report.open(QIODevice::WriteOnly))return 3;
 report.write(QJsonDocument(QJsonObject{{"actualSystemReducedMotion",actualSystemReducedMotion},{"animatedSystemPolicyFixture",0},{"systemReducedPolicyFixture",1},{"restoredSystemPolicy",policy->systemReducedMotion()==actualSystemReducedMotion},{"settingsRetargetSamples",settingsRetargetSamples},{"nodeClickDispatchMs",nodeClickMs},{"checks",checks},{"failures",failures},{"dxgiPresentations",displaySamples},{"dxgiStatisticsErrors",statisticsErrors},{"animationWindows",animationWindows},{"refreshPhases",refreshPhases},{"resourceBefore",resourceBefore},{"resourceAfter",resources()},{"minimizedIdle",background},{"performanceStartQpcMs",performanceStart},{"performanceEndQpcMs",performanceEnd},{"reportedRefreshHz",window->screen()->refreshRate()},{"nativeDpr",window->devicePixelRatio()},{"sampleCount",intervals.size()},{"meanFrameDeliveryMs",mean},{"p95FrameDeliveryMs",intervals.isEmpty()?0:intervals[qMin(intervals.size()-1,qsizetype(intervals.size()*0.95))]},{"p99FrameDeliveryMs",intervals.isEmpty()?0:intervals[qMin(intervals.size()-1,qsizetype(intervals.size()*0.99))]},{"method","Passive Qt frameSwapped delivery during native interaction, excluding screenshot readback. These intervals are not hardware display presentation FPS; use external PresentMon data for presentation evidence."}}).toJson());
 return failures?2:0;
}
