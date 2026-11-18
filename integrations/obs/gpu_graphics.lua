-- Own GPU alpha consumer. Public OBS/DXGI APIs, one local producer/reader.
local ffi=require('ffi')
ffi.cdef[[
typedef struct {uint32_t a;uint16_t b,c;uint8_t d[8];} SMBGPUGuid;
typedef struct {
 uint16_t name[128];uint32_t vendor,device,subsystem,revision;
 size_t video_memory,system_memory,shared_memory;
 uint32_t luid_low;int32_t luid_high;
} SMBGPUAdapterDesc;
int gs_get_device_type(void);
void *gs_get_device_obj(void);
void *gs_texture_open_shared(uint32_t);
void *gs_texture_create(uint32_t,uint32_t,int,uint32_t,const uint8_t**,uint32_t);
void gs_texture_destroy(void*);
void gs_copy_texture(void*,void*);
int gs_texture_acquire_sync(void*,uint64_t,uint32_t);
int gs_texture_release_sync(void*,uint64_t);
]]
assert(ffi.sizeof('SMBGPUGuid')==16 and ffi.sizeof('SMBGPUAdapterDesc')==304,'Unsupported adapter ABI')
local g=ffi.load('obs')
local M={}
local function com(object,index,kind)
 return ffi.cast(kind,ffi.cast('void***',object)[0][index])
end
local function release(object)
 if object~=nil then com(object,2,'uint32_t (__stdcall *)(void*)')(object) end
end
function M.adapter_luid()
 if g.gs_get_device_type()~=2 then return nil end -- Never interpret an OpenGL object as COM.
 local device=g.gs_get_device_obj();if device==nil then return nil end
 local iid=ffi.new('SMBGPUGuid[1]')
 iid[0].a=0x54ec77fa;iid[0].b=0x1377;iid[0].c=0x44e6
 local tail={0x8c,0x32,0x88,0xfd,0x5f,0x44,0xc8,0x4c}
 for i=1,8 do iid[0].d[i-1]=tail[i] end
 local dxgi=ffi.new('void*[1]')
 if com(device,0,'int32_t (__stdcall *)(void*, const SMBGPUGuid*,void**)')(device,iid,dxgi)~=0 then return nil end
 local adapter=ffi.new('void*[1]')
 local code=com(dxgi[0],7,'int32_t (__stdcall *)(void*,void**)')(dxgi[0],adapter)
 release(dxgi[0]);if code~=0 then return nil end
 local desc=ffi.new('SMBGPUAdapterDesc[1]')
 code=com(adapter[0],8,'int32_t (__stdcall *)(void*,SMBGPUAdapterDesc*)')(adapter[0],desc)
 release(adapter[0]);if code~=0 then return nil end
 return tonumber(desc[0].luid_low),tonumber(desc[0].luid_high)
end
function M.close(data)
 if data.gpu_shared~=nil then g.gs_texture_destroy(data.gpu_shared);data.gpu_shared=nil end
 if data.gpu_private~=nil then g.gs_texture_destroy(data.gpu_private);data.gpu_private=nil end
 data.gpu_key=nil;data.gpu_captured=nil;data.gpu_failed=false;data.gpu_error_code=nil
end
function M.cached(data,now)
 if not data.gpu_failed and data.gpu_captured and now-data.gpu_captured<=1000 then
  return data.gpu_private
 end
 return nil
end
function M.update(data,resource,now)
 if resource==nil then return nil end
 local key=tostring(resource.resource_epoch)..'|'..resource.handle..'|'..resource.width..'|'..resource.height
 if data.gpu_key~=key then
  M.close(data);data.gpu_key=key
  local low,high=M.adapter_luid()
  if low~=resource.luid_low or high~=resource.luid_high then
   data.gpu_failed=true;data.gpu_error_code=1;data.gpu_error='A fonte OBS precisa usar a mesma GPU do SMB Camera.';return nil
  end
  data.gpu_shared=g.gs_texture_open_shared(resource.handle)
  data.gpu_private=g.gs_texture_create(resource.width,resource.height,3,1,nil,0) -- GS_RGBA
  if data.gpu_shared==nil or data.gpu_private==nil then
   data.gpu_failed=true;data.gpu_error_code=2;data.gpu_error='Não foi possível abrir a saída GPU.';return nil
  end
 end
 if data.gpu_failed then return nil end
 local acquired=g.gs_texture_acquire_sync(data.gpu_shared,1,0)
 if acquired==0 then
  g.gs_copy_texture(data.gpu_private,data.gpu_shared)
  if g.gs_texture_release_sync(data.gpu_shared,0)~=0 then data.gpu_failed=true;data.gpu_error_code=2;data.gpu_captured=nil;return nil end
  data.gpu_captured=resource.captured
  data.gpu_copied_frames=(data.gpu_copied_frames or 0)+1
 elseif acquired~=138 then -- OBS32.2.2 Windows returns CRT ETIMEDOUT, not DXGI258.
  data.gpu_failed=true;data.gpu_error_code=2;data.gpu_captured=nil;return nil
 end
 return M.cached(data,now)
end
return M
