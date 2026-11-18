#pragma once
#include <windows.h>
#ifdef UCS_FRAME_BRIDGE
#include "../bridge/BridgeId.h"
#else
inline constexpr GUID UCS_PROBE_CLSID={0x1a20172a,0xb194,0x41b7,{0xbc,0xc4,0x94,0x45,0xb9,0x65,0x1b,0xf7}};
inline constexpr wchar_t UCS_PROBE_CLSID_TEXT[]=L"{1A20172A-B194-41B7-BCC4-9445B9651BF7}";
inline constexpr wchar_t UCS_PROBE_REGKEY[]=L"SOFTWARE\\Classes\\CLSID\\{1A20172A-B194-41B7-BCC4-9445B9651BF7}";
inline constexpr wchar_t UCS_PROBE_FRIENDLY_NAME[]=L"SMB Camera native test";
#endif
