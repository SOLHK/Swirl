#pragma once

#include <QEasingCurve>
#include <QElapsedTimer>
#include <QObject>
#include <QPointer>
#include <QQuickItem>
#include <QQuickWindow>
#include <QtQml/qqmlregistration.h>
#include <memory>
#include <optional>

struct SwirlPressRenderState;
class SwirlPressTransform;

// QML values advance on the GUI thread. Optional visual targets also use one
// native sample taken after the render loop's beginFrame wait, during sync.
// That sample only changes transform calculations, never QML properties.
class SwirlPressClock : public QObject {
    Q_OBJECT
    QML_ELEMENT
    Q_PROPERTY(QQuickWindow *window READ window WRITE setWindow NOTIFY windowChanged)
    Q_PROPERTY(qreal from READ from WRITE setFrom NOTIFY fromChanged)
    Q_PROPERTY(qreal to READ to WRITE setTo NOTIFY toChanged)
    Q_PROPERTY(int duration READ duration WRITE setDuration NOTIFY durationChanged)
    Q_PROPERTY(qreal value READ value NOTIFY valueChanged)
    Q_PROPERTY(bool running READ running NOTIFY runningChanged)
    Q_PROPERTY(QQuickItem *surfaceTarget READ surfaceTarget WRITE setSurfaceTarget NOTIFY surfaceTargetChanged)
    Q_PROPERTY(QQuickItem *contentTarget READ contentTarget WRITE setContentTarget NOTIFY contentTargetChanged)
    Q_PROPERTY(qreal minimumScale READ minimumScale WRITE setMinimumScale NOTIFY minimumScaleChanged)
public:
    explicit SwirlPressClock(QObject *parent = nullptr);
    ~SwirlPressClock() override;
    QQuickWindow *window() const { return m_window; }
    qreal from() const { return m_from; }
    qreal to() const { return m_to; }
    int duration() const { return m_duration; }
    qreal value() const { return m_value; }
    bool running() const { return m_running; }
    QQuickItem *surfaceTarget() const { return m_surfaceTarget; }
    QQuickItem *contentTarget() const { return m_contentTarget; }
    qreal minimumScale() const { return m_minimumScale; }
    void setWindow(QQuickWindow *window);
    void setFrom(qreal value);
    void setTo(qreal value);
    void setDuration(int value);
    void setSurfaceTarget(QQuickItem *item);
    void setContentTarget(QQuickItem *item);
    void setMinimumScale(qreal value);
    Q_INVOKABLE void start();
    Q_INVOKABLE void stop();
signals:
    void windowChanged();
    void fromChanged();
    void toChanged();
    void durationChanged();
    void valueChanged();
    void runningChanged();
    void surfaceTargetChanged();
    void contentTargetChanged();
    void minimumScaleChanged();
private:
    bool canAnimate() const;
    void connectFrames();
    void disconnectFrames();
    void advance();
    void setValue(qreal value);
    void stopInternal(bool restoreCommittedPose);
    void rebuildRenderTargets();
    void connectRenderFrames();
    void disconnectRenderFrames();
    void invalidateRenderTransforms();
    std::optional<qreal> committedVisualContact() const;
    QPointer<QQuickWindow> m_window;
    QMetaObject::Connection m_frameConnection, m_visibilityConnection, m_destroyedConnection;
    QMetaObject::Connection m_syncConnection, m_afterSyncConnection;
    QMetaObject::Connection m_surfaceDestroyedConnection, m_contentDestroyedConnection;
    QMetaObject::Connection m_surfaceWindowConnection, m_contentWindowConnection;
    QPointer<QQuickItem> m_surfaceTarget, m_contentTarget;
    QPointer<SwirlPressTransform> m_surfaceTransform, m_contentTransform;
    std::shared_ptr<SwirlPressRenderState> m_renderState;
    QElapsedTimer m_elapsed;
    QEasingCurve m_curve{QEasingCurve::OutExpo};
    qreal m_from = 0, m_to = 1, m_value = 0, m_start = 0, m_end = 1;
    qreal m_minimumScale = 0.98;
    int m_duration = 0, m_runDuration = 0;
    quint64 m_generation = 0;
    quint64 m_renderSetupRevision = 0;
    bool m_running = false;
};
