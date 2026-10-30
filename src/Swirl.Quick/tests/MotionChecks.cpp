#include "MotionChecks.h"
#include "RouteBench.h"
#include "app/MotionPolicy.h"
#include <QQuickWindow>
#include <QAccessible>
#include <QGuiApplication>
#include <QQuickItem>
#include <QQuickItemGrabResult>
#include <QQmlExpression>
#include <QQmlContext>
#include <QQmlComponent>
#include <QQmlIncubator>
#include <QQmlProperty>
#include "engine/SystemProxySession.h"
#include "engine/EngineController.h"
#include <QDateTime>
#include <memory>
#include <QTest>
#include <QSignalSpy>
#include <QDir>
#include <QImage>
#include <QJsonArray>
#include <QJsonObject>
#include <QJsonDocument>
#include <QFile>
#include <QFileInfo>
#include <QLineF>
#include <QDebug>
#include <QElapsedTimer>
#include <QEventLoop>
#include <QTimer>
#include <QSGRendererInterface>
#include <QScreen>
#include <QKeyEvent>
#include <QWheelEvent>
#include <algorithm>
#include <functional>
#include <QMutex>
#include <QMutexLocker>
#include <QPointer>
#include <QThread>
#include <QPainter>
#include <QQmlEngine>
#ifdef Q_OS_WIN
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <psapi.h>
#endif

