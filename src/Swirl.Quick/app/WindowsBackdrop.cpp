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
        // DWM owns the outer contour, shadow and backdrop as one HWND surface.
        // QML must not cut a different (28px superellipse) hole over this frame.
        const auto oldStyle = GetWindowLongPtrW(hwnd, GWL_STYLE);
        // Keep Swirl's traffic lights as the ONLY caption controls. A native
        // WS_CAPTION can paint Microsoft's buttons into the extended frame.
        const auto style = (oldStyle & ~WS_CAPTION) | WS_THICKFRAME | WS_SYSMENU | WS_MINIMIZEBOX | WS_MAXIMIZEBOX;
        if (oldStyle != style) {
            SetWindowLongPtrW(hwnd, GWL_STYLE, style);
            SetWindowPos(hwnd, nullptr, 0, 0, 0, 0, SWP_NOMOVE|SWP_NOSIZE|SWP_NOZORDER|SWP_NOACTIVATE|SWP_FRAMECHANGED);
        }
        const int nc = 1; // DWMNCRP_DISABLED: no system caption band behind traffic lights
        DwmSetWindowAttribute(hwnd, 2, &nc, sizeof(nc));
        const DWORD border = m_dark ? RGB(70,86,108) : RGB(189,207,229);
        DwmSetWindowAttribute(hwnd, 34, &border, sizeof(border));
        const int corner = 2; // DWMWCP_ROUND, shared by every top-level window
        corners = !software && SUCCEEDED(DwmSetWindowAttribute(hwnd, 33, &corner, sizeof(corner)));
        // Qt's frameless+alpha flags request WS_EX_LAYERED even on accelerated
        // windows. DWM explicitly cannot round a layered HWND. D3D's alpha
        // swapchain + extended glass frame supplies transparency instead.
        if (corners) {
            const auto extended = GetWindowLongPtrW(hwnd,GWL_EXSTYLE);
            if (extended & WS_EX_LAYERED)
                SetWindowLongPtrW(hwnd,GWL_EXSTYLE,extended & ~WS_EX_LAYERED);
        }
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
        // Windows 11 22H2+: Desktop Acrylic samples the LIVE compositor.
        // Mica intentionally uses wallpaper; it cannot satisfy live blur-behind.
        const int backdrop = allowed ? 3 : 1; // DWMSBT_TRANSIENTWINDOW / NONE
        const HRESULT material = DwmSetWindowAttribute(hwnd,38,&backdrop,sizeof(backdrop));
        const MARGINS margins{-1,-1,-1,-1};
        const HRESULT frame = DwmExtendFrameIntoClientArea(hwnd, &margins);
        active = allowed && SUCCEEDED(material) && SUCCEEDED(frame);
        status = active ? QStringLiteral("Windows Desktop Acrylic: DWM live backdrop, native corners and shadow")
            : !m_enabled ? QStringLiteral("Opaque: application transparency disabled")
            : software ? QStringLiteral("Opaque: software renderer")
            : batterySaver ? QStringLiteral("Opaque: battery saver")
            : remote ? QStringLiteral("Opaque: remote desktop session")
            : QStringLiteral("Opaque: native backdrop unavailable (DWM 0x%1)").arg(quint32(material),8,16,QChar('0'));    } else status = QStringLiteral("Opaque: offscreen renderer");
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
#ifdef Q_OS_WIN
        SetWindowRgn(reinterpret_cast<HWND>(m_window->winId()),nullptr,TRUE);
#endif
        m_window->setMask(QRegion()); return;
    }
    // Compatibility fallback only. Native Windows 11 never receives a region:
    // regions prevent DWM from rounding the complete composition surface.
    QPainterPath path;
    const auto requested=m_window->property("swirlWindowRadius").toReal();
    const auto radius=requested>0?requested:8.0;
    path.addRoundedRect(QRectF(0,0,m_window->width(),m_window->height()),radius,radius);
    m_window->setMask(QRegion(path.toFillPolygon().toPolygon()));
}
bool WindowsBackdrop::eventFilter(QObject *object, QEvent *event) {
    if (object == m_window && event->type() == QEvent::Show)
        QTimer::singleShot(0,this,[this]{refresh();});
    else if (object == m_window && (event->type() == QEvent::Resize || event->type() == QEvent::WindowStateChange))
        QTimer::singleShot(0,this,[this]{updateCornerMask();});
    return QObject::eventFilter(object,event);
}
bool WindowsBackdrop::nativeEventFilter(const QByteArray &, void *message, qintptr *result) {
#ifdef Q_OS_WIN
    if (!m_window || !m_handle) return false;
    const auto *msg = static_cast<MSG *>(message);
    if (msg->hwnd != reinterpret_cast<HWND>(m_handle)) return false;
    switch (msg->message) {
    case WM_NCACTIVATE:
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
#ifdef SWIRL_UI_TESTS
            // Render-only viewport checks can allocate a 4K swapchain on a
            // smaller desktop. Ordinary windows retain Windows track limits.
            if(m_window->property("swirlViewportTest").toBool())info->ptMaxTrackSize={32768,32768};
#endif
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
    return isCaptureForeground();
#else
    return false;
#endif
}
bool WindowsBackdrop::isCaptureForeground() const {
#ifdef Q_OS_WIN
    const auto input=OpenInputDesktop(0,FALSE,DESKTOP_READOBJECTS);
    if(!input)return false;
    wchar_t inputName[128]{},threadName[128]{};DWORD needed=0;
    const bool same=GetUserObjectInformationW(input,UOI_NAME,inputName,sizeof(inputName),&needed) &&
        GetUserObjectInformationW(GetThreadDesktop(GetCurrentThreadId()),UOI_NAME,threadName,sizeof(threadName),&needed) &&
        wcscmp(inputName,threadName)==0;
    CloseDesktop(input);
    return same && m_handle && GetForegroundWindow()==reinterpret_cast<HWND>(m_handle);
#else
    return false;
#endif
}
void WindowsBackdrop::finishNativeCapture() {
#ifdef Q_OS_WIN
    if(m_handle&&!m_captureWasTopmost)SetWindowPos(reinterpret_cast<HWND>(m_handle),HWND_NOTOPMOST,0,0,0,0,SWP_NOMOVE|SWP_NOSIZE|SWP_NOACTIVATE);
#endif
}
