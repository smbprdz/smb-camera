// Copyright (C) Microsoft Corporation. All rights reserved.
// IMFAttributes methods adapted underMIT; own activation/lifecycle wrapper below.
#include "pch.h"
#include "NativeActivate.h"
namespace ucs_probe {
IFACEMETHODIMP NativeActivate::ActivateObject(REFIID iid,void** out) {
 if(!out)return E_POINTER;*out=nullptr;
 try {if(!source_){source_=winrt::make_self<winrt::WindowsSample::implementation::SimpleMediaSource>();winrt::check_hresult(source_->Initialize(m_spActivateAttributes.get()));}return source_->QueryInterface(iid,out);}catch(...){return winrt::to_hresult();}
}
IFACEMETHODIMP NativeActivate::ShutdownObject(){if(source_){source_->Shutdown();source_=nullptr;}return S_OK;}
IFACEMETHODIMP NativeActivate::DetachObject(){source_=nullptr;return S_OK;}
IFACEMETHODIMP NativeActivate::GetItem(_In_ REFGUID guidKey, _Inout_opt_  PROPVARIANT* pValue)
    {
        if (!m_spActivateAttributes)
            RETURN_IF_FAILED(MFCreateAttributes(&m_spActivateAttributes, 1));
        return m_spActivateAttributes->GetItem(guidKey, pValue);
    }
IFACEMETHODIMP NativeActivate::GetItemType(_In_ REFGUID guidKey, _Out_ MF_ATTRIBUTE_TYPE* pType)
    {
        if (!m_spActivateAttributes)
            RETURN_IF_FAILED(MFCreateAttributes(&m_spActivateAttributes, 1));
        return m_spActivateAttributes->GetItemType(guidKey, pType);
    }
IFACEMETHODIMP NativeActivate::CompareItem(_In_ REFGUID guidKey, _In_ REFPROPVARIANT Value, _Out_ BOOL* pbResult)
    {
        if (!m_spActivateAttributes)
            RETURN_IF_FAILED(MFCreateAttributes(&m_spActivateAttributes, 1));
        return m_spActivateAttributes->CompareItem(guidKey, Value, pbResult);
    }
IFACEMETHODIMP NativeActivate::Compare(_In_ IMFAttributes* pTheirs, _In_ MF_ATTRIBUTES_MATCH_TYPE MatchType, _Out_ BOOL* pbResult)
    {
        if (!m_spActivateAttributes)
            RETURN_IF_FAILED(MFCreateAttributes(&m_spActivateAttributes, 1));
        return m_spActivateAttributes->Compare(pTheirs, MatchType, pbResult);
    }
IFACEMETHODIMP NativeActivate::GetUINT32(_In_ REFGUID guidKey, _Out_ UINT32* punValue)
    {
        if (!m_spActivateAttributes)
            RETURN_IF_FAILED(MFCreateAttributes(&m_spActivateAttributes, 1));
        return m_spActivateAttributes->GetUINT32(guidKey, punValue);
    }
IFACEMETHODIMP NativeActivate::GetUINT64(_In_ REFGUID guidKey, _Out_ UINT64* punValue)
    {
        if (!m_spActivateAttributes)
            RETURN_IF_FAILED(MFCreateAttributes(&m_spActivateAttributes, 1));
        return m_spActivateAttributes->GetUINT64(guidKey, punValue);
    }
IFACEMETHODIMP NativeActivate::GetDouble(_In_ REFGUID guidKey, _Out_ double* pfValue)
    {
        if (!m_spActivateAttributes)
            RETURN_IF_FAILED(MFCreateAttributes(&m_spActivateAttributes, 1));
        return m_spActivateAttributes->GetDouble(guidKey, pfValue);
    }
IFACEMETHODIMP NativeActivate::GetGUID(_In_ REFGUID guidKey, _Out_ GUID* pguidValue)
    {
        if (!m_spActivateAttributes)
            RETURN_IF_FAILED(MFCreateAttributes(&m_spActivateAttributes, 1));
        return m_spActivateAttributes->GetGUID(guidKey, pguidValue);
    }
IFACEMETHODIMP NativeActivate::GetStringLength(_In_ REFGUID guidKey, _Out_ UINT32* pcchLength)
    {
        if (!m_spActivateAttributes)
            RETURN_IF_FAILED(MFCreateAttributes(&m_spActivateAttributes, 1));
        return m_spActivateAttributes->GetStringLength(guidKey, pcchLength);
    }
IFACEMETHODIMP NativeActivate::GetString(_In_ REFGUID guidKey, _Out_writes_(cchBufSize) LPWSTR pwszValue, _In_ UINT32 cchBufSize, _Inout_opt_ UINT32* pcchLength)
    {
        if (!m_spActivateAttributes)
            RETURN_IF_FAILED(MFCreateAttributes(&m_spActivateAttributes, 1));
        return m_spActivateAttributes->GetString(guidKey, pwszValue, cchBufSize, pcchLength);
    }
IFACEMETHODIMP NativeActivate::GetAllocatedString(_In_ REFGUID guidKey, _Out_writes_(*pcchLength + 1) LPWSTR* ppwszValue, _Inout_  UINT32* pcchLength)
    {
        if (!m_spActivateAttributes)
            RETURN_IF_FAILED(MFCreateAttributes(&m_spActivateAttributes, 1));
        return m_spActivateAttributes->GetAllocatedString(guidKey, ppwszValue, pcchLength);
    }
IFACEMETHODIMP NativeActivate::GetBlobSize(_In_ REFGUID guidKey, _Out_ UINT32* pcbBlobSize)
    {
        if (!m_spActivateAttributes)
            RETURN_IF_FAILED(MFCreateAttributes(&m_spActivateAttributes, 1));
        return m_spActivateAttributes->GetBlobSize(guidKey, pcbBlobSize);
    }
IFACEMETHODIMP NativeActivate::GetBlob(_In_ REFGUID  guidKey, _Out_writes_(cbBufSize) UINT8* pBuf, UINT32 cbBufSize, _Inout_  UINT32* pcbBlobSize)
    {
        if (!m_spActivateAttributes)
            RETURN_IF_FAILED(MFCreateAttributes(&m_spActivateAttributes, 1));
        return m_spActivateAttributes->GetBlob(guidKey, pBuf, cbBufSize, pcbBlobSize);
    }
IFACEMETHODIMP NativeActivate::GetAllocatedBlob(__RPC__in REFGUID guidKey, __RPC__deref_out_ecount_full_opt(*pcbSize) UINT8** ppBuf, __RPC__out UINT32* pcbSize)
    {
        if (!m_spActivateAttributes)
            RETURN_IF_FAILED(MFCreateAttributes(&m_spActivateAttributes, 1));
        return m_spActivateAttributes->GetAllocatedBlob(guidKey, ppBuf, pcbSize);
    }
IFACEMETHODIMP NativeActivate::GetUnknown(__RPC__in REFGUID guidKey, __RPC__in REFIID riid, __RPC__deref_out_opt LPVOID* ppv)
    {
        if (!m_spActivateAttributes)
            RETURN_IF_FAILED(MFCreateAttributes(&m_spActivateAttributes, 1));
        return m_spActivateAttributes->GetUnknown(guidKey, riid, ppv);
    }
IFACEMETHODIMP NativeActivate::SetItem(_In_ REFGUID guidKey, _In_ REFPROPVARIANT Value)
    {
        if (!m_spActivateAttributes)
            RETURN_IF_FAILED(MFCreateAttributes(&m_spActivateAttributes, 1));
        return m_spActivateAttributes->SetItem(guidKey, Value);
    }
IFACEMETHODIMP NativeActivate::DeleteItem(_In_ REFGUID guidKey)
    {
        if (!m_spActivateAttributes)
            RETURN_IF_FAILED(MFCreateAttributes(&m_spActivateAttributes, 1));
        return m_spActivateAttributes->DeleteItem(guidKey);
    }
IFACEMETHODIMP NativeActivate::DeleteAllItems()
    {
        if (!m_spActivateAttributes)
            RETURN_IF_FAILED(MFCreateAttributes(&m_spActivateAttributes, 1));
        return m_spActivateAttributes->DeleteAllItems();
    }
IFACEMETHODIMP NativeActivate::SetUINT32(_In_ REFGUID guidKey, _In_ UINT32  unValue)
    {
        if (!m_spActivateAttributes)
            RETURN_IF_FAILED(MFCreateAttributes(&m_spActivateAttributes, 1));
        return m_spActivateAttributes->SetUINT32(guidKey, unValue);
    }
IFACEMETHODIMP NativeActivate::SetUINT64(_In_ REFGUID guidKey, _In_ UINT64  unValue)
    {
        if (!m_spActivateAttributes)
            RETURN_IF_FAILED(MFCreateAttributes(&m_spActivateAttributes, 1));
        return m_spActivateAttributes->SetUINT64(guidKey, unValue);
    }
IFACEMETHODIMP NativeActivate::SetDouble(_In_ REFGUID guidKey, _In_ double  fValue)
    {
        if (!m_spActivateAttributes)
            RETURN_IF_FAILED(MFCreateAttributes(&m_spActivateAttributes, 1));
        return m_spActivateAttributes->SetDouble(guidKey, fValue);
    }
IFACEMETHODIMP NativeActivate::SetGUID(_In_ REFGUID guidKey, _In_ REFGUID guidValue)
    {
        if (!m_spActivateAttributes)
            RETURN_IF_FAILED(MFCreateAttributes(&m_spActivateAttributes, 1));
        return m_spActivateAttributes->SetGUID(guidKey, guidValue);
    }
IFACEMETHODIMP NativeActivate::SetString(_In_ REFGUID guidKey, _In_ LPCWSTR wszValue)
    {
        if (!m_spActivateAttributes)
            RETURN_IF_FAILED(MFCreateAttributes(&m_spActivateAttributes, 1));
        return m_spActivateAttributes->SetString(guidKey, wszValue);
    }
IFACEMETHODIMP NativeActivate::SetBlob(_In_ REFGUID guidKey, _In_reads_(cbBufSize) const UINT8* pBuf, UINT32 cbBufSize)
    {
        if (!m_spActivateAttributes)
            RETURN_IF_FAILED(MFCreateAttributes(&m_spActivateAttributes, 1));
        return m_spActivateAttributes->SetBlob(guidKey, pBuf, cbBufSize);
    }
IFACEMETHODIMP NativeActivate::SetUnknown(_In_ REFGUID guidKey, _In_ IUnknown* pUnknown)
    {
        if (!m_spActivateAttributes)
            RETURN_IF_FAILED(MFCreateAttributes(&m_spActivateAttributes, 1));
        return m_spActivateAttributes->SetUnknown(guidKey, pUnknown);
    }
IFACEMETHODIMP NativeActivate::LockStore()
    {
        if (!m_spActivateAttributes)
            RETURN_IF_FAILED(MFCreateAttributes(&m_spActivateAttributes, 1));
        return m_spActivateAttributes->LockStore();
    }
IFACEMETHODIMP NativeActivate::UnlockStore()
    {
        if (!m_spActivateAttributes)
            RETURN_IF_FAILED(MFCreateAttributes(&m_spActivateAttributes, 1));
        return m_spActivateAttributes->UnlockStore();
    }
IFACEMETHODIMP NativeActivate::GetCount(_Out_ UINT32* pcItems)
    {
        if (!m_spActivateAttributes)
            RETURN_IF_FAILED(MFCreateAttributes(&m_spActivateAttributes, 1));
        return m_spActivateAttributes->GetCount(pcItems);
    }
IFACEMETHODIMP NativeActivate::GetItemByIndex(UINT32 unIndex, _Out_ GUID* pguidKey, _Inout_ PROPVARIANT* pValue)
    {
        if (!m_spActivateAttributes)
            RETURN_IF_FAILED(MFCreateAttributes(&m_spActivateAttributes, 1));
        return m_spActivateAttributes->GetItemByIndex(unIndex, pguidKey, pValue);
    }
IFACEMETHODIMP NativeActivate::CopyAllItems(_In_ IMFAttributes* pDest)
    {
        if (!m_spActivateAttributes)
            RETURN_IF_FAILED(MFCreateAttributes(&m_spActivateAttributes, 1));
        return m_spActivateAttributes->CopyAllItems(pDest);
    }
}
