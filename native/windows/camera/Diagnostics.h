#pragma once
#include <windows.h>
#include <cstdio>
#include <string>
namespace ucs::bridge {
inline HRESULT diagnose(const wchar_t* stage,HRESULT result) noexcept {
#ifdef UCS_DEVICE_PRODUCT
    if(FAILED(result)) {
        wchar_t message[192]{};swprintf_s(message,L"SMB Camera %s: 0x%08X",stage,static_cast<unsigned>(result));
        const auto source=RegisterEventSourceW(nullptr,L"SMBCamera");
        if(source){const wchar_t* values[]={message};ReportEventW(source,EVENTLOG_ERROR_TYPE,0,1,nullptr,1,0,values,nullptr);DeregisterEventSource(source);}
        // Optional bounded developer trace. The directory exists only when the
        // CI installer creates its explicit user/service ACL. No payload data.
        wchar_t base[32768]{};
        if(GetEnvironmentVariableW(L"ProgramData",base,32768)>0) {
            const auto path=std::wstring(base)+L"\\SMB Camera Bridge Diagnostics\\service-errors.log";
            HANDLE file=CreateFileW(path.c_str(),FILE_APPEND_DATA|FILE_READ_ATTRIBUTES,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,nullptr,OPEN_ALWAYS,FILE_ATTRIBUTE_NORMAL,nullptr);
            if(file!=INVALID_HANDLE_VALUE) {
                LARGE_INTEGER size{};
                if(GetFileSizeEx(file,&size) && size.QuadPart<65536){char line[400]{};const int length=snprintf(line,sizeof(line),"pid=%lu %ls\r\n",GetCurrentProcessId(),message);DWORD written=0;if(length>0 && length<sizeof(line))WriteFile(file,line,length,&written,nullptr);}
                CloseHandle(file);
            }
        }
    }
#endif
    return result;
}
#ifdef UCS_DEVICE_PRODUCT
inline void __stdcall log_failure(const wil::FailureInfo& failure) noexcept {
    wchar_t stage[160]{};const char* file=failure.pszFile?failure.pszFile:"unknown";
    const char* last=file;for(const char* p=file;*p;++p)if(*p=='/'||*p=='\\')last=p+1;
    swprintf_s(stage,L"WIL %hs:%u",last,failure.uLineNumber);diagnose(stage,failure.hr);
}
#endif
}
