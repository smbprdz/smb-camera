// Own integrated consumer. Reads generated verification pixels, never records.
#include "pch.h"
#include "pipe_windows.hpp"
#include <iostream>
#include <set>
#include "SharedReadOnly.h"
using winrt::check_hresult;
int wmain(int argc,wchar_t** argv) {
    const bool absent=argc==2 && wcscmp(argv[1],L"--absent")==0;
    const bool direct=argc==2 && wcscmp(argv[1],L"--direct")==0;
    const bool single=argc==2 && wcscmp(argv[1],L"--single")==0;
    const bool shared=argc==2 && wcscmp(argv[1],L"--shared")==0;
    if(argc!=1 && !absent && !direct && !single && !shared)return 2;
    winrt::init_apartment(winrt::apartment_type::multi_threaded);
    const char* stage="enumeration";
    try {
        check_hresult(MFStartup(MF_VERSION));struct MFGuard{~MFGuard(){MFShutdown();}} mf;
        wil::com_ptr_nothrow<IMFAttributes> attrs;check_hresult(MFCreateAttributes(&attrs,1));
        check_hresult(attrs->SetGUID(MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE,MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE_VIDCAP_GUID));
        IMFActivate** devices=nullptr;UINT32 count=0;check_hresult(MFEnumDeviceSources(attrs.get(),&devices,&count));
        wil::com_ptr_nothrow<IMFActivate> selected;
        for(UINT32 i=0;i<count;++i) {
            wil::unique_cotaskmem_string name;UINT32 length=0;
            if(SUCCEEDED(devices[i]->GetAllocatedString(MF_DEVSOURCE_ATTRIBUTE_FRIENDLY_NAME,&name,&length)) &&
               std::wstring(name.get()).starts_with(L"SMB Camera") && std::wstring(name.get()).find(L"test")==std::wstring::npos) {
                if(selected)check_hresult(E_UNEXPECTED);selected=devices[i];
            }
            devices[i]->Release();
        }
        CoTaskMemFree(devices);
        if(absent){if(selected)check_hresult(E_UNEXPECTED);std::cout<<"{\"status\":\"pass\",\"own_camera_absent\":true}"<<std::endl;return 0;}
        if(!selected)check_hresult(MF_E_NOT_FOUND);
        ucs::bridge::Config config{};if(!ucs::bridge::read_config(config))check_hresult(E_INVALIDARG);
        if(shared) {
            wil::unique_cotaskmem_string id;UINT32 length=0;
            check_hresult(selected->GetAllocatedString(MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE_VIDCAP_SYMBOLIC_LINK,&id,&length));
            return read_shared(id.get(),config);
        }
        stage="source activation";
        wil::com_ptr_nothrow<IMFMediaSource> source;
        if(direct) {
            wil::com_ptr_nothrow<IMFActivate> activate;
            check_hresult(CoCreateInstance(UCS_PROBE_CLSID,nullptr,CLSCTX_INPROC_SERVER,IID_PPV_ARGS(&activate)));
            check_hresult(activate->ActivateObject(IID_PPV_ARGS(&source)));
            wil::com_ptr_nothrow<IMFSampleAllocatorControl> control;check_hresult(source->QueryInterface(IID_PPV_ARGS(&control)));
            wil::com_ptr_nothrow<IMFVideoSampleAllocatorEx> allocator;check_hresult(MFCreateVideoSampleAllocatorEx(IID_PPV_ARGS(&allocator)));
            check_hresult(control->SetDefaultAllocator(0,allocator.get()));
        }else {
        wil::unique_cotaskmem_string symbolic;UINT32 symbolic_length=0;
        check_hresult(selected->GetAllocatedString(MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE_VIDCAP_SYMBOLIC_LINK,&symbolic,&symbolic_length));
        wil::com_ptr_nothrow<IMFAttributes> device_attrs;check_hresult(MFCreateAttributes(&device_attrs,2));
        check_hresult(device_attrs->SetGUID(MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE,MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE_VIDCAP_GUID));
        check_hresult(device_attrs->SetString(MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE_VIDCAP_SYMBOLIC_LINK,symbolic.get()));
        // Use the camera-device activation path, as in the validated device lab,
        // rather than invoking an enumerator's activation object directly.
        check_hresult(MFCreateDeviceSource(device_attrs.get(),&source));
        }
        // The reference source is uncompressed NV12. Do not insert an unrelated
        // hardware conversion path in this consumer, matching the proven lab.
        wil::com_ptr_nothrow<IMFAttributes> reader_attrs;check_hresult(MFCreateAttributes(&reader_attrs,1));check_hresult(reader_attrs->SetUINT32(MF_READWRITE_DISABLE_CONVERTERS,TRUE));
        stage="source reader";
        wil::com_ptr_nothrow<IMFSourceReader> reader;check_hresult(MFCreateSourceReaderFromMediaSource(source.get(),reader_attrs.get(),&reader));
        check_hresult(reader->SetStreamSelection(MF_SOURCE_READER_FIRST_VIDEO_STREAM,TRUE));
        wil::com_ptr_nothrow<IMFMediaType> type;check_hresult(reader->GetCurrentMediaType(MF_SOURCE_READER_FIRST_VIDEO_STREAM,&type));
        stage="media type";UINT32 w=0,h=0;GUID subtype{};check_hresult(MFGetAttributeSize(type.get(),MF_MT_FRAME_SIZE,&w,&h));check_hresult(type->GetGUID(MF_MT_SUBTYPE,&subtype));
        if(w!=config.mode.width || h!=config.mode.height || subtype!=MFVideoFormat_NV12)check_hresult(MF_E_INVALIDMEDIATYPE);
        UINT32 matrix=0,range=0;check_hresult(type->GetUINT32(MF_MT_YUV_MATRIX,&matrix));check_hresult(type->GetUINT32(MF_MT_VIDEO_NOMINAL_RANGE,&range));
        if(matrix!=MFVideoTransferMatrix_BT709 || range!=MFNominalRange_16_235)check_hresult(MF_E_INVALIDMEDIATYPE);
        std::set<unsigned> ids;unsigned samples=0,black=0;LONGLONG previous=-1;bool live=false,lost=false,recovered=false;
        const auto end=GetTickCount64()+15000;
        stage="stream samples";
        const unsigned target=direct||single?60:180;
        while(samples<target && GetTickCount64()<end) {
            DWORD index=0,flags=0;LONGLONG time=0;wil::com_ptr_nothrow<IMFSample> sample;
            check_hresult(reader->ReadSample(MF_SOURCE_READER_FIRST_VIDEO_STREAM,0,&index,&flags,&time,&sample));
            if(flags&(MF_SOURCE_READERF_ERROR|MF_SOURCE_READERF_ENDOFSTREAM))check_hresult(E_UNEXPECTED);
            if(!sample)continue;if(time<=previous)check_hresult(E_UNEXPECTED);previous=time;
            wil::com_ptr_nothrow<IMFMediaBuffer> buffer;check_hresult(sample->ConvertToContiguousBuffer(&buffer));
            BYTE* pixels=nullptr;DWORD maximum=0,bytes=0;check_hresult(buffer->Lock(&pixels,&maximum,&bytes));
            bool valid=bytes==std::uint64_t{w}*h*3/2;
            unsigned id=0;if(valid && pixels[0]=='U' && pixels[1]=='C' && pixels[2]=='S' && pixels[3]=='B') {
                for(unsigned n=0;n<16;++n)if(pixels[n+4]>128)id|=1U<<n;ids.insert(id);
                if(!live){live=true;std::cout<<"{\"state\":\"receiving\"}"<<std::endl;}
                if(lost)recovered=true;
            }else {++black;if(live)lost=true;}
            check_hresult(buffer->Unlock());if(!valid)check_hresult(E_UNEXPECTED);
            ++samples;Sleep(34);
        }
        reader.reset();source->Shutdown();source.reset();
        if(samples!=target || ids.size()<30 || black>80 || (!(direct||single) && (!lost || !recovered)))check_hresult(E_UNEXPECTED);
        std::cout<<"{\"status\":\"pass\",\"samples\":"<<samples<<",\"unique_producer_ids\":"<<ids.size()<<",\"black_samples\":"<<black
            <<",\"width\":"<<w<<",\"height\":"<<h<<",\"format\":\"NV12\",\"producer_loss_and_recovery\":"<<(lost&&recovered?"true":"false")<<",\"direct\":"<<(direct?"true":"false")<<",\"shared_client\":"<<(shared?"true":"false")<<",\"recorded_media\":false}\n";return 0;
    }catch(const winrt::hresult_error& error){std::cerr<<"Camera consumer "<<stage<<":0x"<<std::hex<<static_cast<unsigned>(error.code().value)<<'\n';return 1;}
}
