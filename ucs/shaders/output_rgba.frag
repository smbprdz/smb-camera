#version 330
in vec2 uv;
out vec4 result;
#include "output_common.glsl"
void main() {
    // Own RGBA8 premultiplied output. No checkerboard or CPU channel conversion.
    result=composed_rgba(uv);
}
