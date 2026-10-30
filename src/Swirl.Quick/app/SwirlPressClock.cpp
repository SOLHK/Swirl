#include "SwirlPressClock.h"

#include <QMatrix4x4>
#include <QMutex>
#include <QMutexLocker>
#include <QThread>
#include <algorithm>
#include <cmath>

struct SwirlPressRenderState {
    QMutex mutex;
    QElapsedTimer elapsed;
    QEasingCurve curve{QEasingCurve::OutExpo};
    qreal from=0,to=1,minimumScale=0.98,sampledContact=0,committedContact=0;
    int duration=0;
    quint64 generation=0,frameSerial=0,syncGeneration=0,committedFrame=0;
    unsigned appliedTargets=0;
    Qt::HANDLE syncThread=nullptr;
    bool armed=false,synchronizing=false;
};

class SwirlPressTransform final : public QQuickTransform {
public:
    SwirlPressTransform(std::shared_ptr<SwirlPressRenderState> state,QQuickItem *item,
                        unsigned targetBit,QObject *owner)
        :QQuickTransform(owner),m_state(std::move(state)),m_item(item),m_targetBit(targetBit) {
        // Qt applies the transform list in reverse order before its native
        // scale/rotation. Put this correction next to that native scale, while
        // retaining every pre-existing translation/rotation and its order.
        prependToItem(item);
    }
    void invalidateOnGui() {
        Q_ASSERT(QThread::currentThread()==thread());
        update();
    }
    void applyTo(QMatrix4x4 *matrix) const override {
        qreal contact,minimumScale;
        quint64 generation,serial;
        bool synchronizedSample;
        {
            QMutexLocker lock(&m_state->mutex);
            if(!m_state->armed)return;
            synchronizedSample=m_state->synchronizing&&m_state->syncThread==QThread::currentThreadId();
            contact=synchronizedSample?m_state->sampledContact:m_state->committedContact;
            minimumScale=m_state->minimumScale;
            generation=m_state->generation;serial=m_state->frameSerial;
        }
        // Qt invokes this while building item transforms. During render sync
        // the GUI thread is blocked. Outside sync these are ordinary GUI reads.
        // Do not write QObject/QML properties or emit signals here.
        const auto *item=m_item.data();
        if(!item)return;
        const qreal base=item->scale();
        if(!std::isfinite(base)||base==0)return;
        const qreal ratio=(1-(1-minimumScale)*contact)/base;
        const QPointF origin=item->transformOriginPoint();
        if(!std::isfinite(ratio)||!std::isfinite(origin.x())||!std::isfinite(origin.y()))return;
        matrix->translate(origin.x(),origin.y());
        matrix->scale(ratio,ratio);
        matrix->translate(-origin.x(),-origin.y());
        if(synchronizedSample){
            QMutexLocker lock(&m_state->mutex);
            if(m_state->armed&&m_state->synchronizing&&m_state->generation==generation
                &&m_state->syncGeneration==generation&&m_state->frameSerial==serial)
                m_state->appliedTargets|=m_targetBit;
        }
    }
private:
    const std::shared_ptr<SwirlPressRenderState> m_state;
    QPointer<QQuickItem> m_item;
    const unsigned m_targetBit;
};

SwirlPressClock::SwirlPressClock(QObject *parent)
    : QObject(parent),m_renderState(std::make_shared<SwirlPressRenderState>()) {}
SwirlPressClock::~SwirlPressClock() {
    disconnectFrames();
    disconnect(m_destroyedConnection);
    disconnect(m_surfaceDestroyedConnection);disconnect(m_contentDestroyedConnection);
    disconnect(m_surfaceWindowConnection);disconnect(m_contentWindowConnection);
    delete m_surfaceTransform.data();delete m_contentTransform.data();
}

bool SwirlPressClock::canAnimate() const {
    return m_window && m_window->isVisible() && m_window->visibility() != QWindow::Minimized;
}

void SwirlPressClock::setWindow(QQuickWindow *window) {
    if (m_window == window) return;
    const QPointer<SwirlPressClock> guard(this);
    const auto visual=committedVisualContact();
    disconnectFrames();
    disconnect(m_destroyedConnection);
    m_destroyedConnection = {};
    m_window = window;
    if (m_window) {
        // Keep the property notification alive even when no animation runs.
        // This connection does not request frames or run a timer.
        m_destroyedConnection = connect(m_window, &QObject::destroyed, this, [this] {
            const QPointer<SwirlPressClock> guard(this);
            m_window = nullptr;
            stop();
            if (guard && !m_window) emit windowChanged();
        });
    }
    if(visual&&m_running)setValue(*visual);
    if(!guard||m_window!=window)return;
    rebuildRenderTargets();
    if(!guard||m_window!=window)return;
    if (m_running) {
        if (canAnimate()) {
            // Reparenting keeps the same monotonic interval and current value.
            connectFrames();
            m_window->update();
        } else stop();
    }
    if (guard && m_window == window) emit windowChanged();
}

