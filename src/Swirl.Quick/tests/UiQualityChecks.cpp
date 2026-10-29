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
#include <QFont>
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
        if(!baseline){const bool exact=w->property("swirlExactWindowRadius").toBool();check(corner==(exact?1:2)&&material==(backdrop->active()?3:1),name+": exact-region or native-preset contour and effective material confirmed");check(!(GetWindowLongPtrW(hwnd,GWL_EXSTYLE)&WS_EX_LAYERED),name+": no layered HWND blocking native composition");
            constexpr LONG_PTR required=WS_CAPTION|WS_THICKFRAME|WS_SYSMENU|WS_MINIMIZEBOX|WS_MAXIMIZEBOX;
            check((GetWindowLongPtrW(hwnd,GWL_STYLE)&required)==required,name+": native transition, resize, system menu and minimize/maximize styles retained");
            RECT client{};POINT origin{};
            check(GetClientRect(hwnd,&client)&&ClientToScreen(hwnd,&origin)&&origin.x==r.left&&origin.y==r.top
                &&client.right==r.right-r.left&&client.bottom==r.bottom-r.top,name+": custom client occupies the full HWND without a native caption band");
            check(SendMessageW(hwnd,WM_NCPAINT,1,0)==0&&SendMessageW(hwnd,WM_NCACTIVATE,FALSE,0)==TRUE
                &&SendMessageW(hwnd,WM_NCACTIVATE,TRUE,0)==TRUE,name+": native caption paint and activation are handled by the custom frame");
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
    auto auditText=[&](QQuickWindow *window,const QString &route) {
        int glyphs=0,native=0,layered=0,scaled=0,smallTextCount=0,wrongFamily=0;
        std::function<void(QQuickItem *)> scan=[&](QQuickItem *item) {
            if(!item->isVisible())return;
            if(item->property("text").isValid() && item->property("renderType").isValid()) {
                ++glyphs;if(item->property("renderType").toInt()==1)++native;
                const auto font=item->property("font").value<QFont>();if(font.pixelSize()>0&&font.pixelSize()<12)++smallTextCount;
                if(font.family()!=QGuiApplication::font().family()){++wrongFamily;qInfo()<<"TEXT_FONT_MISMATCH"<<item->property("text").toString().left(30)<<font.family();}
                for(auto *p=item;p;p=p->parentItem()) {
                    QQmlExpression layer(qmlContext(window),p,"layer.enabled");
                    if(layer.evaluate().toBool()){++layered;break;}
                }
                for(auto *p=item;p;p=p->parentItem())if(p->scale()!=1){++scaled;break;}
            }
            for(auto *child:item->childItems())scan(child);
        };scan(window->contentItem());
        qInfo()<<"TEXT_AUDIT"<<route<<"glyphs"<<glyphs<<"native"<<native<<"layered"<<layered<<"scaled"<<scaled<<"small"<<smallTextCount;
        check(glyphs>0 && glyphs==native && !layered && !scaled && !smallTextCount && !wrongFamily,route+": selected font, native text >=12px, no textured or scaled glyph ancestors");
    };
    main->resize(914,672);
    for(const auto &route:QStringList{"activity","overview","processes","policies","rules","capture","tls","featurehub"}){eval(QString("AppState.navigate('%1')").arg(route));QTest::qWait(250);const auto frame=capture(main,route);if(!baseline)auditText(main,route);
        if(!baseline && route=="capture"){eval("pageLoader.item.scrollToBottom()");QTest::qWait(150);capture(main,"capture-bottom");}
        if(!baseline && route=="activity" && !frame.isNull()){
            // The old x=195 sample crosses the floating sidebar's curved rim.
            // The workspace centre stays clear of controls and that shadow.
            const auto ratio=main->devicePixelRatio();const auto a=frame.pixelColor(frame.width()/2,qRound(20*ratio)),b=frame.pixelColor(frame.width()/2,qRound(45*ratio));
            const int delta=qAbs(a.red()-b.red())+qAbs(a.green()-b.green())+qAbs(a.blue()-b.blue());qInfo()<<"TITLE_BAND_DELTA"<<delta;check(delta<5,"traffic lights and proxy row have no horizontal caption band");
        }
    }
    if(!baseline){auto *events=find(main->contentItem(),"eventsCapsule");check(events&&!events->property("label").toString().contains("警告")&&events->property("tone").toString()!="warning","top capsule uses event rather than warning semantics");}
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
    if(!baseline){
        auto *button=find(main->contentItem(),"nav-policies");
        check(button&&button->isVisible()&&button->isEnabled(),"policy navigation has a visible operable sidebar entry");
        if(button)QTest::mouseClick(main,Qt::LeftButton,Qt::NoModifier,button->mapToScene(QPointF(button->width()/2,button->height()/2)).toPoint());
        QTest::qWait(300);
        check(eval("AppState.currentPage==='policies' && pageLoader.item!==null").toBool(),"real sidebar mouse input opens the current policy workspace");
    }
    // Real node-store entries, reserved loopback endpoints; never connect.
    for(int i=0;i<13;++i)check(eval(QString("engineController.saveNode({name:'验证节点 %1 · 长名称自适应排版',protocol:'http',host:'127.0.0.1',port:%2})").arg(i+1).arg(25000+i)).toBool(),"isolated node fixture saved");
    eval("AppState.navigate('proxies')");QTest::qWait(200);capture(main,"nodes-many");
    if(!baseline){
        check(eval("pageLoader.item.resultCount===13 && pageLoader.item.filteredNodeIds().length===13").toBool(),"all thirteen nodes belong to the current source-sectioned library");
        auto *table=find(main->contentItem(),"realNodeTable");
        auto *viewport=table?find(table,"tableRowsViewport"):nullptr;
        check(viewport&&viewport->isVisible()&&viewport->property("reuseItems").toBool(),"many-node library has an operable recycled-row viewport");
        if(viewport){
            bool reachable=true;
            for(int i=0;i<13;++i){
                const auto id=eval(QString("pageLoader.item.filteredNodeIds()[%1]").arg(i)).toString();
                const auto rowIndex=eval(QString("pageLoader.item.sectionIndexForNode('%1')").arg(id)).toInt();
                const bool positioned=QMetaObject::invokeMethod(viewport,"positionViewAtIndex",Q_ARG(int,rowIndex),Q_ARG(int,1));
                QTest::qWait(35);QQuickItem *row=nullptr;
                const bool materialized=QMetaObject::invokeMethod(viewport,"itemAtIndex",Q_RETURN_ARG(QQuickItem *,row),Q_ARG(int,rowIndex));
                QQmlExpression rowId(row?qmlContext(row):nullptr,row,"record.id");
                const auto actual=row?rowId.evaluate().toString():QString();
                const auto visible=viewport->mapRectToScene(QRectF(QPointF(),viewport->size()));
                reachable=reachable&&positioned&&materialized&&row&&!rowId.hasError()&&actual==id
                    &&visible.contains(row->mapToScene(QPointF(row->width()/2,row->height()/2)));
            }
            check(reachable,"each of thirteen real node rows can be scrolled into view with its matching identity");
            const auto firstRow=eval("pageLoader.item.sectionIndexForNode(pageLoader.item.filteredNodeIds()[0])").toInt();
            viewport->setProperty("currentIndex",firstRow);
            QMetaObject::invokeMethod(viewport,"positionViewAtBeginning");QTest::qWait(50);
            viewport->forceActiveFocus();
            // Qt ListView implements arrow navigation; End is not bound here.
            for(int index=firstRow;index<viewport->property("count").toInt()-1;++index){QTest::keyClick(main,Qt::Key_Down);QTest::qWait(20);}
            QTest::qWait(100);
            qInfo()<<"NODE_ARROW_NAVIGATION"<<"first row"<<firstRow<<"current"<<viewport->property("currentIndex")
                <<"count"<<viewport->property("count")<<"contentY"<<viewport->property("contentY")
                <<"originY"<<viewport->property("originY")<<"contentHeight"<<viewport->property("contentHeight")
                <<"height"<<viewport->height()<<"activeFocus"<<viewport->hasActiveFocus();
            check(viewport->property("contentY").toReal()>viewport->property("originY").toReal()
                &&viewport->property("currentIndex").toInt()==viewport->property("count").toInt()-1,"native Down keys scroll the virtual node list to its final row");
            capture(main,"nodes-scrolled-end");
        }
    }
    for(const auto &route:QStringList{"proxies","settings","subscriptions"}){
        eval(QString("window.openSettings('%1')").arg(route));QTest::qWait(450);
        check(eval("pageLoader.item.Window.window===window").toBool(),route+": route belongs to main HWND");
        capture(main,route=="proxies"?"nodes":route);if(!baseline)auditText(main,route);
        if(route=="proxies"&&!baseline){auto *search=find(main->contentItem(),"nodeSearchField"),*combo=find(main->contentItem(),"nodeSourceFilter");check(search&&combo&&qAbs(search->height()-combo->height())<1,"node search and the current source filter share control height");}
    }
    eval("window.openDashboard()");QTest::qWait(200);auto *panel=main->findChild<QQuickWindow *>("dashboardWindow");if(panel){panel->resize(qMin(1300,area.width()-60),600);capture(panel,"panel");panel->hide();}
    eval("Theme.mode='Dark';AppState.navigate('activity')");QTest::qWait(200);capture(main,"activity-dark");eval("Theme.transparency=false");QTest::qWait(200);
    if(!baseline)check(!backdrop->active(),"transparency off disables system material");
    capture(main,"opaque-fallback"); // stored even though material is NONE
    if(!baseline){
        check(eval("fontManager.selectFamily('Microsoft YaHei UI')").toBool(),"live font alternative is available");
        eval("Theme.mode='Light';AppState.navigate('capture')");QTest::qWait(150);
        capture(main,"capture-font-switch");auditText(main,"capture-live-font-switch");
    }
    delete pattern;behind.hide();main->hide();
    QFile report(directory+"/quality-report.json");if(report.open(QIODevice::WriteOnly))report.write(QJsonDocument(QJsonObject{{"baseline",baseline},{"dpr",main->devicePixelRatio()},{"checks",results},{"failures",failures}}).toJson());
    qInfo()<<"UI_QUALITY_CHECKS"<<results.size()<<"failures"<<failures;return failures?2:0;
#endif
}
