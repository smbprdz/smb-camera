#version 330
in vec2 uv;
out vec4 result;
uniform sampler2D plane_y;
uniform sampler2D plane_u;
uniform sampler2D plane_v;
uniform sampler2D alpha_mask;
uniform float alpha_gain;
uniform sampler3D grade_lut;
uniform vec2 source_size;
uniform bool nv12;
uniform bool full_range;
uniform bool use_alpha;
uniform bool apply_color;
uniform vec4 basic; // EV, contrast, saturation, vibrance
uniform vec4 tones; // shadows, highlights, blacks, whites
uniform vec3 balance; // temperature, tint, gamma
uniform vec3 rgb_gain;
uniform vec3 domain_min;
uniform vec3 domain_max;
uniform float lut_size;
uniform float lut_strength;
vec2 coords(sampler2D image, vec2 visible, vec2 q) {
    return clamp(q * visible, vec2(0.5), visible - vec2(0.5)) / vec2(textureSize(image,0));
}
vec3 linearize(vec3 c) {
    return mix(c/12.92, pow(max((c+0.055)/1.055,vec3(0.0)),vec3(2.4)), step(vec3(0.04045),c));
}
vec3 encode(vec3 c) {
    return mix(c*12.92,1.055*pow(max(c,vec3(0.0)),vec3(1.0/2.4))-0.055,step(vec3(0.0031308),c));
}
vec3 grade(vec3 c) {
    if (!apply_color) return c;
    vec3 gain = vec3(balance.x*0.25+balance.y*0.08,-balance.y*0.16,-balance.x*0.25+balance.y*0.08);
    c = encode(linearize(max(c,vec3(0.0))) * exp2(gain + rgb_gain + vec3(basic.x)));
    c = (c-0.5)*exp2(basic.y)+0.5;
    float y = clamp(dot(c,vec3(0.2126,0.7152,0.0722)),0.0,1.0);
    c += tones.x*0.25*(1.0-smoothstep(0.0,0.55,y))*(1.0-c);
    c += tones.y*0.25*smoothstep(0.45,1.0,y)*c;
    c += tones.z*0.15*(1.0-y)*(1.0-y) + tones.w*0.15*y*y;
    c = pow(max(c,vec3(0.0)),vec3(1.0/balance.z));
    y = dot(c,vec3(0.2126,0.7152,0.0722));
    float chroma=clamp(max(max(c.r,c.g),c.b)-min(min(c.r,c.g),c.b),0.0,1.0);
    c = mix(vec3(y),c,max(0.0,basic.z + basic.w*(1.0-chroma)*0.65));
    if (lut_strength>0.0) {
        vec3 q=clamp((c-domain_min)/(domain_max-domain_min),0.0,1.0);
        q=(q*(lut_size-1.0)+0.5)/lut_size;
        c=mix(c,texture(grade_lut,q).rgb,lut_strength);
    }
    return c;
}
void main() {
    vec2 q=vec2(uv.x,1.0-uv.y);
    float y=texture(plane_y,coords(plane_y,source_size,q)).r;
    vec2 chroma_size=source_size*0.5;
    vec2 cbcr;
    if(nv12) cbcr=texture(plane_u,coords(plane_u,chroma_size,q)).rg;
    else cbcr=vec2(texture(plane_u,coords(plane_u,chroma_size,q)).r,texture(plane_v,coords(plane_v,chroma_size,q)).r);
    cbcr-=vec2(128.0/255.0);
    vec3 rgb;
    if(full_range) rgb=vec3(y+1.402*cbcr.y,y-0.344136*cbcr.x-0.714136*cbcr.y,y+1.772*cbcr.x);
    else {
        y=(y-16.0/255.0)*(255.0/219.0);cbcr*=255.0/224.0;
        rgb=vec3(y+1.5748*cbcr.y,y-0.187324*cbcr.x-0.468124*cbcr.y,y+1.8556*cbcr.x);
    }
    float a=use_alpha ? clamp(texture(alpha_mask,q).r*alpha_gain,0.0,1.0) : 1.0;
    result=vec4(clamp(grade(rgb),0.0,1.0)*a,a);
}
