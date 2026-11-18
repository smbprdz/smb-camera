#pragma once
#include <windows.h>
#ifdef UCS_DEVICE_PRODUCT
#include "../camera/CameraId.h"
#else
inline constexpr GUID UCS_PROBE_CLSID={0x3cefe818,0x1f33,0x49cb,{0x9f,0x60,0xdb,0x97,0x34,0x1b,0xbe,0x65}};
inline constexpr wchar_t UCS_PROBE_CLSID_TEXT[]=L"{3CEFE818-1F33-49CB-9F60-DB97341BBE65}";
inline constexpr wchar_t UCS_PROBE_REGKEY[]=L"SOFTWARE\\Classes\\CLSID\\{3CEFE818-1F33-49CB-9F60-DB97341BBE65}";
inline constexpr wchar_t UCS_PROBE_FRIENDLY_NAME[]=L"SMB Camera frame bridge test";
#endif
