#include "NodeUiChecks.h"
#include "ControlledNetwork.h"
#include "engine/EngineController.h"
#include <QQuickWindow>
#include <QQuickItem>
#include <QQmlContext>
#include <QQmlExpression>
#include <QTest>
#include <QClipboard>
#include <QGuiApplication>
#include <functional>

int runNodeUiChecks(QQuickWindow *window,EngineController *controller) {
    if(!window||!controller)return 1;
    int checks=0,failures=0;
    const auto check=[&](bool ok,const char *label){++checks;if(!ok)++failures;qInfo()<<(ok?"PASS":"FAIL")<<label;return ok;};
    std::function<QQuickItem *(QQuickItem *,const QString &)> find;
    find=[&](QQuickItem *p,const QString &n)->QQuickItem *{if(p->objectName()==n)return p;for(auto *c:p->childItems())if(auto *f=find(c,n))return f;return nullptr;};
    const auto item=[&](const QString &n){return find(window->contentItem(),n);};
    const auto eval=[&](const QString &s){QQmlExpression e(qmlContext(window),window,s);auto v=e.evaluate();check(!e.hasError(),"QML expression valid");return v;};
    const auto click=[&](const QString &n){auto *t=item(n);if(check(t&&t->isEnabled(),"node input exists and is enabled"))QTest::mouseClick(window,Qt::LeftButton,Qt::NoModifier,t->mapToScene(QPointF(t->width()/2,t->height()/2)).toPoint());QTest::qWait(300);};
    const auto fill=[&](const QString &n,const QString &v){auto *t=item(n);if(check(t!=nullptr,"node field exists"))t->setProperty("text",v);};
    const auto select=[&](int index){auto *t=item("realNodeTable");if(!check(t!=nullptr,"real node table exists"))return;QTest::mouseClick(window,Qt::LeftButton,Qt::NoModifier,t->mapToScene(QPointF(80,39+t->property("itemHeight").toInt()*(index+0.5))).toPoint());QTest::qWait(150);};
    ControlledNetwork net;if(!check(net.start(),"controlled real TCP endpoints start"))return 2;
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
    QTcpServer port;port.listen(QHostAddress::LocalHost,0);controller->setProxyPort(port.serverPort());port.close();
    port.listen(QHostAddress::LocalHost,0);controller->setControlPort(port.serverPort());port.close();
    select(0);click("nodeConnectButton");
    if(check(QTest::qWaitFor([&]{return controller->apiHealthy();},15000),"UI starts actual pinned Mihomo")) {
        check(!controller->requestSucceeded(),"running engine does not imply successful request");fill("nodeTestUrl",net.url().toString());click("nodeTestButton");
        check(QTest::qWaitFor([&]{return !controller->nodeBusy();},8000)&&controller->requestSucceeded()&&net.a.forwarded>=2&&net.b.forwarded==0,"UI real request passes only through selected node A");
        const auto pid=controller->processId();select(1);
        check(QTest::qWaitFor([&]{return !controller->nodeBusy();},5000)&&controller->activeNodeId()==controller->selectedNodeId()&&controller->processId()==pid,"row selection switches real engine node without restarting");
        check(!controller->requestSucceeded(),"switch invalidates previous request success");click("nodeTestButton");
        check(QTest::qWaitFor([&]{return !controller->nodeBusy();},8000)&&controller->requestSucceeded()&&net.b.forwarded>=2,"UI new requests use authenticated selected node B");
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
    check(QTest::qWaitFor([&]{return controller->apiHealthy();},15000),"UI imported node starts real Mihomo");
    fill("nodeTestUrl",net.url().toString());click("nodeTestButton");
    check(QTest::qWaitFor([&]{return !controller->nodeBusy();},8000) && controller->requestSucceeded(),"UI imported node forwards a real HTTP request");
    controller->stop();check(QTest::qWaitFor([&]{return !controller->processAlive();},4000),"UI imported node cleanup reaps owned engine");
    controller->deleteNode(controller->nodes().first().toMap().value("id").toString());
    qInfo()<<"Node UI checks:"<<checks<<"checks,"<<failures<<"failures";return failures?2:0;
}
