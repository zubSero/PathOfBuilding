local xmlPath, request = ...
local json = require("dkjson")
local settings = assert(json.decode(request, 1, json.null))
local xmlFile = assert(io.open(xmlPath, "rb"))
local xml = xmlFile:read("*a")
xmlFile:close()

loadBuildFromXML(xml, "Headless replay")
assert(not __mainObject__.promptMsg, __mainObject__.promptMsg)
assert(build.targetVersion and build.calcsTab.mainOutput, "PoB could not load the build")

local config = build.configTab
if next(settings.config) then
	local options = { }
	for _, option in ipairs(require("Modules.ConfigOptions")) do
		if option.var then options[option.var] = option end
	end
	for name, value in pairs(settings.config) do
		local option = assert(options[name], "Unknown config option: " .. name)
		if value == json.null then
			config.input[name] = nil
		else
			local valid
			if option.type == "list" then
				for _, choice in ipairs(option.list) do
					if choice.val == value then
						valid = true
						break
					end
				end
			elseif option.type == "check" then
				valid = type(value) == "boolean"
			elseif option.type == "text" then
				valid = type(value) == "string"
			else
				valid = type(value) == "number"
			end
			assert(valid, "Invalid config value for " .. name)
			config.input[name] = value
		end
	end
	config:BuildModList()
	build.buildFlag = true
	runCallback("OnFrame")
	assert(not __mainObject__.promptMsg, __mainObject__.promptMsg)
end

local function printable(value)
	if value == nil then return json.null end
	if type(value) == "number" and (value ~= value or math.abs(value) == math.huge) then
		return tostring(value)
	end
	return value
end

local output = build.calcsTab.mainOutput
local stats = { }
local modifiers = setmetatable({ }, { __jsontype = "object" })
for _, name in ipairs(settings.stats) do
	local value = output
	for key in name:gmatch("[^.]+") do
		if type(value) ~= "table" then
			value = nil
			break
		end
		value = value[key]
	end
	assert(type(value) ~= "table", "Select a specific output field within " .. name)
	stats[name] = printable(value)
end

local env = build.calcsTab.mainEnv
local skill = env.player.mainSkill
for _, probe in ipairs(settings.probes) do
	local scope, kind, name = probe:match("^([^:]+):([^:]+):(.+)$")
	local actor = env[scope]
	local db = scope == "skill" and skill.skillModList or actor and actor.modDB
	local cfg = scope == "skill" and skill.skillCfg or nil
	local value
	if db then
		if kind == "MORE" then
			value = db:More(cfg, name)
		elseif kind == "FLAG" then
			value = not not db:Flag(cfg, name)
		elseif kind == "OVERRIDE" then
			value = db:Override(cfg, name)
		else
			value = db:Sum(kind, cfg, name)
		end
	end
	modifiers[probe] = printable(value)
end

local set = config.configSets[config.activeConfigSetId]
print("POB_REPLAY_RESULT " .. json.encode({
	skill = skill.activeEffect.grantedEffect.name,
	configSet = set.title or tostring(config.activeConfigSetId),
	input = config.input,
	placeholder = set.placeholder,
	stats = stats,
	modifiers = modifiers,
}))
