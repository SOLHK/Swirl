#version 440
layout(location=0) in vec2 qt_TexCoord0;
layout(location=0) out vec4 fragColor;
layout(std140,binding=0) uniform buf {
    mat4 qt_Matrix;
    float qt_Opacity;
    vec2 stepSize;
    float upscale;
};
layout(binding=1) uniform sampler2D source;
void main() {
    vec2 p=qt_TexCoord0;
    vec2 s=stepSize;
    vec4 value;
    if(upscale>1.5 && upscale<2.5) {
        value=texture(source,p)*0.227027;
        value+=(texture(source,p+s)+texture(source,p-s))*0.194595;
        value+=(texture(source,p+2.0*s)+texture(source,p-2.0*s))*0.121622;
        value+=(texture(source,p+3.0*s)+texture(source,p-3.0*s))*0.054054;
        value+=(texture(source,p+4.0*s)+texture(source,p-4.0*s))*0.016216;
    } else if(upscale>2.5) {
        value=(texture(source,p+s)+texture(source,p-s)+texture(source,p+vec2(s.x,-s.y))+texture(source,p+vec2(-s.x,s.y)))*0.25;
    } else if(upscale<0.5) {
        value=texture(source,p)*4.0;
        value+=texture(source,p+s)+texture(source,p-s);
        value+=texture(source,p+vec2(s.x,-s.y))+texture(source,p+vec2(-s.x,s.y));
        value/=8.0;
    } else {
        value=texture(source,p+vec2(-2.0*s.x,0))+texture(source,p+vec2(2.0*s.x,0));
        value+=texture(source,p+vec2(0,-2.0*s.y))+texture(source,p+vec2(0,2.0*s.y));
        value+=2.0*(texture(source,p+s)+texture(source,p-s)+texture(source,p+vec2(s.x,-s.y))+texture(source,p+vec2(-s.x,s.y)));
        value/=12.0;
    }
    fragColor=value*qt_Opacity;
}