namespace {
QQuickItem *activityVisual(QQuickItem *root,const QString &name) {
    if(!root)return nullptr;
    if(root->objectName()==name)return root;
    for(auto *child:root->childItems())if(auto *found=activityVisual(child,name))return found;
    return nullptr;
}
void activityWait(int milliseconds) {
    QEventLoop loop;QTimer timer;timer.setTimerType(Qt::PreciseTimer);timer.setSingleShot(true);
    QObject::connect(&timer,&QTimer::timeout,&loop,&QEventLoop::quit);timer.start(milliseconds);loop.exec();
}
const QStringList activityDetailKeys={"sources","diagnostics","traffic","connections","connection"};
const QStringList activityDetailButtons={"activitySourcesDetails","networkDiagnosticDetails","activityTrafficDetails","activityConnectionsDetails","activityConnectionDetails"};
const QStringList activityDetailCards={"activitySourcesCard","activityDiagnosticCard","activityTrafficCard","activityConnectionsCard","activityStatusCard"};

void checkActivityWeaveLayers(QQuickWindow *window,QQuickItem *weave,const QString &output,
    const std::function<void(const QString &,bool)> &check,QJsonArray &samples) {
    const auto eval=[&](const QString &code){
        QQmlExpression expression(qmlContext(weave),weave,code);
        const auto result=expression.evaluate();
        check("weave-layer-expression: "+code.left(70),!expression.hasError());
        if(expression.hasError())qWarning()<<expression.error();
        return result;
    };
    const auto find=[&](const QString &name){return activityVisual(window->contentItem(),name);};
    auto *back=find("cloudKnotBackFlight"),*front=find("cloudKnotFrontFlight"),*rest=find("cloudKnotRest");
    auto *behind=weave->property("behindCards").value<QQuickItem *>();
    auto *frontLayer=weave->property("frontLayer").value<QQuickItem *>();
    auto *target=weave->property("knotTarget").value<QQuickItem *>();
    auto *sourceFilter=find("activitySourceFilter");
    check("weave-shares-page-back-front-and-local-rest-layers",back&&front&&rest&&behind&&frontLayer&&target&&sourceFilter
        &&back->parentItem()==behind&&front->parentItem()==frontLayer&&rest->parentItem()==target);
    if(!back||!front||!rest||!behind||!frontLayer||!target||!sourceFilter)return;
    const auto behindItem=[](QQuickItem *lower,QQuickItem *upper){
        QList<QQuickItem *> a,b;
        for(auto *item=lower;item;item=item->parentItem())a.prepend(item);
        for(auto *item=upper;item;item=item->parentItem())b.prepend(item);
        int i=0;while(i<a.size()&&i<b.size()&&a[i]==b[i])++i;
        if(i==0||i==a.size()||i==b.size())return false;
        if(a[i]->z()!=b[i]->z())return a[i]->z()<b[i]->z();
        const auto siblings=a[i-1]->childItems();
        return siblings.indexOf(a[i])<siblings.indexOf(b[i]);
    };
    check("weave-flight-stacks-behind-real-source-controls",behindItem(back,sourceFilter));
    const QList<QPointF> corners={QPointF(),QPointF(target->width(),0),QPointF(0,target->height()),QPointF(target->width(),target->height())};
    bool sameClip=front->clip()&&front->size()==target->size();
    for(const auto &point:corners)sameClip=sameClip&&QLineF(front->mapToScene(point),target->mapToScene(point)).length()<0.01;
    check("weave-foreground-clip-follows-live-reserved-knot-rectangle",sameClip);
    const QStringList keys={"warm","return","crown","forward","heart"};
    const QList<QPointF> probes={QPointF(),QPointF(1024,0),QPointF(0,1024)};
    const auto matchingCopies=[&]{
        bool same=true;
        for(const auto &key:keys){
            auto *piece=find("cloudFeather-"+key),*copy=find("cloudFeatherFront-"+key);
            if(!piece||!copy){same=false;continue;}
            same=same&&piece->property("sourcePath")==copy->property("sourcePath")
                &&piece->property("targetPath")==copy->property("targetPath")
                &&piece->property("morphProgress")==copy->property("morphProgress");
            for(const auto &point:probes)same=same&&QLineF(piece->mapToScene(point),copy->mapToScene(point)).length()<0.01;
        }
        return same;
    };
    // Reach the reported obstruction through the actual animation clock, then
    // freeze that observed frame for deterministic native-render comparisons.
    QTest::mouseMove(window,QPoint(1,1));activityWait(180);
    eval("previewAt(0.44,0);retarget()");
    check("weave-layer-regression-runs-real-flight-clock",QTest::qWaitFor([&]{return weave->property("progress").toDouble()>=0.472;},1500));
    const double sampledProgress=weave->property("progress").toDouble();
    check("weave-obstruction-frame-is-intermediate-flight",sampledProgress>=0.472&&sampledProgress<0.55&&weave->property("moving").toBool());
    eval(QString("previewAt(%1,0)").arg(sampledProgress,0,'g',17));
    check("weave-front-and-back-copies-share-global-pose",matchingCopies());
    window->update();activityWait(80);
    const QImage withFlight=window->grabWindow();
    QQmlComponent opacityComponent(qmlEngine(window));
    opacityComponent.setData(R"(
        import QtQuick
        Binding {
            required property var targetWeave
            target: targetWeave
            property: "opacity"
            value: 0
            restoreMode: Binding.RestoreBindingOrValue
        }
    )",QUrl());
    std::unique_ptr<QObject> hideFlight(opacityComponent.createWithInitialProperties(
        {{"targetWeave",QVariant::fromValue(weave)}},qmlContext(window)));
    check("weave-pixel-reference-hides-only-decorative-opacity",hideFlight!=nullptr);
    window->update();activityWait(80);
    const QImage withoutFlight=window->grabWindow();
    check("weave-control-pixel-comparison-has-real-window-images",!withFlight.isNull()&&!withoutFlight.isNull()
        &&withFlight.size()==withoutFlight.size());
    if(!withFlight.isNull()&&!withoutFlight.isNull()&&withFlight.size()==withoutFlight.size()){
        QJsonArray controls;
        for(const auto &name:QStringList{"activitySourceFilter","activityTrafficFilter","activitySourcesDetails","activityInternetValue","activityCurrentNode","proxyCapsule"}){
            auto *control=find(name);
            check(name+"-present-for-weave-pixel-regression",control!=nullptr);
            if(!control)continue;
            QList<QQuickItem *> regions={control};
            // The toolbar capsule has intentionally transparent rounded corners.
            // Its real label and status accessory must remain fully unobstructed;
            // legal artwork visible outside the capsule is not a text overlap.
            if(name=="proxyCapsule")regions={activityVisual(control,"statusCapsuleLabel"),activityVisual(control,"statusCapsuleAccessory")};
            for(int regionIndex=0;regionIndex<regions.size();++regionIndex){
                auto *region=regions[regionIndex];
                const QString regionName=region?region->objectName():name+"-missing-region-"+QString::number(regionIndex);
                const bool readable=control->isVisible()&&region&&region->isVisible()&&region->width()>2&&region->height()>2;
                check(name+"-visible-content-region-"+regionName,readable);
                if(!readable)continue;
                const auto local=QRectF(QPointF(),region->size());
                const auto logical=region->mapRectToScene(name=="proxyCapsule"?local:local.adjusted(1,1,-1,-1));
                const double sx=double(withFlight.width())/window->width(),sy=double(withFlight.height())/window->height();
                const QRect pixels=QRectF(logical.x()*sx,logical.y()*sy,logical.width()*sx,logical.height()*sy).toAlignedRect().intersected(withFlight.rect());
                const auto a=withFlight.copy(pixels).convertToFormat(QImage::Format_ARGB32);
                const auto b=withoutFlight.copy(pixels).convertToFormat(QImage::Format_ARGB32);
                int changed=0;
                for(int y=0;y<a.height();++y)for(int x=0;x<a.width();++x)if(a.pixel(x,y)!=b.pixel(x,y))++changed;
                check(name+"-pixels-unchanged-by-passing-feathers-"+regionName,!pixels.isEmpty()&&changed==0);
                controls.append(QJsonObject{{"control",name},{"region",regionName},{"pixelWidth",pixels.width()},{"pixelHeight",pixels.height()},{"changedPixels",changed}});
            }
        }
        samples.append(QJsonObject{{"kind","weave-control-occlusion"},{"observedProgress",sampledProgress},
            {"devicePixelRatio",window->devicePixelRatio()},{"controls",controls}});
        if(!output.isEmpty()){
            const auto directory=QFileInfo(output).absolutePath();
            check("weave-render-evidence-directory-created",QDir().mkpath(directory));
            check("weave-obstruction-frame-saved",withFlight.save(directory+"/activity-feather-flight.png"));
            check("weave-control-reference-frame-saved",withoutFlight.save(directory+"/activity-feather-hidden-reference.png"));
        }
    }
    hideFlight.reset();
    // Exercise different layer origins without breaking the production anchor
    // bindings. The copies must remain coincident in window space.
    QQmlComponent offsetComponent(qmlEngine(window));
    offsetComponent.setData(R"(
        import QtQuick
        QtObject {
            required property var layer
            required property real offsetX
            required property real offsetY
            property Binding xOffset: Binding { target: layer; property: "x"; value: offsetX; restoreMode: Binding.RestoreBindingOrValue }
            property Binding yOffset: Binding { target: layer; property: "y"; value: offsetY; restoreMode: Binding.RestoreBindingOrValue }
        }
    )",QUrl());
    const QPointF originalBackPosition=behind->position();
    const QPointF offsetBackPosition=originalBackPosition+QPointF(17.25,11.5);
    std::unique_ptr<QObject> offset(offsetComponent.createWithInitialProperties(
        {{"layer",QVariant::fromValue(behind)},{"offsetX",offsetBackPosition.x()},{"offsetY",offsetBackPosition.y()}},qmlContext(window)));
    check("weave-offset-layer-fixture-created",offset!=nullptr);
    if(offset){
        eval("updateGeometry(true)");
        check("weave-back-layer-really-moves-to-distinct-origin",QLineF(behind->position(),offsetBackPosition).length()<0.001);
        check("weave-copies-align-with-distinct-back-layer-origin",matchingCopies());
        offset.reset();eval("updateGeometry(true)");
        check("weave-back-layer-original-position-restored",QLineF(behind->position(),originalBackPosition).length()<0.001);
    }
    eval("previewAt(0.999999,0)");
    QList<QList<QPointF>> before;
    for(const auto &key:keys){
        auto *piece=find("cloudFeather-"+key);QList<QPointF> points;
        if(piece)for(const auto &point:probes)points.append(piece->mapToScene(point));
        before.append(points);
    }
    eval("previewAt(1,0)");
    bool continuous=!front->isVisible();
    for(int i=0;i<keys.size();++i){
        auto *piece=find("cloudFeather-"+keys[i]);
        continuous=continuous&&piece&&piece->parentItem()==rest&&before[i].size()==probes.size();
        if(piece&&before[i].size()==probes.size())for(int p=0;p<probes.size();++p)
            continuous=continuous&&QLineF(before[i][p],piece->mapToScene(probes[p])).length()<0.01;
    }
    check("weave-final-frame-reparents-without-geometry-or-scale-jump",continuous);
    std::function<int(QQuickItem *)> countFeathers=[&](QQuickItem *item){
        int count=item->inherits("WholeFeatherItem")?1:0;
        for(auto *child:item->childItems())count+=countFeathers(child);
        return count;
    };
    const int featherCount=countFeathers(window->contentItem());
    bool bounded=featherCount>=10;
    for(int cycle=0;cycle<4;++cycle)for(const auto &state:QStringList{"0.12,0","0.472,0","0.98,0","1,0","1,0.5","1,1"}){
        eval("previewAt("+state+")");
        bounded=bounded&&countFeathers(window->contentItem())==featherCount;
    }
    check("weave-repeated-flight-and-withdrawal-keeps-native-feather-count-bounded",bounded);
}

int runActivityDetailChecks(QQuickWindow *window,const QString &output) {
    QJsonArray checks,samples,dataSamples;int failures=0;
    const auto check=[&](const QString &name,bool passed){checks.append(QJsonObject{{"name",name},{"passed",passed}});if(!passed)++failures;qInfo()<<"ACTIVITY_DETAIL_CHECK"<<name<<passed;};
    const auto eval=[&](const QString &code){QQmlExpression expression(qmlContext(window),window,code);auto result=expression.evaluate();if(expression.hasError()){qWarning()<<expression.error();check("expression: "+expression.error().toString(),false);}return result;};
    auto *policy=qobject_cast<MotionPolicy *>(qmlContext(window)->contextProperty("motionPolicy").value<QObject *>());
    check("motion-policy-present",policy!=nullptr);if(!policy)return 1;
    policy->setSystemReducedMotionOverrideForTest(0);
    struct RestorePolicy{MotionPolicy *policy;~RestorePolicy(){policy->setSystemReducedMotionOverrideForTest(-1);}} restore{policy};
    const auto hostProxyBefore=SystemProxySession::snapshot();
    eval("Theme.reduceMotion=false;Theme.followSystemMotion=false;AppState.navigate('activity')");
    const QSize initialSize=window->size();window->resize(1100,760);window->requestActivate();activityWait(650);
    auto *page=activityVisual(window->contentItem(),"activityScroll");page=page?page->parentItem():nullptr;
    auto *transition=activityVisual(window->contentItem(),"activityDetailTransition");
    auto *surface=activityVisual(window->contentItem(),"activityDetailSurface");
    check("all-five-details-share-one-transition-container",page&&transition&&surface);
    if(!page||!transition||!surface)return 1;
    const auto bounds=[&](QQuickItem *item){return item->mapRectToItem(window->contentItem(),QRectF(QPointF(),item->size()));};
    QRectF firstVisibleBounds;double firstVisibleProgress=0;bool originObserved=false;
    const auto originConnection=QObject::connect(transition,&QQuickItem::visibleChanged,window,[&]{if(transition->isVisible()){firstVisibleBounds=bounds(surface);firstVisibleProgress=transition->property("progress").toDouble();originObserved=true;}});
    const auto settled=[&]{return QTest::qWaitFor([&]{return !transition->property("moving").toBool();},2000);};
    const auto close=[&]{QMetaObject::invokeMethod(transition,"closeDetail");settled();};
    const auto click=[&](const QString &name){auto *button=activityVisual(window->contentItem(),name);if(!button||!button->isVisible()||!button->isEnabled())return false;QTest::mouseClick(window,Qt::LeftButton,Qt::NoModifier,button->mapToScene(QPointF(button->width()/2,button->height()/2)).toPoint());return true;};
    const auto homeCountsMatch=[&](int connectionCount,int processCount,int deviceCount){
        auto *section=activityVisual(window->contentItem(),"activityConnectionsCard");
        auto *connectionValue=activityVisual(window->contentItem(),"activityConnectionCount");
        int processes=-1,devices=-1;
        if(section)for(auto *row:section->findChildren<QObject *>()){
            const auto caption=row->property("caption").toString();
            if(caption==QStringLiteral("已识别进程"))processes=row->property("value").toString().toInt();
            else if(caption==QStringLiteral("非本机来源"))devices=row->property("value").toString().toInt();
        }
        return connectionValue&&connectionValue->property("text").toString().toInt()==connectionCount&&processes==processCount&&devices==deviceCount;
    };
    const auto snapshot=[&](const QString &key,const QString &phase){const auto rect=bounds(surface);samples.append(QJsonObject{{"key",key},{"phase",phase},{"progress",transition->property("progress").toDouble()},{"x",rect.x()},{"y",rect.y()},{"width",rect.width()},{"height",rect.height()},{"radius",surface->property("radius").toDouble()}});return rect;};
    auto *sourceOverview=activityVisual(window->contentItem(),activityDetailCards[0]);
    auto *diagnosticOverview=activityVisual(window->contentItem(),activityDetailCards[1]);
    auto *trafficOverview=activityVisual(window->contentItem(),activityDetailCards[2]);
    auto *connectionOverview=activityVisual(window->contentItem(),activityDetailCards[3]);
    auto *statusOverview=activityVisual(window->contentItem(),activityDetailCards[4]);
    check("overview-five-card-grid-is-present",sourceOverview&&diagnosticOverview&&trafficOverview&&connectionOverview&&statusOverview);
    if(sourceOverview&&diagnosticOverview&&trafficOverview&&connectionOverview&&statusOverview){
        const auto source=bounds(sourceOverview),diagnostic=bounds(diagnosticOverview),traffic=bounds(trafficOverview),connections=bounds(connectionOverview),status=bounds(statusOverview);
        check("overview-grid-keeps-top-row-bottom-stack-and-outer-edges-aligned",
            qAbs(status.top()-traffic.top())<1&&qAbs(status.height()-traffic.height())<1
            &&qAbs(source.top()-diagnostic.top())<1&&qAbs(source.bottom()-connections.bottom())<1
            &&qAbs(diagnostic.left()-connections.left())<1&&qAbs(diagnostic.width()-connections.width())<1
            &&qAbs(status.left()-source.left())<1&&qAbs(traffic.right()-diagnostic.right())<1);
        check("overview-grid-keeps-five-seven-and-seven-five-width-ratios",
            qAbs(status.width()/(status.width()+traffic.width())-5.0/12)<0.03
            &&qAbs(source.width()/(source.width()+diagnostic.width())-7.0/12)<0.03);
    }
    for(int i=0;i<activityDetailButtons.size();++i){
        auto *heading=activityVisual(window->contentItem(),activityDetailButtons[i]);
        auto *card=activityVisual(window->contentItem(),activityDetailCards[i]);
        const auto titleBounds=heading&&card?heading->mapRectToItem(card,QRectF(QPointF(),heading->size())):QRectF();
        check(activityDetailButtons[i]+"-title-stays-readable-inside-card",heading&&card&&heading->width()>=60
            &&titleBounds.left()>=0&&titleBounds.right()<=card->width()+1&&titleBounds.top()>=0&&titleBounds.bottom()<=card->height()+1
            &&QQmlProperty::read(heading,"font.pixelSize").toDouble()>=12);
    }
    auto *sourceCategory=activityVisual(window->contentItem(),"activitySourceFilter");
    auto *sourceHeading=activityVisual(window->contentItem(),activityDetailButtons[0]);
    check("source-category-control-sits-below-title-at-shared-left-inset",sourceCategory&&sourceOverview&&sourceHeading
        &&qAbs(sourceCategory->mapToItem(sourceOverview,0,0).x()-page->property("cardInset").toDouble())<1
        &&bounds(sourceCategory).top()>=bounds(sourceHeading).bottom());
    const int historyIndex=eval("AppState.historyIndex").toInt();
    auto *homeScroll=activityVisual(window->contentItem(),"activityScroll");
    const double scrollBefore=homeScroll->property("contentY").toDouble();
    for(int i=0;i<activityDetailKeys.size();++i){
        const auto key=activityDetailKeys[i];auto *card=activityVisual(window->contentItem(),activityDetailCards[i]);
        check(key+"-opaque-origin-card-present",card&&card->isVisible()&&card->property("color").value<QColor>().alpha()==255);if(!card)continue;
        const auto source=bounds(card);const auto normalBorderWidth=QQmlProperty::read(card,"border.width").toDouble();
        originObserved=false;check(key+"-title-click-opens",click(activityDetailButtons[i]));
        const auto start=snapshot(key,"open-start");
        const auto storedOrigin=transition->mapRectToItem(window->contentItem(),transition->property("origin").toRectF());
        check(key+"-begins-at-own-card",originObserved&&firstVisibleProgress==0&&qAbs(firstVisibleBounds.x()-source.x())<6&&qAbs(firstVisibleBounds.y()-source.y())<6&&qAbs(firstVisibleBounds.width()-source.width())<6&&qAbs(firstVisibleBounds.height()-source.height())<6
            &&qAbs(storedOrigin.x()-source.x())<6&&qAbs(storedOrigin.y()-source.y())<6&&qAbs(storedOrigin.width()-source.width())<6&&qAbs(storedOrigin.height()-source.height())<6);
        const auto destination=transition->mapRectToItem(window->contentItem(),transition->property("destination").toRectF());const auto startProgress=transition->property("progress").toDouble();
        check(key+"-surface-keeps-origin-through-click-dispatch",qAbs(start.x()-storedOrigin.x()-(destination.x()-storedOrigin.x())*startProgress)<1&&qAbs(start.y()-storedOrigin.y()-(destination.y()-storedOrigin.y())*startProgress)<1
            &&qAbs(start.width()-storedOrigin.width()-(destination.width()-storedOrigin.width())*startProgress)<1&&qAbs(start.height()-storedOrigin.height()-(destination.height()-storedOrigin.height())*startProgress)<1);
        activityWait(90);const auto middle=snapshot(key,"open-middle");const auto progress=transition->property("progress").toDouble();
        check(key+"-visible-geometric-expansion",transition->property("moving").toBool()&&progress>0&&progress<1&&middle.width()>source.width()+2&&middle.height()>source.height()+2);
        const double originRadius=card->property("radius").toDouble(),targetRadius=eval("Theme.cardRadius").toDouble();
        check(key+"-corner-curvature-remains-continuous",surface->property("radius").toDouble()>=qMin(originRadius,targetRadius)-0.1&&surface->property("radius").toDouble()<=qMax(originRadius,targetRadius)+0.1);
        check(key+"-opens-correct-detail",settled()&&transition->property("opened").toBool()&&transition->property("detailKey").toString()==key);
        const auto full=snapshot(key,"open-end");
        check(key+"-expanded-corner-curvature-reaches-target",qAbs(surface->property("radius").toDouble()-targetRadius)<0.1);
        check(key+"-fills-main-content",full.width()>source.width()&&full.height()>source.height()&&full.left()>=0&&full.right()<=window->width()+1&&full.bottom()<=window->height()+1);
        QTest::keyClick(window,Qt::Key_Escape);activityWait(80);const auto reverse=snapshot(key,"close-middle");
        check(key+"-escape-geometrically-contracts",transition->property("moving").toBool()&&transition->property("progress").toDouble()>0&&transition->property("progress").toDouble()<1&&reverse.width()<full.width()-2&&reverse.height()<full.height()-2);
        check(key+"-return-restores-corner-curvature-continuously",surface->property("radius").toDouble()>=qMin(originRadius,targetRadius)-0.1&&surface->property("radius").toDouble()<=qMax(originRadius,targetRadius)+0.1);
        check(key+"-returns-cleanly",settled()&&!transition->property("opened").toBool()&&transition->property("progress").toDouble()==0&&!transition->isVisible());
        QTest::mouseMove(window,QPoint(1,1));activityWait(150);
        check(key+"-return-keeps-keyboard-focus",card->hasActiveFocus());
        // The accepted 0.2.30 surface intentionally removed ordinary outlines.
        // Preserve the no-persistent-click-state check against that contract;
        // do not restore an obsolete border merely to satisfy an older test.
        check(key+"-return-has-no-persistent-click-outline",normalBorderWidth==eval("Theme.increaseContrast ? Theme.dp(2) : 0").toDouble()
            &&QQmlProperty::read(card,"border.width").toDouble()==normalBorderWidth);
        check(key+"-preserves-main-route-and-history",eval("AppState.currentPage==='activity'").toBool()&&eval("AppState.historyIndex").toInt()==historyIndex);
    }
    if(auto *sourceCard=activityVisual(window->contentItem(),"activitySourcesCard")){
        QTest::mouseMove(window,QPoint(1,1));activityWait(150);const auto rest=bounds(sourceCard);
        const auto blank=sourceCard->mapToScene(QPointF(sourceCard->width()*0.65,sourceCard->height()*0.55)).toPoint();
        QTest::mouseMove(window,blank);activityWait(150);const auto hover=bounds(sourceCard);
        check("card-hover-has-a-gentle-continuous-lift",sourceCard->property("hovered").toBool()&&hover.y()<rest.y()-0.3&&rest.y()-hover.y()<4);
        QTest::mousePress(window,Qt::LeftButton,Qt::NoModifier,blank);activityWait(55);const auto press=bounds(sourceCard);
        check("card-press-keeps-accepted-hover-without-extra-offset-or-scale",!sourceCard->property("pressed").toBool()
            &&qAbs(press.y()-hover.y())<0.1&&qAbs(press.width()-hover.width())<0.1);
        QTest::mouseRelease(window,Qt::LeftButton,Qt::NoModifier,blank);activityWait(50);
        check("card-blank-area-opens-same-source-detail",transition->property("opened").toBool()&&transition->property("detailKey").toString()=="sources");close();
    }
    if(auto *sourceCard=activityVisual(window->contentItem(),"activitySourcesCard")){
        // Tab must remain visible even if the pointer was already resting on
        // this card; mouse position cannot identify the input that gave focus.
        const auto blank=sourceCard->mapToScene(QPointF(sourceCard->width()*0.65,sourceCard->height()*0.55)).toPoint();
        QTest::mouseMove(window,blank);
        auto *previous=sourceCard->nextItemInFocusChain(false);
        check("source-card-has-preceding-keyboard-focus-target",previous&&previous!=sourceCard);
        if(previous&&previous!=sourceCard){
            previous->forceActiveFocus(Qt::TabFocusReason);
            QTest::keyClick(window,Qt::Key_Tab);activityWait(180);
            check("tab-focus-is-recognized-with-pointer-over-card",sourceCard->hasActiveFocus()&&sourceCard->property("keyboardFocus").toBool());
            QTest::mouseMove(window,QPoint(1,1));activityWait(180);
            check("card-keyboard-focus-retains-visible-lift-without-click-outline",sourceCard->property("focused").toBool()
                &&sourceCard->property("lift").toDouble()<-.3&&sourceCard->property("lift").toDouble()>-4
                &&QQmlProperty::read(sourceCard,"border.width").toDouble()==eval("Theme.increaseContrast ? Theme.dp(2) : 0").toDouble());
            QSignalSpy activations(sourceCard,SIGNAL(activated()));
            QTest::keyClick(window,Qt::Key_Return);
            check("card-enter-activates-exactly-once",activations.count()==1&&settled()
                &&transition->property("detailKey").toString()=="sources"&&transition->property("opened").toBool());
            close();
            check("card-enter-return-restores-keyboard-focus-state",sourceCard->hasActiveFocus()&&sourceCard->property("keyboardFocus").toBool());
            QTest::keyClick(window,Qt::Key_Space);
            check("card-space-activates-exactly-once",activations.count()==2&&settled()
                &&transition->property("detailKey").toString()=="sources"&&transition->property("opened").toBool());
            close();
        }
    }
    check("source-segment-click-does-not-open-detail",click("activitySourceFilter")&&!transition->property("opened").toBool()&&transition->property("progress").toDouble()==0);
    check("traffic-segment-click-does-not-open-detail",click("activityTrafficFilter")&&!transition->property("opened").toBool()&&transition->property("progress").toDouble()==0);
    check("traffic-scope-control-opens-own-popup",eval("dismissals.hasPopup(window)").toBool());
    QTest::keyClick(window,Qt::Key_Escape);activityWait(180);
    check("traffic-scope-escape-closes-popup-without-detail-navigation",!eval("dismissals.hasPopup(window)").toBool()&&!transition->property("activeDetail").toBool());
    check("period-segment-click-does-not-open-detail",click("activityPeriodFilter")&&!transition->property("opened").toBool()&&transition->property("progress").toDouble()==0);
    click(activityDetailButtons[1]);settled();check("shared-return-button-receives-input",click("activityDetailBack"));activityWait(70);
    check("return-button-uses-same-geometric-contraction",transition->property("moving").toBool()&&transition->property("progress").toDouble()>0&&transition->property("progress").toDouble()<1);close();
    click(activityDetailButtons[0]);activityWait(95);const auto beforeReverse=transition->property("progress").toDouble();
    QTest::keyClick(window,Qt::Key_Escape);activityWait(30);
    check("escape-reverses-incomplete-expansion-continuously",beforeReverse>0&&beforeReverse<1&&transition->property("moving").toBool()&&transition->property("progress").toDouble()<beforeReverse);
    for(int repeat=0;repeat<8;++repeat)QTest::keyClick(window,Qt::Key_Escape);
    check("repeated-escape-settles-without-history-pop",settled()&&!transition->isVisible()&&eval("AppState.currentPage==='activity'").toBool()&&eval("AppState.historyIndex").toInt()==historyIndex);
    for(int i=0;i<8;++i){click(activityDetailButtons[i%activityDetailKeys.size()]);activityWait(14);QTest::keyClick(window,Qt::Key_Escape);activityWait(9);}
    close();check("rapid-repeated-input-releases-overlay",!transition->isVisible()&&!transition->property("moving").toBool());
    for(const auto size:{QSize(914,672),QSize(1100,760)}){
        click(activityDetailButtons[1]);activityWait(70);window->resize(size);activityWait(60);
        check("resize-during-expansion-"+QString::number(size.width()),settled()&&transition->property("progress").toDouble()==1&&bounds(surface).right()<=window->width()+1&&bounds(surface).bottom()<=window->height()+1);
        QTest::keyClick(window,Qt::Key_Escape);activityWait(70);window->resize(1100,760);close();
        check("resize-during-contraction-"+QString::number(size.width()),!transition->isVisible()&&transition->property("progress").toDouble()==0);
    }
    click(activityDetailButtons[2]);activityWait(85);
    eval("pageLoader.item.refreshSnapshot()");
    check("real-model-refresh-does-not-interrupt-transition",transition->property("moving").toBool()&&transition->property("detailKey").toString()=="traffic"&&settled());
    close();
    check("home-scroll-retained",qAbs(homeScroll->property("contentY").toDouble()-scrollBefore)<1);
    eval("Theme.reduceMotion=true");click(activityDetailButtons[3]);activityWait(30);
    check("reduced-motion-opens-complete-detail",!transition->property("moving").toBool()&&transition->property("progress").toDouble()==1);
    QTest::keyClick(window,Qt::Key_Escape);activityWait(30);
    check("reduced-motion-return-releases-overlay",!transition->isVisible()&&transition->property("progress").toDouble()==0);
    eval("Theme.reduceMotion=false");
    // Exercise the real page-owned weave and its real detail-opacity binding.
    // A temporary Binding restores the original active binding on destruction;
    // this never changes the system proxy or the controller's network state.
    auto *weave=activityVisual(window->contentItem(),"activityCloudKnotWeave");
    check("activity-weave-present-for-detail-pause-regression",weave!=nullptr);
    if(weave){
        QQmlComponent bindingComponent(qmlEngine(window));
        bindingComponent.setData(R"(
            import QtQuick
            Binding {
                required property var targetWeave
                property bool requestedActive: true
                target: targetWeave
                property: "active"
                value: requestedActive
                restoreMode: Binding.RestoreBindingOrValue
            }
        )",QUrl());
        std::unique_ptr<QObject> activeOverride(bindingComponent.createWithInitialProperties(
            {{"targetWeave",QVariant::fromValue(weave)}},qmlContext(window)));
        check("weave-test-override-created-with-binding-restoration",activeOverride!=nullptr);
        if(activeOverride){
            checkActivityWeaveLayers(window,weave,output,check,dataSamples);
            QQmlExpression pose(qmlContext(weave),weave,"previewAt(0.4,0);retarget()");
            pose.evaluate();
            check("weave-continues-real-flight-from-controlled-intermediate-phase",!pose.hasError()
                &&weave->property("moving").toBool()&&weave->property("progress").toDouble()<1);
            check("weave-pause-case-opens-detail",click(activityDetailButtons[1]));
            const double pausedProgress=weave->property("progress").toDouble();
            const double pausedRelease=weave->property("release").toDouble();
            check("weave-pauses-at-intermediate-phase-on-detail-entry",pausedProgress>0&&pausedProgress<1
                &&!weave->property("presentationActive").toBool()&&!weave->property("moving").toBool());
            check("weave-pause-case-reaches-fully-open-detail",settled()&&transition->property("progress").toDouble()==1);
            activityWait(120);
            check("fully-transparent-overview-preserves-paused-weave-state",weave->opacity()==0
                &&qAbs(weave->property("progress").toDouble()-pausedProgress)<0.001
                &&qAbs(weave->property("release").toDouble()-pausedRelease)<0.001);
            close();activityWait(100);
            const double resumedProgress=weave->property("progress").toDouble();
            check("detail-return-resumes-weaving-from-paused-phase",weave->property("presentationActive").toBool()
                &&weave->property("moving").toBool()&&resumedProgress>pausedProgress&&resumedProgress<1);
            check("weave-hidden-state-change-case-opens-detail",click(activityDetailButtons[1])&&settled());
            activeOverride->setProperty("requestedActive",false);
            check("proxy-state-change-while-detail-open-settles-latest-inactive-state",weave->property("progress").toDouble()==0
                &&weave->property("release").toDouble()==1&&!weave->property("moving").toBool());
            activeOverride->setProperty("requestedActive",true);
            check("proxy-state-change-while-detail-open-settles-latest-active-state",weave->property("progress").toDouble()==1
                &&weave->property("release").toDouble()==0&&!weave->property("moving").toBool());
            close();
            check("detail-return-keeps-current-completed-knot",weave->property("progress").toDouble()==1
                &&weave->property("release").toDouble()==0);

            // Exercise real route hiding, not only the detail's opacity fade.
            // PageHost retains these two routes below its existing cache limit;
            // leaving a page resets its detail and settles the hidden weave.
            const auto routeReady=[&](const QString &route){
                return QTest::qWaitFor([&]{return eval(QStringLiteral(
                    "AppState.currentPage==='%1' && pageLoader.activeLoader && "
                    "pageLoader.activeLoader.routeId==='%1' && pageLoader.activeLoader.status===Loader.Ready && "
                    "pageLoader.item!==null && !pageLoader.pendingGrab && !pageLoader.moving && "
                    "motionPolicy.activeGrabCount===0 && SwirlTransitionRegistry.activeCount===0").arg(route)).toBool();},2000);
            };
            const auto recordRouteState=[&](const char *phase){
                auto state=QJsonDocument::fromJson(eval(QStringLiteral(
                    "JSON.stringify({route:AppState.currentPage,activeRoute:pageLoader.activeLoader?"
                    "pageLoader.activeLoader.routeId:'',loaderStatus:pageLoader.activeLoader?"
                    "pageLoader.activeLoader.status:-1,pendingGrab:pageLoader.pendingGrab,hostMoving:pageLoader.moving,"
                    "grabCount:motionPolicy.activeGrabCount,transitionCount:SwirlTransitionRegistry.activeCount,"
                    "historyIndex:AppState.historyIndex,cachedPages:pageLoader.cachedPageCount,cacheLimit:pageLoader.maximumCachedPages})"
                )).toString().toUtf8()).object();
                state.insert("phase",QString::fromLatin1(phase));
                state.insert("activityVisible",page->isVisible());
                state.insert("overviewActive",page->property("overviewActive").toBool());
                state.insert("detailOpened",transition->property("opened").toBool());
                state.insert("detailMoving",transition->property("moving").toBool());
                state.insert("detailActive",transition->property("activeDetail").toBool());
                state.insert("detailProgress",transition->property("progress").toDouble());
                state.insert("weaveActive",weave->property("active").toBool());
                state.insert("weaveMoving",weave->property("moving").toBool());
                state.insert("weaveProgress",weave->property("progress").toDouble());
                state.insert("weaveRelease",weave->property("release").toDouble());
                dataSamples.append(state);
                qInfo().noquote()<<"ACTIVITY_ROUTE_HIDE_STATE"<<QJsonDocument(state).toJson(QJsonDocument::Compact);
            };
            const auto detailReset=[&]{return !transition->property("opened").toBool()
                &&!transition->property("activeDetail").toBool()&&!transition->property("moving").toBool()
                &&transition->property("progress").toDouble()==0&&!transition->isVisible();};
            const auto activeKnotSettled=[&]{return weave->property("active").toBool()
                &&weave->property("progress").toDouble()==1&&weave->property("release").toDouble()==0
                &&!weave->property("moving").toBool();};
            pose.evaluate();
            check("route-hide-starts-real-weave-and-detail",!pose.hasError()&&weave->property("moving").toBool()
                &&click(activityDetailButtons[1]));
            activityWait(90);recordRouteState("route-hide-detail-opening");
            check("route-hide-is-requested-during-detail-expansion",transition->property("moving").toBool()
                &&transition->property("progress").toDouble()>0&&transition->property("progress").toDouble()<1);
            eval("AppState.navigate('overview')");
            check("route-hide-reaches-ready-overview-with-no-transient-owners",routeReady("overview"));
            recordRouteState("route-hide-activity-hidden");
            check("route-hide-retires-detail-and-settles-current-knot",!page->isVisible()&&detailReset()&&activeKnotSettled());
            check("route-hide-retains-activity-within-page-cache-contract",eval(
                "pageLoader.pages.activity && pageLoader.cachedPageCount<=pageLoader.maximumCachedPages").toBool()
                &&qvariant_cast<QObject *>(eval("pageLoader.pages.activity.item"))==page);
            eval("AppState.goBack()");
            check("route-restore-reaches-ready-activity-with-no-transient-owners",routeReady("activity"));
            recordRouteState("route-restore-activity-visible");
            check("route-restore-reuses-clean-cached-activity",qvariant_cast<QObject *>(eval("pageLoader.item"))==page
                &&activityVisual(window->contentItem(),"activityDetailTransition")==transition
                &&activityVisual(window->contentItem(),"activityCloudKnotWeave")==weave
                &&page->isVisible()&&page->isEnabled()&&page->property("overviewActive").toBool()
                &&detailReset()&&activeKnotSettled()&&eval("AppState.historyIndex").toInt()==historyIndex);
            check("route-restored-card-opens-detail-again",click(activityDetailButtons[1])&&settled()
                &&transition->property("opened").toBool()&&transition->property("progress").toDouble()==1
                &&transition->property("detailKey").toString()==activityDetailKeys[1]);
            QTest::keyClick(window,Qt::Key_Escape);
            check("route-restored-detail-escape-releases-all-transient-state",settled()&&detailReset()
                &&QTest::qWaitFor(activeKnotSettled,1500)
                &&eval("motionPolicy.activeGrabCount===0 && SwirlTransitionRegistry.activeCount===0").toBool());
            recordRouteState("route-restore-detail-returned");
            activeOverride.reset();
            check("weave-original-proxy-state-binding-restored",weave->property("active").toBool()
                ==(page->property("proxyOwned").toBool()&&page->property("runtimeHealthy").toBool()));
            check("weave-restoration-stops-transient-animation",QTest::qWaitFor([&]{return !weave->property("moving").toBool();},1500));
        }
    }
    auto *controller=qobject_cast<EngineController *>(qmlContext(window)->contextProperty("engineController").value<QObject *>());
    check("real-telemetry-model-present",controller!=nullptr);
    if(controller){
        // Reserved-address records enter the actual isolated model. They are
        // controlled rendering/filter fixtures, never measured network results.
        ProxyEngine::Status fixture;fixture.processAlive=true;fixture.apiHealthy=true;fixture.processId=1;
        fixture.connectionsAt=fixture.trafficAt=QDateTime::currentMSecsSinceEpoch();
        for(int row=0;row<600;++row){
            const int down=row==1?1024*1024:row==2?950*1024:1000+row;
            const int up=10+row;
            fixture.uploadTotal+=up;fixture.downloadTotal+=down;
            fixture.connections.append(QVariantMap{{"id",QString("activity-fixture-%1").arg(row)},{"host",QString("source-%1.example.test").arg(row,4,10,QChar('0'))},
                {"process",QString("fixture-%1.exe").arg(row,4,10,QChar('0'))},{"ip","198.51.100.8"},{"port",443},{"sourceIp","192.0.2.10"},{"sourcePort",40000+row},
                {"protocol",row%2?"tcp":"udp"},{"category",row%2?"proxy":"direct"},{"policy",row%2?"fixture-proxy":"DIRECT"},
                {"uploadBytes",up},{"downloadBytes",down},{"time",QDateTime::fromMSecsSinceEpoch(fixture.connectionsAt).toString(Qt::ISODateWithMs)}});
        }
        controller->telemetry()->ingest(fixture);
        check("visible-home-counts-follow-initial-native-data",homeCountsMatch(600,600,1));
        click(activityDetailButtons[0]);settled();activityWait(350);
        const auto owner=[&](QObject *control,const char *property){while(control&&control->metaObject()->indexOfProperty(property)<0)control=control->parent();return control;};
        const auto evalOn=[&](QObject *target,const QString &code){if(!target)return QVariant();QQmlExpression expression(qmlContext(target),target,code);auto result=expression.evaluate();if(expression.hasError()){qWarning()<<expression.error();check("detail-expression: "+expression.error().toString(),false);}return result;};
        auto *sourceSearch=activityVisual(window->contentItem(),"activitySourcesSearch");
        auto *sourceSort=activityVisual(window->contentItem(),"activitySourcesSort");
        auto *sources=owner(sourceSearch,"kindIndex");
        auto *sourceTable=activityVisual(window->contentItem(),"activitySourcesTable");
        check("sources-search-sort-and-reused-table-present",sourceSearch&&sourceSort&&sources&&sourceTable);
        if(sourceSearch&&sourceSort&&sources&&sourceTable){
            sources->setProperty("kindIndex",2);sources->setProperty("period",0);sources->setProperty("proxyOnly",false);QMetaObject::invokeMethod(sources,"refreshSnapshot");activityWait(100);
            check("sources-details-preserve-all-retained-classifications-and-overflow",evalOn(sources,"sourceRows.length===129 && visibleRows.length===129 && sourceRows.some(row=>row.name==='其他（分类上限）' && row.connections===472)").toBool());
            sourceSearch->setProperty("text","source-0001");
            check("sources-search-applies-to-real-records",evalOn(sources,"visibleRows.length===1 && visibleRows[0].name==='source-0001.example.test'").toBool());
            sourceSearch->setProperty("text",QString());sourceSort->setProperty("currentIndex",2);
            check("sources-sort-uses-numeric-byte-values",evalOn(sources,"visibleRows[0].downloadBytes===1048576 && visibleRows[1].downloadBytes===972800").toBool());
            sourceSort->setProperty("currentIndex",5);activityWait(70);
            check("large-source-table-virtualizes-delegates",sourceTable->property("renderedRows").toInt()>0&&sourceTable->property("renderedRows").toInt()<80&&sourceTable->property("incrementalRows").toBool());
            sourceTable->setProperty("scrollPosition",500);activityWait(80);
            const auto sourceScroll=sourceTable->property("scrollPosition").toDouble();
            const auto selected=evalOn(sources,"visibleRows[20].id").toString();sources->setProperty("selectedId",selected);
            const auto sourceState=[&](const QString &phase){
                auto *view=activityVisual(sourceTable,"tableRowsViewport");
                auto *name=activityVisual(qobject_cast<QQuickItem *>(sources),"activitySourceSelectedName");
                auto *facts=name?name->parentItem():nullptr;
                const int top=view?evalOn(view,"indexAt(1,contentY+1)").toInt():-1;
                QJsonObject state{{"phase",phase},{"expectedSort",5},{"sort",sourceSort->property("currentIndex").toInt()},{"expectedSelected",selected},{"selected",sources->property("selectedId").toString()},
                    {"expectedScroll",sourceScroll},{"scroll",sourceTable->property("scrollPosition").toDouble()},{"tableWidth",sourceTable->width()},{"tableHeight",sourceTable->height()},{"rows",evalOn(sourceTable,"rows.length").toInt()},
                    {"renderedRows",sourceTable->property("renderedRows").toInt()},{"selectedFactsHeight",facts?facts->height():-1},{"selectedFactsVisible",facts&&facts->isVisible()},{"sourceVisible",sources->property("visible").toBool()},
                    {"anchorKey",sourceTable->property("anchorKey").toString()},{"anchorOffset",sourceTable->property("anchorOffset").toDouble()},{"projectionGeneration",sourceTable->property("projectionGeneration").toInt()},
                    {"viewHeight",view?view->height():-1},{"contentHeight",view?view->property("contentHeight").toDouble():-1},{"originY",view?view->property("originY").toDouble():-1},{"currentIndex",view?view->property("currentIndex").toInt():-1},
                    {"topIndex",top},{"topId",top>=0?evalOn(sourceTable,QString("recordAt(%1) ? String(recordAt(%1).id) : ''").arg(top)).toString():QString()},
                    {"topItemPresent",view&&top>=0&&evalOn(view,QString("itemAtIndex(%1)!==null").arg(top)).toBool()},
                    {"topOffset",view&&top>=0?evalOn(view,QString("itemAtIndex(%1) ? itemAtIndex(%1).y-contentY : null").arg(top)).toDouble():0}};
                dataSamples.append(state);qInfo().noquote()<<"ACTIVITY_SOURCE_STATE"<<QJsonDocument(state).toJson(QJsonDocument::Compact);
            };
            auto last=fixture.connections.last().toMap();last["downloadBytes"]=last.value("downloadBytes").toLongLong()+1024;fixture.connections.last()=last;
            fixture.connectionsAt+=1000;fixture.trafficAt=fixture.connectionsAt;fixture.downloadTotal+=1024;controller->telemetry()->ingest(fixture);activityWait(380);
            check("source-refresh-retains-scroll-and-selection",qAbs(sourceTable->property("scrollPosition").toDouble()-sourceScroll)<1&&sources->property("selectedId").toString()==selected);
            const auto sourceClickGeometry=[&](const QString &phase){
                const auto itemGeometry=[&](QQuickItem *item){const auto rect=bounds(item);return QJsonObject{{"name",item->objectName()},{"x",rect.x()},{"y",rect.y()},{"width",rect.width()},{"height",rect.height()},{"visible",item->isVisible()},{"enabled",item->isEnabled()}};};
                QJsonArray ranks;for(int i=0;i<8;++i)if(auto *rank=activityVisual(window->contentItem(),"activitySourceRow-"+QString::number(i)))ranks.append(itemGeometry(rank));
                auto *heading=activityVisual(window->contentItem(),activityDetailButtons[0]);
                QJsonObject state{{"phase",phase},{"title",heading?itemGeometry(heading):QJsonObject()},{"ranks",ranks}};
                dataSamples.append(state);qInfo().noquote()<<"ACTIVITY_SOURCE_CLICK_GEOMETRY"<<QJsonDocument(state).toJson(QJsonDocument::Compact);
            };
            sourceState("source-before-close");close();sourceState("source-after-close");sourceClickGeometry("source-title-before-rapid-click");
            click(activityDetailButtons[0]);sourceState("source-reopen-dispatched");sourceClickGeometry("source-title-after-rapid-click");
            check("source-rapid-reentry-keeps-selection-during-layout",sources->property("selectedId").toString()==selected);
            settled();sourceState("source-reentry-settled");
            check("source-reentry-retains-sort-selection-and-scroll",sourceSort->property("currentIndex").toInt()==5&&sources->property("selectedId").toString()==selected&&qAbs(sourceTable->property("scrollPosition").toDouble()-sourceScroll)<1);
            activityWait(30);sourceState("source-reentry-after-event-loop");
        }
        auto first=fixture.connections.first().toMap();first["downloadBytes"]=first.value("downloadBytes").toLongLong()+256;fixture.connections.first()=first;fixture.downloadTotal+=256;
        auto countFixture=fixture;auto ended=countFixture.connections.last().toMap();ended["closed"]=true;countFixture.connections.last()=ended;
        auto otherDevice=countFixture.connections[598].toMap();otherDevice["sourceIp"]="192.0.2.11";countFixture.connections[598]=otherDevice;
        countFixture.connectionsAt+=1000;countFixture.trafficAt=countFixture.connectionsAt;controller->telemetry()->ingest(countFixture);activityWait(350);
        close();
        check("return-refreshes-native-connection-process-device-counts",homeCountsMatch(599,599,2));
        check("return-refreshes-overview-summary",qAbs(eval("pageLoader.item.totals.total").toDouble()-double(fixture.uploadTotal+fixture.downloadTotal))<0.01);
        fixture.connectionsAt=countFixture.connectionsAt+1;fixture.trafficAt=fixture.connectionsAt;controller->telemetry()->ingest(fixture);
        check("visible-home-counts-follow-reopened-connection",homeCountsMatch(600,600,1));
        click(activityDetailButtons[3]);settled();
        auto *connectionSearch=activityVisual(window->contentItem(),"activityConnectionSearch");
        auto *connectionSort=activityVisual(window->contentItem(),"activityConnectionSort");
        auto *connectionProtocol=activityVisual(window->contentItem(),"activityConnectionProtocol");
        auto *connectionStatus=activityVisual(window->contentItem(),"activityConnectionStatus");
        auto *connectionPage=owner(connectionSearch,"visibleRows");
        auto *connectionTable=activityVisual(window->contentItem(),"connectionTable");
        check("connection-search-protocol-status-sort-and-table-present",connectionSearch&&connectionSort&&connectionProtocol&&connectionStatus&&connectionPage&&connectionTable);
        if(connectionSearch&&connectionSort&&connectionProtocol&&connectionStatus&&connectionPage&&connectionTable){
            connectionSearch->setProperty("text","192.0.2.10");
            check("connections-searches-source-address",evalOn(connectionPage,"visibleRows.length===600").toBool());
            connectionSearch->setProperty("text","fixture-0002.exe");
            check("connections-searches-process",evalOn(connectionPage,"visibleRows.length===1 && visibleRows[0].id==='activity-fixture-2'").toBool());
            connectionSearch->setProperty("text",QString());connectionSort->setProperty("currentIndex",2);
            check("connections-sort-uses-raw-bytes-across-unit-boundary",evalOn(connectionPage,"visibleRows[0].downloadBytes===1048576 && visibleRows[1].downloadBytes===972800").toBool());
            connectionProtocol->setProperty("currentIndex",1);QMetaObject::invokeMethod(connectionProtocol,"activated",Q_ARG(int,1));
            dataSamples.append(QJsonObject{{"phase","protocol-filter"},{"filter",connectionPage->property("protocolFilter").toString()},{"rows",evalOn(connectionPage,"visibleRows.length").toInt()}});
            check("connections-protocol-filter-uses-actual-field",evalOn(connectionPage,"protocolFilter==='tcp' && visibleRows.length===300 && visibleRows.every(row=>row.protocol===protocolFilter)").toBool());
            connectionProtocol->setProperty("currentIndex",0);QMetaObject::invokeMethod(connectionProtocol,"activated",Q_ARG(int,0));connectionStatus->setProperty("currentIndex",1);
            dataSamples.append(QJsonObject{{"phase","status-filter"},{"protocolFilter",connectionPage->property("protocolFilter").toString()},{"status",connectionStatus->property("currentText").toString()},{"rows",evalOn(connectionPage,"visibleRows.length").toInt()}});
            check("connections-status-filter-uses-actual-field",evalOn(connectionPage,"visibleRows.length===600 && visibleRows.every(row=>row.status==='活动')").toBool());
            connectionStatus->setProperty("currentIndex",0);activityWait(80);
            check("large-connection-table-virtualizes-delegates",connectionTable->property("renderedRows").toInt()>0&&connectionTable->property("renderedRows").toInt()<80&&connectionTable->property("incrementalRows").toBool());
        }
        close();
        controller->telemetry()->ingest({});
    }
    const auto privateBytes=[]()->qint64{
#ifdef Q_OS_WIN
        PROCESS_MEMORY_COUNTERS_EX counters{};
        if(GetProcessMemoryInfo(GetCurrentProcess(),reinterpret_cast<PROCESS_MEMORY_COUNTERS *>(&counters),sizeof(counters)))return qint64(counters.PrivateUsage);
#endif
        return 0;
    };
    qmlEngine(window)->collectGarbage();activityWait(100);const auto memoryBeforeWarmup=privateBytes();
    QJsonArray warmupSamples;
    // The first five visits above rendered empty details. The later 600-row
    // fixture remains in retained rankings/history after ingest({}); warm all
    // five views with that data before measuring repeated navigation growth.
    for(int i=0;i<activityDetailKeys.size();++i){
        const auto &key=activityDetailKeys[i];
        const bool opened=click(activityDetailButtons[i])&&settled()&&transition->property("detailKey").toString()==key;
        check("retained-data-warmup-opens-"+key,opened);
        activityWait(350);
        auto *incubation=qmlEngine(window)->incubationController();
        check("retained-data-warmup-finishes-incubation-"+key,!incubation||QTest::qWaitFor([&]{return incubation->incubatingObjectCount()==0;},1500));
        int rankingRows=-1;
        if(key=="traffic"){
            auto *table=activityVisual(window->contentItem(),"trafficRankingTable");
            if(table){QQmlExpression expression(qmlContext(table),table,"rows.length");rankingRows=expression.evaluate().toInt();}
            check("retained-data-warmup-includes-populated-traffic-ranking",rankingRows>0);
        }
        warmupSamples.append(QJsonObject{{"detail",key},{"privateBytes",privateBytes()},{"trafficRankingRows",rankingRows}});
        close();activityWait(100);
    }
    qmlEngine(window)->collectGarbage();activityWait(100);const auto memoryBefore=privateBytes();
    QList<double> frameIntervals;QElapsedTimer delivery;delivery.start();qint64 previousFrame=0;
    {
        // Disconnecting does not remove already queued deliveries. Destroy this
        // receiver before the GC wait/report snapshot and before its captures.
        QObject frameReceiver;
        const auto frameConnection=QObject::connect(window,&QQuickWindow::frameSwapped,&frameReceiver,[&]{
            const auto now=delivery.nsecsElapsed();
            if(previousFrame&&transition->property("moving").toBool())frameIntervals.append((now-previousFrame)/1000000.0);
            previousFrame=now;
        },Qt::QueuedConnection);
        for(int cycle=0;cycle<8;++cycle){click(activityDetailButtons[cycle%activityDetailKeys.size()]);activityWait(470);QTest::keyClick(window,Qt::Key_Escape);activityWait(410);}
        QObject::disconnect(frameConnection);
    }
    qmlEngine(window)->collectGarbage();activityWait(100);
    const auto memoryAfter=privateBytes();std::sort(frameIntervals.begin(),frameIntervals.end());
    check("repeated-details-release-transient-input-and-grab-state",!transition->isVisible()&&!transition->property("moving").toBool()&&eval("motionPolicy.activeGrabCount===0 && SwirlTransitionRegistry.activeCount===0").toBool());
    check("repeated-details-private-memory-growth-below-24MiB",memoryBefore>0&&memoryAfter-memoryBefore<24*1024*1024);
    check("native-animation-delivers-multiple-frames",frameIntervals.size()>=16);
    check("host-system-proxy-unchanged",SystemProxySession::snapshot()==hostProxyBefore);
    QObject::disconnect(originConnection);window->resize(initialSize);window->update();activityWait(100);
    auto *incubation=qmlEngine(window)->incubationController();
    check("restored-viewport-finishes-delegate-incubation-before-exit",!incubation||QTest::qWaitFor([&]{return incubation->incubatingObjectCount()==0;},1500));
    QJsonObject performance{{"cycles",8},{"warmupCycles",activityDetailKeys.size()},{"warmupSamples",warmupSamples},
        {"privateBytesBeforeRetainedDataWarmup",memoryBeforeWarmup},{"retainedDataWarmupGrowthBytes",memoryBefore-memoryBeforeWarmup},
        {"privateBytesBefore",memoryBefore},{"privateBytesAfter",memoryAfter},{"privateGrowthBytes",memoryAfter-memoryBefore},{"frameSamples",frameIntervals.size()},
        {"p95FrameDeliveryMs",frameIntervals.isEmpty()?0:frameIntervals[qMin(frameIntervals.size()-1,qsizetype(frameIntervals.size()*0.95))]},
        {"maxFrameDeliveryMs",frameIntervals.isEmpty()?0:frameIntervals.last()},
        {"method","All five retained detail pages are opened after the 600-record fixture, with model-update and delegate-incubation settlement, before the memory baseline. This one-time populated-data warmup allocation is reported separately. Passive Qt frameSwapped delivery is then sampled during eight warm forward/reverse cycles driven by precise timers, without screenshot readback. The 24 MiB growth bound is unchanged. Qt frame delivery is not hardware presentation FPS; this finite sequence is not an unlimited leak proof."}};
    QJsonObject report{{"checks",checks},{"failures",failures},{"geometrySamples",samples},{"dataSamples",dataSamples},{"performance",performance},{"qt",qVersion()},{"renderer",int(window->rendererInterface()->graphicsApi())},{"dpr",window->devicePixelRatio()},{"scaleFactor",qEnvironmentVariable("QT_SCALE_FACTOR")},{"controlledFixtureRows",600},{"limitations",QJsonArray{"Qt scale-factor runs validate native-window layout and geometry at controlled DPR; they do not prove physical cross-monitor DPI transitions.","Geometry and input observations do not establish display presentation FPS or subjective animation smoothness.","Filter, sort and virtualization use 600 controlled records passed through the actual isolated TelemetryService, not real network acceptance. The separate animation demo has truthful empty production data."}}};
    QDir().mkpath(QFileInfo(output).absolutePath());QFile file(output);if(!file.open(QIODevice::WriteOnly))return 1;file.write(QJsonDocument(report).toJson());
    qInfo()<<"ACTIVITY_DETAIL_RESULT"<<failures;return failures?1:0;
}

int recordActivityDetailDemo(QQuickWindow *window,const QString &directory) {
    QDir().mkpath(directory);QJsonArray frames;int failures=0;
    const auto eval=[&](const QString &code){QQmlExpression expression(qmlContext(window),window,code);expression.evaluate();if(expression.hasError()){qWarning()<<expression.error();++failures;}};
    auto *policy=qobject_cast<MotionPolicy *>(qmlContext(window)->contextProperty("motionPolicy").value<QObject *>());
    if(!policy)return 1;
    policy->setSystemReducedMotionOverrideForTest(0);
    struct RestorePolicy{MotionPolicy *policy;~RestorePolicy(){policy->setSystemReducedMotionOverrideForTest(-1);}} restore{policy};
    eval("Theme.reduceMotion=false;Theme.followSystemMotion=false;Theme.mode='Light';AppState.navigate('activity')");
    window->resize(1013,672);window->requestActivate();activityWait(700);
    auto *transition=activityVisual(window->contentItem(),"activityDetailTransition");
    if(!transition)return 1;
    QElapsedTimer clock;clock.start();int index=0;
    const auto capture=[&](const QString &key,const QString &phase,int duration,bool finishTransition=false){
        QElapsedTimer phaseClock;phaseClock.start();
        while(phaseClock.elapsed()<duration||(finishTransition&&transition->property("moving").toBool())){
            if(phaseClock.elapsed()>5000){++failures;break;}
            const auto name=QString("%1.png").arg(index++,5,10,QChar('0'));
            const double start=clock.nsecsElapsed()/1000000.0;const auto image=window->grabWindow();
            if(!image.save(directory+"/"+name))++failures;
            frames.append(QJsonObject{{"file",name},{"key",key},{"phase",phase},{"startMs",start},{"endMs",clock.nsecsElapsed()/1000000.0},{"progress",transition->property("progress").toDouble()}});
            activityWait(16);
        }
    };
    for(int i=0;i<activityDetailKeys.size();++i){
        auto *button=activityVisual(window->contentItem(),activityDetailButtons[i]);
        if(!button){++failures;continue;}
        auto *sourceCard=activityVisual(window->contentItem(),activityDetailCards[i]);
        const auto center=i==0&&sourceCard?sourceCard->mapToScene(QPointF(sourceCard->width()*0.65,sourceCard->height()*0.55)).toPoint()
            :button->mapToScene(QPointF(button->width()/2,button->height()/2)).toPoint();
        QTest::mouseMove(window,center);capture(activityDetailKeys[i],"hover",160);
        QTest::mousePress(window,Qt::LeftButton,Qt::NoModifier,center);capture(activityDetailKeys[i],"press",90);
        QTest::mouseRelease(window,Qt::LeftButton,Qt::NoModifier,center);capture(activityDetailKeys[i],"expand",650,true);
        if(transition->property("progress").toDouble()!=1||transition->property("detailKey").toString()!=activityDetailKeys[i])++failures;
        capture(activityDetailKeys[i],"detail",450);
        QTest::keyClick(window,Qt::Key_Escape);capture(activityDetailKeys[i],"return",600,true);
        if(transition->isVisible()||transition->property("progress").toDouble()!=0)++failures;
    }
    activityWait(400);window->update();
    if(auto *incubation=qmlEngine(window)->incubationController())if(!QTest::qWaitFor([&]{return incubation->incubatingObjectCount()==0;},1500))++failures;
    QFile report(directory+"/frames.json");if(!report.open(QIODevice::WriteOnly))return 1;
    report.write(QJsonDocument(QJsonObject{{"frames",frames},{"failures",failures},{"qt",qVersion()},{"renderer",int(window->rendererInterface()->graphicsApi())},{"dpr",window->devicePixelRatio()},{"method","Actual Qt Quick window readbacks of isolated real UI, with monotonic capture times. Readback overhead changes cadence; this clip demonstrates geometry and is not display FPS evidence."}}).toJson());
    return failures?1:0;
}
}

