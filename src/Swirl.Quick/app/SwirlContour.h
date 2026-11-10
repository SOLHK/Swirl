#pragma once
#include <QtGlobal>
#include <algorithm>
#include <cmath>

// CPU counterpart of shaders/swirl-contour.glsl. The zero set is the same
// 2.5-power corner used by the window alpha mask and all visible surfaces.
namespace SwirlContour {
inline constexpr qreal power = 2.5;
inline qreal insetAtY(qreal radius, qreal distanceFromCenter) {
    return radius - std::pow(qMax<qreal>(0,
        std::pow(radius, power) - std::pow(distanceFromCenter, power)), 1 / power);
}
inline qreal distance(qreal x, qreal y, qreal width, qreal height, qreal radius) {
    radius = qBound<qreal>(0, radius, qMin(width, height) / 2);
    const qreal qx=std::abs(x-width/2)-width/2+radius;
    const qreal qy=std::abs(y-height/2)-height/2+radius;
    const qreal cx=qMax<qreal>(0,qx), cy=qMax<qreal>(0,qy);
    const qreal norm=std::pow(std::pow(cx,power)+std::pow(cy,power),1/power);
    const qreal gradient=norm>0.0001 ? std::hypot(std::pow(cx/norm,power-1),std::pow(cy/norm,power-1)) : 1;
    return (norm+qMin(qMax(qx,qy),qreal(0))-radius)/qMax(gradient,qreal(0.001));
}
}
