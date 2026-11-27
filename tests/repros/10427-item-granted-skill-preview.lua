-- Compare the same stat before previewing, during preview and after equipping.
local function rebuild()
	build.buildFlag = true
	runCallback("OnFrame")
	return build.calcsTab.mainOutput
end

local function nearlyEqual(left, right)
	return math.abs(left - right) <= math.max(1, math.abs(right)) * 1e-6
end

local function sameDps(left, right)
	return nearlyEqual(left.TotalDPS, right.TotalDPS) and nearlyEqual(left.FullDPS, right.FullDPS)
end

newBuild()
local cutlass = new("Item"):Item("Rarity: NORMAL\nCutlass")
build.itemsTab:AddItem(cutlass)
build.skillsTab:PasteSocketGroup("Ethereal Knives 20/0  1\n")
build.skillsTab.socketGroupList[1].includeInFullDPS = true
local withoutEnvy = rebuild()

local envySword = new("Item"):Item("Rarity: UNIQUE\nUnited in Dream\nCutlass\nImplicits: 0\nGrants Level 25 Envy")
build.itemsTab:AddItem(envySword, true)
rebuild()
local weaponSlot = build.itemsTab.slots["Weapon 1"]

local function preview(item)
	local equippedId = weaponSlot.selItemId
	local groups = copyTable(build.skillsTab.socketGroupList, true)
	local calculate = build.calcsTab:GetMiscCalculator()
	local output = calculate({ repSlotName = "Weapon 1", repItem = item })
	assert(weaponSlot.selItemId == equippedId, "Preview changed the equipped item")
	assert(#build.skillsTab.socketGroupList == #groups, "Preview changed the number of live skill groups")
	for index, group in ipairs(groups) do
		assert(build.skillsTab.socketGroupList[index] == group, "Preview changed the live skill groups")
	end
	return output
end

assert(sameDps(preview(cutlass), withoutEnvy), "Comparing the equipped Cutlass to itself should leave DPS unchanged")
local addingEnvy = preview(envySword)
weaponSlot:SetSelItemId(envySword.id)
local withEnvy = rebuild()
local removingEnvy = preview(cutlass)
weaponSlot:SetSelItemId(cutlass.id)
local swappedBack = rebuild()

print(string.format("Add Envy: preview %.2f DPS / %.2f Full DPS, equipped %.2f DPS / %.2f Full DPS",
	addingEnvy.TotalDPS, addingEnvy.FullDPS, withEnvy.TotalDPS, withEnvy.FullDPS))
print(string.format("Remove Envy: preview %.2f DPS / %.2f Full DPS, equipped %.2f DPS / %.2f Full DPS",
	removingEnvy.TotalDPS, removingEnvy.FullDPS, swappedBack.TotalDPS, swappedBack.FullDPS))
assert(withEnvy.TotalDPS > withoutEnvy.TotalDPS and sameDps(swappedBack, withoutEnvy),
	"Envy must increase DPS while equipped in this fixture, and swapping back must restore both DPS totals")
assert(sameDps(addingEnvy, withEnvy) and sameDps(removingEnvy, swappedBack),
	"Item previews must add and remove item-granted Envy just as equipping does")
