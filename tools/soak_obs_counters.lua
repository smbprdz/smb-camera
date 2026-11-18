-- Runs only inside the generated libobs fixture. The original modules stay intact.
local obs = obslua
local module_dir = script_path()
local copies, distinct_ids, epochs = 0, 0, 0
local last_id, last_epoch
local env = setmetatable({}, {__index = _G})

env.dofile = function(path)
    local module = dofile(path)
    if path == module_dir .. 'gpu_transport.lua' then
        local new = module.new
        module.new = function(endpoint)
            local client = new(endpoint)
            local disconnect = client.disconnect
            client.disconnect = function(self, reason, keep_private)
                if reason then obs.script_log(obs.LOG_INFO, 'GPU fixture disconnect: ' .. reason) end
                return disconnect(self, reason, keep_private)
            end
            return client
        end
    end
    if path == module_dir .. 'gpu_graphics.lua' then
        local update = module.update
        module.update = function(data, resource, now)
            local before = data.gpu_copied_frames or 0
            local texture = update(data, resource, now)
            if (data.gpu_copied_frames or 0) > before then
                copies = copies + 1
                if last_id == nil or resource.frame_id > last_id then
                    distinct_ids = distinct_ids + 1
                    last_id = resource.frame_id
                end
                if last_epoch ~= resource.resource_epoch then
                    epochs = epochs + 1
                    last_epoch = resource.resource_epoch
                end
            end
            return texture
        end
    end
    return module
end

local source = assert(loadfile(module_dir .. 'smb-camera.lua'))
setfenv(source, env)
source()

function script_unload()
    env.script_unload()
    local file = assert(io.open(module_dir .. 'observed-copies.txt', 'w'))
    file:write(string.format('%d %d %d\n', copies, distinct_ids, epochs))
    file:close()
end
