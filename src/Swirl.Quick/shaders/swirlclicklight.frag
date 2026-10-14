#version 440

layout(location = 0) in vec2 texCoord;
layout(location = 0) out vec4 fragColor;

layout(std140, binding = 0) uniform buf {
    mat4 qt_Matrix;
    float qt_Opacity;
};



void main() {
    vec2 p = (texCoord - vec2(0.5)) * vec2(1.5, 1.0);
    float shine = exp(-5.0 * dot(p, p));
    vec2 edge = smoothstep(vec2(0.0), vec2(0.12), texCoord) * smoothstep(vec2(0.0), vec2(0.12), vec2(1.0) - texCoord);
    float alpha = shine * edge.x * edge.y;
    fragColor = vec4(vec3(alpha), alpha) * qt_Opacity;
}
