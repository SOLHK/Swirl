#version 440
layout(location=0) in vec2 qt_TexCoord0;
layout(location=0) out vec4 fragColor;
layout(std140,binding=0) uniform buf {
    mat4 qt_Matrix;
    float qt_Opacity;
    vec2 surfaceSize;
    float cornerRadius;
    float pixelWidth;
    float interaction;
    vec2 lightPoint;
    vec4 highlightColor;
    vec4 reflectionColor;
};
float distanceToSurface(vec2 p) {
    float r=min(cornerRadius,min(surfaceSize.x,surfaceSize.y)*0.5);
    vec2 q=abs(p-surfaceSize*0.5)-surfaceSize*0.5+r;
    vec2 c=max(q,vec2(0));
    return pow(pow(c.x,2.5)+pow(c.y,2.5),0.4)+min(max(q.x,q.y),0.0)-r;
}
void main() {
    vec2 p=qt_TexCoord0*surfaceSize;
    float d=distanceToSurface(p);
    float aa=max(fwidth(d),0.001);
    // Only a one-physical-pixel bevel catches light. The pane interior is
    // exactly transparent, including while hovering, focusing or pressing.
    float rim=(1.0-smoothstep(pixelWidth*0.5,pixelWidth*1.15,abs(d+pixelWidth*0.5)))
        *(1.0-smoothstep(-aa,aa,d));
    if(rim<=0.0) { fragColor=vec4(0); return; }
    vec2 normal=normalize(vec2(distanceToSurface(p+vec2(0.5,0))-distanceToSurface(p-vec2(0.5,0)),
        distanceToSurface(p+vec2(0,0.5))-distanceToSurface(p-vec2(0,0.5)))+vec2(0.00001));
    float facing=max(0.0,dot(normal,normalize(vec2(-0.65,-1.0))));
    vec2 lightDelta=(p-lightPoint*surfaceSize)/max(4.0*cornerRadius,1.0);
    float localLight=interaction*exp(-dot(lightDelta,lightDelta)*2.0);
    float highlight=rim*(0.10+0.22*facing+0.16*localLight)*highlightColor.a;
    float reflection=rim*(1.0-facing)*0.055*reflectionColor.a;
    vec4 color=vec4(highlightColor.rgb*highlight,highlight);
    color+=vec4(reflectionColor.rgb*reflection,reflection)*(1.0-color.a);
    fragColor=color*qt_Opacity;
}
