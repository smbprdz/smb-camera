// Own isolated test component, not an installed product camera.
#include "pch.h"
#include "NativeActivate.h"
#include "NativeId.h"
#include <atomic>
#ifdef UCS_DEVICE_PRODUCT
#include "../camera/Diagnostics.h"
#endif
namespace {
std::atomic<unsigned> server_locks{0};
struct Factory : winrt::implements<Factory,IClassFactory> {
    HRESULT STDMETHODCALLTYPE CreateInstance(IUnknown* outer,REFIID iid,void** result) noexcept override {
        if(!result)return E_POINTER;*result=nullptr;
        if(outer)return CLASS_E_NOAGGREGATION;
        try {return winrt::make_self<ucs_probe::NativeActivate>()->QueryInterface(iid,result);}
        catch(...){return winrt::to_hresult();}
    }
    HRESULT STDMETHODCALLTYPE LockServer(BOOL lock) noexcept override {
        if(lock){++server_locks;return S_OK;}
        auto current=server_locks.load();
        while(current && !server_locks.compare_exchange_weak(current,current-1)){}
        return current?S_OK:E_UNEXPECTED;
    }
};
}
extern "C" HRESULT __stdcall DllGetClassObject(REFCLSID clsid,REFIID iid,void** result) {
#ifdef UCS_DEVICE_PRODUCT
    wil::SetResultLoggingCallback(ucs::bridge::log_failure);
#endif
    if(!result)return E_POINTER;*result=nullptr;
    if(clsid!=UCS_PROBE_CLSID)return CLASS_E_CLASSNOTAVAILABLE;
    try{return winrt::make_self<Factory>()->QueryInterface(iid,result);}catch(...){return winrt::to_hresult();}
}
extern "C" HRESULT __stdcall DllCanUnloadNow() {
    return !winrt::get_module_lock() && server_locks.load()==0?S_OK:S_FALSE;
}
