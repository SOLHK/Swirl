#version 440
#extension GL_GOOGLE_include_directive : require
#include "swirl-contour.glsl"
layout(location=0) in vec2 qt_TexCoord0;
layout(location=0) out vec4 fragColor;
layout(std140,binding=0) uniform buf {
    mat4 qt_Matrix;
    float qt_Opacity;
    vec2 surfaceSize;
    float cornerRadius;
    float borderWidth;
    vec4 fillColor;
    vec4 rimColor;
};
void main() {
    float d = swirlSurfaceDistance((qt_TexCoord0 - 0.5) * surfaceSize, surfaceSize, cornerRadius);
    float coverage = swirlCoverage(d);
    float inner = borderWidth > 0.0 ? swirlCoverage(d + borderWidth) : coverage;
    fragColor = (fillColor * inner + rimColor * (coverage - inner)) * qt_Opacity;
}