int runViewportChecks(QQuickWindow *window,const QString &directory) {
    QDir().mkpath(directory);QJsonArray checks;int failures=0;
    auto eval=[&](const QString &code){QQmlExpression e(qmlContext(window),window,code);return e.evaluate();};
    eval("Theme.reduceMotion=true;Theme.transparency=false");
    window->setProperty("swirlViewportTest",true);
    const auto dpr=window->devicePixelRatio();
    for(const auto pixels:{QSize(1920,1080),QSize(2560,1440),QSize(3840,2160)}) {
        window->resize(qRound(pixels.width()/dpr),qRound(pixels.height()/dpr));
        for(const auto theme:{QString("Light"),QString("Dark")}) {
            eval("Theme.mode='"+theme+"'");
            for(const auto route:{QString("featurehub"),QString("overview"),QString("subscriptions")}) {
                eval("AppState.navigate('"+route+"')");QTest::qWait(180);window->update();QTest::qWait(80);
                const auto shot=window->grabWindow();
                const auto name=QString("%1-%2-%3.png").arg(pixels.width()).arg(theme.toLower(),route);
                const bool valid=!shot.isNull() && qAbs(shot.width()-pixels.width())<=2 && qAbs(shot.height()-pixels.height())<=2 && shot.save(directory+"/"+name) && eval("pageLoader.item!==null").toBool();
                checks.append(QJsonObject{{"file",name},{"valid",valid},{"physicalWidth",shot.width()},{"physicalHeight",shot.height()},{"dpr",dpr}});
                if(!valid)++failures;
            }
        }
    }
    QFile report(directory+"/viewports.json");if(!report.open(QIODevice::WriteOnly))return 2;report.write(QJsonDocument(QJsonObject{{"checks",checks},{"failures",failures},{"note","GPU UI render at requested physical viewport sizes; OS desktop resolution was not changed"}}).toJson());
    qInfo()<<"VIEWPORT_CHECKS"<<checks.size()<<"failures"<<failures<<"DPR"<<dpr;
    return failures?1:0;
}

