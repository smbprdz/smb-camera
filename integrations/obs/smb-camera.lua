-- SMB Camera: own OBS source via its documented Lua extension API.
-- Prototype RAM bridge. No capture, recording, virtual webcam or third-party SDK.
local obs=obslua
local ffi=require('ffi')
local bit=require('bit')
local transport=dofile(script_path() .. 'alpha_transport.lua')
local gpu_transport=dofile(script_path() .. 'gpu_transport.lua')
local gpu_graphics=dofile(script_path() .. 'gpu_graphics.lua')
ffi.cdef[[
void *gs_texture_create(uint32_t, uint32_t, int, uint32_t, const uint8_t**, uint32_t);
void gs_texture_destroy(void*);
void gs_texture_set_image(void*, const uint8_t*, uint32_t, bool);
void *gs_effect_get_param_by_name(void*, const char*);
void gs_effect_set_texture(void*, void*);
bool gs_effect_loop(void*, const char*);
void *obs_get_base_effect(int);
void gs_draw_sprite(void*, uint32_t, uint32_t, uint32_t);
void gs_blend_state_push(void);
void gs_blend_state_pop(void);
void gs_blend_function(int, int);
]]
local graphics=ffi.load('obs') -- the OBS host's own public C graphics API
local info={id='smb_camera_alpha_v1', type=obs.OBS_SOURCE_TYPE_INPUT,
    output_flags=bit.bor(obs.OBS_SOURCE_VIDEO, obs.OBS_SOURCE_CUSTOM_DRAW)}
local instances={}
local function disconnect(data)
    data.frame=nil;data.gpu_resource=nil;data.gpu_reset=true
    if data.client then data.client:close(); data.client=nil end
end
local function destroy_texture(data)
    if data.texture ~= nil then graphics.gs_texture_destroy(data.texture); data.texture=nil end
    gpu_graphics.close(data)
end
local function read_endpoint(path)
    if type(path) ~= 'string' or path == '' then return nil end
    local file=io.open(path, 'rb')
    if not file then return nil end
    local size=file:seek('end')
    if not size or size > 32768 then file:close(); return nil end
    file:seek('set'); local text=file:read('*a'); file:close()
    local value=obs.obs_data_create_from_json(text)
    if not value then return nil end
    local endpoint={schema=obs.obs_data_get_int(value, 'schema'),
        transport=obs.obs_data_get_string(value,'transport'),
        alpha_mode=obs.obs_data_get_string(value, 'alpha_mode'),
        pipe_name=obs.obs_data_get_string(value, 'pipe_name'),
        owner_sid=obs.obs_data_get_string(value, 'owner_sid'),
        producer_pid=obs.obs_data_get_int(value, 'producer_pid'),
        epoch_hex=obs.obs_data_get_string(value, 'epoch_hex'),
        width=obs.obs_data_get_int(value, 'width'), height=obs.obs_data_get_int(value, 'height')}
    obs.obs_data_release(value)
    return endpoint
end
info.get_name=function() return 'SMB Camera' end
info.get_defaults=function(settings)
    obs.obs_data_set_default_string(settings, 'endpoint', script_path() .. '../../runtime/alpha-output.json')
end
info.get_properties=function()
    local props=obs.obs_properties_create()
    obs.obs_properties_add_path(props, 'endpoint', 'Conexão com SMB Camera',
        obs.OBS_PATH_FILE, 'Conexão SMB (*.json)', nil)
    return props
end
info.update=function(data, settings)
    disconnect(data)
    data.path=obs.obs_data_get_string(settings, 'endpoint')
    data.key=nil; data.next_metadata=0
end
info.create=function(settings, source)
    local data={source=source, width=1920, height=1080, showing=true, uploaded=nil}
    info.update(data, settings); instances[data]=true
    return data
end
info.destroy=function(data)
    disconnect(data); instances[data]=nil
    obs.obs_enter_graphics(); destroy_texture(data); obs.obs_leave_graphics()
end
info.hide=function(data)
    data.showing=false;disconnect(data);data.key=nil
    obs.obs_enter_graphics();destroy_texture(data);obs.obs_leave_graphics()
