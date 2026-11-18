#version 330
in vec2 uv;
out vec4 result;
#include "output_common.glsl"
void main() {
    // First GL readback row becomes the top image row. No CPU row reversal.
    vec3 rgb=composed_rgb(uv);
    result=vec4(rgb.b,rgb.g,rgb.r,1.0);
}
