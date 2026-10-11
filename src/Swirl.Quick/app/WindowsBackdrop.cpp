#include "WindowsBackdrop.h"
#include <QQuickWindow>
#include <QGuiApplication>
#include <QEvent>
#include <QPainterPath>
#include <QRegion>
#include <QTimer>
#include <QDebug>
#include <QScreen>
#include <QSGRendererInterface>
#ifdef Q_OS_WIN
#include <windows.h>
#include <windowsx.h>
#include <dwmapi.h>
#endif
WindowsBackdrop::WindowsBackdrop(QObject *parent) : QObject(parent) {
    if (qApp) qApp->installNativeEventFilter(this);
}
WindowsBackdrop::~WindowsBackdrop() {
    if (qApp) qApp->removeNativeEventFilter(this);
}
void WindowsBackdrop::apply(QObject *object, bool enabled, bool dark) {
    auto *window = qobject_cast<QQuickWindow *>(object);
    if (!window) return;
    if (m_window != window) {
        if (m_window) m_window->removeEventFilter(this);
        m_window = window;
        window->installEventFilter(this);
    }
    m_enabled = enabled; m_dark = dark; refresh();
}
void WindowsBackdrop::refresh() {
    if (!m_window) return;
    bool active = false, corners = false;
    QString status = QStringLiteral("Opaque: unsupported platform");
#ifdef Q_OS_WIN
    if (QGuiApplication::platformName() != QStringLiteral("offscreen")) {
        const bool software=QQuickWindow::graphicsApi()==QSGRendererInterface::Software || qEnvironmentVariable("QT_QUICK_BACKEND")==QStringLiteral("software");
        const HWND hwnd = reinterpret_cast<HWND>(m_window->winId());
        m_handle = reinterpret_cast<quintptr>(hwnd);
        // Qt marks an alpha frameless HWND as layered. That path prevents the
        // DWM system backdrop from reaching the accelerated client surface.
        // DWM's extended frame supplies per-pixel alpha instead; window opacity
        // remains 1.0. Never use SetLayeredWindowAttributes as a blur substitute.
        const auto extended = GetWindowLongPtrW(hwnd,GWL_EXSTYLE);
        if (!software && (extended & WS_EX_LAYERED))
            SetWindowLongPtrW(hwnd,GWL_EXSTYLE,extended & ~WS_EX_LAYERED);
        // Keep native snap/resize styles. Only the visible caption is removed.
        const auto oldStyle = GetWindowLongPtrW(hwnd, GWL_STYLE);
        const auto style = oldStyle | WS_THICKFRAME | WS_SYSMENU | WS_MINIMIZEBOX | WS_MAXIMIZEBOX;
        if (oldStyle != style) {
            SetWindowLongPtrW(hwnd, GWL_STYLE, style);
            SetWindowPos(hwnd, nullptr, 0, 0, 0, 0, SWP_NOMOVE|SWP_NOSIZE|SWP_NOZORDER|SWP_NOACTIVATE|SWP_FRAMECHANGED);
        }
        const int nc = 2; // DWMNCRP_ENABLED: native clipping and shadow
        DwmSetWindowAttribute(hwnd, 2, &nc, sizeof(nc));
        const DWORD noBorder = 0xFFFFFFFE;
        DwmSetWindowAttribute(hwnd, 34, &noBorder, sizeof(noBorder));
        const int corner = 2; // DWMWCP_ROUND; DWM removes it when maximized
        corners = !software && SUCCEEDED(DwmSetWindowAttribute(hwnd, 33, &corner, sizeof(corner)));
        const BOOL dark = m_dark;
        DwmSetWindowAttribute(hwnd, 20, &dark, sizeof(dark));
        HIGHCONTRASTW contrast{sizeof(HIGHCONTRASTW), 0, nullptr};
        const bool contrastKnown = SystemParametersInfoW(SPI_GETHIGHCONTRAST, sizeof(contrast), &contrast, 0);
        DWORD transparency = 0, bytes = sizeof(transparency);
        const bool transparencyKnown = RegGetValueW(HKEY_CURRENT_USER,
            L"Software\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize",
            L"EnableTransparency", RRF_RT_REG_DWORD, nullptr, &transparency, &bytes) == ERROR_SUCCESS;
        BOOL composition = FALSE;
        const bool compositionEnabled = SUCCEEDED(DwmIsCompositionEnabled(&composition)) && composition;
        SYSTEM_POWER_STATUS power{};
        const bool batterySaver=GetSystemPowerStatus(&power) && power.SystemStatusFlag==1;
        const bool remote=GetSystemMetrics(SM_REMOTESESSION)!=0;
        const bool allowed = m_enabled && !software && !batterySaver && !remote && contrastKnown && !(contrast.dwFlags & HCF_HIGHCONTRASTON)
            && transparencyKnown && transparency && compositionEnabled;
        const int backdrop = allowed ? 3 : 1; // DWMSBT_TRANSIENTWINDOW / NONE
        const HRESULT result = DwmSetWindowAttribute(hwnd, 38, &backdrop, sizeof(backdrop));
        const MARGINS margins = allowed && SUCCEEDED(result) ? MARGINS{-1,-1,-1,-1} : MARGINS{0,0,0,0};
        const HRESULT frame = DwmExtendFrameIntoClientArea(hwnd, &margins);
        active = allowed && SUCCEEDED(result) && SUCCEEDED(frame);
        if (active) status = QStringLiteral("Desktop Acrylic: DWM attribute 38 = 3, frame extended");
        else {
            const int none = 1;
            DwmSetWindowAttribute(hwnd, 38, &none, sizeof(none));
            status = !m_enabled ? QStringLiteral("Opaque: application transparency disabled")
                : software ? QStringLiteral("Opaque: software renderer")
                : batterySaver ? QStringLiteral("Opaque: battery saver")
                : remote ? QStringLiteral("Opaque: remote desktop session")
                : !contrastKnown || (contrast.dwFlags & HCF_HIGHCONTRASTON) ? QStringLiteral("Opaque: high contrast or unknown accessibility policy")
                : !transparencyKnown || !transparency ? QStringLiteral("Opaque: system transparency disabled or unavailable")
                : !compositionEnabled ? QStringLiteral("Opaque: desktop composition unavailable")
                : QStringLiteral("Opaque: unsupported DWM backdrop/frame (0x%1 / 0x%2)").arg(quint32(result),8,16,QChar('0')).arg(quint32(frame),8,16,QChar('0'));
        }
    } else status = QStringLiteral("Opaque: offscreen renderer");
#endif
    if (active != m_active || corners != m_nativeCorners || status != m_status) {
        m_active = active; m_nativeCorners = corners; m_status = status;
        qInfo().noquote() << "Window composition:" << status;
        emit changed();
    }
    updateCornerMask();
}
void WindowsBackdrop::updateCornerMask() {
    if (!m_window || QGuiApplication::platformName() == QStringLiteral("offscreen")) return;
    if (m_nativeCorners || m_window->visibility() == QWindow::Maximized || m_window->visibility() == QWindow::FullScreen) {
        m_window->setMask(QRegion()); return;
    }
    QPainterPath shape;
    const qreal radius = m_window->property("swirlWindowRadius").toReal();
    shape.addRoundedRect(QRectF(0,0,m_window->width(),m_window->height()),radius,radius);
    m_window->setMask(QRegion(shape.toFillPolygon().toPolygon()));
}
bool WindowsBackdrop::eventFilter(QObject *object, QEvent *event) {
    if (object == m_window && (event->type() == QEvent::Resize || event->type() == QEvent::WindowStateChange || event->type() == QEvent::Show)) updateCornerMask();
    return QObject::eventFilter(object,event);
}
bool WindowsBackdrop::nativeEventFilter(const QByteArray &, void *message, qintptr *result) {
#ifdef Q_OS_WIN
    if (!m_window || !m_handle) return false;
    const auto *msg = static_cast<MSG *>(message);
    if (msg->hwnd != reinterpret_cast<HWND>(m_handle)) return false;
    switch (msg->message) {
    case WM_NCACTIVATE:
        // Qt 6 consumes this for frameless windows. DWM still needs the native
        // activation notification to switch Acrylic out of its opaque fallback.
        *result=DefWindowProcW(msg->hwnd,msg->message,msg->wParam,-1);
        return true;
    case WM_NCCALCSIZE:
        if (msg->wParam) { *result = 0; return true; } break;
    case WM_GETMINMAXINFO: {
        MONITORINFO monitor{sizeof(MONITORINFO)};
        if (GetMonitorInfoW(MonitorFromWindow(msg->hwnd,MONITOR_DEFAULTTONEAREST), &monitor)) {
            auto *info = reinterpret_cast<MINMAXINFO *>(msg->lParam);
            info->ptMaxPosition = {monitor.rcWork.left-monitor.rcMonitor.left,monitor.rcWork.top-monitor.rcMonitor.top};
            info->ptMaxSize = {monitor.rcWork.right-monitor.rcWork.left,monitor.rcWork.bottom-monitor.rcWork.top};
            const auto dpi = m_window->devicePixelRatio();
            info->ptMinTrackSize = {LONG(m_window->minimumWidth()*dpi),LONG(m_window->minimumHeight()*dpi)};
            *result = 0; return true;
        } break;
    }
    case WM_NCHITTEST: {
        if (IsZoomed(msg->hwnd)) break;
        RECT r; GetWindowRect(msg->hwnd,&r);
        const int x = GET_X_LPARAM(msg->lParam), y = GET_Y_LPARAM(msg->lParam);
        const int border = qMax(5,int(6*m_window->devicePixelRatio()));
        const bool l=x<r.left+border, right=x>=r.right-border, t=y<r.top+border, b=y>=r.bottom-border;
        if (l||right||t||b) {
            *result = t ? (l ? HTTOPLEFT : right ? HTTOPRIGHT : HTTOP) : b ? (l ? HTBOTTOMLEFT : right ? HTBOTTOMRIGHT : HTBOTTOM) : l ? HTLEFT : HTRIGHT;
            return true;
        } break;
    }
    case WM_SETTINGCHANGE: case WM_THEMECHANGED: case WM_DWMCOMPOSITIONCHANGED:
        QTimer::singleShot(0,this,[this]{refresh();}); break;
    }
#else
    Q_UNUSED(message) Q_UNUSED(result)
#endif
    return false;
}
void WindowsBackdrop::showSystemMenu() {
#ifdef Q_OS_WIN
    if (!m_window) return;
    const HWND hwnd = reinterpret_cast<HWND>(m_window->winId());
    RECT r; GetWindowRect(hwnd,&r);
    const auto menu = GetSystemMenu(hwnd,FALSE);
    const bool maximized = IsZoomed(hwnd);
    EnableMenuItem(menu,SC_RESTORE,MF_BYCOMMAND|(maximized?MF_ENABLED:MF_GRAYED));
    EnableMenuItem(menu,SC_MAXIMIZE,MF_BYCOMMAND|(maximized?MF_GRAYED:MF_ENABLED));
    EnableMenuItem(menu,SC_SIZE,MF_BYCOMMAND|(maximized?MF_GRAYED:MF_ENABLED));
    const int command = TrackPopupMenu(menu,TPM_RETURNCMD|TPM_LEFTALIGN,r.left+16,r.top+40,0,hwnd,nullptr);
    if (command) PostMessageW(hwnd,WM_SYSCOMMAND,command,0);
#endif
}
bool WindowsBackdrop::prepareNativeCapture() {
#ifdef Q_OS_WIN
    if (!m_handle || !m_window) return false;
    const HWND hwnd=reinterpret_cast<HWND>(m_handle);
    m_captureWasTopmost=(GetWindowLongPtrW(hwnd,GWL_EXSTYLE)&WS_EX_TOPMOST)!=0;
    SetWindowPos(hwnd,HWND_TOPMOST,0,0,0,0,SWP_NOMOVE|SWP_NOSIZE);
    if(GetForegroundWindow()!=hwnd) {
        const DWORD foregroundThread=GetWindowThreadProcessId(GetForegroundWindow(),nullptr);
        const DWORD currentThread=GetCurrentThreadId();
        const bool attached=foregroundThread!=currentThread && AttachThreadInput(currentThread,foregroundThread,TRUE);
        SetForegroundWindow(hwnd);
        if(attached)AttachThreadInput(currentThread,foregroundThread,FALSE);
    }
    return GetForegroundWindow()==hwnd;
#else
    return false;
#endif
}
bool WindowsBackdrop::isCaptureForeground() const {
#ifdef Q_OS_WIN
    return m_handle && GetForegroundWindow()==reinterpret_cast<HWND>(m_handle);
#else
    return false;
#endif
}
void WindowsBackdrop::finishNativeCapture() {
#ifdef Q_OS_WIN
    if(m_handle&&!m_captureWasTopmost)SetWindowPos(reinterpret_cast<HWND>(m_handle),HWND_NOTOPMOST,0,0,0,0,SWP_NOMOVE|SWP_NOSIZE|SWP_NOACTIVATE);
#endif
}