end
info.show=function(data) data.showing=true; data.next_metadata=0 end
info.video_tick=function(data, seconds)
    if not data.showing then return end
    local now=transport.tick_ms()
    if now >= data.next_metadata then
        data.next_metadata=now+1000
        local endpoint=read_endpoint(data.path)
        if not endpoint then disconnect(data); data.key=nil; return end
        local key=endpoint.pipe_name .. '|' .. endpoint.epoch_hex .. '|'
            .. tostring(endpoint.width) .. '|' .. tostring(endpoint.height) .. '|'
            .. tostring(endpoint.producer_pid) .. '|' .. endpoint.owner_sid .. '|'
            .. tostring(endpoint.schema) .. '|' .. endpoint.alpha_mode .. '|' .. endpoint.transport
        if key ~= data.key then
            disconnect(data)
            local factory=endpoint.transport=='d3d11-keyed-v1' and gpu_transport or transport
            local good, client=pcall(factory.new, endpoint)
            if not good then data.key=nil; return end
            data.client=client; data.key=key; data.width=client.width; data.height=client.height
            data.uploaded=nil
        end
    end
    if data.client then
        local frame=data.client:poll()
        if frame then data.frame=frame end
    end
end
info.video_render=function(data, effect)
    if data.gpu_reset then gpu_graphics.close(data);data.gpu_reset=false end
    if not data.client then return end
    if data.client.invalidate_private then
        gpu_graphics.close(data);data.gpu_resource=nil;data.client.invalidate_private=false
    end
    local cached_only=data.client.gpu and data.client.cached_only
    if not cached_only and not data.client:fresh() then return end
    if data.client.gpu then
        if data.texture~=nil then graphics.gs_texture_destroy(data.texture);data.texture=nil end
        if data.frame then data.gpu_resource=data.frame;data.frame=nil end
        local texture
        if cached_only then
            data.gpu_resource=nil
            texture=gpu_graphics.cached(data,transport.tick_ms())
        else
            texture=gpu_graphics.update(data,data.gpu_resource,transport.tick_ms())
        end
        if data.gpu_failed then data.client:report_error(data.gpu_error_code or 2) end
        if texture==nil then return end
        local base=graphics.obs_get_base_effect(obs.OBS_EFFECT_DEFAULT)
        graphics.gs_effect_set_texture(graphics.gs_effect_get_param_by_name(base,'image'),texture)
        graphics.gs_blend_state_push();graphics.gs_blend_function(obs.GS_BLEND_ONE,obs.GS_BLEND_INVSRCALPHA)
        while graphics.gs_effect_loop(base,'Draw') do graphics.gs_draw_sprite(texture,0,data.width,data.height) end
        graphics.gs_blend_state_pop();return
    end
    if data.gpu_shared~=nil or data.gpu_private~=nil then gpu_graphics.close(data) end
    if data.frame then
        local frame=data.frame
        if data.texture ~= nil and (data.texture_width ~= frame.width or data.texture_height ~= frame.height) then
            destroy_texture(data)
        end
        if data.texture == nil then
            data.texture=graphics.gs_texture_create(frame.width, frame.height, obs.GS_RGBA, 1, nil, 2)
            data.texture_width=frame.width; data.texture_height=frame.height
        end
        if data.texture == nil then return end
        graphics.gs_texture_set_image(data.texture, frame.pixels, frame.stride, false)
        data.uploaded=frame.frame_id; data.frame=nil
    end
    if data.texture == nil or data.uploaded == nil then return end
    local base=graphics.obs_get_base_effect(obs.OBS_EFFECT_DEFAULT)
    if base == nil then return end
    graphics.gs_effect_set_texture(graphics.gs_effect_get_param_by_name(base, 'image'), data.texture)
    graphics.gs_blend_state_push()
    graphics.gs_blend_function(obs.GS_BLEND_ONE, obs.GS_BLEND_INVSRCALPHA)
    while graphics.gs_effect_loop(base, 'Draw') do
        graphics.gs_draw_sprite(data.texture, 0, data.width, data.height)
    end
    graphics.gs_blend_state_pop()
end
info.get_width=function(data) return data.width end
info.get_height=function(data) return data.height end
function script_description()
    return 'SMB Camera: fonte própria com transparência. Protótipo por memória, sem áudio ou gravação.'
end
function script_unload()
    for data in pairs(instances) do info.destroy(data) end
end
obs.obs_register_source(info)
