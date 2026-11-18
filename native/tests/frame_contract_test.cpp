#include "../core/frame_contract.hpp"
#include "../core/latest_slot.hpp"
#include <chrono>
#include <future>
#include <iostream>
#include <stdexcept>

using namespace ucs::native;
using namespace std::chrono_literals;
void expect(bool condition,const char* message) {
    if(!condition)throw std::runtime_error(message);
}
int main() {
    try {
        FrameDescriptor nv12;
        nv12.width=1920;nv12.height=1080;nv12.stride0=1920;nv12.stride1=1920;
        nv12.plane1_offset=1920*1080;nv12.payload_bytes=1920*1080*3/2;nv12.frame_id=1;
        expect(validate(nv12,nv12.payload_bytes)==FrameError::ok,"valid NV12");
        auto bad=nv12;bad.header_bytes=63;expect(validate(bad,bad.payload_bytes)==FrameError::header,"bad header");
        bad=nv12;bad.abi_major=2;expect(validate(bad,bad.payload_bytes)==FrameError::header,"bad ABI");
        bad=nv12;bad.height=1079;expect(validate(bad,bad.payload_bytes)==FrameError::dimensions,"odd NV12");
        bad=nv12;bad.plane1_offset=16;expect(validate(bad,bad.payload_bytes)==FrameError::planes,"overlap");
        bad=nv12;bad.stride1=0xffffffff;expect(validate(bad,bad.payload_bytes)==FrameError::planes,"pitch overflow");
        bad=nv12;bad.flags=premultiplied_alpha;expect(validate(bad,bad.payload_bytes)==FrameError::flags,"NV12 cannot carry alpha");
        bad=nv12;bad.pts_100ns=-1;expect(validate(bad,bad.payload_bytes)==FrameError::timestamp,"negative PTS");
        bad=nv12;bad.frame_id=0;expect(validate(bad,bad.payload_bytes)==FrameError::timestamp,"missing identity");
        bad=nv12;bad.format=static_cast<PixelFormat>(99);expect(validate(bad,bad.payload_bytes)==FrameError::format,"unknown format");
        expect(validate(nv12,nv12.payload_bytes-1)==FrameError::storage,"truncated storage");
        FrameDescriptor rgba;
        rgba.width=3840;rgba.height=2160;rgba.format=PixelFormat::rgba8;rgba.color_space=ColorSpace::srgb_full;
        rgba.stride0=3840*4;rgba.payload_bytes=std::uint64_t{rgba.stride0}*rgba.height;
        rgba.frame_id=2;rgba.flags=premultiplied_alpha;rgba.pts_100ns=333333;
        expect(validate(rgba,rgba.payload_bytes)==FrameError::ok,"4K RGBA without allocating video");
        bad=rgba;bad.color_space=ColorSpace::bt709_limited_sdr;expect(validate(bad,bad.payload_bytes)==FrameError::color,"color mismatch");
        bad=rgba;bad.stride0=1;expect(validate(bad,bad.payload_bytes)==FrameError::planes,"packed pitch");
        LatestSlot<int> slot;
        expect(slot.put(1) && slot.put(2),"publish");
        expect(slot.replaced()==1,"replacement counter");
        expect(slot.take_for(0ms)==2,"latest only");
        expect(!slot.take_for(0ms).has_value(),"take removes");
        std::promise<void> waiting;auto ready=waiting.get_future();
        auto consumer=std::async(std::launch::async,[&]{waiting.set_value();return slot.take_for(5s);});
        ready.wait();slot.close();
        expect(consumer.wait_for(500ms)==std::future_status::ready,"close wakes consumer");
        expect(!consumer.get().has_value() && !slot.put(3),"closed slot rejects input");
        std::cout<<"{\"status\":\"pass\",\"scope\":\"C++20 CPU frame ABI and bounded mailbox, not a virtual camera\",\"descriptor_bytes\":"<<sizeof(FrameDescriptor)<<"}\n";
        return 0;
    } catch(const std::exception& error) {
        std::cerr<<"Native contract test failed: "<<error.what()<<'\n';return 1;
    }
}
