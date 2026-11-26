"""Render a Lua screenshot recipe with PoB's Windows runtime."""

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory

from replay_build import checkout_baseline
from run_headless import PROJECT


CAPTURE = r"""
local drawFrame = launch.OnFrame
local frameCount = 0
local afterSetup

local function fail(message)
	local log = assert(io.open(os.getenv("POB_SCREENSHOT_ERROR"), "wb"))
	log:write(message)
	log:close()
	Exit()
end

local function runRecipe(action, build)
	local ok, result = xpcall(function() return action(build) end, debug.traceback)
	if not ok then return fail(result) end
	return result
end

function launch:OnFrame()
	drawFrame(self)
	if self.promptMsg then
		return fail(self.promptMsg)
	end
	frameCount = frameCount + 1
	if frameCount == 1 then
		self.main.disableDevAutoSave = true
		self.main:SetMode("BUILD", false, "Screenshot example")
	elseif frameCount == 3 then
		local recipe, message = loadfile(os.getenv("POB_SCREENSHOT_RECIPE"))
		if not recipe then return fail(message) end
		afterSetup = runRecipe(recipe, self.main.modes.BUILD)
	elseif frameCount == 8 and type(afterSetup) == "function" then
		runRecipe(afterSetup, self.main.modes.BUILD)
	elseif frameCount == 18 then
		TakeScreenshot()
	elseif frameCount == 24 then
		Exit()
	end
end
"""


def capture(checkout, recipe, scratch):
    from windows_desktop import run

    runtime = checkout / "runtime"
    executable = runtime / "Path{space}of{space}Building.exe"
    launch = checkout / "src" / "Launch.lua"
    original = launch.read_bytes()
    error_log = scratch / "capture-error.txt"
    environment = {
        **os.environ,
        "POB_SCREENSHOT_ERROR": str(error_log),
        "POB_SCREENSHOT_RECIPE": str(recipe),
    }
    try:
        launch.write_bytes(original + b"\n" + CAPTURE.encode("utf-8"))
        exit_code = run(executable, runtime, environment, timeout=60)
    finally:
        launch.write_bytes(original)
    if error_log.exists():
        raise RuntimeError(error_log.read_text(encoding="utf-8", errors="replace"))
    if exit_code:
        raise RuntimeError(f"PoB exited with code {exit_code}")

    images = [image for image in (runtime / "SimpleGraphic" / "Screenshots").glob("*") if image.is_file()]
    if len(images) != 1:
        raise RuntimeError(f"Expected one screenshot from PoB, found {len(images)}")
    return images[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recipe", type=Path, help="Lua file receiving a new build as its first argument")
    parser.add_argument("output", type=Path, help="output path without a file extension")
    parser.add_argument("--repo", type=Path, default=PROJECT, help="PoB repository with the Windows runtime")
    parser.add_argument("--ref", default="HEAD", help="Git revision to render (default: HEAD)")
    args = parser.parse_args()
    if sys.platform != "win32":
        parser.error("the PoB screenshot runner requires the Windows graphics runtime")
    if args.output.suffix:
        parser.error("provide an output path without an extension")

    try:
        repo = args.repo.resolve(strict=True)
        recipe = args.recipe.resolve(strict=True)
        with TemporaryDirectory(prefix="pob-capture-") as directory:
            scratch = Path(directory).resolve()
            with checkout_baseline(repo, args.ref, scratch) as checkout:
                screenshot = capture(checkout, recipe, scratch)
                output = args.output.resolve().with_suffix(screenshot.suffix.lower())
                output.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(screenshot, output)
        print(output)
    except (OSError, RuntimeError, subprocess.SubprocessError) as failure:
        print(failure, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
