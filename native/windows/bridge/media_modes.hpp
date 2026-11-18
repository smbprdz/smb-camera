#pragma once
#include "pipe_protocol.hpp"
#include <initializer_list>

namespace ucs::bridge {
// Public configuration, no camera/network credentials. Limits protect storage;
// they do not describe available capture modes of a particular phone.
struct MediaMode {
    std::uint32_t width=640,height=480,fps_num=30,fps_den=1,formats=3,reserved=0;
};
static_assert(sizeof(MediaMode)==24);
inline bool supports(const MediaMode& mode,PixelFormat format) noexcept {
    return (format==PixelFormat::nv12 && (mode.formats&1)) ||
           (format==PixelFormat::bgra8 && (mode.formats&2));
}
inline bool valid(const MediaMode& mode) noexcept {
    if(mode.reserved || !mode.formats || (mode.formats&~3U) || !mode.fps_num || !mode.fps_den ||
       mode.fps_num>1000000 || mode.fps_den>1000000)return false;
    for(auto format:{PixelFormat::nv12,PixelFormat::bgra8}) {
        Request request{};request.width=mode.width;request.height=mode.height;request.format=format;
        if(supports(mode,format) && !valid(request))return false;
    }
    return true;
}
inline std::int64_t duration_100ns(const MediaMode& mode) noexcept {
    return valid(mode)?(10000000LL*mode.fps_den+mode.fps_num/2)/mode.fps_num:0;
}
}
