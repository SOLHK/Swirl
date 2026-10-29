#version 440
layout(location=0) in vec2 qt_TexCoord0;
layout(location=0) out vec4 fragColor;
layout(std140,binding=0) uniform buf {
    mat4 qt_Matrix;
    float qt_Opacity;
    vec2 surfaceSize;
    vec4 glassRect;
    float cornerRadius;
    float glassActive;
};
layout(binding=1) uniform sampler2D source;
void main(){
    vec2 p=qt_TexCoord0*surfaceSize-glassRect.xy-glassRect.zw*.5;
    float r=min(cornerRadius,min(glassRect.z,glassRect.w)*.5);
    vec2 q=abs(p)-glassRect.zw*.5+r,c=max(q,vec2(0));
    float d=pow(pow(c.x,2.5)+pow(c.y,2.5),.4)+min(max(q.x,q.y),0.)-r;
    float outside=smoothstep(-max(.6,fwidth(d)),max(.6,fwidth(d)),d);
    fragColor=texture(source,qt_TexCoord0)*mix(1.,outside,glassActive)*qt_Opacity;
}