void SwirlPressClock::setSurfaceTarget(QQuickItem *item) {
    if(m_surfaceTarget==item)return;
    const QPointer<SwirlPressClock> guard(this);
    disconnect(m_surfaceDestroyedConnection);disconnect(m_surfaceWindowConnection);
    m_surfaceTarget=item;
    if(item){
        m_surfaceDestroyedConnection=connect(item,&QObject::destroyed,this,[this]{
            const QPointer<SwirlPressClock> guard(this);rebuildRenderTargets();
            if(guard)emit surfaceTargetChanged();
        });
        m_surfaceWindowConnection=connect(item,&QQuickItem::windowChanged,this,[this]{rebuildRenderTargets();});
    }
    rebuildRenderTargets();
    if(guard&&m_surfaceTarget==item)emit surfaceTargetChanged();
}

void SwirlPressClock::setContentTarget(QQuickItem *item) {
    if(m_contentTarget==item)return;
    const QPointer<SwirlPressClock> guard(this);
    disconnect(m_contentDestroyedConnection);disconnect(m_contentWindowConnection);
    m_contentTarget=item;
    if(item){
        m_contentDestroyedConnection=connect(item,&QObject::destroyed,this,[this]{
            const QPointer<SwirlPressClock> guard(this);rebuildRenderTargets();
            if(guard)emit contentTargetChanged();
        });
        m_contentWindowConnection=connect(item,&QQuickItem::windowChanged,this,[this]{rebuildRenderTargets();});
    }
    rebuildRenderTargets();
    if(guard&&m_contentTarget==item)emit contentTargetChanged();
}

void SwirlPressClock::setMinimumScale(qreal value) {
    if(!std::isfinite(value)||value<=0||m_minimumScale==value)return;
    m_minimumScale=value;
    {
        QMutexLocker lock(&m_renderState->mutex);
        m_renderState->minimumScale=value;
        ++m_renderState->generation;m_renderState->synchronizing=false;
    }
    invalidateRenderTransforms();
    emit minimumScaleChanged();
}

std::optional<qreal> SwirlPressClock::committedVisualContact() const {
    QMutexLocker lock(&m_renderState->mutex);
    if(!m_renderState->armed)return std::nullopt;
    return m_renderState->committedContact;
}

void SwirlPressClock::invalidateRenderTransforms() {
    if(m_surfaceTransform)m_surfaceTransform->invalidateOnGui();
    if(m_contentTransform)m_contentTransform->invalidateOnGui();
}

void SwirlPressClock::rebuildRenderTargets() {
    const auto revision=++m_renderSetupRevision;
    const QPointer<SwirlPressClock> guard(this);
    const auto visual=committedVisualContact();
    disconnectRenderFrames();
    delete m_surfaceTransform.data();delete m_contentTransform.data();
    if(visual&&m_running)setValue(*visual);
    if(!guard||revision!=m_renderSetupRevision)return;
    if(m_window&&m_surfaceTarget&&m_contentTarget&&m_surfaceTarget!=m_contentTarget
        &&m_surfaceTarget->window()==m_window&&m_contentTarget->window()==m_window){
        m_surfaceTransform=new SwirlPressTransform(m_renderState,m_surfaceTarget,1,this);
        m_contentTransform=new SwirlPressTransform(m_renderState,m_contentTarget,2,this);
    }
    if(m_running)connectRenderFrames();
}

void SwirlPressClock::connectRenderFrames() {
    disconnectRenderFrames();
    if(!m_running||!m_window||!m_surfaceTransform||!m_contentTransform||m_runDuration<=0)return;
    const auto state=m_renderState;
    {
        QMutexLocker lock(&state->mutex);
        state->elapsed=m_elapsed;state->from=m_start;state->to=m_end;state->duration=m_runDuration;
        state->minimumScale=m_minimumScale;
        // Before the first sync, preserve the already-visible GUI pose. A
        // release must not hand off an unsynchronized, hypothetical sample.
        state->sampledContact=m_value;state->committedContact=m_value;state->committedFrame=0;
        state->armed=true;state->synchronizing=false;state->appliedTargets=0;++state->generation;
    }
    m_syncConnection=connect(m_window,&QQuickWindow::beforeSynchronizing,this,[state]{
        QMutexLocker lock(&state->mutex);
        if(!state->armed)return;
        const qreal progress=std::min(qreal(1),qreal(state->elapsed.nsecsElapsed())/(qreal(state->duration)*1000000));
        state->sampledContact=state->from+(state->to-state->from)*state->curve.valueForProgress(progress);
        state->syncGeneration=state->generation;++state->frameSerial;state->appliedTargets=0;
        state->syncThread=QThread::currentThreadId();state->synchronizing=true;
    },Qt::DirectConnection);
    m_afterSyncConnection=connect(m_window,&QQuickWindow::afterSynchronizing,this,[state]{
        QMutexLocker lock(&state->mutex);
        // GUI invalidation dirties both real target transforms every active
        // frame. Commit only when both consumed this generation's sync sample.
        // This is scene-graph adoption, not frameSwapped or physical scan-out.
        if(state->armed&&state->synchronizing&&state->syncGeneration==state->generation
            &&state->appliedTargets==3){
            state->committedContact=state->sampledContact;state->committedFrame=state->frameSerial;
        }
        state->synchronizing=false;
    },Qt::DirectConnection);
}

