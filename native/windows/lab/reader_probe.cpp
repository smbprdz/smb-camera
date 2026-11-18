#include "pch.h"
#include <chrono>
#include <iostream>
#include <set>
#include <thread>

using namespace winrt::WindowsSample::implementation;

const char* stage="startup";
void check(HRESULT hr) {winrt::check_hresult(hr);}
int main() {
    winrt::init_apartment(winrt::apartment_type::multi_threaded);
    try {
        check(MFStartup(MF_VERSION,MFSTARTUP_NOSOCKET));
        struct MFGuard {~MFGuard(){MFShutdown();}} mf_guard;
        for(const auto subtype:{MFVideoFormat_NV12,MFVideoFormat_RGB32}) {
            stage="source initialize";auto source=winrt::make_self<SimpleMediaSource>();check(source->Initialize(nullptr));
            struct SourceGuard {SimpleMediaSource* source;~SourceGuard(){source->Shutdown();}} guard{source.get()};
            wil::com_ptr_nothrow<IMFVideoSampleAllocatorEx> allocator;
            stage="create allocator";check(MFCreateVideoSampleAllocatorEx(IID_PPV_ARGS(&allocator)));
            stage="set allocator";check(source->SetDefaultAllocator(0,allocator.get()));
            wil::com_ptr_nothrow<IMFAttributes> attrs;check(MFCreateAttributes(&attrs,1));
            check(attrs->SetUINT32(MF_READWRITE_DISABLE_CONVERTERS,TRUE));
            wil::com_ptr_nothrow<IMFSourceReader> reader;
            stage="create source reader";check(MFCreateSourceReaderFromMediaSource(source.get(),attrs.get(),&reader));
            wil::com_ptr_nothrow<IMFMediaType> type;check(MFCreateMediaType(&type));
            check(type->SetGUID(MF_MT_MAJOR_TYPE,MFMediaType_Video));check(type->SetGUID(MF_MT_SUBTYPE,subtype));
            stage="set current media type";check(reader->SetCurrentMediaType(MF_SOURCE_READER_FIRST_VIDEO_STREAM,nullptr,type.get()));
            stage="select video stream";check(reader->SetStreamSelection(MF_SOURCE_READER_FIRST_VIDEO_STREAM,TRUE));
            stage="get current media type";check(reader->GetCurrentMediaType(MF_SOURCE_READER_FIRST_VIDEO_STREAM,&type));
            UINT32 width=0,height=0;check(MFGetAttributeSize(type.get(),MF_MT_FRAME_SIZE,&width,&height));
            if(width!=640 || height!=480)throw winrt::hresult_error(E_UNEXPECTED);
            LONGLONG previous=-1;std::set<std::uint64_t> hashes;DWORD bytes=0;
            for(unsigned n=0;n<65;++n) {
                DWORD stream=0,flags=0;LONGLONG timestamp=0;wil::com_ptr_nothrow<IMFSample> sample;
                stage="read sample";check(reader->ReadSample(MF_SOURCE_READER_FIRST_VIDEO_STREAM,0,&stream,&flags,&timestamp,&sample));
                if(!sample || timestamp<=previous || flags&MF_SOURCE_READERF_ERROR)throw winrt::hresult_error(E_UNEXPECTED);
                previous=timestamp;
                wil::com_ptr_nothrow<IMFMediaBuffer> buffer;stage="contiguous buffer";check(sample->ConvertToContiguousBuffer(&buffer));
                BYTE* data=nullptr;DWORD maximum=0;check(buffer->Lock(&data,&maximum,&bytes));
                const auto expected=width*height*(subtype==MFVideoFormat_NV12?3:8)/2;
                if(bytes<expected){buffer->Unlock();throw winrt::hresult_error(E_UNEXPECTED);}
                std::uint64_t hash=1469598103934665603ULL;
                for(DWORD i=0;i<bytes;++i){hash^=data[i];hash*=1099511628211ULL;}
                check(buffer->Unlock());hashes.insert(hash);
                std::this_thread::sleep_for(std::chrono::milliseconds(34));
            }
            if(hashes.size()<2)throw winrt::hresult_error(E_UNEXPECTED);
            reader.reset();
            std::cout<<"{\"status\":\"pass\",\"source\":\"MIT Microsoft synthetic sample\",\"format\":\""
                <<(subtype==MFVideoFormat_NV12?"NV12":"RGB32")<<"\",\"width\":"<<width<<",\"height\":"<<height
                <<",\"samples\":65,\"different_frame_hashes\":"<<hashes.size()<<",\"buffer_bytes\":"<<bytes
                <<",\"camera_registered\":false,\"phone_capture\":false}\n";
        }
        return 0;
    } catch(const winrt::hresult_error& error) {
        std::cerr<<"Native source/reader failed at "<<stage<<":0x"<<std::hex<<static_cast<unsigned>(error.code().value)<<'\n';return 1;
    }
}
