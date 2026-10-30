#include "SwirlPressClock.h"

#include <algorithm>
#include <cmath>

SwirlPressClock::SwirlPressClock(QObject *parent) : QObject(parent) {}
SwirlPressClock::~SwirlPressClock() {
    disconnectFrames();
    disconnect(m_destroyedConnection);
}

bool SwirlPressClock::canAnimate() const {
    return m_window && m_window->isVisible() && m_window->visibility() != QWindow::Minimized;
}

void SwirlPressClock::setWindow(QQuickWindow *window) {
    if (m_window == window) return;
    const QPointer<SwirlPressClock> guard(this);
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
    if (m_running) {
        if (canAnimate()) {
            // Reparenting keeps the same monotonic interval and current value.
            connectFrames();
            m_window->update();
        } else stop();
    }
    if (guard && m_window == window) emit windowChanged();
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
        if (guard && generation == m_generation) stop();
        return;
    }
    connectFrames();
    if (m_window) m_window->update();
}

void SwirlPressClock::stop() {
    ++m_generation;
    disconnectFrames();
    if (!m_running) return;
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
}

void SwirlPressClock::disconnectFrames() {
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
    if (progress == 1) stop();
    else if (m_window) m_window->update();
}
