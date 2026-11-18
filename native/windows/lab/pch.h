#pragma once
#define NOMINMAX
#include <windows.h>
#include <unknwn.h>
#include <ole2.h>
#include <propvarutil.h>
#include <initguid.h>
#include <devpropdef.h>
#include <devpkey.h>
#include <cfgmgr32.h>
#include <ks.h>
#include <ksproxy.h>
#include <ksmedia.h>
#include <mfapi.h>
#include <mfidl.h>
#include <mfobjects.h>
#include <mferror.h>
#include <mfreadwrite.h>
#include <mfvirtualcamera.h>
#include <nserror.h>
#include <d3d9types.h>
#include <functional>
#include <wil/cppwinrt.h>
#include <wil/result.h>
#include <wil/com.h>
#include <winrt/Windows.ApplicationModel.h>
#define DEBUG_MSG(...) ((void)0)
#include "VirtualCameraMediaSource.h"
#include "SimpleFrameGenerator.h"
#include "SimpleMediaSource.h"
#include "SimpleMediaStream.h"

// Adapted helper from the MIT Microsoft sample; original copyright/license is
// preserved next to this isolated experiment. No original snapshot is changed.
namespace wilEx {
    template<typename T>
    wil::unique_cotaskmem_array_ptr<T> make_unique_cotaskmem_array(size_t count) {
        wil::unique_cotaskmem_array_ptr<T> result;
        using Element=typename wil::details::element_traits<T>::type;
        if(count>SIZE_MAX/sizeof(Element))return result;
        const auto bytes=sizeof(Element)*count;
        void* data=CoTaskMemAlloc(bytes);
        if(data){ZeroMemory(data,bytes);result.reset(reinterpret_cast<Element*>(data),count);}
        return result;
    }
}
namespace winrt {
    template<> bool is_guid_of<IMFMediaSourceEx>(guid const& id) noexcept;
    template<> bool is_guid_of<IMFMediaStream2>(guid const& id) noexcept;
    template<> bool is_guid_of<IMFActivate>(guid const& id) noexcept;
}
