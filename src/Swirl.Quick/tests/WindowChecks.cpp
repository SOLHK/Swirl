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
    window->resize(1280,800);
    window->setPosition(available.topLeft()+QPoint(60,40));
    window->showNormal();window->raise();window->requestActivate();QTest::qWait(900);
#ifdef Q_OS_WIN
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
    if(GetForegroundWindow()!=testHwnd){qCritical()<<"Native validation blocked: test window is not in foreground";return 3;}
    const auto radius=state("Theme.windowRadius").toReal()*window->devicePixelRatio();
    const auto region=CreateRectRgn(0,0,0,0);
    check(GetWindowRgn(testHwnd,region)==ERROR,"native hard region is removed so it cannot cut antialiased pixels");
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
    check(normalCorner.second>=5,"opaque main surface has partially covered antialiased corner pixels");
    state("Theme.setScalePercent(125)");QTest::qWait(150);
    check(cornerCoverage().first<normalCorner.first,"manual UI zoom updates alpha corner coverage without a resize");
    state("Theme.resetScale()");QTest::qWait(150);
#endif
    const auto grab=[&](const QString &name){
#ifdef Q_OS_WIN
        check(GetForegroundWindow()==testHwnd,"native screenshot samples the foreground test window");
        qInfo()<<"Capture state"<<name<<"active="<<window->isActive()<<"foreground="<<(GetForegroundWindow()==reinterpret_cast<HWND>(window->winId()))<<"extended style="<<QString::number(GetWindowLongPtrW(reinterpret_cast<HWND>(window->winId()),GWL_EXSTYLE),16)<<"QML opacity="<<state("Theme.sidebarOpacity");
#endif
        // Read the actual desktop compositor, never QQuickWindow::grabWindow,
        // which contains only the application's alpha surface.
        auto img=window->screen()->grabWindow(0,window->x(),window->y(),window->width(),window->height()).toImage();
        check(!img.isNull() && img.save(directory+"/"+name+".png"),"native compositor screenshot saved");
        return img;
    };
    const auto sample=[](const QImage &img,qreal x,qreal y){return img.pixelColor(qBound(0,int(x*img.width()),img.width()-1),qBound(0,int(y*img.height()),img.height()-1));};
    const auto distance=[](QColor a,QColor b){return qAbs(a.red()-b.red())+qAbs(a.green()-b.green())+qAbs(a.blue()-b.blue());};
    QCursor::setPos(window->screen()->availableGeometry().topLeft()+QPoint(10,10));QTest::qWait(300);
    auto red=grab("backdrop-red");
    const QColor behind("#D72D31");
    check(distance(red.pixelColor(0,0),behind)<=3 && distance(red.pixelColor(red.width()-1,0),behind)<=3 && distance(red.pixelColor(0,red.height()-1),behind)<=3 && distance(red.pixelColor(red.width()-1,red.height()-1),behind)<=3,
          "all four composed corner pixels show the background instead of a rectangular material fill");
    background.setColor(QColor("#2464D8"));QTest::qWait(800);
    auto blue=grab("backdrop-blue");
    const int sidebarChange=distance(sample(red,0.01,0.83),sample(blue,0.01,0.83));
    const int contentChange=distance(sample(red,0.96,0.03),sample(blue,0.96,0.03));
    qInfo()<<"Native pixel delta: sidebar="<<sidebarChange<<"content="<<contentChange<<"DPR="<<window->devicePixelRatio()<<backdrop->status();
    check(backdrop->active(),"native translucent surface actually enabled on this machine");
    check(sidebarChange>12,"sidebar responds to changing real window behind it");
    check(contentChange<=3,"main content remains opaque under background color changes");
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
    check(distance(sample(left,0.01,0.83),sample(right,0.01,0.83))>12,"moving Swirl changes sidebar composition over split-color window");
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
    check(high-low>3,"native alpha sidebar responds to the background edge");
    delete rectangle;
    window->setPosition(available.topLeft()+QPoint(60,40));
    state("Theme.transparency=false");QTest::qWait(500);
    auto opaqueBlue=grab("backdrop-disabled-blue");
    background.setColor(QColor("#D72D31"));QTest::qWait(500);
    auto opaqueRed=grab("backdrop-disabled-red");
    check(!backdrop->active(),"application transparency setting disables native backdrop");
    check(distance(sample(opaqueBlue,0.01,0.83),sample(opaqueRed,0.01,0.83))<=3,"disabled transparency gives opaque sidebar fallback");
    state("Theme.transparency=true;Theme.mode='Dark'");QTest::qWait(500);grab("overview-native-dark");
    check(backdrop->active(),"native backdrop remains available in dark theme");
    state("Theme.mode='Light'");
    auto *title=find(window->contentItem(),"titleDragArea");
    check(title,"title drag region exists");
    if (title) {
        QTest::mouseDClick(window,Qt::LeftButton,Qt::NoModifier,title->mapToScene(QPointF(title->width()/2,20)).toPoint());QTest::qWait(350);
        check(window->visibility()==QWindow::Maximized,"double click title maximizes actual window");
        QTest::mouseDClick(window,Qt::LeftButton,Qt::NoModifier,title->mapToScene(QPointF(title->width()/2,20)).toPoint());QTest::qWait(350);
        check(window->visibility()==QWindow::Windowed,"double click title restores actual window");
    }
    click("windowMaximizeButton");QTest::qWait(500);grab("overview-maximized");
    qInfo()<<"Maximized geometry"<<window->geometry()<<"work area"<<available;
    check(window->geometry()==available,"maximization respects work area without corner gaps");
    click("windowMaximizeButton");QTest::qWait(300);
    check(window->visibility()==QWindow::Windowed,"restore returns to windowed state");
    click("windowMinimizeButton");QTest::qWait(300);
    check(window->visibility()==QWindow::Minimized,"minimization works");
    window->showNormal();window->requestActivate();QTest::qWait(300);
    check(window->visibility()==QWindow::Windowed,"restore from minimized works");
#ifdef Q_OS_WIN
    const HWND hwnd=reinterpret_cast<HWND>(window->winId());
    const auto style=GetWindowLongPtrW(hwnd,GWL_STYLE);
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
