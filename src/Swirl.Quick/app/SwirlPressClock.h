#pragma once

#include <QEasingCurve>
#include <QElapsedTimer>
#include <QObject>
#include <QPointer>
#include <QQuickWindow>
#include <QtQml/qqmlregistration.h>

// Sample a press on the GUI thread immediately before scene-graph sync. Qt's
// regular animation driver advances after sync in the single-window threaded
// render loop; afterAnimating is the public GUI-thread sync boundary in all modes.
class SwirlPressClock : public QObject {
    Q_OBJECT
    QML_ELEMENT
    Q_PROPERTY(QQuickWindow *window READ window WRITE setWindow NOTIFY windowChanged)
    Q_PROPERTY(qreal from READ from WRITE setFrom NOTIFY fromChanged)
    Q_PROPERTY(qreal to READ to WRITE setTo NOTIFY toChanged)
    Q_PROPERTY(int duration READ duration WRITE setDuration NOTIFY durationChanged)
    Q_PROPERTY(qreal value READ value NOTIFY valueChanged)
    Q_PROPERTY(bool running READ running NOTIFY runningChanged)
public:
    explicit SwirlPressClock(QObject *parent = nullptr);
    ~SwirlPressClock() override;
    QQuickWindow *window() const { return m_window; }
    qreal from() const { return m_from; }
    qreal to() const { return m_to; }
    int duration() const { return m_duration; }
    qreal value() const { return m_value; }
    bool running() const { return m_running; }
    void setWindow(QQuickWindow *window);
    void setFrom(qreal value);
    void setTo(qreal value);
    void setDuration(int value);
    Q_INVOKABLE void start();
    Q_INVOKABLE void stop();
signals:
    void windowChanged();
    void fromChanged();
    void toChanged();
    void durationChanged();
    void valueChanged();
    void runningChanged();
private:
    bool canAnimate() const;
    void connectFrames();
    void disconnectFrames();
    void advance();
    void setValue(qreal value);
    QPointer<QQuickWindow> m_window;
    QMetaObject::Connection m_frameConnection, m_visibilityConnection, m_destroyedConnection;
    QElapsedTimer m_elapsed;
    QEasingCurve m_curve{QEasingCurve::OutExpo};
    qreal m_from = 0, m_to = 1, m_value = 0, m_start = 0, m_end = 1;
    int m_duration = 0, m_runDuration = 0;
    quint64 m_generation = 0;
    bool m_running = false;
};
