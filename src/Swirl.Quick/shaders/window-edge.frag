#version 440
#extension GL_GOOGLE_include_directive : require
#include "swirl-contour.glsl"
layout(location=0) in vec2 localCorner;
layout(location=0) out vec4 color;
layout(std140,binding=0) uniform buf {mat4 matrix;float radius;float dpr;};
void main() {
    float distanceToEdge = swirlCornerDistance(vec2(radius) - localCorner, radius);
    color = vec4(0, 0, 0, 1.0 - swirlCoverage(distanceToEdge));
}
