#version 440
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
// Continuous 2.5-power contour, matching the software outline and shadow.
// Curvature approaches zero where each corner meets its straight edge.
void main() {
    float r=clamp(cornerRadius,0.0,min(surfaceSize.x,surfaceSize.y)*0.5);
    vec2 q=abs((qt_TexCoord0-0.5)*surfaceSize)-surfaceSize*0.5+r;
    vec2 k=max(q,vec2(0.0));
    float d=pow(pow(k.x,2.5)+pow(k.y,2.5),0.4)+min(max(q.x,q.y),0.0)-r;
    float aa=max(fwidth(d),0.001);
    float coverage=1.0-smoothstep(-aa,0.0,d);
    float edge=borderWidth>0.0?smoothstep(-borderWidth-aa,-borderWidth,d):0.0;
    fragColor=mix(fillColor,rimColor,edge)*coverage*qt_Opacity;
}
