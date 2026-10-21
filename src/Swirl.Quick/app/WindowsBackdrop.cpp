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
#include <QImage>
#include <cmath>
#include <cstring>
#ifdef Q_OS_WIN
#include <windows.h>
#include <windowsx.h>
#include <dwmapi.h>

namespace {
// Evaluate a circular corner at physical pixel centres. Mirroring each row
// makes all four curves identical at fractional DPI, without rounding the
// design radius to a logical pixel or allocating a whole-window texture.
HRGN roundedWindowRegion(int width, int height, qreal radius) {
    radius = qBound<qreal>(0, radius, qMin(width, height) / 2.0);
    const int rows = qCeil(radius);
    const HRGN region = CreateRectRgn(0, rows, width, height - rows);
    if (!region) return nullptr;
    for (int y = 0; y < rows; ++y) {
        const qreal dy = qMax<qreal>(0, radius - y - 0.5);
        const int inset = qMax(0, qCeil(radius - std::sqrt(qMax<qreal>(0, radius * radius - dy * dy)) - 0.5));
        const HRGN top = CreateRectRgn(inset, y, width - inset, y + 1);
        const HRGN bottom = CreateRectRgn(inset, height - y - 1, width - inset, height - y);
        if (top) { CombineRgn(region, region, top, RGN_OR); DeleteObject(top); }
        if (bottom) { CombineRgn(region, region, bottom, RGN_OR); DeleteObject(bottom); }
    }
    return region;
}

LRESULT CALLBACK shadowWindowProc(HWND hwnd, UINT message, WPARAM wparam, LPARAM lparam) {
    if (message == WM_NCHITTEST) return HTTRANSPARENT;
    if (message == WM_MOUSEACTIVATE) return MA_NOACTIVATE;
    return DefWindowProcW(hwnd, message, wparam, lparam);
}

HWND createShadowWindow() {
    static const auto registered = [] {
        WNDCLASSEXW cls{};
        cls.cbSize = sizeof(cls); cls.hInstance = GetModuleHandleW(nullptr);
        cls.lpfnWndProc = shadowWindowProc; cls.lpszClassName = L"SwirlExactContourShadow";
        return RegisterClassExW(&cls);
    }();
    if (!registered) return nullptr;
    // No owner HWND: owned popup windows must stay ABOVE their owner, which
    // would cover translucent client content. This pure visual sibling is
    // explicitly kept immediately below its shell and destroyed with it.
    return CreateWindowExW(WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE | WS_EX_TRANSPARENT | WS_EX_LAYERED,
        L"SwirlExactContourShadow", L"", WS_POPUP, 0, 0, 0, 0, nullptr, nullptr, GetModuleHandleW(nullptr), nullptr);
}

qreal roundedDistance(qreal x, qreal y, qreal width, qreal height, qreal radius) {
    const qreal dx = std::abs(x - width / 2) - (width / 2 - radius);
    const qreal dy = std::abs(y - height / 2) - (height / 2 - radius);
    return std::hypot(qMax<qreal>(dx, 0), qMax<qreal>(dy, 0)) + qMin(qMax(dx, dy), qreal(0)) - radius;
}

QImage shadowImage(QSize body, qreal radius, qreal dpr, bool active) {
    const int padding = qCeil(20 * dpr);
    const qreal sigma = 6.0 * dpr, offset = 2.5 * dpr;
    const qreal strength = active ? 0.22 : 0.14;
    QImage image(body + QSize(padding * 2, padding * 2), QImage::Format_ARGB32_Premultiplied);
    image.fill(Qt::transparent);
    // Only the perimeter is painted. The interior stays completely clear so
    // the main window's Acrylic never blurs an artificial dark rectangle.
    for (int y = 0; y < image.height(); ++y) {
        auto *row = reinterpret_cast<QRgb *>(image.scanLine(y));
        const qreal localY = y + 0.5 - padding;
        int clearLeft = image.width(), clearRight = image.width();
        if (localY >= 0 && localY < body.height()) {
            const qreal dy = qMax<qreal>(0, qMax(radius - localY, localY - (body.height() - radius)));
            const qreal inset = radius - std::sqrt(qMax<qreal>(0, radius * radius - dy * dy));
            clearLeft = padding + qMax(0, qCeil(inset - 0.5));
            clearRight = padding + body.width() - qMax(0, qCeil(inset - 0.5));
        }
        for (int x = 0; x < image.width(); ++x) {
            if (x == clearLeft) { x = clearRight; if (x >= image.width()) break; }
            const qreal localX = x + 0.5 - padding;
            if (localX >= radius && localX < body.width() - radius
                && localY >= 0 && localY < body.height()) continue;
            if (localY >= radius && localY < body.height() - radius
                && localX >= 0 && localX < body.width()) continue;
            if (roundedDistance(localX, localY, body.width(), body.height(), radius) <= 0) continue;
            const qreal distance = qMax<qreal>(0, roundedDistance(localX, localY - offset, body.width(), body.height(), radius));
            const int alpha = qRound(255 * strength * std::exp(-distance * distance / (2 * sigma * sigma)));
            row[x] = qRgba(0, 0, 0, alpha);
        }
    }
    return image;
}
}
#endif
WindowsBackdrop::WindowsBackdrop(QObject *parent) : QObject(parent) {
    if (qApp) qApp->installNativeEventFilter(this);
}
WindowsBackdrop::~WindowsBackdrop() {
    destroyBackdropBlur();
    destroyCompatibilityShadow();
    if (qApp) qApp->removeNativeEventFilter(this);
}
void WindowsBackdrop::apply(QObject *object, bool enabled, bool dark) {
    auto *window = qobject_cast<QQuickWindow *>(object);
    if (!window) return;
    if (m_window != window) {
        if (m_window) m_window->removeEventFilter(this);
        destroyCompatibilityShadow();
        destroyBackdropBlur();
        m_window = window;
        window->installEventFilter(this);
        connect(window, &QObject::destroyed, this, [this, window] {
            if (!m_window || m_window.data() == window) {destroyCompatibilityShadow();destroyBackdropBlur();}
        });
    }
    m_enabled = enabled; m_dark = dark; refresh();
}
void WindowsBackdrop::refresh() {
    if (!m_window) return;
    bool active = false, corners = false, translucent = false;
    QString status = QStringLiteral("Opaque: unsupported platform");
#ifdef Q_OS_WIN
    if (QGuiApplication::platformName() != QStringLiteral("offscreen")) {
        const bool software=QQuickWindow::graphicsApi()==QSGRendererInterface::Software || qEnvironmentVariable("QT_QUICK_BACKEND")==QStringLiteral("software");
        const HWND hwnd = reinterpret_cast<HWND>(m_window->winId());
        if (m_handle != reinterpret_cast<quintptr>(hwnd)) m_regionSize = {};
        m_handle = reinterpret_cast<quintptr>(hwnd);
        const bool exact = m_window->property("swirlExactWindowRadius").toBool();
        const auto oldStyle = GetWindowLongPtrW(hwnd, GWL_STYLE);
        // Keep Swirl's traffic lights as the ONLY caption controls. A native
        // WS_CAPTION can paint Microsoft's buttons into the extended frame.
        const auto style = (oldStyle & ~WS_CAPTION) | WS_THICKFRAME | WS_SYSMENU | WS_MINIMIZEBOX | WS_MAXIMIZEBOX;
        if (oldStyle != style) {
            SetWindowLongPtrW(hwnd, GWL_STYLE, style);
            SetWindowPos(hwnd, nullptr, 0, 0, 0, 0, SWP_NOMOVE|SWP_NOSIZE|SWP_NOZORDER|SWP_NOACTIVATE|SWP_FRAMECHANGED);
        }
        // Exact regions cannot receive the system's automatic rounded shadow.
        // Their input-transparent sibling supplies the matching shadow below.
        const int nc = 1; // DWMNCRP_DISABLED: no system caption band
        DwmSetWindowAttribute(hwnd, 2, &nc, sizeof(nc));
        const DWORD border = exact ? 0xFFFFFFFE : m_dark ? RGB(70,86,108) : RGB(189,207,229); // DWMWA_COLOR_NONE
        DwmSetWindowAttribute(hwnd, 34, &border, sizeof(border));
        const int corner = exact ? 1 : 2; // DONOTROUND: do not stack a preset curve over the exact region
        const auto cornerResult = DwmSetWindowAttribute(hwnd, 33, &corner, sizeof(corner));
        corners = exact ? m_exactCorners : !software && SUCCEEDED(cornerResult);
        // Qt's frameless+alpha flags request WS_EX_LAYERED even on accelerated
        // windows. DWM explicitly cannot round a layered HWND. D3D's alpha
        // swapchain + extended glass frame supplies transparency instead.
        if (!software) {
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
        // DWMSBT_TRANSIENTWINDOW paints a full HWND brush even outside a
        // custom region on Windows 11. Keep exact corners free of pale square
        // tips by using the existing opaque palette for this capability case.
        // The saved transparency preference is retained for preset windows.
        const bool transparencyAllowed = m_enabled && !software && !batterySaver && !remote && contrastKnown && !(contrast.dwFlags & HCF_HIGHCONTRASTON)
            && transparencyKnown && transparency && compositionEnabled;
        const bool allowed = transparencyAllowed && !exact;
        // Preserve subtle live desktop transmission with exact AA corners.
        // This is alpha composition, explicitly not system Acrylic blur.
        translucent = transparencyAllowed && exact;
        // Windows 11 22H2+: Desktop Acrylic samples the LIVE compositor.
        // Mica intentionally uses wallpaper; it cannot satisfy live blur-behind.
        const int backdrop = allowed ? 3 : 1; // DWMSBT_TRANSIENTWINDOW / NONE
        const HRESULT material = DwmSetWindowAttribute(hwnd,38,&backdrop,sizeof(backdrop));
        const MARGINS margins{-1,-1,-1,-1};
        const HRESULT frame = DwmExtendFrameIntoClientArea(hwnd, &margins);
        active = allowed && SUCCEEDED(material) && SUCCEEDED(frame);
        status = active ? QStringLiteral("Windows Desktop Acrylic: DWM live backdrop, %1 contour").arg(exact ? QStringLiteral("exact HWND") : QStringLiteral("native preset"))
            : !m_enabled ? QStringLiteral("Opaque: application transparency disabled")
            : translucent ? QStringLiteral("Alpha translucency: exact 10pt contour; system Acrylic unavailable for custom contours")
            : exact ? QStringLiteral("Opaque: exact 10pt contour; system transparency policy or renderer requires fallback")
            : software ? QStringLiteral("Opaque: software renderer")
            : batterySaver ? QStringLiteral("Opaque: battery saver")
            : remote ? QStringLiteral("Opaque: remote desktop session")
            : QStringLiteral("Opaque: native backdrop unavailable (DWM 0x%1)").arg(quint32(material),8,16,QChar('0'));    } else status = QStringLiteral("Opaque: offscreen renderer");
#endif
    if (active != m_active || translucent != m_translucent || corners != m_nativeCorners || status != m_status) {
        m_active = active; m_translucent = translucent; m_nativeCorners = corners; m_status = status;
        qInfo().noquote() << "Window composition:" << status;
        emit changed();
    }
    updateCornerMask();
}
void WindowsBackdrop::updateCornerMask() {
    if (!m_window || QGuiApplication::platformName() == QStringLiteral("offscreen")) return;
    updateBackdropBlur();
    const bool rectangular = m_window->visibility() == QWindow::Maximized || m_window->visibility() == QWindow::FullScreen;
    const auto requested = m_window->property("swirlWindowRadius").toReal();
    const auto radius = requested > 0 ? requested : 10.0 * 96.0 / 72.0;
#ifdef Q_OS_WIN
    if (m_window->property("swirlExactWindowRadius").toBool()) {
        const HWND hwnd = reinterpret_cast<HWND>(m_window->winId());
        RECT bounds{};
        if (!GetWindowRect(hwnd, &bounds)) return;
        const QSize physicalSize(bounds.right - bounds.left, bounds.bottom - bounds.top);
        const qreal dpr = m_window->devicePixelRatio();
        const qreal effectiveRadius = rectangular ? 0 : radius;
        if (m_exactCorners && m_regionSize == physicalSize && qFuzzyCompare(m_regionDpr, dpr)
            && qFuzzyCompare(m_cornerRadius + 1, effectiveRadius + 1)) { updateCompatibilityShadow(); return; }
        const bool software=QQuickWindow::graphicsApi()==QSGRendererInterface::Software;
        // Accelerated windows feather the final framebuffer alpha using four
        // tiny WindowEdge quads. An integer HRGN would cut those AA samples off.
        // Software remains an explicitly reported binary compatibility path.
        const HRGN region = rectangular || !software ? nullptr : roundedWindowRegion(physicalSize.width(), physicalSize.height(), radius * dpr);
        if (!rectangular && software && !region) return;
        // Windows takes ownership only after a successful SetWindowRgn.
        if (!SetWindowRgn(hwnd, region, FALSE)) {
            if (region) DeleteObject(region);
            qWarning() << "Exact window contour failed" << GetLastError();
            return;
        }
        m_regionSize = physicalSize; m_regionDpr = dpr;
        m_cornerRadius = effectiveRadius;
        m_exactCorners = true; m_nativeCorners = true;
        updateCompatibilityShadow();
        emit changed();
        return;
    }
#endif
    if (m_exactCorners) { m_exactCorners = false; m_regionSize = {}; destroyCompatibilityShadow(); emit changed(); }
    if (m_nativeCorners || rectangular) {
#ifdef Q_OS_WIN
        SetWindowRgn(reinterpret_cast<HWND>(m_window->winId()),nullptr,TRUE);
#endif
        m_window->setMask(QRegion()); return;
    }
    // Compatibility fallback for platforms without the Win32 region path.
    QPainterPath path;
    path.addRoundedRect(QRectF(0,0,m_window->width(),m_window->height()),radius,radius);
    m_window->setMask(QRegion(path.toFillPolygon().toPolygon()));
}
void WindowsBackdrop::applyTransientClip(QObject *object, const QRectF &logicalRect, qreal logicalRadius) {
    auto *window = qobject_cast<QQuickWindow *>(object);
    if (!window || window == m_window || logicalRect.isEmpty()) return;
#ifdef Q_OS_WIN
    if(QQuickWindow::graphicsApi()!=QSGRendererInterface::Software){
        // The flight surface owns an alpha edge too. Avoid a synchronous
        // HWND region rebuild/redraw on every animation tick.
        return;
    }
    const qreal dpr = window->devicePixelRatio();
    const int left = qRound(logicalRect.x() * dpr), top = qRound(logicalRect.y() * dpr);
    const int right = qRound((logicalRect.x() + logicalRect.width()) * dpr);
    const int bottom = qRound((logicalRect.y() + logicalRect.height()) * dpr);
    const HRGN region = roundedWindowRegion(right - left, bottom - top, qMax<qreal>(0, logicalRadius) * dpr);
    if (!region) return;
    OffsetRgn(region, left, top);
    if (!SetWindowRgn(reinterpret_cast<HWND>(window->winId()), region, TRUE)) DeleteObject(region);
#else
    QPainterPath path;
    path.addRoundedRect(logicalRect, logicalRadius, logicalRadius);
    window->setMask(QRegion(path.toFillPolygon().toPolygon()));
#endif
}
void WindowsBackdrop::clearTransientClip(QObject *object) {
    auto *window = qobject_cast<QQuickWindow *>(object);
    if (!window || window == m_window) return;
#ifdef Q_OS_WIN
    SetWindowRgn(reinterpret_cast<HWND>(window->winId()), nullptr, TRUE);
#else
    window->setMask({});
#endif
}

void WindowsBackdrop::destroyCompatibilityShadow() {
#ifdef Q_OS_WIN
    if (m_shadowHandle) DestroyWindow(reinterpret_cast<HWND>(m_shadowHandle));
#endif
    m_shadowHandle = 0; m_shadowSize = {}; m_shadowVisible = false;
}

void WindowsBackdrop::updateCompatibilityShadow() {
#ifdef Q_OS_WIN
    const auto setVisible = [this](bool visible) {
        if (visible == m_shadowVisible) return;
        m_shadowVisible = visible; emit changed();
    };
    if (!m_window || !m_exactCorners || !m_window->isVisible() || m_window->property("swirlSuppressShadow").toBool()
        || m_window->visibility() == QWindow::Maximized || m_window->visibility() == QWindow::FullScreen
        || m_window->visibility() == QWindow::Minimized) {
        if (m_shadowHandle) ShowWindow(reinterpret_cast<HWND>(m_shadowHandle), SW_HIDE);
        setVisible(false); return;
    }
    const HWND target = reinterpret_cast<HWND>(m_window->winId());
    RECT bounds{};
    if (!GetWindowRect(target, &bounds)) return;
    const QSize body(bounds.right - bounds.left, bounds.bottom - bounds.top);
    const qreal dpr = m_window->devicePixelRatio(), radius = m_cornerRadius * dpr;
    const bool active = m_window->isActive();
    const int padding = qCeil(20 * dpr);
    if (!m_shadowHandle) {
        m_shadowHandle = reinterpret_cast<quintptr>(createShadowWindow());
        m_shadowSize = {};
    }
    if (!m_shadowHandle) return;
    const HWND shadow = reinterpret_cast<HWND>(m_shadowHandle);
    if (m_shadowSize != body || !qFuzzyCompare(m_shadowRadius + 1, radius + 1)
        || !qFuzzyCompare(m_shadowDpr, dpr) || m_shadowActive != active) {
        const auto image = shadowImage(body, radius, dpr, active);
        BITMAPINFO info{};
        info.bmiHeader.biSize = sizeof(BITMAPINFOHEADER);
        info.bmiHeader.biWidth = image.width(); info.bmiHeader.biHeight = -image.height();
        info.bmiHeader.biPlanes = 1; info.bmiHeader.biBitCount = 32; info.bmiHeader.biCompression = BI_RGB;
        const HDC screen = GetDC(nullptr), memory = CreateCompatibleDC(screen);
        void *bits = nullptr;
        const HBITMAP bitmap = CreateDIBSection(memory, &info, DIB_RGB_COLORS, &bits, nullptr, 0);
        bool success = false;
        if (bitmap && bits) {
            std::memcpy(bits, image.constBits(), size_t(image.sizeInBytes()));
            const auto previous = SelectObject(memory, bitmap);
            POINT position{bounds.left - padding, bounds.top - padding}, source{0, 0};
            SIZE size{image.width(), image.height()};
            BLENDFUNCTION blend{AC_SRC_OVER, 0, 255, AC_SRC_ALPHA};
            success = UpdateLayeredWindow(shadow, screen, &position, &size, memory, &source, 0, &blend, ULW_ALPHA);
            SelectObject(memory, previous);
        }
        if (bitmap) DeleteObject(bitmap);
        DeleteDC(memory); ReleaseDC(nullptr, screen);
        if (!success) { ShowWindow(shadow, SW_HIDE); setVisible(false); return; }
        ++m_shadowBuildCount;
        m_shadowSize = body; m_shadowRadius = radius; m_shadowDpr = dpr; m_shadowActive = active;
    }
    // Moving changes only the cached HWND's placement. There is no desktop
    // sampling, timer, input capture, or per-frame image reconstruction.
    const bool visible = SetWindowPos(shadow, target, bounds.left - padding, bounds.top - padding, 0, 0,
        SWP_NOSIZE | SWP_NOACTIVATE | SWP_NOOWNERZORDER | SWP_SHOWWINDOW);
    setVisible(visible);
#endif
}
void WindowsBackdrop::destroyBackdropBlur() {
#ifdef Q_OS_WIN
    if(m_blurHandle)DestroyWindow(reinterpret_cast<HWND>(m_blurHandle));
#endif
    m_blurHandle=0;
    m_blurSize={};m_blurDarkSet=false;
    if(m_blurActive){m_blurActive=false;emit changed();}
}
void WindowsBackdrop::updateBackdropBlur() {
#ifdef Q_OS_WIN
    const auto width=m_window && m_window->property("swirlUnifiedBlur").toBool()?m_window->width():0;
    const bool available=m_window && m_translucent && width>0;
    if(!available){destroyBackdropBlur();return;}
    if(!m_blurHandle){
        static const auto registered=[] {
            WNDCLASSEXW cls{};cls.cbSize=sizeof(cls);cls.hInstance=GetModuleHandleW(nullptr);
            cls.lpfnWndProc=[](HWND hwnd,UINT message,WPARAM wp,LPARAM lp)->LRESULT {
                if(message==WM_NCCALCSIZE && wp)return 0;
                return shadowWindowProc(hwnd,message,wp,lp);
            };
            cls.lpszClassName=L"SwirlUnifiedBackdrop";return RegisterClassExW(&cls);
        }();
        if(!registered)return;
        const HWND blur=CreateWindowExW(WS_EX_TOOLWINDOW|WS_EX_NOACTIVATE|WS_EX_TRANSPARENT,
            L"SwirlUnifiedBackdrop",L"",WS_POPUP|WS_THICKFRAME,0,0,0,0,nullptr,nullptr,GetModuleHandleW(nullptr),nullptr);
        if(!blur)return;
        const int material=1,corner=2,nc=1;const DWORD border=0xFFFFFFFE;
        const BOOL dark=m_dark;const MARGINS margins{-1,-1,-1,-1};
        DwmSetWindowAttribute(blur,2,&nc,sizeof(nc));
        DwmSetWindowAttribute(blur,33,&corner,sizeof(corner));
        DwmSetWindowAttribute(blur,34,&border,sizeof(border));
        m_blurDarkSet=SUCCEEDED(DwmSetWindowAttribute(blur,20,&dark,sizeof(dark)));
        m_blurDark=m_dark;
        if(FAILED(DwmSetWindowAttribute(blur,38,&material,sizeof(material))) || FAILED(DwmExtendFrameIntoClientArea(blur,&margins))){DestroyWindow(blur);return;}
        // Desktop Acrylic becomes opaque for an inactive helper HWND. Use
        // the compositor's blur policy for this non-activating visual only.
        // Resolve the optional API dynamically and keep the alpha fallback
        // when Windows does not expose it; never claim a blur from alpha.
        struct AccentPolicy {int state;int flags;DWORD tint;int animation;};
        struct CompositionData {int attribute;void *data;SIZE_T size;};
        using SetComposition=BOOL(WINAPI *)(HWND,CompositionData *);
        const auto setComposition=reinterpret_cast<SetComposition>(GetProcAddress(GetModuleHandleW(L"user32.dll"),"SetWindowCompositionAttribute"));
        AccentPolicy accent{3,0,0,0};CompositionData data{19,&accent,sizeof(accent)};
        if(!setComposition || !setComposition(blur,&data)){DestroyWindow(blur);return;}
        m_blurHandle=reinterpret_cast<quintptr>(blur);
        m_blurActive=true;emit changed();
    }
    const HWND blur=reinterpret_cast<HWND>(m_blurHandle);
    if(!m_window->isVisible() || m_window->visibility()==QWindow::Minimized){ShowWindow(blur,SW_HIDE);return;}
    const HWND shell=reinterpret_cast<HWND>(m_window->winId());RECT bounds{};
    if(!GetWindowRect(shell,&bounds))return;
    if(!m_blurDarkSet || m_blurDark!=m_dark){
        const BOOL dark=m_dark;
        m_blurDarkSet=SUCCEEDED(DwmSetWindowAttribute(blur,20,&dark,sizeof(dark)));
        m_blurDark=m_dark;
    }
    const auto dpr=m_window->devicePixelRatio();const int inset=qMax(1,qCeil(dpr));
    // One compositor-only surface covers the entire shell. Sidebar and
    // workspace sample the same live backdrop, with one uniform tint above.
    // No desktop capture, CPU blur, foreground texture or timer is involved.
    const QSize size(bounds.right-bounds.left-2*inset,bounds.bottom-bounds.top-2*inset);
    // During a move the compositor surface keeps its size; only its position changes.
    const UINT flags=SWP_NOACTIVATE|SWP_NOOWNERZORDER|SWP_SHOWWINDOW|
        (size==m_blurSize?SWP_NOSIZE:0);
    if(SetWindowPos(blur,shell,bounds.left+inset,bounds.top+inset,size.width(),size.height(),flags))
        m_blurSize=size;
#endif
}
void WindowsBackdrop::scheduleCornerUpdate() {
    if (m_cornerUpdateQueued) return;
    m_cornerUpdateQueued = true;
    QTimer::singleShot(0, this, [this] { m_cornerUpdateQueued = false; updateCornerMask(); });
}
bool WindowsBackdrop::eventFilter(QObject *object, QEvent *event) {
    if (object == m_window && event->type() == QEvent::Show)
        QTimer::singleShot(0,this,[this]{refresh();});
    else if (object == m_window && (event->type() == QEvent::Resize || event->type() == QEvent::WindowStateChange
             || event->type() == QEvent::DevicePixelRatioChange || event->type() == QEvent::Move
             || event->type() == QEvent::WindowActivate || event->type() == QEvent::WindowDeactivate || event->type() == QEvent::Hide))
        scheduleCornerUpdate();
    return QObject::eventFilter(object,event);
}
bool WindowsBackdrop::nativeEventFilter(const QByteArray &, void *message, qintptr *result) {
#ifdef Q_OS_WIN
    if (!m_window || !m_handle) return false;
    const auto *msg = static_cast<MSG *>(message);
    if (msg->hwnd != reinterpret_cast<HWND>(m_handle)) return false;
    switch (msg->message) {
    case WM_SIZE: case WM_DPICHANGED: case WM_WINDOWPOSCHANGED:
        scheduleCornerUpdate(); break;
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
