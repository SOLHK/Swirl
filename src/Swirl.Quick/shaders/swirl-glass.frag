#version 440
#extension GL_GOOGLE_include_directive : require
#include "swirl-contour.glsl"
layout(location=0) in vec2 qt_TexCoord0;
layout(location=0) out vec4 fragColor;
layout(std140,binding=0) uniform buf {
    mat4 qt_Matrix;
    float qt_Opacity;
    vec4 sampleRect;
    vec4 tint;
    float tintAmount;
    float surfaceOpacity;
    vec2 surfaceSize;
    float cornerRadius;
};
layout(binding=1) uniform sampler2D source;
void main() {
    vec2 uv=sampleRect.xy+qt_TexCoord0*sampleRect.zw;
    vec3 wallpaper=texture(source,clamp(uv,vec2(0),vec2(1))).rgb;
    vec3 shade=mix(wallpaper,tint.rgb,tintAmount);
    // One uniform pale-blue material. Preserve desktop alpha without a
    // second sidebar/workspace tint or decorative sheen.
    // Evaluate the continuous silhouette in the final material pass instead
    // of sampling a second whole-window mask (including all native text).
    float d=swirlSurfaceDistance((qt_TexCoord0-0.5)*surfaceSize,surfaceSize,cornerRadius);
    float coverage=swirlCoverage(d);
    float alpha=surfaceOpacity*coverage*qt_Opacity;
    fragColor=vec4(shade*alpha,alpha);
}
