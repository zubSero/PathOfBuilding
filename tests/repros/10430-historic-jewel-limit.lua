-- Load the bundled Lethal Pride table with the Windows runtime's zlib. The
-- headless wrapper stubs Inflate, so the generated conquests would be absent.
local ffi = require("ffi")
ffi.cdef[[
	int uncompress(unsigned char *dest, unsigned long *destLen,
		const unsigned char *source, unsigned long sourceLen);
]]
local zlib = ffi.load("../runtime/zlib1.dll")
local file = assert(io.open("Data/TimelessJewelData/LethalPride.zip", "rb"))
local compressed = file:read("*a")
file:close()
local capacity = #compressed * 4
local decompressed = ffi.new("unsigned char[?]", capacity)
local length = ffi.new("unsigned long[1]", capacity)
assert(zlib.uncompress(decompressed, length, compressed, #compressed) == 0, "Unable to inflate the bundled Lethal Pride data")

local function rebuild()
	build.buildFlag = true
	runCallback("OnFrame")
	return build.calcsTab.mainOutput
end

local function equipLethalPride(socketId, seed)
	local spec = build.spec
	local socket = assert(spec.nodes[socketId], "Missing a fixture jewel socket")
	spec:AllocNode(socket)
	local item = new("Item"):Item(string.format([[Rarity: UNIQUE
Lethal Pride
Timeless Jewel
Radius: Large
Limited to: 1 Historic
Implicits: 0
Commanded leadership over %d warriors under Kaom
Passives in radius are Conquered by the Karui
Historic]], seed))
	build.itemsTab:AddItem(item, true)
	spec.jewels[socketId] = item.id
	build.itemsTab.sockets[socketId].selItemId = item.id
end

local function setIgnoreLimits(ignoreLimits)
	build.configTab.input.ignoreJewelLimits = ignoreLimits
	build.configTab:BuildModList()
	return rebuild()
end

local function checkReload(ignoreLimits)
	setIgnoreLimits(ignoreLimits)
	build.spec:BuildAllDependsAndPaths()
	rebuild()
	loadBuildFromXML(build:SaveDB("code"), "Historic jewel limit repro")
	local opened = build.calcsTab.mainOutput
	local strength, life = opened.Str, opened.Life
	build.spec:BuildAllDependsAndPaths()
	local rebuilt = rebuild()
	print(string.format("Ignore Jewel Limits = %s: reopened %d Strength / %d Life, rebuilt %d Strength / %d Life",
		tostring(ignoreLimits), strength, life, rebuilt.Str, rebuilt.Life))
	return strength == rebuilt.Str and life == rebuilt.Life, rebuilt.Str
end

local function checkToggle(ignoreLimits)
	local changed = setIgnoreLimits(ignoreLimits)
	local strength, life = changed.Str, changed.Life
	build.spec:BuildAllDependsAndPaths()
	local rebuilt = rebuild()
	print(string.format("Toggle Ignore Jewel Limits to %s: immediate %d Strength / %d Life, rebuilt %d Strength / %d Life",
		tostring(ignoreLimits), strength, life, rebuilt.Str, rebuilt.Life))
	return strength == rebuilt.Str and life == rebuilt.Life
end

newBuild()
local lethalPride = assert(isValueInArray(data.timelessJewelTypes, "Lethal Pride"))
data.timelessJewelLUTs[lethalPride] = { data = ffi.string(decompressed, length[0]) }
equipLethalPride(26196, 10000)
equipLethalPride(26725, 12000)
local limitedStable, limitedStrength = checkReload(false)
local ignoredStable, ignoredStrength = checkReload(true)
local enabledImmediately = checkToggle(false)
local ignoredImmediately = checkToggle(true)

build.itemsTab.sockets[26725]:SetSelItemId(0)
local singleStable, singleStrength = checkReload(false)

assert(ignoredStable and ignoredStrength > limitedStrength, "The control case must count the second jewel when limits are ignored")
assert(singleStable and singleStrength == limitedStrength, "With limits on, the second jewel should match the result with the second socket empty")
assert(limitedStable and enabledImmediately and ignoredImmediately,
	"Jewel limit changes must apply at load time and on toggling, without an extra passive tree rebuild")
