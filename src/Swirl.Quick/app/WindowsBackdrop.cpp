#include "WindowsBackdrop.h"
#include <QQuickWindow>
#ifdef Q_OS_WIN
#include <windows.h>
#include <dwmapi.h>
#endif
void WindowsBackdrop::apply(QObject *object, bool enabled)
{
    auto *window = qobject_cast<QQuickWindow *>(object);
    if (!window) return;
#ifdef Q_OS_WIN
    // Request rounded top-level corners on Windows 11; Qt draws transparent
    // rounded corners when the platform lacks this DWM preference.
    constexpr DWORD cornerAttribute = 33; // DWMWA_WINDOW_CORNER_PREFERENCE
    const int cornerType = 2; // DWMWCP_ROUND
    const HWND hwnd = reinterpret_cast<HWND>(window->winId());
    if (hwnd)
        DwmSetWindowAttribute(hwnd, cornerAttribute, &cornerType, sizeof(cornerType));
    // 38 is DWMWA_SYSTEMBACKDROP_TYPE on supported Windows 11.
    // Return value may indicate unsupported Windows 10: solid fallback remains.
    constexpr DWORD attribute = 38;
    const int type = enabled ? 2 : 1; // Mica or disabled
    if (hwnd)
        DwmSetWindowAttribute(hwnd, attribute, &type, sizeof(type));
#else
    Q_UNUSED(enabled)
#endif
}
