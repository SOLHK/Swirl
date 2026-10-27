#pragma once
#include <QImage>
#include <QSize>

// GUI-thread renderer. The two small kernels retain the same alpha function
// for active/inactive windows; resizing only stretches its constant edge runs.
class WindowShadowRenderer final {
public:
    QImage render(QSize body, qreal radius, qreal dpr, bool active);
    quint64 kernelBuildCount() const { return m_kernelBuildCount; }
private:
    QImage m_activeKernel, m_inactiveKernel;
    qreal m_radius = -1, m_dpr = -1;
    quint64 m_kernelBuildCount = 0;
};
