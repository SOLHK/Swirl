#include "NodeUiChecks.h"
#include "ControlledNetwork.h"
#include "LoopbackPortLease.h"
#include "engine/EngineController.h"
#include <QQuickWindow>
#include <QQuickItem>
#include <QQmlContext>
#include <QQmlExpression>
#include <QTest>
#include <QClipboard>
#include <QGuiApplication>
#include <QDir>
#include <QImage>
#include <cstdio>
#include <functional>

int runNodeUiChecks(QQuickWindow *window,EngineController *controller) {
    if(!window||!controller)return 1;
    int checks=0,failures=0;
    const auto check=[&](bool ok,const char *label){++checks;if(!ok)++failures;qInfo()<<(ok?"PASS":"FAIL")<<label;return ok;};
    std::function<QQuickItem *(QQuickItem *,const QString &)> find;
    find=[&](QQuickItem *p,const QString &n)->QQuickItem *{if(p->objectName()==n)return p;for(auto *c:p->childItems())if(auto *f=find(c,n))return f;return nullptr;};
    const auto item=[&](const QString &n){return find(window->contentItem(),n);};
    const auto eval=[&](const QString &s){QQmlExpression e(qmlContext(window),window,s);auto v=e.evaluate();check(!e.hasError(),"QML expression valid");return v;};
    const auto click=[&](const QString &n){QTest::qWaitFor([&]{auto *hero=item("nodeHero");return !hero||!hero->property("moving").toBool();},3500);auto *t=item(n);if(check(t&&t->isEnabled(),"node input exists and is enabled"))QTest::mouseClick(window,Qt::LeftButton,Qt::NoModifier,t->mapToScene(QPointF(t->width()/2,t->height()/2)).toPoint());QTest::qWait(300);};
    const auto fill=[&](const QString &n,const QString &v){auto *t=item(n);if(check(t!=nullptr,"node field exists"))t->setProperty("text",v);};
    const auto select=[&](int index){ eval("pageLoader.item.dismissDetail()"); QTest::qWait(450);
        auto *t=item("realNodeTable");if(!check(t!=nullptr,"real node table exists"))return;
        QTest::mouseClick(window,Qt::LeftButton,Qt::NoModifier,t->mapToScene(QPointF(80,39+t->property("itemHeight").toInt()*(index+0.5))).toPoint());
        // The next click targets a card which moves for longer than 150 ms.
        // Sample its hit position after the real transition has settled.
        check(QTest::qWaitFor([&]{auto *hero=item("nodeHero");return hero&&!hero->property("moving").toBool();},3500),"node card settles before next coordinate-based input");
    };
    ControlledNetwork net;if(!check(net.start(),"controlled real TCP endpoints start"))return 2;
    const auto probeSelected=[&](SocksPeer &selected,SocksPeer &other,const char *label){
        const auto forwarded=selected.forwarded,otherForwarded=other.forwarded;
        const auto before=net.httpRequestsByExit;
        click("nodeTestButton");
        const bool finished=QTest::qWaitFor([&]{return !controller->tests()->busy();},41000);
        const bool passed=finished&&controller->tests()->result(controller->selectedNodeId()).value("success").toBool()
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
    check(QTest::qWaitFor([&]{auto *active=host?qvariant_cast<QObject *>(host->property("activeLoader")):nullptr;return active && active->property("routeId").toString()=="proxies" && !host->property("moving").toBool() && !host->property("pendingGrab").toBool();},3500),"node navigation animation settles before input");
    QTest::qWait(150);
    check(controller->nodes().isEmpty()&&!controller->processAlive(),"node page starts empty without starting engine");
    click("nodeAddButton");fill("nodeNameField","A");fill("nodeHostField","https://invalid");fill("nodePortField",QString::number(net.a.serverPort()));click("nodeSaveButton");
    check(controller->nodes().isEmpty()&&!controller->nodeError().isEmpty(),"invalid host rejected through UI without fake save");
    fill("nodeHostField","127.0.0.1");click("nodeSaveButton");check(controller->nodes().size()==1,"UI saves first real node");
    click("nodeAddButton");fill("nodeNameField","B");fill("nodeHostField","127.0.0.1");fill("nodePortField",QString::number(net.b.serverPort()));fill("nodeUsernameField",QString::fromUtf8(net.b.username));fill("nodePasswordField",QString::fromUtf8(net.b.password));
    check(item("nodePasswordField")&&item("nodePasswordField")->property("echoMode").toInt()==2,"credential field is masked");click("nodeSaveButton");check(controller->nodes().size()==2,"UI saves authenticated SOCKS5 node");
    LoopbackPortLease ports;
    if(!check(ports.reserve(),"distinct UI TCP/UDP and control ports are reserved together")) {
        qInfo()<<"Port reservation evidence"<<ports.errorString();return 2;
    }
    controller->setProxyPort(ports.proxyPort());controller->setControlPort(ports.controlPort());
    ports.release();
    const auto waitEngineReady=[&]{
        const bool ready=QTest::qWaitFor([&]{return controller->apiHealthy();},15000);
        if(!ready)qInfo()<<"Engine startup evidence"<<controller->stateText()<<controller->errorCode()<<controller->error();
        return ready;
    };
    select(0);click("nodeConnectButton");
    if(check(waitEngineReady(),"UI starts actual configured engine")) {
        check(!controller->requestSucceeded(),"running engine does not imply successful request");fill("nodeTestUrl",net.url().toString());
        probeSelected(net.a,net.b,"UI real request passes only through selected node A");
        const auto pid=controller->processId();
        const auto selectedBeforeNavigation=controller->selectedNodeId();
        for(const auto &route:QStringList{"featurehub","settings","fonts","dns","modules","profiles","scripts","subscriptions","proxies"}){
            eval("AppState.navigate('"+route+"')");
            check(QTest::qWaitFor([&]{auto *active=host?qvariant_cast<QObject *>(host->property("activeLoader")):nullptr;return active&&active->property("routeId").toString()==route&&!host->property("moving").toBool()&&!host->property("pendingGrab").toBool();},3500),"live navigation settles inside the main host");
            check(controller->processId()==pid&&controller->apiHealthy()&&controller->selectedNodeId()==selectedBeforeNavigation,"all settings routes preserve the real running proxy and selected node");
        }
        select(1);
        check(QTest::qWaitFor([&]{return !controller->nodeBusy();},5000)&&controller->activeNodeId()==controller->selectedNodeId()&&controller->processId()==pid,"row selection switches real engine node without restarting");
        check(!controller->tests()->result(controller->selectedNodeId()).value("success").toBool(),"new selected node has no inherited request result");
        probeSelected(net.b,net.a,"UI new requests use authenticated selected node B");
        check(item("nodeRequestState")&&item("nodeRequestState")->property("text").toString().contains("成功"),"visible request state follows actual result");click("nodeConnectButton");
        check(QTest::qWaitFor([&]{return controller->canStart();},4000)&&!controller->processAlive(),"UI disconnect reaps engine");
    }
    check(!controller->requestSucceeded() && controller->requestStateText()==QStringLiteral("尚未发起实际请求"),"disconnect clears stale request success text");
    select(1);click("nodeEditButton");check(item("nodePasswordField")&&item("nodePasswordField")->property("text").toString().isEmpty(),"editing never reveals stored credentials");fill("nodeNameField","B edited");click("nodeSaveButton");check(controller->nodes().last().toMap().value("name").toString()=="B edited","UI edits saved metadata");
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
    select(0);click("nodeConnectButton");
    check(waitEngineReady(),"UI imported node starts configured Rust engine");
    fill("nodeTestUrl",net.url().toString());click("nodeTestButton");
    check(QTest::qWaitFor([&]{return !controller->tests()->busy();},41000) && controller->tests()->result(controller->selectedNodeId()).value("success").toBool(),"UI imported node forwards a real HTTP request");
    controller->stop();check(QTest::qWaitFor([&]{return !controller->processAlive();},4000),"UI imported node cleanup reaps owned engine");
    const auto importedNodes=controller->nodes();
    if(importedNodes.isEmpty()) {
        const auto reason=controller->imports()->message().toUtf8();
        std::fprintf(stderr,"NODE_UI_IMPORT_MISSING: %s\n",reason.constData());
        return failures?failures:1;
    }
    controller->deleteNode(importedNodes.first().toMap().value("id").toString());
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
            const auto content=QString("proxies: [{name: %2 fixture, type: socks5, server: 127.0.0.1, port: %1}]\n").arg(net.a.serverPort()).arg(subscriptionRequests==1?"HK":"JP").toUtf8();
            QTimer::singleShot(600,socket,[socket,content]{socket->write("HTTP/1.1 200 OK\r\nContent-Length: "+QByteArray::number(content.size())+"\r\nConnection: close\r\n\r\n"+content);socket->disconnectFromHost();});
        });
        QObject::connect(socket,&QTcpSocket::disconnected,socket,&QObject::deleteLater);
    }});
    check(subscriptions.listen(QHostAddress::LocalHost,0),"subscription HTTPS fixture listens");
    eval("AppState.navigate('subscriptions')");QTest::qWait(350);
    click("addSubscription");fill("subscriptionName","Subscription fixture");fill("subscriptionUrl",QString("https://localhost:%1/fixture").arg(subscriptions.serverPort()));click("saveSubscription");
    const auto businessQa=qEnvironmentVariable("SWIRL_UI_QA_DIRECTORY");
    if(!businessQa.isEmpty()) {
        QDir().mkpath(businessQa+"/business-frames");
        for(int frame=0;frame<25;++frame){QTest::qWait(40);window->grabWindow().scaledToWidth(1000,Qt::SmoothTransformation).save(businessQa+QString("/business-frames/%1.png").arg(frame,3,10,QChar('0')));}
    }
    check(QTest::qWaitFor([&]{return !controller->imports()->busy();},8000)&&controller->imports()->providers().size()==1&&controller->nodes().size()==1&&subscriptionRequests==1,"subscription UI saves HTTPS source and imports an actual node");
    eval("AppState.navigate('proxies')");QTest::qWait(350);
    check(eval("pageLoader.item.countries.length===1 && pageLoader.item.countries[0].code==='HK'").toBool(),"country filter contains only the imported subscription's actual Hong Kong label");
    eval("pageLoader.item.countryCode='HK'");
    check(eval("pageLoader.item.resultCount===1").toBool(),"country filter combines with the real imported node list");
    const auto subscriptionSource=controller->imports()->providers().first().toMap().value("id").toString();
    check(controller->saveNode({{"name","JP manual HTTP"},{"protocol","http"},{"host","127.0.0.1"},{"port",9}}),"manual node adds a second region outside the subscription");
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
    eval("pageLoader.item.countryCode='HK'");
    eval("AppState.navigate('subscriptions')");QTest::qWait(350);
    if(!controller->imports()->providers().isEmpty()) {
        const auto id=controller->imports()->providers().first().toMap().value("id").toString();
        QPointer<QQuickItem> card=item("subscriptionCard-"+id);
        const auto collapsedHeight=card?card->height():0;
        click("expandSubscription-"+id);
        check(card&&card->height()>collapsedHeight,"subscription details animate open without replacing the card");
        click("editSubscription-"+id);check(item("subscriptionUrl")&&item("subscriptionUrl")->property("text").toString().isEmpty(),"editing subscription keeps its protected URL hidden");
        fill("subscriptionName","Edited subscription fixture");click("saveSubscription");
        check(QTest::qWaitFor([&]{return !controller->imports()->busy();},8000)&&controller->imports()->providers().first().toMap().value("name").toString()=="Edited subscription fixture"&&subscriptionRequests==2,"editing preserves encrypted URL and refreshes the real source");
        check(card&&item("subscriptionCard-"+id)==card,"subscription refresh keeps the same card delegate and expanded state");
        eval("AppState.navigate('proxies')");QTest::qWait(350);
        check(eval("pageLoader.item.countries.length===1 && pageLoader.item.countries[0].code==='JP' && pageLoader.item.countryCode==='' && pageLoader.item.resultCount===1").toBool(),"subscription refresh replaces country options and clears an obsolete country selection");
        eval("AppState.navigate('subscriptions')");QTest::qWait(350);
        const auto qa=qEnvironmentVariable("SWIRL_UI_QA_DIRECTORY");
        if(!qa.isEmpty()){QDir().mkpath(qa);window->grabWindow().save(qa+"/subscription-success.png");}
        subscriptions.close();click("refreshSubscription-"+id);
        check(QTest::qWaitFor([&]{return !controller->imports()->busy();},8000)&&!controller->imports()->providers().first().toMap().value("error").toString().isEmpty()&&controller->nodes().size()==1,"failed real refresh displays an error and retains imported nodes");
        if(!qa.isEmpty())window->grabWindow().save(qa+"/subscription-failure.png");
        click("deleteSubscription-"+id);QTest::keyClick(window,Qt::Key_Escape);QTest::qWait(250);
        check(controller->imports()->providers().size()==1,"Escape cancels destructive subscription confirmation");
        click("deleteSubscription-"+id);click("confirmSubscriptionDelete");
        check(controller->imports()->providers().isEmpty()&&controller->nodes().size()==1,"confirmed deletion retains nodes as documented");
        controller->deleteNode(controller->nodes().first().toMap().value("id").toString());
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
    if(!qa.isEmpty()){QDir().mkpath(qa);window->grabWindow().save(qa+"/nodes-minimum-180.png");}
    for(int i=0;i<180;++i){
        auto *viewport=item("tableRowsViewport");
        if(viewport)QMetaObject::invokeMethod(viewport,"positionViewAtIndex",Q_ARG(int,i),Q_ARG(int,0));
        QTest::qWait(5);
        eval(QString("pageLoader.item.selectRow(engineController.nodes[%1])").arg(i));
    }
    check(QTest::qWaitFor([&]{return hero&&!hero->property("moving").toBool();},3500),"180 rapid node selections settle");
    check(eval("pageLoader.item.selected.name.indexOf('179')>=0").toBool(),"last of 180 rapid detail retargets retains its selected node");
    auto *identity=item("nodeIdentitySurface");
    check(identity&&identity->parentItem()!=hero->parentItem(),"settled node details return to scroll ownership");
    if(!qa.isEmpty())window->grabWindow().save(qa+"/nodes-selected-minimum.png");
    qInfo()<<"Node UI checks:"<<checks<<"checks,"<<failures<<"failures";return failures?2:0;
}
