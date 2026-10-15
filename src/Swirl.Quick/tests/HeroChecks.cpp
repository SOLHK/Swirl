#include "HeroChecks.h"
#include "engine/EngineController.h"
#include <QQuickWindow>
#include <QQuickItem>
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
#include <QPainter>
#include <QCoreApplication>
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
int runHeroChecks(QQuickWindow *window,EngineController *controller,const QString &directory) {
 if(!window||!controller)return 3;QDir().mkpath(directory);
 auto wait=[](int milliseconds){QEventLoop loop;QTimer timer;timer.setTimerType(Qt::PreciseTimer);timer.setSingleShot(true);QObject::connect(&timer,&QTimer::timeout,&loop,&QEventLoop::quit);timer.start(milliseconds);loop.exec();};
 QJsonArray checks;int failures=0;QJsonArray nodeClickMs;
 auto check=[&](bool value,const QString &name){checks.append(QJsonObject{{"name",name},{"passed",value}});if(!value)++failures;qInfo()<<"HERO_CHECK"<<name<<value;};
 auto eval=[&](const QString &code){QQmlExpression expression(qmlContext(window),window,code);auto result=expression.evaluate();if(expression.hasError()){++failures;qWarning()<<expression.error();}return result;};
 std::function<QQuickItem *(QQuickItem *,const QString &)> find;
 find=[&](QQuickItem *parent,const QString &name)->QQuickItem *{if(parent->objectName()==name)return parent;for(auto child:parent->childItems())if(auto match=find(child,name))return match;return nullptr;};
 auto item=[&](const QString &name,QQuickWindow *owner=nullptr){return find((owner?owner:window)->contentItem(),name);};
 auto click=[&](const QString &name,QQuickWindow *owner=nullptr){auto control=item(name,owner);if(!control){check(false,"input exists: "+name);return;}QTest::mouseClick(owner?owner:window,Qt::LeftButton,Qt::NoModifier,control->mapToScene(QPointF(control->width()/2,control->height()/2)).toPoint());};
 auto route=[&](const QString &name){eval("AppState.navigate('"+name+"')");wait(350);};
 const bool recording=!QCoreApplication::arguments().contains("--hero-no-recording");
 auto snapshot=[&](const QString &name,QQuickWindow *sheet=nullptr){if(!recording)return true;auto image=window->grabWindow();if(sheet&&sheet->isVisible()){QPainter painter(&image);painter.drawImage(sheet->position()-window->position(),sheet->grabWindow());}return image.save(directory+"/"+name+".png");};
 auto record=[&](const QString &name,QQuickWindow *sheet=nullptr){QDir().mkpath(directory+"/"+name);for(int frame=0;frame<26;++frame){snapshot(name+QString("/%1").arg(frame,3,10,QChar('0')),sheet);wait(10);}};
 window->resize(1100,850);window->setPosition(window->screen()->availableGeometry().topLeft()+QPoint(40,40));window->show();window->requestActivate();
#ifdef Q_OS_WIN
 window->setFlag(Qt::WindowStaysOnTopHint,true);
 const HWND qaWindow=reinterpret_cast<HWND>(window->winId());
 SetWindowPos(qaWindow,HWND_TOPMOST,0,0,0,0,SWP_NOMOVE|SWP_NOSIZE|SWP_NOACTIVATE);
 struct RestoreQaStack {QQuickWindow *window;~RestoreQaStack(){window->setFlag(Qt::WindowStaysOnTopHint,false);}} restoreQaStack{window};
#endif
 eval("Theme.mode='Light';Theme.transparency=true;Theme.reduceMotion=false;SwirlMotion.speed=1");route("featurehub");
 check(item("settings-proxies")&&item("settings-subscriptions")&&!item("settings-license"),"More has direct node/subscription entries and no paid license entry");
 auto origin=item("settings-subscriptions");click("settings-subscriptions");
 QQuickWindow *sheet=nullptr;for(auto candidate:QGuiApplication::allWindows())if(candidate->objectName()=="settingsSheet")sheet=qobject_cast<QQuickWindow *>(candidate);
#ifdef Q_OS_WIN
 if(sheet){sheet->setFlag(Qt::WindowStaysOnTopHint,true);SetWindowPos(reinterpret_cast<HWND>(sheet->winId()),HWND_TOPMOST,0,0,0,0,SWP_NOMOVE|SWP_NOSIZE|SWP_NOACTIVATE);}
#endif
 check(sheet&&sheet->isVisible()&&eval("settingsSheet.section==='subscriptions'").toBool(),"settings window responds synchronously to the originating card");
 if(sheet){record("more-open",sheet);check(origin&&origin->property("transfer").toDouble()>0.99,"source card keeps its shared return identity while native sheet is open");
  auto settingsPage=eval("settingsLoader.item").value<QObject *>();QTest::keyClick(sheet,Qt::Key_Escape);record("more-return",sheet);wait(100);check(!sheet->isVisible()&&window->isVisible(),"Escape returns from the native sheet without closing the main window");
  check(origin&&origin->property("transfer").toDouble()==0&&origin->hasActiveFocus(),"return restores originating card geometry and keyboard focus");
  click("settings-subscriptions");wait(350);check(settingsPage&&eval("settingsLoader.item").value<QObject *>()==settingsPage,"secondary route cache retains the original subscription page");QTest::keyClick(sheet,Qt::Key_Escape);wait(350);
  click("settings-fonts");wait(350);
  check(sheet->isVisible()&&eval("settingsLoader.item.section==='字体' && Theme.fontFamily===fontManager.defaultFamily").toBool(),"More font entry opens the platform default font settings");
  check(find(sheet->contentItem(),"fontFamilyList")&&find(sheet->contentItem(),"fontImport")&&find(sheet->contentItem(),"fontReset"),"font chooser, import and reset controls are available in the native settings window");
  if(!qApp->arguments().contains("--hero-no-recording"))sheet->grabWindow().save(directory+"/font-settings.png");
  QTest::keyClick(sheet,Qt::Key_Escape);wait(350);
 }
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
 QString yaml="proxies:\n";for(int i=0;i<180;++i)yaml+=QString("  - {name: 'Fixture node %1', type: socks5, server: 127.0.0.1, port: 9}\n").arg(i,3,10,QChar('0'));
 controller->imports()->importText(yaml);check(QTest::qWaitFor([&]{return !controller->imports()->busy();},8000)&&controller->nodes().size()==180,"180 synthetic node records imported by the real importer for rendering stress only");
 route("proxies");auto table=item("realNodeTable");
 check(table&&eval("pageLoader.item.viewRows.length===180").toBool(),"node list exposes all 180 records");
 if(table){auto point=[&](int row){return table->mapToScene(QPointF(65,table->property("headerHeight").toDouble()+table->property("itemHeight").toInt()*(row+0.5))).toPoint();};
  QElapsedTimer response;response.start();
  QTest::mouseClick(window,Qt::LeftButton,Qt::NoModifier,point(1));
  const double dispatchMs=response.nsecsElapsed()/1000000.0;nodeClickMs.append(dispatchMs);
  auto hero=item("nodeHero");auto identity=item("nodeIdentitySurface");auto requestSurface=item("nodeRequestSurface");
  check(controller->selectedNodeName()=="Fixture node 001","node selection reaches the actual clicked row");
  check(item("nodeDetailTitle")&&item("nodeDetailTitle")->property("text").toString()==controller->selectedNodeName(),"detail title updates in the click handler without an animation wait");
  check(hero&&hero->property("moving").toBool()&&identity&&requestSurface&&identity->isVisible(),"node selection starts the restored boundary transition with mounted detail controls");
  check(dispatchMs<100,"180-node click dispatch completes within 100 ms");
  qInfo()<<"NODE_CLICK_DISPATCH_MS"<<dispatchMs;record("node-local");
  check(QTest::qWaitFor([&]{return hero&&!hero->property("moving").toBool()&&requestSurface&&requestSurface->isVisible()&&requestSurface->opacity()>0.99;},2000),"detail controls reach full opacity after the boundary transition");
  const auto identityRect=identity?QRectF(identity->position(),identity->size()):QRectF();
  double slowest=dispatchMs;
  for(int i=0;i<10;++i){response.restart();QTest::mouseClick(window,Qt::LeftButton,Qt::NoModifier,point(i%6));const auto ms=response.nsecsElapsed()/1000000.0;nodeClickMs.append(ms);slowest=qMax(slowest,ms);wait(12);}
  check(item("nodeDetailTitle")&&item("nodeDetailTitle")->property("text").toString()==controller->selectedNodeName(),"rapid selection keeps the latest clicked node");
  check(QTest::qWaitFor([&]{return hero&&!hero->property("moving").toBool();},2000),"rapid selection settles the last requested boundary");
  check(identity&&identity==item("nodeIdentitySurface")&&QRectF(identity->position(),identity->size())==identityRect,"rapid selection retains the same inspector and returns to its settled geometry");
  check(slowest<100,"all rapid node click dispatches complete within 100 ms");qInfo()<<"NODE_CLICK_MAX_MS"<<slowest;
  check(table->scale()==1&&eval("motionPolicy.activeGrabCount===0 && SwirlTransitionRegistry.activeCount===0").toBool(),"settled node selection retains no table textures or transient transition resources");
  click("nodeReturnButton");record("node-return");
  check(hero&&!hero->property("opened").toBool(),"return closes the inspector immediately");
  QTest::mouseClick(window,Qt::LeftButton,Qt::NoModifier,point(3));wait(50);
 }
 snapshot("nodes-180");check(!controller->processAlive(),"rendering fixture selection never starts a proxy or fabricates a connection");
 if(auto *search=item("nodeSearchField")) {
  QElapsedTimer filter;filter.start();search->setProperty("text","179");const double filterMs=filter.nsecsElapsed()/1000000.0;
  check(eval("pageLoader.item.viewRows.length===1 && pageLoader.item.viewRows[0].name==='Fixture node 179'").toBool(),"tail search prunes a large prefix and keeps the real node ID");
  check(filterMs<100,"180-node tail filter updates within 100 ms");qInfo()<<"NODE_FILTER_DISPATCH_MS"<<filterMs;
  search->setProperty("text","");check(eval("pageLoader.item.viewRows.length===180").toBool(),"clearing search restores the entire catalog");
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
 QFile report(directory+"/hero-report.json");if(!report.open(QIODevice::WriteOnly))return 3;
 report.write(QJsonDocument(QJsonObject{{"nodeClickDispatchMs",nodeClickMs},{"checks",checks},{"failures",failures},{"dxgiPresentations",displaySamples},{"dxgiStatisticsErrors",statisticsErrors},{"animationWindows",animationWindows},{"refreshPhases",refreshPhases},{"resourceBefore",resourceBefore},{"resourceAfter",resources()},{"minimizedIdle",background},{"performanceStartQpcMs",performanceStart},{"performanceEndQpcMs",performanceEnd},{"reportedRefreshHz",window->screen()->refreshRate()},{"nativeDpr",window->devicePixelRatio()},{"sampleCount",intervals.size()},{"meanFrameDeliveryMs",mean},{"p95FrameDeliveryMs",intervals.isEmpty()?0:intervals[qMin(intervals.size()-1,qsizetype(intervals.size()*0.95))]},{"p99FrameDeliveryMs",intervals.isEmpty()?0:intervals[qMin(intervals.size()-1,qsizetype(intervals.size()*0.99))]},{"method","Passive Qt frameSwapped delivery during native interaction, excluding screenshot readback. These intervals are not hardware display presentation FPS; use external PresentMon data for presentation evidence."}}).toJson());
 return failures?2:0;
}
