#include "WallpaperBackdrop.h"
#include <QQuickWindow>
#include <QGuiApplication>
#include <QScreen>
#include <QImageReader>
#include <QPainter>
#include <QMutexLocker>
#include <QTimer>
#ifdef Q_OS_WIN
#include <windows.h>
#include <shobjidl.h>
#endif
WallpaperImages::WallpaperImages():QQuickImageProvider(QQuickImageProvider::Image,QQuickImageProvider::ForceAsynchronousImageLoading) {}
QImage WallpaperImages::requestImage(const QString &key,QSize *size,const QSize &) {
    QMutexLocker lock(&m_mutex);
    if(auto *cached=m_images.object(key)){if(size)*size=cached->size();return *cached;}
    const auto fields=key.section('/',0,0).split(',');
    if(fields.size()!=4)return {};
    const QRect monitor(fields[0].toInt(),fields[1].toInt(),fields[2].toInt(),fields[3].toInt());
    if(monitor.width()<=0||monitor.height()<=0)return {};
    const QSize target=monitor.size().scaled(2048,2048,Qt::KeepAspectRatio);
    QImage image(target,QImage::Format_ARGB32_Premultiplied);image.fill(QColor("#D6E6F4"));
    if(key.endsWith("/fixture")) {
        QPainter painter(&image);
        for(int y=0;y<target.height();y+=40)for(int x=0;x<target.width();x+=40)painter.fillRect(x,y,40,40,QColor((x/40*37+y/40*19)%220+20,(x/40*11+y/40*47)%220+20,(x/40*71+y/40*3)%220+20));
        painter.setPen(QPen(Qt::white,3));for(int i=0;i<14;++i)painter.drawEllipse(QPoint(target.width()*i/14,target.height()/2),80+i*5,80+i*5);
    } else {
#ifdef Q_OS_WIN
    const HRESULT apartment=CoInitializeEx(nullptr,COINIT_APARTMENTTHREADED);
    IDesktopWallpaper *desktop=nullptr;
    if(SUCCEEDED(CoCreateInstance(CLSID_DesktopWallpaper,nullptr,CLSCTX_ALL,IID_PPV_ARGS(&desktop)))) {
        UINT count=0;desktop->GetMonitorDevicePathCount(&count);
        DESKTOP_WALLPAPER_POSITION position=DWPOS_FILL;desktop->GetPosition(&position);
        COLORREF background=0;desktop->GetBackgroundColor(&background);image.fill(QColor(GetRValue(background),GetGValue(background),GetBValue(background)));
        for(UINT i=0;i<count;++i) {
            LPWSTR id=nullptr;RECT rect{};
            if(FAILED(desktop->GetMonitorDevicePathAt(i,&id)))continue;
            const bool matches=SUCCEEDED(desktop->GetMonitorRECT(id,&rect)) && QRect(rect.left,rect.top,rect.right-rect.left,rect.bottom-rect.top)==monitor;
            if(!matches){CoTaskMemFree(id);continue;}
            LPWSTR path=nullptr;desktop->GetWallpaper(id,&path);CoTaskMemFree(id);
            QImageReader reader(path?QString::fromWCharArray(path):QString());CoTaskMemFree(path);
            const auto nativeSize=reader.size();
            if(nativeSize.isValid())reader.setScaledSize(nativeSize.scaled(4096,4096,Qt::KeepAspectRatio));
            const auto original=reader.read();
            if(!original.isNull()) {
                QPainter painter(&image);painter.setRenderHint(QPainter::SmoothPixmapTransform);
                const auto fit=position==DWPOS_FIT?Qt::KeepAspectRatio:Qt::KeepAspectRatioByExpanding;
                if(position==DWPOS_TILE) {
                    const QSize tile(qMax(1,qRound(nativeSize.width()*double(target.width())/monitor.width())),qMax(1,qRound(nativeSize.height()*double(target.height())/monitor.height())));
                    const auto pixmap=original.scaled(tile,Qt::IgnoreAspectRatio,Qt::SmoothTransformation);
                    for(int y=0;y<target.height();y+=tile.height())for(int x=0;x<target.width();x+=tile.width())painter.drawImage(QPoint(x,y),pixmap);
                } else if(position==DWPOS_SPAN) {
                    const QRect desktopRect(GetSystemMetrics(SM_XVIRTUALSCREEN),GetSystemMetrics(SM_YVIRTUALSCREEN),GetSystemMetrics(SM_CXVIRTUALSCREEN),GetSystemMetrics(SM_CYVIRTUALSCREEN));
                    const auto fitted=nativeSize.scaled(desktopRect.size(),Qt::KeepAspectRatioByExpanding);
                    const QPoint offset=desktopRect.topLeft()+QPoint((desktopRect.width()-fitted.width())/2,(desktopRect.height()-fitted.height())/2);
                    const QRectF crop((monitor.x()-offset.x())*double(nativeSize.width())/fitted.width(),(monitor.y()-offset.y())*double(nativeSize.height())/fitted.height(),monitor.width()*double(nativeSize.width())/fitted.width(),monitor.height()*double(nativeSize.height())/fitted.height());
                    painter.drawImage(QRectF(QPointF(),target),original,QRectF(crop.x()*original.width()/nativeSize.width(),crop.y()*original.height()/nativeSize.height(),crop.width()*original.width()/nativeSize.width(),crop.height()*original.height()/nativeSize.height()));
                } else {
                    QSize draw=position==DWPOS_STRETCH?target:position==DWPOS_CENTER?QSize(qRound(nativeSize.width()*double(target.width())/monitor.width()),qRound(nativeSize.height()*double(target.height())/monitor.height())):nativeSize.scaled(target,fit);
                    painter.drawImage(QRect(QPoint((target.width()-draw.width())/2,(target.height()-draw.height())/2),draw),original);
                }
            }
            break;
        }
        desktop->Release();
    }
    if(SUCCEEDED(apartment))CoUninitialize();
#endif
    }
    if(size)*size=image.size();m_images.insert(key,new QImage(image),qMax(1,int(image.sizeInBytes()/1024)));return image;
}
WallpaperBackdrop::WallpaperBackdrop(bool fixture,QObject *parent):QObject(parent),m_fixture(fixture) {qApp->installNativeEventFilter(this);}
WallpaperBackdrop::~WallpaperBackdrop(){qApp->removeNativeEventFilter(this);}
QVariantMap WallpaperBackdrop::describe(QObject *object) const {
    const auto window=qobject_cast<QQuickWindow *>(object);if(!window||!window->screen())return {};
    const QRect logical=window->screen()->geometry();QRect physical=logical;
#ifdef Q_OS_WIN
    if(QGuiApplication::platformName()!=QStringLiteral("offscreen")) {
        MONITORINFO info{sizeof(info)};
        if(GetMonitorInfoW(MonitorFromWindow(reinterpret_cast<HWND>(window->winId()),MONITOR_DEFAULTTONEAREST),&info))physical=QRect(info.rcMonitor.left,info.rcMonitor.top,info.rcMonitor.right-info.rcMonitor.left,info.rcMonitor.bottom-info.rcMonitor.top);
    }
#endif
    const auto key=QString("%1,%2,%3,%4/%5").arg(physical.x()).arg(physical.y()).arg(physical.width()).arg(physical.height()).arg(m_revision);
    return {{"url","image://swirlwallpaper/"+key+(m_fixture?"/fixture":"")},{"x",logical.x()},{"y",logical.y()},{"width",logical.width()},{"height",logical.height()}};
}
bool WallpaperBackdrop::nativeEventFilter(const QByteArray &,void *message,qintptr *) {
#ifdef Q_OS_WIN
    const auto msg=static_cast<MSG *>(message);
    if(msg->message==WM_SETTINGCHANGE||msg->message==WM_DISPLAYCHANGE) {
        ++m_revision;emit changed();
    }
#else
    Q_UNUSED(message);
#endif
    return false;
}
