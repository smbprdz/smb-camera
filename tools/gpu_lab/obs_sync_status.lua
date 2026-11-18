-- OBS32.2.2 Windows D3D wrapper converts WAIT_TIMEOUT to CRT ETIMEDOUT.
-- This is an errno contract, distinct from direct IDXGIKeyedMutex HRESULTs.
local M={ETIMEDOUT=138}
function M.classify(value)
 if value==0 then return 'acquired' end
 if value==M.ETIMEDOUT then return 'busy' end
 return 'failed' -- includes abandoned resources hidden behind the OBS wrapper
end
return M
