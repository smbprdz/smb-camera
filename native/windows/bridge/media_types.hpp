#pragma once
#include "pipe_windows.hpp"

namespace ucs::bridge {
inline HRESULT make_media_type(const MediaMode& mode,PixelFormat format,IMFMediaType** result) {
    if(!result)return E_POINTER;
    *result=nullptr;if(!valid(mode) || !supports(mode,format))return MF_E_INVALIDMEDIATYPE;
    const bool nv12=format==PixelFormat::nv12;
    wil::com_ptr_nothrow<IMFMediaType> type;
    RETURN_IF_FAILED(MFCreateMediaType(&type));
    RETURN_IF_FAILED(type->SetGUID(MF_MT_MAJOR_TYPE,MFMediaType_Video));
    RETURN_IF_FAILED(type->SetGUID(MF_MT_SUBTYPE,nv12?MFVideoFormat_NV12:MFVideoFormat_RGB32));
    RETURN_IF_FAILED(type->SetUINT32(MF_MT_INTERLACE_MODE,MFVideoInterlace_Progressive));
    RETURN_IF_FAILED(type->SetUINT32(MF_MT_ALL_SAMPLES_INDEPENDENT,TRUE));
    RETURN_IF_FAILED(type->SetUINT32(MF_MT_FIXED_SIZE_SAMPLES,TRUE));
    RETURN_IF_FAILED(MFSetAttributeSize(type.get(),MF_MT_FRAME_SIZE,mode.width,mode.height));
    RETURN_IF_FAILED(MFSetAttributeRatio(type.get(),MF_MT_FRAME_RATE,mode.fps_num,mode.fps_den));
    RETURN_IF_FAILED(MFSetAttributeRatio(type.get(),MF_MT_PIXEL_ASPECT_RATIO,1,1));
    RETURN_IF_FAILED(type->SetUINT32(MF_MT_DEFAULT_STRIDE,mode.width*(nv12?1:4)));
    Request request{};request.width=mode.width;request.height=mode.height;request.format=format;
    RETURN_IF_FAILED(type->SetUINT32(MF_MT_SAMPLE_SIZE,static_cast<UINT32>(payload_size(request))));
    RETURN_IF_FAILED(type->SetUINT32(MF_MT_VIDEO_PRIMARIES,MFVideoPrimaries_BT709));
    RETURN_IF_FAILED(type->SetUINT32(MF_MT_VIDEO_NOMINAL_RANGE,nv12?MFNominalRange_16_235:MFNominalRange_0_255));
    if(nv12) {
        RETURN_IF_FAILED(type->SetUINT32(MF_MT_YUV_MATRIX,MFVideoTransferMatrix_BT709));
        RETURN_IF_FAILED(type->SetUINT32(MF_MT_TRANSFER_FUNCTION,MFVideoTransFunc_709));
    }
    // Uncompressed bitrate can exceed DWORD at 4K60 RGB32. Do not truncate an
    // optional compressed-bitrate attribute or impose a fake resolution cap.
    *result=type.detach();return S_OK;
}
}
