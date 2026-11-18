-- Own local RGBA receiver. Public Windows API only, no Spout/virtual-camera SDK.
-- Messages are bounded; the frame is never written to a file or converted in Lua.
local ffi = require('ffi')
local bit = require('bit')
assert(ffi.os == 'Windows' and ffi.arch == 'x64', 'Windows x64 required')
ffi.cdef[[
typedef struct {
    uintptr_t Internal, InternalHigh;
    uint32_t Offset, OffsetHigh;
    void *hEvent;
} SMBAlphaOverlapped;
typedef struct {
    uint32_t magic; uint16_t version, bytes;
    uint32_t format, width, height, reserved;
} SMBAlphaRequest;
typedef struct {
    uint32_t magic; uint16_t version, status;
    uint32_t body_bytes, reserved;
    uint64_t captured_tick_ms, epoch;
} SMBAlphaReply;
typedef struct {
    uint32_t magic; uint16_t version, bytes;
    uint32_t format, width, height, stride0, stride1, plane1_offset;
    uint64_t payload_bytes, frame_id;
    int64_t pts_100ns; uint32_t color, flags;
} SMBAlphaDescriptor;
void *CreateFileW(const uint16_t*, uint32_t, uint32_t, void*, uint32_t, uint32_t, void*);
void *CreateEventW(void*, int, int, const uint16_t*);
int CloseHandle(void*);
int ResetEvent(void*);
int SetNamedPipeHandleState(void*, uint32_t*, void*, void*);
int GetNamedPipeServerProcessId(void*, uint32_t*);
int TransactNamedPipe(void*, void*, uint32_t, void*, uint32_t, uint32_t*, SMBAlphaOverlapped*);
int GetOverlappedResult(void*, SMBAlphaOverlapped*, uint32_t*, int);
int CancelIoEx(void*, SMBAlphaOverlapped*);
uint32_t GetLastError(void);
uint64_t GetTickCount64(void);
uint32_t GetSecurityInfo(void*, int, uint32_t, void**, void**, void**, void**, void**);
int ConvertStringSidToSidW(const uint16_t*, void**);
int EqualSid(void*, void*);
void *LocalFree(void*);
]]
assert(ffi.sizeof('SMBAlphaRequest') == 24 and ffi.sizeof('SMBAlphaReply') == 32
    and ffi.sizeof('SMBAlphaDescriptor') == 64, 'Unsupported frame ABI')
