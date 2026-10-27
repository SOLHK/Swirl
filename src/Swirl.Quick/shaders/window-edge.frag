#version 440
layout(location=0) in vec2 localCorner;
layout(location=0) out vec4 color;
layout(std140,binding=0) uniform buf {mat4 matrix;float radius;float dpr;};
void main(){
 vec2 q=max(vec2(radius)-localCorner,vec2(0));
 float norm=pow(pow(q.x,2.5)+pow(q.y,2.5),0.4);
 vec2 derivative=pow(q,vec2(1.5))/max(pow(norm,1.5),0.001);
 float gradient=max(length(derivative),0.001);
 float distanceToEdge=(norm-radius)/gradient;
 // Integrate the local edge across one square physical pixel. A fixed
 // smoothstep in normal-distance space under-covers diagonal pixel footprints.
 vec2 footprint=derivative/(gradient*dpr);
 float a=min(footprint.x,footprint.y),b=max(max(footprint.x,footprint.y),0.001);
 float t=distanceToEdge+0.5*(a+b);
 float outside;
 if(a<0.001)outside=clamp(t/b,0.0,1.0);
 else if(t<=0.0)outside=0.0;
 else if(t>=a+b)outside=1.0;
 else if(t<a)outside=t*t/(2.0*a*b);
 else if(t<b)outside=(t-0.5*a)/b;
 else {float tail=a+b-t;outside=1.0-tail*tail/(2.0*a*b);}
 color=vec4(0,0,0,outside);
}
