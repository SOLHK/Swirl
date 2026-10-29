#pragma once
#include <QFile>
#include <QJsonDocument>
#include <QJsonObject>
#include <QQuickWindow>
#include <QScreen>
#include <QTest>

inline QJsonObject fontTestViewportReport(QQuickWindow *window, const QSize &requested)
{
    const auto rect = [](const QRect &value) {
        return QJsonObject{{"x", value.x()}, {"y", value.y()},
                           {"width", value.width()}, {"height", value.height()}};
    };
    const auto *screen = window->screen();
    const auto margins = window->frameMargins();
    return {{"requestedWidth", requested.width()}, {"requestedHeight", requested.height()},
            {"logicalWidth", window->width()}, {"logicalHeight", window->height()},
            {"dpr", window->devicePixelRatio()},
            {"availableGeometry", rect(screen ? screen->availableGeometry() : QRect())},
            {"frameGeometry", rect(window->frameGeometry())},
            {"frameMargins", QJsonObject{{"left", margins.left()}, {"top", margins.top()},
                                          {"right", margins.right()}, {"bottom", margins.bottom()}}},
            {"fitsAvailableGeometry", screen && screen->availableGeometry().contains(window->frameGeometry())}};
}

// Test setup only: keep the native frame inside the real screen work area.
// QScreen geometry and QWindow frame margins already use logical coordinates;
// multiplying them by DPR would reproduce the oversized 200% viewport.
// Do not lower application minimum sizes or change Windows scale/refresh rate.
inline bool prepareFontTestViewport(QQuickWindow *window, const QSize &requested,
                                    const QString &failurePath)
{
    if (!window) return false;
    window->create();
    const auto *screen = window->screen();
    if (screen) {
        const auto available = screen->availableGeometry();
        const auto margins = window->frameMargins();
        const QSize frameExtra(margins.left() + margins.right(), margins.top() + margins.bottom());
        const QSize capacity = (available.size() - frameExtra).boundedTo(window->maximumSize());
        if (capacity.width() > 0 && capacity.height() > 0
            && window->minimumWidth() <= capacity.width()
            && window->minimumHeight() <= capacity.height()) {
            const auto size = requested.expandedTo(window->minimumSize()).boundedTo(capacity);
            window->resize(size);
            window->setFramePosition(available.topLeft()
                                     + QPoint((available.width() - size.width() - frameExtra.width()) / 2,
                                              (available.height() - size.height() - frameExtra.height()) / 2));
            window->showNormal();
            if (QTest::qWaitFor([&] {
                    return window->size() == size
                        && screen->availableGeometry().contains(window->frameGeometry());
                }, 1000)) return true;
        }
    }
    auto report = fontTestViewportReport(window, requested);
    report.insert("reason", "The native test frame does not fit the real available screen area without changing application minimum sizes.");
    QFile failure(failurePath);
    if (failure.open(QIODevice::WriteOnly)) failure.write(QJsonDocument(report).toJson());
    qCritical() << "Font acceptance viewport setup failed" << report;
    return false;
}
