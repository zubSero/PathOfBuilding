#!/bin/sh
# Run the upstream checks under Linux, in WSL or in the CI container.
set -eu

mode=${1:-container}
luajit_revision=2460b3ff93a1c955de3d62cfc825de7d68dc272e
tools="${XDG_CACHE_HOME:-$HOME/.cache}/pob-headless/$luajit_revision"
rocks="$tools/rocks"

export CI=true
checkout=$(pwd)
scratch=$(mktemp -d)
trap 'rm -rf -- "$scratch"' EXIT

if [ "$mode" = setup-wsl ]; then
    for tool in git make cc luarocks; do
        if ! command -v "$tool" >/dev/null 2>&1; then
            echo "Missing $tool in WSL. See the Ubuntu prerequisites in tests/README.md." >&2
            exit 1
        fi
    done
    if [ ! -x "$tools/luajit/bin/luajit" ]; then
        git init -q "$scratch/luajit"
        git -C "$scratch/luajit" fetch -q --depth=1 https://github.com/LuaJIT/LuaJIT.git "$luajit_revision"
        git -C "$scratch/luajit" checkout -q --detach FETCH_HEAD
        make -C "$scratch/luajit"
        make -C "$scratch/luajit" install PREFIX="$tools/luajit"
    fi
    luarocks --lua-version=5.1 --tree "$rocks" install busted 2.2.0-1
    luarocks --lua-version=5.1 --tree "$rocks" install luautf8 0.1.6-1
fi

if [ "$mode" = wsl ] || [ "$mode" = setup-wsl ]; then
    if [ -x "$tools/luajit/bin/luajit" ] && [ -x "$rocks/bin/busted" ]; then
        export PATH="$tools/luajit/bin:$rocks/bin:$PATH"
        export LUA_PATH="$rocks/share/lua/5.1/?.lua;$rocks/share/lua/5.1/?/init.lua;${LUA_PATH:-;}"
        export LUA_CPATH="$rocks/lib/lua/5.1/?.so;${LUA_CPATH:-;}"
    fi
    if ! command -v busted >/dev/null 2>&1 ||
       ! command -v luajit >/dev/null 2>&1 ||
       ! luajit -e 'assert(loadfile("src/HeadlessWrapper.lua")); assert(require("lua-utf8"))'; then
        echo "Run py tests/check_headless.py setup-wsl to prepare the PoB test toolchain." >&2
        exit 1
    fi
    if [ "$mode" = setup-wsl ]; then
        busted --version
        echo "WSL test toolchain ready at $tools"
        exit 0
    fi
fi

export POB_HEADLESS_PROFILE="$scratch/profile"
mkdir -p "$POB_HEADLESS_PROFILE"

mkdir "$scratch/checkout"
cp -R src spec "$scratch/checkout"
cp manifest.xml .busted "$scratch/checkout"
ln -s "$checkout/runtime" "$scratch/checkout/runtime"
cd "$scratch/checkout"

busted --lua=luajit

cd src
rm Data/ModCache.lua
LUA_PATH="../runtime/lua/?.lua;../runtime/lua/?/init.lua;${LUA_PATH:-;}" \
  REGENERATE_MOD_CACHE=1 luajit HeadlessWrapper.lua

# A Windows checkout may have CRLF even though Git stores the cache as LF.
sed 's/\r$//' "$checkout/src/Data/ModCache.lua" > "$scratch/original-cache.lua"
if ! cmp -s "$scratch/original-cache.lua" Data/ModCache.lua; then
    echo "ModCache.lua changed during regeneration" >&2
    diff -u "$scratch/original-cache.lua" Data/ModCache.lua | head -n 120
    exit 1
fi
echo "ModCache.lua matches the regenerated file"
