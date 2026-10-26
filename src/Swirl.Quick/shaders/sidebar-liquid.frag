#version 440
layout(location=0) in vec2 qt_TexCoord0;
layout(location=0) out vec4 fragColor;
layout(std140,binding=0) uniform buf {
    mat4 qt_Matrix;
    float qt_Opacity;
    vec2 surfaceSize;
    vec2 textureExtent;
    float padding;
    float cornerRadius;
    float blurRadius;
    float refraction;
    float interaction;
    vec2 lightPoint;
    vec4 tintColor;
    float tintAmount;
    float darkMode;
};
layout(binding=1) uniform sampler2D source;
float distanceToSurface(vec2 p){
    float r=min(cornerRadius,min(surfaceSize.x,surfaceSize.y)*.5);
    vec2 q=abs(p-surfaceSize*.5)-surfaceSize*.5+r;
    vec2 c=max(q,vec2(0));
    return pow(pow(c.x,2.5)+pow(c.y,2.5),.4)+min(max(q.x,q.y),0.)-r;
}
vec4 sampleSafe(vec2 p){vec2 halfTexel=.5/max(textureExtent,vec2(1));return texture(source,clamp(p,halfTexel,1.-halfTexel));}
void main(){
    vec2 p=qt_TexCoord0*surfaceSize;
    float d=distanceToSurface(p),aa=max(.6,fwidth(d));
    float mask=1.-smoothstep(-aa,aa,d);
    if(mask<=0.){fragColor=vec4(0);return;}
    vec2 normal=normalize(vec2(distanceToSurface(p+vec2(.5,0))-distanceToSurface(p-vec2(.5,0)),distanceToSurface(p+vec2(0,.5))-distanceToSurface(p-vec2(0,.5)))+vec2(.00001));
    float edge=1.-smoothstep(0.,16.,max(0.,-d));
    vec2 extent=surfaceSize+2.*padding;
    // A padded capture prevents the refracted rim from sampling outside the
    // real app scene crop. Refraction is at most a few logical pixels.
    vec2 uv=(p+padding-normal*edge*edge*refraction*(1.+.3*interaction))/extent;
    // Horizontal Gaussian is prepared in one panel-sized texture. This
    // vertical pass also performs refraction, tint and rim lighting. Closely
    // spaced weighted taps avoid hard bands at high-contrast source edges.
    vec2 s=vec2(0.,blurRadius/4.)/extent;
    vec4 blur=sampleSafe(uv)*.227027;
    blur+=(sampleSafe(uv+s)+sampleSafe(uv-s))*.194595;
    blur+=(sampleSafe(uv+2.*s)+sampleSafe(uv-2.*s))*.121622;
    blur+=(sampleSafe(uv+3.*s)+sampleSafe(uv-3.*s))*.054054;
    blur+=(sampleSafe(uv+4.*s)+sampleSafe(uv-4.*s))*.016216;
    vec3 transmitted=blur.rgb/max(.001,blur.a);
    vec3 color=mix(transmitted,tintColor.rgb,tintAmount);
    float facing=max(0.,dot(normal,normalize(vec2(-.65,-1.))));
    float rim=exp(-max(0.,-d)*1.25)*facing;
    float localLight=exp(-dot((qt_TexCoord0-lightPoint)*vec2(1.,2.),(qt_TexCoord0-lightPoint)*vec2(1.,2.))*8.);
    // Directional highlights and a restrained opposite reflection, not a
    // uniform white outline. They move only with real interaction state.
    color+=vec3(.82,.94,1.)*rim*(.24+.24*interaction*localLight);
    color-=vec3(.08,.12,.18)*edge*edge*(1.-facing)*mix(.09,.20,darkMode);
    float alpha=mask*qt_Opacity;
    fragColor=vec4(clamp(color,0.,1.)*alpha,alpha);
}
