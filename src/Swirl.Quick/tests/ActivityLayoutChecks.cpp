#include "ActivityLayoutChecks.h"
#include "app/MotionPolicy.h"
#include "engine/SystemProxySession.h"
#include <QColor>
#include <QCoreApplication>
#include <QDateTime>
#include <QDebug>
#include <QDir>
#include <QElapsedTimer>
#include <QFile>
#include <QGuiApplication>
#include <QImage>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QKeyEvent>
#include <QQmlContext>
#include <QQmlExpression>
#include <QQuickItem>
#include <QQuickWindow>
#include <QScreen>
#include <QSGRendererInterface>
#include <QSysInfo>
#include <QTest>
#include <QtMath>
#include <algorithm>
#include <cmath>
#include <functional>
#ifdef Q_OS_WIN
#ifndef NOMINMAX
#define NOMINMAX
#endif
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>
#endif

namespace {
QQuickItem *visual(QQuickItem *root, const QString &name) {
    if (root->objectName() == name) return root;
    for (auto *child : root->childItems())
        if (auto *found = visual(child, name)) return found;
    return nullptr;
}
QJsonObject rectangle(const QRectF &rect) {
    return {{"x", rect.x()}, {"y", rect.y()}, {"width", rect.width()}, {"height", rect.height()}};
}
QJsonObject dimensions(const QSize &size) {
    return {{"width", size.width()}, {"height", size.height()}};
}
bool nearScalar(qreal a, qreal b, qreal tolerance = 1.1) { return std::abs(a - b) <= tolerance; }
bool nearRect(const QRectF &a, const QRectF &b, qreal tolerance = 2) {
    return nearScalar(a.x(), b.x(), tolerance) && nearScalar(a.y(), b.y(), tolerance)
        && nearScalar(a.width(), b.width(), tolerance) && nearScalar(a.height(), b.height(), tolerance);
}
}

