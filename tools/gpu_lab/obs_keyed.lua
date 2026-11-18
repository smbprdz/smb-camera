-- Own generated-only mutable GPU source. Laboratory control file is not the
-- product endpoint: peer identity/transport integration remains a separate gate.
local obs=obslua
local ffi=require('ffi')
local bit=require('bit')
local sync_status=dofile(script_path() .. 'obs_sync_status.lua')
ffi.cdef[[
void *gs_texture_open_shared(uint32_t);
void *gs_texture_create(uint32_t,uint32_t,int,uint32_t,const uint8_t**,uint32_t);
void gs_texture_destroy(void*);
void gs_copy_texture(void*,void*);
int gs_texture_acquire_sync(void*,uint64_t,uint32_t);
int gs_texture_release_sync(void*,uint64_t);
void *obs_get_base_effect(int);
void *gs_effect_get_param_by_name(void*,const char*);
void gs_effect_set_texture(void*,void*);
bool gs_effect_loop(void*,const char*);
void gs_draw_sprite(void*,uint32_t,uint32_t,uint32_t);
void gs_blend_state_push(void);
void gs_blend_state_pop(void);
void gs_blend_function(int,int);
uint64_t GetTickCount64(void);
]]
local g=ffi.load('obs')
local k=ffi.load('kernel32')
local info={id='smb_keyed_generated_lab',type=obs.OBS_SOURCE_TYPE_INPUT,
 output_flags=bit.bor(obs.OBS_SOURCE_VIDEO,obs.OBS_SOURCE_CUSTOM_DRAW)}
local function clock()return tonumber(k.GetTickCount64())end
local function destroy(data)
 if data.shared~=nil then g.gs_texture_destroy(data.shared);data.shared=nil end
 if data.private~=nil then g.gs_texture_destroy(data.private);data.private=nil end
 data.last=nil;data.failed=false
end
info.get_name=function()return 'Own keyed generated GPU source' end
info.create=function(settings,source)
 return {path=obs.obs_data_get_string(settings,'config'),width=obs.obs_data_get_int(settings,'width'),
 height=obs.obs_data_get_int(settings,'height'),next_metadata=0,epoch=nil,failed=false}
end
info.video_tick=function(data,seconds)
 local now=clock()
 if now<data.next_metadata then return end
 data.next_metadata=now+100
 local file=io.open(data.path,'rb');if not file then data.pending=nil;return end
 local text=file:read(4097);file:close()
 if not text or #text>4096 then return end
 local settings=obs.obs_data_create_from_json(text);if not settings then return end
 local scope=obs.obs_data_get_string(settings,'scope')
 local epoch=obs.obs_data_get_string(settings,'epoch')
 local handle=obs.obs_data_get_int(settings,'handle')
 local width=obs.obs_data_get_int(settings,'width');local height=obs.obs_data_get_int(settings,'height')
 obs.obs_data_release(settings)
 if scope~='generated keyed OBS ownership' or width~=data.width or height~=data.height
  or handle<=0 or handle>=4294967296 or #epoch~=32 or epoch:find('[^%x]') then return end
 data.pending={epoch=epoch,handle=handle}
end
info.video_render=function(data,effect)
 if data.pending and data.pending.epoch~=data.epoch then
  destroy(data);data.epoch=data.pending.epoch
  data.shared=g.gs_texture_open_shared(data.pending.handle)
  data.private=g.gs_texture_create(data.width,data.height,obs.GS_RGBA,1,nil,0)
 end
 if data.shared==nil or data.private==nil or data.failed then return end
 local acquired=sync_status.classify(g.gs_texture_acquire_sync(data.shared,1,0))
 if acquired=='acquired' then
  g.gs_copy_texture(data.private,data.shared)
  if g.gs_texture_release_sync(data.shared,0)~=0 then data.failed=true;data.last=nil;return end
  data.last=clock()
 elseif acquired~='busy' then
  data.failed=true;data.last=nil;return
 end
 if not data.last or clock()-data.last>1000 then return end
 local e=g.obs_get_base_effect(obs.OBS_EFFECT_DEFAULT)
 g.gs_effect_set_texture(g.gs_effect_get_param_by_name(e,'image'),data.private)
 g.gs_blend_state_push();g.gs_blend_function(obs.GS_BLEND_ONE,obs.GS_BLEND_INVSRCALPHA)
 while g.gs_effect_loop(e,'Draw') do g.gs_draw_sprite(data.private,0,data.width,data.height) end
 g.gs_blend_state_pop()
end
info.get_width=function(data)return data.width end
info.get_height=function(data)return data.height end
info.destroy=function(data)obs.obs_enter_graphics();destroy(data);obs.obs_leave_graphics()end
function script_description()return 'Own generated keyed GPU experiment, not installed.'end
obs.obs_register_source(info)
