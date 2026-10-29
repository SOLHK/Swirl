#include "WindowChecks.h"
#include "../app/WindowsBackdrop.h"
#include "../app/BrandRaster.h"
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
    // Keep Qt's flag model in sync when native DPI and size changes reapply it.
    window->setFlag(Qt::WindowStaysOnTopHint,true);
    // This explicit validation fixture must not sample an unrelated window
    // that happens to cover Swirl. Temporarily keep the test HWND on top and
    // activate it, without changing any other application's window settings.
    const HWND testHwnd=reinterpret_cast<HWND>(window->winId());
    // A hidden process STARTUPINFO can suppress Qt's first native ShowWindow
    // even though QWindow already reports visible. Match the quality fixture.
    ShowWindow(testHwnd,SW_SHOWNORMAL);
    check(IsWindowVisible(testHwnd)&&(GetWindowLongPtrW(testHwnd,GWL_STYLE)&WS_VISIBLE),
          "hidden test-process launch explicitly presents the actual native window");
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
    check(qAbs(state("Theme.windowRadius").toReal()-14.0)<0.001
          && qAbs(state("Theme.sidebarRadius").toReal()-state("Theme.dp(14)").toReal())<0.001,
          "approved 14dp shell stays fixed while 14dp sidebar follows manual content zoom");
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
        DWORD cloaked=0;
        check(IsWindowVisible(testHwnd)&&SUCCEEDED(DwmGetWindowAttribute(testHwnd,DWMWA_CLOAKED,&cloaked,sizeof(cloaked)))&&!cloaked,
            "native screenshot samples a visible uncloaked application window");
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
        ICONINFO nativeInfo{};BITMAP nativeBitmap{};
        const bool iconInfoKnown=GetIconInfo(nativeIcon,&nativeInfo);
        const bool nativeSizeKnown=iconInfoKnown && nativeInfo.hbmColor && GetObjectW(nativeInfo.hbmColor,sizeof(nativeBitmap),&nativeBitmap);
        if(nativeInfo.hbmColor)DeleteObject(nativeInfo.hbmColor);
        if(nativeInfo.hbmMask)DeleteObject(nativeInfo.hbmMask);
        check(nativeSizeKnown && nativeBitmap.bmWidth>0 && nativeBitmap.bmWidth==nativeBitmap.bmHeight,"native taskbar icon reports its actual square raster frame");
        const int size=nativeSizeKnown?nativeBitmap.bmWidth:0;
        if(size>0){
        BITMAPINFO info{};info.bmiHeader.biSize=sizeof(BITMAPINFOHEADER);info.bmiHeader.biWidth=size;info.bmiHeader.biHeight=-size;info.bmiHeader.biPlanes=1;info.bmiHeader.biBitCount=32;info.bmiHeader.biCompression=BI_RGB;
        void *bits=nullptr;const auto dc=CreateCompatibleDC(nullptr);const auto bitmap=CreateDIBSection(dc,&info,DIB_RGB_COLORS,&bits,nullptr,0);
        const auto previous=SelectObject(dc,bitmap);RECT box{0,0,size,size};FillRect(dc,&box,reinterpret_cast<HBRUSH>(GetStockObject(WHITE_BRUSH)));
        DrawIconEx(dc,0,0,nativeIcon,size,size,0,nullptr,DI_NORMAL);
        QImage image(static_cast<uchar *>(bits),size,size,QImage::Format_RGB32);
        QSvgRenderer canonical(QStringLiteral(":/swirl/icons/swirl_windows.svg"));
        QImage reference(size,size,QImage::Format_RGB32);reference.fill(Qt::white);
        {QPainter painter(&reference);painter.drawImage(QPoint(),swirlBrandRaster(canonical,size));}
        int maximumError=0,warm=0,cool=0,green=0;qint64 totalError=0;
        for(int y=0;y<size;++y)for(int x=0;x<size;++x){
            const auto actual=image.pixelColor(x,y),expected=reference.pixelColor(x,y);
            maximumError=qMax(maximumError,qMax(qAbs(actual.red()-expected.red()),qMax(qAbs(actual.green()-expected.green()),qAbs(actual.blue()-expected.blue()))));
            totalError+=distance(actual,expected);
            if(actual.red()>actual.green()+35 && actual.red()>actual.blue()+35)++warm;
            if(actual.blue()>actual.red()+35)++cool;
            if(actual.green()>actual.red()+25 && actual.green()>actual.blue()+10)++green;
        }
        qInfo()<<"NATIVE_ICON_CANONICAL"<<size<<"maxChannelError"<<maximumError<<"totalChannelError"<<totalError<<"warm/cool/green"<<warm<<cool<<green;
        check(canonical.isValid() && warm>0 && cool>0 && green>0 && maximumError<=2 && totalError<=size*size,
              "native taskbar frame matches the canonical colored knot and every color passage");
        image.save(directory+"/taskbar-native-icon.png");SelectObject(dc,previous);DeleteObject(bitmap);DeleteDC(dc);
        }
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
    const int contentChange=distance(red.pixelColor(red.width()-2,red.height()/2),blue.pixelColor(blue.width()-2,blue.height()/2));
    const QPoint headerPoint(red.width()/2,qRound(8*window->devicePixelRatio()));
    const int workspaceMaterialChange=distance(red.pixelColor(headerPoint),blue.pixelColor(headerPoint));
    qInfo()<<"Native pixel delta: sidebar="<<sidebarChange<<"content="<<contentChange<<"DPR="<<window->devicePixelRatio()<<backdrop->status();
    const bool exactOpaque=backdrop->exactCorners()&&!backdrop->micaActive()&&!backdrop->blurActive();
    check(exactOpaque ? !backdrop->translucent()&&backdrop->status().startsWith("Opaque:")
                      : (backdrop->micaActive()&&backdrop->status().contains("Windows Mica"))||(backdrop->blurActive()&&backdrop->status().contains("Windows native blur")),
          "composition reports actual native material or an opaque fallback without raw desktop alpha");
    check(sidebarChange<=12,"sidebar retains a restrained neutral material tint");
    check(contentChange<=3,"opaque outer edge does not reveal desktop content");
    check(state("window.opacity===1 && !scaledCanvas.layer.enabled").toBool(),"native material changes background only; foreground text and controls remain fully opaque");
    if(backdrop->blurActive()){
        check(sidebarChange<=workspaceMaterialChange&&workspaceMaterialChange<80,"darker sidebar subdues the shared native material while workspace tint remains restrained");
        const auto scale=window->devicePixelRatio();const auto divider=state("window.actualSidebarWidth").toReal();
        const auto lhs=red.pixelColor(qRound((divider-12)*scale),qRound(20*scale));
        const auto rhs=red.pixelColor(qRound((divider+12)*scale),qRound(20*scale));
        qInfo()<<"SIDEBAR_INTENTIONAL_RIM_SHADOW"<<QPointF(divider-12,20)<<lhs<<QPointF(divider+12,20)<<rhs<<"delta"<<distance(lhs,rhs);
        auto *pane=find(window->contentItem(),QStringLiteral("sidebarFloatingBackground"));
        auto *identity=find(window->contentItem(),QStringLiteral("engineIdentityLabel"));
        auto *firstNavigation=find(window->contentItem(),QStringLiteral("nav-activity"));
        auto *statusCard=find(window->contentItem(),QStringLiteral("activityStatusCard"));
        QQuickItem *shadow=nullptr;
        if(pane)for(auto *child:pane->childItems())if(child->property("shadowOffset").isValid() && child->property("softness").isValid())shadow=child;
        const auto sceneRect=[](QQuickItem *item){return item?item->mapRectToScene(QRectF(QPointF(),item->size())):QRectF();};
        const auto paneRect=sceneRect(pane),shadowRect=sceneRect(shadow),identityRect=sceneRect(identity),navigationRect=sceneRect(firstNavigation);
        const qreal quietY=(identityRect.bottom()+navigationRect.top())/2;
        const qreal paneRadius=pane?pane->property("radius").toReal():0;
        const QPointF inside(paneRect.right()-2*paneRadius,quietY),outside(shadowRect.right()+2/scale,quietY);
        const bool quietSamplesKnown=pane && shadow && identity && firstNavigation && statusCard
            && quietY>identityRect.bottom() && quietY<navigationRect.top() && paneRect.contains(inside)
            && inside.x()<paneRect.right()-paneRadius && !paneRect.contains(outside) && !shadowRect.contains(outside)
            && !sceneRect(statusCard).contains(outside) && QRectF(QPointF(),window->size()).contains(outside);
        check(quietSamplesKnown,"sidebar continuity samples avoid foreground content, rounded rim and the full shadow envelope");
        const auto interior=quietSamplesKnown?red.pixelColor((inside*scale).toPoint()):QColor();
        const auto exterior=quietSamplesKnown?red.pixelColor((outside*scale).toPoint()):QColor();
        qInfo()<<"SIDEBAR_QUIET_CONTINUITY"<<inside<<interior<<outside<<exterior<<"delta"<<distance(interior,exterior);
        check(quietSamplesKnown && distance(interior,exterior)<=20,"sidebar and workspace share the base material away from the intentional floating rim and shadow");
    }
    // The native material stays behind an opaque perimeter. The QML
    // tint is translucent only where the native helper fully covers it.
    const auto perimeter=window->grabWindow();
    const auto materialAlpha=perimeter.pixelColor(perimeter.width()-2,perimeter.height()/2).alpha();
    check(materialAlpha==255,"outer material perimeter is fully opaque");
    const auto innerAlpha=window->grabWindow().pixelColor(int(window->width()*0.5*window->devicePixelRatio()),qRound(8*window->devicePixelRatio())).alpha();
    check(exactOpaque ? innerAlpha==255 : qAbs(innerAlpha-qRound(state("Theme.nativeTintOpacity").toReal()*255))<=2,"inner alpha follows effective native-material capability");
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
    check(moveDelta<=12,"moving across other windows retains the restrained neutral shell tint");
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
    check(backdrop->micaActive() ? backdrop->status().contains("Windows Mica") : backdrop->blurActive()?backdrop->status().contains("Windows native blur"):!backdrop->translucent()&&backdrop->status().startsWith("Opaque:"),
          "dark theme retains actual native material or opaque capability fallback");
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
#ifdef Q_OS_WIN
    const HWND hwnd=reinterpret_cast<HWND>(window->winId());
    MONITORINFO monitor{sizeof(MONITORINFO)};RECT nativeFrame{},maximizedClient{};POINT maximizedOrigin{};
    const bool clientBounds=GetMonitorInfoW(MonitorFromWindow(hwnd,MONITOR_DEFAULTTONEAREST),&monitor)
        &&GetClientRect(hwnd,&maximizedClient)&&ClientToScreen(hwnd,&maximizedOrigin);
    OffsetRect(&maximizedClient,maximizedOrigin.x,maximizedOrigin.y);
    const bool frameKnown=SUCCEEDED(DwmGetWindowAttribute(hwnd,DWMWA_EXTENDED_FRAME_BOUNDS,&nativeFrame,sizeof(nativeFrame)));
    qInfo()<<"MAXIMIZED_NATIVE_FRAME"<<nativeFrame.left<<nativeFrame.top<<nativeFrame.right<<nativeFrame.bottom
        <<"CLIENT"<<maximizedClient.left<<maximizedClient.top<<maximizedClient.right<<maximizedClient.bottom
        <<"WORK_AREA"<<monitor.rcWork.left<<monitor.rcWork.top<<monitor.rcWork.right<<monitor.rcWork.bottom;
    // DWM reports the entire native frame when NC rendering is disabled.
    // Every actual client pixel must fit the work area without being cropped.
    check(window->visibility()==QWindow::Maximized&&IsZoomed(hwnd)&&frameKnown&&clientBounds&&EqualRect(&maximizedClient,&monitor.rcWork),
        "Windows maximize client exactly matches the monitor work area and excludes the taskbar");
    click("windowMinimizeButton");
    WINDOWPLACEMENT placement{sizeof(WINDOWPLACEMENT)};
    check(GetWindowPlacement(hwnd,&placement)&&window->windowStates().testFlag(Qt::WindowMinimized)
        &&window->windowStates().testFlag(Qt::WindowMaximized)&&(placement.flags&WPF_RESTORETOMAXIMIZED),
        "actual minimize button preserves maximized Qt and Windows placement state");
    SendMessageW(hwnd,WM_SYSCOMMAND,SC_RESTORE,0);QTest::qWait(350);
    check(IsZoomed(hwnd)&&window->visibility()==QWindow::Maximized,"native taskbar restore retains the button's maximized state");
    SendMessageW(hwnd,WM_SYSCOMMAND,SC_MINIMIZE,0);QTest::qWait(250);
    check(window->windowStates().testFlag(Qt::WindowMinimized)&&window->windowStates().testFlag(Qt::WindowMaximized),
        "native taskbar minimize preserves maximized state");
    window->setWindowStates(window->windowStates()&~Qt::WindowMinimized);
    if(!window->isVisible())window->setVisible(true);
    window->requestActivate();QTest::qWait(350);
    check(IsZoomed(hwnd)&&window->visibility()==QWindow::Maximized,"instance activation restores maximized state without show resetting it");
