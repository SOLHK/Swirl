#include "NavigationChecks.h"
#include "engine/EngineController.h"
#include "app/MotionPolicy.h"
#include <QQuickWindow>
#include <QQuickItem>
#include <QColor>
#include <QCursor>
#include <QSignalSpy>
#include <QtMath>
#include <QGuiApplication>
#include <QScreen>
#include <QQmlExpression>
#include <QQmlContext>
#include <QQmlEngine>
#include <QTest>
#include <QFile>
#include <QSaveFile>
#include <QCryptographicHash>
#include <QDateTime>
#include <QCoreApplication>
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
#ifdef Q_OS_WIN
#include <windows.h>
#endif

int runNavigationChecks(QQuickWindow *window,EngineController *controller,const QString &directory) {
 int failures=0;QJsonArray checks,endpointSamples,buttonSamples;QJsonObject performance;QDir().mkpath(directory);
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
  bool collected=false;
  bool coverage=true,sawMorph=false,unframed=true,backFollowsPage=true;int frame=0;QJsonArray frameTimes;QElapsedTimer timer;timer.start();
  do {
   wait(6);
   // A cold page's helpers must remain owned through asynchronous creation
   // and GC, including a dialog's deferred content and header creation.
   if(round==0 && id=="subscriptions" && !collected){qmlEngine(window)->collectGarbage();collected=true;}
   coverage&=eval("Object.keys(pageLoader.pages).reduce((sum,key)=>sum+(pageLoader.pages[key].visible?pageLoader.pages[key].opacity:0),0)>0.98").toBool();
   sawMorph|=eval("pageLoader.moving && pageLoader.heroData && pageLoader.heroData.key==='settings'").toBool();
   backFollowsPage&=eval("!pageLoader.heroData || pageLoader.heroData.key!=='settings' || pageLoader.position>=0.82 || settingsBack.opacity===0").toBool();
   if(auto *morph=item("sharedSurface")){
    unframed&=!morph->property("independentCard").toBool()&&morph->property("radius").toDouble()>0&&QQmlExpression(qmlContext(morph),morph,"border.width===0").evaluate().toBool();
    unframed&=QQmlExpression(qmlContext(morph),morph,"!settingsTransition || color.a<0.01 || ['r','g','b'].every(channel=>color[channel]>=Math.min(host.heroData.fromColor[channel],host.heroData.toColor[channel])-0.005 && color[channel]<=Math.max(host.heroData.fromColor[channel],host.heroData.toColor[channel])+0.005)").evaluate().toBool();
    // A pointer click can sample an intermediate hover/press color. Preserve
    // that live neutral feedback rather than requiring the resting white.
    unframed&=QQmlExpression(qmlContext(morph),morph,"!settingsTransition || color.a<0.01 || ['r','g','b'].every(channel=>color[channel]>=Math.min(Theme.cardPressed[channel],Theme.independentCard[channel])-0.005 && color[channel]<=Math.max(Theme.cardPressed[channel],Theme.independentCard[channel])+0.005)").evaluate().toBool();
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
  if(id=="dns"){
   auto *title=page?page->property("motionTitle").value<QQuickItem *>():nullptr;
   check(title&&title->opacity()>0.999&&title->property("color").value<QColor>()==eval("Theme.text").value<QColor>(),"settled DNS title restores the opaque semantic foreground after expansion");
   if(round==0)if(auto *field=item("dnsServerAddress"))field->setProperty("text","1.1.1.1, 8.8.8.8");
  }
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
  if(auto *card=item("settings-"+id)){
   const auto center=card->mapToScene(QPointF(card->width()/2,card->height()/2)).toPoint();
   QCursor::setPos(window->mapToGlobal(center));QTest::mouseMove(window,center);wait(160);
  }
  click("settings-"+id);
  // Leave the destination's controls unhovered: this comparison concerns
  // surface retirement, not a new hover animation under the old card point.
  // The APEC shell places Close at the old top-right parking coordinate.
  // Park in the actual empty title-bar span so a delayed tooltip cannot
  // appear between the two full-window endpoint captures.
  auto *dragArea=item("titleDragArea"),*windowControls=item("windowControls");
  auto *sidebar=item("sidebar"),*backButton=item("settingsBackButton");
  const auto sceneRect=[](QQuickItem *control){return control?control->mapRectToScene(QRectF(QPointF(),control->size())):QRectF();};
  const auto dragRect=sceneRect(dragArea),controlsRect=sceneRect(windowControls);
  const auto sidebarRect=sceneRect(sidebar),backRect=sceneRect(backButton);
  const qreal parkingLeft=qMax(sidebarRect.right(),backRect.right());
  const qreal parkingTop=qMax(dragRect.top(),controlsRect.top());
  const QRectF parkingRect(parkingLeft,parkingTop,controlsRect.left()-parkingLeft,qMin(dragRect.bottom(),controlsRect.bottom())-parkingTop);
  const QPoint parkingPoint=parkingRect.center().toPoint();
  const bool parkingSafe=dragArea&&windowControls&&sidebar&&parkingRect.width()>2&&parkingRect.height()>2
      &&dragRect.contains(parkingPoint)&&!controlsRect.contains(parkingPoint)
      &&!sidebarRect.contains(parkingPoint)&&(!backButton||!backRect.contains(parkingPoint));
  check(parkingSafe,"endpoint pointer has an empty title-bar position outside controls: "+id);
  if(parkingSafe){QCursor::setPos(window->mapToGlobal(parkingPoint));QTest::mouseMove(window,parkingPoint);}
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
  if(changedRatio>=0.0005||!qApp->arguments().contains("--hero-no-recording")){before.save(directory+"/"+id+"-before-retirement.png");after.save(directory+"/"+id+"-after-retirement.png");}
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
 QTest::keyClick(window,Qt::Key_Escape);
 check(await([&]{return eval("dismissals.count===0").toBool();},2000),"Escape closes the node filter dialog and releases its modal shield");
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
 {
  // Exercise the actual page controls with canceled pointer releases. No
  // command handler, import, subscription refresh or system setting is invoked.
  struct RestoreCursor {QPoint position=QCursor::pos();~RestoreCursor(){QCursor::setPos(position);}} restoreCursor;
  eval("Theme.reduceMotion=false;Theme.followSystemMotion=false;SwirlMotion.speed=1");
  const auto available=window->screen()->availableGeometry();
  const QSize auditSize(qMax(window->minimumWidth(),qMin(qRound(eval("Theme.dp(1100)").toDouble()),available.width())),qMax(window->minimumHeight(),qMin(qRound(eval("Theme.dp(760)").toDouble()),available.height())));
  window->resize(auditSize);
  window->setPosition(available.topLeft()+QPoint(qMax(0,(available.width()-auditSize.width())/2),qMax(0,(available.height()-auditSize.height())/2)));
  window->requestActivate();wait(150);
#ifdef Q_OS_WIN
  // Keyboard focus and compositor evidence require the owned test HWND to be
  // foreground. Qt's activation request alone can be refused by Windows when
  // another application had focus before the test process started.
  const bool wasTopmost=window->flags().testFlag(Qt::WindowStaysOnTopHint);
  window->setFlag(Qt::WindowStaysOnTopHint,true);
  const HWND auditHwnd=reinterpret_cast<HWND>(window->winId());
  SetWindowPos(auditHwnd,HWND_TOPMOST,0,0,0,0,SWP_NOMOVE|SWP_NOSIZE);
  const DWORD foregroundThread=GetWindowThreadProcessId(GetForegroundWindow(),nullptr),currentThread=GetCurrentThreadId();
  const bool attached=foregroundThread&&foregroundThread!=currentThread&&AttachThreadInput(currentThread,foregroundThread,TRUE);
  SetForegroundWindow(auditHwnd);
  if(attached)AttachThreadInput(currentThread,foregroundThread,FALSE);
  check(await([&]{return GetForegroundWindow()==auditHwnd&&window->isActive();},1500),"marked-button runtime evidence owns the actual foreground window and keyboard focus");
#else
  window->raise();window->requestActivate();check(await([&]{return window->isActive();},1500),"marked-button runtime evidence owns keyboard focus");
#endif
  const auto evidence=directory+"/marked-buttons";QDir().mkpath(evidence);
  const auto movePointer=[&](const QPoint &point,int delay=0){QCursor::setPos(window->mapToGlobal(point));QCoreApplication::processEvents();QTest::mouseMove(window,window->mapFromGlobal(QCursor::pos()));if(delay)wait(delay);};
  const auto park=[&]{return QPoint(window->width()-2,window->height()/2);};
  std::function<QQuickItem *(QQuickItem *,const QString &)> byText;
  byText=[&](QQuickItem *root,const QString &text)->QQuickItem *{
   if(!root||!root->isVisible())return nullptr;
   if(root->property("down").isValid()&&root->property("text").toString()==text)return root;
   for(auto *child:root->childItems())if(auto *found=byText(child,text))return found;
   return nullptr;
  };
  const auto reveal=[&](QQuickItem *control){
   for(auto *ancestor=control?control->parentItem():nullptr;ancestor;ancestor=ancestor->parentItem())if(ancestor->property("contentY").isValid()){
    const auto bounds=control->mapRectToItem(ancestor,control->boundingRect());
    const auto y=ancestor->property("contentY").toDouble();
    const auto maximum=qMax(0.0,ancestor->property("contentHeight").toDouble()-ancestor->height());
    if(bounds.top()<0)ancestor->setProperty("contentY",qBound(0.0,y+bounds.top()-8,maximum));
    else if(bounds.bottom()>ancestor->height())ancestor->setProperty("contentY",qBound(0.0,y+bounds.bottom()-ancestor->height()+8,maximum));
   }
   wait(60);
  };
  const auto audit=[&](QQuickItem *control,const QString &key){
   check(control!=nullptr,"marked page button exists: "+key);if(!control)return;
   reveal(control);movePointer(park(),170);
   auto *surface=control->property("background").value<QQuickItem *>();
   const auto size=control->size();const auto position=control->position();
   const auto point=control->mapToScene(QPointF(size.width()/2,size.height()/2)).toPoint();
   const auto globalPoint=window->mapToGlobal(point);
   const bool inside=QRectF(QPointF(),window->size()).contains(point);
   check(surface&&inside&&control->isVisible(),"marked page button is visible inside the native window: "+key);if(!surface||!inside)return;
   const bool pointerReachable=window->screen()->availableGeometry().contains(globalPoint);
   check(pointerReachable,"marked page button native pointer target fits the actual screen: "+key);if(!pointerReachable)return;
   const auto snapshot=[&](const QString &phase){
    const auto image=window->grabWindow();const auto rect=control->mapRectToScene(control->boundingRect()).adjusted(-5,-5,5,5);const auto dpr=window->devicePixelRatio();
    const QRect pixels(qFloor(rect.x()*dpr),qFloor(rect.y()*dpr),qCeil(rect.width()*dpr),qCeil(rect.height()*dpr));
    const auto crop=image.copy(pixels.intersected(image.rect()));
    check(!crop.isNull()&&crop.save(evidence+"/"+key+"-"+phase+".png"),"actual marked-button pixels saved: "+key+"/"+phase);return crop;
   };
   const auto sample=[&](const QString &phase){const auto cursor=window->mapFromGlobal(QCursor::pos());buttonSamples.append(QJsonObject{{"button",key},{"phase",phase},{"windowActive",window->isActive()},{"activeFocus",control->hasActiveFocus()},{"visualFocus",control->property("visualFocus").toBool()},{"focusReason",control->property("focusReason").toInt()},{"cursorX",cursor.x()},{"cursorY",cursor.y()},{"targetGlobalX",globalPoint.x()},{"targetGlobalY",globalPoint.y()},{"targetScreenReachable",pointerReachable},{"enabled",control->isEnabled()},{"hovered",control->property("hovered").toBool()},{"down",control->property("down").toBool()},{"scale",control->property("motionScale").toDouble()},{"lift",control->property("motionLift").toDouble()},{"surfaceColor",surface->property("color").value<QColor>().name(QColor::HexArgb)}});};
   QSignalSpy clicked(control,SIGNAL(clicked()));
   const bool enabled=control->isEnabled();
   const auto fullLift=eval("Theme.dp(1)").toDouble();
   QImage idle,hover;bool intermediate=false,stableHover=false;
   for(int attempt=0;attempt<(enabled?3:1);++attempt){
    // Observe actual animation progress instead of assuming one fixed sleep
    // lands on a rendered frame. A real user pointer move can cancel hover
    // during readback; retain that sample and repeat only interrupted input.
    movePointer(park());await([&]{return !control->property("hovered").toBool()&&qAbs(control->property("motionLift").toDouble())<.01;},600);
    idle=snapshot("idle");sample("idle");movePointer(point);
    if(enabled){
     intermediate|=await([&]{const auto lift=control->property("motionLift").toDouble();return control->property("hovered").toBool()&&lift<0&&lift>-fullLift;},350);
     sample("hover-intermediate");
     if(!await([&]{return control->property("hovered").toBool()&&control->property("motionLift").toDouble()<-fullLift*.95;},600)){sample("hover-interrupted");continue;}
    }else wait(150);
    hover=snapshot("hover");sample("hover");
    stableHover=!enabled||(control->property("hovered").toBool()&&control->property("motionLift").toDouble()<-fullLift*.5);
    if(stableHover)break;
    sample("hover-interrupted");
   }
   if(enabled){
    check(intermediate,"marked button hover travels through an intermediate lifted frame: "+key);
    check(stableHover&&!hover.isNull()&&hover!=idle,"marked button hover visibly changes its real pixels: "+key);
   }
   QTest::mousePress(window,Qt::LeftButton,Qt::NoModifier,point);wait(70);snapshot("pressed");sample("pressed");
   if(enabled)check(control->property("down").toBool()&&control->property("motionScale").toDouble()<0.995,"marked button contracts during a normal70ms press: "+key);
   else check(!control->property("down").toBool()&&qAbs(control->property("motionScale").toDouble()-1)<.001&&qAbs(control->property("motionLift").toDouble())<.001,"disabled marked button has no misleading press or lift: "+key);
   movePointer(park());QTest::mouseRelease(window,Qt::LeftButton,Qt::NoModifier,park());wait(30);sample("release-intermediate");
   if(enabled)check(control->property("motionScale").toDouble()<.999,"marked button release continues naturally from its compressed frame: "+key);
   check(await([&]{return !control->property("down").toBool()&&qAbs(control->property("motionScale").toDouble()-1)<.001&&qAbs(control->property("motionLift").toDouble())<.01;},1800),"marked button returns completely after canceled release: "+key);
   snapshot("released");sample("released");
   if(enabled){
    // The preceding mouse press already focused this control. Qt retains that
    // mouse reason when forceActiveFocus targets the same focused item, so
    // first give the content root focus to generate a fresh keyboard FocusIn.
    control->setFocus(false);window->contentItem()->forceActiveFocus(Qt::OtherFocusReason);QCoreApplication::processEvents();
    control->forceActiveFocus(Qt::TabFocusReason);
    check(await([&]{return window->isActive()&&control->hasActiveFocus()&&control->property("visualFocus").toBool()&&control->property("focusReason").toInt()==Qt::TabFocusReason;},600),"marked button exposes keyboard focus: "+key);
    wait(170);snapshot("focus");sample("focus");
   }
   check(clicked.isValid()&&clicked.count()==0&&control->size()==size&&control->position()==position,"marked button feedback preserves layout and invokes no action: "+key);
  };
  // The accepted flat toolbar and Activity cards have different feedback
  // contracts from ordinary motion buttons. Observe their rendered geometry,
  // not inherited motion getters whose transforms the toolbar does not use.
  const auto sceneRect=[](QQuickItem *control){return control?control->mapRectToScene(control->boundingRect()):QRectF();};
  const auto sameSceneRect=[&](const QRectF &first,const QRectF &second){
   const auto dpr=window->devicePixelRatio();
   return qAbs(first.x()-second.x())*dpr<=.5&&qAbs(first.y()-second.y())*dpr<=.5
       &&qAbs(first.width()-second.width())*dpr<=.5&&qAbs(first.height()-second.height())*dpr<=.5;
  };
  const auto geometryEvidence=[&](QQuickItem *control){
   if(!control)return QJsonObject();const auto rect=sceneRect(control);
   return QJsonObject{{"x",control->x()},{"y",control->y()},{"width",control->width()},{"height",control->height()},
       {"sceneX",rect.x()},{"sceneY",rect.y()},{"sceneWidth",rect.width()},{"sceneHeight",rect.height()},{"scale",control->scale()}};
  };
  const auto savePixels=[&](QQuickItem *control,const QString &key,const QString &phase){
   const auto image=window->grabWindow();const auto rect=sceneRect(control).adjusted(-5,-5,5,5);const auto dpr=window->devicePixelRatio();
   const QRect pixels(qFloor(rect.x()*dpr),qFloor(rect.y()*dpr),qCeil(rect.width()*dpr),qCeil(rect.height()*dpr));
   const auto crop=image.copy(pixels.intersected(image.rect()));
   check(!crop.isNull()&&crop.save(evidence+"/"+key+"-"+phase+".png"),"actual marked-button pixels saved: "+key+"/"+phase);return crop;
  };
  const auto pointerFits=[&](QQuickItem *control,const QPoint &point,const QString &key){
   const bool inside=control&&control->isVisible()&&QRectF(QPointF(),window->size()).contains(point);
   check(inside,"marked page control is visible inside the native window: "+key);
   const bool onScreen=inside&&window->screen()->availableGeometry().contains(window->mapToGlobal(point));
   check(onScreen,"marked page control native pointer target fits the actual screen: "+key);return onScreen;
  };
  const auto colorDistance=[](const QColor &first,const QColor &second){return std::max({qAbs(first.redF()-second.redF()),qAbs(first.greenF()-second.greenF()),qAbs(first.blueF()-second.blueF()),qAbs(first.alphaF()-second.alphaF())});};
  const auto auditFlatToolbar=[&](QQuickItem *control,const QString &key){
   check(control!=nullptr,"marked flat toolbar button exists: "+key);if(!control)return;
   reveal(control);movePointer(park(),170);
   auto *surface=control->property("background").value<QQuickItem *>(),*contents=control->property("contentItem").value<QQuickItem *>();
   check(surface&&contents,"flat toolbar owns a real background and content group: "+key);if(!surface||!contents)return;
   const auto size=control->size();const auto position=control->position();
   const auto point=control->mapToScene(QPointF(size.width()/2,size.height()/2)).toPoint();
   if(!pointerFits(control,point,key))return;
   const auto controlRect=sceneRect(control),surfaceRect=sceneRect(surface),contentRect=sceneRect(contents);
   check(qAbs(control->height()-eval("Theme.toolbarHeight").toDouble())<.001
       &&qAbs(surface->property("radius").toDouble()-surface->height()/2)<.001
       &&QQmlExpression(qmlContext(surface),surface,"border.width===0").evaluate().toBool(),"flat toolbar keeps the common height and unframed pill surface: "+key);
   const auto geometryStable=[&]{return sameSceneRect(sceneRect(control),controlRect)&&sameSceneRect(sceneRect(surface),surfaceRect)&&sameSceneRect(sceneRect(contents),contentRect)
       &&qAbs(control->scale()-1)<.001&&qAbs(surface->scale()-1)<.001&&qAbs(contents->scale()-1)<.001;};
   const auto currentColor=[&]{return surface->property("color").value<QColor>();};
   const auto idleColor=eval("Theme.dark ? '#292929' : '#EEEEEE'").toString();
   const auto hoverColor=QColor(eval("Theme.dark ? '#323232' : '#E8E8E8'").toString());
   const auto pressedColor=QColor(eval("Theme.dark ? '#383838' : '#E3E3E3'").toString());
   const auto between=[&](const QColor &first,const QColor &second){const auto color=currentColor();return color.isValid()&&colorDistance(color,first)>.001&&colorDistance(color,second)>.001;};
   const auto sample=[&](const QString &phase){buttonSamples.append(QJsonObject{{"button",key},{"kind","flat-toolbar"},{"phase",phase},{"windowActive",window->isActive()},{"activeFocus",control->hasActiveFocus()},{"visualFocus",control->property("visualFocus").toBool()},{"hover",surface->property("hoverProgress").toDouble()},{"contact",surface->property("contactProgress").toDouble()},{"surfaceColor",currentColor().name(QColor::HexArgb)},{"controlGeometry",geometryEvidence(control)},{"backgroundGeometry",geometryEvidence(surface)},{"contentGeometry",geometryEvidence(contents)}});};
   QSignalSpy clicked(control,SIGNAL(clicked()));const bool enabled=control->isEnabled();
   bool stableGeometry=true,intermediateHover=false,intermediateContact=false,stableHover=false;
   QTimer sampler;sampler.setTimerType(Qt::PreciseTimer);
   QObject::connect(&sampler,&QTimer::timeout,window,[&]{
    stableGeometry&=geometryStable();
    const auto contact=surface->property("contactProgress").toDouble();
    intermediateContact|=control->property("down").toBool()&&contact>0&&contact<1&&between(hoverColor,pressedColor);
   });
   sampler.start(4);QImage idle,hover;
   for(int attempt=0;attempt<(enabled?3:1);++attempt){
    movePointer(park());await([&]{return !control->property("hovered").toBool()&&surface->property("hoverProgress").toDouble()<.01&&colorDistance(currentColor(),QColor(idleColor))<.001;},600);
    idle=savePixels(control,key,"idle");sample("idle");movePointer(point);
    if(enabled){
     intermediateHover|=await([&]{const auto progress=surface->property("hoverProgress").toDouble();return control->property("hovered").toBool()&&progress>0&&progress<1&&between(QColor(idleColor),hoverColor);},350);
     sample("hover-intermediate");
     if(!await([&]{return control->property("hovered").toBool()&&surface->property("hoverProgress").toDouble()>.95&&colorDistance(currentColor(),hoverColor)<.001;},600)){sample("hover-interrupted");continue;}
    }else wait(150);
    hover=savePixels(control,key,"hover");sample("hover");
    stableHover=!enabled||(control->property("hovered").toBool()&&surface->property("hoverProgress").toDouble()>.5);
    if(stableHover)break;sample("hover-interrupted");
   }
   if(enabled){
    check(intermediateHover,"flat toolbar hover traverses actual intermediate surface colors: "+key);
    check(stableHover&&!hover.isNull()&&hover!=idle,"flat toolbar hover visibly changes its real pixels: "+key);
   }
   QTest::mousePress(window,Qt::LeftButton,Qt::NoModifier,point);wait(70);const auto pressed=savePixels(control,key,"pressed");sample("pressed");
   if(enabled)check(control->property("down").toBool()&&intermediateContact&&surface->property("contactProgress").toDouble()>.95&&pressed!=hover&&geometryStable(),"flat toolbar gives continuous contact color and real pixel feedback without a pressed scale or lift: "+key);
   else check(!control->property("down").toBool()&&qAbs(surface->property("contactProgress").toDouble())<.001&&surface->property("hoverProgress").toDouble()<.001&&geometryStable(),"disabled flat toolbar has no misleading hover or press feedback: "+key);
   movePointer(park());QTest::mouseRelease(window,Qt::LeftButton,Qt::NoModifier,park());wait(30);sample("release-intermediate");
   if(enabled)check(surface->property("contactProgress").toDouble()>.05&&geometryStable(),"flat toolbar canceled release continues its contact feedback without moving the surface: "+key);
   check(await([&]{return !control->property("down").toBool()&&qAbs(surface->property("contactProgress").toDouble())<.001&&surface->property("hoverProgress").toDouble()<.01&&colorDistance(currentColor(),QColor(idleColor))<.001;},1800),"flat toolbar returns completely after canceled release: "+key);
   savePixels(control,key,"released");sample("released");
   if(enabled){
    control->setFocus(false);window->contentItem()->forceActiveFocus(Qt::OtherFocusReason);QCoreApplication::processEvents();control->forceActiveFocus(Qt::TabFocusReason);
    check(await([&]{return window->isActive()&&control->hasActiveFocus()&&control->property("visualFocus").toBool()&&control->property("focusReason").toInt()==Qt::TabFocusReason;},600),"flat toolbar exposes keyboard focus: "+key);
    wait(170);const auto focused=savePixels(control,key,"focus");sample("focus");
    check(focused!=idle&&geometryStable(),"flat toolbar keyboard focus changes pixels without moving or scaling content: "+key);
   }
   sampler.stop();
   check(clicked.isValid()&&clicked.count()==0&&stableGeometry&&control->size()==size&&control->position()==position,"flat toolbar feedback preserves actual scene geometry and invokes no action: "+key);
  };
  const auto auditActivityCard=[&](const QString &key,const QString &detailKey){
   auto *control=item(key);check(control!=nullptr,"actual Activity card exists: "+key);if(!control)return;
   reveal(control);control->setFocus(false);window->contentItem()->forceActiveFocus(Qt::OtherFocusReason);movePointer(park(),170);
   const auto size=control->size();const auto position=control->position();const auto idleRect=sceneRect(control);
   // The reserved card inset is part of its real hit surface and does not
   // overlap the embedded chart filters, source rows or diagnostic refresh.
   const auto point=control->mapToScene(QPointF(size.width()/2,eval("pageLoader.item.cardInset/2").toDouble())).toPoint();
   if(!pointerFits(control,point,key))return;
   QQuickItem *hit=nullptr;for(auto *child:control->childItems())if(child->property("acceptedButtons").isValid()&&child->property("pressed").isValid()){hit=child;break;}
   check(hit!=nullptr,"Activity card exposes its actual pointer hit surface: "+key);if(!hit)return;
   const auto fullLift=eval("Theme.dp(1.5)").toDouble();
   const auto unframed=[&]{return QQmlExpression(qmlContext(control),control,"border.width===0").evaluate().toBool();};
   check(control->property("color").value<QColor>().alphaF()==1&&qAbs(control->property("radius").toDouble()-eval("Theme.cardRadius").toDouble())<.001&&unframed(),"Activity card retains its opaque surface and shared unframed curvature: "+key);
   const auto followsLift=[&]{return sameSceneRect(sceneRect(control),idleRect.translated(0,control->property("lift").toDouble()))&&qAbs(control->scale()-1)<.001;};
   const auto sample=[&](const QString &phase){buttonSamples.append(QJsonObject{{"button",key},{"kind","activity-card"},{"phase",phase},{"activeFocus",control->hasActiveFocus()},{"keyboardFocus",control->property("keyboardFocus").toBool()},{"hovered",control->property("hovered").toBool()},{"pointerPressed",hit->property("pressed").toBool()},{"lift",control->property("lift").toDouble()},{"controlGeometry",geometryEvidence(control)}});};
   QSignalSpy activated(control,SIGNAL(activated()));bool stableGeometry=true,intermediate=false,stableHover=false;
   QTimer sampler;sampler.setTimerType(Qt::PreciseTimer);QObject::connect(&sampler,&QTimer::timeout,window,[&]{stableGeometry&=followsLift();});sampler.start(4);
   QImage idle,hover;
   for(int attempt=0;attempt<3;++attempt){
    movePointer(park());await([&]{return !control->property("hovered").toBool()&&qAbs(control->property("lift").toDouble())<.01;},600);
    idle=savePixels(control,key,"idle");sample("idle");movePointer(point);
    intermediate|=await([&]{const auto lift=control->property("lift").toDouble();return control->property("hovered").toBool()&&lift<0&&lift>-fullLift&&followsLift();},350);sample("hover-intermediate");
    if(!await([&]{return control->property("hovered").toBool()&&control->property("lift").toDouble()<-fullLift*.95;},600)){sample("hover-interrupted");continue;}
    hover=savePixels(control,key,"hover");sample("hover");stableHover=control->property("hovered").toBool()&&control->property("lift").toDouble()<-fullLift*.5;
    if(stableHover)break;sample("hover-interrupted");
   }
   check(intermediate,"Activity card hover passes through an actual intermediate 1.5dp scene lift: "+key);
   check(stableHover&&!hover.isNull()&&hover!=idle,"Activity card hover visibly changes its real pixels: "+key);
   QTest::mousePress(window,Qt::LeftButton,Qt::NoModifier,point);wait(70);savePixels(control,key,"pressed");sample("pressed");
   check(hit->property("pressed").toBool()&&!control->property("pressed").toBool()&&qAbs(control->property("lift").toDouble()+fullLift)<.001&&followsLift()&&unframed(),"Activity card accepts the pointer press without an additional scale, border or press lift: "+key);
   movePointer(park());QTest::mouseRelease(window,Qt::LeftButton,Qt::NoModifier,park());wait(30);sample("release-intermediate");
   check(control->property("lift").toDouble()<0&&followsLift(),"Activity card canceled release continues from its current scene lift: "+key);
   check(await([&]{return !hit->property("pressed").toBool()&&!control->property("hovered").toBool()&&qAbs(control->property("lift").toDouble())<.01;},1800),"Activity card returns completely after canceled release: "+key);
   savePixels(control,key,"released");sample("released");
   control->setFocus(false);window->contentItem()->forceActiveFocus(Qt::OtherFocusReason);QCoreApplication::processEvents();control->forceActiveFocus(Qt::TabFocusReason);
   check(await([&]{return window->isActive()&&control->hasActiveFocus()&&control->property("keyboardFocus").toBool()&&control->property("focused").toBool()&&qAbs(control->property("lift").toDouble()+fullLift)<.001;},600),"Activity card exposes keyboard focus through the same complete scene lift: "+key);
   wait(170);savePixels(control,key,"focus");sample("focus");sampler.stop();
   check(activated.isValid()&&activated.count()==0&&stableGeometry&&control->size()==size&&control->position()==position&&!eval("pageLoader.item.detailOpen").toBool(),"Activity card canceled feedback preserves layout and never activates a detail: "+key);
   QTest::keyClick(window,Qt::Key_Return);
   check(await([&]{
    auto *detail=item("activityDetailTransition");if(!detail||detail->property("detailKey").toString()!=detailKey||detail->property("progress").toDouble()!=1||detail->property("moving").toBool()||!item("activityDetailBack"))return false;
    auto *body=detail->property("bodyItem").value<QQuickItem *>();if(!body||!body->isEnabled())return false;
    for(auto *loader:body->childItems())if(loader->isVisible()&&loader->property("active").toBool()&&loader->property("status").toInt()==1&&loader->property("item").value<QObject *>())return true;
    return false;
   },4000)&&activated.count()==1,"Activity card keyboard activation reaches its loaded functional detail and return control: "+key);
   QTest::keyClick(window,Qt::Key_Escape);
   check(await([&]{return !eval("pageLoader.item.detailOpen").toBool()&&control->hasActiveFocus()&&control->property("keyboardFocus").toBool();},4000),"Activity detail Escape returns keyboard focus to the same source card: "+key);
  };
  const auto auditActivityStatusGeometry=[&]{
   auto *card=item("activityStatusCard"),*fact=item("activityPolicyFact"),*value=item("activityPolicyFactValue"),*emblem=item("activityStatusEmblem"),*header=item("activityStatusHeader");
   QQuickItem *caption=nullptr,*arrow=nullptr;
   if(fact)for(auto *child:fact->childItems())if(child!=value&&child->property("text").toString()==fact->property("caption").toString()){caption=child;break;}
   if(header)for(auto *child:header->childItems())if(child->property("name").toString()=="chevron-right"){arrow=child;break;}
   const auto dpr=window->devicePixelRatio();
   const bool centered=await([&]{return arrow&&header&&arrow->isVisible()&&arrow->height()>0&&qAbs(sceneRect(arrow).center().y()-sceneRect(header).center().y())*dpr<=.5;},1000);
   check(centered,"Activity status title arrow stays centered in the real card header");
   check(caption&&value&&qAbs(caption->mapToScene(QPointF(0,caption->baselineOffset())).y()-value->mapToScene(QPointF(0,value->baselineOffset())).y())*dpr<=.5
       &&caption->property("text").toString()==QStringLiteral("默认策略")&&value->property("text").toString()==eval("pageLoader.item.defaultTargetName").toString()&&!caption->property("truncated").toBool()&&!value->property("truncated").toBool(),
       "Activity default-policy caption and actual target remain complete on the same rendered baseline");
   bool contained=card&&fact&&emblem&&header&&arrow;
   if(contained){
    const auto cardBounds=QRectF(QPointF(),card->size()),emblemBounds=emblem->mapRectToItem(card,emblem->boundingRect());
    contained&=cardBounds.contains(emblemBounds)&&cardBounds.contains(header->mapRectToItem(card,header->boundingRect()))&&header->boundingRect().contains(arrow->mapRectToItem(header,arrow->boundingRect()));
    for(const auto &name:QStringList{"activityNodeSection","activityIpSection","activityNetworkFact","activityProfileFact","activityPolicyFact"}){
     auto *section=item(name);const auto rect=section?section->mapRectToItem(card,section->boundingRect()):QRectF();
     contained&=section&&cardBounds.contains(rect)&&(rect.right()-emblemBounds.left())*dpr<=.5;
    }
   }
   check(contained,"Activity status text and policy facts remain inside the opaque card and outside the reserved feather area");
   buttonSamples.append(QJsonObject{{"button","activityStatusCard"},{"phase","status-policy-alignment"},{"arrowCentered",centered},{"textContained",contained},{"card",geometryEvidence(card)},{"header",geometryEvidence(header)},{"arrow",geometryEvidence(arrow)},{"policyCaption",geometryEvidence(caption)},{"policyValue",geometryEvidence(value)},{"brandArea",geometryEvidence(emblem)}});
  };
  check(route("processes"),"marked process-page audit settles");
  auto *processPage=qobject_cast<QQuickItem *>(eval("pageLoader.item").value<QObject *>());
  const auto processController=processPage?processPage->property("engineController"):QVariant();
  // The actual production page receives a geometry-only row through its view
  // property; it is never inserted into accounting or reported as real traffic.
  eval("pageLoader.item.engineController={telemetry:{revision:0,ranking:function(){return [{id:'motion-geometry',name:'Motion geometry fixture',upload:'0 B',download:'0 B',connections:0,value:'0 B'}]}},routingError:'',networkConfigurationError:'',meteredEnabled:false,meteredAllowlist:[],busy:false,elevated:false};pageLoader.item.selectedId='motion-geometry'");wait(350);
  audit(byText(processPage,QStringLiteral("查看连接")),"process-connections");
  if(processPage)processPage->setProperty("engineController",processController);
  for(const auto &spec:QList<QPair<QString,QString>>{{"rules","addRoutingRule"},{"scripts","scriptAddButton"},{"profiles","profileAddButton"},{"subscriptions","refreshAllSubscriptions"},{"subscriptions","addSubscription"},{"proxies","allNodesTestButton"},{"proxies","nodeImportButton"},{"proxies","nodeAddButton"}}){
   check(route(spec.first),"marked-button page settles: "+spec.first);audit(item(spec.second),spec.second);
  }
  check(route("dns"),"marked DNS-page audit settles");audit(byText(qobject_cast<QQuickItem *>(eval("pageLoader.item").value<QObject *>()),QStringLiteral("添加映射")),"dns-add-mapping");
  check(route("activity"),"marked Activity-page audit settles");
  for(const auto &name:QStringList{"activityOutboundMode","proxyCapsule","tunCapsule"})auditFlatToolbar(item(name),name);
  auditActivityStatusGeometry();
  for(const auto &spec:QList<QPair<QString,QString>>{{"activityStatusCard","connection"},{"activityTrafficCard","traffic"},{"activitySourcesCard","sources"},{"activityDiagnosticCard","diagnostics"},{"activityConnectionsCard","connections"}})auditActivityCard(spec.first,spec.second);
  audit(item("nav-external"),"nav-external");
  check(route("scripts"),"rapid hover audit returns to the actual script action");
  auto *rapid=item("scriptAddButton");
  if(rapid){
   for(int i=0;i<16;++i){movePointer(i%2?park():rapid->mapToScene(QPointF(rapid->width()/2,rapid->height()/2)).toPoint(),8);}
   movePointer(park());
   check(await([&]{return !rapid->property("hovered").toBool()&&!rapid->property("down").toBool()&&qAbs(rapid->property("motionLift").toDouble())<.01&&qAbs(rapid->property("motionScale").toDouble()-1)<.001;},1800),"rapid actual-button enter/leave interruptions settle without a stale state");
   movePointer(rapid->mapToScene(QPointF(rapid->width()/2,rapid->height()/2)).toPoint(),35);
   check(route("profiles")&&route("scripts")&&!rapid->property("down").toBool(),"page switching during actual-button hover returns a synchronized live control");
  }
  window->setGeometry(geometry);movePointer(park(),170);
#ifdef Q_OS_WIN
  window->setFlag(Qt::WindowStaysOnTopHint,wasTopmost);
  SetWindowPos(reinterpret_cast<HWND>(window->winId()),wasTopmost?HWND_TOPMOST:HWND_NOTOPMOST,0,0,0,0,SWP_NOMOVE|SWP_NOSIZE|SWP_NOACTIVATE);
#endif
 }
 check(controller->processId()==pid&&controller->selectedNodeId()==selected&&controller->nodes().size()==nodeCount,"navigation preserves proxy process, selected node and stored records");
 // Restoring the window height retargets the bottom-anchored sidebar selection
 // for selectionDuration (240 ms). Observe completion rather than assuming
 // the preceding fixed geometry wait also finishes every transition.
 const bool resourcesReleased=await([&]{return eval("motionPolicy.activeGrabCount===0 && SwirlTransitionRegistry.activeCount===0 && dismissals.count===0").toBool();},2000);
 if(!resourcesReleased){
  auto *sidebarMotion=item("sidebarArcMotion");
  qInfo()<<"NAVIGATION_RESOURCE_STATE"<<"activeGrabCount"<<eval("motionPolicy.activeGrabCount").toInt()
      <<"activeTransitions"<<eval("SwirlTransitionRegistry.activeCount").toInt()
      <<"dismissals"<<eval("dismissals.count").toInt()
      <<"sidebarArcMoving"<<(sidebarMotion&&sidebarMotion->property("moving").toBool());
 }
 check(resourcesReleased,"navigation releases all transient resources");
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
 // CTest can use this completed suite as Hero's prerequisite. Stream the
 // executable rather than trusting a build label or loading the EXE into RAM.
 QFile executable(QCoreApplication::applicationFilePath());
 QCryptographicHash executableHash(QCryptographicHash::Sha256);
 const bool executableHashed=executable.open(QIODevice::ReadOnly)&&executableHash.addData(&executable);
 const QString executableSha256=executableHashed?QString::fromLatin1(executableHash.result().toHex()):QString();
 check(executableHashed&&!executableSha256.isEmpty(),"completed navigation evidence identifies the actual executable");
 QSaveFile file(directory+"/navigation-report.json");
 const auto report=QJsonDocument(QJsonObject{{"test","swirl-navigation-ui"},{"executableSha256",executableSha256},
     {"completedUtc",QDateTime::currentDateTimeUtc().toString(Qt::ISODateWithMs)},
     {"githubRunId",qEnvironmentVariable("GITHUB_RUN_ID")},{"githubRunAttempt",qEnvironmentVariable("GITHUB_RUN_ATTEMPT")},{"githubSha",qEnvironmentVariable("GITHUB_SHA")},
     {"checks",checks},{"nativeMotionPolicy",nativeMotionPolicy},{"endpointSamples",endpointSamples},{"buttonSamples",buttonSamples},{"buttonAuditScope","Actual production page controls; canceled pointer releases invoke no commands. Process detail uses one page-local geometry row, never accounting data. Empty-source refresh-all is verified disabled."},{"performance",performance},{"failures",failures},{"nativeHandleUnchanged",window->winId()==handle},{"dpr",window->devicePixelRatio()}}).toJson();
 if(!file.open(QIODevice::WriteOnly)||file.write(report)!=report.size()||!file.commit()){
  qWarning()<<"NAVIGATION_REPORT_WRITE_FAILED"<<file.errorString();return failures+1;
 }
 return failures;
}
