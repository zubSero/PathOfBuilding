"""Run targeted Windows specs, a batch, or the upstream Linux/CI checks."""

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

from run_headless import PROJECT


TESTS = Path(__file__).resolve().parent
UPSTREAM = "PathOfBuildingCommunity/PathOfBuilding"
IMAGE = "ghcr.io/pathofbuildingcommunity/pathofbuilding-tests:latest"
JOBS = ("run_tests", "check_modcache")


def windows_check(repo, tools, specs=()):
    command = [sys.executable, "-B", str(TESTS / "run_headless.py"), "--repo", str(repo), "--busted"]
    if tools:
        command.extend(("--tools", str(tools.resolve())))
    if specs:
        command.extend(("--", *(spec.as_posix() for spec in specs)))
    return subprocess.run(command, cwd=repo).returncode


def installed_wsl_distros():
    if not shutil.which("wsl.exe"):
        return []
    result = subprocess.run(["wsl.exe", "--list", "--quiet"], capture_output=True, timeout=15)
    if result.returncode:
        return []
    encoding = "utf-16-le" if b"\x00" in result.stdout else "utf-8-sig"
    names = [line.strip().lstrip("\ufeff") for line in result.stdout.decode(encoding).splitlines()]
    return [name for name in names if name and name not in ("docker-desktop", "docker-desktop-data")]


def choose_linux_backend(backend, distro):
    if backend != "docker":
        available = installed_wsl_distros()
        if distro:
            for name in available:
                if name.casefold() == distro.casefold():
                    return "wsl", name
            raise RuntimeError(f"WSL distribution {distro} is unavailable. See tests/README.md for setup.")
        if available:
            return "wsl", available[0]
        if backend == "wsl":
            raise RuntimeError("No WSL Linux distribution is available. See tests/README.md for setup.")
    if shutil.which("docker"):
        return "docker", None
    raise RuntimeError("Linux checks need WSL or Docker. For a published PR, use the ci command.")


def run_wsl(repo, distro, mode):
    script = (TESTS / "check_linux.sh").read_bytes().replace(b"\r\n", b"\n")
    return subprocess.run(
        ["wsl.exe", "--distribution", distro, "--exec", "sh", "-s", "--", mode],
        cwd=repo, input=script,
    ).returncode


def linux_check(repo, backend, distro):
    if backend == "wsl":
        return run_wsl(repo, distro, "wsl")
    return subprocess.run(
        ["docker", "run", "--rm", "--security-opt", "no-new-privileges", "-e", "HOME=/tmp",
         "--workdir", "/workdir",
         "--mount", f"type=bind,source={repo},target=/workdir,readonly",
         "--mount", f"type=bind,source={TESTS / 'check_linux.sh'},target=/pob-check-linux.sh,readonly",
         IMAGE, "sh", "/pob-check-linux.sh"],
        cwd=repo,
    ).returncode


def workflow_jobs(checks):
    matching = {}
    for check in checks:
        job = check.get("name", "").rsplit("/", 1)[-1].split(" (", 1)[0].strip()
        if check.get("workflowName") == "Run Tests" and job in JOBS:
            previous = matching.get(job)
            if previous is None or (check["startedAt"] or "") > (previous["startedAt"] or ""):
                matching[job] = check
    return matching


def ci_check(number, repository):
    result = subprocess.run(
        ["gh", "pr", "view", str(number), "--repo", repository, "--json", "statusCheckRollup"],
        capture_output=True, encoding="utf-8", timeout=60,
    )
    if result.returncode:
        print(result.stderr.strip(), file=sys.stderr)
        return result.returncode
    checks = workflow_jobs(json.loads(result.stdout)["statusCheckRollup"] or [])
    failed, waiting = False, False
    for job in JOBS:
        check = checks.get(job)
        if not check:
            print(f"{job}\tawaiting a check result")
            waiting = True
        else:
            status = (check.get("conclusion") or "unknown").lower() if check["status"] == "COMPLETED" else "pending"
            print(f"{job}\t{status}\t{check['detailsUrl']}")
            waiting = waiting or status == "pending"
            failed = failed or status not in ("success", "pending")
    if failed:
        return 1
    return 8 if waiting else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout", type=Path, default=PROJECT)
    parser.add_argument("--tools", type=Path, help="override the Windows Busted toolchain")
    commands = parser.add_subparsers(dest="mode", required=True)
    quick = commands.add_parser("quick", help="run one or more specs")
    quick.add_argument("specs", nargs="+", metavar="TestName_spec.lua")
    backend_options = argparse.ArgumentParser(add_help=False)
    backend_options.add_argument("--backend", choices=("auto", "wsl", "docker"), default="auto")
    backend_options.add_argument("--distro", help="select a WSL distribution")
    batch = commands.add_parser("batch", parents=[backend_options], help="run the full Windows suite")
    batch.add_argument("--linux", action="store_true", help="also run the Linux suite and check ModCache there")
    commands.add_parser("linux", parents=[backend_options], help="run the suite and ModCache in WSL or Docker")
    setup_wsl = commands.add_parser("setup-wsl", help="prepare the test toolchain in an existing WSL distribution")
    setup_wsl.add_argument("--distro", help="select a WSL distribution")
    ci = commands.add_parser("ci", help="check both upstream CI jobs for a PR")
    ci.add_argument("number", type=int)
    ci.add_argument("--github-repo", default=UPSTREAM)
    args = parser.parse_args()

    try:
        if args.mode == "ci":
            if args.number < 1:
                parser.error("the PR number must be positive")
            return ci_check(args.number, args.github_repo)
        repo = args.checkout.resolve(strict=True)
        if args.mode == "setup-wsl":
            _, distro = choose_linux_backend("wsl", args.distro)
            return run_wsl(repo, distro, "setup-wsl")
        run_linux = args.mode == "linux" or (args.mode == "batch" and args.linux)
        if run_linux:
            if args.backend == "docker" and args.distro:
                parser.error("--distro selects a WSL distribution")
            backend, distro = choose_linux_backend(args.backend, args.distro)
        if args.mode == "quick":
            specs = [repo / "spec/System" / Path(name).name for name in args.specs]
            for spec in specs:
                if not spec.name.endswith("_spec.lua") or not spec.is_file():
                    parser.error(f"Unknown system spec {spec.name}")
            return windows_check(repo, args.tools, list(dict.fromkeys(specs)))
        if args.mode == "batch":
            status = windows_check(repo, args.tools)
            if status:
                return status
        return linux_check(repo, backend, distro) if run_linux else 0
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as failure:
        print(failure, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
