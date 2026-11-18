#include "pch.h"
#include "pipe_windows.hpp"
#include <thread>
SimpleFrameGenerator::SimpleFrameGenerator() noexcept=default;
SimpleFrameGenerator::~SimpleFrameGenerator()=default;
HRESULT SimpleFrameGenerator::Initialize(IMFMediaType* type) {
    if(!type)return E_INVALIDARG;
    RETURN_IF_FAILED(type->GetGUID(MF_MT_SUBTYPE,&subtype_));
    if(subtype_!=MFVideoFormat_NV12 && subtype_!=MFVideoFormat_RGB32)return MF_E_UNSUPPORTED_FORMAT;
    RETURN_IF_FAILED(MFGetAttributeSize(type,MF_MT_FRAME_SIZE,&width_,&height_));
    ucs::bridge::Request request{};request.width=width_;request.height=height_;
    request.format=subtype_==MFVideoFormat_NV12?ucs::native::PixelFormat::nv12:ucs::native::PixelFormat::bgra8;
    if(!ucs::bridge::valid(request))return MF_E_INVALIDMEDIATYPE;
    ucs::bridge::Config config{};UINT32 numerator=0,denominator=0;
    RETURN_IF_FAILED(MFGetAttributeRatio(type,MF_MT_FRAME_RATE,&numerator,&denominator));
    if(!ucs::bridge::read_config(config))return ucs::bridge::diagnose(L"generator.configuration",MF_E_INVALIDMEDIATYPE);
    if(width_!=config.mode.width || height_!=config.mode.height ||
       std::uint64_t{numerator}*config.mode.fps_den!=std::uint64_t{config.mode.fps_num}*denominator || !ucs::bridge::supports(config.mode,request.format))return ucs::bridge::diagnose(L"generator.mode",MF_E_INVALIDMEDIATYPE);
    duration_=ucs::bridge::duration_100ns(config.mode);
    next_output_={};
    try{client_=std::make_unique<ucs::bridge::Client>(config.mode);return S_OK;}catch(...){return E_OUTOFMEMORY;}
}
HRESULT SimpleFrameGenerator::CreateFrame(BYTE* data,DWORD bytes,LONG pitch,ULONG /*mask*/) {
    const bool nv12=subtype_==MFVideoFormat_NV12;
    const auto row_bytes=std::uint64_t{width_}*(nv12?1:4);
    const auto needed=std::uint64_t{static_cast<ULONG>(pitch)}*height_*(nv12?3:2)/2;
    if(!data || pitch<=0 || static_cast<std::uint64_t>(pitch)<row_bytes || needed>bytes)return E_INVALIDARG;
    // Request-driven consumers can pull faster than the negotiated frame rate.
    // Pace output rather than manufacturing a new timestamp for every repeat.
    const auto period=std::chrono::nanoseconds(duration_*100);
    auto now=std::chrono::steady_clock::now();
    if(next_output_>now)std::this_thread::sleep_until(next_output_);
    now=std::chrono::steady_clock::now();
    next_output_=std::max(next_output_+period,now+period);
    // Transport failures yield a fresh black sample, allowing the sample's
    // allocator lock to be released by the unchanged Microsoft stream code.
    if(nv12){std::memset(data,16,static_cast<std::size_t>(pitch)*height_);std::memset(data+static_cast<std::size_t>(pitch)*height_,128,static_cast<std::size_t>(pitch)*height_/2);}
    else {std::memset(data,0,static_cast<std::size_t>(needed));for(UINT32 y=0;y<height_;++y)for(UINT32 x=0;x<width_;++x)data[static_cast<std::size_t>(y)*pitch+x*4+3]=255;}
    try {
        ucs::bridge::Request request{};request.width=width_;request.height=height_;
        request.format=nv12?ucs::native::PixelFormat::nv12:ucs::native::PixelFormat::bgra8;
        ucs::native::FrameDescriptor frame{};const BYTE* pixels=nullptr;
        if(!client_ || !client_->receive(request,frame,pixels))return S_OK;
        for(UINT32 y=0;y<height_;++y)std::memcpy(data+static_cast<std::size_t>(y)*pitch,pixels+static_cast<std::size_t>(y)*frame.stride0,static_cast<std::size_t>(row_bytes));
        if(nv12)for(UINT32 y=0;y<height_/2;++y)std::memcpy(data+static_cast<std::size_t>(pitch)*(height_+y),pixels+frame.plane1_offset+static_cast<std::size_t>(y)*frame.stride1,width_);
    }catch(...){/* Already black; no stale image or exception across COM. */}
    return S_OK;
}
