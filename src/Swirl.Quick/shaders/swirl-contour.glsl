// One analytic 2.5-power contour for fill, rim, clipping and GPU shadows.
// Its curvature tends to zero at the eight straight/corner junctions.
float swirlCornerNorm(vec2 p) {
    return pow(pow(p.x, 2.5) + pow(p.y, 2.5), 0.4);
}
float swirlCornerDistance(vec2 q, float radius) {
    vec2 c = max(q, vec2(0));
    float n = swirlCornerNorm(c);
    float gradient = n > 0.0001 ? length(pow(c / n, vec2(1.5))) : 1.0;
    return (n + min(max(q.x, q.y), 0.0) - radius) / max(gradient, 0.001);
}
float swirlSurfaceDistance(vec2 p, vec2 size, float radius) {
    float r = clamp(radius, 0.0, min(size.x, size.y) * 0.5);
    return swirlCornerDistance(abs(p) - size * 0.5 + r, r);
}
// Area coverage across a square physical pixel. The same filter is used by
// the destination-out window edge and its rim, avoiding a second edge phase.
float swirlCoverage(float distanceToEdge) {
    vec2 footprint = abs(vec2(dFdx(distanceToEdge), dFdy(distanceToEdge)));
    float a = min(footprint.x, footprint.y);
    float b = max(max(footprint.x, footprint.y), 0.001);
    float t = distanceToEdge + 0.5 * (a + b);
    float outside;
    if (a < 0.001) outside = clamp(t / b, 0.0, 1.0);
    else if (t <= 0.0) outside = 0.0;
    else if (t >= a + b) outside = 1.0;
    else if (t < a) outside = t * t / (2.0 * a * b);
    else if (t < b) outside = (t - 0.5 * a) / b;
    else { float tail = a + b - t; outside = 1.0 - tail * tail / (2.0 * a * b); }
    return 1.0 - outside;
}
