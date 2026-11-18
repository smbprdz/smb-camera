#include "../windows/bridge/pipe_protocol.hpp"
#include <iostream>
#include <stdexcept>
using namespace ucs::bridge;
void require(bool value){if(!value)throw std::runtime_error("Bridge protocol contract failed");}
int main(){
    try {
        Request request{};request.width=640;request.height=480;require(valid(request));
        Reply reply{};reply.epoch=7;reply.captured_tick_ms=1000;
        FrameDescriptor frame{};frame.width=640;frame.height=480;frame.stride0=frame.stride1=640;frame.plane1_offset=640*480;frame.payload_bytes=640*480*3/2;frame.frame_id=1;
        const auto size=sizeof(reply)+sizeof(frame)+frame.payload_bytes;reply.body_bytes=static_cast<std::uint32_t>(size-sizeof(reply));
        auto accepted=[&]{return validate_reply(request,reply,frame,static_cast<std::size_t>(size),7,1100);};require(accepted());
        require(!validate_reply(request,reply,frame,size-1,7,1100));require(!validate_reply(request,reply,frame,size+1,7,1100));
        require(!validate_reply(request,reply,frame,size,8,1100));require(!validate_reply(request,reply,frame,size,7,1251));require(!validate_reply(request,reply,frame,size,7,999));
        auto original=frame;frame.width=642;require(!accepted());frame=original;frame.payload_bytes=0xffffffffffffffffULL;require(!accepted());frame=original;
        frame.flags=ucs::native::premultiplied_alpha;require(!accepted());frame=original;frame.abi_major=2;require(!accepted());frame=original;
        auto original_reply=reply;reply.body_bytes=0x7fffffff;require(!accepted());reply=original_reply;reply.reserved=1;require(!accepted());reply=original_reply;
        auto old_request=request;request.width=641;require(!valid(request));request=old_request;request.format=static_cast<PixelFormat>(99);require(!valid(request));request=old_request;
        request.width=3840;request.height=2160;request.format=PixelFormat::bgra8;require(valid(request));
        frame={};frame.format=PixelFormat::bgra8;frame.width=3840;frame.height=2160;frame.stride0=3840*4;frame.payload_bytes=3840ULL*2160*4;frame.frame_id=2;frame.color_space=ucs::native::ColorSpace::srgb_full;
        const auto rgb_size=sizeof(reply)+sizeof(frame)+frame.payload_bytes;reply.body_bytes=static_cast<std::uint32_t>(rgb_size-sizeof(reply));
        require(validate_reply(request,reply,frame,rgb_size,7,1100));
        request.format=PixelFormat::rgba8;frame.format=PixelFormat::rgba8;
        require(!validate_reply(request,reply,frame,rgb_size,7,1100));
        frame.flags=ucs::native::premultiplied_alpha;
        require(validate_reply(request,reply,frame,rgb_size,7,1100));
        request.format=PixelFormat::bgra8;require(!validate_reply(request,reply,frame,rgb_size,7,1100));
        request.format=PixelFormat::rgba8;request.width=request.height=16384;require(!valid(request));
        std::cout<<"{\"status\":\"pass\",\"scope\":\"local IPC envelope validation, not hardware\",\"request_bytes\":24,\"reply_bytes\":32,\"descriptor_bytes\":64}\n";return 0;
    }catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 1;}
}