int runMotionDemo(QQuickWindow *window,const QString &directory) {
    if(qEnvironmentVariableIsSet("SWIRL_ACTIVITY_DETAIL_DEMO"))return recordActivityDetailDemo(window,directory);
    QDir().mkpath(directory);
    const auto eval=[&](const QString &code){QQmlExpression e(qmlContext(window),window,code);e.evaluate();};
    std::function<QQuickItem *(QQuickItem *,const QString &)> find;
    find=[&](QQuickItem *root,const QString &name)->QQuickItem *{if(root->objectName()==name)return root;for(auto *child:root->childItems())if(auto *match=find(child,name))return match;return nullptr;};
    const auto point=[&](QQuickWindow *owner,const QString &name){auto *control=find(owner->contentItem(),name);return control?control->mapToScene(QPointF(control->width()/2,control->height()/2)).toPoint():QPoint(-10,-10);};
    window->resize(1100,860);window->requestActivate();
    eval("Theme.reduceMotion=false;Theme.transparency=false;Theme.mode='Light';AppState.navigate('featurehub')");
    QTest::qWait(450);
    int failures=0;
    for(int frame=0;frame<80;++frame) {
        if(frame==0)QTest::mouseMove(window,point(window,"settings-subscriptions"));
        if(frame==5)QTest::mousePress(window,Qt::LeftButton,Qt::NoModifier,point(window,"settings-subscriptions"));
        if(frame==8)QTest::mouseRelease(window,Qt::LeftButton,Qt::NoModifier,point(window,"settings-subscriptions"));
        if(frame==25)QTest::mousePress(window,Qt::LeftButton,Qt::NoModifier,point(window,"addSubscription"));
        if(frame==28)QTest::mouseRelease(window,Qt::LeftButton,Qt::NoModifier,point(window,"addSubscription"));
        if(frame==48)QTest::keyClick(window,Qt::Key_Escape);
        if(frame==60)QTest::keyClick(window,Qt::Key_Escape);
        if(frame==65)QTest::mouseClick(window,Qt::LeftButton,Qt::NoModifier,point(window,"nav-overview"));
        QTest::qWait(40);
        auto image=window->grabWindow();
        if(!image.scaledToWidth(825,Qt::SmoothTransformation).save(directory+QString("/%1.png").arg(frame,3,10,QChar('0'))))++failures;
    }
    return failures?1:0;
}

