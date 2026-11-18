uniform sampler2D foreground;
uniform sampler2D background_image;
uniform int background_mode;
uniform int angle;
uniform bool mirror;
uniform vec4 crop;
uniform vec2 canvas_size;
uniform vec2 background_size;
// t is a top-down logical canvas coordinate for all exporters.
vec4 composed_rgba(vec2 t) {
    vec2 q=t;
    if(angle==90) q=vec2(t.y,1.0-t.x);
    else if(angle==180) q=vec2(1.0-t.x,1.0-t.y);
    else if(angle==270) q=vec2(1.0-t.y,t.x);
    if(mirror) q.x=1.0-q.x;
    q=crop.xy+q*crop.zw;
    vec4 color=texture(foreground,vec2(q.x,1.0-q.y));
    vec3 bg=vec3(0.0);
    if(background_mode==2) {
        vec2 visible=vec2(1.0);
        float target=canvas_size.x/canvas_size.y;
        float source=background_size.x/background_size.y;
        if(source>target) visible.x=target/source;else visible.y=source/target;
        vec4 image=texture(background_image,(t-0.5)*visible+0.5);
        bg=image.rgb*image.a;
    }
    // The foreground is already premultiplied. Only transparent mode exports
    // its alpha. Original and image-background modes keep their opaque output.
    return vec4(clamp(color.rgb+bg*(1.0-color.a),0.0,1.0),
                background_mode==1 ? color.a : 1.0);
}
vec3 composed_rgb(vec2 t) {
    return composed_rgba(t).rgb;
}
