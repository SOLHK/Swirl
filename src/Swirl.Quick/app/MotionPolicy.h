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
#ifdef SWIRL_UI_TESTS
    // Process-local fixture injection; never changes the OS accessibility policy.
    void setSystemReducedMotionOverrideForTest(int policy);
#endif
    bool alwaysShowScrollbars() const;
    bool complexMotion() const { return m_complex.load(); }
    void attach(QQuickWindow *);
    Q_INVOKABLE void leavePage(QObject *);
    Q_INVOKABLE int capture(QQuickItem *, QJSValue callback);
    Q_INVOKABLE void releaseGrab(int id);
    int activeGrabCount() const { return m_grabs.size(); }
    Q_INVOKABLE void setTransitioning(bool);
    Q_INVOKABLE void finishPopup(QObject *popup);
    Q_INVOKABLE bool reversePopupExit(QObject *popup);
private:
    std::atomic_bool m_transitioning{false};
    QElapsedTimer m_clock;
    std::atomic<qint64> m_lastFrame{0};
    int m_slowFrames=0;
    std::atomic<double> m_budget{16.67};
    QMetaObject::Connection m_refreshSignal;
signals:
    void policyChanged();
    void grabsChanged();
private:
    std::atomic_bool m_complex{true};
#ifdef SWIRL_UI_TESTS
    int m_systemReducedMotionOverrideForTest=-1;
#endif
    int m_nextGrab=0;
    QHash<int,QSharedPointer<QQuickItemGrabResult>> m_grabs;
};
