#pragma once
#include <bit>
#include <cstddef>
#include <cstdint>
#include <type_traits>

namespace ucs::native {

// CPU buffer descriptor for internal native tests. No pointer/HANDLE is sent
// in this header, and it is NOT the existing UCS1 network protocol.
enum class PixelFormat : std::uint32_t { nv12=1, bgra8=2, rgba8=3 };
enum class ColorSpace : std::uint32_t { bt709_limited_sdr=1, srgb_full=2 };
enum FrameFlags : std::uint32_t { opaque=0, premultiplied_alpha=1 };

struct alignas(8) FrameDescriptor {
    std::uint32_t magic=0x46534355; // UCSF in little-endian memory
    std::uint16_t abi_major=1;
    std::uint16_t header_bytes=64;
    PixelFormat format=PixelFormat::nv12;
    std::uint32_t width=0, height=0, stride0=0, stride1=0, plane1_offset=0;
    std::uint64_t payload_bytes=0, frame_id=0;
    std::int64_t pts_100ns=0; // Relative to the stream clock, not wall time.
    ColorSpace color_space=ColorSpace::bt709_limited_sdr;
    std::uint32_t flags=opaque;
};
static_assert(std::is_standard_layout_v<FrameDescriptor>);
static_assert(std::is_trivially_copyable_v<FrameDescriptor>);
static_assert(sizeof(FrameDescriptor)==64);
static_assert(offsetof(FrameDescriptor,payload_bytes)==32);
static_assert(offsetof(FrameDescriptor,pts_100ns)==48);
static_assert(std::endian::native==std::endian::little);

enum class FrameError { ok, header, dimensions, format, color, flags, timestamp, storage, planes };

inline FrameError validate(const FrameDescriptor& d,std::uint64_t available_bytes) noexcept {
    if(d.magic!=0x46534355 || d.abi_major!=1 || d.header_bytes!=sizeof(FrameDescriptor))return FrameError::header;
    // Explicit allocation-safety ceiling, not an advertised capture-mode limit.
    if(d.width<2 || d.height<2 || d.width>16384 || d.height>16384)return FrameError::dimensions;
    if(d.frame_id==0 || d.pts_100ns<0)return FrameError::timestamp;
    if(d.flags & ~premultiplied_alpha)return FrameError::flags;
    if(d.payload_bytes==0 || d.payload_bytes>1024ULL*1024*1024 || available_bytes<d.payload_bytes)return FrameError::storage;
    if(d.format==PixelFormat::nv12) {
        if(d.width%2 || d.height%2)return FrameError::dimensions;
        if(d.color_space!=ColorSpace::bt709_limited_sdr)return FrameError::color;
        if(d.flags!=opaque)return FrameError::flags;
        if(d.stride0<d.width || d.stride1<d.width)return FrameError::planes;
        const auto y_bytes=std::uint64_t{d.stride0}*d.height;
        const auto end=std::uint64_t{d.plane1_offset}+std::uint64_t{d.stride1}*(d.height/2);
        if(d.plane1_offset<y_bytes || end>d.payload_bytes)return FrameError::planes;
    } else if(d.format==PixelFormat::bgra8 || d.format==PixelFormat::rgba8) {
        if(d.color_space!=ColorSpace::srgb_full)return FrameError::color;
        if(d.stride0<std::uint64_t{d.width}*4 || d.stride1 || d.plane1_offset)return FrameError::planes;
        if(std::uint64_t{d.stride0}*d.height>d.payload_bytes)return FrameError::planes;
    } else return FrameError::format;
    return FrameError::ok;
}
} // namespace ucs::native