#else
    check(window->visibility()==QWindow::Maximized&&window->geometry()==window->screen()->availableGeometry(),"maximize respects the available work area");
#endif
    click("windowMaximizeButton");QTest::qWait(300);
    check(window->visibility()==QWindow::Windowed,"restore returns to windowed state");
    click("windowMinimizeButton");QTest::qWait(300);
    check(window->visibility()==QWindow::Minimized,"minimization works");
    window->showNormal();window->requestActivate();QTest::qWait(300);
    check(window->visibility()==QWindow::Windowed,"restore from minimized works");
#ifdef Q_OS_WIN
    const auto style=GetWindowLongPtrW(hwnd,GWL_STYLE);
    constexpr LONG_PTR required=WS_CAPTION|WS_THICKFRAME|WS_SYSMENU|WS_MINIMIZEBOX|WS_MAXIMIZEBOX;
    check((style&required)==required,"native transition, resize and caption-command styles survive repeated window state changes");
    check(!(GetWindowLongPtrW(hwnd,GWL_EXSTYLE)&WS_EX_LAYERED),"restore retains DWM-compatible alpha composition");
    RECT rect;GetWindowRect(hwnd,&rect);
    RECT client{};POINT origin{};
    check(GetClientRect(hwnd,&client)&&ClientToScreen(hwnd,&origin)&&origin.x==rect.left&&origin.y==rect.top
        &&client.right==rect.right-rect.left&&client.bottom==rect.bottom-rect.top,"custom client covers the entire HWND without a native caption band");
    NCCALCSIZE_PARAMS calculation{};calculation.rgrc[0]=rect;
    check(SendMessageW(hwnd,WM_NCCALCSIZE,TRUE,reinterpret_cast<LPARAM>(&calculation))==0
        &&EqualRect(&rect,&calculation.rgrc[0]),"native nonclient calculation preserves all client pixels");
    check(SendMessageW(hwnd,WM_NCPAINT,1,0)==0&&SendMessageW(hwnd,WM_NCACTIVATE,FALSE,0)==TRUE
        &&SendMessageW(hwnd,WM_NCACTIVATE,TRUE,0)==TRUE,"native nonclient paint and activation are suppressed by the custom frame");
    const auto hit=SendMessageW(hwnd,WM_NCHITTEST,0,MAKELPARAM(rect.left+2,rect.top+2));
    check(hit==HTTOPLEFT,"native corner hit test enables edge resizing");
    check(GetSystemMenu(hwnd,FALSE)!=nullptr,"native Alt+Space menu exists");
    // A translucent test surface exposes native caption painting that opaque
    // application cards could conceal. The ordinary scene is restored below.
    QQmlComponent captionComponent(qmlEngine(window));
    captionComponent.setData("import QtQuick; Rectangle {color:'#ADF52171';radius:14;antialiasing:true}",QUrl());
    auto *captionProbe=qobject_cast<QQuickItem *>(captionComponent.create(qmlContext(window)));
    check(captionProbe,"translucent native-caption fixture created");
    if(captionProbe){
        QList<QPair<QQuickItem *,bool>> visibility;
        for(auto *child:window->contentItem()->childItems()){visibility.append(qMakePair(child,child->isVisible()));child->setVisible(false);}
        captionProbe->setParentItem(window->contentItem());captionProbe->setSize(window->size());
        QTest::qWait(150);
        SendMessageW(hwnd,WM_NCPAINT,1,0);SendMessageW(hwnd,WM_NCACTIVATE,FALSE,0);SendMessageW(hwnd,WM_NCACTIVATE,TRUE,0);
        QTest::qWait(100);
        const auto alphaSurface=window->grabWindow();
        check(!alphaSurface.isNull()&&qAbs(alphaSurface.pixelColor(alphaSurface.width()/2,alphaSurface.height()/2).alpha()-173)<=1,
            "native-caption fixture remains translucent instead of hiding native paint with opaque fill");
        const auto captionFrame=grab("native-caption-alpha");
        bool clean=!captionFrame.isNull();int delta=0;
        if(clean){
            const auto dpr=window->devicePixelRatio();
            const auto expected=captionFrame.pixelColor(qRound(window->width()*0.6*dpr),qRound(100*dpr));
            for(int y=qRound(8*dpr);y<qRound(28*dpr);++y)for(int x=qRound(window->width()*0.55*dpr);x<qRound(window->width()*0.94*dpr);++x){
                const auto color=captionFrame.pixelColor(x,y);
                delta=qMax(delta,qMax(qAbs(color.red()-expected.red()),qMax(qAbs(color.green()-expected.green()),qAbs(color.blue()-expected.blue()))));
            }
            qInfo()<<"NATIVE_CAPTION_ALPHA_DELTA"<<delta;
        }
        check(clean&&delta<=2,"actual DWM translucent header has no native caption, buttons or frame stripe");
        delete captionProbe;
        for(const auto &entry:visibility)entry.first->setVisible(entry.second);
        QTest::qWait(100);
    }
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
