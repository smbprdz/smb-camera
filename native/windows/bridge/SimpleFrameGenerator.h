// Interface adapted from the MIT Microsoft sample, Copyright Microsoft Corporation.
// Own IPC implementation; see docs/licenses/Microsoft-Windows-Camera-LICENSE.txt.
#pragma once
#include <memory>
#include <chrono>
namespace ucs::bridge {class Client;}
class SimpleFrameGenerator {
public:
    SimpleFrameGenerator() noexcept;
    ~SimpleFrameGenerator();
    HRESULT Initialize(IMFMediaType* type);
    HRESULT CreateFrame(BYTE* data,DWORD bytes,LONG pitch,ULONG mask);
    LONGLONG FrameDuration() const noexcept {return duration_;}
private:
    UINT32 width_=0,height_=0;GUID subtype_=GUID_NULL;
    LONGLONG duration_=333333;
    std::chrono::steady_clock::time_point next_output_{};
    std::unique_ptr<ucs::bridge::Client> client_;
};
