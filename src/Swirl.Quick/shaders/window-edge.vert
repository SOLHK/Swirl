#version 440
layout(location=0) in vec4 position;
layout(location=1) in vec2 corner;
layout(location=0) out vec2 localCorner;
layout(std140,binding=0) uniform buf {mat4 matrix;float radius;float dpr;};
void main(){localCorner=corner;gl_Position=matrix*position;}
