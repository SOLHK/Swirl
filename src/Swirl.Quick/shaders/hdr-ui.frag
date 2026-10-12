#version 440
layout(location=0) in vec2 qt_TexCoord0;
layout(location=0) out vec4 fragColor;
layout(std140,binding=0) uniform buf {
    mat4 qt_Matrix;
    float qt_Opacity;
    vec2 outputSize;
    float hdrActive;
    float whiteScale;
    float peakValue;
    float glowEnabled;
    vec4 redLamp;
    vec4 yellowLamp;
    vec4 greenLamp;
};
layout(binding=1) uniform sampler2D source;
vec3 srgbToLinear(vec3 c) {
    return mix(c/12.92,pow((c+0.055)/1.055,vec3(2.4)),step(vec3(0.04045),c));
}
float lampHighlight(vec2 p,vec4 lamp) {
    vec2 d=(p-lamp.xy)/max(lamp.z,0.001);
    float inside=1.0-smoothstep(0.80,1.0,length(d));
    return inside*exp(-12.0*dot(d+vec2(0.18,0.24),d+vec2(0.18,0.24)))*lamp.w;
}
void main() {
    vec4 c=texture(source,qt_TexCoord0);
    if(hdrActive<0.5 || c.a<0.0001) { fragColor=c*qt_Opacity;return; }
    // Root UI texture stays SDR. Convert straight sRGB once, then restore
    // premultiplied alpha in the *final FP16 swapchain pass*, avoiding RGBA8
    // intermediate targets that would clamp real HDR values back to 1.0.
    vec3 straight=c.rgb/c.a;
    vec3 linear=srgbToLinear(straight)*whiteScale;
    vec2 p=qt_TexCoord0*outputSize;
    float spot=max(lampHighlight(p,redLamp),max(lampHighlight(p,yellowLamp),lampHighlight(p,greenLamp)));
    float visibleColor=smoothstep(0.60,0.75,max(straight.r,max(straight.g,straight.b)));
    vec3 target=min(linear+vec3(whiteScale*1.6),vec3(peakValue));
    linear=mix(linear,target,clamp(spot*visibleColor*glowEnabled,0.0,1.0));
    fragColor=vec4(linear*c.a,c.a)*qt_Opacity;
}
