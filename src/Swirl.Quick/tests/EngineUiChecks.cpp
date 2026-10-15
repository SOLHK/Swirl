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
#ifdef Q_OS_WIN
#include <windows.h>
#endif

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
    const auto originalPath = controller->executablePath();
    controller->setExecutablePath(originalPath + ".missing"); click("engineStartButton");
    check(controller->errorCode() == "MissingExecutable", "missing executable reported through business facade");
    auto *error = item("engineErrorText");
    check(error && error->isVisible() && error->property("text").toString().contains(".missing"), "QML displays the concrete missing path");
    controller->setExecutablePath(originalPath);
    QTcpServer occupied; check(occupied.listen(QHostAddress::LocalHost, 0), "reserve conflicting control port");
    controller->setControlPort(occupied.serverPort()); click("engineStartButton");
    check(controller->errorCode() == "PortConflict" && !controller->processAlive(), "port conflict updates QML without crashing");
    occupied.close();
    click("engineStartButton");
    check(QTest::qWaitFor([&] { return controller->apiHealthy() || !controller->error().isEmpty() && !controller->busy(); }, 15000), "real engine startup completes");
    check(controller->processAlive() && controller->apiHealthy(), "real process and authenticated API are ready");
    check(controller->version() == controller->expectedVersion(), "real API version reaches QML");
    auto *badge = item("engineStatusBadge");
    check(badge && badge->property("label").toString() == controller->stateText(), "visible state reflects real engine health");
    if (controller->apiHealthy()) {
        check(runCaptureChecks(capture) == 0, "existing HTTP and CONNECT integration passes with Mihomo running");
        click("engineStopButton");
        check(QTest::qWaitFor([&] { return controller->canStart() && !controller->processAlive(); }, 4000), "UI stop button reaps owned engine");
        click("engineStartButton");
        check(QTest::qWaitFor([&] { return controller->apiHealthy(); }, 15000), "UI supports another real start");
#ifdef Q_OS_WIN
        HANDLE process = OpenProcess(PROCESS_TERMINATE, FALSE, DWORD(controller->processId().toULongLong()));
        check(process != nullptr, "test can access only the owned engine process");
        if (process) { check(TerminateProcess(process, 42), "simulate owned engine unexpected exit"); CloseHandle(process); }
        check(QTest::qWaitFor([&] { return controller->errorCode() == "UnexpectedExit"; }, 4000), "unexpected exit reaches UI facade");
        check(!controller->processAlive() && !controller->apiHealthy(), "unexpected exit clears real health flags");
        check(badge && badge->property("label").toString() == "引擎异常" && error && error->isVisible(), "QML badge and error update after real exit");
#endif
    }
    controller->stop();
    check(QTest::qWaitFor([&] { return !controller->processAlive() && controller->canStart(); }, 4000), "UI test leaves no owned engine running");
    qInfo() << "Engine UI checks:" << checks << "checks," << failures << "failures";
    return failures ? 2 : 0;
}
