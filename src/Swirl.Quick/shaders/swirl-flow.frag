#version 440
layout(location=0) in vec2 qt_TexCoord0;
layout(location=0) out vec4 fragColor;
layout(std140,binding=0) uniform buf {
    mat4 qt_Matrix;
    float qt_Opacity;
    vec2 surfaceSize;
    float head;
    float pending;
    float energy;
    vec4 coldColor;
};
vec2 path(float t, float layer) {
    vec2 a=mix(vec2(.06,.80),vec2(.17,.95),layer);
    vec2 b=mix(vec2(.30,.80),vec2(.43,.95),layer);
    vec2 c=mix(vec2(.56,.10),vec2(.63,.35),layer);
    vec2 d=mix(vec2(.94,.20),vec2(.87,.43),layer);
    float s=1.-t;
    return (s*s*s*a+3.*s*s*t*b+3.*s*t*t*c+t*t*t*d)*surfaceSize;
}
vec4 ribbon(vec2 p,float layer) {
    // Two small fixed polylines give geometric distance and arc length. Colour
    // is indexed by measured path distance, not by rectangle x or UV phase.
    float total=0.;vec2 a=path(0.,layer);
    for(int i=1;i<=24;++i){vec2 b=path(float(i)/24.,layer);total+=length(b-a);a=b;}
    float best=1e6,at=0.,lengthSoFar=0.;a=path(0.,layer);
    for(int i=1;i<=24;++i){
        vec2 b=path(float(i)/24.,layer),ab=b-a;
        float len=length(ab),h=clamp(dot(p-a,ab)/max(.001,dot(ab,ab)),0.,1.);
        float distanceTo=length(p-a-h*ab);
        if(distanceTo<best){best=distanceTo;at=(lengthSoFar+h*len)/max(1.,total);}
        lengthSoFar+=len;a=b;
    }
    float phase=head-layer*.12;
    float delta=pending>.5?min(abs(at-phase),1.-abs(at-phase)):abs(at-phase);
    float light=exp(-delta*delta/0.012)*energy;
    vec3 warm=vec3(.961,.627,.302),blue=vec3(.157,.365,.827),green=vec3(.235,.667,.475);
    vec3 pigment=mix(warm,blue,smoothstep(.04,.31,at));
    pigment=mix(pigment,coldColor.rgb,smoothstep(.33,.70,at));
    pigment=mix(pigment,green,smoothstep(.80,1.,at));
    pigment=mix(coldColor.rgb,pigment,energy*.6);
    pigment=mix(pigment,vec3(.90,.98,1.),light*.72);
    float alpha=(1.-smoothstep(.8,1.65,best))*mix(.72,.40,layer);
    return vec4(pigment*alpha,alpha);
}
void main(){vec2 p=qt_TexCoord0*surfaceSize;vec4 back=ribbon(p,1.),front=ribbon(p,0.);fragColor=(front+back*(1.-front.a))*qt_Opacity;}
