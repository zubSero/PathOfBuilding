# Headless Path of Building testing

To find candidates, authenticate the GitHub CLI and scan recent open issues.
The scan includes bug reports and unlabeled issues, and skips issues already
linked to an open PR for closure. Check for PRs without closing links and
reproduce the issue on `dev` before changing code.

```powershell
py tests/scan_issues.py --limit 60
```

On 64-bit Windows with Python 3, use the LuaJIT DLL in the repository to run a
small Lua reproduction without starting the desktop app.

```powershell
'newBuild(); assert(build.calcsTab.mainOutput.Life > 0)' | py tests/run_headless.py -
py tests/run_headless.py C:/path/to/repro.lua
```

Each invocation starts a new Lua state and a temporary PoB profile. The script
runs from `src`, with `newBuild()`, `loadBuildFromXML()` and `runCallback()`
provided by PoB's `HeadlessWrapper.lua`. Lua errors and failed assertions return
a nonzero exit code. Use `--repo` to test another checkout.

For an upstream fix, reproduce the failure on `dev`, then add a regression
case to the relevant file under `spec/System`. The Windows runner uses the
same Busted configuration and specs as CI.

```powershell
py tests/run_headless.py --busted -- -p TestFlasks_spec.lua
py tests/run_headless.py --busted
```

The runner looks for Busted 2.2 and its Lua 5.1 dependencies in
`tests/.headless`, using the LuaRocks tree layout. Use `--tools` for a different
tree. To set up a fresh tree with LuaRocks and a 64-bit LuaJIT toolchain
configured for native modules, run
`luarocks --lua-version=5.1 --tree tests/.headless install busted 2.2.0-1`.
The repository provides the PoB-specific Lua modules and LuaJIT runtime.

With Docker, the repository's prebuilt test image supplies all dependencies.

```powershell
docker compose run --rm busted-tests
```
