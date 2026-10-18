#include "FontDisplayContext.h"

#include <QEvent>
#include <QScreen>
#include <cmath>

FontDisplayContext::FontDisplayContext(QObject *parent)
    : QObject(parent), m_window(qobject_cast<QWindow *>(parent))
{
    if (!m_window)
        return;
    m_window->installEventFilter(this);
    connect(m_window, &QWindow::screenChanged, this, &FontDisplayContext::observeScreen);
    observeScreen();
}

FontDisplayContext *FontDisplayContext::qmlAttachedProperties(QObject *object)
{
    return new FontDisplayContext(object);
}

void FontDisplayContext::observeScreen()
{
    disconnect(m_logicalDpiConnection);
    disconnect(m_physicalDpiConnection);
    if (m_window && m_window->screen()) {
        auto *screen = m_window->screen();
        m_logicalDpiConnection = connect(screen, &QScreen::logicalDotsPerInchChanged,
                                        this, &FontDisplayContext::updateMetrics);
        m_physicalDpiConnection = connect(screen, &QScreen::physicalDotsPerInchChanged,
                                         this, &FontDisplayContext::updateMetrics);
    }
    updateMetrics();
}

void FontDisplayContext::updateMetrics()
{
    // Qt's point-to-pixel font conversion uses vertical logical DPI. DPR already
    // participates in rendering and must not multiply the requested point size.
    qreal dpi = m_window && m_window->screen() ? m_window->screen()->logicalDotsPerInchY() : 96.0;
    qreal dpr = m_window ? m_window->devicePixelRatio() : 1.0;
    if (!std::isfinite(dpi) || dpi <= 0) dpi = 96.0;
    if (!std::isfinite(dpr) || dpr <= 0) dpr = 1.0;
    if (qFuzzyCompare(dpi, m_logicalDpi) && qFuzzyCompare(dpr, m_devicePixelRatio))
        return;
    m_logicalDpi = dpi;
    m_devicePixelRatio = dpr;
    emit metricsChanged();
}

bool FontDisplayContext::eventFilter(QObject *watched, QEvent *event)
{
    if (watched == m_window && (event->type() == QEvent::DevicePixelRatioChange
                                || event->type() == QEvent::PlatformSurface))
        updateMetrics();
    return QObject::eventFilter(watched, event);
}
