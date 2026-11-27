-- A passive tree preview should predict the result of allocating the socket.
local function rebuild()
	build.buildFlag = true
	runCallback("OnFrame")
	return build.calcsTab.mainOutput.Str
end

local function equipSplitPersonality(socket)
	local jewel = new("Item"):Item([[Rarity: UNIQUE
Split Personality
Crimson Jewel
Implicits: 0
Limited to: 2
This Jewel's Socket has 25% increased effect per Allocated Passive Skill between
it and your Class' starting location
+5 to Strength
+5 to maximum Life]])
	build.itemsTab:AddItem(jewel, true)
	build.spec.jewels[socket.id] = jewel.id
	build.itemsTab.sockets[socket.id].selItemId = jewel.id
end

newBuild()
local spec = build.spec
local socket = assert(spec.nodes[26196], "Missing the fixture's jewel socket")
spec:AllocNode(socket)
equipSplitPersonality(socket)
local initial = rebuild()
assert(socket.distanceToClassStart > 0, "Fixture must grant scaled jewel stats")

spec:DeallocNode(socket)
local before = rebuild()
assert(not socket.alloc and #socket.path == 1, "The preview should allocate only the socket")
local calculate = build.calcsTab:GetMiscCalculator()
local preview = calculate({ addNodes = { [socket] = true } }).Str
assert(not socket.alloc and build.calcsTab.mainOutput.Str == before, "The preview changed the live build")
spec:AllocNode(socket)
local after = rebuild()

print(string.format("Split Personality: preview %+d Strength, allocation %+d Strength", preview - before, after - before))
assert(after == initial and after - before > 5, "Reallocating the socket should restore its scaled stats")
local allocationMatches = preview == after

newBuild()
spec = build.spec
socket = assert(spec.nodes[2491], "Missing the shortcut fixture's jewel socket")
-- This allocated route reaches the socket without taking node 22703.
local detour = { }
for _, id in ipairs({2491, 18901, 62319, 34400, 14056, 6741, 24865, 476, 30691, 43374, 49178, 30733,
	46578, 28330, 19144, 35503, 36881, 33508, 48828}) do
	detour[#detour + 1] = assert(spec.nodes[id], "Missing a passive on the detour")
end
spec:AllocNode(socket, detour)
equipSplitPersonality(socket)
before = rebuild()
local originalDistance = socket.distanceToClassStart
local shortcut = assert(spec.nodes[22703], "Missing the shortcut passive")
assert(not shortcut.alloc and #shortcut.path == 1, "Only the shortcut passive should need allocation")
calculate = build.calcsTab:GetMiscCalculator()
preview = calculate({ addNodes = { [shortcut] = true } }).Str
assert(not shortcut.alloc and socket.distanceToClassStart == originalDistance, "The preview changed the live path")
spec:AllocNode(shortcut)
after = rebuild()
assert(socket.distanceToClassStart < originalDistance, "Allocating the shortcut must reduce the allocated distance")

print(string.format("Shorter path: distance %d to %d, preview %+d Strength, allocation %+d Strength",
	originalDistance, socket.distanceToClassStart, preview - before, after - before))
assert(allocationMatches and preview == after, "Tree previews must use the simulated allocation's distances to the class start")
