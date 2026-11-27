# Headless Path of Building testing

## Set up Windows

Run this from the repository root with 64-bit Python 3.11 or newer.

```powershell
py tests/setup_headless.py
```

Setup downloads pinned Busted 2.2 dependencies and a build toolchain, checks their SHA-256 digests and runs a PoB smoke test. It publishes the verified dependency tree under `tests/.headless`. The next invocation checks and reuses it. Use `--tools` with setup and the runners to share a cache across checkouts or use an existing LuaRocks tree. The runners use the LuaJIT DLL supplied by PoB.

## Find and reproduce a bug

1. Scan recent open issues with the authenticated GitHub CLI. The scan includes bug reports and unlabeled issues and skips issues with a linked open PR. Search for open PRs that mention the bug without a closing link as well.
2. Identify the affected PoB or game version, the build and config, and the expected result. For calculations that depend on game behavior, record the in-game measurement or other evidence behind the expected value.
3. Reproduce against the current upstream `dev` revision before making a fix. Work in an isolated checkout with a fresh profile. For a UI-only bug, use the Windows runtime and record the interaction and result.

```powershell
py tests/scan_issues.py --limit 50
git fetch https://github.com/PathOfBuildingCommunity/PathOfBuilding.git dev
py tests/replay_build.py --issue 10586 --against FETCH_HEAD --stat CorruptingBloodDPS --set conditionCorruptingCryStages=0
```

Replay reads one actual PoE1 build code or XML export. Give it a file, `--code` or stdin. A saved GitHub issue or pasted Discord message works if it contains the code in plain text or a Markdown block. `--issue` reads an issue body through `gh`. If a report contains several builds, select the one you want to replay.

```powershell
py tests/replay_build.py .\build.txt --against FETCH_HEAD --stat TotalEHP --stat Minion.Life --probe minion:INC:Speed --show-config
py tests/replay_build.py .\build.xml --baseline-dir ..\PathOfBuilding-dev --set enemyIsBoss=Pinnacle --json
'newBuild(); assert(build.calcsTab.mainOutput.Life > 0)' | py tests/run_headless.py -
```

`--against` accepts a local commit or ref and creates a temporary detached worktree. `--baseline-dir` uses an existing checkout. Both calculations receive the same build and overrides. `--set` accepts numbers, booleans, strings and `null` for clearing an input. `--probe` reads modifier totals, multipliers, overrides or flags from the player, enemy, minion or active skill. `--json` includes the observed config inputs and placeholders. The scripts calculate in a temporary profile without saving over the build being replayed.

## Fix and verify

Add a regression in the relevant `spec/System` file. Verify that it fails for the reported reason on `dev` and passes with the fix. Run the affected specs while iterating. Run the full suite once the batch is ready.

```powershell
py tests/check_headless.py quick TestFlasks_spec.lua TestConfigTab_spec.lua
py tests/check_headless.py batch
py -B -m unittest discover -s tests -p test_headless_tools.py
```

### Run the Linux checks in WSL

The `linux` command prefers an installed WSL distribution and can also use the Docker image from PoB's GitHub workflow. Both backends run the suite and check ModCache in a scratch copy.

If WSL is absent, install Ubuntu with `wsl --install -d Ubuntu` from administrator PowerShell. Restart Windows and start Ubuntu once to finish the first-time setup. See [Microsoft's WSL installation guide](https://learn.microsoft.com/en-us/windows/wsl/install).

Install these prerequisites inside Ubuntu. The PoB setup uses the LuaJIT revision from the Dockerfile and installs Busted and Lua UTF-8 into a user cache.

```bash
sudo apt-get update
sudo apt-get install build-essential ca-certificates git liblua5.1-0-dev lua5.1 luarocks unzip
```

Then run from the PoB checkout in Windows PowerShell.

```powershell
py tests/check_headless.py setup-wsl --distro Ubuntu
py tests/check_headless.py linux --backend wsl --distro Ubuntu
py tests/check_headless.py batch --linux --backend wsl --distro Ubuntu
```

For a published PR, `py tests/check_headless.py ci 10585` reads the existing GitHub jobs. It requires a pass from both jobs and returns exit code 8 while results are pending or missing.

## Log Timeless Jewel checks

Add reproducible cases and data comparisons to [the Timeless Jewel audit log](timeless-jewel-audit.json). Track coverage work in [PoB issue #10601](https://github.com/PathOfBuildingCommunity/PathOfBuilding/issues/10601).

- Record the tree version, jewel, seed, variant, socket and relevant build inputs. Include the exact target passive, replacement or stat rolls and link the source of the expected result.
- Record the expected result's evidence type. Use `in_game` for a direct game observation and `packaged_data` for values read from a versioned PoB archive. Keep predicted results and counts under `model_comparisons`.
- Pin the PoB revisions and record what the equipped tree, jewel finder and final build modifiers actually do when each applies. Record any downstream data revision and result separately.
- For a generation run, keep the full diff of changed cases and record the scope and counts in the audit log. Add a new entry when the game data or verified results change.

```powershell
$audit = Get-Content -Raw tests/timeless-jewel-audit.json | ConvertFrom-Json
$audit.cases | Select-Object issue, tree_version, jewel, seed, @{Name='Evidence'; Expression={$_.expected.kind}}
```

## Capture PoB screenshots on Windows

The screenshot runner uses PoB's renderer on a private Windows desktop. It keeps the active desktop in place and loads the requested Git revision in a temporary worktree with its own build and settings directories. The runtime writes a JPEG, and the runner exits after copying it to the requested destination.

Write a Lua recipe that receives a new build as its first argument. For example, save this as `config-example.lua`.

```lua
local build = ...
build.skillsTab:PasteSocketGroup("Fireball 20/0  1\n")
build.mainSocketGroup = #build.skillsTab.socketGroupList
build.viewMode = "CONFIG"
```

```powershell
py -B tests/capture_screenshot.py --ref HEAD config-example.lua .\captures\config-after
py -B tests/capture_screenshot.py --ref FETCH_HEAD config-example.lua .\captures\config-before
```

Leave the output extension off. A recipe can return a function that also receives the build. The runner calls it after the initial edits have had time to rebuild, so it can click a setup button or open a popup before the capture.

## Publish when requested

Keep fixes independently reviewable. A testing batch can combine separate commits on the testing branch. For upstream review, use a focused branch targeting `dev`, link the issue, and include the before-and-after result and the tests that ran. Use `Fixes #number` when the PR resolves the full issue. Keep a related issue linked as context if the fix covers part of it.
