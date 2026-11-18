"""Derive the MIT stream from verified source; never edit the pinned cache."""
import json
from pathlib import Path
if __package__:
    from .prepare_native_lab import ROOT,DEST,main as prepare,verify_source
else:
    from prepare_native_lab import ROOT,DEST,main as prepare,verify_source

def derive(data,row):
    verify_source(data,row)
    text=data.decode('utf-8').replace('\r\n','\n')
    start='        const uint32_t NUM_MEDIATYPES = 2;'
    end='        RETURN_IF_FAILED(MFCreateAttributes(&m_spAttributes, 10));'
    duration='sample->SetSampleDuration(333333)'
    if text.count(start)!=1 or text.count(end)!=1 or text.count(duration)!=1:
        raise ValueError('Pinned stream anchors changed')
    first=text.index(start);last=text.index(end,first)
    replacement='''        ucs::bridge::Config bridgeConfig{};
        RETURN_HR_IF(MF_E_INVALIDMEDIATYPE, !ucs::bridge::read_config(bridgeConfig));
        const uint32_t NUM_MEDIATYPES = bridgeConfig.mode.formats == 3 ? 2 : 1;
        auto mediaTypeList = wilEx::make_unique_cotaskmem_array<wil::com_ptr_nothrow<IMFMediaType>>(NUM_MEDIATYPES);
        uint32_t modeIndex=0;
        for(auto format : {ucs::native::PixelFormat::nv12, ucs::native::PixelFormat::bgra8}) {
            if(ucs::bridge::supports(bridgeConfig.mode,format))
                RETURN_IF_FAILED(ucs::bridge::make_media_type(bridgeConfig.mode,format,&mediaTypeList[modeIndex++]));
        }

'''
    text=text[:first]+replacement+text[last:]
    text=text.replace('#include "pch.h"','#include "pch.h"\n#include "media_types.hpp"',1)
    text=text.replace(duration,'sample->SetSampleDuration(m_spFrameGenerator->FrameDuration())')
    for operation,label in [('m_spSampleAllocator->InitializeSampleAllocator(10, m_spMediaType.get())','allocator.initialize'),('m_spFrameGenerator->Initialize(m_spMediaType.get())','generator.initialize')]:
        if text.count(operation)>1:raise ValueError('Ambiguous stream operation')
        text=text.replace(operation,'ucs::bridge::diagnose(L"'+label+'", '+operation+')')
    text=text.replace('RETURN_HR_IF_NULL_MSG(E_POINTER, m_spSampleAllocator, "Sample allocator is not set");',
        'RETURN_IF_FAILED(ucs::bridge::diagnose(L"allocator.missing", m_spSampleAllocator ? S_OK : E_POINTER));')
    return text.encode('utf-8')

def main():
    prepare()
    lock=json.loads((ROOT/'docs/NATIVE-LAB.lock.json').read_text(encoding='utf-8'))
    row=next(x for x in lock['files'] if x['path'].endswith('/SimpleMediaStream.cpp'))
    data=(DEST/'src/SimpleMediaStream.cpp').read_bytes()
    target=ROOT/'runtime/native-bridge/SimpleMediaStream.cpp';target.parent.mkdir(parents=True,exist_ok=True)
    target.write_bytes(derive(data,row))
    print(json.dumps({'status':'derived_verified_MIT_stream','path':str(target),'pinned_cache_modified':False}))

if __name__=='__main__':main()