int runActivityLayoutChecks(QQuickWindow *window, const QString &outputDirectory) {
    QDir directory(outputDirectory);
    if (!QDir().mkpath(directory.absolutePath())) return 2;
    QJsonArray checks, layouts, travel, nativeViewportSamples;
    int failures = 0;
    const auto check = [&](const QString &name, bool success) {
        checks.append(QJsonObject{{"name", name}, {"passed", success}});
        qInfo() << "ACTIVITY_LAYOUT_CHECK" << name << success;
        if (!success) ++failures;
    };
    const auto eval = [&](const QString &script) {
        QQmlExpression expression(qmlContext(window), window, script);
        const auto result = expression.evaluate();
        check("qml-expression: " + script.left(90), !expression.hasError());
        if (expression.hasError()) qWarning() << expression.error();
        return result;
    };
    auto *policy = qobject_cast<MotionPolicy *>(qmlContext(window)->contextProperty("motionPolicy").value<QObject *>());
    check("motion-policy-present", policy != nullptr);
    if (!policy) return 2;
    const auto hostProxyBefore = SystemProxySession::snapshot();
    const bool nativeDpi = qEnvironmentVariableIsEmpty("QT_SCALE_FACTOR") && qEnvironmentVariableIsEmpty("QT_SCREEN_SCALE_FACTORS");
    if (qEnvironmentVariableIsSet("SWIRL_LAYOUT_EXPECTED_DPR"))
        check("window-DPR-matches-requested-Windows-scale", nearScalar(window->devicePixelRatio(), qEnvironmentVariable("SWIRL_LAYOUT_EXPECTED_DPR").toDouble(), 0.01));
    policy->setSystemReducedMotionOverrideForTest(0);
    struct PolicyRestore {
        MotionPolicy *policy;
        ~PolicyRestore() { policy->setSystemReducedMotionOverrideForTest(-1); }
    } restore{policy};
    eval("Theme.reduceMotion=false;Theme.followSystemMotion=false;Theme.mode='Light';AppState.navigate('activity')");
    window->requestActivate();
    QTest::qWait(550);
    const auto find = [&](const char *name) { return visual(window->contentItem(), QString::fromLatin1(name)); };
    auto *scroll = find("activityScroll");
    auto *transition = find("activityDetailTransition");
    auto *surface = find("activityDetailSurface");
    auto *page = scroll ? scroll->parentItem() : nullptr;
    check("real-activity-page-and-transition-loaded", scroll && page && transition && surface);
    if (!scroll || !page || !transition || !surface) return 2;
    const QStringList names = {"activityStatusCard", "activityTrafficCard", "activitySourcesCard", "activityDiagnosticCard", "activityConnectionsCard"};
    const QStringList keys = {"connection", "traffic", "sources", "diagnostics", "connections"};
    QList<QQuickItem *> cards;
    for (const auto &name : names) {
        auto *item = visual(window->contentItem(), name);
        check(name + "-exists", item != nullptr);
        if (!item) return 2;
        cards.append(item);
    }
    const auto rect = [&](QQuickItem *item) { return item->mapRectToItem(page, QRectF(QPointF(), item->size())); };
    QSize requestedViewport = window->size();
    const bool renderOnlyViewport = window->property("swirlViewportTest").toBool();
    const auto requestViewport = [&](const QSize &size) {
        requestedViewport = size;
        window->resize(size);
    };
    const auto screenshot = [&](const QString &name) {
        const auto image = window->grabWindow();
        const QSize actualLogical = window->size();
        const qreal actualDpr = window->devicePixelRatio();
        const QSize expectedPixels(qRound(actualLogical.width() * actualDpr), qRound(actualLogical.height() * actualDpr));
        check(name + "-requested-logical-viewport-reached", actualLogical == requestedViewport);
        check(name + "-render-image-matches-logical-size-times-actual-DPR", !image.isNull() && image.size() == expectedPixels);
        QJsonObject nativeSample{{"case", name}, {"requestedLogicalSize", dimensions(requestedViewport)},
            {"actualLogicalSize", dimensions(actualLogical)}, {"actualDevicePixelRatio", actualDpr},
            {"expectedPixelSize", dimensions(expectedPixels)}, {"imagePixelSize", dimensions(image.size())},
            {"renderOnlyViewport", renderOnlyViewport}, {"physicalWindows11Acceptance", "not-run"}};
        if (const auto *screen = window->screen()) {
            nativeSample.insert("screenName", screen->name());
            nativeSample.insert("screenGeometry", rectangle(screen->geometry()));
            nativeSample.insert("screenAvailableGeometry", rectangle(screen->availableGeometry()));
        }
#ifdef Q_OS_WIN
        // Read the actual HWND client after the native render. Enlarging the
        // test track limit must not turn a truncated native window into a pass.
        const HWND hwnd = reinterpret_cast<HWND>(window->winId());
        RECT nativeClient{}, nativeWindow{};
        POINT clientOrigin{};
        MONITORINFO monitor{sizeof(MONITORINFO)};
        const bool clientRead = hwnd && GetClientRect(hwnd, &nativeClient);
        const bool windowRead = hwnd && GetWindowRect(hwnd, &nativeWindow);
        const bool clientOriginRead = hwnd && ClientToScreen(hwnd, &clientOrigin);
        const bool monitorRead = hwnd && GetMonitorInfoW(MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST), &monitor);
        const auto fromNative = [](const RECT &value) {
            return QRect(value.left, value.top, value.right - value.left, value.bottom - value.top);
        };
        const QSize clientPixels(nativeClient.right - nativeClient.left, nativeClient.bottom - nativeClient.top);
        const QRect clientBounds(QPoint(clientOrigin.x, clientOrigin.y), clientPixels);
        const QRect desktopBounds(GetSystemMetrics(SM_XVIRTUALSCREEN), GetSystemMetrics(SM_YVIRTUALSCREEN),
            GetSystemMetrics(SM_CXVIRTUALSCREEN), GetSystemMetrics(SM_CYVIRTUALSCREEN));
        const bool desktopRead = desktopBounds.width() > 0 && desktopBounds.height() > 0;
        check(name + "-native-HWND-client-size-readable", clientRead);
        check(name + "-native-client-matches-logical-size-times-actual-DPR", clientRead && clientPixels == expectedPixels);
        check(name + "-render-image-matches-native-client-pixels", clientRead && !image.isNull() && image.size() == clientPixels);
        check(name + "-native-window-monitor-and-desktop-bounds-readable", windowRead && clientOriginRead && monitorRead && desktopRead);
        nativeSample.insert("nativeClientRead", clientRead);
        nativeSample.insert("nativeClientPixelSize", dimensions(clientPixels));
        nativeSample.insert("nativeWindowRead", windowRead);
        nativeSample.insert("nativeMonitorRead", monitorRead);
        nativeSample.insert("nativeClientOriginRead", clientOriginRead);
        nativeSample.insert("nativeVirtualDesktopRead", desktopRead);
        nativeSample.insert("nativeWindowBoundsPixels", rectangle(fromNative(nativeWindow)));
        nativeSample.insert("nativeClientBoundsPixels", rectangle(clientBounds));
        nativeSample.insert("nativeMonitorBoundsPixels", rectangle(fromNative(monitor.rcMonitor)));
        nativeSample.insert("nativeMonitorWorkAreaPixels", rectangle(fromNative(monitor.rcWork)));
        nativeSample.insert("nativeVirtualDesktopBoundsPixels", rectangle(desktopBounds));
        nativeSample.insert("windowOutsideNativeDesktop", windowRead && desktopRead
            ? QJsonValue(!desktopBounds.contains(fromNative(nativeWindow))) : QJsonValue(QJsonValue::Null));
        nativeSample.insert("clientOutsideNativeDesktop", clientRead && clientOriginRead && desktopRead
            ? QJsonValue(!desktopBounds.contains(clientBounds)) : QJsonValue(QJsonValue::Null));
        nativeSample.insert("clientOutsideNativeMonitor", clientRead && clientOriginRead && monitorRead
            ? QJsonValue(!fromNative(monitor.rcMonitor).contains(clientBounds)) : QJsonValue(QJsonValue::Null));
#else
        check(name + "-native-HWND-client-evidence-requires-Windows", false);
        nativeSample.insert("nativeClientRead", false);
#endif
        nativeViewportSamples.append(nativeSample);
        check(name + "-native-render-image-saved", !image.isNull() && image.save(directory.filePath(name + ".png")));
    };
    const auto settle = [&] {
        return QTest::qWaitFor([&] { return !transition->property("moving").toBool(); }, 2500);
    };
    const auto close = [&] {
        QMetaObject::invokeMethod(transition, "closeDetail");
        check("transition-settles-after-close", settle());
    };
    const auto scrollTo = [&](QQuickItem *card) {
        const auto local = card->mapToItem(scroll, QPointF());
        const qreal before = scroll->property("contentY").toDouble();
        const qreal limit = std::max(0.0, scroll->property("contentHeight").toDouble() - scroll->height());
        scroll->setProperty("contentY", std::clamp(before + local.y() - 2, 0.0, limit));
        QTest::qWait(40);
    };
    const auto clickCard = [&](QQuickItem *card) {
        scrollTo(card);
        // The heading is a card navigation target, outside all inner controls.
        const auto *heading = card->property("titleItem").value<QQuickItem *>();
        const auto point = heading ? heading->mapToScene(QPointF(heading->width() / 2, heading->height() / 2))
                                   : card->mapToScene(QPointF(20, 20));
        QTest::mouseClick(window, Qt::LeftButton, Qt::NoModifier, point.toPoint());
    };
    const auto captureLayout = [&](const QString &caseName) {
        QTest::mouseMove(window, QPoint(1, 1));
        scroll->setProperty("contentY", 0);
        QTest::qWait(200);
        check(caseName + "-actual-logical-size-equals-requested-case", window->size() == requestedViewport);
        const qreal contentWidth = page->property("contentLogicalWidth").toDouble();
        const qreal breakpoint = page->property("dualColumnMinimumWidth").toDouble();
        const bool wide = page->property("wide").toBool();
        QJsonObject sample{{"case", caseName}, {"logicalWidth", window->width()}, {"logicalHeight", window->height()},
            {"requestedLogicalSize", dimensions(requestedViewport)}, {"renderOnlyViewport", renderOnlyViewport},
            {"physicalWidth", window->width() * window->devicePixelRatio()}, {"physicalHeight", window->height() * window->devicePixelRatio()},
            {"devicePixelRatio", window->devicePixelRatio()}, {"contentLogicalWidth", contentWidth},
            {"dualColumnMinimumWidth", breakpoint}, {"wide", wide},
            {"viewport", rectangle(rect(scroll))}, {"contentHeight", scroll->property("contentHeight").toDouble()}};
        QList<QRectF> bounds;
        for (int index = 0; index < cards.size(); ++index) {
            const auto boundsHere = rect(cards[index]);
            bounds.append(boundsHere);
            sample.insert(names[index], rectangle(boundsHere));
            check(caseName + "-" + names[index] + "-positive-readable-size", boundsHere.width() >= 240 && boundsHere.height() >= 130);
            check(caseName + "-" + names[index] + "-opaque", cards[index]->property("color").value<QColor>().alpha() == 255);
            check(caseName + "-" + names[index] + "-inside-content-horizontal-edges",
                boundsHere.left() >= -1 && boundsHere.right() <= page->width() + 1);
            // The sources card uses its existing "view all" button instead.
            if (names[index] != QStringLiteral("activitySourcesCard")) {
                auto *chevron = visual(cards[index], QStringLiteral("activityCardChevron"));
                auto *header = chevron ? chevron->parentItem() : nullptr;
                const auto chevronBounds = chevron ? rect(chevron) : QRectF();
                const auto headerBounds = header ? rect(header) : QRectF();
                const qreal centerErrorPixels = std::abs(chevronBounds.center().y() - headerBounds.center().y()) * window->devicePixelRatio();
                check(caseName + "-" + names[index] + "-chevron-centered-within-half-physical-pixel",
                    chevron && header && centerErrorPixels <= 0.5);
                check(caseName + "-" + names[index] + "-chevron-keeps-square-size",
                    chevron && chevron->width() > 0 && chevron->width() == chevron->height());
                sample.insert(names[index] + "Chevron", QJsonObject{{"bounds", rectangle(chevronBounds)},
                    {"header", rectangle(headerBounds)}, {"centerErrorPhysicalPixels", centerErrorPixels}});
            }
            QJsonArray clippedText;
            std::function<void(QQuickItem *)> inspectText = [&](QQuickItem *item) {
                if (!item->isVisible() || item->opacity() <= 0) return;
                if (item->inherits("QQuickText") && !item->property("text").toString().isEmpty()) {
                    const auto textRect = item->mapRectToItem(cards[index], QRectF(QPointF(), item->size()));
                    if (!QRectF(QPointF(-1, -1), cards[index]->size() + QSizeF(2, 2)).contains(textRect))
                        clippedText.append(QJsonObject{{"objectName", item->objectName()}, {"text", item->property("text").toString().left(90)}, {"bounds", rectangle(textRect)}});
                }
                for (auto *child : item->childItems()) inspectText(child);
            };
            inspectText(cards[index]);
            sample.insert(names[index] + "ClippedText", clippedText);
            check(caseName + "-" + names[index] + "-text-stays-inside-card", clippedText.isEmpty());
        }
        check(caseName + "-breakpoint-follows-real-content-width", breakpoint > 0 && wide == (contentWidth >= breakpoint));
        for (int first = 0; first < bounds.size(); ++first)
            for (int second = first + 1; second < bounds.size(); ++second)
                check(caseName + "-cards-do-not-overlap-" + QString::number(first) + "-" + QString::number(second),
                    !bounds[first].adjusted(1, 1, -1, -1).intersects(bounds[second].adjusted(1, 1, -1, -1)));
        const auto status = bounds[0], traffic = bounds[1], sources = bounds[2], diagnosis = bounds[3], connections = bounds[4];
        if (wide) {
            const qreal topRatio = status.width() / (status.width() + traffic.width());
            const qreal bottomRatio = sources.width() / (sources.width() + diagnosis.width());
            sample.insert("topWidthRatio", topRatio);
            sample.insert("bottomWidthRatio", bottomRatio);
            check(caseName + "-top-row-aligned", nearScalar(status.top(), traffic.top()) && nearScalar(status.height(), traffic.height()));
            check(caseName + "-top-ratio-five-seven", std::abs(topRatio - 5.0 / 12) < 0.03);
            check(caseName + "-bottom-ratio-seven-five", std::abs(bottomRatio - 7.0 / 12) < 0.03);
            check(caseName + "-bottom-stack-matches-source", nearScalar(sources.top(), diagnosis.top())
                && nearScalar(sources.bottom(), connections.bottom()) && nearScalar(diagnosis.x(), connections.x())
                && nearScalar(diagnosis.width(), connections.width()));
            const qreal gap = traffic.left() - status.right();
            check(caseName + "-consistent-gaps", gap > 8 && gap < 25
                && nearScalar(diagnosis.left() - sources.right(), gap) && nearScalar(connections.top() - diagnosis.bottom(), gap)
                && nearScalar(sources.top() - status.bottom(), gap));
            check(caseName + "-same-page-outer-edges", nearScalar(status.left(), sources.left()) && nearScalar(traffic.right(), diagnosis.right()));
            check(caseName + "-status-row-has-no-excess-vertical-empty-space", status.height() <= std::max(290.0, scroll->height() * 0.47));
            check(caseName + "-source-reserves-summary-records", sources.height() >= 326);
            if (scroll->height() >= 596) {
                const auto viewport = rect(scroll);
                check(caseName + "-all-five-cards-fit-current-viewport", std::all_of(bounds.cbegin(), bounds.cend(), [&](const QRectF &card) {
                    return card.top() >= viewport.top() - 1 && card.bottom() <= viewport.bottom() + 1;
                }));
            }
        } else {
            for (int index = 1; index < bounds.size(); ++index)
                check(caseName + "-single-column-order-" + keys[index], bounds[index].top() > bounds[index - 1].bottom()
                    && nearScalar(bounds[index].left(), bounds[0].left()) && nearScalar(bounds[index].width(), bounds[0].width()));
            check(caseName + "-single-column-scrolls", scroll->property("contentHeight").toDouble() > scroll->height());
        }
        check(caseName + "-content-height-encloses-last-card", scroll->property("contentHeight").toDouble() + rect(scroll).top() >= bounds[4].bottom() - 1);
        if (auto *chart = find("activityTrafficChart")) check(caseName + "-trend-chart-remains-readable", chart->height() >= 110 && chart->width() >= 230);
        layouts.append(sample);
        screenshot(caseName);
    };
    const QSize initialSize = window->size();
    QString previewSizeArgument;
    for (const auto &argument : QCoreApplication::arguments())
        if (argument.startsWith("--preview-size=")) previewSizeArgument = argument.mid(QStringLiteral("--preview-size=").size());
    if (!previewSizeArgument.isEmpty()) {
        const auto parts = previewSizeArgument.split('x');
        bool widthValid = false, heightValid = false;
        const int width = parts.size() == 2 ? parts[0].toInt(&widthValid) : 0;
        const int height = parts.size() == 2 ? parts[1].toInt(&heightValid) : 0;
        const bool valid = widthValid && heightValid && width > 0 && height > 0;
        check("initial-CLI-preview-size-is-valid", valid);
        if (valid) requestedViewport = QSize(width, height);
        check("initial-CLI-preview-size-equals-actual-logical-window", valid && initialSize == requestedViewport);
    }
    if (qEnvironmentVariableIsSet("SWIRL_LAYOUT_EXPECTED_DPR"))
        check("controlled-DPR-case-has-explicit-initial-CLI-viewport", !previewSizeArgument.isEmpty());
    captureLayout("current-physical-window");
    if (nearScalar(window->width() * window->devicePixelRatio(), 1520, 20) && nearScalar(window->devicePixelRatio(), 1.5, 0.05))
        check("current-1520px-at150pct-is-dual-column", page->property("wide").toBool());
    requestViewport(QSize(1100, 760));
    captureLayout("wide-1100x760");
    check("wide-1100-window-is-dual-column", page->property("wide").toBool());
    requestViewport(QSize(1030, 672));
    captureLayout("reference-1030x672");
    check("reference-1030-window-is-dual-column", page->property("wide").toBool());
    requestViewport(QSize(1100, window->minimumHeight()));
    captureLayout("short-window");
    requestViewport(QSize(760, window->minimumHeight()));
    captureLayout("narrow-window");
    check("narrow-760-window-is-single-column", !page->property("wide").toBool());
    requestViewport(QSize(1100, 760));
    QTest::qWait(200);
    const int routeHistory = eval("AppState.historyIndex").toInt();
    for (int index = 0; index < cards.size(); ++index) {
        auto *card = cards[index];
        scrollTo(card);
        const auto origin = rect(card);
        clickCard(card);
        check(keys[index] + "-card-click-immediately-starts-expansion", transition->property("opened").toBool()
            && transition->property("detailKey").toString() == keys[index]);
        const auto storedOrigin = transition->mapRectToItem(page, transition->property("origin").toRectF());
        check(keys[index] + "-expands-from-current-card-geometry", nearRect(storedOrigin, origin, 4));
        QTest::qWait(90);
        const qreal openingProgress = transition->property("progress").toDouble();
        check(keys[index] + "-expansion-has-intermediate-geometry", transition->property("moving").toBool() && openingProgress > 0 && openingProgress < 1);
        travel.append(QJsonObject{{"detail", keys[index]}, {"phase", "expanding"}, {"progress", openingProgress}, {"surface", rectangle(rect(surface))}});
        screenshot(keys[index] + "-expanding");
        check(keys[index] + "-settles-open", settle() && transition->property("progress").toDouble() == 1);
        const auto destination = transition->mapRectToItem(page, transition->property("destination").toRectF());
        check(keys[index] + "-fills-current-detail-destination", nearRect(rect(surface), destination));
        screenshot(keys[index] + "-detail");
        QTest::keyClick(window, Qt::Key_Escape);
        QTest::qWait(75);
        const auto closingProgress = transition->property("progress").toDouble();
        check(keys[index] + "-escape-starts-visible-contraction", transition->property("moving").toBool() && closingProgress > 0 && closingProgress < 1);
        travel.append(QJsonObject{{"detail", keys[index]}, {"phase", "contracting-escape"}, {"progress", closingProgress}, {"surface", rectangle(rect(surface))}});
        screenshot(keys[index] + "-contracting-escape");
        check(keys[index] + "-returns-without-residual-shield", settle() && !transition->isVisible() && !transition->property("activeDetail").toBool());
        const auto returnedOrigin = transition->mapRectToItem(page, transition->property("origin").toRectF());
        check(keys[index] + "-returns-to-current-source-card", nearRect(returnedOrigin, rect(card), 4));
    }
    clickCard(cards[1]);
    QTest::qWait(65);
    const auto progressBeforeInterrupt = transition->property("progress").toDouble();
    const auto beforeInterrupt = rect(surface);
    // QTest::keyClick(QWindow*) processes the event loop after both press and
    // release. Compare synchronous dispatch so a normal intervening animation
    // frame is not mistaken for a discontinuity in the reversal itself.
    QKeyEvent interruptPress(QEvent::KeyPress, Qt::Key_Escape, Qt::NoModifier);
    interruptPress.setAccepted(false);
    QElapsedTimer dispatchTimer;
    dispatchTimer.start();
    const bool interruptDelivered = QCoreApplication::sendEvent(window, &interruptPress);
    const auto afterInterrupt = rect(surface);
    const auto progressAfterInterrupt = transition->property("progress").toDouble();
    const double dispatchMilliseconds = dispatchTimer.nsecsElapsed() / 1000000.0;
    QKeyEvent interruptRelease(QEvent::KeyRelease, Qt::Key_Escape, Qt::NoModifier);
    QCoreApplication::sendEvent(window, &interruptRelease);
    travel.append(QJsonObject{{"detail", "traffic"}, {"phase", "synchronous-escape-reversal"},
        {"dispatchMs", dispatchMilliseconds}, {"delivered", interruptDelivered}, {"accepted", interruptPress.isAccepted()},
        {"progressBefore", progressBeforeInterrupt}, {"progressAfter", progressAfterInterrupt},
        {"surfaceBefore", rectangle(beforeInterrupt)}, {"surfaceAfter", rectangle(afterInterrupt)}});
    check("escape-interrupts-in-progress-expansion-synchronously", interruptDelivered && progressBeforeInterrupt > 0
        && progressBeforeInterrupt < 1 && !transition->property("opened").toBool() && transition->property("moving").toBool());
    check("escape-during-expansion-preserves-drawn-geometry", nearRect(beforeInterrupt, afterInterrupt, 5));
    check("interrupted-expansion-releases-shield", settle() && !transition->isVisible());
    clickCard(cards[2]);
    check("resize-case-opens", settle() && transition->property("opened").toBool());
    requestViewport(QSize(760, window->minimumHeight()));
    QTest::qWait(200);
    check("resize-while-open-reaches-requested-logical-viewport", window->size() == requestedViewport);
    QTest::keyClick(window, Qt::Key_Escape);
    check("resize-while-open-returns-without-shield", settle() && !transition->isVisible());
    const auto resizedOrigin = transition->mapRectToItem(page, transition->property("origin").toRectF());
    check("resize-while-open-returns-to-new-single-column-position", nearRect(resizedOrigin, rect(cards[2]), 4));
    requestViewport(QSize(1100, 760));
    QTest::qWait(200);
    check("back-button-case-reaches-requested-logical-viewport", window->size() == requestedViewport);
    clickCard(cards[3]);
    check("back-button-case-opens", settle());
    if (auto *back = find("activityDetailBack"))
        QTest::mouseClick(window, Qt::LeftButton, Qt::NoModifier, back->mapToScene(QPointF(back->width() / 2, back->height() / 2)).toPoint());
    check("back-button-contracts-and-releases-shield", settle() && !transition->isVisible());
    for (int attempt = 0; attempt < 4; ++attempt) {
        clickCard(cards[attempt]);
        QTest::qWait(15);
        QTest::keyClick(window, Qt::Key_Escape);
        check("rapid-input-return-" + QString::number(attempt), settle() && !transition->isVisible());
    }
    close();
    check("main-route-and-history-preserved", eval("AppState.currentPage==='activity'").toBool() && eval("AppState.historyIndex").toInt() == routeHistory);
    check("host-system-proxy-unchanged", hostProxyBefore == SystemProxySession::snapshot());
    requestViewport(initialSize);
    check("original-logical-viewport-restored", window->size() == initialSize);
    const auto *screen = window->screen();
    QJsonArray screens;
    for (const auto *display : QGuiApplication::screens())
        screens.append(QJsonObject{{"name", display->name()}, {"geometry", rectangle(display->geometry())},
            {"availableGeometry", rectangle(display->availableGeometry())}, {"devicePixelRatio", display->devicePixelRatio()},
            {"logicalDpi", display->logicalDotsPerInch()}});
    const QJsonObject report{{"schema", 2}, {"source", "live ActivityPage.qml QObject/QQuickItem geometry"},
        {"qtVersion", QString::fromLatin1(qVersion())}, {"renderer", int(window->rendererInterface()->graphicsApi())},
        {"nativeD3D11", window->rendererInterface()->graphicsApi() == QSGRendererInterface::Direct3D11},
        {"dpiMode", nativeDpi ? "Actual Windows display scaling; no Qt scale overrides" : "Qt scale-factor simulation on the current Windows screen"},
        {"scaleFactorEnvironment", QString::fromUtf8(qgetenv("QT_SCALE_FACTOR"))},
        {"initialPreviewSizeArgument", previewSizeArgument}, {"initialActualLogicalSize", dimensions(initialSize)},
        {"renderOnlyViewport", renderOnlyViewport}, {"operatingSystem", QSysInfo::prettyProductName()},
        {"screens", screens}, {"nativeViewportSamples", nativeViewportSamples},
        {"physicalWindows11Acceptance", "not-run"}, {"hardwarePresentationAcceptance", "not-run"},
        {"limitations", QJsonArray{
            "Render-only viewport mode keeps the real HWND and Qt scene, but permits its client to extend beyond the available desktop.",
            "Win32 client dimensions and native QImage pixels establish the rendered viewport, not physical monitor coverage or hardware scan-out.",
            "The original QTest event input and application animation clocks remain in use; physical Windows 11 interaction and cross-monitor DPI acceptance were not run."}},
        {"screenLogicalDpi", screen ? screen->logicalDotsPerInch() : 0},
        {"screenDevicePixelRatio", screen ? screen->devicePixelRatio() : 0}, {"devicePixelRatio", window->devicePixelRatio()},
        {"startedAtUtc", QDateTime::currentDateTimeUtc().toString(Qt::ISODate)}, {"checks", checks},
        {"layouts", layouts}, {"animationSamples", travel}, {"failures", failures}, {"success", failures == 0}};
    QFile file(directory.filePath("activity-layout-report.json"));
    if (!file.open(QIODevice::WriteOnly) || file.write(QJsonDocument(report).toJson()) < 0) return 2;
    return failures == 0 ? 0 : 1;
}
