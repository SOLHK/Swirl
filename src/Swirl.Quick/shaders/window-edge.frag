#version 440
layout(location=0) in vec2 localCorner;
layout(location=0) out vec4 color;
layout(std140,binding=0) uniform buf {mat4 matrix;float radius;float dpr;};
void main(){
 vec2 q=max(vec2(radius)-localCorner,vec2(0));
 float norm=pow(pow(q.x,2.5)+pow(q.y,2.5),0.4);
 float gradient=length(pow(q,vec2(1.5)))/max(pow(norm,1.5),0.001);
 float distanceToEdge=(norm-radius)/max(gradient,0.001);
 float outside=smoothstep(-0.5/dpr,0.5/dpr,distanceToEdge);
 color=vec4(0,0,0,outside);
}
