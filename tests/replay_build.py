"""Replay a PoB build code, exported XML, or issue body and compare calculations."""

import argparse
import base64
import binascii
from contextlib import contextmanager
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory
from xml.etree import ElementTree
import zlib

from run_headless import PROJECT, lua_quote


TESTS = Path(__file__).resolve().parent
UPSTREAM = "PathOfBuildingCommunity/PathOfBuilding"
MAX_XML_BYTES = 16 * 1024 * 1024
MAX_INPUT_BYTES = 32 * 1024 * 1024
DEFAULT_STATS = ("CombinedDPS", "FullDPS", "TotalEHP", "Life", "EnergyShield")
RESULT_PREFIX = "POB_REPLAY_RESULT "
CODE = re.compile(r"[A-Za-z0-9_+/-]{40,}={0,2}")
FENCE = re.compile(r"(?ms)^ {0,3}~~~[^\n]*\n(.*?)^ {0,3}~~~|^ {0,3}\x60\x60\x60[^\n]*\n(.*?)^ {0,3}\x60\x60\x60")


def decode_build(text):
    """Extract one unique PoB XML document from a code, XML, or Markdown."""
    def candidate(value):
        value = value.strip().lstrip("\ufeff")
        if value.startswith("<"):
            xml = value.encode("utf-8")
        else:
            code = "".join(value.split())
            if not CODE.fullmatch(code):
                return None
            try:
                padded = code + "=" * (-len(code) % 4)
                compressed = base64.b64decode(padded, altchars=b"-_", validate=True)
                decoder = zlib.decompressobj(47)
                xml = decoder.decompress(compressed, MAX_XML_BYTES + 1)
                if not decoder.eof or decoder.unused_data:
                    return None
            except (binascii.Error, zlib.error):
                return None
        if len(xml) > MAX_XML_BYTES or re.search(rb"<!DOCTYPE|<!ENTITY", xml, re.IGNORECASE):
            return None
        try:
            if ElementTree.fromstring(xml).tag == "PathOfBuilding":
                return xml
        except ElementTree.ParseError:
            pass
        return None

    direct = candidate(text)
    if direct is not None:
        return direct
    # Markdown report bodies can contain wrapped codes or other unrelated blocks.
    candidates = (left or right for left, right in FENCE.findall(text))
    builds = set()
    for value in (*candidates, *CODE.findall(text)):
        xml = candidate(value)
        if xml is not None:
            builds.add(xml)
            if len(builds) > 1:
                raise ValueError("Found multiple different PoB builds. Provide one code or XML file.")
    if not builds:
        raise ValueError("No valid PoB for PoE1 build code or XML found.")
    return builds.pop()


def config_override(text):
    name, separator, raw = text.partition("=")
    if not separator or not re.fullmatch(r"[A-Za-z_]\w*", name, re.ASCII):
        raise argparse.ArgumentTypeError("use NAME=VALUE for config overrides")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        value = raw
    if isinstance(value, (list, dict)) or (isinstance(value, float) and not math.isfinite(value)):
        raise argparse.ArgumentTypeError("use a number, boolean, string, or null")
    return name, value


def modifier_probe(text):
    if not re.fullmatch(r"(player|enemy|minion|skill):(BASE|INC|MORE|FLAG|OVERRIDE):[A-Za-z0-9_:]+", text):
        raise argparse.ArgumentTypeError("use SCOPE:TYPE:MODIFIER, for example minion:INC:Speed")
    return text


def read_input(args):
    if args.issue is not None:
        response = subprocess.check_output(
            ["gh", "issue", "view", str(args.issue), "--repo", args.github_repo, "--json", "body"],
            timeout=45,
        )
        return json.loads(response)["body"]
    if args.code is not None:
        return args.code
    if args.input in (None, "-"):
        data = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
    else:
        with Path(args.input).open("rb") as source:
            data = source.read(MAX_INPUT_BYTES + 1)
    if len(data) > MAX_INPUT_BYTES:
        raise ValueError("Build input is too large")
    return data.decode("utf-8-sig")


@contextmanager
def checkout_baseline(repo, ref, scratch):
    commit = subprocess.check_output(
        ["git", "rev-parse", "--verify", "--end-of-options", f"{ref}^{{commit}}"],
        cwd=repo, text=True,
    ).strip()
    checkout = scratch / "baseline"
    subprocess.run(
        ["git", "worktree", "add", "--quiet", "--detach", str(checkout), commit],
        cwd=repo, check=True,
    )
    try:
        yield checkout
    finally:
        subprocess.run(["git", "worktree", "remove", str(checkout)], cwd=repo, check=True)


