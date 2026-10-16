#include "NavigationChecks.h"
#include "engine/EngineController.h"
#include "app/MotionPolicy.h"
#include <QQuickWindow>
#include <QQuickItem>
#include <QGuiApplication>
#include <QQmlExpression>
#include <QQmlContext>
#include <QTest>
#include <QFile>
#include <QJsonDocument>
#include <QJsonArray>
#include <QJsonObject>
#include <QDir>
#include <QElapsedTimer>
#include <QSet>
#include <QMap>
#include <functional>

int runNavigationChecks(QQuickWindow *window,EngineController *controller,const QString &directory) {
 int failures=0;QJsonArray checks;QDir().mkpath(directory);
 auto check=[&](bool ok,const QString &name){checks.append(QJsonObject{{"name",name},{"passed",ok}});if(!ok)++failures;qInfo()<<"NAVIGATION_CHECK"<<name<<ok;};
 auto eval=[&](const QString &code){QQmlExpression expression(qmlContext(window),window,code);auto value=expression.evaluate();if(expression.hasError()){qWarning()<<expression.error();++failures;}return value;};
 std::function<QQuickItem *(QQuickItem *,const QString &)> find;
 find=[&](QQuickItem *parent,const QString &name)->QQuickItem *{if(parent->objectName()==name&&parent->isVisible())return parent;for(auto *child:parent->childItems())if(auto *value=find(child,name))return value;return nullptr;};
 auto item=[&](const QString &name){return find(window->contentItem(),name);};
 auto settled=[&]{return eval("pageLoader.item && !pageLoader.moving && !pageLoader.pendingGrab && pageLoader.activeLoader.routeId===AppState.currentPage").toBool();};
 auto settle=[&]{return QTest::qWaitFor(settled,4000);};
 auto click=[&](const QString &name){auto *control=item(name);check(control!=nullptr,"input exists: "+name);if(control)QTest::mouseClick(window,Qt::LeftButton,Qt::NoModifier,control->mapToScene(QPointF(control->width()/2,control->height()/2)).toPoint());};
 auto route=[&](const QString &id){eval("AppState.navigate('"+id+"')");return settle();};
 if(controller->nodes().isEmpty()){
  QString yaml="proxies:\n";for(int i=0;i<180;++i)yaml+=QString("  - {name: 'Fixture node %1', type: socks5, server: 127.0.0.1, port: 9}\n").arg(i,3,10,QChar('0'));
  controller->imports()->importText(yaml);
  check(QTest::qWaitFor([&]{return !controller->imports()->busy();},8000)&&controller->nodes().size()==180,"standalone navigation fixture imports 180 local node records");
 }
 auto *policy=qobject_cast<MotionPolicy *>(qmlContext(window)->contextProperty("motionPolicy").value<QObject *>());
 const bool standalone=qApp->arguments().contains("--navigation-test");
 if(standalone&&policy)policy->setSystemReducedMotionOverrideForTest(0);
 struct RestorePolicy {MotionPolicy *policy;bool enabled;~RestorePolicy(){if(enabled&&policy)policy->setSystemReducedMotionOverrideForTest(-1);}} restorePolicy{policy,standalone};
 const auto handle=window->winId();const auto geometry=window->geometry();
 const auto pid=controller->processId();const auto selected=controller->selectedNodeId();const auto nodeCount=controller->nodes().size();
 eval("Theme.reduceMotion=false;SwirlMotion.speed=1");check(route("featurehub"),"card hub settles before input");
 auto *hub=eval("pageLoader.item").value<QObject *>();
 check(!item("settingsBackButton"),"settings hub has no redundant back control");
 QSet<QWindow *> windows;for(auto *candidate:QGuiApplication::allWindows())windows.insert(candidate);
 auto noNewWindows=[&]{for(auto *candidate:QGuiApplication::allWindows())if(!windows.contains(candidate))return false;return true;};
 const QStringList routes{"settings","appearance","fonts","dns","modules","profiles","scripts","subscriptions","proxies"};
 QMap<QString,QObject *> pages;
 for(int round=0;round<2;++round)for(const auto &id:routes){
  auto *source=item("settings-"+id);check(source!=nullptr,"hub card remains reachable: "+id);
  click("settings-"+id);
  bool coverage=true,sawMorph=false,unframed=true,backFollowsPage=true;int frame=0;QJsonArray frameTimes;QElapsedTimer timer;timer.start();
  do {
   QTest::qWait(6);
   coverage&=eval("Object.keys(pageLoader.pages).reduce((sum,key)=>sum+(pageLoader.pages[key].visible?pageLoader.pages[key].opacity:0),0)>0.98").toBool();
   sawMorph|=eval("pageLoader.moving && pageLoader.heroData && pageLoader.heroData.key==='settings'").toBool();
   backFollowsPage&=eval("!pageLoader.heroData || pageLoader.heroData.key!=='settings' || pageLoader.position>=0.82 || settingsBack.opacity===0").toBool();
   if(auto *morph=item("sharedSurface")){
    unframed&=!morph->property("independentCard").toBool()&&morph->property("radius").toDouble()>0&&QQmlExpression(qmlContext(morph),morph,"border.width===0").evaluate().toBool();
    unframed&=QQmlExpression(qmlContext(morph),morph,"!settingsTransition || color.a<0.01 || Math.abs(color.r-(host.heroData.returning?host.heroData.toColor.r:host.heroData.fromColor.r))<0.005").evaluate().toBool();
   }
   if(round==0&&id=="subscriptions"&&!qApp->arguments().contains("--hero-no-recording")&&eval("pageLoader.moving").toBool()){
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
  if(id=="appearance"||id=="fonts"||id=="settings")check(page&&page->property("section").toString()==(id=="appearance"?"外观":id=="fonts"?"字体":"常规"),"independent settings sections retain their route: "+id);
  if(round==0&&id=="dns")if(auto *field=item("dnsServerAddress"))field->setProperty("text","1.1.1.1, 8.8.8.8");
  if(round==1&&id=="dns")check(item("dnsServerAddress")&&item("dnsServerAddress")->property("text").toString()=="1.1.1.1, 8.8.8.8","unsubmitted DNS draft survives back and re-entry");
  if(id=="proxies"){
   auto *search=item("nodeSearchField"),*table=item("realNodeTable");
   if(round==0&&search){
    search->setProperty("text","Fixture node 1");QTest::qWait(30);
    if(table)table->setProperty("scrollPosition",88);
   }
   else if(round==1){
    check(search&&search->property("text").toString()=="Fixture node 1","node search is retained across back navigation");
    check(table&&qAbs(table->property("scrollPosition").toDouble()-88)<1,"node table scroll position survives back and re-entry");
    if(search)search->setProperty("text","");
   }
   if(table)check(table->property("renderedRows").toInt()>0&&table->property("renderedRows").toInt()<60,"180-node table only mounts the visible virtualized rows");
  }
  if(!qApp->arguments().contains("--hero-no-recording")&&(id=="dns"||id=="proxies"||id=="appearance"))window->grabWindow().save(directory+"/"+id+"-embedded.png");
  click("settingsBackButton");check(settle()&&eval("AppState.currentPage==='featurehub'").toBool()&&eval("pageLoader.item").value<QObject *>()==hub,"back returns to the same cached hub: "+id);
 }
 const auto cacheCount=eval("pageLoader.cachedPageCount").toInt();
 for(int i=0;i<27;++i){eval("window.openSettings('"+routes[i%routes.size()]+"')");QTest::qWait(9);}
 check(settle()&&eval("AppState.currentPage==='proxies'").toBool(),"rapid requests settle at the last requested route");
 check(noNewWindows()&&eval("pageLoader.cachedPageCount").toInt()==cacheCount,"rapid requests create one cached instance per route and no windows");
 route("featurehub");click("settings-subscriptions");
 QTest::qWait(70);auto *surface=item("sharedSurface");const auto before=surface?QRectF(surface->position(),surface->size()):QRectF();
 eval("window.closeSettings()");QCoreApplication::processEvents();
 const auto after=surface?QRectF(surface->position(),surface->size()):QRectF();
 qInfo()<<"NAVIGATION_REVERSE"<<before<<after;
 check(surface&&eval("pageLoader.retargetRequestedRect===pageLoader.retargetCommittedRect").toBool(),"mid-flight back reverses from the current displayed boundary");
 check(settle()&&eval("AppState.currentPage==='featurehub'").toBool(),"interrupted expansion returns cleanly");
 route("proxies");auto *page=qobject_cast<QQuickItem *>(pages.value("proxies"));
 window->resize(window->minimumWidth(),window->minimumHeight());QTest::qWait(180);
 auto *table=item("realNodeTable");check(table&&page&&table->mapToItem(page,QPointF()).x()>=0&&table->mapToItem(page,QPointF(table->width(),table->height())).x()<=page->width()+1,"node table fits the main content at minimum window size");
 check(item("nodeSearchField")&&item("nodeCountryFilter")&&item("nodeImportButton")&&item("nodeAddButton")&&item("allNodesTestButton"),"embedded nodes retain search, filters, import, add and test controls");
 window->setGeometry(geometry);QTest::qWait(150);
 check(controller->processId()==pid&&controller->selectedNodeId()==selected&&controller->nodes().size()==nodeCount,"navigation preserves proxy process, selected node and stored records");
 check(eval("motionPolicy.activeGrabCount===0 && SwirlTransitionRegistry.activeCount===0").toBool(),"navigation releases all transient resources");
 route("featurehub");
 QFile file(directory+"/navigation-report.json");if(file.open(QIODevice::WriteOnly))file.write(QJsonDocument(QJsonObject{{"checks",checks},{"failures",failures},{"nativeHandleUnchanged",window->winId()==handle},{"dpr",window->devicePixelRatio()}}).toJson());
 return failures;
}
