#include "NavigationChecks.h"
#include "engine/EngineController.h"
#include "app/MotionPolicy.h"
#include <QQuickWindow>
#include <QQuickItem>
#include <QGuiApplication>
#include <QScreen>
#include <QQmlExpression>
#include <QQmlContext>
#include <QTest>
#include <QFile>
#include <QJsonDocument>
#include <QJsonArray>
#include <QJsonObject>
#include <QDir>
#include <QElapsedTimer>
#include <QEventLoop>
#include <QTimer>
#include <QSet>
#include <QMap>
#include <QMutex>
#include <QMutexLocker>
#include <atomic>
#include <algorithm>
#include <memory>
#include <functional>

int runNavigationChecks(QQuickWindow *window,EngineController *controller,const QString &directory) {
 int failures=0;QJsonArray checks,endpointSamples;QJsonObject performance;QDir().mkpath(directory);
 auto wait=[](int ms){QEventLoop loop;QTimer::singleShot(ms,&loop,&QEventLoop::quit);loop.exec();};
 auto await=[](const std::function<bool()> &predicate,int timeout){
  if(predicate())return true;QEventLoop loop;QTimer poll,deadline;poll.setInterval(4);poll.setTimerType(Qt::PreciseTimer);deadline.setSingleShot(true);
  QObject::connect(&poll,&QTimer::timeout,&loop,[&]{if(predicate())loop.quit();});QObject::connect(&deadline,&QTimer::timeout,&loop,&QEventLoop::quit);
  poll.start();deadline.start(timeout);loop.exec();return predicate();
 };
 auto check=[&](bool ok,const QString &name){checks.append(QJsonObject{{"name",name},{"passed",ok}});if(!ok)++failures;qInfo()<<"NAVIGATION_CHECK"<<name<<ok;};
 auto eval=[&](const QString &code){QQmlExpression expression(qmlContext(window),window,code);auto value=expression.evaluate();if(expression.hasError()){qWarning()<<expression.error();++failures;}return value;};
 std::function<QQuickItem *(QQuickItem *,const QString &)> find;
 find=[&](QQuickItem *parent,const QString &name)->QQuickItem *{if(parent->objectName()==name&&parent->isVisible())return parent;for(auto *child:parent->childItems())if(auto *value=find(child,name))return value;return nullptr;};
 auto item=[&](const QString &name){return find(window->contentItem(),name);};
 auto settled=[&]{return eval("pageLoader.item && !pageLoader.moving && !pageLoader.pendingGrab && pageLoader.activeLoader.routeId===AppState.currentPage").toBool();};
 auto settle=[&]{return await(settled,4000);};
 auto click=[&](const QString &name){auto *control=item(name);check(control!=nullptr,"input exists: "+name);if(control)QTest::mouseClick(window,Qt::LeftButton,Qt::NoModifier,control->mapToScene(QPointF(control->width()/2,control->height()/2)).toPoint());};
 auto route=[&](const QString &id){eval("AppState.navigate('"+id+"')");return settle();};
 if(controller->nodes().isEmpty()){
  QString yaml="proxies:\n";for(int i=0;i<180;++i)yaml+=QString("  - {name: 'Fixture node %1', type: socks5, server: 127.0.0.1, port: 9}\n").arg(i,3,10,QChar('0'));
  controller->imports()->importText(yaml);
  check(await([&]{return !controller->imports()->busy();},8000)&&controller->nodes().size()==180,"standalone navigation fixture imports 180 local node records");
 }
 auto *policy=qobject_cast<MotionPolicy *>(qmlContext(window)->contextProperty("motionPolicy").value<QObject *>());
 const auto nativeMotionPolicy=QJsonDocument::fromJson(eval("JSON.stringify({systemReduced:motionPolicy.systemReducedMotion,followSystem:Theme.followSystemMotion,applicationReduced:Theme.reduceMotion,effectiveReduced:SwirlMotion.reduced,expandDuration:SwirlMotion.expandDuration})").toString().toUtf8()).object();
 check(policy&&!nativeMotionPolicy.value("followSystem").toBool()&&!nativeMotionPolicy.value("applicationReduced").toBool()&&!nativeMotionPolicy.value("effectiveReduced").toBool()&&nativeMotionPolicy.value("expandDuration").toInt()>0,"fresh application defaults keep full animation under the actual system policy without an override");
 const auto handle=window->winId();const auto geometry=window->geometry();
 const auto pid=controller->processId();const auto selected=controller->selectedNodeId();const auto nodeCount=controller->nodes().size();
 eval("Theme.reduceMotion=false;SwirlMotion.speed=1");check(route("featurehub"),"card hub settles before input");
 auto *hub=eval("pageLoader.item").value<QObject *>();
 check(!item("settingsBackButton"),"settings hub has no redundant back control");
 QSet<QWindow *> windows;for(auto *candidate:QGuiApplication::allWindows())windows.insert(candidate);
 auto noNewWindows=[&]{for(auto *candidate:QGuiApplication::allWindows())if(!windows.contains(candidate))return false;return true;};
 const QStringList routes{"settings","fonts","dns","modules","profiles","scripts","subscriptions","proxies"};
 QMap<QString,QObject *> pages;
 for(int round=0;round<2;++round)for(const auto &id:routes){
  auto *source=item("settings-"+id);check(source!=nullptr,"hub card remains reachable: "+id);
  click("settings-"+id);
  bool coverage=true,sawMorph=false,unframed=true,backFollowsPage=true;int frame=0;QJsonArray frameTimes;QElapsedTimer timer;timer.start();
  do {
   wait(6);
   coverage&=eval("Object.keys(pageLoader.pages).reduce((sum,key)=>sum+(pageLoader.pages[key].visible?pageLoader.pages[key].opacity:0),0)>0.98").toBool();
   sawMorph|=eval("pageLoader.moving && pageLoader.heroData && pageLoader.heroData.key==='settings'").toBool();
   backFollowsPage&=eval("!pageLoader.heroData || pageLoader.heroData.key!=='settings' || pageLoader.position>=0.82 || settingsBack.opacity===0").toBool();
   if(auto *morph=item("sharedSurface")){
    unframed&=!morph->property("independentCard").toBool()&&morph->property("radius").toDouble()>0&&QQmlExpression(qmlContext(morph),morph,"border.width===0").evaluate().toBool();
    unframed&=QQmlExpression(qmlContext(morph),morph,"!settingsTransition || color.a<0.01 || Math.abs(color.r-(host.heroData.returning?host.heroData.toColor.r:host.heroData.fromColor.r))<0.005").evaluate().toBool();
    unframed&=QQmlExpression(qmlContext(morph),morph,"!settingsTransition || color.a<0.01 || (Math.abs(color.r-Theme.material('content').r)<0.005 && Math.abs(color.g-Theme.material('content').g)<0.005 && Math.abs(color.b-Theme.material('content').b)<0.005)").evaluate().toBool();
   }
   if(round==0&&id=="subscriptions"&&qApp->arguments().contains("--navigation-record-motion")){
    const QString path=directory+"/settings-expansion";QDir().mkpath(path);
    const auto name=QString("%1.png").arg(frame++,3,10,QChar('0'));
    window->grabWindow().save(path+"/"+name);
    frameTimes.append(QJsonObject{{"file",name},{"elapsedMs",timer.elapsed()},{"progress",eval("pageLoader.position").toDouble()}});
   }
  }while(!settled()&&timer.elapsed()<4000);
  check(settled()&&eval("AppState.currentPage==='"+id+"'").toBool(),"card navigates inside the main content: "+id);
  auto *page=qobject_cast<QQuickItem *>(eval("pageLoader.item").value<QObject *>());
  check(page&&page->window()==window&&noNewWindows(),"no settings or taskbar HWND is created: "+id);
  check(coverage&&sawMorph,"live page coverage and card expansion remain continuous: "+id);
  check(unframed,"settings expansion adds no full-page card shadow or square frame: "+id);
  check(backFollowsPage&&item("settingsBackButton")&&item("settingsBackButton")->property("text").toString()=="返回","back enters after the expanded page, without a redundant settings label: "+id);
  if(!frameTimes.isEmpty()){QFile timestamps(directory+"/settings-expansion/timestamps.json");if(timestamps.open(QIODevice::WriteOnly))timestamps.write(QJsonDocument(frameTimes).toJson());}
  check(window->winId()==handle&&window->geometry()==geometry,"navigation leaves the native shell stationary: "+id);
  check(item("nav-featurehub")&&item("windowCloseButton"),"sidebar and original traffic lights remain present: "+id);
  if(round==0)pages.insert(id,page);else check(pages.value(id)==page,"same cached page is reused: "+id);
  if(id=="fonts"||id=="settings")check(page&&page->property("section").toString()==(id=="fonts"?"字体":"常规"),"independent settings sections retain their route: "+id);
  if(round==0&&id=="dns")if(auto *field=item("dnsServerAddress"))field->setProperty("text","1.1.1.1, 8.8.8.8");
  if(round==1&&id=="dns")check(item("dnsServerAddress")&&item("dnsServerAddress")->property("text").toString()=="1.1.1.1, 8.8.8.8","unsubmitted DNS draft survives back and re-entry");
  if(id=="proxies"){
   auto *search=item("nodeSearchField"),*table=item("realNodeTable");
   if(round==0&&search){
    search->setProperty("text","Fixture node 1");wait(30);
    if(table)table->setProperty("scrollPosition",88);
   }
   else if(round==1){
    check(search&&search->property("text").toString()=="Fixture node 1","node search is retained across back navigation");
    check(table&&qAbs(table->property("scrollPosition").toDouble()-88)<1,"node table scroll position survives back and re-entry");
    if(search)search->setProperty("text","");
   }
   if(table)check(table->property("renderedRows").toInt()>0&&table->property("renderedRows").toInt()<60,"180-node table only mounts the visible virtualized rows");
  }
  if(!qApp->arguments().contains("--hero-no-recording")&&(id=="dns"||id=="proxies"||id=="settings"))window->grabWindow().save(directory+"/"+id+"-embedded.png");
  const auto contentCenter=page?page->mapToScene(QPointF(page->width()/2,page->height()/2)):QPointF();
  click("settingsBackButton");
  if(round==0){
   const bool returning=await([&]{return eval("pageLoader.moving && pageLoader.heroData && pageLoader.heroData.returning").toBool();},2000);
   wait(70);
   auto *boundary=item("sharedSurface");
   const auto origin=eval("pageLoader.surfaceStart").toRectF();
   const auto contentTravel=page?page->mapToScene(QPointF(page->width()/2,page->height()/2))-contentCenter:QPointF();
   const auto surfaceTravel=boundary?boundary->position()-origin.topLeft():QPointF();
   check(returning&&boundary&&surfaceTravel.manhattanLength()>1&&(contentTravel-surfaceTravel).manhattanLength()<0.5,"returning functional content travels with its card instead of crossing the shared title: "+id);
  }
  check(settle()&&eval("AppState.currentPage==='featurehub'").toBool()&&eval("pageLoader.item").value<QObject *>()==hub,"back returns to the same cached hub: "+id);
 }
 // Observe a real late frame before either layer is retired, with enough
 // duration to sample the final one percent without stopping the animation.
 eval("SwirlMotion.speed=0.5");click("settings-subscriptions");
 const bool lateFrame=await([&]{return eval("pageLoader.moving && pageLoader.position>=0.90 && pageLoader.position<1").toBool();},3000);
 auto *lateHero=item("pageHeroTitle");
 auto *lateTitle=lateHero?lateHero->property("targetItem").value<QQuickItem *>():nullptr;
 check(lateFrame&&lateTitle&&lateTitle->opacity()>0.999,"live title takes over in an actual final animation frame, before completion");
 check(settle(),"late-frame expansion completes normally");click("settingsBackButton");check(settle(),"late-frame fixture reverses normally");eval("SwirlMotion.speed=1");
 // Hold the actual final animation value before retiring the shared layer.
 // Its pixels must already equal the committed page; otherwise completion
 // swaps a hidden title, material or clip boundary in a single frame.
 for(const auto &id:routes){
  click("settings-"+id);
  // Leave the destination's controls unhovered: this comparison concerns
  // surface retirement, not a new hover animation under the old card point.
  QTest::mouseMove(window,QPoint(window->width()-24,20));
  QElapsedTimer endpointWait;endpointWait.start();bool reachedEndpoint=false;
  do{wait(2);reachedEndpoint=eval("pageLoader.moving && pageLoader.position===1").toBool();}while(!reachedEndpoint&&endpointWait.elapsed()<4000);
  check(reachedEndpoint,"endpoint fixture naturally reaches the final expansion segment: "+id);
  auto *clock=window->findChild<QObject *>("pageTravel");
  if(clock)QMetaObject::invokeMethod(clock,"stop");
  auto *commit=window->findChild<QObject *>("pageCommit");if(commit)QMetaObject::invokeMethod(commit,"stop");
  // Every visible channel has naturally reached its endpoint. Holding the
  // remaining clock tail neither skips visible motion nor disables feedback.
  wait(25);
  auto *sharedTitle=item("pageHeroTitle");
  auto *target=sharedTitle?sharedTitle->property("targetItem").value<QQuickItem *>():nullptr;
  check(sharedTitle&&target&&target->opacity()>0.999&&sharedTitle->property("handoff").toDouble()>0.999,"real destination title is visible before shared-layer retirement: "+id);
  const auto before=window->grabWindow().convertToFormat(QImage::Format_ARGB32);
  const QString geometryScript="JSON.stringify((function(){const rows=[];function visit(item){if(item.text!==undefined&&item.font!==undefined){const p=item.mapToItem(window.contentItem,0,0);rows.push({text:item.text,x:p.x,y:p.y,w:item.width,h:item.height,baseline:item.baselineOffset,font:item.font.pixelSize,weight:item.font.weight,opacity:item.opacity})}for(const child of item.children||[])visit(child)}visit(pageLoader.item);return rows})())";
  const auto geometryBefore=id=="profiles"?eval(geometryScript).toString():QString();
  eval("pageLoader.finish()");wait(25);
  const auto after=window->grabWindow().convertToFormat(QImage::Format_ARGB32);
  qint64 changed=0;
  if(before.size()==after.size())for(int y=0;y<before.height();++y){
   const auto *a=reinterpret_cast<const QRgb *>(before.constScanLine(y));const auto *b=reinterpret_cast<const QRgb *>(after.constScanLine(y));
   for(int x=0;x<before.width();++x)if(qMax(qMax(qAbs(qRed(a[x])-qRed(b[x])),qAbs(qGreen(a[x])-qGreen(b[x]))),qMax(qAbs(qBlue(a[x])-qBlue(b[x])),qAbs(qAlpha(a[x])-qAlpha(b[x]))))>2)++changed;
  }
  const double changedRatio=before.isNull()?1:double(changed)/(before.width()*before.height());
  check(!before.isNull()&&before.size()==after.size()&&changedRatio<0.0005,"final expanded frame and committed page have no visual jump: "+id);
  endpointSamples.append(QJsonObject{{"route",id},{"changedPixels",double(changed)},{"changedRatio",changedRatio},{"geometryBefore",geometryBefore},{"geometryAfter",id=="profiles"?eval(geometryScript).toString():QString()}});
  if(!qApp->arguments().contains("--hero-no-recording")){before.save(directory+"/"+id+"-before-retirement.png");after.save(directory+"/"+id+"-after-retirement.png");}
  click("settingsBackButton");check(settle(),"endpoint fixture returns to the card hub: "+id);
 }
 const auto cacheCount=eval("pageLoader.cachedPageCount").toInt();
 for(int i=0;i<27;++i){eval("window.openSettings('"+routes[i%routes.size()]+"')");wait(9);}
 check(settle()&&eval("AppState.currentPage==='"+routes[26%routes.size()]+"'").toBool(),"rapid requests settle at the last requested route");
 check(noNewWindows()&&eval("pageLoader.cachedPageCount").toInt()==cacheCount,"rapid requests create one cached instance per route and no windows");
 route("featurehub");click("settings-subscriptions");
 wait(70);auto *surface=item("sharedSurface");const auto before=surface?QRectF(surface->position(),surface->size()):QRectF();
 eval("window.closeSettings()");QCoreApplication::processEvents();
 const auto after=surface?QRectF(surface->position(),surface->size()):QRectF();
 qInfo()<<"NAVIGATION_REVERSE"<<before<<after;
 check(surface&&eval("pageLoader.retargetRequestedRect===pageLoader.retargetCommittedRect").toBool(),"mid-flight back reverses from the current displayed boundary");
 check(settle()&&eval("AppState.currentPage==='featurehub'").toBool(),"interrupted expansion returns cleanly");
 click("settings-subscriptions");check(settle(),"return retarget fixture expands normally");
 click("settingsBackButton");
 check(await([&]{return eval("pageLoader.moving && pageLoader.heroData && pageLoader.heroData.returning && pageLoader.position>0.15").toBool();},2000),"return retarget fixture reaches a moving content frame");
 auto *clock=window->findChild<QObject *>("pageTravel");if(clock)QMetaObject::invokeMethod(clock,"pause");
 auto *returningPage=qobject_cast<QQuickItem *>(pages.value("subscriptions"));
 const auto centerBefore=returningPage?returningPage->mapToScene(QPointF(returningPage->width()/2,returningPage->height()/2)):QPointF();
 eval("window.openSettings('subscriptions')");QCoreApplication::processEvents();
 const auto centerAfter=returningPage?returningPage->mapToScene(QPointF(returningPage->width()/2,returningPage->height()/2)):QPointF();
 check(returningPage&&(centerAfter-centerBefore).manhattanLength()<0.5,"reopening a returning card preserves its currently displayed functional content position");
 check(settle()&&eval("pageLoader.item").value<QObject *>()==returningPage,"return reversal reuses and settles the same page");
 click("settingsBackButton");check(settle(),"return retarget fixture settles back at the hub");
 route("proxies");auto *page=qobject_cast<QQuickItem *>(pages.value("proxies"));
 window->resize(window->minimumWidth(),window->minimumHeight());wait(180);
 auto *table=item("realNodeTable");check(table&&page&&table->mapToItem(page,QPointF()).x()>=0&&table->mapToItem(page,QPointF(table->width(),table->height())).x()<=page->width()+1,"node table fits the main content at minimum window size");
 check(item("nodeSearchField")&&item("nodeCountryFilter")&&item("nodeImportButton")&&item("nodeAddButton")&&item("allNodesTestButton"),"embedded nodes retain search, filters, import, add and test controls");
 window->setGeometry(geometry);wait(150);
 check(controller->processId()==pid&&controller->selectedNodeId()==selected&&controller->nodes().size()==nodeCount,"navigation preserves proxy process, selected node and stored records");
 check(eval("motionPolicy.activeGrabCount===0 && SwirlTransitionRegistry.activeCount===0").toBool(),"navigation releases all transient resources");
 route("featurehub");
 if(qApp->arguments().contains("--navigation-performance")){
  // Passive delivery sampling: no screenshots, expression polling, layout
  // traversal or per-frame logging while the actual navigation is moving.
  struct DeliverySamples {QElapsedTimer clock;QMutex mutex;QList<double> intervals,allIntervals;std::atomic_bool sampling{false};qint64 previous=0,previousAll=0,start=0,end=0;};
  auto delivery=std::make_shared<DeliverySamples>();delivery->clock.start();
  auto connection=QObject::connect(window,&QQuickWindow::frameSwapped,window,[delivery]{
   if(!delivery->sampling.load())return;const auto now=delivery->clock.nsecsElapsed();QMutexLocker guard(&delivery->mutex);
   if(delivery->previousAll)delivery->allIntervals.append(double(now-delivery->previousAll)/1000000.0);delivery->previousAll=now;
   if(now<delivery->start||now>delivery->end){delivery->previous=0;return;}
   if(delivery->previous)delivery->intervals.append(double(now-delivery->previous)/1000000.0);delivery->previous=now;
  },Qt::DirectConnection);
  const int waitMs=qRound(eval("SwirlMotion.expandDuration*1.15+80").toDouble());
  auto beginSample=[&]{QMutexLocker guard(&delivery->mutex);delivery->previous=delivery->previousAll=0;const auto now=delivery->clock.nsecsElapsed();delivery->start=now+20000000;delivery->end=now+qint64(waitMs-100)*1000000;delivery->sampling=true;};
  auto runEventLoop=[&]{QEventLoop loop;QTimer::singleShot(waitMs,&loop,&QEventLoop::quit);loop.exec();};
  for(int cycle=0;cycle<18;++cycle){
   beginSample();
   auto *control=item("settings-"+routes[cycle%routes.size()]);if(control)QTest::mouseClick(window,Qt::LeftButton,Qt::NoModifier,control->mapToScene(QPointF(control->width()/2,control->height()/2)).toPoint());
   runEventLoop();delivery->sampling=false;check(settled(),"passive forward cycle settles: "+QString::number(cycle));
   beginSample();
   QMetaObject::invokeMethod(window,"closeSettings");runEventLoop();delivery->sampling=false;check(settled(),"passive reverse cycle settles: "+QString::number(cycle));
  }
  QObject::disconnect(connection);QList<double> intervals,allIntervals;{QMutexLocker guard(&delivery->mutex);intervals=delivery->intervals;allIntervals=delivery->allIntervals;}std::sort(intervals.begin(),intervals.end());std::sort(allIntervals.begin(),allIntervals.end());
  const double refresh=window->screen()->refreshRate(),budget=1000/qMax(1.0,refresh);
  int overBudget=0,overDouble=0;for(double ms:intervals){if(ms>budget*1.5)++overBudget;if(ms>budget*2.5)++overDouble;}
  auto percentile=[&](double fraction){return intervals.isEmpty()?0:intervals[qMin(intervals.size()-1,qsizetype(intervals.size()*fraction))];};
  performance={{"cycles",18},{"samples",intervals.size()},{"reportedRefreshHz",refresh},{"p50Ms",percentile(0.50)},{"p95Ms",percentile(0.95)},{"p99Ms",percentile(0.99)},{"maxMs",intervals.isEmpty()?0:intervals.last()},{"over1_5Budgets",overBudget},{"over2_5Budgets",overDouble},{"allDeliverySamples",allIntervals.size()},{"allDeliveryP95Ms",allIntervals.isEmpty()?0:allIntervals[qMin(allIntervals.size()-1,qsizetype(allIntervals.size()*0.95))]},{"method","Passive Qt frameSwapped intervals during 36 warm forward/reverse transitions driven by a normal QEventLoop; no QTest sleep polling, screenshot readback or per-frame expression polling. Active samples cover 20 ms through duration minus 20 ms; all-delivery statistics additionally retain the stationary commit tail. Delivery intervals are not physical display presentation FPS."}};
 }
 QFile file(directory+"/navigation-report.json");if(file.open(QIODevice::WriteOnly))file.write(QJsonDocument(QJsonObject{{"checks",checks},{"nativeMotionPolicy",nativeMotionPolicy},{"endpointSamples",endpointSamples},{"performance",performance},{"failures",failures},{"nativeHandleUnchanged",window->winId()==handle},{"dpr",window->devicePixelRatio()}}).toJson());
 return failures;
}
