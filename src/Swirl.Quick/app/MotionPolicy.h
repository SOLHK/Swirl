#pragma once
#include <QObject>
#include <atomic>
#include <QElapsedTimer>
#include <QJSValue>
#include <QHash>
#include <QSharedPointer>
#include <QQuickItemGrabResult>
class QQuickItem;
class QQuickWindow;
class MotionPolicy final : public QObject {
    Q_OBJECT
    Q_PROPERTY(bool systemReducedMotion READ systemReducedMotion NOTIFY policyChanged)
    Q_PROPERTY(bool alwaysShowScrollbars READ alwaysShowScrollbars NOTIFY policyChanged)
    Q_PROPERTY(bool complexMotion READ complexMotion NOTIFY policyChanged)
    Q_PROPERTY(int activeGrabCount READ activeGrabCount NOTIFY grabsChanged)
public:
    explicit MotionPolicy(QObject *parent=nullptr);
    bool systemReducedMotion() const;
    bool alwaysShowScrollbars() const;
    bool complexMotion() const { return m_complex.load(); }
    void attach(QQuickWindow *);
    Q_INVOKABLE void leavePage(QObject *);
    Q_INVOKABLE int capture(QQuickItem *, QJSValue callback);
    Q_INVOKABLE void releaseGrab(int id);
    int activeGrabCount() const { return m_grabs.size(); }
    Q_INVOKABLE void setTransitioning(bool);
private:
    std::atomic_bool m_transitioning{false};
    QElapsedTimer m_clock;
    std::atomic<qint64> m_lastFrame{0};
    int m_slowFrames=0;
    std::atomic<double> m_budget{16.67};
signals:
    void policyChanged();
    void grabsChanged();
private:
    std::atomic_bool m_complex{true};
    int m_nextGrab=0;
    QHash<int,QSharedPointer<QQuickItemGrabResult>> m_grabs;
};