int runMotionVisualChecks(QQuickWindow *window, const QString &directory) {
    QDir().mkpath(directory);QJsonArray captures;int errors=0;
    const auto eval=[&](const QString &code){QQmlExpression e(qmlContext(window),window,code);const auto result=e.evaluate();if(e.hasError()){qWarning()<<e.error();++errors;}return result;};
    std::function<QQuickItem *(QQuickItem *,const QString &)> find;
    find=[&](QQuickItem *root,const QString &name)->QQuickItem *{if(root->objectName()==name&&root->isVisible())return root;for(auto *child:root->childItems())if(auto *value=find(child,name))return value;return nullptr;};
    std::function<void(QQuickItem *)> repaint;
    repaint=[&](QQuickItem *item){if(item->metaObject()->indexOfMethod("requestPaint()")>=0)QMetaObject::invokeMethod(item,"requestPaint");for(auto *child:item->childItems())repaint(child);};
    const auto capture=[&](const QString &fileKey,const QString &route,const QString &theme,const QSize &size,const QString &state=QString(),QQuickWindow *target=nullptr){
        auto *owner=target?target:window;QTest::mouseMove(owner,QPoint(-20,-20));repaint(owner->contentItem());owner->update();QTest::qWait(60);
        QImage shot=owner->grabWindow();
        if(shot.isNull()){auto grab=owner->contentItem()->grabToImage();if(grab){QSignalSpy ready(grab.data(),&QQuickItemGrabResult::ready);owner->update();ready.wait(2000);shot=grab->image();}}
        const auto name=theme.toLower()+"-"+QString::number(size.width())+"-"+fileKey+".png";
        const bool saved=!shot.isNull()&&shot.save(directory+"/"+name);if(!saved)++errors;
        captures.append(QJsonObject{{"file",name},{"route",route},{"state",state},{"theme",theme},{"saved",saved},{"logicalWidth",owner->width()},{"logicalHeight",owner->height()},{"pixelWidth",shot.width()},{"pixelHeight",shot.height()},{"dpr",owner->devicePixelRatio()},{"window",owner->objectName()},{"renderer",int(owner->rendererInterface()->graphicsApi())}});
    };
    const auto popup=[&](const QString &name)->QObject *{for(auto *object:window->findChildren<QObject *>())if(object->property("opened").isValid()&&object->property("opened").toBool()&&(name.isEmpty()||object->objectName()==name))return object;return nullptr;};
    const auto click=[&](const QString &name){auto *control=find(window->contentItem(),name);if(!control||!control->isEnabled())return false;QTest::mouseClick(window,Qt::LeftButton,Qt::NoModifier,control->mapToScene(QPointF(control->width()/2,control->height()/2)).toPoint());return true;};
    // These are own-window Qt renders of the real isolated, stopped state.
    // No fake traffic, successful operations, nodes or recent events are seeded.
    eval("Theme.reduceMotion=true;Theme.transparency=true;AppState.toast='';AppState.recentEvents=[]");
    QStringList routes=eval("AppState.allPageIds").toStringList();
    if(routes.isEmpty())for(const auto &value:QJsonDocument::fromJson(eval("JSON.stringify(AppState.allPageIds)").toString().toUtf8()).array())routes.append(value.toString());
    routes<<"activity"<<"fonts";routes.removeDuplicates();
    // These navigation aliases open a separate window/overlay and reset the
    // main route. Their real surfaces are captured in the external branch.
    routes.removeAll("dashboard");routes.removeAll("requestlogs");
    for(const auto &size:{QSize(1100,760),QSize(800,672)}){
        window->resize(size);
        for(const auto &theme:{QString("Light"),QString("Dark")}){
            eval("Theme.mode='"+theme+"'");
            for(const auto &route:routes){
                eval("AppState.currentPage='"+route+"';AppState.toast=''");
                if(!QTest::qWaitFor([&]{return eval("pageLoader.item && pageLoader.activeLoader.routeId===AppState.currentPage && !pageLoader.pendingGrab && !pageLoader.moving").toBool();},5000)){qWarning()<<"Capture route not ready"<<route;++errors;continue;}
                if(route=="settings"||route=="fonts"){
                    eval(route=="fonts"?"pageLoader.item.section='字体'":"pageLoader.item.section='常规'");
                    if(!QTest::qWaitFor([&]{return eval("pageLoader.item.currentSectionReady()").toBool();},5000)){++errors;continue;}
                    eval("pageLoader.item.scrollToTop()");
                }
                if(route=="policies")eval("pageLoader.item.tabIndex=0");
                QTest::qWait(100);capture(route,route,theme,size);
                if(route=="settings"){
                    const auto sections=QJsonDocument::fromJson(eval("JSON.stringify(pageLoader.item.sections)").toString().toUtf8()).array();
                    for(int index=0;index<sections.size();++index){
                        const auto section=sections[index].toString();
                        const auto quoted=QString::fromUtf8(QJsonDocument(QJsonArray{section}).toJson(QJsonDocument::Compact));
                        eval("pageLoader.item.section=("+quoted+")[0]");
                        if(!QTest::qWaitFor([&]{return eval("pageLoader.item.currentSectionReady()").toBool();},5000)){++errors;continue;}
                        eval("pageLoader.item.scrollToTop()");QTest::qWait(60);
                        const auto key=QString("settings-%1").arg(index,2,10,QChar('0'));
                        capture(key,"settings",theme,size,section);
                        if(section=="常规"||section=="字体"||section=="代理"){eval("pageLoader.item.scrollToBottom()");QTest::qWait(60);capture(key+"-bottom","settings",theme,size,section+" / bottom");}
                    }
                    eval("pageLoader.item.section='常规';pageLoader.item.scrollToTop()");
                }
                if(route=="policies"){eval("pageLoader.item.tabIndex=1");QTest::qWait(60);capture("policies-groups",route,theme,size,"策略组");eval("pageLoader.item.tabIndex=0");}
                const auto button=route=="proxies"?QString("nodeAddButton"):route=="subscriptions"?QString("addSubscription"):route=="rules"?QString("addRoutingRule"):route=="tls"?QString("addMitmHostname"):route=="rewrite"?QString("rewriteEditor-redirect"):QString();
                if(!button.isEmpty()&&click(button)){
                    if(QTest::qWaitFor([&]{return popup(QString())!=nullptr;},4000)){capture(route+"-editor",route,theme,size,"empty editor");if(auto *dialog=popup(QString())){QMetaObject::invokeMethod(dialog,"close");QTest::qWaitFor([&]{return !dialog->property("visible").toBool();},2500);}}
                    else{qWarning()<<"Capture editor did not open"<<route;++errors;}
                }
                if(route=="external"){
                    QMetaObject::invokeMethod(window,"openDashboard");QTest::qWait(120);
                    if(auto *panel=window->findChild<QQuickWindow *>("dashboardWindow")){panel->resize(size);capture("external-window",route,theme,size,"independent request window",panel);panel->hide();}
                    else ++errors;
                    QMetaObject::invokeMethod(window,"openCaptureInspector");
                    if(QTest::qWaitFor([&]{return popup("captureInspectorDialog")!=nullptr;},5000)){capture("capture-inspector-dialog","requestlogs",theme,size,"main overlay request inspector");if(auto *dialog=popup("captureInspectorDialog")){QMetaObject::invokeMethod(dialog,"close");QTest::qWaitFor([&]{return !dialog->property("visible").toBool();},2500);}}
                    else ++errors;
                }
            }
        }
    }
    QFile file(directory+"/manifest.json");if(!file.open(QIODevice::WriteOnly))return 1;file.write(QJsonDocument(captures).toJson());
    qInfo()<<"MOTION_VISUAL_CAPTURES"<<captures.size()<<"uniqueRoutes"<<routes.size()<<"errors"<<errors;
    return errors?1:0;
}
#include "ScrollBench.h"
#include "SixAChecks.h"
#include "ActivityPerfChecks.h"
int runMotionChecks(QQuickWindow *window, const QString &output) {
    if(qEnvironmentVariableIsSet("SWIRL_ACTIVITY_PERF_CHECKS"))return runActivityPerfChecks(window,output);
    if(qEnvironmentVariableIsSet("SWIRL_ACTIVITY_DETAIL_CHECKS"))return runActivityDetailChecks(window,output);
    if(qEnvironmentVariableIsSet("SWIRL_APEC_GLASS_CHECKS")) {
        extern int runApecGlassChecks(QQuickWindow *,const QString &);
        return runApecGlassChecks(window,output);
    }
    if(qEnvironmentVariableIsSet("SWIRL_APEC_MOTION_CHECKS")) {
        extern int runApecMotionChecks(QQuickWindow *,const QString &);
        return runApecMotionChecks(window,output);
    }
    if(qEnvironmentVariableIsSet("SWIRL_ROUTE_BENCH"))return runRouteBench(window,output);
    if(qEnvironmentVariableIsSet("SWIRL_U2_CHECKS")) {
        extern int runU2Checks(QQuickWindow *, const QString &);
        return runU2Checks(window,output);
    }
    if(qEnvironmentVariableIsSet("SWIRL_LIQUID_GLASS_CHECKS")) {
        extern int runLiquidGlassChecks(QQuickWindow *, const QString &);
        return runLiquidGlassChecks(window,output);
    }
    if(qEnvironmentVariableIsSet("SWIRL_6A_CHECKS"))return runSixAChecks(window,output);
    if(qEnvironmentVariableIsSet("SWIRL_RECORD_INTERACTIONS"))return recordInteractionSequence(window,output);
    if(qEnvironmentVariableIsSet("SWIRL_SCROLL_BENCH"))return runScrollBench(window,output);
    // Use the application's event dispatcher for timing. QTest::qWait polls
    // with sleeps, which can quantize Windows samples to 15.6 ms and prevent
    // the animation driver from receiving native high-refresh frame events.
    auto wait=[](int milliseconds) {
        QEventLoop loop;QTimer timer;timer.setTimerType(Qt::PreciseTimer);
        timer.setSingleShot(true);QObject::connect(&timer,&QTimer::timeout,&loop,&QEventLoop::quit);
        timer.start(milliseconds);loop.exec();
    };
    QJsonArray checks,activityLayoutSamples;
    QJsonObject activityEscapeContinuity;
    int failures=0;
    auto check=[&](const QString &name,bool passed) {
        checks<<QJsonObject{{"name",name},{"passed",passed}};
        if(!passed)++failures;
        qInfo()<<"MOTION_CHECK"<<name<<passed;
    };
    auto eval=[&](const QString &code) {
        QQmlExpression e(qmlContext(window),window,code);
        auto value=e.evaluate();
        if(e.hasError()){qWarning()<<e.error();check("expression: "+e.error().toString(),false);}
        return value;
    };
    auto *host=window->findChild<QQuickItem *>("pageLoader");
    if(!host)return 1;
    auto *policy=qobject_cast<MotionPolicy *>(qmlContext(window)->contextProperty("motionPolicy").value<QObject *>());
    check("motion-policy-present",policy!=nullptr);
    if(!policy)return 1;
    const bool nativeSystemReducedMotion=policy->systemReducedMotion();
    // CI may legitimately disable client animations. Exercise the animated
    // branch deterministically in this test process, then check both reduced
    // paths independently. The production executable has no override API.
    policy->setSystemReducedMotionOverrideForTest(0);
    struct RestoreSystemMotionPolicy {
        MotionPolicy *policy;
        ~RestoreSystemMotionPolicy(){policy->setSystemReducedMotionOverrideForTest(-1);}
    } restoreSystemMotionPolicy{policy};
    auto item=[&] {return qvariant_cast<QObject *>(host->property("item"));};
    std::function<QQuickItem *(QQuickItem *,const QString &)> findVisual;
    findVisual=[&](QQuickItem *root,const QString &name)->QQuickItem * {
        if(!root)return nullptr;
        if(root->objectName()==name)return root;
        for(auto *child:root->childItems())if(auto *found=findVisual(child,name))return found;
        return nullptr;
    };
    auto waitOpen=[&](QObject *popup) {
        QElapsedTimer timer;timer.start();
        while(!popup->property("opened").toBool()&&timer.elapsed()<1800)wait(20);
    };
    auto settle=[&](int timeout=2500) {
        QElapsedTimer timer;timer.start();
        do {wait(20);} while((host->property("moving").toBool()||host->property("pendingGrab").toBool())&&timer.elapsed()<timeout);
        return !host->property("moving").toBool()&&!host->property("pendingGrab").toBool();
    };
    auto route=[&](const QString &id) {eval("AppState.navigate('"+id+"')");wait(25);return settle();};
    auto memory=[]()->qint64 {
#ifdef Q_OS_WIN
        PROCESS_MEMORY_COUNTERS counters{};
        if(GetProcessMemoryInfo(GetCurrentProcess(),&counters,sizeof(counters)))return qint64(counters.WorkingSetSize);
#endif
        return 0;
    };
    window->resize(1100,760);
    eval("Theme.reduceMotion=false;Theme.transparency=false;Theme.mode='Light';AppState.toast=''");
    wait(120);
    const bool reduced=eval("SwirlMotion.reduced").toBool();
    check("animated-test-policy-is-active",!reduced);
    check("initial-page-present",item()!=nullptr);
    auto *rewriteLoader=window->findChild<QObject *>("rewriteRulesLoader");
    check("rewrite-editor-is-lazy-at-startup",rewriteLoader&&!rewriteLoader->property("active").toBool()&&!qvariant_cast<QObject *>(rewriteLoader->property("item")));
    eval("window.openRewriteEditor('redirect','HTTP redirect rules')");
    QTest::keyClick(window,Qt::Key_Escape);
    const bool rewriteReady=rewriteLoader&&QTest::qWaitFor([&]{return rewriteLoader->property("status").toInt()==1;},5000);
    auto *rewriteEditor=rewriteReady?qvariant_cast<QObject *>(rewriteLoader->property("item")):nullptr;
    check("escape-cancels-pending-rewrite-opening",rewriteEditor&&QTest::qWaitFor([&]{return !rewriteEditor->property("visible").toBool();},2500)&&!rewriteLoader->property("wantOpen").toBool());
    eval("window.openRewriteEditor('header','HTTP header rules');window.openRewriteEditor('redirect','HTTP redirect rules')");
    check("rewrite-editor-opens-after-asynchronous-load",rewriteEditor&&QTest::qWaitFor([&]{return rewriteEditor->property("opened").toBool();},2500));
    check("rewrite-editor-last-request-wins",rewriteEditor&&rewriteEditor->property("kind")=="redirect"&&rewriteEditor->property("title")=="HTTP redirect rules");
    if(rewriteEditor){
        const auto previousSelection=rewriteEditor->property("chosen");
        rewriteEditor->setProperty("chosen","retained-selection-fixture");
        QMetaObject::invokeMethod(rewriteEditor,"close");
        check("rewrite-editor-releases-first-modal-grab",QTest::qWaitFor([&]{return !rewriteEditor->property("visible").toBool();},2500));
        eval("window.openRewriteEditor('redirect','HTTP redirect rules')");
        check("rewrite-editor-reuses-instance-and-local-state",qvariant_cast<QObject *>(rewriteLoader->property("item"))==rewriteEditor&&rewriteEditor->property("chosen")=="retained-selection-fixture"&&QTest::qWaitFor([&]{return rewriteEditor->property("opened").toBool();},2500));
        rewriteEditor->setProperty("chosen",previousSelection);
        QMetaObject::invokeMethod(rewriteEditor,"close");
        check("rewrite-editor-releases-reopened-modal-grab",QTest::qWaitFor([&]{return !rewriteEditor->property("visible").toBool();},2500));
    }
    QPointer<QObject> captureLoader=window->findChild<QObject *>("captureInspectorLoader");
    check("capture-inspector-is-lazy-at-startup",captureLoader&&!captureLoader->property("active").toBool()&&!qvariant_cast<QObject *>(captureLoader->property("item")));
    if(captureLoader){
        const QString captureRoute=eval("AppState.currentPage").toString();
        const int captureHistory=eval("AppState.historyIndex").toInt();
        const int dismissalsBeforeCapture=eval("dismissals.count").toInt();
        eval("window.openCaptureInspector()");
        check("capture-inspector-is-pending-before-escape",captureLoader&&captureLoader->property("status").toInt()==2&&captureLoader->property("wantOpen").toBool());
        QTest::keyClick(window,Qt::Key_Escape);
        check("capture-pending-escape-preserves-route",eval("AppState.currentPage").toString()==captureRoute&&eval("AppState.historyIndex").toInt()==captureHistory);
        check("capture-pending-escape-clears-admission",captureLoader&&!captureLoader->property("wantOpen").toBool());
        const bool captureReady=QTest::qWaitFor([&]{return captureLoader&&captureLoader->property("status").toInt()==1;},5000);
        QPointer<QObject> inspectorDialog=captureReady?qvariant_cast<QObject *>(captureLoader->property("item")):nullptr;
        check("capture-inspector-loads-asynchronously",captureReady&&inspectorDialog);
        check("capture-cancelled-load-does-not-open",inspectorDialog&&!inspectorDialog->property("visible").toBool()&&eval("dismissals.count").toInt()==dismissalsBeforeCapture);
        if(inspectorDialog){
            eval("window.openCaptureInspector()");
            check("capture-inspector-reopens-after-cancel",QTest::qWaitFor([&]{return inspectorDialog&&inspectorDialog->property("opened").toBool();},2500));
            check("capture-inspector-has-owned-modal-layer",eval("captureInspectorLoader.item.ownerWindow===window").toBool()&&eval("dismissals.count").toInt()==dismissalsBeforeCapture+1);
            auto *dialogContent=qvariant_cast<QQuickItem *>(inspectorDialog->property("contentItem"));
            std::function<QQuickItem *(QQuickItem *)> findInspectorPage;
            findInspectorPage=[&](QQuickItem *candidate)->QQuickItem *{
                if(!candidate)return nullptr;
                if(candidate->metaObject()->indexOfProperty("captureProvider")>=0
                    &&candidate->metaObject()->indexOfProperty("selectedId")>=0
                    &&candidate->metaObject()->indexOfProperty("query")>=0)return candidate;
                for(auto *child:candidate->childItems())if(auto *found=findInspectorPage(child))return found;
                return nullptr;
            };
            QPointer<QQuickItem> inspectorPage=findInspectorPage(dialogContent);
            check("capture-inspector-real-state-properties-present",inspectorPage!=nullptr);
            QVariant previousSelectedId,previousQuery;
            if(inspectorPage){
                previousSelectedId=inspectorPage->property("selectedId");previousQuery=inspectorPage->property("query");
                check("capture-inspector-state-can-be-edited",inspectorPage->setProperty("selectedId",QStringLiteral("retained-capture-session-fixture"))
                    &&inspectorPage->setProperty("query",QStringLiteral("retained capture filter")));
            }
            QMetaObject::invokeMethod(inspectorDialog,"close");
            check("capture-inspector-close-releases-modal-layer",QTest::qWaitFor([&]{return inspectorDialog&&!inspectorDialog->property("visible").toBool()&&eval("dismissals.count").toInt()==dismissalsBeforeCapture;},2500));
            eval("window.openCaptureInspector()");
            const bool reopened=QTest::qWaitFor([&]{return inspectorDialog&&inspectorDialog->property("opened").toBool();},2500);
            check("capture-inspector-retains-instance-and-state",reopened&&captureLoader&&inspectorPage
                &&qvariant_cast<QObject *>(captureLoader->property("item"))==inspectorDialog
                &&findInspectorPage(qvariant_cast<QQuickItem *>(inspectorDialog->property("contentItem")))==inspectorPage
                &&inspectorPage->property("selectedId").toString()==QStringLiteral("retained-capture-session-fixture")
                &&inspectorPage->property("query").toString()==QStringLiteral("retained capture filter"));
            if(inspectorPage){inspectorPage->setProperty("selectedId",previousSelectedId);inspectorPage->setProperty("query",previousQuery);}
            QTest::keyClick(window,Qt::Key_Escape);
            check("capture-inspector-escape-releases-reopened-modal-layer",QTest::qWaitFor([&]{return inspectorDialog&&!inspectorDialog->property("visible").toBool()&&eval("dismissals.count").toInt()==dismissalsBeforeCapture;},2500));
        }
    }
    route("featurehub");
    auto *hub=item();
    check("hub-loaded",hub!=nullptr);
    route("rules");auto *rulePage=item();auto *search=findVisual(qobject_cast<QQuickItem *>(rulePage),"rulesSearch");
    if(search)search->setProperty("text","http");route("settings");route("rules");
    check("page-instance-preserved",item()==rulePage);
    check("editable-state-preserved",search&&search->property("text").toString()=="http");
    if(search)search->setProperty("text","");
    route("dns");auto *dnsPage=item();auto *flick=findVisual(qobject_cast<QQuickItem *>(dnsPage),"motion-dns-scroll");
    if(flick)flick->setProperty("contentY",qMin(40.0,flick->property("contentHeight").toDouble()-flick->height()));
    wait(80);const double scrollBefore=flick?flick->property("contentY").toDouble():-1;
    route("settings");route("dns");
    qInfo()<<"MOTION_SCROLL"<<scrollBefore<<(flick?flick->property("contentY"):QVariant())<<(flick?flick->property("contentHeight"):QVariant())<<(flick?flick->height():-1);
    check("scroll-state-preserved",flick&&scrollBefore>0&&qAbs(flick->property("contentY").toDouble()-scrollBefore)<0.1);
    if(flick)flick->setProperty("contentY",0);
    route("proxies");
    auto *proxy=item();
    auto *dialog=proxy?proxy->findChild<QObject *>("proxyAddDialog"):nullptr;
    check("dialog-present",dialog!=nullptr);
    if(dialog) {
        QMetaObject::invokeMethod(dialog,"open");waitOpen(dialog);
        check("dialog-open",dialog->property("opened").toBool());
        QTest::keyClick(window,Qt::Key_Escape);wait(450);
        check("escape-closes-dialog",!dialog->property("visible").toBool());
        QMetaObject::invokeMethod(dialog,"open");wait(100);
        route("settings");wait(250);
        check("leaving-page-releases-modal",!dialog->property("visible").toBool());
    }
    route("gateway");
    auto *combo=findVisual(qobject_cast<QQuickItem *>(item()),"deviceSortPicker");
    auto *popup=combo?qvariant_cast<QObject *>(combo->property("popup")):nullptr;
    if(popup){const auto point=combo->mapToScene(QPointF(combo->width()/2,combo->height()/2)).toPoint();
        QTest::mouseClick(window,Qt::LeftButton,Qt::NoModifier,point);waitOpen(popup);qInfo()<<"MOTION_DROPDOWN"<<point<<combo->isEnabled()<<combo->isVisible()<<popup->property("visible")<<popup->property("opened")<<popup->property("scale")<<popup->property("opacity");check("dropdown-opens",popup->property("opened").toBool());
        QQuickWindow *popupWindow=window;for(auto *candidate:QGuiApplication::allWindows())if(candidate->isVisible()&&candidate->flags().testFlag(Qt::Popup))if(auto *quick=qobject_cast<QQuickWindow *>(candidate))popupWindow=quick;
        QTest::keyClick(popupWindow,Qt::Key_Escape);wait(400);check("dropdown-escape",!popup->property("visible").toBool());
    }else check("dropdown-present",false);
    auto *button=findVisual(window->contentItem(),"nav-overview");
    if(button) {
        const auto p=button->mapToScene(QPointF(button->width()/2,button->height()/2)).toPoint();
        for(int i=0;i<8;++i){QTest::mousePress(window,Qt::LeftButton,Qt::NoModifier,p);wait(22);QTest::mouseRelease(window,Qt::LeftButton,Qt::NoModifier,p);wait(15);}
        wait(1400);settle();
        check("rapid-button-release-restores-scale",qAbs(button->property("motionScale").toDouble()-1)<0.001);
        check("button-hit-area-unchanged",button->scale()==1);
        check("click-light-stops-after-release",button->property("clickLight").toDouble()==0);
        QTest::mouseClick(window,Qt::LeftButton,Qt::NoModifier,p);wait(60);
        auto *shader=button->findChild<QObject *>("clickLightShaderLoader");
        check("ordinary-click-has-no-light-overlay",shader==nullptr && button->property("clickLight").toDouble()==0);
        const auto beforeRoute=eval("AppState.currentPage").toString();
        QTest::mousePress(window,Qt::LeftButton,Qt::NoModifier,p);
        QTest::mouseMove(window,QPoint(window->width()-15,window->height()-15));
        QTest::mouseRelease(window,Qt::LeftButton,Qt::NoModifier,QPoint(window->width()-15,window->height()-15));wait(220);
        check("drag-away-cancels-activation",eval("AppState.currentPage").toString()==beforeRoute && !button->property("down").toBool());
        button->forceActiveFocus();QTest::keyClick(window,Qt::Key_Space);wait(250);
        check("keyboard-activation-keeps-stable-hit-area",button->scale()==1 && !button->property("down").toBool());

    } else check("navigation-button-present",false);
    auto *indicator=findVisual(window->contentItem(),"sidebarSelectionIndicator");
    check("one-sidebar-indicator-present",indicator!=nullptr);
    const QStringList sidebarRoutes={"activity","overview","processes","gateway","policies","rules","capture","tls","rewrite","featurehub"};
    for(int i=0;i<30;++i){
        auto *entry=findVisual(window->contentItem(),"nav-"+sidebarRoutes[(i%2?29-i:i)%sidebarRoutes.size()]);
        if(entry)QTest::mouseClick(window,Qt::LeftButton,Qt::NoModifier,entry->mapToScene(QPointF(entry->width()/2,entry->height()/2)).toPoint());
        wait(20);
        check("sidebar-single-owner-"+QString::number(i),indicator&&findVisual(window->contentItem(),"sidebarSelectionIndicator")==indicator);
    }
    settle();wait(300);
    check("sidebar-selection-reaches-last-click",eval("AppState.currentPage==='activity'").toBool());
    route("activity");
    auto *activity=qobject_cast<QQuickItem *>(item());
    auto *upload=findVisual(activity,"activityUploadRateValue");
    auto *activityScroll=findVisual(activity,"activityScroll");
    auto *connections=findVisual(activity,"activityConnectionCount"),*total=findVisual(activity,"activityTotal");
    auto *diagnostic=findVisual(activity,"activityDiagnosticCard"),*trafficCard=findVisual(activity,"activityTrafficCard");
    auto *trafficFilter=findVisual(activity,"activityTrafficFilter"),*sourceFilter=findVisual(activity,"activitySourceFilter");
    auto *periodFilter=findVisual(activity,"activityPeriodFilter"),*trafficChart=findVisual(activity,"activityTrafficChart");
    auto *activityTransition=findVisual(activity,"activityDetailTransition");
    auto *activitySurface=findVisual(activity,"activityDetailSurface");
    check("activity-apec-status-transfer-diagnostics-and-detail-origins-present",activity&&activityScroll&&diagnostic&&trafficCard&&upload&&connections&&total&&activityTransition&&activitySurface);
    if(activity&&activityScroll&&diagnostic&&trafficCard&&upload&&connections&&total&&activityTransition&&activitySurface){
        const auto originalSize=window->size();
        // The five-card layout has a 736dp *content* breakpoint. 1030dp keeps
        // the expanded sidebar and both page paddings in the normal-width case.
        const QSize normalSize(qRound(eval("Theme.dp(1030)").toDouble()),qRound(eval("Theme.dp(672)").toDouble()));
        window->resize(normalSize);wait(250);
        auto *sourceCard=findVisual(activity,"activitySourcesCard");
        auto *statusCard=findVisual(activity,"activityStatusCard");
        auto *connectionsSurface=findVisual(activity,"activityConnectionsCard");
        const auto cardGeometry=[&]{
            QJsonArray cards;
            for(const auto &name:activityDetailCards){
                auto *card=findVisual(activity,name);
                if(!card){cards.append(QJsonObject{{"name",name},{"present",false}});continue;}
                const auto rect=card->mapRectToItem(activity,QRectF(QPointF(),card->size()));
                cards.append(QJsonObject{{"name",name},{"x",rect.x()},{"y",rect.y()},{"width",rect.width()},{"height",rect.height()},
                    {"alpha",card->property("color").value<QColor>().alpha()},{"hovered",card->property("hovered").toBool()},
                    {"focused",card->property("focused").toBool()},{"lift",card->property("lift").toDouble()}});
            }
            return cards;
        };
        const auto insideSurface=[](QQuickItem *section,QQuickItem *surface){return section&&surface&&QRectF(QPointF(),surface->size()).adjusted(-1,-1,1,1).contains(section->mapRectToItem(surface,QRectF(QPointF(),section->size())));};
        const auto settleDetail=[&]{return QTest::qWaitFor([&]{return !activityTransition->property("moving").toBool();},2000);};
        const auto closeDetail=[&]{QTest::keyClick(window,Qt::Key_Escape);return settleDetail()&&!activityTransition->isVisible();};
        const auto visibleControl=[&](QQuickItem *control){
            return control&&control->isVisible()&&control->isEnabled()&&control->width()>0&&control->height()>0
                &&control->mapToItem(activityScroll,0,0).y()>=-1
                &&control->mapToItem(activityScroll,0,control->height()).y()<=activityScroll->height()+1;
        };
        const auto revealControl=[&](QQuickItem *control){
            if(!control)return false;
            const auto top=control->mapToItem(activityScroll,0,0).y(),bottom=top+control->height();
            auto position=activityScroll->property("contentY").toDouble();
            if(top<0)position+=top-8;else if(bottom>activityScroll->height())position+=bottom-activityScroll->height()+8;
            const auto currentHeight=activityScroll->property("contentHeight").toDouble();
            activityScroll->setProperty("contentY",qBound(0.0,position,qMax(0.0,currentHeight-activityScroll->height())));wait(40);
            return visibleControl(control);
        };
        for(int i=0;i<activityDetailButtons.size();++i){
            auto *entry=findVisual(activity,activityDetailButtons[i]);
            auto *card=findVisual(activity,activityDetailCards[i]);
            // Attached properties require the card's QML import context.
            const auto accessibleRole=card?QQmlProperty::read(card,"Accessible.role",qmlContext(card)):QVariant();
            check("activity-detail-heading-has-full-card-hit-area-"+activityDetailKeys[i],entry&&card
                &&card->isEnabled()&&card->width()>=240&&card->height()>=130&&insideSurface(entry,card)
                &&entry->width()>=60&&accessibleRole.isValid()&&accessibleRole.toInt()==int(QAccessible::Button));
            if(!entry||!card)continue;
            check("activity-detail-heading-is-reachable-"+activityDetailKeys[i],revealControl(entry));
            const auto before=card->mapRectToItem(activity,QRectF(QPointF(),card->size()));
            QTest::mouseClick(window,Qt::LeftButton,Qt::NoModifier,entry->mapToScene(QPointF(entry->width()/2,entry->height()/2)).toPoint());
            const auto origin=activityTransition->property("origin").toRectF();
            check("activity-detail-heading-opens-from-live-card-"+activityDetailKeys[i],activityTransition->property("opened").toBool()
                &&activityTransition->property("detailKey").toString()==activityDetailKeys[i]
                &&qAbs(origin.x()-before.x())<4&&qAbs(origin.y()-before.y())<4
                &&qAbs(origin.width()-before.width())<1&&qAbs(origin.height()-before.height())<1);
            check("activity-detail-heading-settles-and-esc-returns-"+activityDetailKeys[i],settleDetail()&&closeDetail());
        }
        // Keep the original long-policy-name regression, and cover the long
        // node and IPv6 fields sharing its permanently reserved artwork space.
        // Temporary QML Bindings restore each original data binding afterwards.
        struct LongTextCase {const char *name;QString text;int maxLines;};
        const QList<LongTextCase> longTexts={
            {"activityPolicyFactValue",QString::fromUtf8("新加坡实验性 IEPL 专线 — a deliberately long regional policy name that must elide without moving other facts"),1},
            {"activityCurrentNode",QString::fromUtf8("新加坡实验性 IEPL 专线 — a deliberately long regional node name that must remain inside the text region beside the cloud knot"),2},
            {"activityExitIpValue",QStringLiteral("2001:db8:85a3:0000:0000:8a2e:0370:7334"),1}};
        QQmlComponent textBinding(qmlEngine(window));
        textBinding.setData(R"(
            import QtQuick
            Binding {
                required property var targetText
                required property string testText
                target: targetText
                property: "text"
                value: testText
                restoreMode: Binding.RestoreBindingOrValue
            }
        )",QUrl());
        for(const auto &sample:longTexts){
            auto *value=findVisual(activity,QString::fromLatin1(sample.name));
            check(QString::fromLatin1(sample.name)+"-present",value&&statusCard);
            if(!value||!statusCard)continue;
            const auto cardSize=statusCard->size();
            std::unique_ptr<QObject> override(textBinding.createWithInitialProperties(
                {{"targetText",QVariant::fromValue(value)},{"testText",sample.text}},qmlContext(window)));
            check(QString::fromLatin1(sample.name)+"-long-text-fixture-bound",override!=nullptr);
            if(!override)continue;
            wait(80);
            auto *emblem=findVisual(activity,"activityStatusEmblem");
            const auto valueBounds=value->mapRectToItem(statusCard,QRectF(QPointF(),value->size()));
            check(QString::fromLatin1(sample.name)+"-long-text-elides-in-stable-text-region",value->property("truncated").toBool()
                &&value->property("lineCount").toInt()>0&&value->property("lineCount").toInt()<=sample.maxLines
                &&statusCard->size()==cardSize&&value->width()>0&&insideSurface(value,statusCard)
                &&emblem&&valueBounds.right()<=emblem->x()+1);
        }
        QTest::mouseMove(window,QPoint(1,1));
        // Layout proportions describe resting cards; returning from a detail
        // deliberately restores keyboard focus and its visual lift.
        activity->forceActiveFocus(Qt::OtherFocusReason);wait(180);
        bool restingCards=true;
        for(const auto &name:activityDetailCards){
            auto *card=findVisual(activity,name);
            restingCards=restingCards&&card&&!card->property("focused").toBool()
                &&!card->property("hovered").toBool()&&qAbs(card->property("lift").toDouble())<0.01;
        }
        check("activity-layout-samples-five-resting-cards",restingCards);
        const auto diagnosticAt=diagnostic->mapToItem(activity,0,0),trafficAt=trafficCard->mapToItem(activity,0,0);
        const auto sourceAt=sourceCard?sourceCard->mapToItem(activity,0,0):QPointF();
        const auto statusAt=statusCard?statusCard->mapToItem(activity,0,0):QPointF();
        const auto connectionsAt=connectionsSurface?connectionsSurface->mapToItem(activity,0,0):QPointF();
        const auto uploadAt=upload->mapToItem(activity,0,0),totalAt=total->mapToItem(activity,0,0);
        std::function<int(QQuickItem *)> panelCount=[&](QQuickItem *root){
            int count=activityDetailCards.contains(root->objectName())?1:0;
            for(auto *child:root->childItems())count+=panelCount(child);
            return count;
        };
        bool opaque=true;
        for(const auto &name:activityDetailCards){
            auto *card=findVisual(activity,name);
            opaque=opaque&&card&&card->property("color").value<QColor>().alpha()==255;
        }
        check("activity-five-opaque-cards-retain-source-and-transfer-proportions",panelCount(activity)==5&&opaque&&sourceCard&&statusCard&&connectionsSurface
            &&qAbs(statusAt.y()-trafficAt.y())<1&&qAbs(statusCard->height()-trafficCard->height())<1
            &&qAbs(diagnosticAt.y()-sourceAt.y())<1&&sourceAt.y()>=trafficAt.y()+trafficCard->height()
            &&qAbs(sourceAt.y()+sourceCard->height()-connectionsAt.y()-connectionsSurface->height())<1
            &&qAbs(diagnosticAt.x()-connectionsAt.x())<1&&qAbs(diagnostic->width()-connectionsSurface->width())<1
            &&qAbs(statusCard->width()/(statusCard->width()+trafficCard->width())-5.0/12)<0.03
            &&qAbs(sourceCard->width()/(sourceCard->width()+diagnostic->width())-7.0/12)<0.03);
        const QJsonObject normalLayout{{"phase","normal"},
            {"windowWidth",window->width()},{"windowHeight",window->height()},{"panelCount",panelCount(activity)},
            {"contentLogicalWidth",activity->property("contentLogicalWidth").toDouble()},{"cards",cardGeometry()}};
        activityLayoutSamples.append(normalLayout);
        qInfo().noquote()<<"MOTION_ACTIVITY_LAYOUT"<<QJsonDocument(normalLayout).toJson(QJsonDocument::Compact);
        check("activity-detail-data-stays-in-its-own-opaque-reading-card",
            insideSurface(upload,trafficCard)&&insideSurface(total,trafficCard)&&insideSurface(connections,connectionsSurface)
            &&uploadAt.y()>trafficAt.y()&&totalAt.y()>uploadAt.y());
        const double contentHeight=activityScroll->property("contentHeight").toDouble();
        check("activity-apec-normal-viewport-retains-bounded-vertical-reading",window->size()==normalSize&&activity->property("wide").toBool()
            &&contentHeight>0&&activityScroll->property("contentWidth").toDouble()<=activityScroll->width()+1
            &&trafficAt.x()>=0&&diagnosticAt.x()+diagnostic->width()<=activity->width()+1);
        const auto inside=[&](QQuickItem *region){
            if(!region||!region->isVisible()||region->width()<=0||region->height()<=0)return false;
            const auto bounds=region->mapRectToItem(activityScroll,QRectF(QPointF(),region->size()));
            return bounds.left()>=-1&&bounds.top()>=-1&&bounds.right()<=activityScroll->width()+1&&bounds.bottom()<=activityScroll->height()+1;
        };
        for(auto *card:{statusCard,trafficCard}){
            if(!card)continue;
            const auto restingPosition=card->mapToItem(activity,QPointF());
            const auto restingSize=card->size();
            const double restingScroll=activityScroll->property("contentY").toDouble();
            card->forceActiveFocus(Qt::TabFocusReason);wait(180);
            const auto focusedBounds=card->mapRectToItem(activityScroll,QRectF(QPointF(),card->size()));
            check(card->objectName()+"-keyboard-lift-stays-fully-inside-scroll-clip",card->hasActiveFocus()
                &&card->property("focused").toBool()&&card->property("lift").toDouble()<0&&activityScroll->clip()
                &&focusedBounds.left()>=0&&focusedBounds.top()>=0
                &&focusedBounds.right()<=activityScroll->width()&&focusedBounds.bottom()<=activityScroll->height());
            activityLayoutSamples.append(QJsonObject{{"phase","keyboard-focus"},{"card",card->objectName()},
                {"lift",card->property("lift").toDouble()},{"clipLeft",focusedBounds.left()},{"clipTop",focusedBounds.top()},
                {"clipRight",focusedBounds.right()},{"clipBottom",focusedBounds.bottom()},
                {"scrollWidth",activityScroll->width()},{"scrollHeight",activityScroll->height()}});
            activity->forceActiveFocus(Qt::OtherFocusReason);wait(180);
            check(card->objectName()+"-focus-return-preserves-resting-layout-and-scroll",!card->property("focused").toBool()
                &&qAbs(card->property("lift").toDouble())<0.01&&card->size()==restingSize
                &&QLineF(card->mapToItem(activity,QPointF()),restingPosition).length()<0.01
                &&qAbs(activityScroll->property("contentY").toDouble()-restingScroll)<0.01);
        }
        const auto actualRanks=activity->property("ranks");
        // Geometry-only rows stay out of the real telemetry store. The compact
        // overview is bounded; the retained source detail owns the full table.
        eval("pageLoader.item.ranks=Array.from({length:8},(_,i)=>({id:'layout-'+i,name:'Long source name for full-name accessibility verification — regional service '+i,value:'123.4 GiB',upload:'23.4 GiB',download:'100 GiB',kind:'domains'}))");
        for(const auto size:{QSize(760,672),QSize(914,672),QSize(1100,760)}){
            window->resize(qRound(eval(QString("Theme.dp(%1)").arg(size.width())).toDouble()),qRound(eval(QString("Theme.dp(%1)").arg(size.height())).toDouble()));wait(180);
            activityScroll->setProperty("contentY",0);wait(30);
            const bool wide=activity->property("wide").toBool();
            const QJsonObject responsiveLayout{{"phase","responsive"},
                {"requestedWidth",size.width()},{"requestedHeight",size.height()},
                {"windowWidth",window->width()},{"windowHeight",window->height()},{"wide",wide},
                {"scrollWidth",activityScroll->width()},{"scrollHeight",activityScroll->height()},
                {"contentHeight",activityScroll->property("contentHeight").toDouble()},{"cards",cardGeometry()}};
            activityLayoutSamples.append(responsiveLayout);
            qInfo().noquote()<<"MOTION_ACTIVITY_LAYOUT"<<QJsonDocument(responsiveLayout).toJson(QJsonDocument::Compact);
            check("activity-responsive-breakpoint-"+QString::number(size.width()),wide==
                (activity->property("contentLogicalWidth").toDouble()>=activity->property("dualColumnMinimumWidth").toDouble()));
            if(wide){
                check("activity-wide-one-screen-"+QString::number(size.width()),activityScroll->property("contentHeight").toDouble()<=activityScroll->height()+1
                    &&inside(statusCard)&&inside(trafficCard)&&inside(sourceCard)&&inside(diagnostic)&&inside(connectionsSurface));
            }else{
                QList<QQuickItem *> ordered={statusCard,trafficCard,sourceCard,diagnostic,connectionsSurface};
                bool aligned=true;
                for(int i=0;i<ordered.size();++i){
                    if(!ordered[i]){aligned=false;continue;}
                    const auto rect=ordered[i]->mapRectToItem(activity,QRectF(QPointF(),ordered[i]->size()));
                    aligned=aligned&&rect.width()>=240&&rect.left()>=0&&rect.right()<=activity->width()+1;
                    if(i>0&&ordered[i-1]){
                        const auto previous=ordered[i-1]->mapRectToItem(activity,QRectF(QPointF(),ordered[i-1]->size()));
                        aligned=aligned&&rect.top()>previous.bottom()&&qAbs(rect.left()-previous.left())<1&&qAbs(rect.width()-previous.width())<1;
                    }
                }
                check("activity-narrow-scroll-retains-five-ordered-readable-cards-"+QString::number(size.width()),aligned
                    &&activityScroll->property("contentHeight").toDouble()>activityScroll->height()
                    &&revealControl(connectionsSurface));
            }
        }
        auto *sourceList=findVisual(activity,"activitySourceList");
        auto *sourceRow=findVisual(activity,"activitySourceRow-0");
        const auto previewCount=activity->property("previewRows").toInt();
        auto *lastSourceRow=findVisual(activity,"activitySourceRow-"+QString::number(previewCount-1));
        check("long-source-preview-is-bounded-with-all-visible-rows-inside-card",sourceList&&sourceRow&&lastSourceRow
            &&previewCount>=5&&previewCount<=7&&insideSurface(sourceRow,sourceList)&&insideSurface(lastSourceRow,sourceList));
        if(sourceRow){
            sourceRow->forceActiveFocus();wait(80);
            const auto fullName=sourceRow->property("displayName").toString();
            check("source-full-name-available-to-keyboard-users",sourceRow->hasActiveFocus()
                &&fullName.contains("accessibility verification")
                &&QQmlProperty::read(sourceRow,"Accessible.name",qmlContext(sourceRow)).toString().contains(fullName));
        }
        check("source-direct-id-has-readable-name",eval("pageLoader.item.sourceName({kind:'nodes',name:'SWIRL_V2_DIRECT'})==='直连'").toBool());
        if(!output.isEmpty())window->grabWindow().save(QFileInfo(output).absolutePath()+"/activity-long-sources.png");
        activity->setProperty("ranks",actualRanks);
        window->resize(normalSize);wait(180);
        check("activity-apec-filters-remain-reachable",revealControl(trafficFilter)&&visibleControl(trafficFilter)&&revealControl(sourceFilter)&&visibleControl(sourceFilter)&&revealControl(periodFilter)&&visibleControl(periodFilter)&&trafficChart&&trafficChart->isVisible());
        const auto clickSegment=[&](QQuickItem *control,int index,int count){
            const auto point=control->mapToScene(QPointF(control->width()*(index+0.5)/count,control->height()/2)).toPoint();
            QTest::mouseClick(window,Qt::LeftButton,Qt::NoModifier,point);wait(100);
        };
        if(revealControl(trafficFilter)&&visibleControl(trafficFilter)&&trafficChart){
            const auto chooseTrafficScope=[&](int index){
                trafficFilter->forceActiveFocus();
                QTest::mouseClick(window,Qt::LeftButton,Qt::NoModifier,trafficFilter->mapToScene(QPointF(trafficFilter->width()/2,trafficFilter->height()/2)).toPoint());wait(100);
                QTest::keyClick(window,index==0?Qt::Key_Home:Qt::Key_End);
                QTest::keyClick(window,Qt::Key_Return);wait(100);
            };
            chooseTrafficScope(1);
            check("activity-proxy-scope-filters-sources-without-relabeling-total-rate",activity->property("trafficKind").toInt()==1
                &&trafficFilter->property("currentIndex").toInt()==1&&trafficChart->property("series").toString()=="total");
            chooseTrafficScope(0);
            check("activity-all-scope-restores-source-range",activity->property("trafficKind").toInt()==0
                &&trafficFilter->property("currentIndex").toInt()==0&&trafficChart->property("series").toString()=="total");
        }
        if(revealControl(sourceFilter)&&visibleControl(sourceFilter)){
            clickSegment(sourceFilter,1,3);
            check("activity-v7-domain-filter-switches-source",eval("pageLoader.item.rankingKind===1").toBool()&&sourceFilter->property("currentIndex").toInt()==1);
            clickSegment(sourceFilter,2,3);
            check("activity-v7-strategy-filter-switches-source",eval("pageLoader.item.rankingKind===2").toBool()&&sourceFilter->property("currentIndex").toInt()==2);
            clickSegment(sourceFilter,0,3);
            check("activity-v7-source-filter-restores-processes",eval("pageLoader.item.rankingKind===0").toBool()&&sourceFilter->property("currentIndex").toInt()==0);
        }
        if(revealControl(periodFilter)&&visibleControl(periodFilter)){
            clickSegment(periodFilter,1,2);
            check("activity-v7-month-filter-switches-period",eval("pageLoader.item.period===1").toBool()&&periodFilter->property("currentIndex").toInt()==1);
            clickSegment(periodFilter,0,2);
            check("activity-v7-today-filter-restores-period",eval("pageLoader.item.period===0").toBool()&&periodFilter->property("currentIndex").toInt()==0);
        }
        // Policy facts now live in the connection card/detail. Preserve keyboard
        // reachability and spatial continuity through that accepted destination.
        check("activity-policy-fact-is-visible",statusCard&&findVisual(activity,"activityPolicyFactValue")&&revealControl(statusCard));
        if(statusCard){
            const auto before=statusCard->mapRectToItem(activity,QRectF(QPointF(),statusCard->size()));
            statusCard->forceActiveFocus(Qt::TabFocusReason);
            QTest::keyClick(window,Qt::Key_Space);wait(85);
            const auto origin=activityTransition->property("origin").toRectF();
            check("activity-policy-detail-keyboard-entry-follows-card-transition",activityTransition->property("detailKey").toString()=="connection"
                &&activityTransition->property("moving").toBool()&&activityTransition->property("progress").toDouble()>0
                &&activityTransition->property("progress").toDouble()<1
                &&qAbs(origin.x()-before.x())<4&&qAbs(origin.y()-before.y())<4);
            check("activity-policy-detail-return-restores-page-and-focus",settleDetail()&&closeDetail()
                &&item()==activity&&statusCard->hasActiveFocus());
        }
        window->resize(originalSize);wait(250);
    }
    const double activityScrollBefore=activityScroll?qMax(0.0,qMin(20.0,activityScroll->property("contentHeight").toDouble()-activityScroll->height())):0.0;
    if(activityScroll)activityScroll->setProperty("contentY",activityScrollBefore);
    if(trafficCard&&activityTransition&&activitySurface&&activityScroll){
        // This is the actual activity entry: the whole transfer card expands
        // locally. The old numerical upload label is now plain reading text.
        auto *entry=findVisual(activity,"activityTrafficDetails");
        check("activity-transfer-entry-is-present",entry&&entry->isVisible()&&entry->isEnabled());
        if(entry){
            const auto cardOrigin=trafficCard->mapRectToItem(activity,QRectF(QPointF(),trafficCard->size()));
            QTest::mouseClick(window,Qt::LeftButton,Qt::NoModifier,entry->mapToScene(QPointF(entry->width()/2,entry->height()/2)).toPoint());
            wait(35);
            const auto origin=activityTransition->property("origin").toRectF();
            check("activity-transfer-click-expands-its-own-live-surface",item()==activity
                &&activityTransition->property("sourceCard").value<QObject *>()==trafficCard
                &&activityTransition->property("detailKey").toString()=="traffic"&&activityTransition->property("opened").toBool()
                &&qAbs(origin.x()-cardOrigin.x())<4&&qAbs(origin.y()-cardOrigin.y())<4
                &&qAbs(origin.width()-cardOrigin.width())<1&&qAbs(origin.height()-cardOrigin.height())<1);
            const auto partial=activityTransition->property("progress").toDouble();
            const bool openedBeforeReverse=activityTransition->property("opened").toBool();
            const bool movingBeforeReverse=activityTransition->property("moving").toBool();
            const auto beforeReverse=activitySurface->mapRectToItem(activity,QRectF(QPointF(),activitySurface->size()));
            // QTest::keyClick processes events after both press and release,
            // so its two outer samples may include a normal animation tick.
            // Send the real window key event synchronously to measure only
            // the reversal handler, including the global Escape filter.
            QKeyEvent escapePress(QEvent::KeyPress,Qt::Key_Escape,Qt::NoModifier);
            escapePress.setAccepted(false);
            QElapsedTimer escapeDispatch;escapeDispatch.start();
            const bool escapeDelivered=QCoreApplication::sendEvent(window,&escapePress);
            const double escapeDispatchMs=escapeDispatch.nsecsElapsed()/1000000.0;
            const auto afterReverse=activitySurface->mapRectToItem(activity,QRectF(QPointF(),activitySurface->size()));
            const double progressAfterReverse=activityTransition->property("progress").toDouble();
            const bool openedAfterReverse=activityTransition->property("opened").toBool();
            const bool movingAfterReverse=activityTransition->property("moving").toBool();
            check("activity-transfer-escape-preserves-the-in-flight-geometry",partial>0&&partial<1
                &&!activityTransition->property("opened").toBool()&&activityTransition->property("moving").toBool()
                &&QLineF(beforeReverse.topLeft(),afterReverse.topLeft()).length()<.01
                &&qAbs(beforeReverse.width()-afterReverse.width())<.01&&qAbs(beforeReverse.height()-afterReverse.height())<.01);
            QKeyEvent escapeRelease(QEvent::KeyRelease,Qt::Key_Escape,Qt::NoModifier);
            escapeRelease.setAccepted(false);
            const bool escapeReleaseDelivered=QCoreApplication::sendEvent(window,&escapeRelease);
            wait(25);
            check("activity-transfer-escape-reverses-live-progress",activityTransition->property("progress").toDouble()<partial
                &&activityTransition->property("progress").toDouble()>0&&activityTransition->property("moving").toBool());
            check("activity-transfer-return-restores-scroll-and-focus",QTest::qWaitFor([&]{return !activityTransition->property("moving").toBool();},2000)
                &&item()==activity&&!activityTransition->isVisible()&&trafficCard->hasActiveFocus()
                &&qAbs(activityScroll->property("contentY").toDouble()-activityScrollBefore)<1);
            check("activity-transfer-escape-key-press-is-accepted",escapeDelivered&&escapePress.isAccepted());
            const auto rectangle=[](const QRectF &value){return QJsonObject{{"x",value.x()},{"y",value.y()},{"width",value.width()},{"height",value.height()}};};
            activityEscapeContinuity={{"before",rectangle(beforeReverse)},{"after",rectangle(afterReverse)},
                {"progressBefore",partial},{"progressAfter",progressAfterReverse},
                {"openedBefore",openedBeforeReverse},{"openedAfter",openedAfterReverse},
                {"movingBefore",movingBeforeReverse},{"movingAfter",movingAfterReverse},
                {"topLeftDistance",QLineF(beforeReverse.topLeft(),afterReverse.topLeft()).length()},
                {"widthDifference",afterReverse.width()-beforeReverse.width()},{"heightDifference",afterReverse.height()-beforeReverse.height()},
                {"dispatchMs",escapeDispatchMs},{"sendEventReturned",escapeDelivered},{"sendEventAccepted",escapePress.isAccepted()},
                {"releaseSendEventReturned",escapeReleaseDelivered},{"releaseAccepted",escapeRelease.isAccepted()},
                {"method","Geometry sampled in one GUI call stack across synchronous Escape KeyPress delivery to the actual QQuickWindow and its event filters; the paired KeyRelease follows the geometry sample."}};
            qInfo().noquote()<<"MOTION_ACTIVITY_ESCAPE_CONTINUITY"<<QJsonDocument(activityEscapeContinuity).toJson(QJsonDocument::Compact);
        }
    }
    if(upload&&activity){
        // Retain the separate SwirlPageHost rapid return/reopen regression with
        // a real production surface/title component. It is a component fixture,
        // not an activity-page affordance, and displays the real upload value.
        QQmlComponent metricComponent(qmlEngine(window));
        metricComponent.setData(R"(
            import QtQuick
            import SwirlQuick
            SwirlGlassPanel {
                required property Item valueSource
                readonly property Item motionTitle: metricText
                x: Theme.pagePadding; y: Theme.dp(52)
                width: Theme.dp(240); height: Theme.dp(130); z: 100
                SwirlText {
                    id: metricText
                    anchors.fill: parent; anchors.margins: Theme.cardPadding
                    text: valueSource.text
                    font.pixelSize: valueSource.font.pixelSize
                    color: Theme.text
                }
            }
        )",QUrl("qrc:/qt/qml/SwirlQuick/MotionSharedMetricFixture.qml"));
        std::unique_ptr<QQuickItem> metric(qobject_cast<QQuickItem *>(metricComponent.createWithInitialProperties(
            {{"valueSource",QVariant::fromValue(upload)}},qmlContext(window))));
        check("shared-metric-production-surface-fixture-created",metric!=nullptr);
        if(!metric)qWarning()<<metricComponent.errors();
        if(metric){
            metric->setParentItem(activity);wait(25);
            qmlEngine(window)->rootContext()->setContextProperty("motionTestOrigin",metric.get());
            eval("SwirlMotion.navigateFrom(motionTestOrigin,'traffic','uploadRate')");
            QElapsedTimer metricReady;metricReady.start();
            while(host->property("sourceSurface").value<QObject *>()!=metric.get()&&metricReady.elapsed()<1500)wait(5);
            wait(35);
            check("metric-shares-matching-surface",host->property("heroData").isValid() && host->property("sourceSurface").value<QObject *>()==metric.get()
                &&host->property("surfaceKind").toString()=="uploadRate");
            const auto partial=host->property("progress").toDouble();
            eval("SwirlMotion.returnToHub(null)");wait(25);
            check("immediate-return-reverses-live-transition",item()==activity && partial>0 && partial<1 && host->property("moving").toBool());
            eval("SwirlMotion.navigateFrom(motionTestOrigin,'traffic','uploadRate')");wait(25);
            check("reopen-keeps-latest-route",eval("AppState.currentPage==='traffic'").toBool());
            settle();eval("SwirlMotion.returnToHub(null)");wait(25);settle();
            check("activity-return-preserves-scroll",item()==activity&&activityScroll&&qAbs(activityScroll->property("contentY").toDouble()-activityScrollBefore)<1);
            check("shared-surfaces-restored",!metric->property("surfaceHidden").toBool()&&host->property("sourceSurface").value<QObject *>()==nullptr);
            eval("SwirlMotion.shared=null;SwirlMotion.returnShared=null");
            qmlEngine(window)->rootContext()->setContextProperty("motionTestOrigin",QVariant::fromValue<QObject *>(nullptr));
        }
    }
    route("activity");
    auto *capsule=findVisual(window->contentItem(),"proxyCapsule");
    if(capsule){
        const auto hostProxyBefore=SystemProxySession::snapshot();
        QQmlComponent component(qmlEngine(window));
        component.setData(R"(
            import QtQuick
            QtObject {
                property bool busy: false
                property bool systemProxyBusy: false
                property bool proxyRequested: false
                property bool processAlive: false
                property bool systemProxyStopping: false
                property bool policyBusy: false
                property string routingError: ""
                property string policyError: ""
                property string error: ""
                property string errorCode: "None"
                property int calls: 0
                property bool reject: false
                property bool originalSystemEnabled: false
                property QtObject imports: QtObject { property bool busy: false }
                property QtObject systemProxy: QtObject {
                    property bool systemEnabled: false
                    property bool enabled: false
                    property bool owned: false
                    property string stateReadError: ""
                    property string error: ""
                }
                function toggleSystemProxy() {
                    calls++
                    if(reject) { routingError="test-operation-failed"; return }
                    const requested = !(proxyRequested || systemProxy.owned || processAlive || busy)
                    if(requested) originalSystemEnabled=systemProxy.systemEnabled
                    proxyRequested=requested;processAlive=requested;busy=false;systemProxyBusy=false
                    systemProxy.owned=requested;systemProxy.enabled=requested
                    systemProxy.systemEnabled=requested ? true : originalSystemEnabled
                }
            }
        )",QUrl());
        std::unique_ptr<QObject> fake(component.create());
        check("proxy-toggle-test-controller-created",fake!=nullptr);
        if(fake){
            const auto originalController=capsule->property("controller");
            check("proxy-toggle-test-controller-bound",capsule->setProperty("controller",QVariant::fromValue(fake.get())));
            const auto clickProxy=[&]{QTest::mouseClick(window,Qt::LeftButton,Qt::NoModifier,capsule->mapToScene(QPointF(capsule->width()/2,capsule->height()/2)).toPoint());wait(30);};
            auto *fakeProxy=fake->property("systemProxy").value<QObject *>();
            check("proxy-toggle-test-state-present",fakeProxy!=nullptr);
            const auto proxyState=[&](bool enabled,bool owned,bool systemEnabled,const QString &tone,const QString &phase,const QString &detailToken){
                const auto label=capsule->property("label").toString(),detail=capsule->property("detail").toString();
                const auto accessibleName=QQmlProperty::read(capsule,QStringLiteral("Accessible.name"),qmlContext(capsule));
                const auto accessibleDescription=QQmlProperty::read(capsule,QStringLiteral("Accessible.description"),qmlContext(capsule));
                // Qt Accessible names reflect the visible label; descriptions
                // retain the complete state and action detail without repetition.
                return fakeProxy&&fakeProxy->property("systemEnabled").toBool()==systemEnabled
                    &&fakeProxy->property("owned").toBool()==owned&&fakeProxy->property("enabled").toBool()==owned
                    &&capsule->isEnabled()&&label==QStringLiteral("系统代理")
                    &&capsule->property("proxyEnabled").toBool()==enabled&&capsule->property("proxyOwned").toBool()==owned
                    &&capsule->property("tone").toString()==tone&&capsule->property("activityPhase").toString()==phase
                    &&detail.contains(detailToken)
                    &&accessibleDescription.isValid()&&accessibleDescription.toString()==detail
                    &&accessibleName.isValid()&&accessibleName.toString()==label;
            };
            check("proxy-off-offers-enable",proxyState(false,false,false,"neutral","idle",QStringLiteral("点击启动已保存策略")));
            clickProxy();
            check("proxy-enable-click-dispatches-once",fake->property("calls").toInt()==1);
            check("proxy-on-offers-disable",proxyState(true,true,true,"success","succeeded",QStringLiteral("点击恢复原设置并停止内核")));
            check("proxy-enable-stays-on-activity",eval("AppState.currentPage==='activity'").toBool());
            clickProxy();
            check("proxy-disable-click-dispatches-once",fake->property("calls").toInt()==2);
            check("proxy-disabled-state-updates-action",proxyState(false,false,false,"neutral","idle",QStringLiteral("点击启动已保存策略")));
            fake->setProperty("proxyRequested",true);fake->setProperty("busy",true);fake->setProperty("systemProxyBusy",true);clickProxy();
            check("proxy-pending-request-can-be-cancelled",fake->property("calls").toInt()==3&&!fake->property("proxyRequested").toBool()&&!fake->property("busy").toBool());
            fake->setProperty("systemProxyStopping",true);clickProxy();
            check("proxy-stopping-cannot-repeat-request",fake->property("calls").toInt()==3&&!capsule->isEnabled());
            fake->setProperty("systemProxyStopping",false);
            if(fakeProxy)fakeProxy->setProperty("systemEnabled",true);
            check("external-proxy-does-not-claim-swirl-is-running",proxyState(false,false,true,"neutral","idle",QStringLiteral("其他应用的系统代理已开启")));
            clickProxy();clickProxy();
            check("master-off-restores-external-proxy-state",fake->property("calls").toInt()==5&&proxyState(false,false,true,"neutral","idle",QStringLiteral("其他应用的系统代理已开启")));
            fake->setProperty("processAlive",true);
            check("running-core-without-owned-proxy-stays-neutral",proxyState(true,false,true,"neutral","idle",QStringLiteral("内核正在运行")));
            fake->setProperty("processAlive",false);
            if(fakeProxy)fakeProxy->setProperty("error",QStringLiteral("stale-owner-error"));
            fake->setProperty("reject",true);clickProxy();
            check("proxy-failure-keeps-observed-state",fake->property("calls").toInt()==6&&proxyState(false,false,true,"warning","failed",QStringLiteral("test-operation-failed")));
            check("proxy-failure-visible",capsule->property("tone").toString()=="warning"&&capsule->property("detail").toString()=="test-operation-failed");
            check("proxy-disable-and-error-stay-on-activity",eval("AppState.currentPage==='activity'").toBool());
            check("proxy-toggle-controller-restored",capsule->setProperty("controller",originalController));
        }
        check("proxy-button-test-does-not-mutate-host-settings",SystemProxySession::snapshot()==hostProxyBefore);
    }
    QList<double> intervals;QList<double> warmIntervals;
    QJsonArray frameTimeline;
    QJsonObject frameProbe;
    const QStringList stress={"overview","settings","proxies","featurehub","capture","connections","rules","logs"};
    {
        struct FrameContext {
            QString route,activeRoute,phase,point;
            qint64 timestampNs=0;
            quint64 revision=0;
            bool moving=false,pending=false,valid=false;
        };
        struct FrameSample {
            qint64 timestampNs=0;
            double intervalMs=0;
            bool hasInterval=false,warm=false;
            FrameContext before,after;
        };
        constexpr qsizetype frameCapacity=20000;
        struct FrameProbeState {
            QMutex mutex;
            QElapsedTimer clock;
            QList<double> intervals,warmIntervals;
            QList<FrameSample> samples;
            FrameContext context,previousContext;
            bool warmPhase=false,measuring=true;
            qint64 last=0,callbackCount=0,droppedSamples=0,snapshotCount=0;
            qint64 callbackTotalNs=0,callbackMaxNs=0,snapshotTotalNs=0,snapshotMaxNs=0,maxSnapshotAgeNs=0;
        };
        const auto state=std::make_shared<FrameProbeState>();
        state->samples.reserve(frameCapacity);state->clock.start();
        QString phase=QStringLiteral("rapid-switch");
        // Context ownership keeps queued GUI callbacks from outliving the
        // stack state. Only this GUI callback reads QML; the render callback
        // consumes native state. An in-flight DirectConnection retains that
        // state even if disconnect returns before the callback has finished.
        auto captureContext=[state,host,window,&phase](const QString &point){
            Q_ASSERT(QThread::currentThread()==window->thread());
            const qint64 started=state->clock.nsecsElapsed();
            {QMutexLocker lock(&state->mutex);if(!state->measuring)return;}
            FrameContext next;
            next.route=host->property("routeKey").toString();
            if(auto *active=qvariant_cast<QObject *>(host->property("activeLoader")))next.activeRoute=active->property("routeId").toString();
            next.moving=host->property("moving").toBool();next.pending=host->property("pendingGrab").toBool();
            next.phase=phase;next.point=point;next.valid=true;next.timestampNs=state->clock.nsecsElapsed();
            QMutexLocker lock(&state->mutex);
            if(!state->measuring)return;
            next.revision=++state->snapshotCount;state->context=next;
            const qint64 cost=state->clock.nsecsElapsed()-started;
            state->snapshotTotalNs+=cost;state->snapshotMaxNs=qMax(state->snapshotMaxNs,cost);
        };
        QObject probeContext;
        captureContext(QStringLiteral("phase-start"));
        const auto beforeFrame=QObject::connect(window,&QQuickWindow::afterAnimating,&probeContext,[&]{captureContext(QStringLiteral("afterAnimating"));});
        const auto afterFrame=QObject::connect(window,&QQuickWindow::frameSwapped,&probeContext,[&]{captureContext(QStringLiteral("after-frame-queued"));},Qt::QueuedConnection);
        const auto connection=QObject::connect(window,&QQuickWindow::frameSwapped,&probeContext,[state] {
            const qint64 now=state->clock.nsecsElapsed();
            QMutexLocker lock(&state->mutex);
            if(!state->measuring)return;
            const double delta=double(now-state->last)/1000000.0;
            if(state->last){state->intervals<<delta;if(state->warmPhase)state->warmIntervals<<delta;}
            if(state->samples.size()<frameCapacity)state->samples.append({now,delta,state->last!=0,state->warmPhase,state->previousContext,state->context});
            else ++state->droppedSamples;
            state->previousContext=state->context;state->last=now;++state->callbackCount;
            if(state->context.valid)state->maxSnapshotAgeNs=qMax(state->maxSnapshotAgeNs,now-state->context.timestampNs);
            const qint64 cost=state->clock.nsecsElapsed()-now;
            state->callbackTotalNs+=cost;state->callbackMaxNs=qMax(state->callbackMaxNs,cost);
        },Qt::DirectConnection);
        for(int i=0;i<40;++i) {
            eval("AppState.navigate('"+stress[i%stress.size()]+"')");
            captureContext(QStringLiteral("route-request"));
            wait(23);
            if(i%7==0){window->resize(900+i*2,qMax(window->minimumHeight(),650+i));captureContext(QStringLiteral("resize-request"));}
            check("rapid-switch-has-live-page-"+QString::number(i),item()!=nullptr);
            check("rapid-switch-retains-visible-content-"+QString::number(i),eval("Object.keys(pageLoader.pages).reduce((sum,key)=>sum+(pageLoader.pages[key].visible?pageLoader.pages[key].opacity:0),0)>0.99").toBool());
        }
        check("rapid-switch-settles",settle(3500));
        check("latest-route-wins",qvariant_cast<QObject *>(host->property("activeLoader"))->property("routeId").toString()==stress[39%stress.size()]);
        // Preserve the original aggregate's warm reset and full interval set.
        window->resize(1100,760);
        phase=QStringLiteral("warm-route");
        {QMutexLocker lock(&state->mutex);state->warmPhase=true;state->last=0;state->previousContext=FrameContext{};}
        captureContext(QStringLiteral("phase-start"));
        for(int i=0;i<8;++i)route(stress[i]);
        QList<FrameSample> samples;
        {
            QMutexLocker lock(&state->mutex);
            state->measuring=false;
            intervals=state->intervals;warmIntervals=state->warmIntervals;samples=state->samples;
            frameProbe=QJsonObject{{"schema",1},{"capacity",qint64(frameCapacity)},{"samples",qint64(samples.size())},
                {"droppedSamples",state->droppedSamples},{"frameCallbacks",state->callbackCount},{"guiSnapshots",state->snapshotCount},
                {"callbackMeasuredTotalMs",double(state->callbackTotalNs)/1e6},{"callbackMeasuredMaxMs",double(state->callbackMaxNs)/1e6},
                {"guiSnapshotMeasuredTotalMs",double(state->snapshotTotalNs)/1e6},{"guiSnapshotMeasuredMaxMs",double(state->snapshotMaxNs)/1e6},
                {"maxSnapshotAgeMs",double(state->maxSnapshotAgeNs)/1e6},{"renderCallbackReadsQml",false},
                {"clockDomain","QElapsedTimer nanoseconds since stress probe start; not synchronized to QML trace clock"},
                {"attributionIsExact",false},{"limits",QJsonArray{
                    "Moving/pending are GUI snapshots around presentation, not complete activity histories between frames.",
                    "Inactive endpoints can hide work between snapshots; active endpoints do not prove every millisecond was animated.",
                    "Queued post-frame snapshots can lag; snapshot timestamps and revisions are retained.",
                    "Probe costs include snapshot reads, copies, list appends and mutex waits, but exclude Qt dispatch and final unlock.",
                    "The additional probe changes test overhead; compare matching instrumentation and workloads.",
                    "All original aggregate intervals, including long or inactive gaps, remain in performance totals."}}};
        }
        QObject::disconnect(connection);QObject::disconnect(beforeFrame);QObject::disconnect(afterFrame);
        const auto contextJson=[](const FrameContext &value){return QJsonObject{
            {"valid",value.valid},{"snapshotNs",value.timestampNs},{"revision",qint64(value.revision)},
            {"route",value.route},{"activeRoute",value.activeRoute},{"phase",value.phase},
            {"snapshotPoint",value.point},{"moving",value.moving},{"pending",value.pending}};};
        // JSON allocation and sorting occur after the timed probe is stopped.
        for(const auto &sample:samples){
            const bool beforeActive=sample.before.moving||sample.before.pending;
            const bool afterActive=sample.after.moving||sample.after.pending;
            const QString attribution=!sample.hasInterval||!sample.before.valid||!sample.after.valid?QStringLiteral("unclassified")
                :beforeActive&&afterActive?QStringLiteral("active-at-both-snapshots")
                :!beforeActive&&!afterActive?QStringLiteral("inactive-at-both-snapshots"):QStringLiteral("transition-boundary");
            frameTimeline.append(QJsonObject{{"timestampNs",sample.timestampNs},
                {"intervalMs",sample.hasInterval?QJsonValue(sample.intervalMs):QJsonValue(QJsonValue::Null)},
                {"warm",sample.warm},{"attribution",attribution},
                {"before",contextJson(sample.before)},{"after",contextJson(sample.after)}});
        }
    }
    // Warm the readback/driver pool at the same dimensions before checking
    // repeated growth. The earlier stress deliberately used varied sizes.
    for(int i=0;i<40;++i){eval("AppState.navigate('"+stress[i%stress.size()]+"')");wait(12);}
    settle(3500);
    qmlEngine(window)->collectGarbage();wait(150);
    auto before=memory();const int count=host->property("cachedPageCount").toInt();
    for(int i=0;i<40;++i){eval("AppState.navigate('"+stress[i%stress.size()]+"')");wait(12);}
    settle(3500);
    check("revisits-do-not-create-loaders",count>=stress.size() && host->property("cachedPageCount").toInt()==count);
    qmlEngine(window)->collectGarbage();wait(150);
    const auto growth=memory()-before;
    check("all-transient-grabs-released",eval("motionPolicy.activeGrabCount===0").toBool());
    check("revisit-memory-growth-below-24MiB",growth<24*1024*1024);
    route("featurehub");
    auto *card=findVisual(qobject_cast<QQuickItem *>(item()),"settings-dns");check("settings-tile-present",card!=nullptr);
    if(card){QTest::mouseClick(window,Qt::LeftButton,Qt::NoModifier,card->mapToScene(QPointF(card->width()/2,card->height()/2)).toPoint());settle(2000);
        check("settings-tile-opens-main-route",eval("AppState.currentPage==='dns' && pageLoader.item.Window.window===window").toBool());
        eval("window.closeSettings()");settle(2000);
        check("main-route-preserves-hub",item()==hub);window->requestActivate();
    }
    route("feature-system");
    auto *module=item();
    if(module) {
        QVariantList rows{QVariantMap{{"name","A"},{"value","1"}},QVariantMap{{"name","B"},{"value","2"}}};
        module->setProperty("records",rows);module->setProperty("tab",1);wait(250);
        auto *list=findVisual(qobject_cast<QQuickItem *>(module),"motion-record-list");
        check("incremental-record-insert",list && list->property("count").toInt()==2);
        std::reverse(rows.begin(),rows.end());module->setProperty("records",rows);wait(250);
        QQmlExpression order(qmlContext(list),list,"model.get(0).entry.name");
        check("incremental-record-reorder",list && list->property("count").toInt()==2 && order.evaluate().toString()=="B");
        rows.removeLast();module->setProperty("records",rows);wait(250);
        check("incremental-record-remove",list && list->property("count").toInt()==1);
    }
    eval("Theme.reduceMotion=true");
    route("settings");
    check("reduced-motion-immediate",!host->property("moving").toBool()&&host->property("progress").toDouble()==1);
    check("reduced-motion-no-global-transition",!eval("SwirlMotion.transitioning").toBool());
    eval("Theme.reduceMotion=false");
    policy->setSystemReducedMotionOverrideForTest(1);
    eval("Theme.followSystemMotion=false");
    check("application-full-motion-remains-enabled-with-reduced-system-policy",!eval("SwirlMotion.reduced").toBool()&&eval("SwirlMotion.expandDuration>0").toBool());
    eval("Theme.followSystemMotion=true");
    route("rules");
    check("system-reduced-motion-immediate",eval("SwirlMotion.reduced").toBool()&&!host->property("moving").toBool()&&host->property("progress").toDouble()==1);
    check("system-reduced-motion-no-global-transition",!eval("SwirlMotion.transitioning").toBool());
    eval("Theme.followSystemMotion=false");
    policy->setSystemReducedMotionOverrideForTest(0);
    eval("Theme.reduceMotion=true");
    check("application-reduced-motion-wins-over-animated-system-policy",eval("SwirlMotion.reduced").toBool());
    int idleFrames=0;
    auto idleConnection=QObject::connect(window,&QQuickWindow::frameSwapped,window,[&]{++idleFrames;});
    wait(650);QObject::disconnect(idleConnection);
    check("idle-no-animation-loop",idleFrames<=4);
    policy->setSystemReducedMotionOverrideForTest(-1);
    const bool systemPolicyRestored=policy->systemReducedMotion()==nativeSystemReducedMotion;
    check("system-motion-policy-restored",systemPolicyRestored);
    std::sort(intervals.begin(),intervals.end());
    std::sort(warmIntervals.begin(),warmIntervals.end());
    QJsonObject performance{{"renderer",int(window->rendererInterface()->graphicsApi())},
        {"qt",qVersion()},{"dpr",window->devicePixelRatio()},
        {"refreshHz",window->screen()?window->screen()->refreshRate():0},
        {"systemReducedMotion",nativeSystemReducedMotion},{"testSystemReducedMotionOverride",0},
        {"effectiveReducedMotionDuringAnimatedChecks",reduced},{"injectedSystemReducedPathTested",true},
        {"systemPolicyRestoreOnReturn",-1},{"systemPolicyRestored",systemPolicyRestored},{"frames",intervals.size()},
        {"medianFrameMs",intervals.isEmpty()?0:intervals[intervals.size()/2]},
        {"p95FrameMs",intervals.isEmpty()?0:intervals[qMin(intervals.size()-1,qsizetype(intervals.size()*0.95))]},
        {"p99FrameMs",intervals.isEmpty()?0:intervals[qMin(intervals.size()-1,qsizetype(intervals.size()*0.99))]},
        {"over60HzBudget",int(std::count_if(intervals.begin(),intervals.end(),[](double ms){return ms>1000.0/60;}))},
        {"over120HzBudget",int(std::count_if(intervals.begin(),intervals.end(),[](double ms){return ms>1000.0/120;}))},
        {"longFramesOver50Ms",int(std::count_if(intervals.begin(),intervals.end(),[](double ms){return ms>50;}))},
        {"warmFrames",warmIntervals.size()},
        {"warmMedianFrameMs",warmIntervals.isEmpty()?0:warmIntervals[warmIntervals.size()/2]},
        {"warmP95FrameMs",warmIntervals.isEmpty()?0:warmIntervals[qMin(warmIntervals.size()-1,qsizetype(warmIntervals.size()*0.95))]},
        {"complexMotion",eval("motionPolicy.complexMotion").toBool()},
        {"activeGrabs",eval("motionPolicy.activeGrabCount").toInt()},
        {"cachedPages",host->property("cachedPageCount").toInt()},
        {"memoryBytes",memory()},{"revisitGrowthBytes",growth},{"idleFrames",idleFrames}};
    QJsonObject report{{"checks",checks},{"failures",failures},{"performance",performance},
        {"frameTimeline",frameTimeline},{"frameProbe",frameProbe},{"activityLayout",activityLayoutSamples},{"activityEscapeContinuity",activityEscapeContinuity},
        {"diagnostics",QJsonDocument::fromJson(eval("JSON.stringify(systemProvider.logs())").toString().toUtf8()).array()}};
    if(!output.isEmpty()) {
        QDir().mkpath(QFileInfo(output).absolutePath());QFile file(output);
        if(!file.open(QIODevice::WriteOnly))return 1;
        file.write(QJsonDocument(report).toJson());
    }
    qInfo()<<"MOTION_RESULT"<<failures<<performance;
    return failures?1:0;
}