local k, a = ffi.load('kernel32'), ffi.load('advapi32')
local invalid_handle = ffi.cast('void*', -1)
local M, Client = {}, {}
Client.__index = Client
local function wide_ascii(value)
    local out = ffi.new('uint16_t[?]', #value + 1)
    for i = 1, #value do
        local char = value:byte(i)
        assert(char < 128 and char > 0, 'Invalid endpoint text')
        out[i - 1] = char
    end
    return out
end
local function epoch_from_hex(value)
    assert(type(value) == 'string' and #value == 16 and not value:find('[^%x]'), 'Invalid epoch')
    local number = ffi.new('uint64_t', tonumber(value:sub(1, 8), 16))
        * ffi.new('uint64_t', 4294967296) + tonumber(value:sub(9), 16)
    assert(number ~= 0, 'Invalid epoch')
    return number
end
local function dimension(value)
    return type(value) == 'number' and value == math.floor(value) and value >= 2 and value <= 16384
end
function M.new(endpoint)
    assert(endpoint.schema == 1 and endpoint.alpha_mode == 'premultiplied', 'Not an alpha endpoint')
    local prefix = '\\\\.\\pipe\\UCS.FrameBridge.'
    local name = endpoint.pipe_name
    assert(type(name) == 'string' and name:sub(1, #prefix) == prefix
        and #name == #prefix + 36 and not name:sub(#prefix + 1):find('[^%x%-]'), 'Not a local owned pipe')
    assert(dimension(endpoint.width) and dimension(endpoint.height), 'Invalid canvas')
    local bytes = endpoint.width * endpoint.height * 4
    assert(bytes <= 64 * 1024 * 1024, 'Canvas exceeds allocation bound')
    assert(type(endpoint.producer_pid) == 'number' and endpoint.producer_pid >= 1
        and endpoint.producer_pid <= 4294967295 and endpoint.producer_pid == math.floor(endpoint.producer_pid), 'Invalid producer')
    assert(type(endpoint.owner_sid) == 'string' and #endpoint.owner_sid < 192
        and endpoint.owner_sid:match('^S%-1%-%d[%d%-]+$'), 'Invalid owner')
    local self = setmetatable({width=endpoint.width, height=endpoint.height, size=bytes,
        name=wide_ascii(name), owner=wide_ascii(endpoint.owner_sid), pid=endpoint.producer_pid,
        epoch=epoch_from_hex(endpoint.epoch_hex), last_id=ffi.new('uint64_t', 0),
        next_connect=0, pending=false, captured=nil, error=nil}, Client)
    self.buffer = ffi.new('uint8_t[?]', bytes + 96)
    self.display = ffi.new('uint8_t[?]', bytes + 96)
    self.request = ffi.new('SMBAlphaRequest[1]')
    local r = self.request[0]
    r.magic=0x51534355; r.version=1; r.bytes=24; r.format=3
    r.width=self.width; r.height=self.height
    self.op=ffi.new('SMBAlphaOverlapped[1]'); self.count=ffi.new('uint32_t[1]')
    self.event=k.CreateEventW(nil, 1, 0, nil)
    assert(self.event ~= nil, 'Frame event unavailable')
    return self
end
function Client:disconnect(reason)
    if self.pipe ~= nil then
        if self.pending then
            k.CancelIoEx(self.pipe, self.op)
            k.GetOverlappedResult(self.pipe, self.op, self.count, 1)
        end
        k.CloseHandle(self.pipe)
    end
    self.pipe=nil; self.pending=false; self.captured=nil
    self.last_id=ffi.new('uint64_t', 0)
    self.error=reason
    self.next_connect=tonumber(k.GetTickCount64()) + 250
end
function Client:close()
    self:disconnect(nil)
    if self.event ~= nil then k.CloseHandle(self.event); self.event=nil end
end
function Client:connect(now)
    if self.event == nil or now < self.next_connect then return false end
    self.pipe=k.CreateFileW(self.name, 0x120183, 0, nil, 3, bit.bor(0x40000000, 0x110000), nil)
    if self.pipe == nil or self.pipe == invalid_handle then
        self.pipe=nil; self.next_connect=now+250; return false
    end
    local pid=ffi.new('uint32_t[1]')
    local actual, descriptor, expected=ffi.new('void*[1]'), ffi.new('void*[1]'), ffi.new('void*[1]')
    local good=k.GetNamedPipeServerProcessId(self.pipe, pid) ~= 0 and pid[0] == self.pid
    good=good and a.GetSecurityInfo(self.pipe, 6, 1, actual, nil, nil, nil, descriptor) == 0
        and a.ConvertStringSidToSidW(self.owner, expected) ~= 0
        and a.EqualSid(actual[0], expected[0]) ~= 0
    if descriptor[0] ~= nil then k.LocalFree(descriptor[0]) end
    if expected[0] ~= nil then k.LocalFree(expected[0]) end
    local mode=ffi.new('uint32_t[1]', 2)
    if not good or k.SetNamedPipeHandleState(self.pipe, mode, nil, nil) == 0 then
        self:disconnect('Producer identity or mode rejected'); return false
    end
    return true
end
function Client:validate(bytes, now)
    if bytes == 32 then
        local empty=ffi.cast('const SMBAlphaReply*', self.buffer)[0]
        if empty.magic ~= 0x52534355 or empty.version ~= 1 or empty.status ~= 0
            or empty.reserved ~= 0 or empty.body_bytes ~= 0 or empty.captured_tick_ms ~= 0
            or empty.epoch ~= self.epoch then self:disconnect('Empty reply rejected') end
        return nil
    end
    if bytes ~= self.size + 96 then self:disconnect('Frame size rejected'); return nil end
    local reply=ffi.cast('const SMBAlphaReply*', self.buffer)[0]
    local frame=ffi.cast('const SMBAlphaDescriptor*', self.buffer + 32)[0]
    local captured=tonumber(reply.captured_tick_ms)
    if reply.magic ~= 0x52534355 or reply.version ~= 1 or reply.status ~= 1
        or reply.reserved ~= 0 or reply.body_bytes ~= self.size+64 or reply.epoch ~= self.epoch
        or captured > now or now-captured > 250
        or frame.magic ~= 0x46534355 or frame.version ~= 1 or frame.bytes ~= 64 or frame.format ~= 3
        or frame.width ~= self.width or frame.height ~= self.height
        or frame.stride0 ~= self.width*4 or frame.stride1 ~= 0 or frame.plane1_offset ~= 0
        or frame.payload_bytes ~= self.size or frame.frame_id == 0 or frame.frame_id < self.last_id
        or frame.pts_100ns < 0 or frame.color ~= 2 or frame.flags ~= 1 then
        self:disconnect('Frame descriptor rejected'); return nil
    end
    self.captured=captured
    if frame.frame_id == self.last_id then return nil end
    self.last_id=ffi.new('uint64_t', frame.frame_id)
    self.buffer, self.display=self.display, self.buffer
    return {pixels=self.display+96, width=self.width, height=self.height,
        captured=captured, frame_id=self.last_id, stride=self.width*4}
end
function Client:poll()
    local now=tonumber(k.GetTickCount64())
    if self.pipe == nil and not self:connect(now) then return nil end
    local completed=nil
    if self.pending then
        if k.GetOverlappedResult(self.pipe, self.op, self.count, 0) == 0 then
            if k.GetLastError() ~= 996 or now-self.sent > 100 then self:disconnect('Frame I/O unavailable') end
            return nil
        end
        self.pending=false
        completed=self:validate(tonumber(self.count[0]), now)
        if self.pipe == nil then return nil end
    end
    k.ResetEvent(self.event); ffi.fill(self.op, ffi.sizeof(self.op)); self.op[0].hEvent=self.event
    self.sent=now
    if k.TransactNamedPipe(self.pipe, self.request, 24, self.buffer, self.size+96, self.count, self.op) == 0 then
        if k.GetLastError() == 997 then self.pending=true else self:disconnect('Frame request unavailable') end
        return completed
    end
    return self:validate(tonumber(self.count[0]), now) or completed
end
function Client:fresh()
    -- Accept only <=250ms-old incoming packets, but hold the last matched image
    -- for 1s between arrivals. A 3FPS source must not blink every 250ms.
    return self.captured ~= nil and tonumber(k.GetTickCount64())-self.captured <= 1000
end
M.tick_ms=function() return tonumber(k.GetTickCount64()) end
return M
