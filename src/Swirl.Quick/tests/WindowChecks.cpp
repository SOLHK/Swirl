#include "WindowChecks.h"
#include "../app/WindowsBackdrop.h"
#include <QQuickWindow>
#include <QGuiApplication>
#include <QScreen>
#include <QCursor>
#include <QTest>
#include <QQmlExpression>
#include <QQmlContext>
#include <QQmlComponent>
#include <QQmlEngine>
#include <QDir>
#include <QDebug>
#include <QImage>
#include <QElapsedTimer>
#include <QQuickItem>
#include <functional>
#ifdef Q_OS_WIN
#include <windows.h>
#include <dwmapi.h>
#include <psapi.h>
#endif

int runWindowChecks(QQuickWindow *window, WindowsBackdrop *backdrop, const QString &directory)
{
    qInfo()<<"WINDOW_RENDER_DPR"<<window->devicePixelRatio()<<"graphics_api"<<window->rendererInterface()->graphicsApi();
    int failures=0,checks=0;
    const auto check=[&](bool ok,const char *name){++checks;if(!ok)++failures;qInfo()<< (ok?"PASS":"FAIL") <<name;};
    const auto state=[&](const QString &code){QQmlExpression expression(qmlContext(window),window,code);return expression.evaluate();};
    std::function<QQuickItem *(QQuickItem *,const QString &)> find;
    find=[&](QQuickItem *item,const QString &name)->QQuickItem *{if(item->objectName()==name)return item;for(auto *child:item->childItems())if(auto *match=find(child,name))return match;return nullptr;};
    const auto click=[&](const QString &name){auto *item=find(window->contentItem(),name);check(item,"window button exists");if(item)QTest::mouseClick(window,Qt::LeftButton,Qt::NoModifier,item->mapToScene(QPointF(item->width()/2,item->height()/2)).toPoint());QTest::qWait(350);};
    QDir().mkpath(directory);
    QQuickWindow background;
    background.setTitle(QStringLiteral("Swirl composition test background"));
    background.setFlags(Qt::Window|Qt::FramelessWindowHint);
    const QRect available=window->screen()->availableGeometry();
    background.setGeometry(available);
    background.setColor(QColor("#D72D31"));background.show();
#ifdef Q_OS_WIN
    SetWindowPos(reinterpret_cast<HWND>(background.winId()),HWND_TOPMOST,0,0,0,0,SWP_NOMOVE|SWP_NOSIZE|SWP_NOACTIVATE);
#endif
    const QSize captureSize(qMax(window->minimumWidth(),qMin(1280,available.width()-120)),qMax(window->minimumHeight(),qMin(800,available.height()-100)));
    window->resize(captureSize);
    window->setPosition(available.topLeft()+QPoint(60,40));
    window->showNormal();window->raise();window->requestActivate();QTest::qWait(900);
#ifdef Q_OS_WIN
    // Keep Qt's flag model in sync: a raw HWND_TOPMOST alone is cleared when
    // Qt reapplies its flags after the manual DPI/size checks below.
    window->setFlag(Qt::WindowStaysOnTopHint,true);
    // This explicit validation fixture must not sample an unrelated window
    // that happens to cover Swirl. Temporarily keep the test HWND on top and
    // activate it, without changing any other application's window settings.
    const HWND testHwnd=reinterpret_cast<HWND>(window->winId());
    SetWindowPos(testHwnd,HWND_TOPMOST,0,0,0,0,SWP_NOMOVE|SWP_NOSIZE);
    if(GetForegroundWindow()!=testHwnd) {
        const DWORD foregroundThread=GetWindowThreadProcessId(GetForegroundWindow(),nullptr);
        const DWORD currentThread=GetCurrentThreadId();
        const bool attached=foregroundThread!=currentThread && AttachThreadInput(currentThread,foregroundThread,TRUE);
        SetForegroundWindow(testHwnd);
        if(attached)AttachThreadInput(currentThread,foregroundThread,FALSE);
    }
    QTest::qWait(400);
    if(!backdrop->isCaptureForeground()){qCritical()<<"Native validation blocked: target is covered or the Windows secure desktop is active";return 3;}
    const auto radius=state("Theme.windowRadius").toReal()*window->devicePixelRatio();
    const auto region=CreateRectRgn(0,0,0,0);
    const bool binaryContour=backdrop->exactCorners()&&window->rendererInterface()->graphicsApi()==QSGRendererInterface::Software;
    check(binaryContour ? GetWindowRgn(testHwnd,region)!=ERROR : GetWindowRgn(testHwnd,region)==ERROR,
          "GPU alpha contour has no integer region; software retains compatibility clip");
    DeleteObject(region);
    const auto cornerCoverage=[&](){
        const auto rendered=window->grabWindow();int partial=0,total=0;
        for(int y=0;y<int(radius);++y)for(int x=0;x<int(radius);++x) {
            const auto alpha=rendered.pixelColor(rendered.width()-1-x,y).alpha();
            total+=alpha;if(alpha>0 && alpha<255)++partial;
        }
        return qMakePair(total,partial);
    };
    const auto normalCorner=cornerCoverage();
    check(backdrop->nativeCorners() || normalCorner.second>=5,"system manages the final contour or fallback has antialiased corners");
    state("Theme.setScalePercent(125)");QTest::qWait(150);
    check(qAbs(state("Theme.windowRadius").toReal()-10.0*96.0/72.0)<0.001,
          "10pt window contour stays independent of manual content zoom");
    state("Theme.resetScale()");QTest::qWait(150);
    // Increasing the minimum geometry for manual UI zoom can enlarge the
    // window. Restore the capture bounds so the bottom corners remain on the
    // actual desktop at 200% DPR, rather than sampling offscreen black pixels.
    window->resize(captureSize);QTest::qWait(150);
#endif
    const auto grab=[&](const QString &name){
#ifdef Q_OS_WIN
        if(!backdrop->isCaptureForeground()){qCritical()<<"Native screenshot blocked by foreground or secure desktop";return QImage();}
        check(GetForegroundWindow()==testHwnd,"native screenshot samples the foreground test window");
        qInfo()<<"Capture state"<<name<<"active="<<window->isActive()<<"foreground="<<(GetForegroundWindow()==reinterpret_cast<HWND>(window->winId()))<<"extended style="<<QString::number(GetWindowLongPtrW(reinterpret_cast<HWND>(window->winId()),GWL_EXSTYLE),16)<<"QML opacity="<<state("Theme.sidebarOpacity");
#endif
        // Read the actual desktop compositor, never QQuickWindow::grabWindow,
        // which contains only the application's alpha surface.
        QImage img;
#ifdef Q_OS_WIN
        // QScreen::grabWindow(0, logical x/y) can map to a different desktop
        // rectangle with per-process DPR overrides. Use this HWND's physical
        // rectangle so fractional-DPI checks sample the actual compositor.
        RECT r{};GetWindowRect(testHwnd,&r);
        const int w=r.right-r.left,h=r.bottom-r.top;
        const auto desktop=GetDC(nullptr),dc=CreateCompatibleDC(desktop);
        BITMAPINFO info{};info.bmiHeader.biSize=sizeof(BITMAPINFOHEADER);
        info.bmiHeader.biWidth=w;info.bmiHeader.biHeight=-h;
        info.bmiHeader.biPlanes=1;info.bmiHeader.biBitCount=32;info.bmiHeader.biCompression=BI_RGB;
        void *bits=nullptr;auto bitmap=CreateDIBSection(dc,&info,DIB_RGB_COLORS,&bits,nullptr,0);
        if(bitmap&&bits) {
            const auto previous=SelectObject(dc,bitmap);
            if(BitBlt(dc,0,0,w,h,desktop,r.left,r.top,SRCCOPY|CAPTUREBLT))img=QImage(static_cast<uchar *>(bits),w,h,QImage::Format_RGB32).copy();
            SelectObject(dc,previous);DeleteObject(bitmap);
        }
        DeleteDC(dc);ReleaseDC(nullptr,desktop);
#else
        img=window->screen()->grabWindow(0,window->x(),window->y(),window->width(),window->height()).toImage();
#endif
        check(!img.isNull() && img.save(directory+"/"+name+".png"),"native compositor screenshot saved");
        return img;
    };
    const auto sample=[](const QImage &img,qreal x,qreal y){if(img.isNull())return QColor();return img.pixelColor(qBound(0,int(x*img.width()),img.width()-1),qBound(0,int(y*img.height()),img.height()-1));};
    const auto distance=[](QColor a,QColor b){return qAbs(a.red()-b.red())+qAbs(a.green()-b.green())+qAbs(a.blue()-b.blue());};
    auto *outline=find(window->contentItem(),"windowOutline");
    const bool qmlRim=backdrop->exactCorners() || !backdrop->nativeCorners();
    check(outline && outline->isVisible()==qmlRim,"window uses one rim matching its exact or system-preset contour");
    const auto outlined=grab("outline-enabled");
    if(outline)outline->setVisible(false);QTest::qWait(200);
    const auto borderless=grab("outline-disabled-comparison");
    check(qmlRim ? distance(sample(outlined,0.5,0),sample(borderless,0.5,0))>12 : distance(sample(outlined,0.5,0),sample(borderless,0.5,0))<=3,"only the selected rim paints the window border");
    if(outline)outline->setVisible(qmlRim);QTest::qWait(200);
#ifdef Q_OS_WIN
    const auto nativeIcon=reinterpret_cast<HICON>(SendMessageW(testHwnd,WM_GETICON,ICON_BIG,0));
    check(nativeIcon!=nullptr,"Windows taskbar receives an explicit large icon");
    if(nativeIcon){
        BITMAPINFO info{};info.bmiHeader.biSize=sizeof(BITMAPINFOHEADER);info.bmiHeader.biWidth=32;info.bmiHeader.biHeight=-32;info.bmiHeader.biPlanes=1;info.bmiHeader.biBitCount=32;info.bmiHeader.biCompression=BI_RGB;
        void *bits=nullptr;const auto dc=CreateCompatibleDC(nullptr);const auto bitmap=CreateDIBSection(dc,&info,DIB_RGB_COLORS,&bits,nullptr,0);
        const auto previous=SelectObject(dc,bitmap);RECT box{0,0,32,32};FillRect(dc,&box,reinterpret_cast<HBRUSH>(GetStockObject(WHITE_BRUSH)));
        DrawIconEx(dc,0,0,nativeIcon,32,32,0,nullptr,DI_NORMAL);
        QImage image(static_cast<uchar *>(bits),32,32,QImage::Format_RGB32);int dark=0,blue=0;
        for(int y=0;y<32;++y)for(int x=0;x<32;++x){const auto c=image.pixelColor(x,y);if(c.red()<80&&c.green()<80&&c.blue()<80)++dark;if(c.blue()>c.red()+35)++blue;}
        check(dark>40 && blue==0,"native taskbar icon is the monochrome knot, not the blue legacy logo");
        image.save(directory+"/taskbar-native-icon.png");SelectObject(dc,previous);DeleteObject(bitmap);DeleteDC(dc);
    }
#endif
    state("Theme.mode='Light'");QTest::qWait(300);
    QCursor::setPos(window->screen()->availableGeometry().topLeft()+QPoint(10,10));QTest::qWait(300);
    auto red=grab("backdrop-red");
    const auto lightShell=sample(red,0.995,0.5);
    check(lightShell.red()>=230&&lightShell.green()>=230&&lightShell.blue()>=230,"light shell reads neutral white in the native compositor");
    const QColor behind("#D72D31");
    const auto cornerShowsBackground=[&](QColor pixel){
        // DWM's frame shadow also surrounds Qt's own alpha outline. Check
        // the background hue, then separately require zero corner alpha.
        return pixel.red()>100 && pixel.red()>3*pixel.green() && qAbs(pixel.blue()-pixel.green())<8;
    };
    check(cornerShowsBackground(red.pixelColor(0,0)) && cornerShowsBackground(red.pixelColor(red.width()-1,0)) && cornerShowsBackground(red.pixelColor(0,red.height()-1)) && cornerShowsBackground(red.pixelColor(red.width()-1,red.height()-1)),
          "all four composed corners show desktop or its native shadow without material fill");
    const auto cornerAlpha=window->grabWindow();
    if(backdrop->exactCorners()&&window->rendererInterface()->graphicsApi()!=QSGRendererInterface::Software){
        int fractional=0;const int extent=qCeil(backdrop->cornerRadius()*window->devicePixelRatio());
        for(int y=0;y<extent;++y)for(int x=0;x<extent;++x){const int a=cornerAlpha.pixelColor(x,y).alpha();if(a>0&&a<255)++fractional;}
        check(fractional>3,"exact GPU corners preserve fractional alpha coverage");
    }
    check(cornerAlpha.save(directory+"/window-alpha.png"),"native-resolution alpha surface saved for corner inspection");
    const int cornerExtent=qMin(qMin(cornerAlpha.width(),cornerAlpha.height()),qCeil(state("Theme.windowRadius").toReal()*window->devicePixelRatio())+8);
    const QList<QPoint> origins{{0,0},{cornerAlpha.width()-cornerExtent,0},{0,cornerAlpha.height()-cornerExtent},{cornerAlpha.width()-cornerExtent,cornerAlpha.height()-cornerExtent}};
    for(int i=0;i<origins.size();++i)check(cornerAlpha.copy(QRect(origins[i],QSize(cornerExtent,cornerExtent))).save(directory+QString("/corner-%1-alpha.png").arg(i)),"individual corner alpha sample saved");
    check(state("!scaledCanvas.layer.enabled").toBool(),"native text is outside any whole-window texture mask");
    check(backdrop->nativeCorners() || (cornerAlpha.pixelColor(0,0).alpha()==0&&cornerAlpha.pixelColor(cornerAlpha.width()-1,0).alpha()==0&&cornerAlpha.pixelColor(0,cornerAlpha.height()-1).alpha()==0&&cornerAlpha.pixelColor(cornerAlpha.width()-1,cornerAlpha.height()-1).alpha()==0),"DWM clips final HWND corners; only fallback needs transparent QML tips");
    background.setColor(QColor("#2464D8"));QTest::qWait(800);
    auto blue=grab("backdrop-blue");
    const int sidebarChange=distance(sample(red,0.01,0.83),sample(blue,0.01,0.83));
    const int contentChange=distance(sample(red,0.995,0.5),sample(blue,0.995,0.5));
    qInfo()<<"Native pixel delta: sidebar="<<sidebarChange<<"content="<<contentChange<<"DPR="<<window->devicePixelRatio()<<backdrop->status();
    const bool exactOpaque=backdrop->exactCorners()&&!backdrop->translucent();
    check(exactOpaque ? !backdrop->active()&&backdrop->status().contains("exact 10pt")
                      : (backdrop->active()&&backdrop->status().contains("Desktop Acrylic"))||(backdrop->translucent()&&backdrop->status().contains("Alpha translucency")),
          "composition reports native Acrylic, exact alpha, or a policy-required opaque fallback");
    check(exactOpaque ? sidebarChange<=3 : sidebarChange>=4&&sidebarChange<(backdrop->blurActive()?160:40),"sidebar follows the effective composition capability");
    check(exactOpaque ? contentChange<=3 : contentChange>=4&&contentChange<(backdrop->blurActive()?160:40),"workspace follows the effective composition capability");
    if(backdrop->blurActive()){
        check(qAbs(sidebarChange-contentChange)<=12,"sidebar and workspace share one neutral shell material while responding to live desktop color");
        const auto scale=window->devicePixelRatio();const auto divider=state("window.actualSidebarWidth").toReal();
        const auto lhs=red.pixelColor(qRound((divider-12)*scale),qRound(20*scale));
        const auto rhs=red.pixelColor(qRound((divider+12)*scale),qRound(20*scale));
        check(distance(lhs,rhs)<=20,"sidebar floats above the workspace without a hard material seam");
    }
    // The shared light shell stays white while still allowing restrained live blur.
    const auto materialAlpha=window->grabWindow().pixelColor(int(window->width()*0.995*window->devicePixelRatio()),int(window->height()*0.5*window->devicePixelRatio())).alpha();
    const int expectedBlurAlpha=state("Theme.dark").toBool()?204:245;
    check(exactOpaque ? materialAlpha==255 : backdrop->blurActive()?qAbs(materialAlpha-expectedBlurAlpha)<=2:backdrop->translucent()?materialAlpha>=240&&materialAlpha<=244:materialAlpha>=227&&materialAlpha<=231,"actual alpha matches the single material tint");
    // Move Swirl relative to a split-color native QML window to verify position-
    // dependent composition. The scene is a test window, not a wallpaper image.
    QQuickItem split;
    split.setParentItem(background.contentItem());split.setWidth(background.width()/2);split.setHeight(background.height());
    QQmlEngine engine;
    QQmlComponent component(&engine);
    component.setData("import QtQuick; Rectangle { color: '#D72D31' }",QUrl());
    auto *rectangle=qobject_cast<QQuickItem *>(component.create());
    if(rectangle){rectangle->setParentItem(background.contentItem());rectangle->setSize(QSizeF(background.width()/2,background.height()));}
    window->setPosition(available.topLeft()+QPoint(20,30));QTest::qWait(600);
    auto left=grab("backdrop-moved-left");
    window->setPosition(available.topLeft()+QPoint(available.width()/2,30));QTest::qWait(600);
    auto right=grab("backdrop-moved-right");
    const auto moveDelta=distance(sample(left,0.01,0.83),sample(right,0.01,0.83));
    check(exactOpaque ? moveDelta<=3 : moveDelta>1,"moving follows opaque fallback or actual screen-position Acrylic composition");
    const qreal sidebar=state("window.actualSidebarWidth * window.contentScale").toReal();
    window->setPosition(available.topLeft()+QPoint(int(available.width()/2-sidebar/2),30));QTest::qWait(600);
    auto edge=grab("backdrop-blurred-edge");
    const qreal scale=qreal(edge.width())/window->width();
    const int cx=int(sidebar/2*scale),row=int(50*scale);
    const auto a=edge.pixelColor(cx-60,row),b=edge.pixelColor(cx+60,row);
    const int low=qMin(a.red(),b.red()),high=qMax(a.red(),b.red());
    int intermediate=0;
    for(int x=cx-50;x<=cx+50;++x){const int value=edge.pixelColor(x,row).red();if(value>low+2&&value<high-2)++intermediate;}
    qInfo()<<"Alpha edge profile: left="<<a<<"right="<<b<<"intermediate pixels="<<intermediate;
    auto *sidebarPane=find(window->contentItem(),QStringLiteral("sidebarFloatingBackground"));
    check(sidebarPane&&sidebarPane->x()>0&&sidebarPane->y()>0&&sidebarPane->width()<sidebar&&sidebarPane->height()<window->height()&&sidebarPane->property("radius").toDouble()>0,
          "floating sidebar background is inset and rounded");
    delete rectangle;
    window->setPosition(available.topLeft()+QPoint(60,40));
    state("Theme.transparency=false");QTest::qWait(500);
    auto opaqueBlue=grab("backdrop-disabled-blue");
    background.setColor(QColor("#D72D31"));QTest::qWait(500);
    auto opaqueRed=grab("backdrop-disabled-red");
    check(!backdrop->active(),"application transparency setting disables native backdrop");
    check(distance(sample(opaqueBlue,0.01,0.83),sample(opaqueRed,0.01,0.83))<=3,"disabled transparency gives opaque sidebar fallback");
    check(distance(sample(opaqueBlue,0.995,0.5),sample(opaqueRed,0.995,0.5))<=3,"disabled transparency gives opaque page fallback");
    state("Theme.transparency=true;Theme.mode='Dark'");QTest::qWait(500);grab("overview-native-dark");
    check(exactOpaque ? !backdrop->active()&&backdrop->status().contains("exact 10pt")
                      : (backdrop->active()&&backdrop->status().contains("Desktop Acrylic"))||(backdrop->translucent()&&backdrop->status().contains("Alpha translucency")),
          "dark theme retains its effective contour and composition capability");
    state("Theme.mode='Light'");
    auto *title=find(window->contentItem(),"titleDragArea");
    check(title,"title drag region exists");
    if (title) {
        QTest::mouseDClick(window,Qt::LeftButton,Qt::NoModifier,title->mapToScene(QPointF(100,20)).toPoint());QTest::qWait(350);
        check(window->visibility()==QWindow::Maximized,"double click title maximizes actual window");
        QTest::mouseDClick(window,Qt::LeftButton,Qt::NoModifier,title->mapToScene(QPointF(100,20)).toPoint());QTest::qWait(350);
        check(window->visibility()==QWindow::Windowed,"double click title restores actual window");
    }
    click("windowMaximizeButton");QTest::qWait(500);grab("overview-maximized");
    qInfo()<<"Maximized geometry"<<window->geometry()<<"work area"<<available;
    check(window->visibility()==QWindow::FullScreen&&window->geometry()==window->screen()->geometry(),"green traffic light enters true full screen without corner gaps");
    click("windowMaximizeButton");QTest::qWait(300);
    check(window->visibility()==QWindow::Windowed,"restore returns to windowed state");
    click("windowMinimizeButton");QTest::qWait(300);
    check(window->visibility()==QWindow::Minimized,"minimization works");
    window->showNormal();window->requestActivate();QTest::qWait(300);
    check(window->visibility()==QWindow::Windowed,"restore from minimized works");
#ifdef Q_OS_WIN
    const HWND hwnd=reinterpret_cast<HWND>(window->winId());
    const auto style=GetWindowLongPtrW(hwnd,GWL_STYLE);
    check(!(style&WS_CAPTION),"only Swirl traffic lights remain after window state changes");
    check(!(GetWindowLongPtrW(hwnd,GWL_EXSTYLE)&WS_EX_LAYERED),"restore retains DWM-compatible alpha composition");
    check((style&WS_THICKFRAME)&&(style&WS_SYSMENU)&&(style&WS_MAXIMIZEBOX),"native resize and system menu styles preserved");
    RECT rect;GetWindowRect(hwnd,&rect);
    const auto hit=SendMessageW(hwnd,WM_NCHITTEST,0,MAKELPARAM(rect.left+2,rect.top+2));
    check(hit==HTTOPLEFT,"native corner hit test enables edge resizing");
    check(GetSystemMenu(hwnd,FALSE)!=nullptr,"native Alt+Space menu exists");
    const auto cpuTime=[](){FILETIME create{},exit{},kernel{},user{};GetProcessTimes(GetCurrentProcess(),&create,&exit,&kernel,&user);ULARGE_INTEGER k{},u{};k.LowPart=kernel.dwLowDateTime;k.HighPart=kernel.dwHighDateTime;u.LowPart=user.dwLowDateTime;u.HighPart=user.dwHighDateTime;return k.QuadPart+u.QuadPart;};
    PROCESS_MEMORY_COUNTERS_EX before{},after{};
    GetProcessMemoryInfo(GetCurrentProcess(),reinterpret_cast<PROCESS_MEMORY_COUNTERS *>(&before),sizeof(before));
    const auto cpuStart=cpuTime();QElapsedTimer elapsed;elapsed.start();
    for(int i=0;i<60;++i){window->setPosition(available.topLeft()+QPoint(60+(i%20)*4,40));QTest::qWait(16);}
    GetProcessMemoryInfo(GetCurrentProcess(),reinterpret_cast<PROCESS_MEMORY_COUNTERS *>(&after),sizeof(after));
    qInfo()<<"MOVE_SAMPLE frames=60 wall_ms="<<elapsed.elapsed()<<"CPU_ms="<<(cpuTime()-cpuStart)/10000.0<<"private_bytes_delta="<<qint64(after.PrivateUsage)-qint64(before.PrivateUsage);
#endif
    background.hide();
#ifdef Q_OS_WIN
    window->setFlag(Qt::WindowStaysOnTopHint,false);
    SetWindowPos(testHwnd,HWND_NOTOPMOST,0,0,0,0,SWP_NOMOVE|SWP_NOSIZE|SWP_NOACTIVATE);
#endif
    const bool quitOnClose=QGuiApplication::quitOnLastWindowClosed();
    QGuiApplication::setQuitOnLastWindowClosed(false);
    click("windowCloseButton");
    check(!window->isVisible(),"red window button closes the actual window");
    QGuiApplication::setQuitOnLastWindowClosed(quitOnClose);
    qInfo()<<"WINDOW_CHECKS"<<checks<<"checks"<<failures<<"failures";
    return failures?1:0;
}
