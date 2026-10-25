import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from shebang_sentry.sources import Index, worktree


class TempFixture:
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, "-m", "shebang_sentry", *map(str, args)],
            capture_output=True,
            timeout=20,
        )


class SourceTests(TempFixture, unittest.TestCase):
    def test_worktree_cli_json_and_immutability(self):
        path = self.root / "script.sh"
        original = b"#!/bin/sh\r\necho hi\r\n"
        path.write_bytes(original)
        result = self.run_cli(path, "--skip-mode", "--format", "json")
        self.assertEqual(result.returncode, 1)
        report = json.loads(result.stdout)["files"][0]
        self.assertEqual(report["content_source"], "worktree")
        self.assertEqual(report["findings"][0]["code"], "SB004")
        self.assertEqual(path.read_bytes(), original)

    def test_clean_example_and_failure_policies(self):
        path = self.root / "script.sh"
        path.write_bytes(b"#!/bin/sh\necho hi\n")
        self.assertEqual(self.run_cli(path, "--skip-mode").returncode, 0)
        path.write_bytes(b"#!/bin/sh -e -u\n")
        self.assertEqual(self.run_cli(path, "--skip-mode", "--fail-on", "error").returncode, 0)
        path.write_bytes(b"bad\n")
        self.assertEqual(self.run_cli(path, "--skip-mode", "--fail-on", "none").returncode, 0)

    def test_missing_and_directory_are_input_errors(self):
        self.assertEqual(self.run_cli(self.root / "missing").returncode, 2)
        self.assertEqual(self.run_cli(self.root).returncode, 2)

    def test_special_symlink_refused(self):
        path = self.root / "script.sh"
        path.write_bytes(b"#!/bin/sh\n")
        link = self.root / "link.sh"
        try:
            link.symlink_to(path)
        except OSError:
            self.skipTest("Symlink creation unavailable")
        with self.assertRaisesRegex(ValueError, "symlink"):
            worktree(link)

    def test_worktree_read_is_bounded(self):
        path = self.root / "large.sh"
        path.write_bytes(b"#!/bin/sh\n" + b"x" * 10000)
        self.assertEqual(len(worktree(path)[0]), 4097)


@unittest.skipUnless(shutil.which("git"), "Git required")
class IndexTests(TempFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.git("init", "-q")
        self.git("config", "core.autocrlf", "false")

    def git(self, *args):
        return subprocess.check_output(
            ["git", "-C", str(self.root), *args], stderr=subprocess.STDOUT
        )

    def stage(self, name="script.sh", data=b"#!/bin/sh\necho hi\n", executable=True):
        path = self.root / name
        path.write_bytes(data)
        self.git("add", "--", name)
        self.git("update-index", "--chmod=" + ("+x" if executable else "-x"), "--", name)
        return path

    def test_staged_bytes_and_mode_not_worktree(self):
        path = self.stage()
        path.write_bytes(b"bad worktree\n")
        result = self.run_cli(
            "script.sh", "--repo", self.root, "--source", "index", "--format", "json"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)["files"][0]
        self.assertTrue(report["executable"])
        self.assertEqual(report["mode_source"], "git-index")
        self.assertEqual(report["kernel_argv"], ["/bin/sh", "<script>"])
        self.assertEqual(path.read_bytes(), b"bad worktree\n")

    def test_nonexecutable_index(self):
        self.stage(executable=False)
        result = self.run_cli("script.sh", "--repo", self.root, "--source", "index")
        self.assertEqual(result.returncode, 1)
        self.assertIn(b"SB008", result.stdout)

    def test_outside_and_untracked_refused(self):
        with self.assertRaisesRegex(ValueError, "outside"):
            Index(self.root).read("../outside.sh")
        self.assertEqual(
            self.run_cli("missing.sh", "--repo", self.root, "--source", "index").returncode, 2
        )

    def test_literal_pathspec_characters(self):
        self.stage("script[1].sh")
        result = Index(self.root).read("script[1].sh")
        self.assertTrue(result[1])

    def test_index_symlink_refused_without_resolving_target(self):
        self.stage()
        blob = self.git("hash-object", "-w", "script.sh").decode().strip()
        self.git("update-index", "--add", "--cacheinfo", f"120000,{blob},link.sh")
        with self.assertRaisesRegex(ValueError, "symlink"):
            Index(self.root).read("link.sh")

    def test_oversized_index_blob_refused(self):
        self.stage(data=b"x" * (16 * 1024 * 1024 + 1))
        with self.assertRaisesRegex(ValueError, "exceeds"):
            Index(self.root).read("script.sh")

    def test_staged_file_can_be_absent_from_worktree(self):
        path = self.stage()
        path.unlink()
        self.assertTrue(Index(self.root).read("script.sh")[1])

    def test_unmerged_index_is_not_silently_selected(self):
        self.stage()
        blob = self.git("hash-object", "-w", "script.sh").decode().strip()
        self.git("update-index", "--force-remove", "script.sh")
        records = f"100644 {blob} 1\tscript.sh\n100755 {blob} 2\tscript.sh\n"
        subprocess.run(
            ["git", "-C", str(self.root), "update-index", "--index-info"],
            input=records.encode(),
            check=True,
            capture_output=True,
        )
        with self.assertRaisesRegex(ValueError, "Unmerged"):
            Index(self.root).read("script.sh")


@unittest.skipUnless(sys.platform.startswith("linux"), "Actual Linux exec semantics")
class LinuxExecTests(unittest.TestCase):
    def test_predictions_against_direct_exec(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "run.sh"
            path.write_bytes(b"#!/bin/sh\nprintf 'ok'\n")
            path.chmod(0o755)
            self.assertEqual(subprocess.check_output([str(path)]), b"ok")
            path.write_bytes(b"#!/bin/sh\r\nprintf 'ok'\n")
            with self.assertRaises(FileNotFoundError):
                subprocess.run([str(path)], check=True, capture_output=True)
            path.write_bytes(b"\xef\xbb\xbf#!/bin/sh\nprintf 'ok'\n")
            with self.assertRaises(OSError):
                subprocess.run([str(path)], check=True, capture_output=True)

    def test_env_split_and_unsplit(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "run.sh"
            path.write_bytes(b"#!/usr/bin/env -S sh -eu\nprintf 'split-ok'\n")
            path.chmod(0o755)
            self.assertEqual(subprocess.check_output([str(path)]), b"split-ok")
            path.write_bytes(b"#!/usr/bin/env sh -eu\nprintf 'bad'\n")
            result = subprocess.run([str(path)], capture_output=True)
            self.assertNotEqual(result.returncode, 0)
