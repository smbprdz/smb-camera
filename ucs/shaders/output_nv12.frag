#version 330
out vec4 result;
#include "output_common.glsl"
void main() {
    vec2 pixel=floor(gl_FragCoord.xy);
    float value;
    if(pixel.y<canvas_size.y) {
        vec3 rgb=composed_rgb((pixel+0.5)/canvas_size);
        value=clamp(16.0+219.0*dot(rgb,vec3(0.2126,0.7152,0.0722)),16.0,235.0);
    } else {
        vec2 base=vec2(floor(pixel.x/2.0)*2.0,(pixel.y-canvas_size.y)*2.0);
        vec3 rgb=(composed_rgb((base+vec2(0.5,0.5))/canvas_size)+
                  composed_rgb((base+vec2(1.5,0.5))/canvas_size)+
                  composed_rgb((base+vec2(0.5,1.5))/canvas_size)+
                  composed_rgb((base+vec2(1.5,1.5))/canvas_size))*0.25;
        vec3 weights=mod(pixel.x,2.0)<1.0?vec3(-0.114572,-0.385428,0.5):vec3(0.5,-0.454153,-0.045847);
        value=clamp(128.0+224.0*dot(rgb,weights),16.0,240.0);
    }
    result=vec4(value/255.0,0.0,0.0,1.0);
}
