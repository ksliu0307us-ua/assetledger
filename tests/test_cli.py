import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class CliTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.assets = self.base / "assets"
        self.snapshots = self.base / "snapshots"
        self.assets.mkdir()
        source = Path(__file__).resolve().parents[1]
        self.environment = os.environ.copy()
        old = self.environment.get("PYTHONPATH")
        self.environment["PYTHONPATH"] = str(source) + (os.pathsep + old if old else "")

    def tearDown(self):
        self.temporary.cleanup()

    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, "-m", "assetledger", *map(str, args)],
            cwd=self.base,
            env=self.environment,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )

    def snapshot(self, name):
        output = self.snapshots / name
        result = self.run_cli("snapshot", self.assets, "--output", output)
        self.assertEqual(result.returncode, 0, result.stderr)
        return output

    def test_version_and_help(self):
        version = self.run_cli("--version")
        help_result = self.run_cli("--help")
        self.assertEqual(version.returncode, 0)
        self.assertEqual(version.stdout.strip(), "assetledger 0.1.0")
        self.assertEqual(help_result.returncode, 0)
        self.assertIn("snapshot", help_result.stdout)

    def test_cli_text_json_and_exit_codes(self):
        (self.assets / "same-a.txt").write_text("same", encoding="utf-8")
        (self.assets / "same-b.txt").write_text("same", encoding="utf-8")
        (self.assets / "modify.txt").write_text("before", encoding="utf-8")
        original = {path.name: path.read_bytes() for path in self.assets.iterdir()}
        before = self.snapshot("before.json")

        no_changes = self.run_cli("compare", before, before)
        self.assertEqual(no_changes.returncode, 0)
        self.assertIn("No differences", no_changes.stdout)

        (self.assets / "modify.txt").write_text("after", encoding="utf-8")
        (self.assets / "added.txt").write_text("added", encoding="utf-8")
        after = self.snapshot("after.json")
        changed = self.run_cli("compare", before, after, "--format", "json")
        self.assertEqual(changed.returncode, 1)
        self.assertEqual(json.loads(changed.stdout)["summary"]["modified"], 1)

        duplicates = self.run_cli("duplicates", before, "--format", "json")
        self.assertEqual(duplicates.returncode, 0)
        self.assertEqual(json.loads(duplicates.stdout)["duplicate_group_count"], 1)

        inspected = self.run_cli("inspect", before, "--format", "json")
        self.assertEqual(inspected.returncode, 0)
        self.assertEqual(json.loads(inspected.stdout)["file_count"], 3)
        self.assertFalse(json.loads(inspected.stdout)["filesystem_verified"])

        self.assertEqual((self.assets / "same-a.txt").read_bytes(), original["same-a.txt"])
        self.assertEqual((self.assets / "same-b.txt").read_bytes(), original["same-b.txt"])

    def test_invalid_manifest_returns_two_without_traceback(self):
        invalid = self.base / "invalid.json"
        invalid.write_text("not json", encoding="utf-8")
        result = self.run_cli("inspect", invalid)
        self.assertEqual(result.returncode, 2)
        self.assertIn("malformed JSON", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_inside_output_and_existing_output_return_two(self):
        inside = self.assets / "manifest.json"
        inside_result = self.run_cli("snapshot", self.assets, "--output", inside)
        self.assertEqual(inside_result.returncode, 2)
        self.assertFalse(inside.exists())

        existing = self.base / "existing.json"
        existing.write_text("sentinel", encoding="utf-8")
        existing_result = self.run_cli("snapshot", self.assets, "--output", existing)
        self.assertEqual(existing_result.returncode, 2)
        self.assertEqual(existing.read_text(encoding="utf-8"), "sentinel")


if __name__ == "__main__":
    unittest.main()
