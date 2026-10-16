#version 440
layout(location=0) in vec2 localCorner;
layout(location=0) out vec4 color;
layout(std140,binding=0) uniform buf {mat4 matrix;float radius;float dpr;};
void main(){
 float distanceToEdge=length(max(vec2(radius)-localCorner,vec2(0)))-radius;
 float outside=smoothstep(-0.5/dpr,0.5/dpr,distanceToEdge);
 color=vec4(0,0,0,outside);
}
