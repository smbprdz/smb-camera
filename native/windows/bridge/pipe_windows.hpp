#pragma once
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#include <aclapi.h>
#include <sddl.h>
#include <string>
#include <vector>
#include <stdexcept>
#include <algorithm>
#include <optional>
#include "pipe_protocol.hpp"
#include "media_modes.hpp"
#include "BridgeId.h"
#include "../camera/Diagnostics.h"

namespace ucs::bridge {
struct Handle {
    HANDLE value=nullptr;
    Handle()=default;explicit Handle(HANDLE h):value(h){}
    Handle(const Handle&)=delete;Handle& operator=(const Handle&)=delete;
    ~Handle(){reset();}
    void reset(HANDLE h=nullptr) noexcept {if(value && value!=INVALID_HANDLE_VALUE)CloseHandle(value);value=h;}
    explicit operator bool()const noexcept{return value && value!=INVALID_HANDLE_VALUE;}
};
inline constexpr wchar_t pipe_prefix[]=L"\\\\.\\pipe\\UCS.FrameBridge.";
inline std::wstring ready_name(const std::wstring& pipe,std::uint64_t epoch) {
    return L"Local\\UCS.FrameBridge.Ready."+pipe.substr(std::wstring(pipe_prefix).size())+L"."+std::to_wstring(epoch);
}
struct Config {
    std::uint32_t magic=0x42534355,version=2,producer_pid=0,reserved=0;
    std::uint64_t epoch=0;
    MediaMode mode{};
    wchar_t pipe_name[128]{},owner_sid[192]{};
};
static_assert(sizeof(Config)==688);
inline bool valid_name(const std::wstring& name) {
    const std::wstring prefix=pipe_prefix;
    if(!name.starts_with(prefix) || name.size()!=prefix.size()+36)return false;
    return std::all_of(name.begin()+prefix.size(),name.end(),[](wchar_t c){return (c>=L'0'&&c<=L'9')||(c>=L'A'&&c<=L'F')||(c>=L'a'&&c<=L'f')||c==L'-';});
}
inline std::wstring token_user_sid() {
    Handle token;HANDLE raw=nullptr;
    if(!OpenProcessToken(GetCurrentProcess(),TOKEN_QUERY,&raw))throw std::runtime_error("Token identity unavailable");
    token.reset(raw);DWORD bytes=0;GetTokenInformation(token.value,TokenUser,nullptr,0,&bytes);
    std::vector<BYTE> buffer(bytes);
    if(!GetTokenInformation(token.value,TokenUser,buffer.data(),bytes,&bytes))throw std::runtime_error("Token identity read failed");
    wchar_t* text=nullptr;
    if(!ConvertSidToStringSidW(reinterpret_cast<TOKEN_USER*>(buffer.data())->User.Sid,&text))throw std::runtime_error("Token SID failed");
    std::wstring result=text;LocalFree(text);return result;
}
inline std::wstring service_sid(const wchar_t* name) {
    DWORD sid_bytes=0,domain_chars=0;SID_NAME_USE use{};
    LookupAccountNameW(nullptr,name,nullptr,&sid_bytes,nullptr,&domain_chars,&use);
    std::vector<BYTE> sid(sid_bytes);std::vector<wchar_t> domain(domain_chars);
    if(!sid_bytes || !LookupAccountNameW(nullptr,name,sid.data(),&sid_bytes,domain.data(),&domain_chars,&use))throw std::runtime_error("FrameServer identity unavailable");
    wchar_t* text=nullptr;if(!ConvertSidToStringSidW(sid.data(),&text))throw std::runtime_error("Service SID failed");
    std::wstring result=text;LocalFree(text);return result;
}
inline bool config_valid(const Config& c) {
    if(c.magic!=0x42534355 || c.version!=2 || c.reserved || !c.producer_pid || !c.epoch || !valid(c.mode) ||
       c.pipe_name[127] || c.owner_sid[191] || !valid_name(c.pipe_name))return false;
    PSID sid=nullptr;if(!ConvertStringSidToSidW(c.owner_sid,&sid))return false;
    const bool good=IsValidSid(sid)!=FALSE;LocalFree(sid);return good;
}
inline bool read_config(Config& c) {
    DWORD bytes=sizeof(c);
#ifdef UCS_DEVICE_PRODUCT
    // Installation binds this first product cut to one Windows account. The
    // account writes only its own public endpoint; services receive read access.
    wchar_t owner[192]{};DWORD owner_bytes=sizeof(owner);
    const auto bootstrap=RegGetValueW(HKEY_LOCAL_MACHINE,UCS_PROBE_REGKEY,L"UCS.Camera.OwnerSID",RRF_RT_REG_SZ|RRF_SUBKEY_WOW6464KEY,nullptr,owner,&owner_bytes);
    if(bootstrap!=ERROR_SUCCESS || !owner[0] || owner[191]){diagnose(L"bootstrap.read",HRESULT_FROM_WIN32(bootstrap?bootstrap:ERROR_INVALID_DATA));return false;}
    PSID owner_sid=nullptr;if(!ConvertStringSidToSidW(owner,&owner_sid))return false;LocalFree(owner_sid);
    const auto key=std::wstring(owner)+L"\\"+UCS_CAMERA_RUNTIME_KEY;
    const auto status=RegGetValueW(HKEY_USERS,key.c_str(),L"Endpoint",RRF_RT_REG_BINARY|RRF_SUBKEY_WOW6464KEY,nullptr,&c,&bytes);
    if(status!=ERROR_SUCCESS){diagnose(L"runtime.read",HRESULT_FROM_WIN32(status));return false;}
    const bool valid=bytes==sizeof(c) && config_valid(c) && wcscmp(c.owner_sid,owner)==0;
    if(!valid)diagnose(L"runtime.validate",E_INVALIDARG);return valid;
#else
    return RegGetValueW(HKEY_LOCAL_MACHINE,UCS_PROBE_REGKEY,L"UCS.Bridge.Config",RRF_RT_REG_BINARY|RRF_SUBKEY_WOW6464KEY,nullptr,&c,&bytes)==ERROR_SUCCESS && bytes==sizeof(c) && config_valid(c);
#endif
}
inline HANDLE create_server(const std::wstring& name) {
    if(!valid_name(name))throw std::runtime_error("Invalid pipe name");
    const auto owner=token_user_sid();
    // Clients receive specific data/attribute rights, never CREATE_PIPE_INSTANCE.
    const auto acl=L"O:"+owner+L"D:P(A;;GA;;;"+owner+L")(A;;GA;;;SY)(A;;0x00120183;;;"+
        service_sid(L"NT SERVICE\\FrameServer")+L")(A;;0x00120183;;;"+service_sid(L"NT SERVICE\\FrameServerMonitor")+L")";
    PSECURITY_DESCRIPTOR security=nullptr;
    if(!ConvertStringSecurityDescriptorToSecurityDescriptorW(acl.c_str(),SDDL_REVISION_1,&security,nullptr))throw std::runtime_error("Pipe ACL failed");
    SECURITY_ATTRIBUTES attributes{sizeof(attributes),security,FALSE};
    const auto h=CreateNamedPipeW(name.c_str(),PIPE_ACCESS_DUPLEX|FILE_FLAG_OVERLAPPED|FILE_FLAG_FIRST_PIPE_INSTANCE,
        PIPE_TYPE_MESSAGE|PIPE_READMODE_MESSAGE|PIPE_WAIT|PIPE_REJECT_REMOTE_CLIENTS,1,2*1024*1024,4096,1000,&attributes);
    const auto error=GetLastError();LocalFree(security);SetLastError(error);return h;
}
inline bool finish_io(HANDLE h,OVERLAPPED& op,BOOL immediate,DWORD& bytes,DWORD timeout) {
    if(immediate)return GetOverlappedResult(h,&op,&bytes,FALSE)!=FALSE;
    if(GetLastError()!=ERROR_IO_PENDING)return false;
    if(WaitForSingleObject(op.hEvent,timeout)!=WAIT_OBJECT_0) {
        CancelIoEx(h,&op);
        // Keep OVERLAPPED and its buffers alive until kernel cancellation completes.
        GetOverlappedResult(h,&op,&bytes,TRUE);return false;
    }
    return GetOverlappedResult(h,&op,&bytes,FALSE)!=FALSE;
}
inline bool connected(HANDLE pipe,DWORD timeout=1000) {
    Handle event(CreateEventW(nullptr,TRUE,FALSE,nullptr));if(!event)return false;
    OVERLAPPED op{};op.hEvent=event.value;DWORD bytes=0;
    const auto result=ConnectNamedPipe(pipe,&op);if(!result && GetLastError()==ERROR_PIPE_CONNECTED)return true;
    return finish_io(pipe,op,result,bytes,timeout);
}
inline bool read_request(HANDLE pipe,Request& request) {
    Handle event(CreateEventW(nullptr,TRUE,FALSE,nullptr));if(!event)return false;
    OVERLAPPED op{};op.hEvent=event.value;DWORD bytes=0;
    return finish_io(pipe,op,ReadFile(pipe,&request,sizeof(request),&bytes,&op),bytes,5000) && bytes==sizeof(request) && valid(request);
}
inline bool write_reply(HANDLE pipe,const std::vector<BYTE>& reply) {
    Handle event(CreateEventW(nullptr,TRUE,FALSE,nullptr));if(!event)return false;
    OVERLAPPED op{};op.hEvent=event.value;DWORD bytes=0;
    return finish_io(pipe,op,WriteFile(pipe,reply.data(),static_cast<DWORD>(reply.size()),&bytes,&op),bytes,1000) && bytes==reply.size();
}
inline bool verified_peer(HANDLE pipe,const Config& c) {
    ULONG pid=0;if(!GetNamedPipeServerProcessId(pipe,&pid) || pid!=c.producer_pid)return false;
    PSID actual=nullptr,expected=nullptr;PSECURITY_DESCRIPTOR descriptor=nullptr;
    const auto status=GetSecurityInfo(pipe,SE_KERNEL_OBJECT,OWNER_SECURITY_INFORMATION,&actual,nullptr,nullptr,nullptr,&descriptor);
    const bool parsed=ConvertStringSidToSidW(c.owner_sid,&expected)!=FALSE;
    const bool good=status==ERROR_SUCCESS && actual && parsed && EqualSid(actual,expected);
    if(expected)LocalFree(expected);if(descriptor)LocalFree(descriptor);return good;
}
class Client {
    Handle pipe_;Config config_{};ULONGLONG checked_=0,last_id_=0;
    std::vector<BYTE> reply_;
    std::optional<MediaMode> expected_mode_;
public:
    Client()=default;
    explicit Client(const MediaMode& expected):expected_mode_(expected){}
    enum class Error {none,configuration,connection,identity,mode,transport,message};
    Error error=Error::none;
    bool receive(const Request& request,FrameDescriptor& frame,const BYTE*& pixels) {
        pixels=nullptr;error=Error::configuration;if(!valid(request))return false;
        const auto now=GetTickCount64();
        if(!checked_ || now-checked_>=100) {
            checked_=now;Config next{};
            if(!read_config(next)){pipe_.reset();config_={};return false;}
            if(std::memcmp(&next,&config_,sizeof(next))){pipe_.reset();config_=next;last_id_=0;}
        }
        if(!config_valid(config_))return false;
        if(expected_mode_ && std::memcmp(&*expected_mode_,&config_.mode,sizeof(MediaMode)))return false;
        if(request.width!=config_.mode.width || request.height!=config_.mode.height || !supports(config_.mode,request.format))return false;
        if(!pipe_) {
            constexpr DWORD rights=FILE_READ_DATA|FILE_WRITE_DATA|FILE_READ_ATTRIBUTES|FILE_WRITE_ATTRIBUTES|READ_CONTROL|SYNCHRONIZE;
            pipe_.reset(CreateFileW(config_.pipe_name,rights,0,nullptr,OPEN_EXISTING,FILE_FLAG_OVERLAPPED|SECURITY_SQOS_PRESENT|SECURITY_IDENTIFICATION,nullptr));
            if(!pipe_){error=Error::connection;return false;}
            if(!verified_peer(pipe_.value,config_)){error=Error::identity;pipe_.reset();return false;}
            DWORD mode=PIPE_READMODE_MESSAGE;if(!SetNamedPipeHandleState(pipe_.value,&mode,nullptr,nullptr)){error=Error::mode;pipe_.reset();return false;}
        }
        const auto size=sizeof(Reply)+sizeof(FrameDescriptor)+payload_size(request);
        reply_.resize(static_cast<std::size_t>(size));
        Handle event(CreateEventW(nullptr,TRUE,FALSE,nullptr));if(!event)return false;
        OVERLAPPED op{};op.hEvent=event.value;DWORD bytes=0;
        const auto result=TransactNamedPipe(pipe_.value,const_cast<Request*>(&request),sizeof(request),reply_.data(),static_cast<DWORD>(reply_.size()),&bytes,&op);
        if(!finish_io(pipe_.value,op,result,bytes,50) || bytes<sizeof(Reply)+sizeof(frame)){error=Error::transport;pipe_.reset();return false;}
        Reply envelope{};std::memcpy(&envelope,reply_.data(),sizeof(envelope));std::memcpy(&frame,reply_.data()+sizeof(envelope),sizeof(frame));
        if(!validate_reply(request,envelope,frame,bytes,config_.epoch,GetTickCount64()) || frame.frame_id<last_id_){error=Error::message;pipe_.reset();return false;}
        error=Error::none;last_id_=frame.frame_id;pixels=reply_.data()+sizeof(envelope)+sizeof(frame);return true;
    }
};
}
