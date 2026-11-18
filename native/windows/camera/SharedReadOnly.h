#pragma once
#include <winrt/Windows.Foundation.Collections.h>
#include <winrt/Windows.Media.Capture.h>
#include <winrt/Windows.Media.Capture.Frames.h>
#include <winrt/Windows.Media.MediaProperties.h>
#include <winrt/Windows.Graphics.Imaging.h>
#include <winrt/Windows.Storage.Streams.h>
#include <robuffer.h>
#include <iostream>
#include <set>
#include <memory>

// Ordinary WinRT camera consumer, explicitly SharedReadOnly. This does not
// create/reopen a virtual-camera owner, configure the source or record frames.
inline int read_shared(const wchar_t* device_id,const ucs::bridge::Config& config) {
    using namespace winrt::Windows::Media::Capture;
    using namespace winrt::Windows::Media::Capture::Frames;
    using namespace winrt::Windows::Graphics::Imaging;
    using winrt::check_hresult;
    const char* stage="shared initialization";
    try {
        MediaCapture capture;MediaCaptureInitializationSettings settings;
        settings.VideoDeviceId(device_id);settings.StreamingCaptureMode(StreamingCaptureMode::Video);
        settings.SharingMode(MediaCaptureSharingMode::SharedReadOnly);settings.MemoryPreference(MediaCaptureMemoryPreference::Cpu);
        capture.InitializeAsync(settings).get();
        MediaFrameSource selected{nullptr};
        for(auto item:capture.FrameSources())if(item.Value().Info().SourceKind()==MediaFrameSourceKind::Color){selected=item.Value();break;}
        if(!selected)check_hresult(MF_E_NOT_FOUND);
        const auto format=selected.CurrentFormat();const auto video=format.VideoFormat();
        if(video.Width()!=config.mode.width || video.Height()!=config.mode.height)check_hresult(MF_E_INVALIDMEDIATYPE);
        stage="shared frame reader";
        auto reader=capture.CreateFrameReaderAsync(selected,winrt::Windows::Media::MediaProperties::MediaEncodingSubtypes::Nv12()).get();
        reader.AcquisitionMode(MediaFrameReaderAcquisitionMode::Realtime);
        auto signal=std::make_shared<ucs::bridge::Handle>(CreateEventW(nullptr,FALSE,FALSE,nullptr));
        if(!*signal)check_hresult(E_OUTOFMEMORY);
        const auto token=reader.FrameArrived([signal](const MediaFrameReader&,const auto&){SetEvent(signal->value);});
        if(reader.StartAsync().get()!=MediaFrameReaderStartStatus::Success)check_hresult(E_FAIL);
        std::set<unsigned> ids;unsigned samples=0,black=0;bool live=false,lost=false,recovered=false;const auto end=GetTickCount64()+20000;
        stage="shared frame pixels";
        while(samples<180 && GetTickCount64()<end) {
            if(WaitForSingleObject(signal->value,250)!=WAIT_OBJECT_0)continue;
            auto frame=reader.TryAcquireLatestFrame();if(!frame)continue;
            auto image=frame.VideoMediaFrame();if(!image){frame.Close();continue;}
            auto bitmap=image.SoftwareBitmap();if(!bitmap){frame.Close();continue;}
            if(bitmap.BitmapPixelFormat()!=BitmapPixelFormat::Nv12 || bitmap.PixelWidth()!=config.mode.width || bitmap.PixelHeight()!=config.mode.height)check_hresult(MF_E_INVALIDMEDIATYPE);
            const UINT32 size=config.mode.width*config.mode.height*3/2;
            winrt::Windows::Storage::Streams::Buffer copy(size);copy.Length(size);bitmap.CopyToBuffer(copy);
            BYTE* pixels=nullptr;auto access=copy.as<::Windows::Storage::Streams::IBufferByteAccess>();check_hresult(access->Buffer(&pixels));
            if(copy.Length()!=size)check_hresult(E_UNEXPECTED);
            if(pixels[0]=='U' && pixels[1]=='C' && pixels[2]=='S' && pixels[3]=='B') {
                unsigned id=0;for(unsigned n=0;n<16;++n)if(pixels[n+4]>128)id|=1U<<n;ids.insert(id);
                if(!live){live=true;std::cout<<"{\"state\":\"receiving\"}"<<std::endl;}
                if(lost)recovered=true;
            }else {++black;if(live)lost=true;}
            ++samples;bitmap.Close();frame.Close();
        }
        reader.FrameArrived(token);reader.StopAsync().get();reader.Close();capture.Close();
        if(samples!=180 || ids.size()<30 || black>80 || !lost || !recovered)check_hresult(E_UNEXPECTED);
        std::cout<<"{\"status\":\"pass\",\"samples\":"<<samples<<",\"unique_producer_ids\":"<<ids.size()<<",\"black_samples\":"<<black
            <<",\"width\":"<<config.mode.width<<",\"height\":"<<config.mode.height<<",\"format\":\"NV12\",\"producer_loss_and_recovery\":true,\"shared_client\":true,\"consumer_api\":\"MediaCapture SharedReadOnly\",\"recorded_media\":false}"<<std::endl;
        return 0;
    }catch(const winrt::hresult_error& error){std::cerr<<"Camera consumer "<<stage<<":0x"<<std::hex<<static_cast<unsigned>(error.code().value)<<'\n';return 1;}
}
