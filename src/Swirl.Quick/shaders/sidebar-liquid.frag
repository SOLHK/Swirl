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
    float darkMode;
};
layout(binding=1) uniform sampler2D source;
layout(binding=2) uniform sampler2D sharpSource;
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
    // Surface-space distance keeps the light round as the sidebar changes
    // aspect ratio. Only the nearby rim responds to pointer or focus feedback.
    vec2 lightDelta=(p-lightPoint*surfaceSize)/max(4.*cornerRadius,1.);
    float localLight=exp(-dot(lightDelta,lightDelta)*2.);
    float localInteraction=interaction*localLight;
    // A padded capture prevents the refracted rim from sampling outside the
    // real app scene crop. Refraction is at most a few logical pixels.
    float lens=4.*edge*(1.-edge);
    vec2 uv=(p+padding-normal*lens*refraction*(1.+.3*localInteraction))/extent;
    // Horizontal Gaussian is prepared in one panel-sized texture. This
    // vertical pass also performs refraction and rim lighting. Closely
    // spaced weighted taps avoid hard bands at high-contrast source edges.
    vec2 s=vec2(0.,blurRadius/4.)/extent;
    vec4 blur=sampleSafe(uv)*.227027;
    blur+=(sampleSafe(uv+s)+sampleSafe(uv-s))*.194595;
    blur+=(sampleSafe(uv+2.*s)+sampleSafe(uv-2.*s))*.121622;
    blur+=(sampleSafe(uv+3.*s)+sampleSafe(uv-3.*s))*.054054;
    blur+=(sampleSafe(uv+4.*s)+sampleSafe(uv-4.*s))*.016216;
    // The shared window material is already below this texture. Preserve the
    // decoration's premultiplied alpha instead of adding a second opaque base.
    // At the boundary both displacement and blur reach zero: one continuous wing.
    vec4 color=mix(texture(sharpSource,(p+padding)/extent),blur,smoothstep(0.,8.,-d));
    float facing=max(0.,dot(normal,normalize(vec2(-.65,-1.))));
    float rim=exp(-max(0.,-d)*1.25);
    // Keep the resting light directional, but let the interaction glint reach
    // every edge without shifting the distant wing or lighting a whole outline.
    float highlight=rim*(.16*facing+.12*localInteraction);
    color=vec4(vec3(.88,.96,1.)*highlight,highlight)+color*(1.-highlight);
    float reflection=edge*edge*(1.-facing)*mix(.015,.045,darkMode);
    color=vec4(vec3(.08,.12,.18)*reflection,reflection)+color*(1.-reflection);
    fragColor=color*(mask*qt_Opacity);
}
