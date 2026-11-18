// Own temporary software-camera proof. Registers only a unique test CLSID,
// creates a session-lifetime/current-user device, then removes both.
#include "pch.h"
#include "NativeId.h"
#include "DeviceRegistration.h"
#include <filesystem>
#include <iostream>
#include <set>
#include <thread>
#include <chrono>
#include <string_view>

const char* stage="startup";
using namespace ucs_lab;
int wmain(int argc,wchar_t** argv) {
    const bool cleanup_only=argc==3 && wcscmp(argv[1],L"--cleanup")==0;
    if((argc!=2 && !cleanup_only) || !std::filesystem::is_regular_file(argv[cleanup_only?2:1]))return 2;
    const auto dll=std::filesystem::canonical(argv[cleanup_only?2:1]);
    if(dll.filename()!=L"UcsNativeTestSource.dll")return 2;
    winrt::init_apartment(winrt::apartment_type::multi_threaded);
    try {
        check(MFStartup(MF_VERSION));struct MFGuard {~MFGuard(){MFShutdown();}} guard;
        if(cleanup_only) {
            Camera camera;const auto created=MFCreateVirtualCamera(MFVirtualCameraType_SoftwareCameraSource,MFVirtualCameraLifetime_Session,
                MFVirtualCameraAccess_CurrentUser,UCS_PROBE_FRIENDLY_NAME,UCS_PROBE_CLSID_TEXT,nullptr,0,&camera.value);
            if(FAILED(created) && !(created==MF_E_NOT_FOUND && own_camera_count()==0))check(created);
            const auto removed=camera.cleanup();
            if(FAILED(removed) && removed!=HRESULT_FROM_WIN32(ERROR_NOT_FOUND) && removed!=HRESULT_FROM_WIN32(ERROR_FILE_NOT_FOUND)
                && !(removed==MF_E_NOT_FOUND && own_camera_count()==0))check(removed);
            const auto status=remove_verified_key(dll.c_str());
            if(status!=ERROR_SUCCESS && status!=ERROR_FILE_NOT_FOUND)check_registry(status);
            if(own_camera_count()!=0)check(E_UNEXPECTED);
            std::cout<<"{\"own_cleanup\":true,\"own_devices_remaining\":0}\n";return 0;
        }
        if(own_camera_count()!=0)check(HRESULT_FROM_WIN32(ERROR_ALREADY_EXISTS));
        stage="own temporary COM registration";Registration registration(dll.c_str());
        Camera camera;stage="create virtual camera";
        check(MFCreateVirtualCamera(MFVirtualCameraType_SoftwareCameraSource,MFVirtualCameraLifetime_Session,
            MFVirtualCameraAccess_CurrentUser,UCS_PROBE_FRIENDLY_NAME,UCS_PROBE_CLSID_TEXT,nullptr,0,&camera.value));
        stage="start virtual camera";check(camera.value->Start(nullptr));
        wil::unique_cotaskmem_string symbolic;UINT32 chars=0;
        stage="get virtual camera identity";check(camera.value->GetAllocatedString(MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE_VIDCAP_SYMBOLIC_LINK,&symbolic,&chars));
        wil::com_ptr_nothrow<IMFAttributes> attributes;check(MFCreateAttributes(&attributes,2));
        check(attributes->SetGUID(MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE,MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE_VIDCAP_GUID));
        check(attributes->SetString(MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE_VIDCAP_SYMBOLIC_LINK,symbolic.get()));
        wil::com_ptr_nothrow<IMFMediaSource> source;stage="open own virtual device";check(MFCreateDeviceSource(attributes.get(),&source));
        wil::com_ptr_nothrow<IMFSourceReader> reader;stage="create device reader";check(MFCreateSourceReaderFromMediaSource(source.get(),nullptr,&reader));
        check(reader->SetStreamSelection(MF_SOURCE_READER_FIRST_VIDEO_STREAM,TRUE));
        wil::com_ptr_nothrow<IMFMediaType> type;check(reader->GetCurrentMediaType(MF_SOURCE_READER_FIRST_VIDEO_STREAM,&type));
        UINT32 width=0,height=0;GUID subtype{};check(MFGetAttributeSize(type.get(),MF_MT_FRAME_SIZE,&width,&height));check(type->GetGUID(MF_MT_SUBTYPE,&subtype));
        if(width!=640 || height!=480 || subtype!=MFVideoFormat_NV12)check(MF_E_INVALIDMEDIATYPE);
        std::set<std::uint64_t> hashes;LONGLONG previous=-1;unsigned samples=0,ticks=0;
        for(unsigned n=0;n<260 && samples<65;++n) {
            DWORD index=0,flags=0;LONGLONG time=0;wil::com_ptr_nothrow<IMFSample> sample;
            stage="read registered virtual device";check(reader->ReadSample(MF_SOURCE_READER_FIRST_VIDEO_STREAM,0,&index,&flags,&time,&sample));
            if(flags&(MF_SOURCE_READERF_ERROR|MF_SOURCE_READERF_ENDOFSTREAM))check(E_UNEXPECTED);
            if(!sample && (flags&MF_SOURCE_READERF_STREAMTICK)){++ticks;continue;}
            if(!sample || time<=previous) {
                std::cerr<<"sample_check n="<<n<<" present="<<static_cast<bool>(sample)<<" flags="<<flags<<" pts="<<time<<" previous="<<previous<<'\n';
                stage="validate sample event/time";check(E_UNEXPECTED);
            }
            previous=time;wil::com_ptr_nothrow<IMFMediaBuffer> buffer;check(sample->ConvertToContiguousBuffer(&buffer));
            BYTE* data=nullptr;DWORD bytes=0,maximum=0;check(buffer->Lock(&data,&maximum,&bytes));
            std::uint64_t hash=1469598103934665603ULL;
            for(DWORD i=0;i<bytes;++i){hash^=data[i];hash*=1099511628211ULL;}
            check(buffer->Unlock());hashes.insert(hash);++samples;
            std::this_thread::sleep_for(std::chrono::milliseconds(34));
        }
        if(samples!=65 || hashes.size()<2){std::cerr<<"samples="<<samples<<" hashes="<<hashes.size()<<'\n';stage="validate changing frame content";check(E_UNEXPECTED);}
        reader.reset();source->Shutdown();source.reset();
        stage="remove own virtual camera";check(camera.cleanup());
        stage="remove own COM key";check_registry(registration.remove());
        stage="verify device no longer enumerated";if(own_camera_count()!=0)check(E_UNEXPECTED);
        std::cout<<"{\"status\":\"pass\",\"scope\":\"temporary Windows software camera -> own device consumer\",\"samples\":"<<samples
            <<",\"width\":"<<width<<",\"height\":"<<height<<",\"format\":\"NV12\",\"different_hashes\":"<<hashes.size()
            <<",\"stream_ticks_not_counted_as_frames\":"<<ticks<<",\"camera_removed\":true,\"own_registry_key_removed\":true,\"own_devices_remaining\":0,\"phone_capture\":false,\"user_media_recorded\":false}\n";
        return 0;
    }catch(const winrt::hresult_error& error) {
        std::cerr<<"Virtual test failed at "<<stage<<":0x"<<std::hex<<static_cast<unsigned>(error.code().value)<<'\n';return 1;
    }
}
