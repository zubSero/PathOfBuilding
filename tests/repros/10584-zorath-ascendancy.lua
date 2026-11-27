-- In-game evidence: https://github.com/PathOfBuildingCommunity/PathOfBuilding/issues/10584
-- Run with tests/run_headless.py against a checkout with the 3.30 passive tree.
local ffi = require("ffi")
ffi.cdef[[
	int uncompress(unsigned char *dest, unsigned long *destLen,
		const unsigned char *source, unsigned long sourceLen);
]]
local zlib = ffi.load("../runtime/zlib1.dll")

-- Run the regular multipart loader with zlib in place of the headless stub.
Inflate = function(compressed)
	local capacity = #compressed * 4
	while true do
		local buffer = ffi.new("unsigned char[?]", capacity)
		local length = ffi.new("unsigned long[1]", capacity)
		local status = zlib.uncompress(buffer, length, compressed, #compressed)
		if status == 0 then
			return ffi.string(buffer, length[0])
		end
		assert(status == -5, "Unable to inflate bundled Zorath data (zlib status " .. status .. ")")
		capacity = capacity * 2
	end
end

newBuild()
local spec = build.spec
assert(spec.treeVersion == "3_30", "Use a checkout with the 3.30 passive tree for this repro")
spec:SelectClass(spec.tree.classNameMap.Shadow)
spec:SelectAscendClass(spec.tree.ascendNameMap.Assassin.ascendClassId)

local socketId, opportunisticId, toxicDeliveryId = 41263, 19083, 19598
for _, id in ipairs({ socketId, opportunisticId, toxicDeliveryId }) do
	local node = assert(spec.nodes[id], "Missing fixture node " .. id)
	spec:AllocNode(node)
	assert(spec.allocNodes[id], "Could not allocate fixture node " .. id)
end
assert(spec:GetShortestPathToClassStart(socketId), "The jewel socket must connect to the class start")
assert(spec.nodes[opportunisticId].dn == "Opportunistic" and spec.nodes[toxicDeliveryId].dn == "Toxic Delivery",
	"Unexpected base names for the Assassin notables")

local jewel = new("Item"):Item([[Rarity: UNIQUE
Reclaimed Malevolence
Assembled Eye Jewel
Limited to: 1 Historic
Implicits: 0
Binding 6696 souls to phylacteries to sustain Zorath
Passives affected are Conquered by the Abyssal
Historic]])
assert(jewel.jewelData.conqueredBy.id == 6696, "The item's seed must be parsed")
build.itemsTab:AddItem(jewel, true)
build.itemsTab.sockets[socketId]:SetSelItemId(jewel.id)
spec:BuildAllDependsAndPaths()

local opportunistic = spec.nodes[opportunisticId].dn
local toxicDelivery = spec.nodes[toxicDeliveryId].dn
print(string.format("Zorath 6696, Assassin at socket %d: Opportunistic => %s, Toxic Delivery => %s",
	socketId, opportunistic, toxicDelivery))
assert(opportunistic == "From Below" and toxicDelivery == "Toxic Delivery",
	"PoE 3.30 replaces Opportunistic with From Below and keeps Toxic Delivery")

-- The in-game tooltip in the issue shows both parts of From Below.
local stats = table.concat(spec.nodes[opportunisticId].sd, "\n")
assert(stats:find("Insufficient Mana doesn't prevent your Spells", 1, true)
	and stats:find("Cannot recover Mana", 1, true), "Expected both in-game From Below stats")
