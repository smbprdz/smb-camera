// External producer -> local authenticated pipe -> MF camera -> own consumer.
#include "pch.h"
#include "DeviceRegistration.h"
#include "pipe_windows.hpp"
#include <filesystem>
#include <iostream>
#include <set>
#include <thread>
#include <chrono>

using namespace ucs_lab;
using namespace ucs::bridge;
const char* stage="startup";
bool python_producer=false;
bool rgb_output=false;
std::wstring producer_script;
MediaMode selected_mode{};
struct Producer {
    Handle process,job,ready_event;DWORD pid=0;
    Producer(const std::filesystem::path& executable,const std::wstring& pipe,std::uint64_t epoch,const wchar_t* mode=L"") {
        ready_event.reset(CreateEventW(nullptr,TRUE,FALSE,ready_name(pipe,epoch).c_str()));
        if(!ready_event || GetLastError()==ERROR_ALREADY_EXISTS)check(HRESULT_FROM_WIN32(ERROR_ALREADY_EXISTS));
        auto command=L"\""+executable.wstring()+L"\" ";
        if(python_producer)command+=L"\""+producer_script+L"\" --width "+std::to_wstring(selected_mode.width)+L" --height "+std::to_wstring(selected_mode.height)+L" --fps-num "+std::to_wstring(selected_mode.fps_num)+L" --fps-den "+std::to_wstring(selected_mode.fps_den)+L" ";
        if(python_producer && !rgb_output)command+=L"--nv12 ";
        command+=L"--pipe \""+pipe+L"\" --epoch "+std::to_wstring(epoch)+L" "+mode;
        STARTUPINFOW startup{};startup.cb=sizeof(startup);PROCESS_INFORMATION info{};
        if(!CreateProcessW(executable.c_str(),command.data(),nullptr,nullptr,FALSE,CREATE_NO_WINDOW|CREATE_SUSPENDED,nullptr,nullptr,&startup,&info))check(HRESULT_FROM_WIN32(GetLastError()));
        Handle thread(info.hThread);process.reset(info.hProcess);pid=info.dwProcessId;job.reset(CreateJobObjectW(nullptr,nullptr));
        JOBOBJECT_EXTENDED_LIMIT_INFORMATION limits{};limits.BasicLimitInformation.LimitFlags=JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
        if(!job || !SetInformationJobObject(job.value,JobObjectExtendedLimitInformation,&limits,sizeof(limits)) || !AssignProcessToJobObject(job.value,process.value)) {
            const auto error=GetLastError();TerminateProcess(process.value,1);WaitForSingleObject(process.value,5000);check(HRESULT_FROM_WIN32(error));
        }
        if(ResumeThread(thread.value)==static_cast<DWORD>(-1)){const auto error=GetLastError();TerminateJobObject(job.value,1);check(HRESULT_FROM_WIN32(error));}
    }
    void stop(){if(process){TerminateJobObject(job.value,0);if(WaitForSingleObject(process.value,5000)!=WAIT_OBJECT_0)check(E_UNEXPECTED);process.reset();job.reset();}}
    ~Producer(){if(process){TerminateJobObject(job.value,0);WaitForSingleObject(process.value,5000);}}
    void ready(const std::wstring& pipe) {
        (void)pipe;HANDLE handles[]={ready_event.value,process.value};
        const auto result=WaitForMultipleObjects(2,handles,FALSE,5000);
        if(result==WAIT_OBJECT_0)return;
        DWORD code=0;GetExitCodeProcess(process.value,&code);std::cerr<<"producer_start_wait="<<result<<" exit="<<code<<'\n';check(HRESULT_FROM_WIN32(ERROR_TIMEOUT));
    }
};
void configure(const std::wstring& pipe,const std::wstring& sid,DWORD pid,std::uint64_t epoch) {
    Config config{};config.producer_pid=pid;config.epoch=epoch;config.mode=selected_mode;
    if(wcscpy_s(config.pipe_name,pipe.c_str()) || wcscpy_s(config.owner_sid,sid.c_str()) || !config_valid(config))check(E_INVALIDARG);
    HKEY key=nullptr;check_registry(RegOpenKeyExW(HKEY_LOCAL_MACHINE,UCS_PROBE_REGKEY,0,KEY_SET_VALUE|KEY_WOW64_64KEY,&key));
    const auto result=RegSetValueExW(key,L"UCS.Bridge.Config",0,REG_BINARY,reinterpret_cast<BYTE*>(&config),sizeof(config));RegCloseKey(key);check_registry(result);
}
struct Sample {
    std::vector<BYTE> pixels;LONGLONG time=0;
    unsigned producer_id()const {
        const unsigned step=rgb_output?4:1;
        if(pixels.size()<20*step)return 0;
        constexpr BYTE marker[4]={'U','C','S','B'};for(unsigned n=0;n<4;++n)if(pixels[n*step]!=marker[n])return 0;
        unsigned id=0;for(unsigned n=0;n<16;++n)if(pixels[(4+n)*step]>128)id|=1U<<n;return id;
    }
    bool black()const {
        if(rgb_output){if(pixels.size()!=(static_cast<std::size_t>(selected_mode.width)*selected_mode.height)*4)return false;for(std::size_t i=0;i<pixels.size();i+=4)if(pixels[i]||pixels[i+1]||pixels[i+2]||pixels[i+3]!=255)return false;return true;}
        if(pixels.size()!=(static_cast<std::size_t>(selected_mode.width)*selected_mode.height)*3/2)return false;
        return std::all_of(pixels.begin(),pixels.begin()+(static_cast<std::size_t>(selected_mode.width)*selected_mode.height),[](BYTE b){return b==16;}) &&
            std::all_of(pixels.begin()+(static_cast<std::size_t>(selected_mode.width)*selected_mode.height),pixels.end(),[](BYTE b){return b==128;});
    }
};
Sample read(IMFSourceReader* reader,LONGLONG& last) {
    for(unsigned tries=0;tries<10;++tries) {
        DWORD index=0,flags=0;LONGLONG pts=0;wil::com_ptr_nothrow<IMFSample> sample;
        check(reader->ReadSample(MF_SOURCE_READER_FIRST_VIDEO_STREAM,0,&index,&flags,&pts,&sample));
        if(flags&(MF_SOURCE_READERF_ERROR|MF_SOURCE_READERF_ENDOFSTREAM))check(E_UNEXPECTED);
        if(!sample && flags&MF_SOURCE_READERF_STREAMTICK)continue;
        if(!sample || pts<=last)check(E_UNEXPECTED);last=pts;
        wil::com_ptr_nothrow<IMFMediaBuffer> buffer;check(sample->ConvertToContiguousBuffer(&buffer));
        BYTE* data=nullptr;DWORD maximum=0,length=0;check(buffer->Lock(&data,&maximum,&length));
        LONGLONG sample_duration=0;check(sample->GetSampleDuration(&sample_duration));if(sample_duration!=duration_100ns(selected_mode))check(E_UNEXPECTED);
        Sample result;result.time=pts;result.pixels.assign(data,data+length);check(buffer->Unlock());
        if(length!=(static_cast<std::size_t>(selected_mode.width)*selected_mode.height)*(rgb_output?4:3)/ (rgb_output?1:2))check(E_UNEXPECTED);
        std::this_thread::sleep_for(std::chrono::nanoseconds(duration_100ns(selected_mode)*100));return result;
    }
    check(E_UNEXPECTED);return {};
}
unsigned changing(IMFSourceReader* reader,LONGLONG& last) {
    std::set<unsigned> ids;unsigned received=0;const auto end=GetTickCount64()+5000;
    while(received<40 && GetTickCount64()<end) {
        const auto sample=read(reader,last);const auto id=sample.producer_id();
        if(id){ids.insert(id);++received;}
    }
    if(received!=40 || ids.size()<20){std::cerr<<"producer_samples="<<received<<" ids="<<ids.size()<<'\n';check(E_UNEXPECTED);}
    return static_cast<unsigned>(ids.size());
}
void black_after(IMFSourceReader* reader,LONGLONG& last) {
    const auto end=GetTickCount64()+1500;unsigned consecutive=0;
    while(GetTickCount64()<end && consecutive<8){const auto sample=read(reader,last);consecutive=sample.black()?consecutive+1:0;}
    if(consecutive<8)check(E_UNEXPECTED);
}
void rejected(Client::Error expected) {
    Client client;Request request{};request.width=selected_mode.width;request.height=selected_mode.height;
    if(rgb_output)request.format=ucs::native::PixelFormat::bgra8;
    const auto end=GetTickCount64()+3000;
    while(GetTickCount64()<end){FrameDescriptor frame{};const BYTE* pixels=nullptr;if(client.receive(request,frame,pixels))check(E_UNEXPECTED);if(client.error==expected)return;Sleep(20);}
    std::cerr<<"pipe_error="<<static_cast<int>(client.error)<<" expected="<<static_cast<int>(expected)<<'\n';check(E_UNEXPECTED);
}
int wmain(int argc,wchar_t** argv) {
    const bool cleanup_only=argc==3 && wcscmp(argv[1],L"--cleanup")==0;
    python_producer=argc>=5 && (wcscmp(argv[2],L"--python")==0 || wcscmp(argv[2],L"--python-nv12")==0);
    rgb_output=python_producer && wcscmp(argv[2],L"--python")==0;
    const int expected=python_producer?5:2;
    if(!cleanup_only && argc!=expected && argc!=expected+5)return 2;
    if(python_producer)selected_mode.formats=rgb_output?2:1;
    if(!cleanup_only && argc==expected+5) {
        if(wcscmp(argv[expected],L"--mode"))return 2;
        std::uint32_t* fields[]={&selected_mode.width,&selected_mode.height,&selected_mode.fps_num,&selected_mode.fps_den};
        for(unsigned n=0;n<4;++n) {
            const std::wstring value=argv[expected+1+n];std::uint64_t number=0;
            if(value.empty() || value.size()>10)return 2;
            for(auto c:value){if(c<L'0'||c>L'9')return 2;number=number*10+c-L'0';}
            if(number>UINT32_MAX)return 2;*fields[n]=static_cast<std::uint32_t>(number);
        }
    }
    if(!valid(selected_mode))return 2;const auto dll=std::filesystem::canonical(argv[cleanup_only?2:1]);
    if(dll.filename()!=L"UcsFrameBridgeSource.dll")return 2;
    const auto executable=python_producer?std::filesystem::canonical(argv[3]):dll.parent_path()/L"frame_producer.exe";if(!std::filesystem::is_regular_file(executable))return 2;
    if(python_producer){const auto script=std::filesystem::canonical(argv[4]);if(script.filename()!=L"frame_output_fixture.py" || !std::filesystem::is_regular_file(script))return 2;producer_script=script.wstring();}
    winrt::init_apartment(winrt::apartment_type::multi_threaded);
    try {
        check(MFStartup(MF_VERSION));struct MFGuard{~MFGuard(){MFShutdown();}} mf;
        if(cleanup_only) {
            Camera camera;const auto hr=MFCreateVirtualCamera(MFVirtualCameraType_SoftwareCameraSource,MFVirtualCameraLifetime_Session,MFVirtualCameraAccess_CurrentUser,
                UCS_PROBE_FRIENDLY_NAME,UCS_PROBE_CLSID_TEXT,nullptr,0,&camera.value);
            if(FAILED(hr) && !(hr==MF_E_NOT_FOUND && own_camera_count()==0))check(hr);
            const auto removed=camera.cleanup();if(FAILED(removed) && removed!=HRESULT_FROM_WIN32(ERROR_FILE_NOT_FOUND) && removed!=HRESULT_FROM_WIN32(ERROR_NOT_FOUND) && !(removed==MF_E_NOT_FOUND && own_camera_count()==0))check(removed);
            check_registry(remove_verified_key(dll.c_str()));if(own_camera_count())check(E_UNEXPECTED);
            std::cout<<"{\"own_cleanup\":true,\"own_devices_remaining\":0}\n";return 0;
        }
        if(own_camera_count())check(HRESULT_FROM_WIN32(ERROR_ALREADY_EXISTS));
        stage="register own bridge";Registration registration(dll.c_str());
        GUID guid{};check(CoCreateGuid(&guid));wchar_t text[40]{};StringFromGUID2(guid,text,40);
        const auto pipe=std::wstring(pipe_prefix)+std::wstring(text+1,36);const auto sid=token_user_sid();
        auto producer=std::make_unique<Producer>(executable,pipe,1);configure(pipe,sid,producer->pid,1);producer->ready(pipe);
        stage="direct authenticated transport formats";
        for(const auto format:{ucs::native::PixelFormat::nv12,ucs::native::PixelFormat::bgra8}) {
            if(!supports(selected_mode,format))continue;
            Client client;Request request{};request.width=selected_mode.width;request.height=selected_mode.height;request.format=format;
            FrameDescriptor frame{};const BYTE* pixels=nullptr;bool got=false;const auto end=GetTickCount64()+5000;
            while(GetTickCount64()<end && !(got=client.receive(request,frame,pixels)))Sleep(20);
            if(!got || !pixels || frame.frame_id==0)check(E_UNEXPECTED);
        }
        // Assert exact transport errors without a competing FrameServer client.
        {
            Client client;Request unsupported{};unsupported.width=selected_mode.width+2;unsupported.height=selected_mode.height;
            unsupported.format=rgb_output?PixelFormat::bgra8:PixelFormat::nv12;
            FrameDescriptor frame{};const BYTE* pixels=nullptr;
            if(client.receive(unsupported,frame,pixels) || client.error!=Client::Error::configuration)check(E_UNEXPECTED);
            if(python_producer){unsupported.width=selected_mode.width;unsupported.format=rgb_output?PixelFormat::nv12:PixelFormat::bgra8;
                if(client.receive(unsupported,frame,pixels) || client.error!=Client::Error::configuration)check(E_UNEXPECTED);}
        }
        producer->stop();producer.reset();
        struct Negative {const wchar_t* mode;Client::Error error;bool wrong_pid;};
        std::uint64_t negative_epoch=10;
        for(const auto test:{Negative{L"",Client::Error::identity,true},Negative{L"--invalid-header",Client::Error::message,false},Negative{L"--stall",Client::Error::transport,false}}) {
            stage="isolated transport rejection";
            auto trial=std::make_unique<Producer>(executable,pipe,negative_epoch,test.mode);
            configure(pipe,sid,trial->pid+(test.wrong_pid?1:0),negative_epoch);trial->ready(pipe);
            rejected(test.error);trial->stop();++negative_epoch;
        }
        producer=std::make_unique<Producer>(executable,pipe,1);configure(pipe,sid,producer->pid,1);producer->ready(pipe);
        stage="create bridge camera";Camera camera;
        check(MFCreateVirtualCamera(MFVirtualCameraType_SoftwareCameraSource,MFVirtualCameraLifetime_Session,MFVirtualCameraAccess_CurrentUser,
            UCS_PROBE_FRIENDLY_NAME,UCS_PROBE_CLSID_TEXT,nullptr,0,&camera.value));check(camera.value->Start(nullptr));
        wil::unique_cotaskmem_string symbolic;UINT32 chars=0;check(camera.value->GetAllocatedString(MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE_VIDCAP_SYMBOLIC_LINK,&symbolic,&chars));
        wil::com_ptr_nothrow<IMFAttributes> attrs;check(MFCreateAttributes(&attrs,2));check(attrs->SetGUID(MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE,MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE_VIDCAP_GUID));
        check(attrs->SetString(MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE_VIDCAP_SYMBOLIC_LINK,symbolic.get()));
        wil::com_ptr_nothrow<IMFMediaSource> source;check(MFCreateDeviceSource(attrs.get(),&source));
        wil::com_ptr_nothrow<IMFAttributes> readerAttrs;check(MFCreateAttributes(&readerAttrs,1));check(readerAttrs->SetUINT32(MF_READWRITE_DISABLE_CONVERTERS,TRUE));
        wil::com_ptr_nothrow<IMFSourceReader> reader;check(MFCreateSourceReaderFromMediaSource(source.get(),readerAttrs.get(),&reader));
        if(rgb_output){wil::com_ptr_nothrow<IMFMediaType> selected;check(MFCreateMediaType(&selected));check(selected->SetGUID(MF_MT_MAJOR_TYPE,MFMediaType_Video));check(selected->SetGUID(MF_MT_SUBTYPE,MFVideoFormat_RGB32));check(reader->SetCurrentMediaType(MF_SOURCE_READER_FIRST_VIDEO_STREAM,nullptr,selected.get()));}
        check(reader->SetStreamSelection(MF_SOURCE_READER_FIRST_VIDEO_STREAM,TRUE));
        wil::com_ptr_nothrow<IMFMediaType> type;check(reader->GetCurrentMediaType(MF_SOURCE_READER_FIRST_VIDEO_STREAM,&type));
        UINT32 width=0,height=0;GUID subtype{};check(MFGetAttributeSize(type.get(),MF_MT_FRAME_SIZE,&width,&height));check(type->GetGUID(MF_MT_SUBTYPE,&subtype));
        if(width!=selected_mode.width || height!=selected_mode.height || subtype!=(rgb_output?MFVideoFormat_RGB32:MFVideoFormat_NV12))check(MF_E_INVALIDMEDIATYPE);
        UINT32 numerator=0,denominator=0;check(MFGetAttributeRatio(type.get(),MF_MT_FRAME_RATE,&numerator,&denominator));
        if(numerator!=selected_mode.fps_num || denominator!=selected_mode.fps_den)check(MF_E_INVALIDMEDIATYPE);
        unsigned advertised=0;
        for(DWORD index=0;;++index) {
            wil::com_ptr_nothrow<IMFMediaType> native;const auto hr=reader->GetNativeMediaType(MF_SOURCE_READER_FIRST_VIDEO_STREAM,index,&native);
            if(hr==MF_E_NO_MORE_TYPES)break;check(hr);
            UINT32 w=0,h=0,n=0,d=0;GUID format{};
            check(MFGetAttributeSize(native.get(),MF_MT_FRAME_SIZE,&w,&h));check(MFGetAttributeRatio(native.get(),MF_MT_FRAME_RATE,&n,&d));check(native->GetGUID(MF_MT_SUBTYPE,&format));
            if(w!=selected_mode.width || h!=selected_mode.height || n!=selected_mode.fps_num || d!=selected_mode.fps_den ||
               (format!=MFVideoFormat_RGB32 && format!=MFVideoFormat_NV12) ||
               !supports(selected_mode,format==MFVideoFormat_RGB32?PixelFormat::bgra8:PixelFormat::nv12))check(MF_E_INVALIDMEDIATYPE);
            if(++advertised>2)check(E_UNEXPECTED);
        }
        if(advertised!=(python_producer?1U:2U))check(E_UNEXPECTED);
        wil::com_ptr_nothrow<IMFMediaType> unsupportedType;check(MFCreateMediaType(&unsupportedType));check(type->CopyAllItems(unsupportedType.get()));
        check(MFSetAttributeSize(unsupportedType.get(),MF_MT_FRAME_SIZE,width+2,height));
        if(SUCCEEDED(reader->SetCurrentMediaType(MF_SOURCE_READER_FIRST_VIDEO_STREAM,nullptr,unsupportedType.get())))check(E_UNEXPECTED);
        LONGLONG last=-1;stage="producer pixels through camera";const auto first_ids=changing(reader.get(),last);
        producer->stop();producer.reset();stage="producer loss to black";black_after(reader.get(),last);
        producer=std::make_unique<Producer>(executable,pipe,2);configure(pipe,sid,producer->pid+1,2);producer->ready(pipe);
        stage="wrong producer identity rejected";Sleep(150);black_after(reader.get(),last);
        configure(pipe,sid,producer->pid,2);stage="new producer recovered";const auto recovered_ids=changing(reader.get(),last);
        producer->stop();producer.reset();black_after(reader.get(),last);
        producer=std::make_unique<Producer>(executable,pipe,3,L"--invalid-header");configure(pipe,sid,producer->pid,3);producer->ready(pipe);
        stage="malformed reply rejected";Sleep(150);black_after(reader.get(),last);producer->stop();producer.reset();
        stage="start stalled producer";producer=std::make_unique<Producer>(executable,pipe,4,L"--stall");configure(pipe,sid,producer->pid,4);producer->ready(pipe);
        stage="stalled peer deadline";Sleep(150);black_after(reader.get(),last);producer->stop();producer.reset();
        reader.reset();const auto shutdown=source->Shutdown();if(FAILED(shutdown) && shutdown!=MF_E_SHUTDOWN)check(shutdown);source.reset();
        stage="bridge cleanup";check(camera.cleanup());check_registry(registration.remove());if(own_camera_count())check(E_UNEXPECTED);
        std::cout<<"{\"status\":\"pass\",\"scope\":\"separate synthetic producer -> identity-checked local pipe -> MF virtual camera -> own consumer\",\"producer\":\""<<(python_producer?"python-app-publisher":"native")<<"\",\"format\":\""<<(rgb_output?"RGB32":"NV12")<<"\",\"samples_per_live_phase\":40,\"first_unique_producer_ids\":"<<first_ids
            <<",\"width\":"<<selected_mode.width<<",\"height\":"<<selected_mode.height<<",\"fps_num\":"<<selected_mode.fps_num<<",\"fps_den\":"<<selected_mode.fps_den<<",\"advertised_types\":"<<advertised<<",\"recovered_unique_producer_ids\":"<<recovered_ids<<",\"producer_loss_black\":true,\"wrong_pid_rejected\":true,\"malformed_reply_rejected\":true,\"stalled_peer_black\":true,\"reconnected\":true,\"camera_removed\":true,\"own_devices_remaining\":0,\"phone_capture\":false,\"personal_media_recorded\":false}\n";
        return 0;
    }catch(const winrt::hresult_error& error){std::cerr<<"Bridge failed at "<<stage<<":0x"<<std::hex<<static_cast<unsigned>(error.code().value)<<'\n';return 1;}
    catch(const std::exception& error){std::cerr<<"Bridge failed at "<<stage<<':'<<error.what()<<'\n';return 1;}
}
