#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <sdkddkver.h>
#include <windows.h>
#include <mfapi.h>
#include <mfidl.h>
#include <mfvirtualcamera.h>
#include <d3d11.h>
#include <dxgi.h>
#include <wrl/client.h>
#include <iostream>
#include <string>
#include <type_traits>

using Microsoft::WRL::ComPtr;
static_assert(_MSVC_LANG>=202002L);
static_assert(std::is_pointer_v<decltype(&MFCreateVirtualCamera)>);

std::string utf8(const wchar_t* text) {
    const int count=WideCharToMultiByte(CP_UTF8,0,text,-1,nullptr,0,nullptr,nullptr);
    if(count<=1)return {};
    std::string result(static_cast<std::size_t>(count),'\0');
    WideCharToMultiByte(CP_UTF8,0,text,-1,result.data(),count,nullptr,nullptr);
    result.pop_back();return result;
}
std::string quoted(const std::string& value) {
    std::string result="\"";
    for(char c:value) {
        if(c=='\\' || c=='\"')result+='\\';
        if(static_cast<unsigned char>(c)>=32)result+=c;
    }
    return result+'\"';
}
int fail(const char* stage,HRESULT hr) {
    std::cout<<"{\"status\":\"failed\",\"stage\":"<<quoted(stage)<<",\"hresult\":\"0x"<<std::hex<<static_cast<unsigned long>(hr)<<"\"}\n";
    return 1;
}
int main() {
    const HRESULT com=CoInitializeEx(nullptr,COINIT_MULTITHREADED);
    if(FAILED(com))return fail("COM startup",com);
    struct ComGuard {~ComGuard(){CoUninitialize();}} com_guard;
    const HRESULT startup=MFStartup(MF_VERSION,MFSTARTUP_NOSOCKET);
    if(FAILED(startup))return fail("Media Foundation startup",startup);
    struct MFGuard {~MFGuard(){MFShutdown();}} mf_guard;
    ComPtr<IMFAttributes> attributes;
    HRESULT hr=MFCreateAttributes(&attributes,2);
    if(FAILED(hr))return fail("MF attributes",hr);
    hr=MFSetAttributeSize(attributes.Get(),MF_MT_FRAME_SIZE,1920,1080);
    if(FAILED(hr))return fail("MF dimensions",hr);
    UINT32 width=0,height=0;hr=MFGetAttributeSize(attributes.Get(),MF_MT_FRAME_SIZE,&width,&height);
    if(FAILED(hr) || width!=1920 || height!=1080)return fail("MF dimensions roundtrip",FAILED(hr)?hr:E_UNEXPECTED);
    HMODULE virtual_module=LoadLibraryExW(L"mfsensorgroup.dll",nullptr,LOAD_LIBRARY_SEARCH_SYSTEM32);
    const bool virtual_export=virtual_module && GetProcAddress(virtual_module,"MFCreateVirtualCamera")!=nullptr;
    if(virtual_module)FreeLibrary(virtual_module);
    if(!virtual_export)return fail("virtual camera export",HRESULT_FROM_WIN32(ERROR_PROC_NOT_FOUND));
    ComPtr<ID3D11Device> device;ComPtr<ID3D11DeviceContext> context;
    D3D_FEATURE_LEVEL feature{};
    constexpr D3D_FEATURE_LEVEL requested[]={D3D_FEATURE_LEVEL_11_1,D3D_FEATURE_LEVEL_11_0};
    hr=D3D11CreateDevice(nullptr,D3D_DRIVER_TYPE_HARDWARE,nullptr,D3D11_CREATE_DEVICE_BGRA_SUPPORT,
        requested,static_cast<UINT>(std::size(requested)),D3D11_SDK_VERSION,&device,&feature,&context);
    if(FAILED(hr))return fail("D3D11 hardware device",hr);
    ComPtr<IDXGIDevice> dxgi;hr=device.As(&dxgi);
    if(FAILED(hr))return fail("DXGI device",hr);
    ComPtr<IDXGIAdapter> adapter;hr=dxgi->GetAdapter(&adapter);
    if(FAILED(hr))return fail("DXGI adapter",hr);
    DXGI_ADAPTER_DESC adapter_desc{};hr=adapter->GetDesc(&adapter_desc);
    if(FAILED(hr))return fail("DXGI adapter description",hr);
    D3D11_TEXTURE2D_DESC desc{};desc.Width=64;desc.Height=64;desc.MipLevels=1;desc.ArraySize=1;
    desc.Format=DXGI_FORMAT_B8G8R8A8_UNORM;desc.SampleDesc.Count=1;desc.Usage=D3D11_USAGE_DEFAULT;
    desc.BindFlags=D3D11_BIND_SHADER_RESOURCE|D3D11_BIND_RENDER_TARGET;
    ComPtr<ID3D11Texture2D> texture;hr=device->CreateTexture2D(&desc,nullptr,&texture);
    if(FAILED(hr))return fail("D3D11 texture",hr);
    std::cout<<std::boolalpha<<"{\"status\":\"pass\",\"scope\":\"native platform probe, no camera device created or registered\","
        <<"\"msvc_full_version\":"<<_MSC_FULL_VER<<",\"cpp_standard\":"<<_MSVC_LANG
        <<",\"media_foundation\":true,\"virtual_camera_api_present\":"<<virtual_export
        <<",\"d3d11_hardware_device\":true,\"adapter\":"<<quoted(utf8(adapter_desc.Description))
        <<",\"adapter_vendor\":"<<adapter_desc.VendorId<<",\"feature_level\":"<<feature
        <<",\"texture_size\":[64,64],\"camera_registered\":false,\"phone_capture\":false}\n";
    return 0;
}
