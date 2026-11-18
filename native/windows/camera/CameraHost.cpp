// Product lifecycle host. No video capture, encoder, SDK, network or secrets.
#include "pch.h"
#include "DeviceRegistration.h"
#include "pipe_windows.hpp"
#include <iostream>
#include <string>
#include <atomic>
#include <thread>
#include "CameraSetup.h"
using namespace ucs_lab;
namespace {
std::atomic<bool> quit=false;
BOOL WINAPI stopped(DWORD){quit=true;return TRUE;}
}
int wmain(int argc,wchar_t** argv) {
    if(argc!=2)return 2;
    const std::wstring action=argv[1];
    if(action!=L"--run" && action!=L"--remove" && action!=L"--install" && action!=L"--uninstall" && action!=L"--ci-install" && action!=L"--ci-uninstall")return 2;
    winrt::init_apartment(winrt::apartment_type::multi_threaded);
    try {
        check(MFStartup(MF_VERSION));struct MFGuard{~MFGuard(){MFShutdown();}} mf;
        if(action.find(L"install")!=std::wstring::npos){ucs::camera::setup(action.find(L"uninstall")!=std::wstring::npos,action.starts_with(L"--ci-"));return 0;}
        Camera camera;
        const bool remove=action==L"--remove";
        const auto mutex_name=L"Local\\SMB.CameraHost."+ucs::bridge::token_user_sid();
        ucs::bridge::Handle singleton(CreateMutexW(nullptr,FALSE,mutex_name.c_str()));
        if(!singleton || GetLastError()==ERROR_ALREADY_EXISTS)check(HRESULT_FROM_WIN32(ERROR_ALREADY_EXISTS));
        if(!remove) {
            ucs::bridge::Config config{};
            if(!ucs::bridge::read_config(config) || wcscmp(config.owner_sid,ucs::bridge::token_user_sid().c_str()))check(E_ACCESSDENIED);
        }
        check(MFCreateVirtualCamera(MFVirtualCameraType_SoftwareCameraSource,MFVirtualCameraLifetime_Session,
            MFVirtualCameraAccess_CurrentUser,UCS_PROBE_FRIENDLY_NAME,UCS_PROBE_CLSID_TEXT,nullptr,0,&camera.value));
        if(remove){check(camera.cleanup());std::cout<<"{\"status\":\"removed\"}\n";return 0;}
        check(camera.value->Start(nullptr));
        std::cout<<"{\"status\":\"ready\",\"scope\":\"current-user session camera\"}"<<std::endl;
        SetConsoleCtrlHandler(stopped,TRUE);
        HANDLE input=GetStdHandle(STD_INPUT_HANDLE);const auto kind=GetFileType(input);
        if(kind!=FILE_TYPE_PIPE)check(E_INVALIDARG);
        while(!quit) {
            DWORD available=0;
            if(!PeekNamedPipe(input,nullptr,0,nullptr,&available,nullptr)){quit=true;break;}
            if(available) {char command[32]{};DWORD count=0;if(!ReadFile(input,command,sizeof(command),&count,nullptr) || !count){quit=true;break;}
                // No parser/remote commands: any explicit stdin message stops.
                quit=true;break;
            }
            Sleep(100);
        }
        check(camera.cleanup());std::cout<<"{\"status\":\"stopped\",\"device_removed\":true}"<<std::endl;
        return 0;
    }catch(const winrt::hresult_error& error){std::cerr<<"Camera host:0x"<<std::hex<<static_cast<unsigned>(error.code().value)<<'\n';return 1;}
    catch(const std::exception& error){std::cerr<<"Camera host:"<<error.what()<<'\n';return 1;}
}
