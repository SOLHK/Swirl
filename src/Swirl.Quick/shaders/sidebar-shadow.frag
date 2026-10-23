#version 440
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
float distanceToSurface(vec2 p) {
    float r=min(cornerRadius,min(surfaceSize.x,surfaceSize.y)*0.5);
    vec2 q=abs(p)-surfaceSize*0.5+r;
    return length(max(q,vec2(0)))+min(max(q.x,q.y),0.0)-r;
}
void main() {
    vec2 p=(qt_TexCoord0-0.5)*(surfaceSize+2.0*padding);
    float edge=distanceToSurface(p);
    float aa=max(fwidth(edge),0.001);
    float outside=smoothstep(-aa,aa,edge);
    float d=max(distanceToSurface(p-shadowOffset),0.0)/max(softness,0.001);
    // Exterior-only shadow: never darken the transparent pane's interior.
    fragColor=shadowColor*(exp(-0.5*d*d)*outside*qt_Opacity);
}
