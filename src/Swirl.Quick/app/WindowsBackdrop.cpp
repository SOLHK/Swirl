#include "WindowsBackdrop.h"
#include <QQuickWindow>
#include <QGuiApplication>
#include <QEvent>
#include <QPainterPath>
#include <QPolygon>
#include <QRegion>
#ifdef Q_OS_WIN
#include <windows.h>
#include <dwmapi.h>
#endif

void WindowsBackdrop::updateCornerMask(QQuickWindow *window)
{
    if (!window) return;
    // CI uses the offscreen renderer; a native window mask is meaningful only
    // for the real Windows desktop and should not interfere with its smoke test.
    if (QGuiApplication::platformName() == QStringLiteral("offscreen")) return;
    if (window->visibility() == QWindow::Maximized ||
        window->visibility() == QWindow::FullScreen) {
        window->setMask(QRegion());
        return;
    }
    const int w = window->width();
    const int h = window->height();
    if (w <= 0 || h <= 0) return;
    QPainterPath shape;
    shape.addRoundedRect(QRectF(0, 0, w, h), 24, 24);
    window->setMask(QRegion(shape.toFillPolygon().toPolygon()));
}

bool WindowsBackdrop::eventFilter(QObject *watched, QEvent *event)
{
    if (watched == m_window && (event->type() == QEvent::Resize ||
                                event->type() == QEvent::WindowStateChange ||
                                event->type() == QEvent::Show))
        updateCornerMask(m_window);
    return QObject::eventFilter(watched, event);
}

void WindowsBackdrop::apply(QObject *object, bool enabled)
{
    auto *window = qobject_cast<QQuickWindow *>(object);
    if (!window) return;
    if (m_window != window) {
        if (m_window) m_window->removeEventFilter(this);
        m_window = window;
        window->installEventFilter(this);
    }
#ifdef Q_OS_WIN
    const HWND hwnd = reinterpret_cast<HWND>(window->winId());
    if (hwnd) {
        // Win11 round-corner preference, plus Qt's window mask fallback.
        constexpr DWORD cornerAttribute = 33; // DWMWA_WINDOW_CORNER_PREFERENCE
        const int cornerType = 2; // DWMWCP_ROUND
        DwmSetWindowAttribute(hwnd, cornerAttribute, &cornerType, sizeof(cornerType));
        constexpr DWORD backdropAttribute = 38; // DWMWA_SYSTEMBACKDROP_TYPE
        const int backdropType = enabled ? 3 : 1; // Desktop Acrylic on supported Windows 11, or none
        DwmSetWindowAttribute(hwnd, backdropAttribute, &backdropType, sizeof(backdropType));
    }
#else
    Q_UNUSED(enabled)
#endif
    updateCornerMask(window);
}
