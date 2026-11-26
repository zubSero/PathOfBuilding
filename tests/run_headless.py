"""Run a Lua repro with PoB's bundled Windows LuaJIT and headless wrapper."""

import argparse
import ctypes
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory


BOOTSTRAP = b"""
arg = { [0] = "HeadlessWrapper.lua" }
local read = io.read
local startupError
io.read = function() startupError = true end
dofile("HeadlessWrapper.lua")
io.read = read
assert(not startupError and newBuild, "Path of Building failed to initialise")
"""


def busted_chunk(arguments):
    def quote(value):
        return '"' + "".join(f"\\{byte:03d}" for byte in value.encode("utf-8")) + '"'

    options = ", ".join(quote(argument) for argument in arguments)
    return f"""
arg = {{ [0] = "busted", {options} }}
local exitStatus
local originalExit = os.exit
os.exit = function(status)
    exitStatus = status or 0
    error("Busted exit", 0)
end
local ok, failure = pcall(function()
    require("busted.runner")({{ standalone = false, output = "plainTerminal" }})
end)
os.exit = originalExit
if exitStatus == nil and not ok then error(failure, 0) end
if exitStatus and exitStatus ~= 0 then error("Busted failed", 0) end
""".encode("utf-8")


def run_lua(runtime, chunks):
    lua = ctypes.CDLL(str(runtime / "lua51.dll"))
    lua.luaL_newstate.restype = ctypes.c_void_p
    lua.luaL_openlibs.argtypes = [ctypes.c_void_p]
    lua.luaL_loadbuffer.argtypes = [
        ctypes.c_void_p, ctypes.c_char_p, ctypes.c_size_t, ctypes.c_char_p
    ]
    lua.lua_pcall.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int]
    lua.lua_tolstring.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
    lua.lua_tolstring.restype = ctypes.c_char_p
    lua.lua_close.argtypes = [ctypes.c_void_p]

    state = lua.luaL_newstate()
    if not state:
        raise RuntimeError("Could not initialise LuaJIT")
    try:
        lua.luaL_openlibs(state)
        for name, source in chunks:
            error = lua.luaL_loadbuffer(state, source, len(source), name.encode("utf-8"))
            if error or lua.lua_pcall(state, 0, 0, 0):
                message = lua.lua_tolstring(state, -1, None)
                raise RuntimeError(message.decode("utf-8", errors="replace") if message else name)
    finally:
        lua.lua_close(state)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--busted", action="store_true", help="run the project's Busted suite")
    parser.add_argument("--tools", type=Path, help="Busted's LuaRocks tree (default: tests/.headless)")
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("arguments", nargs=argparse.REMAINDER, help="Lua file, -, or Busted arguments after --")
    args = parser.parse_args()
    if sys.platform != "win32" or ctypes.sizeof(ctypes.c_void_p) != 8:
        parser.error("the bundled PoB runtime requires 64-bit Python on Windows")

    arguments = args.arguments
    if arguments[:1] == ["--"]:
        arguments = arguments[1:]
    if not args.busted and len(arguments) != 1:
        parser.error("provide one Lua file or -")
    try:
        repo = args.repo.resolve(strict=True)
        runtime = repo / "runtime"
        lua_path = [f"{runtime.as_posix()}/lua/?.lua", f"{runtime.as_posix()}/lua/?/init.lua"]
        lua_cpath = [f"{runtime.as_posix()}/?.dll"]
        if args.busted:
            tools = (args.tools or Path(__file__).resolve().parent / ".headless").resolve()
            share = (tools / "share/lua/5.1").as_posix()
            if not (Path(share) / "busted/runner.lua").is_file():
                raise RuntimeError(f"Busted is missing from {tools}. See tests/README.md.")
            lua_path[:0] = [f"{share}/?.lua", f"{share}/?/init.lua"]
            lua_cpath.insert(0, f"{tools.as_posix()}/lib/lua/5.1/?.dll")
            os.chdir(repo)
            chunks = [("=busted", busted_chunk(arguments))]
        else:
            if arguments[0] == "-":
                name, source = "=stdin", sys.stdin.buffer.read()
            else:
                path = Path(arguments[0]).resolve(strict=True)
                name, source = "@" + str(path), path.read_bytes()
            os.chdir(repo / "src")
            chunks = [("=headless bootstrap", BOOTSTRAP), (name, source)]
        os.environ["LUA_PATH"] = ";".join(lua_path) + ";;"
        os.environ["LUA_CPATH"] = ";".join(lua_cpath) + ";;"
        os.environ["CI"] = "true"
        with TemporaryDirectory(prefix="pob-headless-") as profile, os.add_dll_directory(str(runtime)):
            os.environ["POB_HEADLESS_PROFILE"] = Path(profile).as_posix()
            run_lua(runtime, chunks)
    except (OSError, RuntimeError) as failure:
        print(failure, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
