#include "HeroChecks.h"
#include "engine/EngineController.h"
#include "app/MotionPolicy.h"
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
#include <QSet>
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
 quint64 settingsFrames=0,settingsRequestFrame=0;
 std::function<QQuickItem *(QQuickItem *,const QString &)> find;
 find=[&](QQuickItem *parent,const QString &name)->QQuickItem *{if(parent->objectName()==name&&parent->isVisible())return parent;for(auto child:parent->childItems())if(auto match=find(child,name))return match;return nullptr;};
 auto item=[&](const QString &name,QQuickWindow *owner=nullptr){return find((owner?owner:window)->contentItem(),name);};
 auto click=[&](const QString &name,QQuickWindow *owner=nullptr){auto control=item(name,owner);if(!control){check(false,"input exists: "+name);return;}if(name.startsWith("settings-"))settingsRequestFrame=settingsFrames;QTest::mouseClick(owner?owner:window,Qt::LeftButton,Qt::NoModifier,control->mapToScene(QPointF(control->width()/2,control->height()/2)).toPoint());};
 auto route=[&](const QString &name){eval("AppState.navigate('"+name+"')");wait(350);};
 const bool recording=!QCoreApplication::arguments().contains("--hero-no-recording");
 QQuickWindow *settingsFlight=nullptr;
 auto snapshot=[&](const QString &name,QQuickWindow *sheet=nullptr){if(!recording)return true;auto image=window->grabWindow();QPainter painter(&image);if(settingsFlight&&settingsFlight->isVisible())painter.drawImage(settingsFlight->position()-window->position(),settingsFlight->grabWindow());if(sheet&&sheet->isVisible())painter.drawImage(sheet->position()-window->position(),sheet->grabWindow());painter.end();return image.save(directory+"/"+name+".png");};
 auto record=[&](const QString &name,QQuickWindow *sheet=nullptr){if(!recording)return;QDir().mkpath(directory+"/"+name);QElapsedTimer clock;clock.start();QJsonArray timestamps;for(int frame=0;frame<26;++frame){const auto file=QString("%1.png").arg(frame,3,10,QChar('0'));const auto start=clock.nsecsElapsed()/1000000.0;snapshot(name+"/"+file.chopped(4),sheet);timestamps.append(QJsonObject{{"file",file},{"captureStartMs",start},{"captureEndMs",clock.nsecsElapsed()/1000000.0}});wait(10);}QFile output(directory+"/"+name+"/frame-timestamps.json");if(output.open(QIODevice::WriteOnly))output.write(QJsonDocument(QJsonObject{{"frames",timestamps},{"durationMs",clock.nsecsElapsed()/1000000.0},{"method","Actual monotonic readback times; requested 10ms waits are not an assumed frame rate. Qt window readbacks do not capture the final DWM desktop contour."}}).toJson());};
 window->resize(1100,850);window->setPosition(window->screen()->availableGeometry().topLeft()+QPoint(40,40));window->show();window->requestActivate();
#ifdef Q_OS_WIN
 window->setFlag(Qt::WindowStaysOnTopHint,true);
 const HWND qaWindow=reinterpret_cast<HWND>(window->winId());
 SetWindowPos(qaWindow,HWND_TOPMOST,0,0,0,0,SWP_NOMOVE|SWP_NOSIZE|SWP_NOACTIVATE);
 struct RestoreQaStack {QQuickWindow *window;~RestoreQaStack(){window->setFlag(Qt::WindowStaysOnTopHint,false);}} restoreQaStack{window};
