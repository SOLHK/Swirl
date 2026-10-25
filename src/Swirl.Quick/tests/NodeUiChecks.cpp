#include "NodeUiChecks.h"
#include "SwirlBuildIdentity.h"
#include "ControlledNetwork.h"
#include "LoopbackPortLease.h"
#include "PolicySystemProxyBackend.h"
#include "engine/EngineController.h"
#include <QQuickWindow>
#include <QQuickItem>
#include <QQmlContext>
#include <QQmlExpression>
#include <QQmlComponent>
#include <QQmlEngine>
#include <QTest>
#include <QSignalSpy>
#include <QClipboard>
#include <QGuiApplication>
#include <QDir>
#include <QImage>
#include <QFile>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJSValue>
#include <cstdio>
#include <functional>
#include <memory>

int runNodeUiChecks(QQuickWindow *window,EngineController *controller) {
    if(!window||!controller)return 1;
    int checks=0,failures=0;
    const auto check=[&](bool ok,const char *label){++checks;if(!ok)++failures;qInfo()<<(ok?"PASS":"FAIL")<<label;return ok;};
    auto *proxyBackend=dynamic_cast<PolicySystemProxyBackend *>(controller->systemProxy()->backend());
    if(!check(proxyBackend!=nullptr,"node acceptance uses a per-instance system-proxy sandbox before any input"))return 2;
    std::function<QQuickItem *(QQuickItem *,const QString &)> find;
    find=[&](QQuickItem *p,const QString &n)->QQuickItem *{if(p->objectName()==n)return p;for(auto *c:p->childItems())if(auto *f=find(c,n))return f;return nullptr;};
    const auto item=[&](const QString &n){return find(window->contentItem(),n);};
    const auto eval=[&](const QString &s){if(s.contains("resultCount"))check(QTest::qWaitFor([&]{auto *model=window->findChild<QObject *>("nodeViewModel");return model&&model->property("total").toInt()==controller->nodes().size();},1000),"node catalog catches up before count assertion");QQmlExpression e(qmlContext(window),window,s);auto v=e.evaluate();check(!e.hasError(),"QML expression valid");return v;};
    const auto click=[&](const QString &n){if(!check(QTest::qWaitFor([&]{auto *hero=item("nodeHero");auto *target=item(n);if((hero&&hero->property("moving").toBool())||!target||!target->isVisible())return false;qreal opacity=1;for(auto *parent=target;parent;parent=parent->parentItem())opacity*=parent->opacity();return opacity>0.95;},3500),"node input is visible after motion settles"))return;auto *t=item(n);if(check(t&&t->isEnabled(),"node input exists and is enabled"))QTest::mouseClick(window,Qt::LeftButton,Qt::NoModifier,t->mapToScene(QPointF(t->width()/2,t->height()/2)).toPoint());QTest::qWait(300);if(n=="nodeSaveButton"||n=="nodeDeleteButton")check(QTest::qWaitFor([&]{return !controller->policyBusy();},10000),"node mutation waits for its real configuration completion");};
    const auto fill=[&](const QString &n,const QString &v){auto *t=item(n);if(check(t!=nullptr,"node field exists"))t->setProperty("text",v);};
    std::function<QQuickItem *(QQuickItem *,const QString &)> findNodeRow;
    findNodeRow=[&](QQuickItem *parent,const QString &id)->QQuickItem *{
        const auto value=parent->property("record");
        const auto record=value.metaType()==QMetaType::fromType<QJSValue>()?value.value<QJSValue>().toVariant().toMap():value.toMap();
        if(record.value("rowKind")=="node"&&record.value("id")==id&&!parent->property("pooled").toBool())return parent;
        for(auto *child:parent->childItems())if(auto *found=findNodeRow(child,id))return found;
        return nullptr;
    };
    const auto select=[&](int index){ eval("pageLoader.item.dismissDetail()"); QTest::qWait(450);
        auto *t=item("realNodeTable");if(!check(t!=nullptr,"real node table exists"))return;
        const auto id=eval(QString("pageLoader.item.resourceAt(%1).id").arg(index)).toString();
        const auto displayRow=eval(QString("pageLoader.item.sectionIndexForNode('%1')").arg(id)).toInt();
        auto *viewport=item("tableRowsViewport");
        if(viewport)QMetaObject::invokeMethod(viewport,"positionViewAtIndex",Q_ARG(int,displayRow),Q_ARG(int,0));
        QTest::qWait(80);
        auto *row=findNodeRow(t,id);
        if(!check(row!=nullptr,"source-grouped node delegate is visible"))return;
        const auto selection=controller->selectedNodeId(),active=controller->activeNodeId();
        const auto point=row->mapToScene(QPointF(70,row->height()/2)).toPoint();
        QTest::mouseClick(window,Qt::LeftButton,Qt::NoModifier,point);
        check(controller->selectedNodeId()==selection&&controller->activeNodeId()==active,"single-click browsing preserves configured and running exits");
        QTest::mouseDClick(window,Qt::LeftButton,Qt::NoModifier,point);
        // The next click targets a card which moves for longer than 150 ms.
        // Sample its hit position after the real transition has settled.
        check(QTest::qWaitFor([&]{auto *hero=item("nodeHero");return hero&&!hero->property("moving").toBool();},3500),"node card settles before next coordinate-based input");
        check(controller->selectedNodeId()==selection&&controller->activeNodeId()==active,"opening node details preserves configured and running exits");
    };
    ControlledNetwork net;if(!check(net.start(),"controlled real TCP endpoints start"))return 2;
    const auto foreignFixture=QStringLiteral("node-runtime.fixture.invalid");
    net.a.aliases={foreignFixture};net.b.aliases={foreignFixture};
    auto liveUrl=net.url();liveUrl.setHost(foreignFixture);
    const auto probeSelected=[&](SocksPeer &selected,SocksPeer &other,const char *label){
        const auto forwarded=selected.forwarded,otherForwarded=other.forwarded;
        const auto before=net.httpRequestsByExit;
        click("nodeTestButton");
        const bool finished=QTest::qWaitFor([&]{return !controller->tests()->busy();},41000);
        const auto inspected=eval("pageLoader.item.selectedId").toString();
        const bool passed=finished&&controller->tests()->result(inspected).value("success").toBool()
            &&selected.forwarded>forwarded&&other.forwarded==otherForwarded
            &&net.httpRequestsByExit.value(selected.label)>before.value(selected.label)
            &&net.httpRequestsByExit.value(other.label)==before.value(other.label)
            &&net.httpRequestsByExit.value("DIRECT-BYPASS")==before.value("DIRECT-BYPASS");
        // Native probes make one request. Assert the actual origin route, not
        // the old compatibility probe's incidental two-connection count.
        if(!passed)qInfo()<<"Probe evidence"<<finished<<selected.forwarded-forwarded<<other.forwarded-otherForwarded<<net.httpRequestsByExit;
        check(passed,label);
    };
    window->resize(1450,884);eval("AppState.navigate('proxies')");
    auto *host=window->findChild<QObject *>("pageLoader");
    const auto choosePolicy=[&](const QString &id,bool toggleConnection){
        eval("pageLoader.item.dismissDetail()");QTest::qWait(450);
        eval("AppState.navigate('policies')");
        check(QTest::qWaitFor([&]{auto *active=host?qvariant_cast<QObject *>(host->property("activeLoader")):nullptr;return active&&active->property("routeId").toString()=="policies"&&!host->property("moving").toBool()&&!host->property("pendingGrab").toBool();},3500),"policy exit selector settles");
        if(controller->policyMigrationRequired()){
            click("reviewPolicyMigration");click("confirmPolicyMigration");
            check(QTest::qWaitFor([&]{return !controller->policyBusy()&&!controller->policyMigrationRequired();},10000),"policy migration is explicitly reviewed and committed");
        }
        const auto target=controller->defaultPolicy().value("target").toMap();
        if(target.value("kind")!="node"||target.value("id")!=id){
            click("defaultPolicyTarget");click("policyNode-"+id);click("confirmPolicyTarget");
            check(QTest::qWaitFor([&]{return !controller->policyBusy()&&controller->defaultPolicy().value("target").toMap().value("id")==id;},10000),"default exit picker waits for the real configuration commit");
        }
        if(controller->policyDocument().value("mode")!="global"){
            click("routingModePicker");click("swirlComboOption-1");
            check(QTest::qWaitFor([&]{return !controller->policyBusy()&&controller->policyDocument().value("mode")=="global";},10000),"controlled node regression explicitly applies global routing through real input");
        }
        const bool wasRunning=controller->processAlive();
        check(item("policyConnectButton")==nullptr,"policy configuration has no separate connection control");
        if(toggleConnection){
            eval("AppState.navigate('activity')");
            check(QTest::qWaitFor([&]{auto *active=host?qvariant_cast<QObject *>(host->property("activeLoader")):nullptr;auto *capsule=item("proxyCapsule");return active&&active->property("routeId").toString()=="activity"&&!host->property("moving").toBool()&&!host->property("pendingGrab").toBool()&&capsule&&capsule->isVisible();},3500),"activity master switch settles before real input");
            click("proxyCapsule");
            check(QTest::qWaitFor([&]{return wasRunning?controller->canStart()&&!controller->systemProxy()->owned():controller->apiHealthy()&&controller->systemProxy()->owned()&&controller->systemProxy()->enabled();},15000),"activity master switch reaches its real runtime and isolated proxy state");
            check(proxyBackend->current().systemEnabled,"activity start and stop preserve the pre-existing external proxy in the sandbox");
        }else if(wasRunning){
            check(QTest::qWaitFor([&]{return !controller->nodeBusy()&&!controller->policyBusy()&&controller->activeNodeId()==id;},10000),"policy exit selection is applied before resource inspection");
        }
        check(controller->selectedNodeId()==id,"policy selection updates the configured exit through real input");
        eval("AppState.navigate('proxies')");
        check(QTest::qWaitFor([&]{auto *active=host?qvariant_cast<QObject *>(host->property("activeLoader")):nullptr;return active&&active->property("routeId").toString()=="proxies"&&!host->property("moving").toBool()&&!host->property("pendingGrab").toBool();},3500),"policy action returns to the node library");
    };
    check(QTest::qWaitFor([&]{auto *active=host?qvariant_cast<QObject *>(host->property("activeLoader")):nullptr;return active && active->property("routeId").toString()=="proxies" && !host->property("moving").toBool() && !host->property("pendingGrab").toBool();},3500),"node navigation animation settles before input");
    QTest::qWait(150);
    check(controller->nodes().isEmpty()&&!controller->processAlive(),"node page starts empty without starting engine");
    click("nodeAddButton");fill("nodeNameField","A");fill("nodeHostField","https://invalid");fill("nodePortField",QString::number(net.a.serverPort()));click("nodeSaveButton");
    check(controller->nodes().isEmpty()&&!controller->nodeError().isEmpty(),"invalid host rejected through UI without fake save");
    fill("nodeHostField","127.0.0.1");click("nodeSaveButton");check(controller->nodes().size()==1,"UI saves first real node");
    check(controller->selectedNodeId().isEmpty()&&controller->activeNodeId().isEmpty(),"adding a resource does not choose a configured or running exit");
    click("nodeAddButton");fill("nodeNameField","B");fill("nodeHostField","127.0.0.1");fill("nodePortField",QString::number(net.b.serverPort()));fill("nodeUsernameField",QString::fromUtf8(net.b.username));fill("nodePasswordField",QString::fromUtf8(net.b.password));
    check(item("nodePasswordField")&&item("nodePasswordField")->property("echoMode").toInt()==2,"credential field is masked");click("nodeSaveButton");check(controller->nodes().size()==2,"UI saves authenticated SOCKS5 node");
    check(controller->selectedNodeId().isEmpty()&&controller->activeNodeId().isEmpty(),"adding another resource still leaves exit selection to policies");
    LoopbackPortLease ports;
    if(!check(ports.reserve(),"distinct UI TCP/UDP and control ports are reserved together")) {
        qInfo()<<"Port reservation evidence"<<ports.errorString();return 2;
    }
    controller->setProxyPort(ports.proxyPort());
    ports.release();
    controller->setRoutingMode(QStringLiteral("global"));
    const auto waitEngineReady=[&]{
        const bool ready=QTest::qWaitFor([&]{return controller->apiHealthy();},15000);
        if(!ready)qInfo()<<"Engine startup evidence"<<controller->stateText()<<controller->errorCode()<<controller->error();
        return ready;
    };
    select(0);
    check(item("nodeConnectButton")==nullptr,"node resource details have no connection control");
    const auto nodeA=eval("pageLoader.item.selectedId").toString();
    choosePolicy(nodeA,true);select(0);
    if(check(waitEngineReady(),"UI starts actual Rust Core")) {
        check(!controller->requestSucceeded(),"running engine does not imply successful request");fill("nodeTestUrl",net.url().toString());
        probeSelected(net.a,net.b,"UI real request passes only through selected node A");
        // Exercise the real Main toolbar after this test's node-page history,
        // without invoking the real Windows adapter on the developer's host.
        {
            const auto hostProxyBefore=SystemProxySession::snapshot();
#ifdef Q_OS_WIN
            check(!hostProxyBefore.isEmpty(),"read-only Main proxy snapshot is available");
#endif
            const auto pidBefore=controller->processId();
            eval("AppState.navigate('activity')");
            const bool legacyReady=QTest::qWaitFor([&]{return eval("AppState.currentPage==='activity' && !pageLoader.pendingGrab && !pageLoader.moving").toBool();},3500);
            auto *capsule=item("proxyCapsule");
            if(check(capsule&&capsule->isVisible(),"read-only Main proxy capsule is visible")) {
                QQmlComponent component(qmlEngine(window));
                component.setData(R"(
                    import QtQuick
                    QtObject {
                        property bool busy: false
                        property bool policyBusy: false
                        property bool processAlive: false
                        property bool proxyRequested: false
                        property bool systemProxyStopping: false
                        property bool systemProxyBusy: false
                        property string errorCode: "None"
                        property string routingError: ""
                        property string policyError: ""
                        property string error: ""
                        property int calls: 0
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
                            proxyRequested=!proxyRequested
                            processAlive=proxyRequested
                            systemProxy.owned=proxyRequested
                            systemProxy.enabled=proxyRequested
                            systemProxy.systemEnabled=proxyRequested
                        }
                    }
                )",QUrl());
                std::unique_ptr<QObject> fake(component.create());
                if(check(fake!=nullptr,"read-only Main proxy controller is created")) {
                    const auto originalController=capsule->property("controller");
                    {
                        struct RestoreController {
                            QQuickItem *capsule;QVariant original;
                            ~RestoreController(){capsule->setProperty("controller",original);}
                        } restore{capsule,originalController};
                        if(check(capsule->setProperty("controller",QVariant::fromValue(fake.get())),"read-only Main proxy controller is bound")) {
                            QSignalSpy clicked(capsule,SIGNAL(clicked()));
                            check(clicked.isValid(),"read-only Main proxy clicked signal is observed");
                            const auto *legacyActive=host?qvariant_cast<QObject *>(host->property("activeLoader")):nullptr;
                            const auto legacyRoute=legacyActive?legacyActive->property("routeId").toString():QString();
                            const auto legacyPoint=capsule->mapToScene(QPointF(capsule->width()/2,capsule->height()/2));
                            const QSizeF legacySize(capsule->width(),capsule->height());
                            click("proxyCapsule");
                            qInfo()<<"Main proxy legacy readiness evidence"<<legacyReady<<legacyRoute<<legacyPoint<<legacySize<<clicked.count()<<fake->property("calls").toInt();
                            check(clicked.count()==1&&fake->property("calls").toInt()==1,"visible Main proxy accepts an immediate click while the previous page retires");
                            check(capsule->property("label").toString()==QStringLiteral("关闭代理")&&eval("AppState.currentPage==='activity'").toBool(),"immediate Main proxy action updates its label without navigation");
                            check(QTest::qWaitFor([&]{auto *active=host?qvariant_cast<QObject *>(host->property("activeLoader")):nullptr;return active&&active->property("routeId").toString()=="activity"&&!host->property("pendingGrab").toBool()&&!host->property("moving").toBool()&&capsule->isVisible()&&capsule->width()>0&&capsule->height()>0;},3500),"read-only Main proxy input test settles on Activity");
                            fake->setProperty("calls",0);
                            fake->setProperty("proxyRequested",false);
                            fake->setProperty("processAlive",false);
                            fake->property("systemProxy").value<QObject *>()->setProperty("owned",false);
                            fake->property("systemProxy").value<QObject *>()->setProperty("enabled",false);
                            fake->property("systemProxy").value<QObject *>()->setProperty("systemEnabled",false);
                            clicked.clear();
                            click("proxyCapsule");
                            check(clicked.count()==1&&fake->property("calls").toInt()==1,"real Main proxy pointer dispatches enable exactly once");
                            check(capsule->property("label").toString()==QStringLiteral("关闭代理"),"real Main proxy input updates observed action label");
                            click("proxyCapsule");
                            check(clicked.count()==2&&fake->property("calls").toInt()==2,"real Main proxy pointer dispatches disable exactly once");
                            check(capsule->property("label").toString()==QStringLiteral("开启代理"),"real Main proxy second input restores enable label");
                            check(eval("AppState.currentPage==='activity'").toBool(),"real Main proxy pointer input does not navigate");
                        }
                    }
                    check(capsule->property("controller")==originalController,"read-only Main proxy controller is restored");
                }
            }
            check(SystemProxySession::snapshot()==hostProxyBefore,"Main proxy pointer regression leaves host settings unchanged");
            check(controller->processId()==pidBefore&&controller->apiHealthy(),"Main proxy pointer regression leaves live Rust runtime unchanged");
            eval("AppState.navigate('proxies')");
            check(QTest::qWaitFor([&]{auto *active=host?qvariant_cast<QObject *>(host->property("activeLoader")):nullptr;return active&&active->property("routeId").toString()=="proxies"&&!host->property("moving").toBool()&&!host->property("pendingGrab").toBool();},3500),"read-only Main proxy input test returns to nodes");
        }
        if(qEnvironmentVariable("SWIRL_SYSTEM_PROXY_TEST")==QStringLiteral("1")) {
            const int failuresBefore=failures;
            eval("AppState.navigate('activity')");
            check(QTest::qWaitFor([&]{auto *active=host?qvariant_cast<QObject *>(host->property("activeLoader")):nullptr;auto *capsule=item("proxyCapsule");return active&&active->property("routeId").toString()=="activity"&&!host->property("pendingGrab").toBool()&&!host->property("moving").toBool()&&capsule&&capsule->isVisible()&&capsule->width()>0&&capsule->height()>0;},3500),"proxy action page settles before real input");
            auto *actualCapsule=item("proxyCapsule");
            QSignalSpy actualClicked(actualCapsule,SIGNAL(clicked()));
            check(actualClicked.isValid(),"actual proxy action clicked signal is observed");
            const auto savedSelection=controller->selectedNodeId();
            click("proxyCapsule");
            if(!check(QTest::qWaitFor([&]{return controller->canStart()&&!controller->systemProxy()->owned()&&!controller->systemProxyBusy();},10000),"activity master switch stops the live runtime and restores only its isolated proxy ownership"))return 2;
            check(proxyBackend->current().systemEnabled,"activity stop preserves the pre-existing external proxy instead of turning it off");
            check(!savedSelection.isEmpty()&&controller->selectedNodeId()==savedSelection,"one-click enable retains the configured node while stopped");
            actualClicked.clear();
            click("proxyCapsule");
            const bool firstEnabled=QTest::qWaitFor([&]{return controller->apiHealthy()&&controller->systemProxy()->owned()&&controller->systemProxy()->enabled()&&controller->systemProxy()->systemEnabled();},15000);
            const int firstEnableClicks=int(actualClicked.count());
            const QJsonObject firstEnableState{{"owned",controller->systemProxy()->owned()},{"enabled",controller->systemProxy()->enabled()},{"systemEnabled",controller->systemProxy()->systemEnabled()},
                {"busy",controller->busy()},{"systemProxyBusy",controller->systemProxyBusy()},{"apiHealthy",controller->apiHealthy()},
                {"processId",double(controller->processId().toLongLong())},{"activeProxyPort",controller->activeProxyPort()},{"errorCode",controller->errorCode()},
                {"proxyError",controller->systemProxy()->error()},{"routingError",controller->routingError()},{"stateReadError",controller->systemProxy()->stateReadError()}};
            qInfo()<<"Proxy UI first enable evidence"<<firstEnableClicks<<QJsonDocument(firstEnableState).toJson(QJsonDocument::Compact);
            check(firstEnableClicks==1,"actual proxy enable pointer reaches its clicked handler exactly once");
            if(check(firstEnabled,"activity master switch starts the saved Rust node and acquires isolated proxy ownership in one click")) {
                check(controller->selectedNodeId()==savedSelection&&controller->apiHealthy(),"activity enable retains the configured exit and confirms its live Rust runtime");
                check(eval("AppState.currentPage==='activity'").toBool(),"actual proxy enable does not navigate");
                click("proxyCapsule");
                check(QTest::qWaitFor([&]{return controller->canStart()&&!controller->systemProxy()->owned()&&!controller->systemProxyBusy();},10000),"activity master switch stops Rust and releases its own proxy session");
                check(eval("AppState.currentPage==='activity'").toBool(),"actual proxy disable does not navigate");
                const bool restored=proxyBackend->current().systemEnabled&&!proxyBackend->current().owned;
                if(check(restored,"activity stop restores the original external proxy entirely inside the sandbox")) {
                    check(!savedSelection.isEmpty()&&controller->selectedNodeId()==savedSelection,"one-click enable retains the configured node while stopped");
                    click("proxyCapsule");
                    check(QTest::qWaitFor([&]{return controller->apiHealthy()&&controller->systemProxy()->owned()&&controller->systemProxy()->enabled();},15000),"activity master switch restarts the saved node and isolated proxy in one click");
                    check(eval("AppState.currentPage==='activity'").toBool(),"cold proxy enable does not navigate to the node page");
                }
            }
            const auto reportPath=qEnvironmentVariable("SWIRL_SYSTEM_PROXY_UI_REPORT");
            QFile report(reportPath);
            if(check(!reportPath.isEmpty()&&report.open(QIODevice::WriteOnly),"isolated proxy UI evidence file opens"))
                report.write(QJsonDocument(QJsonObject{{"source_sha",QStringLiteral(SWIRL_SOURCE_SHA)},{"executed",true},{"backend","per-instance-memory"},{"restoration_observed",proxyBackend->restoreCalls>0},{"host_proxy_mutations",false},{"success",failures==failuresBefore},
                    {"first_enable_click_count",firstEnableClicks},{"first_enable_state",firstEnableState}}).toJson());
            eval("AppState.navigate('proxies')");QTest::qWait(350);
        }
        const auto pid=controller->processId();
        const auto selectedBeforeNavigation=controller->selectedNodeId();
        for(const auto &route:QStringList{"featurehub","settings","fonts","dns","modules","profiles","scripts","subscriptions","proxies"}){
            eval("AppState.navigate('"+route+"')");
            check(QTest::qWaitFor([&]{auto *active=host?qvariant_cast<QObject *>(host->property("activeLoader")):nullptr;return active&&active->property("routeId").toString()==route&&!host->property("moving").toBool()&&!host->property("pendingGrab").toBool();},3500),"live navigation settles inside the main host");
            check(controller->processId()==pid&&controller->apiHealthy()&&controller->selectedNodeId()==selectedBeforeNavigation,"all settings routes preserve the real running proxy and selected node");
        }
        select(1);
        const auto nodeB=eval("pageLoader.item.selectedId").toString();
        check(controller->selectedNodeId()==selectedBeforeNavigation&&controller->activeNodeId()==selectedBeforeNavigation&&controller->processId()==pid,"browsing node B leaves the real running exit A unchanged");
        eval("pageLoader.item.dismissDetail()");QTest::qWait(450);click("nodeRowFavorite-"+nodeB);
        check(controller->selectedNodeId()==selectedBeforeNavigation&&controller->activeNodeId()==selectedBeforeNavigation,"favoriting another resource does not change the real exit");
        check(eval(QString("pageLoader.item.resourceAt(1).favorite")).toBool(),"inline resource favorite reflects actual saved metadata");
        click("nodeRowMore-"+nodeB);
        check(item("nodeRowDetails-"+nodeB)&&item("nodeRowTest-"+nodeB)&&item("nodeRowCopy-"+nodeB),"node action menu exposes real details, request testing and safe-copy actions");
        click("nodeRowDetails-"+nodeB);
        check(QTest::qWaitFor([&]{auto *hero=item("nodeHero");return hero&&hero->property("opened").toBool()&&!hero->property("moving").toBool();},3500),"node row action opens its real details instead of a placeholder notice");
        check(eval("pageLoader.item.selectedId").toString()==nodeB&&controller->activeNodeId()==selectedBeforeNavigation,"row details preserve resource identity and the live exit");
        select(1);
        check(!controller->tests()->result(nodeB).value("success").toBool(),"new inspected node has no inherited request result");
        probeSelected(net.b,net.a,"independent node B test uses B while the live exit remains A");
        check(controller->activeNodeId()==selectedBeforeNavigation,"isolated test does not switch the live exit");
        const auto liveBeforeA=net.a.forwarded,liveBeforeB=net.b.forwarded;
        const auto liveReceipts=net.httpRequestsByExit;
        controller->testNode(liveUrl);
        check(QTest::qWaitFor([&]{return controller->requestSucceeded()&&!controller->nodeBusy();},8000)
            &&net.a.forwarded>liveBeforeA&&net.b.forwarded==liveBeforeB
            &&net.httpRequestsByExit.value(net.a.label)>liveReceipts.value(net.a.label)
            &&net.httpRequestsByExit.value("DIRECT-BYPASS")==liveReceipts.value("DIRECT-BYPASS"),
            "the actual live runtime still forwards through A after browsing and testing B");
        choosePolicy(nodeB,false);select(1);
        check(QTest::qWaitFor([&]{return !controller->nodeBusy();},5000)&&controller->activeNodeId()==nodeB&&controller->processId()==pid,"policy selection switches real exit without restarting");
        probeSelected(net.b,net.a,"UI new requests use authenticated selected node B");
        check(item("nodeRequestState")&&item("nodeRequestState")->property("text").toString().contains("成功"),"visible request state follows actual result");
        choosePolicy(nodeB,true);select(1);
        check(QTest::qWaitFor([&]{return controller->canStart();},4000)&&!controller->processAlive(),"UI disconnect reaps engine");
    }
    check(!controller->requestSucceeded() && controller->requestStateText()==QStringLiteral("尚未发起实际请求"),"disconnect clears stale request success text");
    choosePolicy(nodeA,false);const auto lastActiveBeforeEdit=controller->activeNodeId();
    select(1);click("nodeEditButton");check(item("nodePasswordField")&&item("nodePasswordField")->property("text").toString().isEmpty(),"editing never reveals stored credentials");fill("nodeNameField","B edited");click("nodeSaveButton");check(controller->nodes().last().toMap().value("name").toString()=="B edited","UI edits saved metadata");
    check(controller->selectedNodeId()==nodeA&&controller->activeNodeId()==lastActiveBeforeEdit&&!controller->processAlive(),"editing resource B preserves the configured exit A and stopped runtime snapshot");
    click("nodeDeleteButton");check(controller->nodes().size()==1,"UI deletes selected node");select(0);click("nodeDeleteButton");check(controller->nodes().isEmpty(),"UI removes all saved test nodes");
    controller->stop();check(QTest::qWaitFor([&]{return !controller->processAlive();},4000),"test cleanup reaps engine");
    QTcpServer reuse;check(reuse.listen(QHostAddress::LocalHost,controller->proxyPort()),"disconnected proxy port is reusable");reuse.close();
    click("nodeImportButton");
    fill("importContentField",QStringLiteral("proxies: ["));click("importApplyButton");
    check(QTest::qWaitFor([&]{return !controller->imports()->busy();},4000) && controller->nodes().isEmpty(),"UI import rejects invalid YAML without modifying stored nodes");
    fill("importContentField",QStringLiteral("proxies: [{name: Imported, type: socks5, server: 127.0.0.1, port: %1}]").arg(net.a.serverPort()));click("importApplyButton");
    check(QTest::qWaitFor([&]{return !controller->imports()->busy();},4000) && controller->nodes().size()==1,"UI one-click import saves an actual controlled proxy configuration");
    check(item("importContentField") && item("importContentField")->property("text").toString().isEmpty(),"import clears credential-bearing input after submission");
    auto *dialog=window->findChild<QObject *>("nodeImportDialog");if(dialog)QMetaObject::invokeMethod(dialog,"close");QTest::qWait(350);
    select(0);const auto importedId=eval("pageLoader.item.selectedId").toString();choosePolicy(importedId,true);select(0);
    check(waitEngineReady(),"UI imported node starts real Rust Core");
    fill("nodeTestUrl",net.url().toString());click("nodeTestButton");
    check(QTest::qWaitFor([&]{return !controller->tests()->busy();},41000) && controller->tests()->result(controller->selectedNodeId()).value("success").toBool(),"UI imported node forwards a real HTTP request");
    controller->stop();check(QTest::qWaitFor([&]{return !controller->processAlive();},4000),"UI imported node cleanup reaps owned engine");
    const auto importedNodes=controller->nodes();
    if(importedNodes.isEmpty()) {
        const auto reason=controller->imports()->message().toUtf8();
        std::fprintf(stderr,"NODE_UI_IMPORT_MISSING: %s\n",reason.constData());
        return failures?failures:1;
    }
    const auto importedFixtureId=importedNodes.first().toMap().value("id").toString();
    check(controller->deleteNode(importedFixtureId)&&QTest::qWaitFor([&]{return !controller->policyBusy()&&controller->nodes().isEmpty();},10000),"controlled import cleanup waits for committed removal");
    // Exercise the actual subscription form against an isolated HTTPS server.
    // Only synthetic fixture data enters this temporary DPAPI store.
    QSslServer subscriptions;subscriptions.setSslConfiguration(net.https.sslConfiguration());
    const auto previousSsl=QSslConfiguration::defaultConfiguration();
    struct RestoreSsl{QSslConfiguration value;~RestoreSsl(){QSslConfiguration::setDefaultConfiguration(value);}} restoreSsl{previousSsl};
    auto trustedSsl=previousSsl;trustedSsl.addCaCertificate(net.certificate);QSslConfiguration::setDefaultConfiguration(trustedSsl);
    int subscriptionRequests=0;
    QObject::connect(&subscriptions,&QTcpServer::pendingConnectionAvailable,&subscriptions,[&]{while(subscriptions.hasPendingConnections()){
        auto *socket=subscriptions.nextPendingConnection();
        QObject::connect(socket,&QTcpSocket::readyRead,socket,[&,socket]{
            socket->readAll();if(socket->property("responded").toBool())return;socket->setProperty("responded",true);++subscriptionRequests;
            const auto content=QString("proxies: [{name: %2 fixture, type: socks5, server: 127.0.0.1, port: %1}]\nproxy-groups: [{name: fixture-route, type: select, proxies: ['%2 fixture']}]\nrules: ['MATCH,fixture-route']\n").arg(net.a.serverPort()).arg(subscriptionRequests==1?"HK":"JP").toUtf8();
            QTimer::singleShot(600,socket,[socket,content]{socket->write("HTTP/1.1 200 OK\r\nContent-Length: "+QByteArray::number(content.size())+"\r\nConnection: close\r\n\r\n"+content);socket->disconnectFromHost();});
        });
        QObject::connect(socket,&QTcpSocket::disconnected,socket,&QObject::deleteLater);
    }});
    check(subscriptions.listen(QHostAddress::LocalHost,0),"subscription HTTPS fixture listens");
    eval("AppState.navigate('subscriptions')");QTest::qWait(350);
    click("addSubscription");fill("subscriptionName","Subscription fixture");fill("subscriptionUrl",QString("https://localhost:%1/fixture").arg(subscriptions.serverPort()));click("saveSubscription");
    const auto pendingProviders=controller->imports()->providers();
    if(!pendingProviders.isEmpty()){
        auto *badge=item("subscriptionStatus-"+pendingProviders.first().toMap().value("id").toString());
        check(badge&&badge->property("busy").toBool()==controller->imports()->busy(),"subscription indicator reflects the actual pending operation");
    }
    const auto businessQa=qEnvironmentVariable("SWIRL_UI_QA_DIRECTORY");
    if(!businessQa.isEmpty()) {
        QDir().mkpath(businessQa+"/business-frames");
        for(int frame=0;frame<25;++frame){QTest::qWait(40);window->grabWindow().scaledToWidth(1000,Qt::SmoothTransformation).save(businessQa+QString("/business-frames/%1.png").arg(frame,3,10,QChar('0')));}
    }
    check(QTest::qWaitFor([&]{return !controller->imports()->busy();},8000)&&controller->imports()->providers().size()==1&&controller->nodes().size()==1&&subscriptionRequests==1,"subscription UI saves HTTPS source and imports an actual node");
    if(!controller->imports()->providers().isEmpty()){
        auto *badge=item("subscriptionStatus-"+controller->imports()->providers().first().toMap().value("id").toString());
        check(badge&&!badge->property("busy").toBool()&&badge->property("tone").toString()=="success","subscription success follows completed storage and stops busy motion");
    }
    eval("AppState.navigate('proxies')");QTest::qWait(350);
    check(eval("pageLoader.item.countries.length===1 && pageLoader.item.countries[0].code==='HK'").toBool(),"country filter contains only the imported subscription's actual Hong Kong label");
    eval("pageLoader.item.countryCode='HK'");
    check(eval("pageLoader.item.resultCount===1").toBool(),"country filter combines with the real imported node list");
    const auto subscriptionSource=controller->imports()->providers().first().toMap().value("id").toString();
    check(controller->saveNode({{"name","JP manual HTTP"},{"protocol","http"},{"host","127.0.0.1"},{"port",9}}),"manual node adds a second region outside the subscription");
    check(QTest::qWaitFor([&]{return !controller->policyBusy()&&controller->nodes().size()==2;},10000),"manual filter fixture waits for its actual saved catalog");
    const auto manualId=controller->nodes().last().toMap().value("id").toString();
    check(eval("pageLoader.item.countries.length===2").toBool(),"all sources exposes both actual regions");
    eval("pageLoader.item.countryCode='JP'");
    check(eval("pageLoader.item.resultCount===1").toBool(),"Japan selection shows only the manual Japan node");
    fill("nodeSearchField","manual");QTest::qWait(150);
    auto *protocol=item("proxyRegionCombo");if(protocol)protocol->setProperty("currentIndex",controller->supportedProtocols().indexOf("http")+1);eval("pageLoader.item.protocol=\"http\"");
    check(eval("pageLoader.item.resultCount===1").toBool(),"search, protocol and country filters compose");
    fill("nodeSearchField","unmatched");QTest::qWait(150);check(eval("pageLoader.item.resultCount===0").toBool(),"combined filters never leak unmatched nodes");
    fill("nodeSearchField","");QTest::qWait(150);if(protocol)protocol->setProperty("currentIndex",0);eval("pageLoader.item.protocol=\"\"");
    eval(QString("pageLoader.item.sourceId='%1'").arg(subscriptionSource));
    check(eval("pageLoader.item.countries.length===1 && pageLoader.item.countries[0].code==='HK' && pageLoader.item.countryCode==='' && pageLoader.item.resultCount===1").toBool(),"switching subscription scopes countries and clears a country absent from that source");
    check(controller->deleteNode(manualId),"remove manual filter fixture");
    check(QTest::qWaitFor([&]{return !controller->policyBusy()&&controller->nodes().size()==1;},10000),"manual filter fixture removal is committed before source refresh");
    eval("pageLoader.item.countryCode='HK'");
    eval("AppState.navigate('subscriptions')");QTest::qWait(350);
    if(!controller->imports()->providers().isEmpty()) {
        const auto id=controller->imports()->providers().first().toMap().value("id").toString();
        QPointer<QQuickItem> card=item("subscriptionCard-"+id);
        const auto qa=qEnvironmentVariable("SWIRL_UI_QA_DIRECTORY");
        if(!qa.isEmpty())QDir().mkpath(qa);
        const auto collapsedHeight=card?card->height():0;
        check(card&&collapsedHeight<=100*eval("Theme.uiScale").toReal(),"subscription source uses a compact list row instead of a dashboard card");
        const auto originalSize=window->size();
        window->resize(window->minimumWidth(),window->minimumHeight());QTest::qWait(250);
        auto *title=item("subscriptionTitle-"+id),*refresh=item("refreshSubscription-"+id),*more=item("moreSubscription-"+id);
        check(title&&title->width()>=60*eval("Theme.uiScale").toReal(),"subscription title keeps readable width at minimum window size");
        check(refresh&&more&&refresh->isVisible()&&refresh->isEnabled()&&more->isVisible()&&more->isEnabled(),"subscription actions stay visible and enabled at minimum window size");
        if(title&&refresh&&more){
            const QRectF bounds(0,0,window->width(),window->height());
            const QRectF titleRect(title->mapToScene(QPointF()),title->size()),refreshRect(refresh->mapToScene(QPointF()),refresh->size()),moreRect(more->mapToScene(QPointF()),more->size());
            check(bounds.contains(titleRect)&&bounds.contains(refreshRect)&&bounds.contains(moreRect)&&!titleRect.intersects(refreshRect)&&!titleRect.intersects(moreRect)&&!refreshRect.intersects(moreRect),"subscription title and actions remain inside the minimum window without overlap");
        }
        if(!qa.isEmpty())window->grabWindow().save(qa+"/subscription-minimum.png");
        window->resize(originalSize);QTest::qWait(250);
        click("moreSubscription-"+id);QTest::qWait(250);
        if(!qa.isEmpty())window->grabWindow().save(qa+"/subscription-menu.png");
        QTest::keyClick(window,Qt::Key_Escape);
        check(QTest::qWaitFor([&]{auto *action=item("editSubscription-"+id);return !action||!action->isVisible();},3000),"subscription action menu closes before continuing source interactions");
        click("expandSubscription-"+id);
        check(card&&card->height()>collapsedHeight,"subscription details animate open without replacing the card");
        click("moreSubscription-"+id);click("editSubscription-"+id);QTest::qWait(250);
        if(!qa.isEmpty())window->grabWindow().save(qa+"/subscription-edit.png");
        check(item("subscriptionUrl")&&item("subscriptionUrl")->property("text").toString().isEmpty(),"editing subscription keeps its protected URL hidden");
        fill("subscriptionName","Edited subscription fixture");click("saveSubscription");
        check(QTest::qWaitFor([&]{return !controller->imports()->busy();},8000)&&controller->imports()->providers().first().toMap().value("name").toString()=="Edited subscription fixture"&&subscriptionRequests==2,"editing preserves encrypted URL and refreshes the real source");
        check(card&&item("subscriptionCard-"+id)==card,"subscription refresh keeps the same card delegate and expanded state");
        eval("AppState.navigate('proxies')");QTest::qWait(350);
        check(eval("pageLoader.item.countries.length===1 && pageLoader.item.countries[0].code==='JP' && pageLoader.item.countryCode==='' && pageLoader.item.resultCount===1").toBool(),"subscription refresh replaces country options and clears an obsolete country selection");
        eval("AppState.navigate('subscriptions')");QTest::qWait(350);
        if(!qa.isEmpty()){QDir().mkpath(qa);window->grabWindow().save(qa+"/subscription-success.png");}
        const auto policyBeforeReview=controller->policyDocument();
        click("moreSubscription-"+id);QTest::keyClick(window,Qt::Key_Escape);QTest::qWait(200);
        check(QTest::qWaitFor([&]{auto *action=item("editSubscription-"+id);return !action||!action->isVisible();},3000),"Escape closes the source action menu");
        check(controller->imports()->providers().size()==1,"source more menu can be dismissed without changing its data");
        click("moreSubscription-"+id);click("reviewSubscription-"+id);
        check(QTest::qWaitFor([&]{return controller->imports()->hasConfigurationReview();},3000),"explicit source review opens the actual encrypted cached configuration preview");
        check(controller->policyDocument()==policyBeforeReview&&!controller->policyBusy()&&!controller->imports()->configurationReview().value("changes").toList().isEmpty(),"configuration review describes differences without applying foreign policy");
        if(!qa.isEmpty())window->grabWindow().save(qa+"/subscription-configuration-review.png");
        QTest::keyClick(window,Qt::Key_Escape);
        check(QTest::qWaitFor([&]{return !controller->imports()->hasConfigurationReview();},3000)&&controller->policyDocument()==policyBeforeReview,"Escape discards the one-use review without changing routing");
        fill("subscriptionSearch","no matching source");QTest::qWait(200);
        check(eval("pageLoader.item.listed.length===0").toBool(),"subscription search presents the genuine empty result state");
        fill("subscriptionSearch","");QTest::qWait(200);
        check(eval("pageLoader.item.listed.length===1").toBool(),"clearing source search restores the real subscription");
        subscriptions.close();click("refreshSubscription-"+id);
        check(QTest::qWaitFor([&]{return !controller->imports()->busy();},8000)&&!controller->imports()->providers().first().toMap().value("error").toString().isEmpty()&&controller->nodes().size()==1,"failed real refresh displays an error and retains imported nodes");
        if(!qa.isEmpty())window->grabWindow().save(qa+"/subscription-failure.png");
        click("moreSubscription-"+id);click("deleteSubscription-"+id);QTest::keyClick(window,Qt::Key_Escape);QTest::qWait(250);
        check(controller->imports()->providers().size()==1,"Escape cancels destructive subscription confirmation");
        click("moreSubscription-"+id);click("deleteSubscription-"+id);click("confirmSubscriptionDelete");
        check(QTest::qWaitFor([&]{return !controller->imports()->busy()&&!controller->policyBusy()&&controller->imports()->providers().isEmpty()&&controller->nodes().isEmpty();},10000),"confirmed deletion removes the source's owned nodes after commit and revocation receipt");
    }
    // Large-list layout/transfer fixture uses reserved local endpoints only.
    QString batch="proxies:\n";
    for(int i=0;i<180;++i)batch+=QString("  - {name: 'Node %1 long readable name', type: http, server: 127.0.0.1, port: %2}\n").arg(i,3,10,QChar('0')).arg(26000+i);
    controller->imports()->importText(batch);
    check(QTest::qWaitFor([&]{return !controller->imports()->busy();},8000)&&controller->nodes().size()==180,"180-node fixture imported");
    eval("AppState.navigate('proxies');Theme.reduceMotion=false");QTest::qWait(400);
    window->resize(window->minimumWidth(),window->minimumHeight());QTest::qWait(250);
    auto *table=item("realNodeTable"),*hero=item("nodeHero");
    check(table&&table->property("gridWidth").toReal()<=table->width()+1,"all four columns fit minimum-width node viewport");
    if(table&&hero){
        // A partially clipped row in both axes must never fly from its full rect.
        QQuickItem clipper(table);clipper.setClip(true);clipper.setSize(QSizeF(100,80));clipper.setPosition(QPointF(10,10));
        QQuickItem row(&clipper);row.setPosition(QPointF(-40,-10));row.setSize(QSizeF(200,60));
        QVariant result;QMetaObject::invokeMethod(hero,"sourceRect",Q_RETURN_ARG(QVariant,result),Q_ARG(QVariant,QVariant::fromValue(&row)));
        const auto rect=result.toRectF();check(qAbs(rect.width()-100)<1&&qAbs(rect.height()-50)<1,"node flight intersects horizontal and vertical clipping ancestors");
        clipper.setVisible(false);
        QMetaObject::invokeMethod(hero,"sourceRect",Q_RETURN_ARG(QVariant,result),Q_ARG(QVariant,QVariant::fromValue(&row)));
        check(result.toRectF()!=rect,"invisible row uses explicit fallback origin");
        clipper.setVisible(true);QMetaObject::invokeMethod(hero,"start",Q_ARG(QVariant,QVariant::fromValue(&row)));QTest::qWait(45);
        const auto reveal=hero->property("reveal").toReal();
        QMetaObject::invokeMethod(hero,"returnTo",Q_ARG(QVariant,QVariant::fromValue(&row)));
        check(qAbs(hero->property("retargetRequestedReveal").toReal()-hero->property("retargetCommittedReveal").toReal())<0.001,"node reversal preserves content opacity at the handler handoff");
        QTest::qWait(30);const auto closingReveal=hero->property("reveal").toReal();
        QMetaObject::invokeMethod(hero,"start",Q_ARG(QVariant,QVariant::fromValue(&row)));
        check(qAbs(hero->property("retargetRequestedReveal").toReal()-hero->property("retargetCommittedReveal").toReal())<0.001,"node reopen preserves partially revealed content at the handler handoff");
        QTest::qWait(400);
    }
    const auto qa=qEnvironmentVariable("SWIRL_UI_QA_DIRECTORY");
    eval("pageLoader.item.dismissDetail()");
    check(QTest::qWaitFor([&]{return hero&&!hero->property("opened").toBool()&&!hero->property("moving").toBool();},3500),"node library is visible before source-list capture");
    if(!qa.isEmpty()){QDir().mkpath(qa);window->grabWindow().save(qa+"/nodes-minimum-180.png");}
    for(int i=0;i<180;++i){
        auto *viewport=item("tableRowsViewport");
        if(viewport)QMetaObject::invokeMethod(viewport,"positionViewAtIndex",Q_ARG(int,i),Q_ARG(int,0));
        QTest::qWait(5);
        eval(QString("pageLoader.item.inspectRow(engineController.nodes[%1])").arg(i));
    }
    check(QTest::qWaitFor([&]{return hero&&!hero->property("moving").toBool();},3500),"180 rapid node selections settle");
    check(eval("pageLoader.item.selected.name.indexOf('179')>=0").toBool(),"last of 180 rapid detail retargets retains its selected node");
    auto *identity=item("nodeIdentitySurface");
    check(identity&&identity->parentItem()!=hero->parentItem(),"settled node details return to scroll ownership");
    if(!qa.isEmpty())window->grabWindow().save(qa+"/nodes-selected-minimum.png");
    qInfo()<<"Node UI checks:"<<checks<<"checks,"<<failures<<"failures";return failures?2:0;
}
