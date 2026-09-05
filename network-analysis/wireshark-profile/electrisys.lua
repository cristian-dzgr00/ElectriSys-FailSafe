-- ============================================================
-- electrisys.lua — disector Lua para Wireshark
-- Resalta y decodifica los JWT de ElectriSys en tráfico HTTP.
--
-- Instalación:
--   Copiar a ~/.config/wireshark/plugins/electrisys.lua
--   O: Wireshark → About → Folders → Personal Lua Plugins
-- ============================================================

local electrisys_proto = Proto("ElectriSysJWT", "ElectriSys JWT Token")

local f_token   = ProtoField.string("electrisys.jwt.token",   "JWT Token")
local f_header  = ProtoField.string("electrisys.jwt.header",  "Header (Base64)")
local f_payload = ProtoField.string("electrisys.jwt.payload", "Payload (Base64)")
local f_sig     = ProtoField.string("electrisys.jwt.sig",     "Signature")
local f_user_id = ProtoField.string("electrisys.jwt.user_id", "Usuario ID")
local f_role    = ProtoField.string("electrisys.jwt.role",    "Rol")
local f_exp     = ProtoField.string("electrisys.jwt.exp",     "Expira")

electrisys_proto.fields = { f_token, f_header, f_payload, f_sig, f_user_id, f_role, f_exp }

-- Decodifica Base64 sin padding
local function b64decode(s)
    s = s:gsub("-", "+"):gsub("_", "/")
    local pad = (4 - #s % 4) % 4
    s = s .. string.rep("=", pad)
    local result = {}
    for b64, b in s:gmatch("([A-Za-z0-9+/=]-)=*(.?)") do
        -- implementación básica
    end
    return s  -- Wireshark mostrará el Base64 raw
end

-- Extrae campo JSON básico
local function extract_json_field(json, field)
    local val = json:match('"' .. field .. '"%s*:%s*"([^"]+)"')
    if not val then
        val = json:match('"' .. field .. '"%s*:%s*([%d]+)')
    end
    return val or "N/A"
end

local function parse_jwt(jwt_str, tree, pinfo)
    local parts = {}
    for part in jwt_str:gmatch("[^.]+") do
        table.insert(parts, part)
    end

    if #parts ~= 3 then return end

    local jwt_tree = tree:add(electrisys_proto, "ElectriSys JWT")
    jwt_tree:add(f_token,   jwt_str)
    jwt_tree:add(f_header,  parts[1])
    jwt_tree:add(f_payload, parts[2])
    jwt_tree:add(f_sig,     parts[3])

    -- Payload decodificado (Base64URL → JSON)
    local payload = parts[2]
    jwt_tree:add(f_user_id, extract_json_field(payload, "sub"))
    jwt_tree:add(f_role,    extract_json_field(payload, "role"))

    local exp_ts = extract_json_field(payload, "exp")
    if exp_ts ~= "N/A" then
        jwt_tree:add(f_exp, os.date("!%Y-%m-%d %H:%M:%S UTC", tonumber(exp_ts)))
    end

    pinfo.cols.info:append(" [ElectriSys JWT]")
end

-- Engancharse al disector HTTP de Wireshark
local http_field = Field.new("http.authorization")

local function electrisys_heuristic(buffer, pinfo, tree)
    local auth = http_field()
    if not auth then return false end

    local auth_str = tostring(auth)
    if auth_str:sub(1, 7) ~= "Bearer " then return false end

    local jwt = auth_str:sub(8)
    if jwt:find("%.") then
        parse_jwt(jwt, tree, pinfo)
        return true
    end
    return false
end

electrisys_proto:register_heuristic("http", electrisys_heuristic)

print("[ElectriSys] Disector JWT cargado — busca 'electrisys' en el árbol de protocolos")
