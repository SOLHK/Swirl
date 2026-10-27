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
  QString yaml="proxies:\n";for(int i=0;i<180;++i)yaml+=QString("  - {name: 'Fixture node %1', type: socks5, server: 127.0.0.1, port: %2}\n").arg(i,3,10,QChar('0')).arg(10000+i);
  controller->imports()->importText(yaml);
  check(await([&]{return !controller->imports()->busy();},8000)&&controller->nodes().size()==180,"standalone navigation fixture imports 180 local node records");
 }
 auto *policy=qobject_cast<MotionPolicy *>(qmlContext(window)->contextProperty("motionPolicy").value<QObject *>());
 const auto nativeMotionPolicy=QJsonDocument::fromJson(eval("JSON.stringify({systemReduced:motionPolicy.systemReducedMotion,followSystem:Theme.followSystemMotion,applicationReduced:Theme.reduceMotion,effectiveReduced:SwirlMotion.reduced,expandDuration:SwirlMotion.expandDuration})").toString().toUtf8()).object();
 check(policy&&nativeMotionPolicy.value("followSystem").toBool()&&!nativeMotionPolicy.value("applicationReduced").toBool()&&nativeMotionPolicy.value("effectiveReduced")==nativeMotionPolicy.value("systemReduced"),"fresh application follows the actual operating-system motion preference");
 if(policy)policy->setSystemReducedMotionOverrideForTest(0);
 const auto handle=window->winId();const auto geometry=window->geometry();
 const auto pid=controller->processId();const auto selected=controller->selectedNodeId();const auto nodeCount=controller->nodes().size();
 eval("Theme.reduceMotion=false;SwirlMotion.speed=1");check(route("featurehub"),"card hub settles before input");
 auto *hub=eval("pageLoader.item").value<QObject *>();
 check(!item("settingsBackButton"),"settings hub has no redundant back control");
 QSet<QWindow *> windows;for(auto *candidate:QGuiApplication::allWindows())windows.insert(candidate);
 auto noNewWindows=[&]{for(auto *candidate:QGuiApplication::allWindows())if(!windows.contains(candidate))return false;return true;};
 const QStringList routes{"settings","dns","modules","profiles","scripts","subscriptions","proxies"};
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
  if(id=="settings"){
   check(page&&page->property("section").toString()=="常规","general settings retain their section");
   // U2 moved fonts inside General. Keep actual font-control coverage without
   // inventing a removed eighth hub card or changing the approved QML layout.
   if(page)page->setProperty("section",QStringLiteral("字体"));
   check(await([&]{return item("fontSearch")&&item("fontFamilyList");},4000)&&noNewWindows(),"font controls become reachable after asynchronous first loading inside the cached settings page");
   if(page){page->setProperty("section",QStringLiteral("常规"));wait(100);}
   if(round==0&&page){
    const auto sections=QJsonDocument::fromJson(eval("JSON.stringify(pageLoader.item.sections)").toString().toUtf8()).array();
    check(sections.size()==13,"settings exposes all thirteen secondary sections");
    for(const auto &section:sections){
     page->setProperty("section",section.toString());
     check(await([&]{return eval("pageLoader.item.currentSectionReady() && SwirlTransitionRegistry.activeCount===0").toBool();},4000)&&noNewWindows(),"settings section loads and motion settles in its cached page: "+section.toString());
    }
    page->setProperty("section",QStringLiteral("代理"));
    check(await([&]{return item("diagnosticUrlField")!=nullptr;},2000),"proxy diagnostic draft input is available");
    auto *diagnosticDraft=item("diagnosticUrlField");
    if(diagnosticDraft)diagnosticDraft->setProperty("text",QStringLiteral("https://example.invalid/settings-draft"));
    page->setProperty("section",QStringLiteral("常规"));wait(350);page->setProperty("section",QStringLiteral("代理"));
    check(await([&]{auto *field=item("diagnosticUrlField");return field&&field==diagnosticDraft&&field->property("text").toString()==QStringLiteral("https://example.invalid/settings-draft");},2000),"switching settings sections preserves the same unsent diagnostic draft without running it");
    if(diagnosticDraft)diagnosticDraft->setProperty("text",QString());
    page->setProperty("section",QStringLiteral("字体"));
    check(await([&]{return item("fontSearch")!=nullptr;},2000),"font draft search is available");
    auto *fontDraft=item("fontSearch");if(fontDraft)fontDraft->setProperty("text",QStringLiteral("Harmony"));
    page->setProperty("section",QStringLiteral("常规"));wait(350);page->setProperty("section",QStringLiteral("字体"));
    check(await([&]{return item("fontSearch")==fontDraft&&fontDraft&&fontDraft->property("text").toString()==QStringLiteral("Harmony");},2000),"switching settings sections preserves the cached font preview controls and search draft");
    if(fontDraft)fontDraft->setProperty("text",QString());
    page->setProperty("section",QStringLiteral("常规"));wait(350);
    auto *directory=item("settingsSectionList");
    if(directory)directory->forceActiveFocus(Qt::TabFocusReason);
    QTest::keyClick(window,Qt::Key_Down);
    check(await([&]{return page->property("section").toString()==QStringLiteral("字体")&&item("fontSearch");},2000),"settings directory accepts real keyboard navigation into fonts");
    QTest::keyClick(window,Qt::Key_Left,Qt::AltModifier);
    check(await([&]{return eval("AppState.currentPage==='settings' && pageLoader.item.section==='常规'").toBool();},2000),"Alt-Left returns inside settings before leaving the cached page");
    QTest::keyClick(window,Qt::Key_Down);wait(350);
    QTest::keyClick(window,Qt::Key_Escape);
    check(await([&]{return eval("AppState.currentPage==='settings' && pageLoader.item.section==='常规'").toBool();},2000),"real Window Escape traverses dismissal handling and returns inside settings before leaving the cached page");
   }
  }
  if(round==0&&id=="dns")if(auto *field=item("dnsServerAddress"))field->setProperty("text","1.1.1.1, 8.8.8.8");
  if(round==1&&id=="dns")check(item("dnsServerAddress")&&item("dnsServerAddress")->property("text").toString()=="1.1.1.1, 8.8.8.8","unsubmitted DNS draft survives back and re-entry");
  if(id=="proxies"){
   auto *search=item("nodeSearchField"),*table=item("realNodeTable");
   if(round==0&&search){
    search->setProperty("text","Fixture node 1");
    check(await([&]{auto *model=window->findChild<QObject *>("nodeViewModel");return model&&model->property("query").toString()=="Fixture node 1"&&model->property("count").toInt()==80;},3500),"node search applies its debounced query before recording scroll position");
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
  // Park in the blank outer gutter. The former top-right point hovered the
  // close button, whose delayed tooltip polluted the retirement comparison.
  QTest::mouseMove(window,QPoint(4,window->height()/2));
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
 check(item("nodeSearchField")&&item("nodeFiltersButton")&&item("nodeImportButton")&&item("nodeAddButton")&&item("allNodesTestButton"),"embedded nodes retain search, filters, import, add and test controls");
 click("nodeFiltersButton");
 check(await([&]{return item("nodeCountryFilter")&&item("nodeSourceFilter");},1000),"node region and source controls open in the approved filter dialog");
 QTest::keyClick(window,Qt::Key_Escape);wait(100);
 window->setGeometry(geometry);wait(150);
 if(qApp->arguments().contains("--navigation-tool-pages")){
  window->resize(qRound(eval("Theme.dp(1100)").toDouble()),qRound(eval("Theme.dp(760)").toDouble()));wait(150);
  const auto typeTool=[&](const QString &name,const QString &value){auto *control=item(name);check(control&&control->isEnabled(),"tool draft input is reachable: "+name);if(!control)return;control->forceActiveFocus();QTest::keyClick(window,Qt::Key_A,Qt::ControlModifier);for(const auto character:value)QTest::keyClick(window,character.toLatin1());wait(50);};
  const auto selectModuleTab=[&](int index){auto *tabs=item("moduleSections");check(tabs&&tabs->isEnabled(),"dynamic module tab input is reachable");if(tabs)QTest::mouseClick(window,Qt::LeftButton,Qt::NoModifier,tabs->mapToScene(QPointF(tabs->width()*(index+0.5)/3,tabs->height()/2)).toPoint());};
  const auto featureId=eval("FeatureCatalog.entries.filter(entry=>entry.id.indexOf('feature-')===0)[0].id").toString();
  check(!featureId.isEmpty()&&route(featureId),"dynamic feature module loads through its actual catalogue route");
  selectModuleTab(1);wait(40);selectModuleTab(2);wait(40);selectModuleTab(1);
  check(await([&]{auto *motion=item("moduleSectionMotion");return eval("pageLoader.item.tab===1").toBool()&&motion&&!motion->property("moving").toBool();},2000),"rapid real module tab input retargets and settles on the last requested section");
  const auto initialRecords=eval("pageLoader.item.records.length").toInt();
  for(const auto &name:QStringList{"local-draft-a","local-draft-b"}){
   click("moduleAddButton");
   check(await([&]{return item("moduleEntryName")&&eval("dismissals.count>0 && SwirlTransitionRegistry.activeCount===0").toBool();},2500),"dynamic module draft editor opens through the real popup lifecycle");
   typeTool("moduleEntryName",name);typeTool("moduleEntryValue","local-only");click("moduleEntryConfirm");
   check(await([&]{return eval("dismissals.count===0").toBool();},2500),"dynamic module draft editor closes without leaving its modal shield");
  }
  check(eval(QString("pageLoader.item.records.length===%1 && pageLoader.item.dirty").arg(initialRecords+2)).toBool(),"real module form input adds only local draft records");
  eval(QString("pageLoader.item.reorder(%1,-1)").arg(initialRecords+1));
  check(eval(QString("pageLoader.item.records[%1].name==='local-draft-b'").arg(initialRecords)).toBool(),"local module reorder preserves record values and changes their priority");
  eval("pageLoader.item.restore()");
  check(eval(QString("pageLoader.item.records.length===%1 && !pageLoader.item.dirty").arg(initialRecords)).toBool(),"restoring the unsaved module fixture leaves durable drafts unchanged");
  check(route("api"),"API reference page loads");click("apiSection-访问日志");
  check(eval("pageLoader.item.tab==='访问日志' && !pageLoader.item.implemented").toBool(),"actual API reference tab input does not start an unimplemented API service");
  check(route("automation"),"automation reference page loads");click("automationSection-Conditions");
  check(eval("pageLoader.item.tab==='Conditions' && !pageLoader.item.implemented").toBool(),"actual automation reference tab input does not execute a task");
  check(route("map"),"mapping draft page loads");click("mapSection-远程映射");typeTool("mapDraftMatch","local-only");click("mapSection-本地映射");click("mapSection-远程映射");
  check(await([&]{auto *field=item("mapDraftMatch");return field&&field->property("text").toString()=="local-only"&&eval("(pageLoader.item.editorBuffers['远程映射']||{}).match==='local-only' && !pageLoader.item.implemented").toBool();},2000),"mapping tabs retain independent local drafts without reading files or redirecting traffic");
  check(route("replay"),"replay draft page loads");click("replaySection-Body");typeTool("replayDraftEditor","local-payload");click("replaySection-Headers");click("replaySection-Body");
  check(await([&]{auto *editor=item("replayDraftEditor");return editor&&editor->property("text").toString()=="local-payload"&&eval("pageLoader.item.editorBuffers.Body==='local-payload' && !pageLoader.item.implemented && pageLoader.item.history.length===0").toBool();},2000),"replay tabs retain local text without sending requests or inventing execution history");
  check(await([&]{return eval("SwirlTransitionRegistry.activeCount===0").toBool();},2500),"tool page motion settles without an idle animation loop");
  for(const int width:{1100,914,760}){
   window->resize(qRound(eval(QString("Theme.dp(%1)").arg(width)).toDouble()),qRound(eval("Theme.dp(672)").toDouble()));
   check(route("inspector"),"inspector boundary fixture loads at width "+QString::number(width));
   eval("pageLoader.item.selected=null");wait(100);
   auto *inspectorPage=qobject_cast<QQuickItem *>(eval("pageLoader.item").value<QObject *>());
   auto *listSurface=item("inspectorListSurface"),*split=item("inspectorWorkspace");
   const auto inside=[&](QQuickItem *surface){if(!surface||!inspectorPage)return false;const auto point=surface->mapToItem(inspectorPage,QPointF());return point.x()>=-1&&point.y()>=-1&&point.x()+surface->width()<=inspectorPage->width()+1&&point.y()+surface->height()<=inspectorPage->height()+1;};
   check(listSurface&&split&&inside(listSurface)&&inside(split)&&!item("inspectorDetails"),"inspector empty view fits without an idle detail pane at width "+QString::number(width));
   // A geometry-only record exercises the selected layout; it is not inserted
   // into the provider, captured as real traffic, or used for network claims.
   eval("pageLoader.item.selected={method:'GET',host:'geometry.invalid',status:0,duration:'unmeasured',requestHeaders:'geometry fixture'}");wait(100);
   auto *detail=item("inspectorDetails");
   check(detail&&inside(detail)&&(!eval("pageLoader.item.compact").toBool()||!item("inspectorListSurface")),"inspector selected layout fits and can return to the list at width "+QString::number(width));
   click("inspectorClearSelection");
   check(await([&]{return eval("pageLoader.item.selected===null").toBool()&&item("inspectorListSurface")&&!item("inspectorDetails");},1000),"inspector clear selection returns to the list at width "+QString::number(width));
  }
  window->setGeometry(geometry);wait(150);
 }
 check(controller->processId()==pid&&controller->selectedNodeId()==selected&&controller->nodes().size()==nodeCount,"navigation preserves proxy process, selected node and stored records");
 check(await([&]{return eval("motionPolicy.activeGrabCount===0 && SwirlTransitionRegistry.activeCount===0").toBool();},2500),"navigation releases all transient resources");
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
