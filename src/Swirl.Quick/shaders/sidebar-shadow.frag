#version 440
#extension GL_GOOGLE_include_directive : require
#include "swirl-contour.glsl"
layout(location=0) in vec2 qt_TexCoord0;
layout(location=0) out vec4 fragColor;
layout(std140,binding=0) uniform buf {
    mat4 qt_Matrix;
    float qt_Opacity;
    vec2 surfaceSize;
    float padding;
    float cornerRadius;
    vec2 shadowOffset;
    float softness;
    vec4 shadowColor;
};
float distanceToSurface(vec2 p) { return swirlSurfaceDistance(p, surfaceSize, cornerRadius); }
void main() {
    vec2 p=(qt_TexCoord0-0.5)*(surfaceSize+2.0*padding);
    float edge=distanceToSurface(p);
    float aa=max(fwidth(edge),0.001);
    float outside=1.0-swirlCoverage(edge);
    float d=max(distanceToSurface(p-shadowOffset),0.0)/max(softness,0.001);
    // Exterior-only shadow: never darken the transparent pane's interior.
    fragColor=shadowColor*(exp(-0.5*d*d)*outside*qt_Opacity);
}
