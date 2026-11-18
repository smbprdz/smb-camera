#pragma once
#include "../../core/frame_contract.hpp"
#include <cstring>
#include <limits>

namespace ucs::bridge {
using native::FrameDescriptor;
using native::PixelFormat;
inline constexpr std::uint32_t max_payload=64*1024*1024;
struct Request {
    std::uint32_t magic=0x51534355;
    std::uint16_t version=1,bytes=24;
    PixelFormat format=PixelFormat::nv12;
    std::uint32_t width=0,height=0,reserved=0;
};
struct Reply {
    std::uint32_t magic=0x52534355;
    std::uint16_t version=1,status=1;
    std::uint32_t body_bytes=0,reserved=0;
    std::uint64_t captured_tick_ms=0,epoch=0;
};
static_assert(sizeof(Request)==24 && sizeof(Reply)==32);
inline std::uint64_t payload_size(const Request& r) noexcept {
    if(r.format==PixelFormat::nv12)return std::uint64_t{r.width}*r.height*3/2;
    if(r.format==PixelFormat::bgra8 || r.format==PixelFormat::rgba8)return std::uint64_t{r.width}*r.height*4;
    return 0;
}
inline bool valid(const Request& r) noexcept {
    return r.magic==0x51534355 && r.version==1 && r.bytes==sizeof(Request) && !r.reserved &&
        r.width>=2 && r.height>=2 && r.width<=16384 && r.height<=16384 &&
        (r.format!=PixelFormat::nv12 || !(r.width%2 || r.height%2)) &&
        payload_size(r)>0 && payload_size(r)<=max_payload;
}
inline bool validate_reply(const Request& request,const Reply& reply,const FrameDescriptor& frame,
                           std::size_t received,std::uint64_t epoch,std::uint64_t now) noexcept {
    return valid(request) && reply.magic==0x52534355 && reply.version==1 && reply.status==1 &&
        !reply.reserved && reply.epoch==epoch && epoch && reply.captured_tick_ms<=now &&
        now-reply.captured_tick_ms<=250 && received>=sizeof(Reply)+sizeof(FrameDescriptor) &&
        reply.body_bytes==received-sizeof(Reply) && received==sizeof(Reply)+sizeof(FrameDescriptor)+frame.payload_bytes && frame.payload_bytes==payload_size(request) &&
        frame.width==request.width && frame.height==request.height && frame.format==request.format &&
        frame.flags==(request.format==PixelFormat::rgba8?native::premultiplied_alpha:native::opaque) &&
        frame.stride0==(request.format==PixelFormat::nv12?request.width:request.width*4) &&
        (request.format!=PixelFormat::nv12 || (frame.stride1==request.width && frame.plane1_offset==request.width*request.height)) &&
        native::validate(frame,received-sizeof(Reply)-sizeof(FrameDescriptor))==native::FrameError::ok;
}
}
