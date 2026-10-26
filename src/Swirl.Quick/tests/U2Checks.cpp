#include <QQuickWindow>
#include <QQuickItem>
#include <QQmlExpression>
#include <QQmlContext>
#include <QJSValue>
#include <QTest>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QFile>
#include <QFileInfo>
#include <QDir>
#include <QElapsedTimer>
#include <QTimer>
#include <QEventLoop>
#include <QMutex>
#include <QMutexLocker>
#include <algorithm>
#include <functional>
#include <memory>
#include "app/NodeViewModel.h"
#ifdef Q_OS_WIN
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <psapi.h>
#endif

int runU2Checks(QQuickWindow *window, const QString &output) {
    QJsonArray checks, samples;
    int failures=0;
    const QString phase=qEnvironmentVariable("SWIRL_U2_CHECKS");
    const auto eval=[&](const QString &code){QQmlExpression e(qmlContext(window),window,code);auto value=e.evaluate();if(e.hasError()){qWarning()<<e.error();++failures;}return value;};
    const auto check=[&](const QString &name,bool passed){checks.append(QJsonObject{{"name",name},{"passed",passed}});if(!passed)++failures;};
    const auto wait=[](int ms){QEventLoop loop;QTimer::singleShot(ms,&loop,&QEventLoop::quit);loop.exec();};
    const auto sample=[&](const QString &name){
        QJsonObject row{{"scenario",name},{"objects",window->findChildren<QObject *>().size()},{"cachedPages",eval("pageLoader.cachedPageCount").toInt()}};
#ifdef Q_OS_WIN
        PROCESS_MEMORY_COUNTERS_EX m{};m.cb=sizeof(m);
        if(GetProcessMemoryInfo(GetCurrentProcess(),reinterpret_cast<PROCESS_MEMORY_COUNTERS *>(&m),sizeof(m))){row["workingSetBytes"]=double(m.WorkingSetSize);row["privateBytes"]=double(m.PrivateUsage);}
        FILETIME created,exited,kernel,user;
        if(GetProcessTimes(GetCurrentProcess(),&created,&exited,&kernel,&user))row["cpuMilliseconds"]=double((quint64(kernel.dwHighDateTime)<<32|kernel.dwLowDateTime)+(quint64(user.dwHighDateTime)<<32|user.dwLowDateTime))/10000.0;
#endif
        samples.append(row);
    };
    const auto navigate=[&](const QString &route){eval("AppState.navigate('"+route+"')");QElapsedTimer t;t.start();wait(25);while(eval("pageLoader.pendingGrab || pageLoader.moving || !pageLoader.item || !pageLoader.activeLoader || pageLoader.activeLoader.routeId!==pageLoader.routeKey").toBool()&&t.elapsed()<5000)wait(10);check("loaded-"+route,t.elapsed()<5000);};
    window->requestActivate();wait(250);
    const QSize initial=window->size();
    const double sidebar=eval("window.actualSidebarWidth").toDouble();
    sample("cold");
    if(phase=="subscription"){
        const auto expectedDprVariable=qEnvironmentVariableIsSet("SWIRL_EXPECTED_DPR")?"SWIRL_EXPECTED_DPR":"QT_SCALE_FACTOR";
        bool expectedDprOk=false;const double expectedDpr=qEnvironmentVariable(expectedDprVariable).toDouble(&expectedDprOk);
        check("requested-dpi-scale-is-effective",expectedDprOk&&expectedDpr>0&&qAbs(window->devicePixelRatio()-expectedDpr)<0.02);
        double lastFormatOptionLabelContentHeight=-1,lastFormatOptionLabelHeight=-1,lastFormatOptionRowHeight=-1;
        std::function<QQuickItem *(QQuickItem *,const QString &)> find=[&](QQuickItem *parent,const QString &name)->QQuickItem *{if(parent->objectName()==name)return parent;for(auto *child:parent->childItems())if(auto *found=find(child,name))return found;return nullptr;};
        const auto item=[&](const QString &name){return find(window->contentItem(),name);};
        const auto click=[&](const QString &name){auto *target=item(name);check("input-"+name,target&&target->isVisible()&&target->isEnabled());if(target)QTest::mouseClick(window,Qt::LeftButton,Qt::NoModifier,target->mapToScene(QPointF(target->width()/2,target->height()/2)).toPoint());wait(250);};
        navigate("subscriptions");click("addSubscription");
        auto *dialog=window->findChild<QObject *>("subscriptionDialog");
        auto *automatic=item("subscriptionAutomaticImport"),*format=item("subscriptionFormat"),*form=item("subscriptionFormViewport"),*name=item("subscriptionName");
        auto *body=item("subscriptionFormBody"),*save=item("saveSubscription");
        check("subscription-form-mounted",dialog&&automatic&&format&&form&&name&&body&&save);
        if(dialog&&automatic&&format&&form&&name&&body&&save){
            check("subscription-import-is-automatic",!item("subscriptionImportScope")&&automatic->property("text").toString().contains(QString::fromUtf8("自动识别")));
            check("format-has-seven-distinct-choices",format->property("count").toInt()==7&&format->property("currentText").toString()==QString::fromUtf8("自动"));
            const auto visibleIn=[&](QQuickItem *field,QQuickItem *viewport){const QRectF outer(viewport->mapToScene(QPointF()),viewport->size());return outer.adjusted(-1,-1,1,1).contains(QRectF(field->mapToScene(QPointF()),field->size()));};
            check("first-input-visible-on-open",visibleIn(name,form));
            check("dialog-footer-inside-window",QRectF(0,0,window->width(),window->height()).contains(QRectF(save->mapToScene(QPointF()),save->size())));
            click("subscriptionAdvanced");
            check("advanced-format-is-visible",format->isVisible());
            format->forceActiveFocus();wait(150);
            check("focused-format-scrolls-fully-into-view",visibleIn(format,form));
            auto *popup=format->property("popup").value<QObject *>();
            if(popup){
                QMetaObject::invokeMethod(popup,"open");wait(250);
                const QRectF popupRect(popup->property("x").toReal(),popup->property("y").toReal(),popup->property("width").toReal(),popup->property("height").toReal());
                check("format-popup-clamped-to-window",popup->property("visible").toBool()&&popupRect.height()>0&&QRectF(0,0,window->width(),window->height()).contains(popupRect));
                auto *list=popup->property("contentItem").value<QQuickItem *>();
                if(list){QMetaObject::invokeMethod(list,"positionViewAtEnd");wait(120);}
                auto *last=item("swirlComboOption-6");
                check("last-format-option-visible-and-tall-enough",last&&list&&last->property("text").toString()=="sing-box"&&last->height()>=eval("Theme.controlHeight").toReal()&&visibleIn(last,list));
                if(last)lastFormatOptionRowHeight=last->height();
                if(auto *label=last?last->property("contentItem").value<QQuickItem *>():nullptr){
                    lastFormatOptionLabelContentHeight=label->property("contentHeight").toReal();lastFormatOptionLabelHeight=label->height();
                    check("format-option-label-not-vertically-clipped",lastFormatOptionLabelContentHeight<=lastFormatOptionLabelHeight+1);
                }
                window->grabWindow().save(QFileInfo(output).absolutePath()+"/subscription-form-popup.png");
                QTest::mouseClick(window,Qt::LeftButton,Qt::NoModifier,format->mapToScene(QPointF(format->width()/2,format->height()/2)).toPoint());wait(220);
                check("format-click-toggles-popup-closed",!popup->property("visible").toBool());
                QMetaObject::invokeMethod(popup,"open");wait(160);
                QTest::keyClick(window,Qt::Key_Escape);wait(220);
                check("escape-closes-format-before-form",!popup->property("visible").toBool()&&dialog->property("visible").toBool());
            }else check("format-popup-present",false);
            auto *flick=form->property("contentItem").value<QQuickItem *>();
            if(flick)flick->setProperty("contentY",qMax(0.0,flick->property("contentHeight").toReal()-flick->height()));
            QTest::keyClick(window,Qt::Key_Escape);wait(250);
            check("escape-closes-unchanged-form",!dialog->property("visible").toBool());
            click("addSubscription");
            check("reopened-form-restores-first-field",visibleIn(name,form)&&flick&&qAbs(flick->property("contentY").toReal())<1);
            name->setProperty("text",QString::fromUtf8("未保存的订阅"));
            QTest::keyClick(window,Qt::Key_Escape);wait(220);
            auto *discard=dialog->findChild<QObject *>("discardChangesPrompt");
            check("escape-guards-unsaved-subscription",dialog->property("visible").toBool()&&discard&&discard->property("visible").toBool()&&name->property("text").toString()==QString::fromUtf8("未保存的订阅"));
            QTest::keyClick(window,Qt::Key_Escape);wait(220);
            check("escape-from-discard-keeps-draft",dialog->property("visible").toBool()&&discard&&!discard->property("visible").toBool()&&!name->property("text").toString().isEmpty());
            QTest::keyClick(window,Qt::Key_Escape);wait(200);click("discardChangesConfirm");
            check("explicit-discard-closes-form",!dialog->property("visible").toBool());
        }
        auto *legacy=window->findChild<QObject *>("legacyNodesDialog");
        check("legacy-cleanup-dialog-mounted",legacy!=nullptr);
        if(legacy){
            QMetaObject::invokeMethod(legacy,"open");wait(250);
            auto *confirm=item("confirmLegacyNodesDelete");
            check("legacy-cleanup-confirmation-visible",confirm&&confirm->isVisible()&&legacy->property("visible").toBool());
            check("legacy-cleanup-footer-inside-window",confirm&&QRectF(0,0,window->width(),window->height()).contains(QRectF(confirm->mapToScene(QPointF()),confirm->size())));
            window->grabWindow().save(QFileInfo(output).absolutePath()+"/legacy-cleanup-dialog.png");
            QTest::keyClick(window,Qt::Key_Escape);wait(250);
            check("escape-cancels-legacy-cleanup",!legacy->property("visible").toBool());
        }
        navigate("proxies");
        auto *model=window->findChild<NodeViewModel *>("nodeViewModel");
        auto *table=item("realNodeTable"),*list=item("tableRowsViewport"),*search=item("nodeSearchField"),*source=item("nodeSourceFilter");
        check("node-layout-mounted",model&&table&&list&&search&&source);
        if(model&&table&&list&&search&&source){
            auto *controller=model->controller();model->setController(nullptr);
            QVariantList rows;for(int i=0;i<600;++i)rows.append(QVariantMap{{"id",QString::number(i)},{"name",QString("Node %1").arg(i,3,10,QChar('0'))},{"protocol","http"},{"host","node.example.test"},{"sourceKind",i%2?"subscription":"manual"},{"sourceId",i%2?"fixture-subscription":""},{"regionName","未知"},{"regionCode","ZZ"},{"status","未测试"},{"latency","—"}});
            model->updateRows(rows);wait(180);
            const QRectF tableBefore(table->mapToScene(QPointF()),table->size());
            QMetaObject::invokeMethod(list,"positionViewAtEnd");wait(150);
            QQmlExpression lastRow(qmlContext(list),list,"itemAtIndex(count-1)");auto *last=qobject_cast<QQuickItem *>(lastRow.evaluate().value<QObject *>());
            const QRectF viewport(list->mapToScene(QPointF()),list->size());
            check("last-of-600-nodes-fully-reachable",last&&viewport.adjusted(-1,-1,1,1).contains(QRectF(last->mapToScene(QPointF()),last->size())));
            check("large-node-list-remains-virtualized",table->property("renderedRows").toInt()<100);
            search->setProperty("text","no-such-node");wait(180);
            check("empty-search-keeps-node-viewport",model->rowCount()==0&&QRectF(table->mapToScene(QPointF()),table->size())==tableBefore&&window->size()==initial);
            search->setProperty("text","");wait(180);
            QMetaObject::invokeMethod(source,"activated",Q_ARG(int,1));wait(180);
            check("manual-source-filter-is-exclusive",model->rowCount()==300&&eval("pageLoader.item.sourceKind==='manual' && pageLoader.item.sourceId===''").toBool());
            check("source-filter-keeps-node-viewport",QRectF(table->mapToScene(QPointF()),table->size())==tableBefore&&window->size()==initial);
            if(auto *sort=item("nodeSortOrder")){sort->setProperty("currentIndex",1);wait(100);check("sorting-keeps-node-viewport",QRectF(table->mapToScene(QPointF()),table->size())==tableBefore&&window->size()==initial);sort->setProperty("currentIndex",0);}
            QMetaObject::invokeMethod(source,"activated",Q_ARG(int,0));wait(150);
            check("all-source-filter-restores-all-nodes",model->rowCount()==600);
            window->grabWindow().save(QFileInfo(output).absolutePath()+"/node-source-layout.png");
            model->setController(controller);
        }
        check("subscription-fixes-preserve-shell-size",window->size()==initial);
        check("subscription-fixes-preserve-sidebar",eval("window.actualSidebarWidth").toDouble()==sidebar);
        QFile file(output);QDir().mkpath(QFileInfo(output).absolutePath());if(!file.open(QIODevice::WriteOnly))return 2;
        file.write(QJsonDocument(QJsonObject{{"phase",phase},{"checks",checks},{"failures",failures},{"logicalWidth",initial.width()},{"logicalHeight",initial.height()},{"dpr",window->devicePixelRatio()},{"expectedDpr",expectedDpr},{"expectedDprVariable",QString::fromLatin1(expectedDprVariable)},{"lastFormatOptionLabelContentHeight",lastFormatOptionLabelContentHeight},{"lastFormatOptionLabelHeight",lastFormatOptionLabelHeight},{"lastFormatOptionRowHeight",lastFormatOptionRowHeight},{"note","Mounted QML layout, popup, Escape and synthetic 600-row virtualization checks only; subscription/network acceptance runs separately. Missing format geometry is reported as -1."}}).toJson());return failures?1:0;
    }
    if(phase=="S4"){
        navigate("proxies");
        auto *model=window->findChild<NodeViewModel *>("nodeViewModel");
        if(!model)return 2;
        auto *controller=model->controller();model->setController(nullptr);
        auto *table=window->findChild<QQuickItem *>("realNodeTable");
        auto *list=table?table->findChild<QQuickItem *>("tableRowsViewport"):nullptr;
        auto *hero=window->findChild<QQuickItem *>("nodeHero");
        if(!table||!list||!hero)return 2;
        QList<double> navigationResponses,navigationComplete,selectionResponses,selectionComplete;
        for(const int count:{100,500,1000,2000}){
            QVariantList rows;
            for(int i=0;i<count;++i)rows.append(QVariantMap{{"id",QString::number(i)},{"name",QString("日本 Tokyo · 性能样本 %1").arg(i,4,10,QChar('0'))},{"protocol",i%2?"vless":"ss"},{"host","node.example.test"},{"port",9},{"address","node.example.test:9"},{"regionName","日本"},{"regionCode","JP"},{"status","可用"},{"latency",QString::number(10+i)},{"capability",QVariantMap{{"native",false},{"compatible",false},{"engine","synthetic fixture"}}}});
            QElapsedTimer load;load.start();model->updateRows(rows);const double updateMs=load.nsecsElapsed()/1e6;wait(180);
            check(QString("nodes-%1").arg(count),model->rowCount()==count);
            check(QString("virtualized-%1").arg(count),table->property("renderedRows").toInt()<100);
            auto *sections=window->findChild<QObject *>("nodeSectionModel");int headerIndex=-1;
            if(sections)QMetaObject::invokeMethod(sections,"rowForDisplayKey",Q_RETURN_ARG(int,headerIndex),Q_ARG(QString,QString("section:manual")));
            check("keyboard-source-header-is-mounted",sections&&headerIndex>=0);
            if(sections&&headerIndex>=0){
                const auto configured=controller?controller->selectedNodeId():QString(),active=controller?controller->activeNodeId():QString();
                const int expandedRows=sections->property("displayCount").toInt();
                QMetaObject::invokeMethod(list,"positionViewAtIndex",Q_ARG(int,headerIndex),Q_ARG(int,0));wait(80);
                list->setProperty("currentIndex",headerIndex);list->forceActiveFocus();
                QTest::keyClick(window,Qt::Key_Space);
                check("space-collapses-source-without-losing-filtered-test-scope",QTest::qWaitFor([&]{return sections->property("displayCount").toInt()==expandedRows-count;},1500)&&sections->property("count").toInt()==count&&model->rowCount()==count);
                check("source-header-does-not-open-node-details",!hero->property("opened").toBool());
                QTest::keyClick(window,Qt::Key_Return);
                check("enter-restores-source-node-rows",QTest::qWaitFor([&]{return sections->property("displayCount").toInt()==expandedRows;},1500));
                check("source-keyboard-actions-preserve-configured-and-running-exits",controller&&controller->selectedNodeId()==configured&&controller->activeNodeId()==active);
                wait(180);
            }
            sample(QString("nodes-%1-before").arg(count));
            QElapsedTimer search;search.start();
            for(int i=0;i<20;++i){model->setQuery(i%2?"TOKYO":"VLESS");check("search-count",model->rowCount()==(i%2?count:count/2));}
            const double searchMs=search.nsecsElapsed()/1e6;model->setQuery("");wait(100);
            struct FrameSamples {QList<double> values;QMutex mutex;QElapsedTimer clock;qint64 last=0;};
            const auto frameSamples=std::make_shared<FrameSamples>();frameSamples->clock.start();
            auto connection=QObject::connect(window,&QQuickWindow::frameSwapped,window,[frameSamples]{QMutexLocker lock(&frameSamples->mutex);const auto now=frameSamples->clock.nsecsElapsed();if(frameSamples->last)frameSamples->values.append((now-frameSamples->last)/1e6);frameSamples->last=now;},Qt::DirectConnection);
            QElapsedTimer eventClock;eventClock.start();double maxGap=0;QTimer ticker;ticker.setInterval(8);
            QObject::connect(&ticker,&QTimer::timeout,&ticker,[&]{maxGap=qMax(maxGap,eventClock.nsecsElapsed()/1e6);eventClock.restart();});ticker.start();
            const double extent=qMax(0.0,list->property("contentHeight").toDouble()-list->height());
            QHash<QObject *,QString> identities;int reused=0,stale=0;
            auto *content=list->property("contentItem").value<QQuickItem *>();
            std::function<void(QQuickItem *)> inspectLatency=[&](QQuickItem *cell){
                if(cell->property("measured").isValid()&&cell->property("measured").toDouble()>=0&&qAbs(cell->property("measured").toDouble()-cell->property("displayed").toDouble())>.01)++stale;
                for(auto *child:cell->childItems())inspectLatency(child);
            };
            for(int i=0;i<80;++i){list->setProperty("contentY",extent*(i<40?i:79-i)/39.0);wait(8);
                for(auto *row:content?content->childItems():QList<QQuickItem *>{}){
                    const auto value=row->property("record");
                    const auto record=value.metaType()==QMetaType::fromType<QJSValue>()?value.value<QJSValue>().toVariant().toMap():value.toMap();if(record.isEmpty()||record.value("rowKind")!="node")continue;
                    const auto id=record.value("id").toString();
                    if(identities.contains(row)&&identities.value(row)!=id){++reused;inspectLatency(row);}
                    identities.insert(row,id);
                }
            }
            check(QString("pooled-latency-identity-%1").arg(count),reused>0&&stale==0);
            ticker.stop();QObject::disconnect(connection);QList<double> frames;
            {QMutexLocker lock(&frameSamples->mutex);frames=frameSamples->values;}
            std::sort(frames.begin(),frames.end());
            const auto percentile=[&](const QList<double> &values,double p){return values.isEmpty()?0:values[qMin(values.size()-1,qsizetype(values.size()*p))];};
            samples.append(QJsonObject{{"scenario",QString("nodes-%1-scroll").arg(count)},{"updateMs",updateMs},{"search20Ms",searchMs},{"renderedRows",table->property("renderedRows").toInt()},{"frames",frames.size()},{"p95FrameMs",percentile(frames,.95)},{"p99FrameMs",percentile(frames,.99)},{"maxEventLoopGapMs",maxGap},{"reusedDelegates",reused},{"staleLatencyOnReuse",stale}});
            list->setProperty("contentY",0);wait(150);
            const int firstNodeIndex=eval("pageLoader.item.sectionIndexForNode('0')").toInt();
            check("latency-sample-is-a-real-node-row",firstNodeIndex>=0);
            QQmlExpression firstRow(qmlContext(list),list,QString("itemAtIndex(%1)").arg(firstNodeIndex));
            auto *first=qobject_cast<QQuickItem *>(firstRow.evaluate().value<QObject *>());
            QQuickItem *latencyCell=nullptr;
            std::function<void(QQuickItem *)> findLatency=[&](QQuickItem *item){if(item->property("measured").isValid()&&item->property("measured").toDouble()>=0)latencyCell=item;for(auto *child:item->childItems())findLatency(child);};
            if(first)findLatency(first);
            auto changedRow=rows[0].toMap();changedRow["latency"]="90";rows[0]=changedRow;model->updateRows(rows);wait(40);
            const double intermediate=latencyCell?latencyCell->property("displayed").toDouble():-1;
            check("same-node-latency-still-animates",intermediate>10&&intermediate<90);
            wait(300);check("same-node-latency-settles-to-real-measurement",latencyCell&&qAbs(latencyCell->property("displayed").toDouble()-90)<.01);
            samples.append(QJsonObject{{"scenario",QString("nodes-%1-latency").arg(count)},{"intermediate",intermediate},{"settled",latencyCell?latencyCell->property("displayed").toDouble():-1},{"measured",latencyCell?latencyCell->property("measured").toDouble():-1}});
            for(int i=0;i<8;++i){
                const auto nodeId=QString::number(i%4);
                const int displayIndex=eval(QString("pageLoader.item.sectionIndexForNode('%1')").arg(nodeId)).toInt();
                check("detail-node-has-source-section-index",displayIndex>=0);
                if(displayIndex>=0)QMetaObject::invokeMethod(list,"positionViewAtIndex",Q_ARG(int,displayIndex),Q_ARG(int,0));
                wait(80);
                QQmlExpression targetRow(qmlContext(list),list,QString("itemAtIndex(%1)").arg(displayIndex));
                auto *row=qobject_cast<QQuickItem *>(targetRow.evaluate().value<QObject *>());
                check("detail-node-delegate-is-mounted",row!=nullptr);
                const auto configured=controller?controller->selectedNodeId():QString();
                const auto active=controller?controller->activeNodeId():QString();
                const auto point=row?row->mapToScene(QPointF(85,row->height()/2)).toPoint():QPoint();
                if(row)QTest::mouseClick(window,Qt::LeftButton,Qt::NoModifier,point);
                check("single-click-focuses-resource-only",eval("pageLoader.item.focusedId").toString()==nodeId&&!hero->property("opened").toBool());
                check("single-click-preserves-configured-and-running-exits",controller&&controller->selectedNodeId()==configured&&controller->activeNodeId()==active);
                QElapsedTimer response;response.start();
                if(row){
                    if(i<4)QTest::mouseDClick(window,Qt::LeftButton,Qt::NoModifier,point);
                    else QTest::keyClick(window,Qt::Key_Return);
                }
                selectionResponses.append(response.nsecsElapsed()/1e6);
                check("selection-opens-actual-detail",hero->property("opened").toBool());
                check("opening-detail-preserves-configured-and-running-exits",controller&&controller->selectedNodeId()==configured&&controller->activeNodeId()==active);
                check("selection-settles",QTest::qWaitFor([&]{return !hero->property("moving").toBool();},2500));selectionComplete.append(response.nsecsElapsed()/1e6);
                QTest::keyClick(window,Qt::Key_Escape);check("escape-restores-list",QTest::qWaitFor([&]{return !hero->property("opened").toBool()&&!hero->property("moving").toBool();},2500));
            }
            window->grabWindow().save(QFileInfo(output).absolutePath()+QString("/nodes-%1.png").arg(count));
            sample(QString("nodes-%1-after").arg(count));
        }
        model->setController(controller);
        for(int i=0;i<20;++i){QElapsedTimer response;response.start();eval(i%2?"AppState.navigate('proxies')":"AppState.navigate('activity')");navigationResponses.append(response.nsecsElapsed()/1e6);check("navigation-settles",QTest::qWaitFor([&]{return !eval("pageLoader.pendingGrab || pageLoader.moving || !pageLoader.item || pageLoader.activeLoader.routeId!==pageLoader.routeKey").toBool();},3000));navigationComplete.append(response.nsecsElapsed()/1e6);}
        navigate("activity");wait(600);sample("idle-start");wait(3000);sample("idle-end");
        window->showMinimized();wait(300);sample("minimized-start");wait(3000);sample("minimized-end");window->showNormal();wait(100);
        QJsonObject timing;
        for(auto pair:{qMakePair(QString("navigationDispatch"),&navigationResponses),qMakePair(QString("navigationComplete"),&navigationComplete),qMakePair(QString("selectionDispatch"),&selectionResponses),qMakePair(QString("selectionComplete"),&selectionComplete)}){std::sort(pair.second->begin(),pair.second->end());timing[pair.first+"P95Ms"]=pair.second->isEmpty()?0:pair.second->at(qMin(pair.second->size()-1,qsizetype(pair.second->size()*.95)));}
        check("shell-size-preserved",window->size()==initial);check("sidebar-preserved",eval("window.actualSidebarWidth").toDouble()==sidebar);
        QFile file(output);QDir().mkpath(QFileInfo(output).absolutePath());if(!file.open(QIODevice::WriteOnly))return 2;
        file.write(QJsonDocument(QJsonObject{{"phase",phase},{"checks",checks},{"failures",failures},{"samples",samples},{"timing",timing},{"dpr",window->devicePixelRatio()},{"note","Synthetic public model data only; no network acceptance. Dispatch is synchronous event handling, completion includes full animation; neither is input-to-photon latency."}}).toJson());return failures?1:0;
    }
    if(phase=="navigation"){
        navigate("activity");QTest::keyClick(window,Qt::Key_Escape);wait(250);
        check("primary-escape-keeps-window",window->isVisible()&&eval("AppState.currentPage").toString()=="activity");
        for(const auto &route:{"traffic","connections","toolbox","processes","gateway","logs"}){
            eval(QString("AppState.openDetail('%1')").arg(route));wait(500);QTest::keyClick(window,Qt::Key_Escape);wait(500);
            check(QString("activity-escape-")+route,eval("AppState.currentPage").toString()=="activity");
        }
        eval("AppState.openDetail('traffic')");wait(400);eval("AppState.openDetail('connections')");wait(400);
        QTest::keyClick(window,Qt::Key_Escape);wait(400);check("nested-first-escape",eval("AppState.currentPage").toString()=="traffic");
        QTest::keyClick(window,Qt::Key_Escape);wait(400);check("nested-second-escape",eval("AppState.currentPage").toString()=="activity");
        navigate("featurehub");navigate("proxies");
        auto *combo=window->findChild<QQuickItem *>("nodeSortOrder");
        if(combo){auto *popup=combo->property("popup").value<QObject *>();QMetaObject::invokeMethod(popup,"open");wait(250);QTest::keyClick(window,Qt::Key_Escape);wait(300);check("popup-first-escape",!popup->property("visible").toBool()&&eval("AppState.currentPage").toString()=="proxies");}
        else check("sort-popup-present",false);
        auto *search=window->findChild<QQuickItem *>("nodeSearchField");if(search)search->forceActiveFocus();
        QTest::keyClick(window,Qt::Key_Escape);wait(450);check("focused-input-back",eval("AppState.currentPage").toString()=="featurehub");
        check("escape-keeps-geometry",window->size()==initial);
        QFile f(output);if(!f.open(QIODevice::WriteOnly))return 2;f.write(QJsonDocument(QJsonObject{{"checks",checks},{"failures",failures}}).toJson());return failures?1:0;
    }
    if(phase=="detail"){
        navigate("proxies");
        auto *model=window->findChild<NodeViewModel *>("nodeViewModel");
        if(!model||!model->controller())return 2;
        auto *controller=model->controller();
        check("save-isolated-detail-node",controller->saveNode({{"name","详情验证 · 日本 Tokyo"},{"protocol","socks5"},{"host","127.0.0.1"},{"port",9}}));
        wait(100);const auto before=window->grabWindow();
        const auto configured=controller->selectedNodeId(),active=controller->activeNodeId();
        eval("pageLoader.item.inspectRow(engineController.nodes[0])");
        check("detail-inspection-preserves-configured-and-running-exits",controller->selectedNodeId()==configured&&controller->activeNodeId()==active);
        auto *hero=window->findChild<QQuickItem *>("nodeHero");
        for(int i=0;i<40;++i){wait(50);if(hero)samples.append(QJsonObject{{"ms",(i+1)*50},{"reveal",hero->property("reveal").toDouble()},{"moving",hero->property("moving").toBool()},{"width",hero->property("cardWidth").toDouble()},{"height",hero->property("cardHeight").toDouble()}});}
        check("detail-fully-revealed",hero&&!hero->property("moving").toBool()&&hero->property("reveal").toDouble()>0.99);
        auto *body=window->findChild<QQuickItem *>("nodeDetailBody");
        check("detail-body-visible",body&&body->isVisible()&&body->opacity()>0.99&&body->width()>100&&body->height()>100);
        auto *scrim=window->findChild<QQuickItem *>("nodeDetailScrim");const auto after=window->grabWindow();
        check("rounded-scrim",scrim&&scrim->property("radius").toDouble()==eval("Theme.cardRadius").toDouble());
        if(scrim&&!before.isNull()&&!after.isNull())for(const auto &p:{QPointF(2,2),QPointF(scrim->width()-3,2),QPointF(2,scrim->height()-3),QPointF(scrim->width()-3,scrim->height()-3)}){
            const auto pixel=(scrim->mapToScene(p)*window->devicePixelRatio()).toPoint();
            check("scrim-corner-preserves-background",before.rect().contains(pixel)&&after.rect().contains(pixel)&&before.pixelColor(pixel)==after.pixelColor(pixel));
        }
        window->grabWindow().save(QFileInfo(output).absolutePath()+"/detail.png");
        window->resize(window->minimumWidth(),window->minimumHeight());wait(500);
        auto *scroll=window->findChild<QQuickItem *>("nodeDetailScroll");
        auto *flick=scroll?scroll->property("contentItem").value<QQuickItem *>():nullptr;
        if(flick){flick->setProperty("contentY",qMax(0.0,flick->property("contentHeight").toDouble()-flick->height()));wait(150);}
        auto *lastAction=window->findChild<QQuickItem *>("nodeDeleteButton");
        auto *requestState=window->findChild<QQuickItem *>("nodeRequestState");
        const QRectF viewport=scroll?QRectF(scroll->mapToScene(QPointF()),QSizeF(scroll->width(),scroll->height())):QRectF();
        check("minimum-size-last-detail-action-reachable",lastAction&&lastAction->isVisible()&&viewport.contains(lastAction->mapToScene(QPointF(lastAction->width()/2,lastAction->height()/2))));
        check("minimum-size-independent-request-state-reachable",requestState&&requestState->isVisible()&&viewport.contains(requestState->mapToScene(QPointF(requestState->width()/2,requestState->height()/2))));
        auto *back=window->findChild<QQuickItem *>("nodeReturnButton");
        check("detail-back-header-stays-visible",back&&back->isVisible()&&QRectF(0,0,window->width(),window->height()).contains(back->mapToScene(QPointF(back->width()/2,back->height()/2))));
        window->grabWindow().save(QFileInfo(output).absolutePath()+"/detail-minimum.png");
        if(back)QTest::mouseClick(window,Qt::LeftButton,Qt::NoModifier,back->mapToScene(QPointF(back->width()/2,back->height()/2)).toPoint());wait(500);
        check("detail-close-restores-list",hero&&!hero->property("opened").toBool());
        QFile f(output);if(!f.open(QIODevice::WriteOnly))return 2;f.write(QJsonDocument(QJsonObject{{"checks",checks},{"samples",samples},{"failures",failures}}).toJson());return failures?1:0;
    }
    const auto routes=QJsonDocument::fromJson(eval("JSON.stringify(AppState.allPageIds.concat(['activity','settings','proxies','featurehub']))").toString().toUtf8()).array();
    for(const auto &route:routes){
        if(route.toString()=="external")continue;
        navigate(route.toString());
        check("geometry-"+route.toString(),window->size()==initial);
        check("sidebar-"+route.toString(),eval("window.actualSidebarWidth").toDouble()==sidebar);
    }
    window->resize(initial+QSize(90,40));const auto resized=window->size();
    for(const auto &route:{"activity","featurehub","settings","proxies","overview","activity"}){navigate(route);check(QString("manual-geometry-")+route,window->size()==resized);}
    window->resize(initial);navigate("activity");
    if(phase!="baseline"&&phase!="A"){
        check("design-window-corner-extent-22",eval("Theme.windowRadius").toDouble()==22);
        check("design-sidebar-radius-20",eval("sidebar.children[0].radius").toDouble()==20);
        window->grabWindow().save(QFileInfo(output).absolutePath()+"/corners-"+QString::number(window->devicePixelRatio())+".png");
    }
    sample("all-pages-warm");
    if(phase=="C"||phase=="D"||phase=="E"){
        navigate("proxies");
        auto *model=window->findChild<NodeViewModel *>("nodeViewModel");
        check("native-node-model",model!=nullptr);
        if(model){
            auto *controller=model->controller();model->setController(nullptr);
            for(const int count:{100,500,1000,2000,419,5000}){
                QVariantList rows;for(int i=0;i<count;++i)rows.append(QVariantMap{{"id",QString::number(i)},{"name",QString("日本 Tokyo · 长节点名称性能样本 %1").arg(i)},{"protocol",i%2?"vless":"ss"},{"host","node.example.test"},{"regionName","日本"},{"regionCode","JP"},{"status","未测试"},{"latency","—"}});
                QElapsedTimer load;load.start();model->updateRows(rows);wait(100);
                check(QString("nodes-%1").arg(count),model->rowCount()==count);
                const auto rendered=eval("pageLoader.item.children.length").toInt();
                Q_UNUSED(rendered);
                auto *table=window->findChild<QQuickItem *>("realNodeTable");
                check(QString("virtualized-%1").arg(count),table&&table->property("renderedRows").toInt()<100);
                samples.append(QJsonObject{{"scenario",QString("nodes-%1").arg(count)},{"loadAndSettleMs",double(load.elapsed())},{"renderedRows",table?table->property("renderedRows").toInt():-1}});
                model->setQuery("VLESS");wait(120);check("protocol-search",model->rowCount()==count/2);
                model->setQuery("不存在");check("empty-search",model->rowCount()==0);model->setQuery("");wait(100);
                if(count==419)window->grabWindow().save(QFileInfo(output).absolutePath()+"/nodes-419.png");
            }
            model->setController(controller);
        }
        navigate("activity");
    }
    qint64 maxGap=0;QElapsedTimer heartbeat;heartbeat.start();QTimer ticker;ticker.setInterval(16);
    QObject::connect(&ticker,&QTimer::timeout,&ticker,[&]{maxGap=qMax(maxGap,heartbeat.restart());});ticker.start();
    for(int i=0;i<100;++i){navigate(i%2?"activity":"featurehub");if(i%20==19)sample(QString("switch-%1").arg(i+1));}
    bool ok=false;const int soak=qEnvironmentVariableIntValue("SWIRL_U2_SOAK_SECONDS",&ok);
    if(ok)for(int i=0;i<soak;++i){wait(1000);if(i%60==59)sample(QString("soak-%1").arg(i+1));}
    ticker.stop();sample("final");
    QFile file(output);QDir().mkpath(QFileInfo(output).absolutePath());if(!file.open(QIODevice::WriteOnly))return 2;
    file.write(QJsonDocument(QJsonObject{{"phase",phase},{"checks",checks},{"failures",failures},{"samples",samples},{"maxEventLoopGapMs",double(maxGap)},{"logicalWidth",initial.width()},{"logicalHeight",initial.height()},{"dpr",window->devicePixelRatio()},{"note","Isolated test storage; real Qt event loop. Synthetic node data, when used, is not networking acceptance. DPI factor is process-local, not a change to Windows display settings."}}).toJson());
    return failures?1:0;
}
