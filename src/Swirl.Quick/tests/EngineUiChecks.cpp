#include "EngineUiChecks.h"
#include "CaptureChecks.h"
#include "engine/EngineController.h"
#include <QQuickWindow>
#include <QQuickItem>
#include <QQmlContext>
#include <QQmlExpression>
#include <QTcpServer>
#include <QTest>
#include <functional>

int runEngineUiChecks(QQuickWindow *window, EngineController *controller, CaptureService *capture) {
    if (!window || !controller) return 1;
    int failures = 0, checks = 0;
    const auto check = [&](bool ok, const char *name) { ++checks; if (!ok) ++failures; qInfo() << (ok ? "PASS" : "FAIL") << name; };
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
        auto *target = item(name); check(target != nullptr, "engine control exists");
        if (target) {
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
                    QCoreApplication::processEvents();
                }
            }
            QTest::mouseClick(window, Qt::LeftButton, Qt::NoModifier,
                target->mapToScene(QPointF(target->width()/2, target->height()/2)).toPoint());
        }
        QTest::qWait(100);
    };
    window->resize(1450, 884);
    evaluate("AppState.navigate('settings')"); QTest::qWait(200);
    evaluate("pageLoader.item.section='代理'"); QTest::qWait(200);
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
    click("engineStartButton");
    check(QTest::qWaitFor([&] { return !controller->error().isEmpty() && !controller->busy(); }, 5000),
          "Rust listener conflict reaches business facade");
    check(!controller->processAlive(), "failed listener does not become a healthy core");
    auto *error = item("engineErrorText");
    check(error && error->isVisible() && !error->property("text").toString().isEmpty(),
          "QML displays a native startup diagnostic");
    occupied.close();
    click("engineStartButton");
    check(QTest::qWaitFor([&] { return controller->apiHealthy() || (!controller->error().isEmpty() && !controller->busy()); }, 15000),
          "Rust startup completes");
    check(controller->processAlive() && controller->apiHealthy(), "Rust runtime is ready");
    check(controller->processId().toLongLong() == QCoreApplication::applicationPid(),
          "runtime belongs to the GUI process");
    check(controller->version().startsWith("Swirl Core Rust "), "native library version reaches QML");
    auto *badge = item("engineStatusBadge");
    check(badge && badge->property("label").toString() == controller->stateText(), "visible state reflects real engine health");
    if (controller->apiHealthy()) {
        check(runCaptureChecks(capture) == 0, "existing capture HTTP and CONNECT integration passes alongside Rust");
        click("engineStopButton");
        check(QTest::qWaitFor([&] { return controller->canStart() && !controller->processAlive(); }, 4000), "UI stop button reaps owned engine");
        click("engineStartButton");
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
