#include "WindowShadowRenderer.h"
#include "SwirlContour.h"
#include <QtMath>
#include <algorithm>
#include <cmath>
#include <cstring>
#include <limits>

namespace {
QImage analyticImage(QSize body, qreal radius, qreal dpr, bool active) {
    const int padding = qCeil(20 * dpr);
    const qreal sigma = 6 * dpr, offset = 2.5 * dpr;
    const qreal strength = active ? 0.22 : 0.14;
    QImage image(body + QSize(padding * 2, padding * 2), QImage::Format_ARGB32_Premultiplied);
    if (image.isNull()) return {};
    image.fill(Qt::transparent);
    for (int y = 0; y < image.height(); ++y) {
        auto *row = reinterpret_cast<QRgb *>(image.scanLine(y));
        const qreal localY = y + 0.5 - padding;
        int clearLeft = image.width(), clearRight = image.width();
        if (localY >= 0 && localY < body.height()) {
            const qreal dy = qMax<qreal>(0, qMax(radius - localY, localY - (body.height() - radius)));
            const qreal inset = SwirlContour::insetAtY(radius, dy);
            clearLeft = padding + qMax(0, qCeil(inset + 0.5));
            clearRight = padding + body.width() - qMax(0, qCeil(inset + 0.5));
        }
        for (int x = 0; x < image.width(); ++x) {
            if (x == clearLeft && clearRight > clearLeft) { x = clearRight; if (x >= image.width()) break; }
            const qreal localX = x + 0.5 - padding;
            if (localX >= radius && localX < body.width() - radius && localY >= 0 && localY < body.height()) continue;
            if (localY >= radius && localY < body.height() - radius && localX >= 0 && localX < body.width()) continue;
            const qreal edge = SwirlContour::distance(localX, localY, body.width(), body.height(), radius);
            if (edge <= -0.5) continue;
            const qreal t = qBound<qreal>(0, edge + 0.5, 1);
            const qreal coverage = t * t * (3 - 2 * t);
            const qreal distance = qMax<qreal>(0, SwirlContour::distance(localX, localY - offset, body.width(), body.height(), radius));
            row[x] = qRgba(0, 0, 0, qRound(255 * strength * coverage * std::exp(-distance * distance / (2 * sigma * sigma))));
        }
    }
    return image;
}
}

QImage WindowShadowRenderer::render(QSize body, qreal radius, qreal dpr, bool active) {
    if (body.isEmpty() || !std::isfinite(radius) || radius < 0 || !std::isfinite(dpr) || dpr <= 0) return {};
    const qreal paddingValue = std::ceil(20 * dpr);
    const qreal horizontalValue = std::ceil(radius), verticalValue = std::ceil(radius + 2.5 * dpr);
    const auto maximum = (std::numeric_limits<int>::max)();
    if (paddingValue > maximum / 4 || horizontalValue > maximum / 4 || verticalValue > maximum / 4) return {};
    const int padding = int(paddingValue), horizontal = int(horizontalValue), vertical = int(verticalValue);
    if (body.width() > maximum - 2 * padding || body.height() > maximum - 2 * padding) return {};
    const QSize kernelBody(2 * horizontal + 1, 2 * vertical + 1);
    if (body.width() < kernelBody.width() || body.height() < kernelBody.height()) return analyticImage(body, radius, dpr, active);
    if (m_radius != radius || m_dpr != dpr) {
        m_radius = radius; m_dpr = dpr;
        m_activeKernel = {}; m_inactiveKernel = {};
    }
    auto &kernel = active ? m_activeKernel : m_inactiveKernel;
    if (kernel.isNull()) {
        kernel = analyticImage(kernelBody, radius, dpr, active);
        if (kernel.isNull()) return {};
        ++m_kernelBuildCount;
    }
    QImage image(body + QSize(2 * padding, 2 * padding), QImage::Format_ARGB32_Premultiplied);
    if (image.isNull()) return {};
    const int left = padding + horizontal, top = padding + vertical;
    const int middleEnd = image.width() - left;
    for (int y = 0; y < image.height(); ++y) {
        const int sourceY = y < top ? y : y >= image.height() - top ? kernel.height() - (image.height() - y) : top;
        const auto *source = reinterpret_cast<const QRgb *>(kernel.constScanLine(sourceY));
        auto *target = reinterpret_cast<QRgb *>(image.scanLine(y));
        std::memcpy(target, source, size_t(left) * sizeof(QRgb));
        std::fill(target + left, target + middleEnd, source[left]);
        std::memcpy(target + middleEnd, source + left + 1, size_t(left) * sizeof(QRgb));
    }
    return image;
}
