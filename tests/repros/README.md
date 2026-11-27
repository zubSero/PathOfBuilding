# Headless bug reproductions

Run these from the testing checkout on Windows. Point `--repo` to a separate PoB checkout at the revision you want to test.

```powershell
py -B tests/run_headless.py --repo ..\PathOfBuilding-dev tests/repros/10429-split-personality.lua
py -B tests/run_headless.py --repo ..\PathOfBuilding-dev tests/repros/10430-historic-jewel-limit.lua
py -B tests/run_headless.py --repo ..\PathOfBuilding-dev tests/repros/10427-item-granted-skill-preview.lua
```

Each script uses a synthetic build and checks an invariant. On upstream `dev` at `bfee69d`, each should exit with code 1 at the assertion for its reported bug. The scripts should exit successfully after the fixes.

| Issue | What the replay checks |
| --- | --- |
| [#10429](https://github.com/PathOfBuildingCommunity/PathOfBuilding/issues/10429) | The tree preview agrees with actual allocation both for a socket containing Split Personality and for a passive that shortens the route to an already allocated socket. |
| [#10430](https://github.com/PathOfBuildingCommunity/PathOfBuilding/issues/10430) | With two Lethal Prides, loading or toggling the limit should give the same stats as rebuilding the passive paths. The controls cover bypassing jewel limits and using a single Lethal Pride. |
| [#10427](https://github.com/PathOfBuildingCommunity/PathOfBuilding/issues/10427) and [#8093](https://github.com/PathOfBuildingCommunity/PathOfBuilding/issues/8093) | The item preview predicts both DPS totals when the candidate grants or removes Envy. Previewing the equipped item produces the same DPS and leaves the equipped item and skill groups in place. |

## Analysis

- Split Personality scaling reads `distanceToClassStart` from the live passive spec. A preview builds a separate set of allocated nodes, but the cached distance describes the original tree. The distance calculation needs to use the preview's allocations when it simulates a tree change. [Allocation override and jewel scaling](https://github.com/PathOfBuildingCommunity/PathOfBuilding/blob/bfee69d10cceef87b7125155645b4d03091ac6ac/src/Modules/CalcSetup.lua#L723)
- The tree applies timeless conquests using the jewel item's `limitDisabled` flag. A later calculation sets that flag. Immediately after loading a build, the initial passive paths therefore use the wrong eligibility until another tree rebuild. Test the same limit decision during initial load, subsequent rebuilds and config changes. [Tree rebuild](https://github.com/PathOfBuildingCommunity/PathOfBuilding/blob/bfee69d10cceef87b7125155645b4d03091ac6ac/src/Classes/PassiveSpec.lua#L1133) · [Limit calculation](https://github.com/PathOfBuildingCommunity/PathOfBuilding/blob/bfee69d10cceef87b7125155645b4d03091ac6ac/src/Modules/CalcSetup.lua#L860)
- The item preview collects the candidate's granted skills, but only the main calculation creates and removes the associated skill groups. The preview needs its own effective groups while preserving the live groups and their settings. [Item override and granted skills](https://github.com/PathOfBuildingCommunity/PathOfBuilding/blob/bfee69d10cceef87b7125155645b4d03091ac6ac/src/Modules/CalcSetup.lua#L828) · [Skill group setup](https://github.com/PathOfBuildingCommunity/PathOfBuilding/blob/bfee69d10cceef87b7125155645b4d03091ac6ac/src/Modules/CalcSetup.lua#L1508)
