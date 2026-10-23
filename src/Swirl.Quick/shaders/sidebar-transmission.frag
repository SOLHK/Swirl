#version 440
layout(location=0) in vec2 qt_TexCoord0;
layout(location=0) out vec4 fragColor;
layout(std140,binding=0) uniform buf {
    mat4 qt_Matrix;
    float qt_Opacity;
    vec2 surfaceSize;
    float cornerRadius;
    float inset;
};
void main() {
    vec2 uv=qt_TexCoord0;
    float r=min(cornerRadius,min(surfaceSize.x,surfaceSize.y)*0.5);
    vec2 q=abs((uv-0.5)*surfaceSize)-surfaceSize*0.5+r;
    vec2 corner=max(q,vec2(0));
    float distanceInside=-(pow(pow(corner.x,2.5)+pow(corner.y,2.5),0.4)+min(max(q.x,q.y),0.0)-r);
    // Leave the existing contour and exterior shadow completely untouched.
    float interior=smoothstep(inset,inset*4.0,distanceInside);
    float breadth=sin(uv.x*3.14159265);
    float depth=0.014+0.010*smoothstep(0.08,0.88,uv.y);
    // Neutral transmission loss only: no white tint, glint, or copied content.
    fragColor=vec4(0.0,0.0,0.0,depth*breadth*interior*qt_Opacity);
}
