#version 440
layout(location=0) in vec2 qt_TexCoord0;
layout(location=0) out vec4 fragColor;
layout(std140,binding=0) uniform buf {
    mat4 qt_Matrix;
    float qt_Opacity;
    vec2 surfaceSize;
    float cornerRadius;
};
layout(binding=1) uniform sampler2D source;
void main() {
    vec2 halfSize=surfaceSize*0.5;
    float r=clamp(cornerRadius,0.0,min(halfSize.x,halfSize.y));
    vec2 p=(qt_TexCoord0-0.5)*surfaceSize;
    vec2 q=abs(p)-halfSize+r;
    float d=length(max(q,vec2(0)))+min(max(q.x,q.y),0.0)-r;
    float aa=max(fwidth(d),0.001);
    float coverage=1.0-smoothstep(-aa,0.0,d);
    if(coverage<=0.0)discard;
    vec2 normal=p-clamp(p,-halfSize+r,halfSize-r);
    normal/=max(length(normal),0.001);
    // Mirror adjacent application content beneath the pane, with restrained
    // edge lensing. No independent tint, luminosity overlay or desktop source.
    vec2 uv=vec2(1.0-qt_TexCoord0.x,qt_TexCoord0.y);
    uv+=normal*vec2(-1.0,1.0)*(2.0*exp(-max(-d,0.0)/4.0))/surfaceSize;
    vec4 c=texture(source,clamp(uv,0.0,1.0));
    fragColor=c*(coverage*qt_Opacity);
}
