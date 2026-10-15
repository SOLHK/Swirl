#pragma once
#include <QString>
#include <QQuickWindow>
#include <QElapsedTimer>
#include <QMutex>
#include <QMutexLocker>
#include <QPointer>
#include <QVariant>
#include <QList>
#include <QRectF>
#include <atomic>
// Test-only receiver keeps QML reads on the GUI thread. The render-thread
// frame signal reads only atomics and a monotonic timer.
class SettingsFrameProbe final:public QObject {
    Q_OBJECT
public:
    struct Sample {QList<double> intervals;qreal firstFrameMs=-1;qreal firstReveal=-1;QRectF firstRect;};
    explicit SettingsFrameProbe(QQuickWindow *window):m_window(window){m_clock.start();}
    void begin(){QMutexLocker lock(&m_mutex);m_intervals.clear();m_first=0;m_previous=0;m_firstReveal=-1;m_firstRect={};m_request=m_clock.nsecsElapsed();m_collecting=true;}
    Sample finish(){m_collecting=false;QMutexLocker lock(&m_mutex);return {m_intervals,m_first?double(m_first-m_request)/1000000.0:-1,m_firstReveal,m_firstRect};}
    void frame(){if(!m_collecting.load()||!m_moving.load())return;const auto now=m_clock.nsecsElapsed();QMutexLocker lock(&m_mutex);if(!m_first){m_first=now;m_firstReveal=m_currentReveal;m_firstRect=m_currentRect;}if(m_previous)m_intervals.append(double(now-m_previous)/1000000.0);m_previous=now;}
public slots:
    void syncMoving(){m_moving=m_window&&m_window->property("moving").toBool();}
    void syncSurface(){if(!m_window)return;const auto reveal=m_window->property("reveal").toReal();const auto rect=m_window->property("surfaceRect").toRectF();QMutexLocker lock(&m_mutex);m_currentReveal=reveal;m_currentRect=rect;}
private:
    QPointer<QQuickWindow> m_window;
    QElapsedTimer m_clock;
    QMutex m_mutex;
    QList<double> m_intervals;
    qint64 m_request=0,m_first=0,m_previous=0;
    qreal m_currentReveal=0,m_firstReveal=-1;
    QRectF m_currentRect,m_firstRect;
    std::atomic_bool m_collecting=false,m_moving=false;
};
class EngineController;
int runHeroChecks(QQuickWindow *,EngineController *,const QString &);
