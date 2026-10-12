#include "MotionPolicy.h"
#include <QQuickWindow>
#include <QQuickItem>
#include <QTimer>
#include <QSGRendererInterface>
#include <QGuiApplication>
#include <QDateTime>
#include <QScreen>
#include <QAbstractNativeEventFilter>
#ifdef Q_OS_WIN
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#endif
namespace {
class PolicyEvents final : public QAbstractNativeEventFilter {
public:
    MotionPolicy *owner=nullptr;
    bool nativeEventFilter(const QByteArray &, void *message, qintptr *) override {
#ifdef Q_OS_WIN
        if(static_cast<MSG *>(message)->message==WM_SETTINGCHANGE && owner)
            emit owner->policyChanged();
#else
        Q_UNUSED(message);
#endif
        return false;
    }
};
}
MotionPolicy::MotionPolicy(QObject *parent):QObject(parent) {
    auto *events=new PolicyEvents;
    events->owner=this;
    qApp->installNativeEventFilter(events);
    connect(this,&QObject::destroyed,qApp,[events]{qApp->removeNativeEventFilter(events);delete events;});
}
bool MotionPolicy::systemReducedMotion() const {
#ifdef Q_OS_WIN
    BOOL enabled=TRUE;
    if(SystemParametersInfoW(SPI_GETCLIENTAREAANIMATION,0,&enabled,0))return !enabled;
#endif
    return false;
}
void MotionPolicy::attach(QQuickWindow *window) {
    m_clock.start();
    // Software rendering uses inexpensive spatial transitions without texture grabs.
    m_complex=window && window->rendererInterface()->graphicsApi()!=QSGRendererInterface::Software;
    if(window && window->screen())m_budget=1000.0/qMax(60.0,window->screen()->refreshRate());
    if(window)connect(window,&QQuickWindow::screenChanged,this,[this](QScreen *screen){if(screen)m_budget=1000.0/qMax(60.0,screen->refreshRate());});
    if(window)connect(window,&QQuickWindow::frameSwapped,this,[this,window]{
        const auto now=m_clock.nsecsElapsed();
        const auto last=m_lastFrame.load();
        if(m_transitioning.load() && last) {
            const double budget=m_budget.load();
            if(double(now-last)/1000000.0>qMax(25.0,budget*2.2))++m_slowFrames;
            else m_slowFrames=qMax(0,m_slowFrames-1);
            if(m_complex && m_slowFrames>=12){m_complex=false;emit policyChanged();}
        }
        m_lastFrame=now;
    },Qt::DirectConnection);
    emit policyChanged();
}
void MotionPolicy::setTransitioning(bool active) {
    m_transitioning=active; m_lastFrame=0;
}
void MotionPolicy::leavePage(QObject *page) {
    if(!page)return;
    for(auto *child:page->findChildren<QObject *>()) {
        if(child->property("opened").isValid() && child->metaObject()->indexOfMethod("close()")>=0)
            QMetaObject::invokeMethod(child,"close");
    }
}

int MotionPolicy::capture(QQuickItem *item,QJSValue callback) {
    if(!item || !callback.isCallable())return 0;
    auto grab=item->grabToImage();
    if(!grab)return 0;
    const int id=++m_nextGrab;
    m_grabs.insert(id,grab);emit grabsChanged();
    // Capture only the numeric handle in the ready connection. Capturing its
    // own QSharedPointer here would create a QObject/connection ownership cycle.
    connect(grab.data(),&QQuickItemGrabResult::ready,this,[this,id,callback]() mutable {
        const auto result=m_grabs.value(id);
        if(!result)return;
        callback.call({QJSValue(id),QJSValue(result->url().toString())});
    });
    return id;
}
void MotionPolicy::releaseGrab(int id) {
    const auto grab=m_grabs.take(id);
    if(grab){QTimer::singleShot(0,this,[grab]{});emit grabsChanged();}
}