void SwirlPressClock::disconnectRenderFrames() {
    bool wasArmed;
    {
        QMutexLocker lock(&m_renderState->mutex);
        wasArmed=m_renderState->armed;m_renderState->armed=false;m_renderState->synchronizing=false;
        ++m_renderState->generation;
    }
    disconnect(m_syncConnection);disconnect(m_afterSyncConnection);
    m_syncConnection={};m_afterSyncConnection={};
    if(wasArmed)invalidateRenderTransforms();
}

void SwirlPressClock::setFrom(qreal value) {
    if (!std::isfinite(value) || m_from == value) return;
    m_from = value;
    emit fromChanged();
}

void SwirlPressClock::setTo(qreal value) {
    if (!std::isfinite(value) || m_to == value) return;
    m_to = value;
    emit toChanged();
}

void SwirlPressClock::setDuration(int value) {
    value = std::max(0, value);
    if (m_duration == value) return;
    m_duration = value;
    emit durationChanged();
}

void SwirlPressClock::setValue(qreal value) {
    if (m_value == value) return;
    m_value = value;
    emit valueChanged();
}

void SwirlPressClock::start() {
    if (m_running) return;
    const quint64 generation = ++m_generation;
    const QPointer<SwirlPressClock> guard(this);
    m_start = m_from;
    m_end = m_to;
    m_runDuration = m_duration;
    m_elapsed.start();
    m_running = true;
    emit runningChanged();
    if (!guard || generation != m_generation || !m_running) return;
    setValue(m_start);
    if (!guard || generation != m_generation || !m_running) return;
    if (!canAnimate() || m_runDuration == 0 || m_start == m_end) {
        setValue(m_end);
        if (guard && generation == m_generation) stopInternal(false);
        return;
    }
    connectFrames();
    if (m_window) m_window->update();
}

void SwirlPressClock::stop() {
    stopInternal(true);
}

void SwirlPressClock::stopInternal(bool restoreCommittedPose) {
    const quint64 generation=++m_generation;
    const QPointer<SwirlPressClock> guard(this);
    const auto visual=restoreCommittedPose&&m_running?committedVisualContact():std::nullopt;
    disconnectFrames();
    if (!m_running) return;
    if(visual)setValue(*visual);
    if(!guard||generation!=m_generation||!m_running)return;
    m_running = false;
    emit runningChanged();
}

void SwirlPressClock::connectFrames() {
    disconnectFrames();
    if (!m_window) return;
    // afterAnimating is a GUI-thread signal, before sync. No QML or Item
    // properties are written from beforeSynchronizing or the render thread.
    m_frameConnection = connect(m_window, &QQuickWindow::afterAnimating,
                                this, &SwirlPressClock::advance);
    m_visibilityConnection = connect(m_window, &QWindow::visibilityChanged,
        this, [this] { if (!canAnimate()) stop(); });
    connectRenderFrames();
}

void SwirlPressClock::disconnectFrames() {
    disconnectRenderFrames();
    disconnect(m_frameConnection);
    disconnect(m_visibilityConnection);
    m_frameConnection = {};
    m_visibilityConnection = {};
}

void SwirlPressClock::advance() {
    if (!m_running) return;
    if (!canAnimate()) { stop(); return; }
    const qreal progress = std::min(qreal(1),
        qreal(m_elapsed.nsecsElapsed()) / (qreal(m_runDuration) * 1000000));
    const quint64 generation = m_generation;
    const QPointer<SwirlPressClock> guard(this);
    setValue(m_start + (m_end - m_start) * m_curve.valueForProgress(progress));
    if (!guard || generation != m_generation || !m_running) return;
    // Natural completion keeps the exact endpoint. Only interruption/release
    // restores the last pose actually adopted by the scene graph.
    if (progress == 1) stopInternal(false);
    else {
        invalidateRenderTransforms();
        if (m_window) m_window->update();
    }
}
