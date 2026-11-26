"""Regression tests for build intake, the toolchain marker, and CI reporting."""

import argparse
import base64
import gzip
import json
from pathlib import Path
from subprocess import CompletedProcess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import zlib

from check_headless import choose_linux_backend, ci_check, installed_wsl_distros, run_wsl, workflow_jobs
from replay_build import config_override, decode_build
from run_headless import tool_tree


def code_for(xml, compress=zlib.compress):
    return base64.urlsafe_b64encode(compress(xml)).decode("ascii").rstrip("=")


XML = b'<PathOfBuilding><Build targetVersion="3_0" level="90"/></PathOfBuilding>'
ALTERNATE = XML.replace(b'level="90"', b'level="91"')


class BuildIntakeTests(unittest.TestCase):
    def test_reads_exported_xml_and_unpadded_codes(self):
        self.assertEqual(decode_build(XML.decode()), XML)
        self.assertEqual(decode_build(code_for(XML)), XML)
        self.assertEqual(decode_build(code_for(XML, gzip.compress)), XML)

    def test_reads_a_wrapped_code_from_markdown(self):
        code = code_for(XML)
        wrapped = f"{code[:50]}\r\n{code[50:]}"
        body = "A Discord message\r\n\x60\x60\x60shell\r\n" + wrapped + "\r\n\x60\x60\x60\r\n"
        self.assertEqual(decode_build(body), XML)

    def test_rejects_multiple_builds(self):
        with self.assertRaisesRegex(ValueError, "multiple different PoB builds"):
            decode_build(f"{code_for(XML)}\n\n{code_for(ALTERNATE)}")

    def test_rejects_invalid_or_oversized_payloads(self):
        for text in (
            "<PathOfBuilding2/>",
            '<!DOCTYPE PathOfBuilding SYSTEM "file:///test"><PathOfBuilding/>',
            code_for(XML)[:-5],
        ):
            with self.subTest(text=text), self.assertRaises(ValueError):
                decode_build(text)
        with patch("replay_build.MAX_XML_BYTES", len(XML) - 1), self.assertRaises(ValueError):
            decode_build(code_for(XML))

    def test_config_overrides_keep_zero_false_and_clear_distinct(self):
        self.assertEqual(config_override("overrideCruelty=0"), ("overrideCruelty", 0))
        self.assertEqual(config_override("buffOnslaught=false"), ("buffOnslaught", False))
        self.assertEqual(config_override("overrideCruelty=null"), ("overrideCruelty", None))
        self.assertEqual(config_override("enemyIsBoss=Pinnacle"), ("enemyIsBoss", "Pinnacle"))
        with self.assertRaises(argparse.ArgumentTypeError):
            config_override("overrideCruelty=Infinity")


class TestStatus(unittest.TestCase):
    def test_ignores_other_workflows_and_uses_latest_retry(self):
        older = self.check("run_tests", "FAILURE", "2026-11-25")
        latest = self.check("Run Tests / run_tests (pull_request)", "SUCCESS", "2026-11-26")
        unrelated = self.check("run_tests", "FAILURE", "2026-11-27", "Other Workflow")
        self.assertEqual(workflow_jobs([older, latest, unrelated]), {"run_tests": latest})

    def test_ci_requires_both_jobs_to_pass(self):
        run = self.check("run_tests", "SUCCESS")
        cache = self.check("check_modcache", "SUCCESS")
        for rows, expected in (
            ([], 8),
            ([run], 8),
            ([run, {**cache, "status": "IN_PROGRESS", "conclusion": ""}], 8),
            ([run, {**cache, "conclusion": "FAILURE"}], 1),
            ([run, cache], 0),
        ):
            result = CompletedProcess([], 0, stdout=json.dumps({"statusCheckRollup": rows}), stderr="")
            with self.subTest(rows=rows), patch("check_headless.subprocess.run", return_value=result):
                with patch("builtins.print"):
                    self.assertEqual(ci_check(123, "owner/project"), expected)

    @staticmethod
    def check(name, conclusion, started="2026-11-26", workflow="Run Tests"):
        return {"name": name, "status": "COMPLETED", "conclusion": conclusion, "startedAt": started,
                "workflowName": workflow, "detailsUrl": "https://example.test/check"}


class ToolchainTests(unittest.TestCase):
    def test_toolchain_marker_and_existing_luarocks_tree(self):
        with TemporaryDirectory() as directory:
            path = Path(directory)
            self.assertEqual(tool_tree(path), path)
            marker = path / "active-tree.txt"
            marker.write_text("busted-test\n", encoding="ascii")
            self.assertEqual(tool_tree(path), path / "busted-test")
            marker.write_text("busted-test/../../external\n", encoding="ascii")
            with self.assertRaisesRegex(RuntimeError, "Invalid Busted toolchain marker"):
                tool_tree(path)


class LinuxBackendTests(unittest.TestCase):
    def test_reads_wsl_list_and_skips_docker_distributions(self):
        output = "docker-desktop\r\nUbuntu\r\nDebian\r\n".encode("utf-16-le")
        result = CompletedProcess([], 0, stdout=output, stderr=b"")
        with patch("check_headless.shutil.which", return_value="wsl.exe"):
            with patch("check_headless.subprocess.run", return_value=result):
                self.assertEqual(installed_wsl_distros(), ["Ubuntu", "Debian"])

    def test_auto_prefers_wsl_and_can_select_a_distribution(self):
        with patch("check_headless.installed_wsl_distros", return_value=["Ubuntu", "Debian"]):
            self.assertEqual(choose_linux_backend("auto", None), ("wsl", "Ubuntu"))
            self.assertEqual(choose_linux_backend("wsl", "debian"), ("wsl", "Debian"))
            with self.assertRaisesRegex(RuntimeError, "WSL distribution.*unavailable"):
                choose_linux_backend("wsl", "missing")

    def test_auto_falls_back_to_docker_and_explicit_wsl_reports_missing(self):
        with patch("check_headless.installed_wsl_distros", return_value=[]):
            with patch("check_headless.shutil.which", return_value="docker"):
                self.assertEqual(choose_linux_backend("auto", None), ("docker", None))
                with self.assertRaisesRegex(RuntimeError, "No WSL Linux distribution"):
                    choose_linux_backend("wsl", None)

    def test_sends_shared_script_to_wsl_in_the_selected_checkout(self):
        repo = Path("another checkout")
        with patch("check_headless.subprocess.run", return_value=CompletedProcess([], 0)) as run:
            self.assertEqual(run_wsl(repo, "Ubuntu", "wsl"), 0)
        args, kwargs = run.call_args
        self.assertEqual(args[0], ["wsl.exe", "--distribution", "Ubuntu", "--exec", "sh", "-s", "--", "wsl"])
        self.assertEqual(kwargs["cwd"], repo)
        self.assertTrue(kwargs["input"].startswith(b"#!/bin/sh\n"))