#endif
 eval("Theme.mode='Light';Theme.transparency=true;Theme.reduceMotion=false;SwirlMotion.speed=1");route("featurehub");
 check(!eval("SwirlMotion.reduced").toBool(),"animated fixture resolves independently of the Windows accessibility preference");
 check(item("settings-proxies")&&item("settings-subscriptions")&&!item("settings-license"),"More has direct node/subscription entries and no paid license entry");
 QJsonArray settingsPerformance;
 settingsFlight=qobject_cast<QQuickWindow *>(eval("settingsFlight").value<QObject *>());
 auto *profileSheet=qobject_cast<QQuickWindow *>(eval("settingsSheet").value<QObject *>());
 QObject settingsFrameScope;
 if(profileSheet)QObject::connect(profileSheet,&QQuickWindow::frameSwapped,&settingsFrameScope,[&]{++settingsFrames;},Qt::QueuedConnection);
 const auto awaitSettings=[&](const std::function<bool()> &condition,int timeout=3000){
  if(!settingsFlight||!profileSheet)return false;QElapsedTimer budget;budget.start();
  while(!condition()&&budget.elapsed()<timeout){
   QEventLoop loop;QTimer deadline;deadline.setSingleShot(true);
   QObject::connect(&deadline,&QTimer::timeout,&loop,&QEventLoop::quit);
   QObject::connect(profileSheet,&QWindow::visibleChanged,&loop,&QEventLoop::quit);
   QObject::connect(settingsFlight,&QWindow::visibleChanged,&loop,&QEventLoop::quit);
   QObject::connect(settingsFlight,SIGNAL(movingChanged()),&loop,SLOT(quit()));
   QObject::connect(profileSheet,&QQuickWindow::frameSwapped,&loop,&QEventLoop::quit,Qt::QueuedConnection);
   QObject::connect(window,&QQuickWindow::activeFocusItemChanged,&loop,&QEventLoop::quit);
   QObject::connect(window,&QWindow::activeChanged,&loop,&QEventLoop::quit);
   deadline.start(qMax(1,timeout-int(budget.elapsed())));loop.exec();
  }
  return condition();
 };
 const auto nativeSettingsReady=[&]{return profileSheet&&profileSheet->isVisible()&&profileSheet->isExposed()&&settingsFrames>settingsRequestFrame&&settingsFlight&&!settingsFlight->isVisible()&&!settingsFlight->property("moving").toBool()&&eval("settingsLoader.activeLoader && settingsLoader.activeLoader.routeId===settingsSheet.section && (settingsLoader.item.section===undefined || settingsLoader.item.section===(settingsSheet.section==='appearance'?'外观':settingsSheet.section==='fonts'?'字体':settingsSheet.section==='license'?'关于 Swirl':'常规'))").toBool();};
 const auto settingsReturned=[&]{return settingsFlight&&settingsFlight->property("phase")=="Idle"&&!settingsFlight->isVisible()&&!profileSheet->isVisible();};
 int settingsRounds=3;
 for(const auto &argument:QCoreApplication::arguments())if(argument.startsWith("--hero-settings-rounds=")){bool ok=false;const auto value=argument.mid(QString("--hero-settings-rounds=").size()).toInt(&ok);if(ok)settingsRounds=qBound(1,value,30);}
 const auto settingsResources=[&]{
  auto snapshot=heroProcessResources();QSet<QObject *> visited;std::function<void(QObject *)> count;
  count=[&](QObject *object){if(!object||visited.contains(object))return;visited.insert(object);for(auto *child:object->children())count(child);if(auto *visual=qobject_cast<QQuickItem *>(object))for(auto *child:visual->childItems())count(child);};
  count(eval("settingsLoader").value<QObject *>());snapshot.insert("cachedPages",eval("settingsLoader.cachedPageCount").toInt());snapshot.insert("qmlObjects",visited.size());return snapshot;
 };
 if(settingsFlight&&profileSheet){
  SettingsFrameProbe probe(settingsFlight);
  QObject::connect(settingsFlight,SIGNAL(movingChanged()),&probe,SLOT(syncMoving()),Qt::DirectConnection);
  QObject::connect(settingsFlight,&QQuickWindow::afterAnimating,&probe,&SettingsFrameProbe::syncSurface,Qt::DirectConnection);
  auto connection=QObject::connect(settingsFlight,&QQuickWindow::frameSwapped,settingsFlight,[&]{probe.frame();},Qt::DirectConnection);
  const auto summary=[&](QList<double> values){QJsonArray raw;for(const auto value:values)raw.append(value);std::sort(values.begin(),values.end());int over16=0,over33=0,overTwo=0;const auto budget=1000/qMax(1.0,window->screen()->refreshRate());for(const auto value:values){over16+=value>16.667;over33+=value>33.333;overTwo+=value>2*budget;}return QJsonObject{{"samples",values.size()},{"p95Ms",values.isEmpty()?0:values[qMin(values.size()-1,qsizetype(values.size()*0.95))]},{"p99Ms",values.isEmpty()?0:values[qMin(values.size()-1,qsizetype(values.size()*0.99))]},{"maxMs",values.isEmpty()?0:values.last()},{"over16_67Ms",over16},{"over33_33Ms",over33},{"overTwoDisplayPeriods",overTwo},{"rawIntervalsMs",raw}};};
  for(int round=0;round<settingsRounds;++round){
   const auto before=settingsResources();QElapsedTimer roundClock;roundClock.start();QList<double> entering,returning;QJsonArray transitions;
   for(const auto *entry:{"settings","appearance","fonts","dns","modules","profiles","scripts","subscriptions","proxies"}){
    const auto routeId=QString::fromLatin1(entry);const bool cacheHit=eval("settingsLoader.pages['"+routeId+"']!==undefined").toBool();
    QElapsedTimer requestClock;requestClock.start();probe.begin();click("settings-"+routeId);
    const bool opened=awaitSettings(nativeSettingsReady);const auto opening=probe.finish();entering.append(opening.intervals);
    transitions.append(QJsonObject{{"route",routeId},{"direction","enter"},{"cacheHit",cacheHit},{"firstFrameMs",opening.firstFrameMs},{"firstFrameReveal",opening.firstReveal},{"firstFrameRect",QJsonObject{{"x",opening.firstRect.x()},{"y",opening.firstRect.y()},{"width",opening.firstRect.width()},{"height",opening.firstRect.height()}}},{"requestToCompletedMs",requestClock.elapsed()},{"intervals",summary(opening.intervals)}});
    check(opened,"passive setting performance run reaches its native page");
    check(opening.firstFrameMs>=0&&!opening.intervals.isEmpty(),"animated settings entry supplies real moving-window frame samples");
    requestClock.restart();probe.begin();QTest::keyClick(profileSheet,Qt::Key_Escape);
    const bool closed=awaitSettings(settingsReturned);const auto closing=probe.finish();returning.append(closing.intervals);
    transitions.append(QJsonObject{{"route",routeId},{"direction","return"},{"firstFrameMs",closing.firstFrameMs},{"firstFrameReveal",closing.firstReveal},{"firstFrameRect",QJsonObject{{"x",closing.firstRect.x()},{"y",closing.firstRect.y()},{"width",closing.firstRect.width()},{"height",closing.firstRect.height()}}},{"requestToCompletedMs",requestClock.elapsed()},{"intervals",summary(closing.intervals)}});
    check(closed,"passive setting performance run returns to its card");
    check(closing.firstFrameMs>=0&&!closing.intervals.isEmpty(),"animated settings return supplies real moving-window frame samples");
   }
   const auto after=settingsResources();settingsPerformance.append(QJsonObject{{"round",round+1},{"wallMs",roundClock.elapsed()},{"before",before},{"after",after},{"cpuMs",after.value("cpuMs").toDouble()-before.value("cpuMs").toDouble()},{"enter",summary(entering)},{"return",summary(returning)},{"transitions",transitions}});
  }
  QObject::disconnect(connection);
  const auto beforeIdle=settingsResources();wait(3000);const auto afterIdle=settingsResources();
  const bool settingsOnly=QCoreApplication::arguments().contains("--hero-settings-only");
  if(settingsOnly){policy->setSystemReducedMotionOverrideForTest(-1);check(policy->systemReducedMotion()==actualSystemReducedMotion,"settings performance fixture restores the actual Windows accessibility policy");}
  QFile performance(directory+"/settings-performance.json");if(performance.open(QIODevice::WriteOnly))performance.write(QJsonDocument(QJsonObject{{"actualSystemReducedMotion",actualSystemReducedMotion},{"animatedSystemPolicyFixture",0},{"rounds",settingsPerformance},{"failures",failures},{"checks",checks},{"beforeNaturalIdle",beforeIdle},{"afterNaturalIdle",afterIdle},{"naturalIdleMs",3000},{"qtRefreshHz",window->screen()->refreshRate()},{"nativeDpr",window->devicePixelRatio()},{"method","Signal-driven event loop; passive frameSwapped intervals from the moving settings transfer window only. No screenshot, forced update, garbage collection or resource release in this segment. No physical display mode change. Cache-hit metadata distinguishes first construction from warm visits. All intervals including long frames retained; Qt delivery times are not hardware presentation FPS. Process private/working-set counters do not separately attribute GPU backing allocations."}}).toJson());
  if(settingsOnly)return failures?2:0;
 }
 auto origin=item("settings-subscriptions");click("settings-subscriptions");
 QQuickWindow *sheet=nullptr;for(auto candidate:QGuiApplication::allWindows())if(candidate->objectName()=="settingsSheet")sheet=qobject_cast<QQuickWindow *>(candidate);
