#include "EngineUiChecks.h"
#include "CaptureChecks.h"
#include "engine/EngineController.h"
#include <QQuickWindow>
#include <QQuickItem>
#include <QQmlContext>
#include <QQmlExpression>
#include <QTcpServer>
#include <QTest>
#include <QSignalSpy>
#include <QElapsedTimer>
#include <QJsonDocument>
#include <QJsonObject>
#include <functional>

int runEngineUiChecks(QQuickWindow *window, EngineController *controller, CaptureService *capture) {
    if (!window || !controller) return 1;
    int failures = 0, checks = 0;
    const auto check = [&](bool ok, const char *name) {
        ++checks;if(!ok)++failures;qInfo()<<(ok?"PASS":"FAIL")<<name;
        if(!ok)qInfo()<<"Engine UI failure evidence"<<name<<QJsonDocument(QJsonObject{
            {"busy",controller->busy()},{"canStart",controller->canStart()},{"processAlive",controller->processAlive()},
            {"apiHealthy",controller->apiHealthy()},{"state",controller->stateText()},{"errorCode",controller->errorCode()},
            {"error",controller->error()},{"routingError",controller->routingError()}}).toJson(QJsonDocument::Compact);
        return ok;
    };
    std::function<QQuickItem *(QQuickItem *, const QString &)> find;
    find = [&](QQuickItem *item, const QString &name) -> QQuickItem * {
        if (item->objectName() == name) return item;
        for (auto *child : item->childItems()) if (auto *found = find(child, name)) return found;
        return nullptr;
    };
    const auto item = [&](const QString &name) { return find(window->contentItem(), name); };
    const auto evaluate = [&](const QString &expression) {
        QQmlExpression eval(qmlContext(window), window, expression); eval.evaluate();
        check(!eval.hasError(), "QML business facade evaluation succeeds");
    };
    const auto click = [&](const QString &name) {
        auto *target = item(name);
        if(!check(target!=nullptr,"engine control exists"))return false;
        QPointF lastPoint;bool havePoint=false;QElapsedTimer stable;
        const bool ready=QTest::qWaitFor([&] {
            if(!target->isVisible()||!target->isEnabled()||target->width()<=0||target->height()<=0)return false;
            // The engine buttons are below the fold at normal window height.
            // Scroll their actual Flickable into view before sending input.
            for(auto *parent=target->parentItem();parent;parent=parent->parentItem()) {
                const auto currentY=parent->property("contentY");
                const auto contentHeight=parent->property("contentHeight");
                if(!currentY.isValid()||!contentHeight.isValid()||contentHeight.toDouble()<=parent->height())continue;
                const auto top=target->mapToItem(parent,QPointF(0,0)).y();
                const auto bottom=top+target->height();
                if(top<0||bottom>parent->height()) {
                    const auto maximum=contentHeight.toDouble()-parent->height();
                    const auto centered=currentY.toDouble()+top-(parent->height()-target->height())/2;
                    parent->setProperty("contentY",qBound(0.0,centered,maximum));
                    havePoint=false;
                }
            }
            const auto center=target->mapToScene(QPointF(target->width()/2,target->height()/2));
            bool visible=center.x()>=0&&center.x()<window->width()&&center.y()>=0&&center.y()<window->height();
            for(auto *parent=target;parent&&visible;parent=parent->parentItem()) {
                const auto local=parent->mapFromScene(center);
                visible=parent->isVisible()&&parent->opacity()>0.99&&(!parent->clip()||QRectF(0,0,parent->width(),parent->height()).contains(local));
            }
            if(!visible){havePoint=false;return false;}
            if(!havePoint||qAbs(center.x()-lastPoint.x())>0.25||qAbs(center.y()-lastPoint.y())>0.25){lastPoint=center;havePoint=true;stable.restart();return false;}
            return stable.elapsed()>=40;
        },3500);
        if(!check(ready,"engine control is enabled and stable inside its visible viewport")){qInfo()<<"Engine UI input target"<<name<<target->isVisible()<<target->isEnabled()<<target->mapToScene(QPointF(target->width()/2,target->height()/2));return false;}
        QSignalSpy clicked(target,SIGNAL(clicked()));
        if(!check(clicked.isValid(),"engine control clicked signal is observed"))return false;
        QTest::mouseClick(window,Qt::LeftButton,Qt::NoModifier,lastPoint.toPoint());
        QTest::qWait(100);
        const bool delivered=clicked.count()==1;
        if(!delivered)qInfo()<<"Engine UI input target"<<name<<"clicked"<<clicked.count()<<"position"<<lastPoint;
        return check(delivered,"engine control receives exactly one pointer click");
    };
    const auto startThroughUi=[&] {
        bool sawStarting=false;
        const auto connection=QObject::connect(controller,&EngineController::statusChanged,window,[&]{sawStarting=sawStarting||controller->busy();});
        const bool delivered=click("engineStartButton");
        QObject::disconnect(connection);
        check(delivered&&sawStarting,"engine start click begins a new startup attempt");
        return delivered&&sawStarting;
    };
    window->resize(1450, 884);
    evaluate("AppState.navigate('settings')");
    auto *host=window->findChild<QObject *>("pageLoader");
    const auto activeSettings=[&]()->QObject *{auto *active=host?qvariant_cast<QObject *>(host->property("activeLoader")):nullptr;return active&&active->property("routeId").toString()=="settings"?qvariant_cast<QObject *>(active->property("item")):nullptr;};
    if(!check(QTest::qWaitFor([&]{return activeSettings()&&!host->property("moving").toBool()&&!host->property("pendingGrab").toBool();},3500),"actual settings page settles before section selection"))return 2;
    evaluate("pageLoader.item.section='代理'");
    if(!check(QTest::qWaitFor([&]{auto *page=activeSettings();auto *button=item("engineStartButton");return page&&page->property("section").toString()==QStringLiteral("代理")&&button&&button->isVisible()&&button->width()>0&&button->height()>0;},3500),"proxy settings section exposes its real engine controls"))return 2;
    check(!controller->processAlive() && !controller->apiHealthy(), "opening settings does not start an engine");
    // The GUI no longer exposes an executable selector or external control API.
    // Dedicated real-library fixtures test missing/wrong DLLs without replacing
    // the DLL of this already-running GUI process.
    check(controller->metaObject()->indexOfProperty("executablePath") == -1,
          "external executable selector is absent");
    check(controller->metaObject()->indexOfProperty("preferCompatibility") == -1,
          "compatibility runtime selector is absent");
    controller->setRoutingMode("direct");
    QTcpServer occupied;
    check(occupied.listen(QHostAddress::LocalHost, 0), "reserve conflicting proxy port");
    controller->setProxyPort(occupied.serverPort());
    startThroughUi();
    check(QTest::qWaitFor([&] { return !controller->error().isEmpty() && !controller->busy(); }, 5000),
          "Rust listener conflict reaches business facade");
    check(!controller->processAlive(), "failed listener does not become a healthy core");
    check(QTest::qWaitFor([&]{auto *error=item("engineErrorText");return error&&error->isVisible()&&!error->property("text").toString().isEmpty();},1000),
          "QML displays a native startup diagnostic");
    occupied.close();
    const bool newStart=startThroughUi();
    check(newStart&&QTest::qWaitFor([&] { return controller->apiHealthy() || (!controller->error().isEmpty() && !controller->busy()); }, 15000),
          "Rust startup completes");
    check(controller->processAlive() && controller->apiHealthy(), "Rust runtime is ready");
    check(controller->processId().toLongLong() == QCoreApplication::applicationPid(),
          "runtime belongs to the GUI process");
    check(controller->version().startsWith("Swirl Core Rust "), "native library version reaches QML");
    check(QTest::qWaitFor([&]{auto *badge=item("engineStatusBadge");return badge&&badge->property("label").toString()==controller->stateText();},1000),"visible state reflects real engine health");
    if (controller->apiHealthy()) {
        check(runCaptureChecks(capture) == 0, "existing capture HTTP and CONNECT integration passes alongside Rust");
        click("engineStopButton");
        check(QTest::qWaitFor([&] { return controller->canStart() && !controller->processAlive(); }, 4000), "UI stop button reaps owned engine");
        startThroughUi();
        check(QTest::qWaitFor([&] { return controller->apiHealthy(); }, 15000), "UI supports another real start");
        // An in-process core cannot be killed as a child process: doing so
        // terminates Swirl itself. Exercise stop/restart and listener release;
        // panic/ABI failure and invalid state are covered at the FFI boundary.
        controller->stop();
        check(QTest::qWaitFor([&] { return controller->canStart() && !controller->processAlive(); }, 4000),
              "second Rust session stops cleanly");
        QTcpServer released;
        check(released.listen(QHostAddress::LocalHost, controller->proxyPort()),
              "Rust stop releases its proxy listener");
    }
    controller->stop();
    check(QTest::qWaitFor([&] { return !controller->processAlive() && controller->canStart(); }, 4000), "UI test leaves no owned engine running");
    qInfo() << "Engine UI checks:" << checks << "checks," << failures << "failures";
    return failures ? 2 : 0;
}
