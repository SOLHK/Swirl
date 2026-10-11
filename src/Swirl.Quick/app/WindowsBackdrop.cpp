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
#ifdef Q_OS_WIN
    // The alpha surface already has antialiased QML corners. A binary HRGN
    // plus DWM's independent frame leaves small gray corner fragments at DPI.
    window->setMask(QRegion());
    return;
#endif
    if (window->visibility() == QWindow::Maximized ||
        window->visibility() == QWindow::FullScreen) {
        window->setMask(QRegion());
        return;
    }
    const int w = window->width();
    const int h = window->height();
    if (w <= 0 || h <= 0) return;
    QPainterPath shape;
    const qreal radius = window->property("swirlWindowRadius").toReal();
    shape.addRoundedRect(QRectF(0, 0, w, h), radius, radius);
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
        // QML owns the complete rounded alpha silhouette. Suppress the native
        // non-client frame and its different-radius border/shadow underneath.
        constexpr DWORD ncPolicyAttribute = 2; // DWMWA_NCRENDERING_POLICY
        const int ncDisabled = 1; // DWMNCRP_DISABLED
        DwmSetWindowAttribute(hwnd, ncPolicyAttribute, &ncDisabled, sizeof(ncDisabled));
        constexpr DWORD borderAttribute = 34; // DWMWA_BORDER_COLOR
        const DWORD noBorder = 0xFFFFFFFE; // DWMWA_COLOR_NONE
        DwmSetWindowAttribute(hwnd, borderAttribute, &noBorder, sizeof(noBorder));
        constexpr DWORD cornerAttribute = 33; // DWMWA_WINDOW_CORNER_PREFERENCE
        const int cornerType = 1; // DWMWCP_DONOTROUND (QML supplies the radius)
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
