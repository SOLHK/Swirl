#include "UiQualityChecks.h"
#include "../app/WindowsBackdrop.h"
#include <QQuickWindow>
#include <QQuickItem>
#include <QGuiApplication>
#include <QScreen>
#include <QTest>
#include <QQmlContext>
#include <QQmlExpression>
#include <QQmlComponent>
#include <QQmlEngine>
#include <QDir>
#include <QFile>
#include <QJsonDocument>
#include <QJsonArray>
#include <QJsonObject>
#include <QImage>
#include <functional>
#ifdef Q_OS_WIN
#include <windows.h>
#include <dwmapi.h>
#endif
int runUiQualityChecks(QQuickWindow *main,WindowsBackdrop *backdrop,const QString &directory,bool baseline) {
#ifndef Q_OS_WIN
    Q_UNUSED(main) Q_UNUSED(backdrop) Q_UNUSED(directory) Q_UNUSED(baseline)
    return 3;
#else
    QDir().mkpath(directory);int failures=0;QJsonArray results;
    const auto desktop=OpenInputDesktop(0,FALSE,DESKTOP_READOBJECTS);
    wchar_t name[128]{};DWORD needed=0;
    const bool defaultDesktop=desktop && GetUserObjectInformationW(desktop,UOI_NAME,name,sizeof(name),&needed) && QString::fromWCharArray(name)==QStringLiteral("Default");
    if(desktop)CloseDesktop(desktop);
    if(!defaultDesktop){qCritical()<<"UI quality capture requires an unlocked Default input desktop";return 3;}
    auto check=[&](bool ok,const QString &name){results.append(QJsonObject{{"name",name},{"pass",ok}});qInfo()<<(ok?"PASS":"FAIL")<<name;if(!ok)++failures;};
    auto eval=[&](const QString &code){QQmlExpression e(qmlContext(main),main,code);auto v=e.evaluate();check(!e.hasError(),"QML: "+code.left(100));if(e.hasError())qWarning()<<e.error();return v;};
    std::function<QQuickItem *(QQuickItem *,const QString &)> find=[&](QQuickItem *p,const QString &name)->QQuickItem *{if(p->objectName()==name)return p;for(auto *c:p->childItems())if(auto *r=find(c,name))return r;return nullptr;};
    eval("Theme.reduceMotion=true;Theme.mode='Light';Theme.transparency=true");
    const auto area=main->screen()->availableGeometry();
    QQuickWindow behind;behind.setTitle("Swirl controlled compositor fixture");behind.setFlags(Qt::Window|Qt::FramelessWindowHint|Qt::WindowStaysOnTopHint);behind.setGeometry(area);behind.setColor(QColor("#536BB4"));
    QQmlComponent fixture(qmlEngine(main));fixture.setData(R"(
import QtQuick
Item { Rectangle {anchors.fill:parent;color:'#536BB4'}
 Column {anchors.fill:parent;spacing:4;Repeater {model:70;Text {text:'BACKGROUND TEXT 0123456789  背景文字不应穿透阅读区域  ABCDEFGHIJKLMNOPQRSTUVWXYZ';font.pixelSize:18;color:index%2?'white':'#101420'}}}
})",QUrl());
    auto *pattern=qobject_cast<QQuickItem *>(fixture.create());if(!pattern)return 3;pattern->setParentItem(behind.contentItem());pattern->setSize(area.size());behind.show();pattern->setVisible(false);QTest::qWait(200);
    auto activate=[&](QQuickWindow *w){if(w!=main)main->hide();SetWindowPos(reinterpret_cast<HWND>(behind.winId()),HWND_TOPMOST,0,0,0,0,SWP_NOMOVE|SWP_NOSIZE|SWP_NOACTIVATE);w->showNormal();w->setPosition(area.topLeft()+QPoint(30,25));w->raise();w->requestActivate();const auto hwnd=reinterpret_cast<HWND>(w->winId());ShowWindow(hwnd,SW_SHOWNORMAL);SetWindowPos(hwnd,HWND_TOPMOST,0,0,0,0,SWP_NOMOVE|SWP_NOSIZE);const DWORD foregroundThread=GetWindowThreadProcessId(GetForegroundWindow(),nullptr);const DWORD currentThread=GetCurrentThreadId();const bool attached=foregroundThread!=currentThread && AttachThreadInput(currentThread,foregroundThread,TRUE);SetForegroundWindow(hwnd);if(attached)AttachThreadInput(currentThread,foregroundThread,FALSE);QTest::qWait(450);return hwnd;};
    auto capture=[&](QQuickWindow *w,const QString &name){
        const auto hwnd=activate(w);RECT r{};GetWindowRect(hwnd,&r);
        if(GetForegroundWindow()!=hwnd){check(false,name+": foreground capture guard");return QImage();}
        check(r.left>=area.x()*w->devicePixelRatio()&&r.top>=area.y()*w->devicePixelRatio(),name+": onscreen origin");
        const auto dc=GetDC(nullptr),mem=CreateCompatibleDC(dc);BITMAPINFO info{};info.bmiHeader.biSize=sizeof(BITMAPINFOHEADER);info.bmiHeader.biWidth=r.right-r.left;info.bmiHeader.biHeight=-(r.bottom-r.top);info.bmiHeader.biPlanes=1;info.bmiHeader.biBitCount=32;void *bits=nullptr;
        const auto bitmap=CreateDIBSection(mem,&info,DIB_RGB_COLORS,&bits,nullptr,0);QImage image;
        if(bitmap&&bits){auto prev=SelectObject(mem,bitmap);if(BitBlt(mem,0,0,r.right-r.left,r.bottom-r.top,dc,r.left,r.top,SRCCOPY|CAPTUREBLT))image=QImage(static_cast<uchar *>(bits),r.right-r.left,r.bottom-r.top,QImage::Format_RGB32).copy();SelectObject(mem,prev);DeleteObject(bitmap);}DeleteDC(mem);ReleaseDC(nullptr,dc);
        check(!image.isNull()&&image.save(directory+"/"+name+".png"),name+": actual DWM image saved");
        int corner=0,material=0;DwmGetWindowAttribute(hwnd,33,&corner,sizeof(corner));DwmGetWindowAttribute(hwnd,38,&material,sizeof(material));
        qInfo()<<name<<"DPR"<<w->devicePixelRatio()<<"styles"<<QString::number(GetWindowLongPtrW(hwnd,GWL_STYLE),16)<<QString::number(GetWindowLongPtrW(hwnd,GWL_EXSTYLE),16)<<"DWM"<<corner<<material;
        if(!baseline){check(corner==2&&material==(backdrop->active()?3:1),name+": native corner preference and effective material confirmed");check(!(GetWindowLongPtrW(hwnd,GWL_EXSTYLE)&WS_EX_LAYERED),name+": no layered HWND blocking native corners");check(!(GetWindowLongPtrW(hwnd,GWL_STYLE)&WS_CAPTION),name+": only Swirl traffic lights, no native caption buttons");
            // The fixture is visible outside the system contour. Each tip must
            // match the nearby desktop rather than QML's light-blue rectangle.
            const auto desktop=GetDC(nullptr);int matches=0;
            for(auto p:{QPoint(0,0),QPoint(image.width()-1,0),QPoint(0,image.height()-1),QPoint(image.width()-1,image.height()-1)}){
                const int side=p.x()==0?-8:8;const auto expected=GetPixel(desktop,r.left+p.x()+side,r.top+p.y());const auto pixel=image.pixelColor(p);const int delta=qAbs(pixel.red()-GetRValue(expected))+qAbs(pixel.green()-GetGValue(expected))+qAbs(pixel.blue()-GetBValue(expected));qInfo()<<"CORNER"<<name<<p<<pixel<<delta;if(delta<60)++matches;
            }ReleaseDC(nullptr,desktop);if(!pattern->isVisible())check(matches==4,name+": all four tips are clipped by compositor");
        }
        if(!image.isNull()){const int n=qRound(36*w->devicePixelRatio());int index=0;for(auto p:{QPoint(0,0),QPoint(image.width()-n,0),QPoint(0,image.height()-n),QPoint(image.width()-n,image.height()-n)})image.copy(QRect(p,QSize(n,n))).save(directory+QString("/%1-corner-%2.png").arg(name).arg(index++));}
        return image;
    };
    main->resize(914,672);
    for(const auto &route:QStringList{"activity","processes","policies","rules","capture","featurehub"}){eval(QString("AppState.navigate('%1')").arg(route));QTest::qWait(250);const auto frame=capture(main,route);
        if(!baseline && route=="capture"){eval("pageLoader.item.scrollToBottom()");QTest::qWait(150);capture(main,"capture-bottom");}
        if(!baseline && route=="activity" && !frame.isNull()){
            const auto ratio=main->devicePixelRatio();const auto a=frame.pixelColor(qRound(195*ratio),qRound(20*ratio)),b=frame.pixelColor(qRound(195*ratio),qRound(45*ratio));
            const int delta=qAbs(a.red()-b.red())+qAbs(a.green()-b.green())+qAbs(a.blue()-b.blue());qInfo()<<"TITLE_BAND_DELTA"<<delta;check(delta<5,"traffic lights and proxy row have no horizontal caption band");
        }
    }
    eval("AppState.navigate('activity')");QTest::qWait(150);
    pattern->setVisible(true);QTest::qWait(200);
    const auto textFrame=capture(main,"background-text");
    pattern->setVisible(false);QTest::qWait(250);const auto flatFrame=capture(main,"background-flat");
    if(!baseline&&!textFrame.isNull()&&textFrame.size()==flatFrame.size()){
        // Fixed empty gutter, no foreground glyphs. Sharp background text must
        // not survive; compare actual DWM pixels, never a QML alpha readback.
        double mean=0;int maximum=0,count=0;const auto dpr=main->devicePixelRatio();
        for(int y=qRound(80*dpr);y<qRound(450*dpr);++y)for(int x=qRound(192*dpr);x<qRound(199*dpr);++x){const auto a=textFrame.pixelColor(x,y),b=flatFrame.pixelColor(x,y);const int delta=qMax(qAbs(a.red()-b.red()),qMax(qAbs(a.green()-b.green()),qAbs(a.blue()-b.blue())));mean+=delta;maximum=qMax(maximum,delta);++count;}
        mean/=qMax(1,count);qInfo()<<"BACKGROUND_TEXT_DELTA mean"<<mean<<"max"<<maximum;check(mean<12&&maximum<24,"background glyph contrast suppressed in native gutter");
    }
    pattern->setVisible(false);
    // Real node-store entries, reserved loopback endpoints; never connect.
    for(int i=0;i<13;++i)eval(QString("engineController.saveNode({name:'验证节点 %1 · 长名称自适应排版',protocol:'http',host:'127.0.0.1',port:%2})").arg(i+1).arg(25000+i));
    eval("AppState.navigate('policies')");QTest::qWait(200);capture(main,"policies-many");
    if(!baseline){check(eval("pageLoader.item.nodePages>1").toBool(),"many nodes have explicit pages");auto *next=find(main->contentItem(),"nextNodePage");check(next&&next->isVisible()&&next->isEnabled(),"next node page is visible and operable");if(next){QTest::mouseClick(main,Qt::LeftButton,Qt::NoModifier,next->mapToScene(QPointF(next->width()/2,next->height()/2)).toPoint());QTest::qWait(100);check(eval("pageLoader.item.nodePage===1").toBool(),"pagination responds to real mouse input");capture(main,"policies-page-2");}}
    for(const auto &route:QStringList{"proxies","settings","subscriptions"}){
        eval(QString("window.openSettings('%1')").arg(route));QTest::qWait(250);auto *sheet=main->findChild<QQuickWindow *>("settingsSheet");check(sheet&&sheet->isVisible(),route+": separate HWND opens");if(!sheet)continue;
        sheet->resize(qMin(900,area.width()-60),qMin(790,area.height()-50));capture(sheet,route=="proxies"?"nodes":route);
        if(route=="proxies"&&!baseline){auto *search=find(sheet->contentItem(),"nodeSearchField"),*combo=find(sheet->contentItem(),"proxyRegionCombo");check(search&&combo&&qAbs(search->height()-combo->height())<1,"node search and protocol filter share height");}
        sheet->hide();
    }
    eval("window.openDashboard()");QTest::qWait(200);auto *panel=main->findChild<QQuickWindow *>("dashboardWindow");if(panel){panel->resize(qMin(1300,area.width()-60),600);capture(panel,"panel");panel->hide();}
    eval("Theme.mode='Dark';AppState.navigate('activity')");QTest::qWait(200);capture(main,"activity-dark");eval("Theme.transparency=false");QTest::qWait(200);
    if(!baseline)check(!backdrop->active(),"transparency off disables system material");
    capture(main,"opaque-fallback"); // stored even though material is NONE
    delete pattern;behind.hide();main->hide();
    QFile report(directory+"/quality-report.json");if(report.open(QIODevice::WriteOnly))report.write(QJsonDocument(QJsonObject{{"baseline",baseline},{"dpr",main->devicePixelRatio()},{"checks",results},{"failures",failures}}).toJson());
    qInfo()<<"UI_QUALITY_CHECKS"<<results.size()<<"failures"<<failures;return failures?2:0;
#endif
}