#ifdef Q_OS_WIN
 if(sheet){sheet->setFlag(Qt::WindowStaysOnTopHint,true);SetWindowPos(reinterpret_cast<HWND>(sheet->winId()),HWND_TOPMOST,0,0,0,0,SWP_NOMOVE|SWP_NOSIZE|SWP_NOACTIVATE);}
#endif
 settingsFlight=qobject_cast<QQuickWindow *>(eval("settingsFlight").value<QObject *>());
 check(sheet&&settingsFlight&&settingsFlight->isVisible()&&!sheet->isVisible()&&eval("settingsFlight.phase==='Expanding' && settingsSheet.section==='subscriptions'").toBool(),"settings entry responds synchronously with one shared surface before the native handoff");
 if(settingsFlight){
  wait(35);
  check(eval("settingsFlight.reveal>0 && settingsFlight.reveal<1 && settingsLoader.parent===settingsFlight.bodySurface && settingsLoader.width===settingsSheet.width").toBool(),"real cached detail content is mounted at a fixed width inside the moving boundary");
  check(origin&&origin->opacity()==0&&eval("settingsFlight.sourceIcon==='subscriptions' && settingsFlight.sourceTitle==='订阅管理'").toBool(),"source card is replaced by its icon and title without a duplicate surface");
 }
 record("more-open",sheet);
 check(awaitSettings(nativeSettingsReady),"native window is opaque after the single live surface completes its handoff");
 if(sheet&&settingsFlight){check(origin&&origin->property("transfer").toDouble()>0.99,"source card keeps its shared return identity while native sheet is open");
  auto settingsPage=eval("settingsLoader.item").value<QObject *>();QTest::keyClick(sheet,Qt::Key_Escape);record("more-return",sheet);check(awaitSettings(settingsReturned)&&window->isVisible(),"Escape returns from the native sheet without closing the main window");
  check(awaitSettings([&]{return origin&&origin->property("transfer").toDouble()==0&&origin->hasActiveFocus();}),"return restores originating card geometry and keyboard focus");
  click("settings-subscriptions");check(awaitSettings(nativeSettingsReady)&&settingsPage&&eval("settingsLoader.item").value<QObject *>()==settingsPage,"secondary route cache retains the original subscription page");QTest::keyClick(sheet,Qt::Key_Escape);check(awaitSettings(settingsReturned),"cached subscription return finishes before the next entry accepts input");
  click("settings-fonts");check(awaitSettings(nativeSettingsReady),"font entry completes its native handoff before inspecting its controls");
  check(sheet->isVisible()&&eval("settingsLoader.item.section==='字体' && Theme.fontFamily===fontManager.defaultFamily").toBool(),"More font entry opens the platform default font settings");
  check(find(sheet->contentItem(),"fontFamilyList")&&find(sheet->contentItem(),"fontImport")&&find(sheet->contentItem(),"fontReset"),"font chooser, import and reset controls are available in the native settings window");
  if(recording&&nativeSettingsReady())sheet->grabWindow().save(directory+"/font-settings.png");
  QTest::keyClick(sheet,Qt::Key_Escape);check(awaitSettings(settingsReturned),"font settings return finishes before interruption checks");
  for(const double fraction:{0.25,0.5,0.75}){
   click("settings-subscriptions");
   check(QTest::qWaitFor([&]{return settingsFlight->property("reveal").toDouble()>=fraction;},1000),"settings opening reaches the requested interruption sample");
   const auto before=settingsFlight->property("surfaceRect").toRectF();
   const auto revealBefore=settingsFlight->property("reveal").toDouble();
   if(fraction==0.5)click("windowCloseButton",settingsFlight);else QTest::keyClick(settingsFlight,Qt::Key_Escape);
   const auto after=settingsFlight->property("surfaceRect").toRectF();
   const auto requested=settingsFlight->property("retargetRequestedRect").toRectF(),committed=settingsFlight->property("retargetCommittedRect").toRectF();
   settingsRetargetSamples.append(QJsonObject{{"fraction",fraction},{"inputBeforeX",before.x()},{"inputAfterX",after.x()},{"inputBeforeReveal",revealBefore},{"inputAfterReveal",settingsFlight->property("reveal").toDouble()},{"handlerRequestedX",requested.x()},{"handlerCommittedX",committed.x()},{"handlerRequestedWidth",requested.width()},{"handlerCommittedWidth",committed.width()}});
   check(requested==committed&&settingsFlight->property("retargetRequestedReveal")==settingsFlight->property("retargetCommittedReveal")&&settingsFlight->property("phase")=="Collapsing","real Escape and close-button reversal preserve the handler's exact displayed boundary and reveal");
   check(QTest::qWaitFor([&]{return settingsFlight->property("phase")=="Idle"&&!sheet->isVisible();},2000),"interrupted settings return releases its window and clock");
  }
  for(const auto *entry:{"settings","appearance","fonts","dns","modules","profiles","scripts","subscriptions","proxies"}){
   const auto name=QString("settings-")+QString::fromLatin1(entry);auto *source=item(name);
   const auto geometry=source?QRectF(source->position(),source->size()):QRectF();
   click(name);
   check(QTest::qWaitFor([&]{return sheet->isVisible()&&!settingsFlight->isVisible();},2500),"all nine setting entries finish a real native handoff");
   if(auto *page=eval("settingsLoader.item").value<QObject *>()){
    for(auto *object:page->findChildren<QObject *>()){
     if(auto *owner=object->property("ownerItem").value<QQuickItem *>()){
      auto *overlay=object->property("parent").value<QQuickItem *>();
      check(owner->window()==sheet&&overlay&&overlay->window()==sheet,"cached settings dialog overlay follows its declaration page: "+QString::fromLatin1(entry));
     }
     if(object->objectName().startsWith("settings")&&object->property("parentWindow").isValid())check(object->property("parentWindow").value<QWindow *>()==sheet,"native file picker follows migrated page: "+object->objectName());
    }
   }
   const auto routeId=QString::fromLatin1(entry);
   const auto formButton=routeId=="profiles"?QString("profileAddButton"):routeId=="scripts"?QString("scriptAddButton"):routeId=="proxies"?QString("nodeImportButton"):routeId=="fonts"?QString("fontLicense"):QString();
   if(!formButton.isEmpty()){
    if(auto *button=item(formButton,sheet))for(auto *ancestor=button->parentItem();ancestor;ancestor=ancestor->parentItem())if(ancestor->property("contentY").isValid()){
     const auto maximum=qMax(0.0,ancestor->property("contentHeight").toDouble()-ancestor->height());
     ancestor->setProperty("contentY",qBound(0.0,ancestor->property("contentY").toDouble()+button->mapToItem(ancestor,QPointF(button->width()/2,button->height()/2)).y()-ancestor->height()/2,maximum));
    }
    wait(20);
    click(formButton,sheet);wait(300);check(eval("dismissals.count===1").toBool(),"migrated settings form opens its native modal: "+routeId);
    QTest::keyClick(sheet,Qt::Key_Escape);wait(300);check(sheet->isVisible()&&eval("dismissals.count===0").toBool(),"native Escape dismisses only the migrated form: "+routeId);
   }
   check(source&&source->position()==geometry.topLeft()&&source->size()==geometry.size()&&source->property("motionScale").toDouble()==1,"setting flight leaves the grid slot and card scale unchanged");
   QTest::keyClick(sheet,Qt::Key_Escape);
   check(QTest::qWaitFor([&]{return settingsFlight->property("phase")=="Idle"&&!settingsFlight->isVisible();},2000),"all nine setting returns clean up the temporary surface");
  }
  click("settings-subscriptions");wait(40);const auto expansion=settingsFlight->property("surfaceRect").toRectF();eval("window.openSettings('subscriptions',window.settingsOrigin)");
  check(settingsFlight->property("surfaceRect").toRectF()==expansion,"repeated opening retargets the current boundary without returning to its origin");
  eval("window.closeSettings()");wait(25);const auto collapsing=settingsFlight->property("surfaceRect").toRectF();eval("window.openSettings('subscriptions',window.settingsOrigin)");
  check(settingsFlight->property("surfaceRect").toRectF()==collapsing,"reopening during collapse reverses the same surface");
  check(QTest::qWaitFor([&]{return sheet->isVisible()&&!settingsFlight->isVisible();},2000),"rapid opening and return settle at the last requested route");
  check(eval("settingsLoader.enabled && settingsLoader.parent===settingsSheet.bodySurface").toBool(),"only the native page accepts form input after handoff");
  auto *cachedPage=eval("settingsLoader.item").value<QObject *>();window->resize(1000,760);wait(80);const auto resizedOrigin=origin->mapToGlobal(QPointF(0,0));QTest::keyClick(sheet,Qt::Key_Escape);
  const auto resizedTarget=settingsFlight->property("toRect").toRectF();
  check(qAbs(resizedTarget.x()-resizedOrigin.x())<0.5&&qAbs(resizedTarget.y()-resizedOrigin.y())<0.5,"return uses the freshly laid out card coordinates instead of the opening snapshot");
  check(QTest::qWaitFor([&]{return settingsFlight->property("phase")=="Idle";},2000),"return recalculates the grid card after the main window resizes");
  policy->setSystemReducedMotionOverrideForTest(1);
  click("settings-subscriptions");
  check(awaitSettings(nativeSettingsReady)&&eval("motionPolicy.systemReducedMotion && SwirlMotion.reduced && !Theme.reduceMotion").toBool()&&eval("settingsLoader.item").value<QObject *>()==cachedPage,"system accessibility reduction opens the same native cached page without a moving surface");
  check(!settingsFlight->property("moving").toBool()&&eval("SwirlTransitionRegistry.activeCount===0").toBool(),"system accessibility reduction creates no settings transition clock");
  QTest::keyClick(sheet,Qt::Key_Escape);
  check(awaitSettings(settingsReturned),"system accessibility reduction Escape hides the modal and restores its source");
  policy->setSystemReducedMotionOverrideForTest(0);
  click("settings-subscriptions");wait(35);eval("Theme.reduceMotion=true");
  check(QTest::qWaitFor([&]{return sheet->isVisible()&&!settingsFlight->isVisible();},1000)&&eval("settingsLoader.item").value<QObject *>()==cachedPage,"changing reduced motion finishes geometry and retains the same cached page");
  QTest::keyClick(sheet,Qt::Key_Escape);wait(40);check(!sheet->isVisible()&&settingsFlight->property("phase")=="Idle","reduced-motion Escape hides the native modal window without a recursive close event");eval("Theme.reduceMotion=false");window->resize(1100,850);
  click("settings-subscriptions");wait(35);auto *fontSource=item("settings-fonts");const auto beforeRouteChange=settingsFlight->property("surfaceRect").toRectF();
  QMetaObject::invokeMethod(window,"openSettings",Q_ARG(QVariant,QString("fonts")),Q_ARG(QVariant,QVariant::fromValue(fontSource)));
  check(settingsFlight->property("surfaceRect").toRectF()==beforeRouteChange&&eval("settingsSheet.section==='fonts' && settingsFlight.sourceTitle==='字体'").toBool(),"a different entry supersedes the route while retaining the currently displayed boundary");
  check(QTest::qWaitFor([&]{return sheet->isVisible()&&!settingsFlight->isVisible();},2000),"superseded entry hands off only its latest page");QTest::keyClick(sheet,Qt::Key_Escape);
  check(QTest::qWaitFor([&]{return settingsFlight->property("phase")=="Idle";},2000),"superseded entry returns to its own original grid slot");
  click("settings-subscriptions");check(QTest::qWaitFor([&]{return sheet->isVisible()&&!settingsFlight->isVisible();},2000),"hidden-source fallback setup reaches a real detail window");origin->setVisible(false);QTest::keyClick(sheet,Qt::Key_Escape);
  check(settingsFlight->property("fadeFallback").toBool(),"an unavailable return card uses a stable fade rather than a flight to stale coordinates");
  check(QTest::qWaitFor([&]{return settingsFlight->property("phase")=="Idle";},2000),"fallback return releases its temporary window");origin->setVisible(true);
  click("settings-subscriptions");wait(70);auto *flightHeader=item("settingsTransferTitleBar",settingsFlight);
  if(flightHeader)QTest::mouseDClick(settingsFlight,Qt::LeftButton,Qt::NoModifier,flightHeader->mapToScene(QPointF(flightHeader->width()/2,flightHeader->height()/2)).toPoint());
  check(QTest::qWaitFor([&]{return sheet->visibility()==QWindow::Maximized&&!settingsFlight->isVisible();},1500),"double-clicking the moving title bar finishes the transfer and maximizes the real detail window");
  QTest::mouseDClick(sheet,Qt::LeftButton,Qt::NoModifier,QPoint(sheet->width()/2,qRound(sheet->property("titleBarHeight").toReal()/2)));
  check(QTest::qWaitFor([&]{return sheet->visibility()==QWindow::Windowed;},1500),"double-clicking the native title bar restores its window");QTest::keyClick(sheet,Qt::Key_Escape);
  check(QTest::qWaitFor([&]{return settingsFlight->property("phase")=="Idle";},2000),"maximized interruption leaves no transfer window on return");
  click("settings-subscriptions");wait(70);click("windowMaximizeButton",settingsFlight);
  check(QTest::qWaitFor([&]{return sheet->visibility()==QWindow::FullScreen&&!settingsFlight->isVisible();},1500),"the moving green control hands off to the real full-screen window");click("windowMaximizeButton",sheet);
  check(QTest::qWaitFor([&]{return sheet->visibility()==QWindow::Windowed;},1500),"the native green control restores its original behavior");QTest::keyClick(sheet,Qt::Key_Escape);
  check(QTest::qWaitFor([&]{return settingsFlight->property("phase")=="Idle";},2000),"full-screen interruption returns to the card cleanly");
  click("settings-subscriptions");wait(70);click("windowMinimizeButton",settingsFlight);
  check(QTest::qWaitFor([&]{return sheet->visibility()==QWindow::Minimized&&!settingsFlight->isVisible();},1500),"the moving yellow control minimizes the native window after finishing the transfer");sheet->showNormal();sheet->requestActivate();wait(80);QTest::keyClick(sheet,Qt::Key_Escape);
  check(QTest::qWaitFor([&]{return settingsFlight->property("phase")=="Idle";},2000),"restoring a minimized interruption leaves no partial transition");
  check(eval("SwirlTransitionRegistry.activeCount===0 && motionPolicy.activeGrabCount===0").toBool(),"setting flight leaves no active clock or foreground capture after settling");
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
 policy->setSystemReducedMotionOverrideForTest(-1);
 check(policy->systemReducedMotion()==actualSystemReducedMotion,"hero fixture restores the actual Windows accessibility policy");
 QFile report(directory+"/hero-report.json");if(!report.open(QIODevice::WriteOnly))return 3;
 report.write(QJsonDocument(QJsonObject{{"actualSystemReducedMotion",actualSystemReducedMotion},{"animatedSystemPolicyFixture",0},{"systemReducedPolicyFixture",1},{"restoredSystemPolicy",policy->systemReducedMotion()==actualSystemReducedMotion},{"settingsRetargetSamples",settingsRetargetSamples},{"nodeClickDispatchMs",nodeClickMs},{"checks",checks},{"failures",failures},{"dxgiPresentations",displaySamples},{"dxgiStatisticsErrors",statisticsErrors},{"animationWindows",animationWindows},{"refreshPhases",refreshPhases},{"resourceBefore",resourceBefore},{"resourceAfter",resources()},{"minimizedIdle",background},{"performanceStartQpcMs",performanceStart},{"performanceEndQpcMs",performanceEnd},{"reportedRefreshHz",window->screen()->refreshRate()},{"nativeDpr",window->devicePixelRatio()},{"sampleCount",intervals.size()},{"meanFrameDeliveryMs",mean},{"p95FrameDeliveryMs",intervals.isEmpty()?0:intervals[qMin(intervals.size()-1,qsizetype(intervals.size()*0.95))]},{"p99FrameDeliveryMs",intervals.isEmpty()?0:intervals[qMin(intervals.size()-1,qsizetype(intervals.size()*0.99))]},{"method","Passive Qt frameSwapped delivery during native interaction, excluding screenshot readback. These intervals are not hardware display presentation FPS; use external PresentMon data for presentation evidence."}}).toJson());
 return failures?2:0;
}
