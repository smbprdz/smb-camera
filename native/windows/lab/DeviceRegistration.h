// Own reusable temporary-device ownership and cleanup helpers.
#pragma once
#include "pch.h"
#include "NativeId.h"
#include <string_view>
namespace ucs_lab {
inline void check(HRESULT hr){winrt::check_hresult(hr);}
inline void check_registry(LSTATUS status){if(status!=ERROR_SUCCESS)check(HRESULT_FROM_WIN32(status));}
inline unsigned own_camera_count() {
    wil::com_ptr_nothrow<IMFAttributes> attrs;check(MFCreateAttributes(&attrs,1));
    check(attrs->SetGUID(MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE,MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE_VIDCAP_GUID));
    IMFActivate** devices=nullptr;UINT32 count=0;check(MFEnumDeviceSources(attrs.get(),&devices,&count));
    unsigned found=0;
    for(UINT32 i=0;i<count;++i){
        wil::unique_cotaskmem_string name;UINT32 length=0;
        if(SUCCEEDED(devices[i]->GetAllocatedString(MF_DEVSOURCE_ATTRIBUTE_FRIENDLY_NAME,&name,&length)) &&
           std::wstring_view(name.get()).starts_with(UCS_PROBE_FRIENDLY_NAME))++found;
        devices[i]->Release();
    }
    CoTaskMemFree(devices);return found;
}
inline LSTATUS remove_verified_key(const wchar_t* dll) {
    wchar_t owner[80]{};DWORD size=sizeof(owner);
    auto status=RegGetValueW(HKEY_LOCAL_MACHINE,UCS_PROBE_REGKEY,L"UCS.Probe.Owner",RRF_RT_REG_SZ|RRF_SUBKEY_WOW6464KEY,nullptr,owner,&size);
    if(status==ERROR_FILE_NOT_FOUND)return ERROR_SUCCESS;
    if(status!=ERROR_SUCCESS || wcscmp(owner,UCS_PROBE_CLSID_TEXT)!=0)return ERROR_ACCESS_DENIED;
    wchar_t recorded_dll[32768]{};size=sizeof(recorded_dll);
    const auto key=std::wstring(UCS_PROBE_REGKEY)+L"\\InprocServer32";
    status=RegGetValueW(HKEY_LOCAL_MACHINE,key.c_str(),nullptr,RRF_RT_REG_SZ|RRF_SUBKEY_WOW6464KEY,nullptr,recorded_dll,&size);
    if(status!=ERROR_SUCCESS || _wcsicmp(dll,recorded_dll)!=0)return ERROR_ACCESS_DENIED;
    return RegDeleteTreeW(HKEY_LOCAL_MACHINE,UCS_PROBE_REGKEY);
}
struct Registration {
    bool owned=false;
    explicit Registration(const wchar_t* dll) {
        HKEY existing=nullptr;
        if(RegOpenKeyExW(HKEY_LOCAL_MACHINE,UCS_PROBE_REGKEY,0,KEY_READ|KEY_WOW64_64KEY,&existing)==ERROR_SUCCESS) {
            RegCloseKey(existing);check(HRESULT_FROM_WIN32(ERROR_ALREADY_EXISTS));
        }
        HKEY key=nullptr;DWORD disposition=0;
        check_registry(RegCreateKeyExW(HKEY_LOCAL_MACHINE,UCS_PROBE_REGKEY,0,nullptr,0,KEY_WRITE|KEY_READ|KEY_WOW64_64KEY,nullptr,&key,&disposition));
        RegCloseKey(key);
        if(disposition!=REG_CREATED_NEW_KEY)check(HRESULT_FROM_WIN32(ERROR_ALREADY_EXISTS));
        owned=true;
        try {
            check_registry(RegOpenKeyExW(HKEY_LOCAL_MACHINE,UCS_PROBE_REGKEY,0,KEY_SET_VALUE|KEY_WOW64_64KEY,&key));
            const auto marker=RegSetValueExW(key,L"UCS.Probe.Owner",0,REG_SZ,reinterpret_cast<const BYTE*>(UCS_PROBE_CLSID_TEXT),sizeof(UCS_PROBE_CLSID_TEXT));
            RegCloseKey(key);check_registry(marker);
            const auto subkey=std::wstring(UCS_PROBE_REGKEY)+L"\\InprocServer32";
            check_registry(RegCreateKeyExW(HKEY_LOCAL_MACHINE,subkey.c_str(),0,nullptr,0,KEY_SET_VALUE|KEY_WOW64_64KEY,nullptr,&key,nullptr));
            struct Close {HKEY key;~Close(){RegCloseKey(key);}} close{key};
            const auto bytes=static_cast<DWORD>((wcslen(dll)+1)*sizeof(wchar_t));
            check_registry(RegSetValueExW(key,nullptr,0,REG_SZ,reinterpret_cast<const BYTE*>(dll),bytes));
            constexpr wchar_t threading[]=L"Both";
            check_registry(RegSetValueExW(key,L"ThreadingModel",0,REG_SZ,reinterpret_cast<const BYTE*>(threading),sizeof(threading)));
        }catch(...){remove();throw;}
    }
    LSTATUS remove() noexcept {
        if(!owned)return ERROR_SUCCESS;
        const auto status=RegDeleteTreeW(HKEY_LOCAL_MACHINE,UCS_PROBE_REGKEY);
        if(status==ERROR_SUCCESS || status==ERROR_FILE_NOT_FOUND){owned=false;return ERROR_SUCCESS;}
        return status;
    }
    ~Registration(){if(owned)remove();}
};
struct Camera {
    wil::com_ptr_nothrow<IMFVirtualCamera> value;
    HRESULT cleanup() noexcept {
        if(!value)return S_OK;
        value->Stop();const auto removed=value->Remove();value->Shutdown();value.reset();return removed;
    }
    ~Camera(){cleanup();}
};
}
