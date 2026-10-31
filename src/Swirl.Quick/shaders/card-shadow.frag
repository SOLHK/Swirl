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
    float outside=1.0-swirlCoverage(edge);
    float d=max(distanceToSurface(p-shadowOffset),0.0)/max(softness,0.001);
    // Fade to a bottom contact shadow before reaching either side or corner.
    // There is no rectangular shadow patch in the card's cut-out corners.
    float bottom=smoothstep(surfaceSize.y*0.5-softness,surfaceSize.y*0.5+softness,p.y);
    float side=1.0-smoothstep(max(0.0,surfaceSize.x*0.5-cornerRadius),surfaceSize.x*0.5,abs(p.x));
    fragColor=shadowColor*(exp(-0.5*d*d)*outside*bottom*side*qt_Opacity);
}
