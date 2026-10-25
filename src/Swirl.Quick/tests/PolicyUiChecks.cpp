#include "PolicyUiChecks.h"
#include "ControlledNetwork.h"
#include "LoopbackPortLease.h"
#include "SwirlBuildIdentity.h"
#include "engine/EngineController.h"
#include <QDir>
#include <QFile>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QQmlContext>
#include <QQmlExpression>
#include <QQmlProperty>
#include <QQuickItem>
#include <QQuickWindow>
#include <QSignalSpy>
#include <QTest>
#include <algorithm>
#include <functional>

int runPolicyUiChecks(QQuickWindow *window,EngineController *controller,const QString &directory) {
    if(!window||!controller)return 1;
    QJsonArray checks;int failures=0;
    const auto check=[&](bool passed,const QString &name){checks.append(QJsonObject{{"name",name},{"passed",passed}});if(!passed)++failures;qInfo()<<(passed?"PASS":"FAIL")<<name;return passed;};
    std::function<QQuickItem *(QQuickItem *,const QString &)> find;
    find=[&](QQuickItem *parent,const QString &name)->QQuickItem *{if(parent->objectName()==name&&parent->isVisible())return parent;for(auto *child:parent->childItems())if(auto *found=find(child,name))return found;return nullptr;};
    // ListView delegates can have a visual parent distinct from their QObject
    // parent. Include objects attached to that visual tree when locating popups.
    const auto namedObjects=[&](const QString &name){
        auto matches=window->findChildren<QObject *>(name);
        std::function<void(QQuickItem *)> collect=[&](QQuickItem *parent){
            for(auto *object:parent->findChildren<QObject *>(name))if(!matches.contains(object))matches.append(object);
            for(auto *child:parent->childItems())collect(child);
        };
        collect(window->contentItem());return matches;
    };
    const auto item=[&](const QString &name){
        if(auto *found=find(window->contentItem(),name))return found;
        for(auto *object:namedObjects(name))if(auto *candidate=qobject_cast<QQuickItem *>(object);candidate&&candidate->isVisible()&&candidate->window())return candidate;
        return static_cast<QQuickItem *>(nullptr);
    };
    const auto popup=[&](const QString &name)->QObject *{for(auto *object:namedObjects(name))if(object->property("visible").toBool())return object;return nullptr;};
    const auto eval=[&](const QString &source){QQmlExpression expression(qmlContext(window),window,source);auto value=expression.evaluate();check(!expression.hasError(),QStringLiteral("QML expression is valid"));return value;};
    const auto reachable=[&](QQuickItem *target){
        if(!target||!target->isVisible()||!target->isEnabled()||target->width()<=0||target->height()<=0)return false;
        qreal opacity=1;const auto point=target->mapToScene(QPointF(target->width()/2,target->height()/2));
        for(auto *ancestor=target;ancestor;ancestor=ancestor->parentItem()){opacity*=ancestor->opacity();if(ancestor->clip()&&!QRectF(ancestor->mapToScene(QPointF()),ancestor->size()).contains(point))return false;}
        auto *surface=target->window();
        return surface&&opacity>0.95&&QRectF(0,0,surface->width(),surface->height()).contains(point);
    };
    const auto click=[&](const QString &name){
        auto *target=item(name);if(target){target->forceActiveFocus();QTest::qWait(45);}
        if(!check(QTest::qWaitFor([&]{return reachable(item(name));},3500),QStringLiteral("Input is reachable: ")+name)){
            for(auto *object:namedObjects(name))if(auto *candidate=qobject_cast<QQuickItem *>(object))qInfo()<<"Unreachable fixture control"<<name<<candidate->isVisible()<<candidate->isEnabled()<<candidate->size()<<candidate->opacity()<<candidate->window();
            if(!directory.isEmpty()){QDir().mkpath(directory);window->grabWindow().save(directory+"/input-failure.png");}
            return false;
        }
        target=item(name);QTest::mouseClick(target->window(),Qt::LeftButton,Qt::NoModifier,target->mapToScene(QPointF(target->width()/2,target->height()/2)).toPoint());QTest::qWait(100);
        if(name.startsWith("servicePolicyMore-")||name.startsWith("policyGroupMore-"))for(auto *menu:namedObjects("swirlContextMenu"))qInfo()<<"Fixture menu state"<<menu->property("visible")<<menu->property("count")<<menu->property("popupType");
        return true;
    };
    const auto fill=[&](const QString &name,const QString &text){auto *field=item(name);if(!check(field!=nullptr,QStringLiteral("Field exists: ")+name))return false;if(!check(std::all_of(text.cbegin(),text.cend(),[](QChar character){return character.unicode()<128;}),QStringLiteral("Keyboard fixture contains only ASCII input")))return false;field->forceActiveFocus();QTest::qWait(45);QTest::keyClick(window,Qt::Key_A,Qt::ControlModifier);for(const auto character:text)QTest::keyClick(window,character.toLatin1());return true;};
    const auto finish=[&]{controller->stop();check(QTest::qWaitFor([&]{return !controller->processAlive()&&!controller->policyBusy();},10000),QStringLiteral("Owned runtime and transaction finish before cleanup"));if(!directory.isEmpty()){QDir().mkpath(directory);QFile report(directory+"/policy-ui.json");if(!report.open(QIODevice::WriteOnly))return 3;report.write(QJsonDocument(QJsonObject{{"source_sha",QStringLiteral(SWIRL_SOURCE_SHA)},{"checks",checks},{"failures",failures},{"scope","Isolated real Qt input, committed policy receipts, Rust runtime and controlled loopback peers. No private-provider, host proxy, TUN or DNS mutations."}}).toJson());}return failures?2:0;};
    const auto document=[&]{return controller->policyDocument();};
    const auto recordNamed=[](const QVariantList &rows,const QString &name){for(const auto &value:rows){const auto row=value.toMap();if(row.value("name")==name)return row;}return QVariantMap{};};
    QString lastSavedRequest=controller->policyReceipt().value("request_id").toString();
    const auto awaitSaved=[&](const QString &label){
        const auto issued=controller->policyRequestId();
        const bool ready=!issued.isEmpty()&&issued!=lastSavedRequest&&QTest::qWaitFor([&]{return !controller->policyBusy()&&controller->policyApplyState()==QStringLiteral("idle")&&controller->policyReceipt().value("request_id")==issued;},12000);
        const bool settled=ready&&QTest::qWaitFor([&]{for(const auto &name:QStringList{"policyTargetPicker","servicePolicyDialog","policyGroupDialog","deletePolicyDialog","policyMigrationDialog"})if(popup(name))return false;return true;},4000);
        if(!ready||!settled||!controller->policyError().isEmpty()){
            qInfo()<<"Policy transaction evidence"<<controller->policyApplyState()<<controller->policyError()<<"modalExitSettled"<<settled;
            for(const auto &name:QStringList{"policyGroupMessage","servicePolicyMessage","policyApplyMessage"})if(auto *message=item(name))qInfo()<<"Fixture validation message"<<name<<message->property("text");
        }
        if(ready)lastSavedRequest=issued;
        return check(ready&&settled&&controller->policyError().isEmpty(),label);
    };
    const auto chooseTarget=[&](const QString &kind,const QString &id){
        if(auto *tabs=item("policyTargetTabs")){QTest::mouseClick(window,Qt::LeftButton,Qt::NoModifier,tabs->mapToScene(QPointF(tabs->width()*(kind=="group"?0.75:0.25),tabs->height()/2)).toPoint());QTest::qWait(60);}
        if(!click(kind=="node"?"policyNode-"+id:"policyTarget-group-"+id)||!click("confirmPolicyTarget"))return false;
        return check(QTest::qWaitFor([&]{return !popup("policyTargetPicker");},12000),QStringLiteral("Target picker releases its modal grab after actual completion"));
    };
    const auto setTab=[&](int index){auto *tabs=item("policyTabs");if(!check(tabs!=nullptr,QStringLiteral("Policy tabs exist")))return;QTest::mouseClick(window,Qt::LeftButton,Qt::NoModifier,tabs->mapToScene(QPointF(tabs->width()*(index?0.75:0.25),tabs->height()/2)).toPoint());QTest::qWait(100);check(eval("pageLoader.item.tabIndex").toInt()==index,QStringLiteral("Real segmented input selects requested policy tab"));};
    const auto setCombo=[&](const QString &name,int index){
        if(!click(name))return;
        auto *control=item(name);auto *listPopup=control?qvariant_cast<QObject *>(control->property("popup")):nullptr;
        if(!check(listPopup&&listPopup->property("visible").toBool(),QStringLiteral("Native combo popup opens: ")+name))return;
        if(!click("swirlComboOption-"+QString::number(index)))return;
        check(QTest::qWaitFor([&]{return !listPopup->property("visible").toBool();},1500),QStringLiteral("Native combo choice releases its popup: ")+name);
        check(QTest::qWaitFor([&]{return item(name)&&item(name)->property("currentIndex").toInt()==index;},12000),QStringLiteral("Native combo selection is committed: ")+name);
    };
    ControlledNetwork net;if(!check(net.start(),QStringLiteral("Controlled real proxy peers and HTTP origin start")))return finish();
    const QString defaultDomain=QStringLiteral("default.policy.fixture.invalid"),serviceDomain=QStringLiteral("service.policy.fixture.invalid"),childDomain="sub."+serviceDomain;net.a.aliases={defaultDomain,serviceDomain,childDomain};net.b.aliases=net.a.aliases;
    auto defaultUrl=net.url();defaultUrl.setHost(defaultDomain);auto serviceUrl=net.url();serviceUrl.setHost(serviceDomain);auto childUrl=net.url();childUrl.setHost(childDomain);
    check(controller->saveNode({{"name","Policy fixture A"},{"protocol","socks5"},{"host","127.0.0.1"},{"port",net.a.serverPort()}}),QStringLiteral("Setup stores isolated node A"));
    check(controller->saveNode({{"name","Policy fixture B"},{"protocol","socks5"},{"host","127.0.0.1"},{"port",net.b.serverPort()},{"username",QString::fromUtf8(net.b.username)},{"password",QString::fromUtf8(net.b.password)}}),QStringLiteral("Setup stores isolated authenticated node B"));
    const auto nodes=controller->nodes();if(!check(nodes.size()==2,QStringLiteral("Exactly two isolated nodes exist")))return finish();const auto nodeA=nodes[0].toMap().value("id").toString(),nodeB=nodes[1].toMap().value("id").toString();
    window->resize(1080,760);eval("AppState.navigate('policies')");
    auto *host=window->findChild<QObject *>("pageLoader");
    if(!check(QTest::qWaitFor([&]{auto *active=host?qvariant_cast<QObject *>(host->property("activeLoader")):nullptr;return active&&active->property("routeId")=="policies"&&!host->property("moving").toBool()&&!host->property("pendingGrab").toBool();},5000),QStringLiteral("Real policy page settles")))return finish();
    QTest::qWait(150);QSignalSpy applied(controller,&EngineController::policyApplyFinished);check(applied.isValid(),QStringLiteral("Configuration completion signal is observable"));
    if(controller->policyMigrationRequired()){
        const auto legacyDocument=controller->policyDocument();
        eval("AppState.navigate('activity')");
        check(QTest::qWaitFor([&]{return item("activityOutboundMode")&&!host->property("moving").toBool();},5000),QStringLiteral("Activity keeps its outbound mode control in the existing facts row"));
        auto *legacyMode=item("activityOutboundMode");
        check(legacyMode&&!legacyMode->property("editable").toBool(),QStringLiteral("Activity mode refuses changes before explicit legacy migration"));
        if(legacyMode){QQmlExpression attempt(qmlContext(legacyMode),legacyMode,"requestMode('global')");check(!attempt.evaluate().toBool()&&!attempt.hasError()&&controller->policyDocument()==legacyDocument&&!controller->policyBusy(),QStringLiteral("Rejected legacy activity mode leaves saved configuration unchanged"));}
        eval("AppState.navigate('policies')");
        check(QTest::qWaitFor([&]{return item("reviewPolicyMigration")&&!host->property("moving").toBool();},5000),QStringLiteral("Migration remains an explicit policy-page action"));
    }
    if(controller->policyMigrationRequired()){click("reviewPolicyMigration");click("confirmPolicyMigration");if(!awaitSaved(QStringLiteral("Legacy migration is explicitly reviewed before changes")))return finish();}
    check(!controller->processMatchingAvailable(),QStringLiteral("Application process matching is truthfully unavailable"));
    click("defaultPolicyTarget");check(item("policyDirectTarget")==nullptr,QStringLiteral("Default proxy target picker excludes DIRECT"));chooseTarget("node",nodeA);
    if(!awaitSaved(QStringLiteral("Default node A is durably saved through real input")))return finish();
    check(controller->defaultPolicy().value("id")=="policy:default"&&controller->defaultPolicy().value("target").toMap().value("id")==nodeA,QStringLiteral("Permanent default policy holds stable identity and selected node"));
    check(!controller->processAlive()&&controller->appliedRevision().isEmpty()&&!controller->policyReceipt().contains("applied_revision")&&controller->policyReceipt().value("scope")=="saved-next-connect",QStringLiteral("Offline save never claims an applied runtime revision"));
    setCombo("routingModePicker",1);if(!awaitSaved(QStringLiteral("Global mode is saved through the real mode control")))return finish();
    LoopbackPortLease ports;if(!check(ports.reserve(),QStringLiteral("Dedicated mixed proxy and control ports are reserved")))return finish();controller->setProxyPort(ports.proxyPort());ports.release();click("policyConnectButton");
    if(!check(QTest::qWaitFor([&]{return controller->apiHealthy()&&!controller->policyBusy();},15000),QStringLiteral("Configured default starts the actual Rust runtime")))return finish();
    const auto liveEpoch=controller->policyReceipt().value("engine_epoch").toString();
    check(!liveEpoch.isEmpty(),QStringLiteral("Live receipt reports the actual runtime epoch"));
    const auto request=[&](const QUrl &url,SocksPeer *expected,const QString &label){
        const auto before=net.httpRequestsByExit;const auto beforeA=net.a.forwarded,beforeB=net.b.forwarded;controller->testNode(url);
        const bool finished=QTest::qWaitFor([&]{return !controller->nodeBusy()&&net.httpRequests>0&&(net.httpRequestsByExit!=before);},10000);
        const auto marker=expected?expected->label:QStringLiteral("DIRECT-BYPASS");
        bool route=finished&&controller->requestSucceeded()&&net.httpRequestsByExit.value(marker)>before.value(marker);
        if(expected)route=route&&net.httpRequestsByExit.value("DIRECT-BYPASS")==before.value("DIRECT-BYPASS")&&(expected==&net.a?net.b.forwarded==beforeB:net.a.forwarded==beforeA);
        else route=route&&net.a.forwarded==beforeA&&net.b.forwarded==beforeB;
        if(!route)qInfo()<<"Actual policy route evidence"<<controller->requestStateText()<<net.httpRequestsByExit;return check(route,label);
    };
    request(defaultUrl,&net.a,QStringLiteral("Global default A reaches origin through A, without direct bypass"));
    click("defaultPolicyTarget");chooseTarget("node",nodeB);if(!awaitSaved(QStringLiteral("Running default change receives a real commit and apply receipt")))return finish();
    check(controller->policyReceipt().value("engine_epoch").toString()==liveEpoch&&controller->appliedRevision()==controller->savedRevision(),QStringLiteral("Hot default switch preserves runtime epoch and matches saved/applied revisions"));
    request(defaultUrl,&net.b,QStringLiteral("New requests after the acknowledged default switch use B"));
    const auto addService=[&](const QString &name,const QString &domain,const QString &target){click("addServicePolicy");check(item("serviceMatchType")&&item("serviceMatchType")->property("count").toInt()==1,QStringLiteral("Unsupported application matching cannot be selected in the service form"));fill("servicePolicyName",name);fill("serviceDomainValue",domain);click("addServiceDomain");click("servicePolicyTarget");chooseTarget("node",target);click("saveServicePolicy");return awaitSaved(QStringLiteral("Service policy is committed from its real form"));};
    if(!addService("Dedicated fixture",serviceDomain,nodeA))return finish();
    const auto service=recordNamed(controller->servicePolicies(),"Dedicated fixture");const auto serviceId=service.value("id").toString();check(!serviceId.isEmpty(),QStringLiteral("New service receives a stable UUID"));
    setCombo("routingModePicker",0);if(!awaitSaved(QStringLiteral("Rule mode is acknowledged before service routing checks")))return finish();
    request(defaultUrl,&net.b,QStringLiteral("Unclassified rule traffic uses the default B"));request(serviceUrl,&net.a,QStringLiteral("Configured dedicated service uses A while ordinary traffic stays on B"));request(net.url(),nullptr,QStringLiteral("Necessary local traffic actually reaches the origin DIRECT"));
    click("addServicePolicy");fill("servicePolicyName","Overlapping fixture");fill("serviceDomainValue",childDomain);click("addServiceDomain");click("servicePolicyTarget");chooseTarget("node",nodeB);click("saveServicePolicy");
    check(controller->servicePolicies().size()==1&&popup("servicePolicyDialog")&&item("servicePolicyMessage")&&item("servicePolicyMessage")->property("text").toString().contains("Dedicated fixture"),QStringLiteral("Actual core overlap winner is shown before saving a conflicting service"));
    click("saveServicePolicy");awaitSaved(QStringLiteral("Explicit conflict review confirms the same candidate"));const auto childId=recordNamed(controller->servicePolicies(),"Overlapping fixture").value("id").toString();
    request(childUrl,&net.a,QStringLiteral("Declared priority wins over implicit more-specific domain guessing"));
    click("servicePolicyMore-"+childId);click("swirlContextOption-1");awaitSaved(QStringLiteral("Explicit service priority move is acknowledged"));request(childUrl,&net.b,QStringLiteral("Moving the child policy earlier changes its actual route to B"));
    click("servicePolicyMore-"+childId);click("swirlContextOption-3");click("confirmDeletePolicy");awaitSaved(QStringLiteral("Overlapping service removal is acknowledged"));request(childUrl,&net.a,QStringLiteral("Removing the child restores its parent service A without direct bypass"));
    click("servicePolicyEnabled-"+serviceId);awaitSaved(QStringLiteral("Disabling a service is committed before showing its disabled state"));request(serviceUrl,&net.b,QStringLiteral("Disabled service falls through to the configured default B"));
    click("servicePolicyEnabled-"+serviceId);awaitSaved(QStringLiteral("Re-enabling a service is committed"));
    setTab(1);
    const auto addManualGroup=[&](const QString &name,const QString &kind,const QString &memberId,bool includeB){
        click("addPolicyGroup");fill("policyGroupName",name);click("addPolicyGroupMember");chooseTarget(kind,memberId);
        if(includeB){click("addPolicyGroupMember");chooseTarget("node",nodeB);}
        click("selectPolicyGroupMember-0");click("savePolicyGroup");return awaitSaved(QStringLiteral("Manual strategy group is committed through real form input"));
    };
    if(!addManualGroup("Manual fixture","node",nodeA,true))return finish();const auto groupA=recordNamed(controller->strategyGroups(),"Manual fixture").value("id").toString();
    if(!addManualGroup("Nested fixture","group",groupA,false))return finish();const auto groupB=recordNamed(controller->strategyGroups(),"Nested fixture").value("id").toString();
    setTab(0);click("defaultPolicyTarget");chooseTarget("group",groupB);awaitSaved(QStringLiteral("Default policy accepts an explicitly selected nested group"));request(defaultUrl,&net.a,QStringLiteral("Default resolves two manual group levels to the actual A peer"));
    setTab(1);click("policyGroupChoose-"+groupA);chooseTarget("node",nodeB);awaitSaved(QStringLiteral("Nested manual member change is acknowledged"));request(defaultUrl,&net.b,QStringLiteral("Nested manual change moves new default traffic to B"));request(serviceUrl,&net.a,QStringLiteral("Dedicated A service remains independent of the nested default B"));
    click("policyGroup-"+groupA);click("addPolicyGroupMember");
    if(auto *tabs=item("policyTargetTabs"))QTest::mouseClick(window,Qt::LeftButton,Qt::NoModifier,tabs->mapToScene(QPointF(tabs->width()*0.75,tabs->height()/2)).toPoint());QTest::qWait(80);
    check(item("policyTarget-group-"+groupA)==nullptr,QStringLiteral("A group is excluded from its own candidate picker"));chooseTarget("group",groupB);click("savePolicyGroup");
    check(popup("policyGroupDialog")&&item("policyGroupMessage")&&!item("policyGroupMessage")->property("text").toString().isEmpty()&&recordNamed(controller->strategyGroups(),"Manual fixture").value("members").toList().size()==2,QStringLiteral("Core cycle error keeps the draft open and committed group unchanged"));
    QTest::keyClick(window,Qt::Key_Escape);QTest::qWait(100);check(popup("discardChangesPrompt")!=nullptr,QStringLiteral("Esc detects member-only draft changes"));click("discardChangesConfirm");QTest::qWait(300);request(defaultUrl,&net.b,QStringLiteral("Rejected cyclic draft never changes the actual route"));
    click("policyGroupMore-"+groupB);
    click("swirlContextOption-1");click("confirmDeletePolicy");
    check(popup("deletePolicyDialog")&&controller->strategyGroups().size()==2,QStringLiteral("Deleting a group referenced by default is refused and retains both groups"));click("cancelDeletePolicy");
    check(QTest::qWaitFor([&]{return !popup("deletePolicyDialog");},4000),QStringLiteral("Cancelled deletion releases its modal grab before the connection control"));
    if(!directory.isEmpty()){QDir().mkpath(directory);window->grabWindow().save(directory+"/strategy-groups.png");}
    click("policyConnectButton");check(QTest::qWaitFor([&]{return !controller->processAlive();},10000),QStringLiteral("Policy connection control stops its owned runtime"));
    for(int strategy=1;strategy<=3;++strategy){
        click("addPolicyGroup");fill("policyGroupName",QString("Automatic fixture %1").arg(strategy));setCombo("policyGroupType",strategy);click("addPolicyGroupMember");chooseTarget("node",nodeA);click("policyGroupAdvanced");
        check(item("policyProbeFailureThreshold")&&item("policyProbeFailureThreshold")->property("text").toString()=="2",QStringLiteral("Advanced failure threshold exposes the core default"));
        if(strategy==1){window->resize(window->minimumWidth(),window->minimumHeight());if(auto *field=item("policyProbeTolerance"))field->forceActiveFocus();QTest::qWait(120);check(reachable(item("policyProbeTolerance")),QStringLiteral("Keyboard focus reveals the last advanced field at minimum window size"));}
        click("savePolicyGroup");awaitSaved(QStringLiteral("Automatic strategy and advanced values are saved offline"));
        const auto group=recordNamed(controller->strategyGroups(),QString("Automatic fixture %1").arg(strategy)),probe=group.value("probe").toMap();
        check(group.value("strategy")==QStringList{"manual","url_test","fallback","load_balance"}[strategy]&&probe.value("failure_threshold").toInt()==2&&probe.value("tolerance_ms").toInt()==(strategy==1?50:0),QStringLiteral("Committed strategy and probe values match the selected type"));
    }
    check(controller->strategyGroups().size()==5,QStringLiteral("All four strategy types and nested groups remain stored"));
    setTab(0);check(controller->defaultPolicy().value("id")=="policy:default",QStringLiteral("Default policy remains permanent after all CRUD operations"));
    if(!directory.isEmpty())window->grabWindow().save(directory+"/service-assignments.png");
    click("servicePolicy-"+serviceId);fill("servicePolicyName","Dedicated fixture edited");click("saveServicePolicy");awaitSaved(QStringLiteral("Editing a service is saved through the same committed transaction"));
    check(recordNamed(controller->servicePolicies(),"Dedicated fixture edited").value("id")==serviceId,QStringLiteral("Service rename preserves its stable identity"));
    click("servicePolicyMore-"+serviceId);click("swirlContextOption-3");click("confirmDeletePolicy");awaitSaved(QStringLiteral("Unreferenced service deletion is committed"));check(controller->servicePolicies().isEmpty(),QStringLiteral("Service deletion removes its stored record without deleting default"));
    setTab(1);if(auto *list=item("policyGroupList")){QMetaObject::invokeMethod(list,"positionViewAtIndex",Q_ARG(int,3),Q_ARG(int,0));QTest::qWait(100);}
    const auto unusedGroup=recordNamed(controller->strategyGroups(),"Automatic fixture 2").value("id").toString();click("policyGroupMore-"+unusedGroup);click("swirlContextOption-1");click("confirmDeletePolicy");awaitSaved(QStringLiteral("Unused strategy group deletion is committed"));check(controller->strategyGroups().size()==4,QStringLiteral("Deleting an unused group retains all unrelated references"));
    check(applied.count()>=14,QStringLiteral("Real policy completion signals accompany accepted transactions"));
    check(!controller->setTunEnabled(true)&&!controller->tunEnabled(),QStringLiteral("Unsupported TUN is rejected before any platform mutation"));
    eval("AppState.navigate('activity')");
    if(!check(QTest::qWaitFor([&]{return item("activityOutboundMode")&&!host->property("moving").toBool();},5000),QStringLiteral("Activity mode is reachable after policy edits")))return finish();
    auto *activityMode=item("activityOutboundMode");
    auto *modeText=item("activityOutboundModeText");
    check(modeText&&qAbs(activityMode->width()-modeText->implicitWidth()-eval("Theme.dp(24)").toReal())<=2,QStringLiteral("The mode value is one compact capsule without an adjacent button"));
    check(modeText&&modeText->width()+0.5>=modeText->implicitWidth()&&!modeText->property("truncated").toBool(),QStringLiteral("The complete mode name remains visible without style padding or elision"));
    const auto originalMode=controller->routingMode();
    check(activityMode->property("displayMode")==originalMode,QStringLiteral("Activity value starts from the controller's acknowledged mode"));
    click("activityOutboundMode");
    check(popup("activityOutboundModeMenu")!=nullptr,QStringLiteral("Activity facts row opens the native three-mode menu"));
    if(auto *menu=popup("activityOutboundModeMenu")) {
        auto *content=menu->property("contentItem").value<QQuickItem *>();
        check(content&&QRectF(QPointF(),window->size()).contains(QRectF(content->mapToScene(QPointF()),content->size())),QStringLiteral("Activity mode menu stays inside the minimum-width window"));
    }
    QTest::keyClick(window,Qt::Key_Escape);
    check(QTest::qWaitFor([&]{return !popup("activityOutboundModeMenu");},2000)&&activityMode->hasActiveFocus()&&controller->routingMode()==originalMode,QStringLiteral("Esc closes the mode menu, restores focus and changes no route"));
    auto *modeSurface=item("activityOutboundModeSurface");
    check(modeSurface&&QQmlProperty(modeSurface,"border.width").read().toReal()==0
          &&qAbs(modeSurface->property("radius").toReal()-modeSurface->height()/2)<0.5,
          QStringLiteral("Focused mode value keeps the event capsule shape without a blue frame"));
    bool busyObserved=false,pendingValueStable=true;
    const auto modeObservation=QObject::connect(controller,&EngineController::policyChanged,window,[&]{
        if(controller->policyBusy()){busyObserved=true;pendingValueStable=pendingValueStable&&activityMode->property("displayMode")==originalMode;}
    });
    click("activityOutboundMode");click("activityMode-global");
    if(!awaitSaved(QStringLiteral("Activity global choice receives the real durable configuration receipt"))){QObject::disconnect(modeObservation);return finish();}
    QObject::disconnect(modeObservation);
    check(busyObserved&&pendingValueStable,QStringLiteral("Activity mode keeps its prior value while the real transaction is pending"));
    check(!controller->processAlive()&&controller->policyReceipt().value("scope")=="saved-next-connect"&&controller->appliedRevision().isEmpty(),QStringLiteral("Offline activity mode save never claims live network application"));
    check(activityMode->property("displayMode")=="global"&&!activityMode->property("pending").toBool()&&activityMode->property("savedForNextConnection").toBool(),QStringLiteral("Activity updates only after matching completion and labels next-connection scope"));
    click("activityOutboundMode");click("activityMode-rule");
    awaitSaved(QStringLiteral("Activity mode can switch back using the same native menu"));
    check(activityMode->property("displayMode")=="rule",QStringLiteral("Activity return choice follows the committed controller mode"));
    check(QTest::qWaitFor([&]{return !popup("activityOutboundModeMenu");},2000),QStringLiteral("Mode selection releases the menu before returning to the activity facts"));
    QTest::qWait(200);
    if(!directory.isEmpty())window->grabWindow().save(directory+"/activity-mode.png");
    return finish();
}
