"""Install and smoke-test PoB's pinned Windows Busted toolchain."""

import argparse
import ctypes
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from urllib.request import urlopen
from uuid import uuid4
from zipfile import ZipFile

from run_headless import DEFAULT_TOOLS, PROJECT, tool_tree


ROCKS = "https://luarocks.org"
MSYS = "https://repo.msys2.org/mingw/ucrt64"
SOURCES = {
    "busted-2.2.0-1.src.rock": (ROCKS, "6a9415c62ba03e3b8c210acb3b04df2a779146c9dd78caa02d67f47a13d14476"),
    "lua_cliargs-3.0-2.src.rock": (ROCKS, "3c79981292aab72dbfba9eb5c006bb37c5f42ee73d7062b15fdd840c00b70d63"),
    "luasystem-0.2.1-0.src.rock": (ROCKS, "d1c706d48efc7279d33f5ea123acb4d27e2ee93e364bedbe07f2c9c8d0ad3d24"),
    "luassert-1.9.0-1.src.rock": (ROCKS, "146a7b2ec8e0cadf7dbca6dc993debcd2090e0e4fdf5c632d9f4ec20670357dd"),
    "say-1.4.1-3.src.rock": (ROCKS, "90a1c0253ec38d6628007eef0b424d0707d0f3e0442fce478a627111eb02bb07"),
    "penlight-1.14.0-3.src.rock": (ROCKS, "84e4d23126694a57997d5499490023468190a4b14a64931da61de627ce4fe0c2"),
    "v1.1.2-0": ("https://codeload.github.com/Olivine-Labs/mediator_lua/tar.gz/refs/tags",
                 "faf5859fd2081be4e9e4fb8873a2dc65f7eff3fd93d6dd14da65f8e123fcff9b"),
    "0.8": ("https://codeload.github.com/hoelzro/lua-term/tar.gz/refs/tags",
            "0cb270be22dfc262beec2f4ffc66b878ccaf236f537d693fa36c8f578fc51aa6"),
    "mingw-w64-ucrt-x86_64-luajit-2.1.1793275035-1-any.pkg.tar.zst": (
        MSYS, "fb9240d58ba413e3e6066618b7e797adb65c1b02ebb02b226e8bee4a5a03eba0"),
    "mingw-w64-ucrt-x86_64-lua51-luafilesystem-1.9.0-2-any.pkg.tar.zst": (
        MSYS, "6c78b1cd0c92035d8421b464491452be6aab198ac68a11796745bfaa12ba9e3d"),
    "ziglang-0.15.2-py3-none-win_amd64.whl": (
        "https://files.pythonhosted.org/packages/b9/6b/8ab0853a312108b4089747486366b824b5da89773cb56f661f9994de17db",
        "ca80dc9c70dbdfdd9ee51d000de3501a95d33d9782ab9ab9b56f700484ebcd83"),
}

MODULES = {
    "busted": "busted/busted",
    "cliargs": "lua_cliargs-3.0-2/src/cliargs",
    "system": "luasystem-0.2.1/system",
    "luassert": "luassert/src",
    "say": "say/src/say",
    "pl": "penlight/lua/pl",
    "term": "lua-term-0.8/term",
}
LOCK = hashlib.sha256(repr(("1", SOURCES, MODULES)).encode()).hexdigest()[:16]


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def archive(name, cache, staging):
    origin, expected = SOURCES[name]
    path = cache / name
    if path.is_file() and sha256(path) == expected:
        return path
    print(f"Downloading {name}", flush=True)
    pending = staging / name
    with urlopen(f"{origin}/{name}", timeout=60) as response, pending.open("wb") as output:
        shutil.copyfileobj(response, output)
    if sha256(pending) != expected:
        raise RuntimeError(f"SHA-256 mismatch for {name}")
    pending.replace(path)
    return path


def assemble(tree, cache, staging):
    sources = staging / "sources"
    sources.mkdir()
    for name in SOURCES:
        package = archive(name, cache, staging)
        if name.endswith((".rock", ".whl")):
            with ZipFile(package) as bundle:
                bundle.extractall(sources)
        else:
            subprocess.run(["tar", "-xf", str(package), "-C", str(sources)], check=True)
    for package in sorted(sources.glob("*.tar.gz")):
        subprocess.run(["tar", "-xf", str(package), "-C", str(sources)], check=True)

    share = tree / "share/lua/5.1"
    lib = tree / "lib/lua/5.1"
    lib.mkdir(parents=True)
    for module, location in MODULES.items():
        shutil.copytree(sources / location, share / module)
    shutil.copy2(sources / "mediator_lua-1.1.2-0/src/mediator.lua", share)
    ucrt = sources / "ucrt64"
    shutil.copy2(ucrt / "lib/lua/5.1/lfs.dll", lib)

    compiler = sources / "ziglang/zig.exe"
    headers = ucrt / "include/luajit-2.1"
    import_library = ucrt / "lib/libluajit-5.1.dll.a"
    for module, files in {
        "system": sorted((sources / "luasystem-0.2.1/src").glob("*.c")),
        "term": [sources / "lua-term-0.8/core.c"],
    }.items():
        destination = lib / module / "core.dll"
        destination.parent.mkdir()
        print(f"Building {module}/core.dll", flush=True)
        subprocess.run(
            [str(compiler), "cc", "-target", "x86_64-windows-gnu", "-shared", "-O2",
             "-DLUA_BUILD_AS_DLL", "-Wno-inconsistent-dllimport", "-I", str(headers),
             *(str(path) for path in files), str(import_library), "-o", str(destination)],
            check=True,
        )
    (tree / "dependency-lock").write_text(LOCK, encoding="ascii")


def smoke(tree):
    return subprocess.run(
        [sys.executable, "-B", str(PROJECT / "tests/run_headless.py"), "--tools", str(tree),
         "--busted", "--", "-p", "TestUtils_spec.lua"],
        cwd=PROJECT,
        timeout=120,
    ).returncode == 0


def install(tools):
    tools.mkdir(parents=True, exist_ok=True)
    current = tool_tree(tools)
    lock = current / "dependency-lock"
    if lock.is_file() and lock.read_text(encoding="ascii") == LOCK and smoke(current):
        print(f"Reused verified toolchain {current}")
        return

    cache = tools / "downloads"
    cache.mkdir(exist_ok=True)
    with TemporaryDirectory(prefix="setup-", dir=tools) as directory:
        staging = Path(directory)
        tree = staging / "install"
        assemble(tree, cache, staging)
        if not smoke(tree):
            raise RuntimeError("The new toolchain failed its PoB smoke test")
        installed = tools / f"busted-{LOCK}-{uuid4().hex[:8]}"
        tree.rename(installed)
        marker = staging / "active-tree.txt"
        marker.write_text(installed.name + "\n", encoding="ascii")
        marker.replace(tools / marker.name)
        print(f"Installed and verified toolchain {installed}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tools", type=Path, default=DEFAULT_TOOLS, help="local toolchain cache")
    args = parser.parse_args()
    if sys.platform != "win32" or ctypes.sizeof(ctypes.c_void_p) != 8:
        parser.error("requires 64-bit Windows Python")
    if sys.version_info < (3, 11):
        parser.error("requires Python 3.11 or newer")
    try:
        install(args.tools.resolve())
    except (OSError, RuntimeError, subprocess.SubprocessError) as failure:
        print(failure, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
