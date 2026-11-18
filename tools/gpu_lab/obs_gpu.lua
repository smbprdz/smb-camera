-- Disposable generated-texture OBS source. Immutable textures avoid producer
-- writes during this import proof. Not a live transport or installed plugin.
local obs=obslua
local ffi=require('ffi')
local bit=require('bit')
ffi.cdef[[
void *gs_texture_open_shared(uint32_t);
void gs_texture_destroy(void*);
void *obs_get_base_effect(int);
void *gs_effect_get_param_by_name(void*, const char*);
void gs_effect_set_texture(void*, void*);
bool gs_effect_loop(void*, const char*);
void gs_draw_sprite(void*, uint32_t, uint32_t, uint32_t);
void gs_blend_state_push(void);
void gs_blend_state_pop(void);
void gs_blend_function(int, int);
]]
local g=ffi.load('obs')
local source={id='smb_gpu_generated_lab',type=obs.OBS_SOURCE_TYPE_INPUT,
output_flags=bit.bor(obs.OBS_SOURCE_VIDEO,obs.OBS_SOURCE_CUSTOM_DRAW)}
source.get_name=function() return 'SMB generated GPU import lab' end
source.create=function(settings,host)
 local data={handles={},textures={},index=1,ticks=0}
 for i=1,3 do data.handles[i]=obs.obs_data_get_int(settings,'handle'..i) end
 data.width=obs.obs_data_get_int(settings,'width');data.height=obs.obs_data_get_int(settings,'height')
 assert(data.width==64 and data.height==36,'Generated64x36fixture required')
 return data
end
source.video_tick=function(data,seconds) data.ticks=data.ticks+1;data.index=math.floor(data.ticks/4)%3+1 end
source.video_render=function(data,effect)
 local i=data.index
 if data.textures[i]==nil then
  assert(data.handles[i]>0 and data.handles[i]<4294967296,'Legacy shared handle outside range')
  data.textures[i]=g.gs_texture_open_shared(data.handles[i])
 end
 if data.textures[i]==nil then return end
 local e=g.obs_get_base_effect(obs.OBS_EFFECT_DEFAULT)
 g.gs_effect_set_texture(g.gs_effect_get_param_by_name(e,'image'),data.textures[i])
 g.gs_blend_state_push();g.gs_blend_function(obs.GS_BLEND_ONE,obs.GS_BLEND_INVSRCALPHA)
 while g.gs_effect_loop(e,'Draw') do g.gs_draw_sprite(data.textures[i],0,data.width,data.height) end
 g.gs_blend_state_pop()
end
source.get_width=function(data)return data.width end
source.get_height=function(data)return data.height end
source.destroy=function(data)
 obs.obs_enter_graphics()
 for _,t in pairs(data.textures) do if t~=nil then g.gs_texture_destroy(t) end end
 obs.obs_leave_graphics()
end
function script_description()return 'Own generated GPU import experiment, not installed.' end
obs.obs_register_source(source)
