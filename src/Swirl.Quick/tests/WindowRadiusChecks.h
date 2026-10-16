#pragma once
#include "../app/WindowsBackdrop.h"
#include <QQuickWindow>
#include <QScreen>
#include <QQuickItem>
#include <QQmlContext>
#include <QQmlExpression>
#include <QTest>
#include <QDir>
#include <QFile>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonArray>
#include <QImage>
#include <QDebug>
#include <cmath>
#ifdef Q_OS_WIN
#include <windows.h>
#include <dwmapi.h>
#endif

// Narrow, isolated render check. It never starts a proxy or changes display DPI.
inline int runWindowRadiusChecks(QQuickWindow *window, WindowsBackdrop *backdrop, const QString &directory) {
#ifndef Q_OS_WIN
    Q_UNUSED(window) Q_UNUSED(backdrop) Q_UNUSED(directory)
    return 3;
#else
    QDir().mkpath(directory);
    QJsonArray checks;
    int failures = 0;
    const auto check = [&](bool pass, const QString &name) {
        checks.append(QJsonObject{{"name", name}, {"pass", pass}});
        if (!pass) ++failures;
        qInfo() << (pass ? "PASS" : "FAIL") << name;
    };
    const auto eval = [&](const QString &code) {
        QQmlExpression expression(qmlContext(window), window, code);
        const auto result = expression.evaluate();
        check(!expression.hasError(), "QML: " + code.left(80));
        return result;
    };
    eval("Theme.mode='Light';Theme.reduceMotion=true;Theme.resetScale()");
    check(qAbs(eval("Theme.windowRadius").toReal() - 10.0 * 96.0 / 72.0) < 0.0001,
          "window token is 10pt = 13.333333 Qt DIP");
    check(eval("Theme.cardRadius===Theme.independentCardRadius && Theme.cardRadius===Theme.containerRadius").toBool(),
          "same-level card tokens share one radius");
    const HWND previousForeground = GetForegroundWindow();
    const auto available = window->screen()->availableGeometry();
    const QColor backgroundColor("#5269A3");
    QQuickWindow background;
    background.setFlags(Qt::Window | Qt::FramelessWindowHint | Qt::WindowStaysOnTopHint);
    background.setGeometry(available);
    background.setColor(backgroundColor);
    background.show();
    window->setFlag(Qt::WindowStaysOnTopHint, true);
    window->resize(qMax(window->minimumWidth(), qMin(914, available.width() - 64)),
                   qMax(window->minimumHeight(), qMin(720, available.height() - 64)));
    window->setPosition(available.topLeft() + QPoint(32, 24));
    window->showNormal();
    QTest::qWait(200);
    backdrop->prepareNativeCapture();
    QTest::qWait(200);
    const HWND hwnd = reinterpret_cast<HWND>(window->winId());
    check(backdrop->isCaptureForeground(), "test window is foreground on the unlocked input desktop");
    const qreal dpr = window->devicePixelRatio();
    const auto verifyRegion = [&](const QString &phase) {
        const HRGN region = CreateRectRgn(0, 0, 0, 0);
        const int kind = GetWindowRgn(hwnd, region);
        RECT bounds{};
        GetWindowRect(hwnd, &bounds);
        const int width = bounds.right - bounds.left, height = bounds.bottom - bounds.top;
        const qreal radius = 10.0 * 96.0 / 72.0 * window->devicePixelRatio();
        const bool alpha=window->rendererInterface()->graphicsApi()!=QSGRendererInterface::Software;
        bool symmetric = alpha?kind==ERROR:kind==COMPLEXREGION, geometric = symmetric;
        for (int y = 0; !alpha && y <= qCeil(radius); ++y) {
            for (int x = 0; x <= qCeil(radius); ++x) {
                const bool present = PtInRegion(region, x, y);
                symmetric = symmetric && present == bool(PtInRegion(region, width - 1 - x, y))
                    && present == bool(PtInRegion(region, x, height - 1 - y))
                    && present == bool(PtInRegion(region, width - 1 - x, height - 1 - y));
                const qreal dx = qMax<qreal>(0, radius - x - 0.5), dy = qMax<qreal>(0, radius - y - 0.5);
                geometric = geometric && present == (dx * dx + dy * dy <= radius * radius);
            }
        }
        check(backdrop->exactCorners() && symmetric, phase + ": contour ownership matches renderer");
        check(geometric, phase + ": accelerated alpha has no binary clip; software keeps compatibility region");
        check(qAbs(backdrop->cornerRadius() - 10.0 * 96.0 / 72.0) < 0.0001, phase + ": active logical radius is 10pt");
        DeleteObject(region);
    };
    verifyRegion("normal");
    const QSize initialSize = window->size();
    eval("Theme.setScalePercent(125)");
    QTest::qWait(80);
    verifyRegion("content zoom 125%");
    eval("Theme.resetScale()");
    window->resize(initialSize);
    QTest::qWait(80);
    const QSize normalSize = window->size();
    for (int i = 0; i < 8; ++i) {
        window->resize(normalSize + QSize((i % 3) * 7, (i % 2) * 5));
        QTest::qWait(20);
    }
    verifyRegion("live resize");
    window->resize(normalSize);
    QTest::qWait(80);
    const auto shadowBuilds = backdrop->compatibilityShadowBuildCount();
    const auto normalPosition = window->position();
    for (int i = 0; i < 8; ++i) {
        window->setPosition(normalPosition + QPoint((i % 3) * 4, (i % 2) * 3));
        QTest::qWait(20);
    }
    window->setPosition(normalPosition); QTest::qWait(40);
    check(backdrop->compatibilityShadowBuildCount() == shadowBuilds,
          "moving repositions the cached shadow without rebuilding pixels");
    const auto style = GetWindowLongPtrW(hwnd, GWL_STYLE);
    check((style & WS_THICKFRAME) && (style & WS_SYSMENU) && !(style & WS_CAPTION),
          "native sizing and system menu remain, with only Swirl traffic lights");
    check(!(GetWindowLongPtrW(hwnd, GWL_EXSTYLE) & WS_EX_LAYERED), "DWM alpha composition is retained");
    // Capture only the test window plus shadow over the flat owned fixture.
    RECT rect{};
    GetWindowRect(hwnd, &rect);
    constexpr int padding = 24;
    const int width = rect.right - rect.left, height = rect.bottom - rect.top;
    const HDC desktop = GetDC(nullptr), memory = CreateCompatibleDC(desktop);
    BITMAPINFO info{};
    info.bmiHeader.biSize = sizeof(BITMAPINFOHEADER);
    info.bmiHeader.biWidth = width + padding * 2;
    info.bmiHeader.biHeight = -(height + padding * 2);
    info.bmiHeader.biPlanes = 1; info.bmiHeader.biBitCount = 32; info.bmiHeader.biCompression = BI_RGB;
    void *bits = nullptr;
    const HBITMAP bitmap = CreateDIBSection(memory, &info, DIB_RGB_COLORS, &bits, nullptr, 0);
    QImage image;
    if (bitmap && bits && backdrop->isCaptureForeground()) {
        const auto previous = SelectObject(memory, bitmap);
        if (BitBlt(memory, 0, 0, width + padding * 2, height + padding * 2, desktop,
                   rect.left - padding, rect.top - padding, SRCCOPY | CAPTUREBLT))
            image = QImage(static_cast<uchar *>(bits), width + padding * 2, height + padding * 2, QImage::Format_RGB32).copy();
        SelectObject(memory, previous);
    }
    if (bitmap) DeleteObject(bitmap);
    DeleteDC(memory); ReleaseDC(nullptr, desktop);
    check(!image.isNull() && image.save(directory + "/window-and-shadow.png"), "actual compositor contour and shadow saved");
    int shadowPixels = 0;
    const auto alphaImage=window->grabWindow();int fractionalAlpha=0;
    if(!alphaImage.isNull())for(int y=0;y<qCeil(14*dpr);++y)for(int x=0;x<qCeil(14*dpr);++x){const auto a=alphaImage.pixelColor(x,y).alpha();if(a>0&&a<255)++fractionalAlpha;}
    check(fractionalAlpha>3,"GPU contour contains fractional coverage instead of an integer staircase");
    int outsideCornerPixels = 0, outsideCornerBrightPixels = 0;
    if (!image.isNull()) {
        image.copy(padding, padding, width, height).save(directory + "/window.png");
        const int extent = qCeil(10.0 * 96.0 / 72.0 * dpr) + 3;
        for (int i = 0; i < 4; ++i) image.copy(padding + (i % 2 ? width - extent : 0),
            padding + (i / 2 ? height - extent : 0), extent, extent).save(directory + QString("/corner-%1.png").arg(i));
        const qreal cornerRadius = 10.0 * 96.0 / 72.0 * dpr;
        for (int y = 0; y < qCeil(cornerRadius); ++y) for (int x = 0; x < qCeil(cornerRadius); ++x) {
            const qreal dx = cornerRadius - x - 0.5, dy = cornerRadius - y - 0.5;
            if (std::hypot(dx,dy) <= cornerRadius + 0.75) continue;
            for (int i = 0; i < 4; ++i) {
                const auto pixel = image.pixelColor(padding + (i % 2 ? width - 1 - x : x),
                    padding + (i / 2 ? height - 1 - y : y));
                ++outsideCornerPixels;
                if (pixel.red() > backgroundColor.red() + 3 || pixel.green() > backgroundColor.green() + 3
                    || pixel.blue() > backgroundColor.blue() + 3) ++outsideCornerBrightPixels;
            }
        }
        for (int y = padding + height / 4; y < padding + height * 3 / 4; ++y)
            for (int x = padding - 8; x < padding; ++x) {
                const auto pixel = image.pixelColor(x, y);
                if (pixel.red() < backgroundColor.red() - 2 && pixel.green() < backgroundColor.green() - 2
                    && pixel.blue() < backgroundColor.blue() - 2) ++shadowPixels;
            }
    }
    check(outsideCornerPixels > 0 && outsideCornerBrightPixels == 0,
          "actual pixels outside all four 10pt corners show only background or dark shadow, never a pale material square");
    check(shadowPixels > 10 && backdrop->compatibilityShadow(), "a visible compatibility shadow follows the exact contour");
    const HWND shadow = reinterpret_cast<HWND>(backdrop->compatibilityShadowHandle());
    const auto shadowStyle = shadow ? GetWindowLongPtrW(shadow, GWL_EXSTYLE) : 0;
    check(shadow && (shadowStyle & WS_EX_TRANSPARENT) && (shadowStyle & WS_EX_NOACTIVATE)
          && (shadowStyle & WS_EX_TOOLWINDOW), "shadow helper is input transparent, does not activate, and has no taskbar entry");
    check(shadow && SendMessageW(shadow, WM_NCHITTEST, 0, 0) == HTTRANSPARENT
          && SendMessageW(shadow, WM_MOUSEACTIVATE, 0, 0) == MA_NOACTIVATE,
          "shadow hit testing and mouse activation pass through");
    const POINT centre{(rect.left + rect.right) / 2, (rect.top + rect.bottom) / 2};
    check(WindowFromPoint(centre) == hwnd && GetForegroundWindow() == hwnd,
          "shadow never covers shell input or steals activation");
    window->showMaximized(); QTest::qWait(180);
    const HRGN maximizedRegion = CreateRectRgn(0, 0, 0, 0);
    check(GetWindowRgn(hwnd, maximizedRegion) == ERROR && backdrop->cornerRadius() == 0,
          "maximized HWND removes region and uses square corners");
    DeleteObject(maximizedRegion);
    window->showNormal(); QTest::qWait(180);
    verifyRegion("restored");
    window->showFullScreen(); QTest::qWait(180);
    const HRGN fullscreenRegion = CreateRectRgn(0, 0, 0, 0);
    check(GetWindowRgn(hwnd, fullscreenRegion) == ERROR && backdrop->cornerRadius() == 0,
          "full-screen HWND also uses square corners");
    DeleteObject(fullscreenRegion);
    window->showNormal(); QTest::qWait(150);
    verifyRegion("restored from full screen");
    backdrop->finishNativeCapture(); background.hide(); window->hide();
    if (IsWindow(previousForeground)) SetForegroundWindow(previousForeground);
    QFile report(directory + "/window-radius.json");
    if (report.open(QIODevice::WriteOnly)) report.write(QJsonDocument(QJsonObject{
        {"dpr", dpr}, {"logicalRadius", 10.0 * 96.0 / 72.0}, {"physicalRadius", 10.0 * 96.0 / 72.0 * dpr},
        {"shadowPixels", shadowPixels}, {"outsideCornerPixels", outsideCornerPixels}, {"outsideCornerBrightPixels", outsideCornerBrightPixels},
        {"shadowKind", "cached input-transparent compatibility HWND"}, {"checks", checks}, {"failures", failures},
        {"scaleNote", "Qt scale-factor validation; no Windows global display setting is changed"}}).toJson());
    return failures ? 1 : 0;
#endif
}
