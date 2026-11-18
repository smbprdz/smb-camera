#pragma once
#include "pipe_windows.hpp"
#include <shlobj.h>
#include <knownfolders.h>
#include <wintrust.h>
#include <softpub.h>
#include <filesystem>
namespace ucs::camera {
inline std::filesystem::path module_path() {
    wchar_t value[32768]{};const auto length=GetModuleFileNameW(nullptr,value,32768);
    if(!length || length>=32768)winrt::throw_hresult(E_UNEXPECTED);
    return std::filesystem::path(value);
}
inline std::filesystem::path install_directory() {
    PWSTR value=nullptr;winrt::check_hresult(SHGetKnownFolderPath(FOLDERID_ProgramFiles,0,nullptr,&value));
    std::filesystem::path result=std::filesystem::path(value)/L"SMB Camera Bridge";CoTaskMemFree(value);return result;
}
inline bool administrator() {
    SID_IDENTIFIER_AUTHORITY authority=SECURITY_NT_AUTHORITY;PSID sid=nullptr;BOOL yes=FALSE;
    if(!AllocateAndInitializeSid(&authority,2,SECURITY_BUILTIN_DOMAIN_RID,DOMAIN_ALIAS_RID_ADMINS,0,0,0,0,0,0,&sid))return false;
    const bool good=CheckTokenMembership(nullptr,sid,&yes)!=FALSE;FreeSid(sid);return good && yes;
}
inline bool trusted_signature(const std::filesystem::path& path) {
    WINTRUST_FILE_INFO file{sizeof(file)};file.pcwszFilePath=path.c_str();
    WINTRUST_DATA trust{sizeof(trust)};trust.dwUIChoice=WTD_UI_NONE;trust.fdwRevocationChecks=WTD_REVOKE_NONE;
    trust.dwUnionChoice=WTD_CHOICE_FILE;trust.pFile=&file;trust.dwStateAction=WTD_STATEACTION_VERIFY;
    GUID action=WINTRUST_ACTION_GENERIC_VERIFY_V2;const auto result=WinVerifyTrust(nullptr,&action,&trust);
    trust.dwStateAction=WTD_STATEACTION_CLOSE;WinVerifyTrust(nullptr,&action,&trust);return result==ERROR_SUCCESS;
}
inline void set_text(HKEY key,const wchar_t* name,const std::wstring& value) {
    const auto status=RegSetValueExW(key,name,0,REG_SZ,reinterpret_cast<const BYTE*>(value.c_str()),static_cast<DWORD>((value.size()+1)*sizeof(wchar_t)));
    if(status)winrt::throw_hresult(HRESULT_FROM_WIN32(status));
}
inline void setup(bool remove,bool ci) {
    if(!administrator())winrt::throw_hresult(E_ACCESSDENIED);
    if(ci) {
        wchar_t value[16]{};
        if(GetEnvironmentVariableW(L"GITHUB_ACTIONS",value,16)!=4 || wcscmp(value,L"true"))winrt::throw_hresult(E_ACCESSDENIED);
    }
    const auto root=install_directory();const auto binary=module_path();const auto package=binary.parent_path();
    const auto dll=root/L"SMBCameraSource.dll";const auto host=root/L"SMBCameraHost.exe";
    const auto sid=bridge::token_user_sid();const auto attributes=GetFileAttributesW(root.c_str());
    if(attributes!=INVALID_FILE_ATTRIBUTES && ((attributes&FILE_ATTRIBUTE_REPARSE_POINT) || !(attributes&FILE_ATTRIBUTE_DIRECTORY)))winrt::throw_hresult(E_ACCESSDENIED);
    if(!ci && (!trusted_signature(binary) || (!remove && !trusted_signature(package/L"SMBCameraSource.dll"))))winrt::throw_hresult(TRUST_E_SUBJECT_NOT_TRUSTED);
    HKEY existing=nullptr;const auto found=RegOpenKeyExW(HKEY_LOCAL_MACHINE,UCS_PROBE_REGKEY,0,KEY_READ|KEY_WOW64_64KEY,&existing);
    if(remove) {
        if(found==ERROR_FILE_NOT_FOUND)return;
        if(found)winrt::throw_hresult(HRESULT_FROM_WIN32(found));
        wchar_t registered[32768]{},owner[192]{},marker[80]{};DWORD bytes=sizeof(owner);
        auto status=RegGetValueW(existing,nullptr,L"UCS.Camera.OwnerSID",RRF_RT_REG_SZ,nullptr,owner,&bytes);
        bytes=sizeof(marker);if(!status)status=RegGetValueW(existing,nullptr,L"UCS.Probe.Owner",RRF_RT_REG_SZ,nullptr,marker,&bytes);
        bytes=sizeof(registered);if(!status)status=RegGetValueW(existing,L"InprocServer32",nullptr,RRF_RT_REG_SZ,nullptr,registered,&bytes);
        RegCloseKey(existing);
        if(status || wcscmp(owner,sid.c_str()) || wcscmp(marker,UCS_PROBE_CLSID_TEXT) || _wcsicmp(registered,dll.c_str()))winrt::throw_hresult(E_ACCESSDENIED);
        const auto mutex_name=L"Local\\SMB.CameraHost."+sid;
        bridge::Handle active(OpenMutexW(SYNCHRONIZE,FALSE,mutex_name.c_str()));if(active)winrt::throw_hresult(HRESULT_FROM_WIN32(ERROR_BUSY));
        wil::com_ptr_nothrow<IMFVirtualCamera> camera;
        winrt::check_hresult(MFCreateVirtualCamera(MFVirtualCameraType_SoftwareCameraSource,MFVirtualCameraLifetime_Session,
            MFVirtualCameraAccess_CurrentUser,UCS_PROBE_FRIENDLY_NAME,UCS_PROBE_CLSID_TEXT,nullptr,0,&camera));
        camera->Stop();const auto removed=camera->Remove();camera->Shutdown();camera.reset();
        if(FAILED(removed) && removed!=MF_E_NOT_FOUND)winrt::check_hresult(removed);
        status=RegDeleteTreeW(HKEY_LOCAL_MACHINE,UCS_PROBE_REGKEY);if(status && status!=ERROR_FILE_NOT_FOUND)winrt::throw_hresult(HRESULT_FROM_WIN32(status));
        HKEY runtime=nullptr;
        if(RegOpenKeyExW(HKEY_CURRENT_USER,UCS_CAMERA_RUNTIME_KEY,0,KEY_SET_VALUE|KEY_WOW64_64KEY,&runtime)==ERROR_SUCCESS) {
            RegDeleteValueW(runtime,L"Endpoint");RegCloseKey(runtime);
        }
        bool reboot=false;
        for(const auto& name:{L"SMBCameraSource.dll",L"SMBCameraHost.exe",L"LICENSES.txt"}) {
            const auto path=root/name;
            if(!DeleteFileW(path.c_str()) && GetLastError()!=ERROR_FILE_NOT_FOUND) {
                if(!MoveFileExW(path.c_str(),nullptr,MOVEFILE_DELAY_UNTIL_REBOOT))winrt::throw_hresult(HRESULT_FROM_WIN32(GetLastError()));reboot=true;
            }
        }
        if(!RemoveDirectoryW(root.c_str()) && GetLastError()!=ERROR_PATH_NOT_FOUND) {
            if(reboot)MoveFileExW(root.c_str(),nullptr,MOVEFILE_DELAY_UNTIL_REBOOT);
            else if(GetLastError()!=ERROR_DIR_NOT_EMPTY)winrt::throw_hresult(HRESULT_FROM_WIN32(GetLastError()));
        }
        std::cout<<"{\"status\":\"uninstalled\",\"own_registry_removed\":true,\"reboot_for_locked_files\":"<<(reboot?"true":"false")<<"}"<<std::endl;return;
    }
    if(!found){RegCloseKey(existing);winrt::throw_hresult(HRESULT_FROM_WIN32(ERROR_ALREADY_EXISTS));}
    if(found!=ERROR_FILE_NOT_FOUND)winrt::throw_hresult(HRESULT_FROM_WIN32(found));
    if(attributes!=INVALID_FILE_ATTRIBUTES)winrt::throw_hresult(HRESULT_FROM_WIN32(ERROR_ALREADY_EXISTS));
    if(!CreateDirectoryW(root.c_str(),nullptr))winrt::throw_hresult(HRESULT_FROM_WIN32(GetLastError()));
    bool owned_key=false;
    try {
        for(const auto& name:{L"SMBCameraSource.dll",L"SMBCameraHost.exe",L"LICENSES.txt"}) {
            const auto from=package/name,to=root/name;
            if(!CopyFileW(from.c_str(),to.c_str(),TRUE))winrt::throw_hresult(HRESULT_FROM_WIN32(GetLastError()));
        }
        HKEY key=nullptr;DWORD disposition=0;
        auto status=RegCreateKeyExW(HKEY_LOCAL_MACHINE,UCS_PROBE_REGKEY,0,nullptr,0,KEY_SET_VALUE|KEY_WOW64_64KEY,nullptr,&key,&disposition);
        if(status)winrt::throw_hresult(HRESULT_FROM_WIN32(status));
        if(disposition!=REG_CREATED_NEW_KEY){RegCloseKey(key);winrt::throw_hresult(HRESULT_FROM_WIN32(ERROR_ALREADY_EXISTS));}
        owned_key=true;
        try{set_text(key,L"UCS.Probe.Owner",UCS_PROBE_CLSID_TEXT);set_text(key,L"UCS.Camera.OwnerSID",sid);set_text(key,L"UCS.Camera.InstallDirectory",root.wstring());}
        catch(...){RegCloseKey(key);throw;}
        RegCloseKey(key);
        const auto subkey=std::wstring(UCS_PROBE_REGKEY)+L"\\InprocServer32";
        status=RegCreateKeyExW(HKEY_LOCAL_MACHINE,subkey.c_str(),0,nullptr,0,KEY_SET_VALUE|KEY_WOW64_64KEY,nullptr,&key,nullptr);
        if(status)winrt::throw_hresult(HRESULT_FROM_WIN32(status));
        try{set_text(key,nullptr,dll.wstring());set_text(key,L"ThreadingModel",L"Both");}catch(...){RegCloseKey(key);throw;}
        RegCloseKey(key);
        std::cout<<"{\"status\":\"installed\",\"scope\":\"one Windows account\",\"signature_required\":"<<(ci?"false":"true")<<"}"<<std::endl;
    }catch(...) {
        if(owned_key)RegDeleteTreeW(HKEY_LOCAL_MACHINE,UCS_PROBE_REGKEY);
        for(const auto& name:{L"SMBCameraSource.dll",L"SMBCameraHost.exe",L"LICENSES.txt"})DeleteFileW((root/name).c_str());
        RemoveDirectoryW(root.c_str());throw;
    }
}
}