def snapshot(repo, xml_path, settings):
    replay = lua_quote((TESTS / "replay_build.lua").as_posix())
    xml = lua_quote(xml_path.as_posix())
    request = lua_quote(json.dumps(settings, ensure_ascii=False, allow_nan=False))
    program = f"assert(loadfile({replay}))({xml}, {request})".encode("utf-8")
    environment = os.environ.copy()
    environment.pop("REGENERATE_MOD_CACHE", None)
    result = subprocess.run(
        [sys.executable, "-B", str(TESTS / "run_headless.py"), "--repo", str(repo), "-"],
        input=program, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=environment, timeout=120,
    )
    output = result.stdout.decode("utf-8", errors="replace")
    if result.returncode:
        raise RuntimeError(f"Replay failed in {repo}\n{output.rstrip()}")
    for line in reversed(output.splitlines()):
        if line.startswith(RESULT_PREFIX):
            return json.loads(line[len(RESULT_PREFIX):])
    raise RuntimeError(f"Replay produced no report in {repo}\n{output.rstrip()}")


def report_text(report, show_config):
    current, baseline = report["current"], report.get("baseline")
    print(f"Current  {current['skill']} ({current['configSet']})")
    if baseline:
        print(f"Baseline {baseline['skill']} ({baseline['configSet']})")
    print()
    print("Field\tBaseline\tCurrent\tChange" if baseline else "Field\tCurrent")
    for group in ("stats", "modifiers"):
        for name, value in current[group].items():
            if baseline:
                previous = baseline[group][name]
                delta = value - previous if type(value) in (int, float) and type(previous) in (int, float) else None
                change = f"{delta:+.6g}" if delta is not None else ""
                print(f"{name}\t{previous}\t{value}\t{change}")
            else:
                print(f"{name}\t{value}")
    if show_config:
        for label, values in report.items():
            config = {key: values[key] for key in ("input", "placeholder")}
            print(f"\n{label.capitalize()} Configuration")
            print(json.dumps(config, indent=2, sort_keys=True, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("input", nargs="?", help="build code, XML, or Markdown file, or - for stdin")
    source.add_argument("--code", help="a raw PoB build code")
    source.add_argument("--issue", type=int, help="read a public or accessible GitHub issue body with gh")
    parser.add_argument("--github-repo", default=UPSTREAM)
    parser.add_argument("--repo", type=Path, default=PROJECT, help="checkout to calculate")
    baseline = parser.add_mutually_exclusive_group()
    baseline.add_argument("--against", metavar="REF", help="compare with a git revision in a temporary worktree")
    baseline.add_argument("--baseline-dir", type=Path, help="compare with an existing checkout")
    parser.add_argument("--stat", action="append", help="output field, such as TotalEHP or Minion.Life")
    parser.add_argument("--probe", action="append", type=modifier_probe, default=[])
    parser.add_argument("--set", action="append", type=config_override, default=[], metavar="NAME=VALUE")
    parser.add_argument("--show-config", action="store_true")
    parser.add_argument("--json", action="store_true", help="include all observed inputs and placeholders")
    args = parser.parse_args()
    if args.issue is not None and args.issue < 1:
        parser.error("--issue must be a positive number")
    if args.stat and any(not re.fullmatch(r"\w+(?:\.\w+)*", name, re.ASCII) for name in args.stat):
        parser.error("--stat expects an output field such as TotalEHP or Minion.Life")

    try:
        xml = decode_build(read_input(args))
        repo = args.repo.resolve(strict=True)
        settings = {"stats": args.stat or DEFAULT_STATS, "probes": args.probe, "config": dict(args.set)}
        with TemporaryDirectory(prefix="pob-replay-") as directory:
            scratch = Path(directory).resolve()
            xml_path = scratch / "build.xml"
            xml_path.write_bytes(xml)
            report = {"current": snapshot(repo, xml_path, settings)}
            if args.against:
                with checkout_baseline(repo, args.against, scratch) as checkout:
                    report["baseline"] = snapshot(checkout, xml_path, settings)
            elif args.baseline_dir:
                report["baseline"] = snapshot(args.baseline_dir.resolve(strict=True), xml_path, settings)
        if args.json:
            print(json.dumps(report, indent=2, ensure_ascii=False))
        else:
            report_text(report, args.show_config)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as failure:
        print(failure, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
