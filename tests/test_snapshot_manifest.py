import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from assetledger.manifest import (
    ManifestError,
    load_manifest,
    manifest_from_data,
    save_manifest,
    serialize_manifest,
)
from assetledger.models import FileEntry, Manifest
from assetledger.snapshot import SnapshotError, create_snapshot, hash_file, snapshot_to_file


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.assets = self.base / "assets"
        self.assets.mkdir()

    def tearDown(self):
        self.temporary.cleanup()

    def test_hash_and_byte_size(self):
        path = self.assets / "sample.bin"
        path.write_bytes(b"abc")
        size, digest = hash_file(path)
        self.assertEqual(size, 3)
        self.assertEqual(digest, "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")

    def test_hashing_reads_in_chunks(self):
        path = self.assets / "chunks.bin"
        path.write_bytes(b"0123456789")
        original_open = Path.open
        read_sizes = []

        class RecordingReader:
            def __init__(self, wrapped):
                self.wrapped = wrapped

            def __enter__(self):
                self.wrapped.__enter__()
                return self

            def __exit__(self, *args):
                return self.wrapped.__exit__(*args)

            def read(self, size=-1):
                read_sizes.append(size)
                return self.wrapped.read(size)

            def fileno(self):
                return self.wrapped.fileno()

        def recording_open(path_object, *args, **kwargs):
            return RecordingReader(original_open(path_object, *args, **kwargs))

        with mock.patch.object(Path, "open", recording_open):
            size, _ = hash_file(path, chunk_size=3)
        self.assertEqual(size, 10)
        self.assertGreater(len(read_sizes), 2)
        self.assertTrue(all(size == 3 for size in read_sizes))

    def test_empty_and_nested_directories(self):
        (self.assets / "empty-dir").mkdir()
        (self.assets / "nested" / "deeper").mkdir(parents=True)
        (self.assets / "nested" / "deeper" / "file.txt").write_text("x", encoding="utf-8")
        manifest = create_snapshot(self.assets)
        self.assertEqual([entry.path for entry in manifest.files], ["nested/deeper/file.txt"])

    def test_unicode_and_space_filenames(self):
        unicode_name = "snow-" + chr(0x96EA) + " file.txt"
        (self.assets / unicode_name).write_text("snow", encoding="utf-8")
        manifest = create_snapshot(self.assets)
        self.assertEqual(manifest.files[0].path, unicode_name)
        payload = serialize_manifest(manifest).decode("utf-8")
        self.assertIn(unicode_name, payload)

    def test_default_exclusions_are_recorded(self):
        for name in (".git", ".venv", "venv", "node_modules", "__pycache__", "build", "dist"):
            directory = self.assets / name
            directory.mkdir()
            (directory / "ignored.txt").write_text("ignore", encoding="utf-8")
        manifest = create_snapshot(self.assets)
        self.assertEqual(manifest.files, ())
        self.assertEqual({item.path for item in manifest.skipped}, {".git", ".venv", "venv", "node_modules", "__pycache__", "build", "dist"})
        self.assertTrue(all(item.reason == "excluded directory" for item in manifest.skipped))

    def test_symbolic_link_is_skipped_when_supported(self):
        target = self.assets / "target.txt"
        target.write_text("target", encoding="utf-8")
        link = self.assets / "link.txt"
        try:
            link.symlink_to(target)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"symbolic links unavailable: {exc}")
        manifest = create_snapshot(self.assets)
        self.assertEqual([item.path for item in manifest.files], ["target.txt"])
        self.assertEqual(manifest.skipped[0].path, "link.txt")
        self.assertEqual(manifest.skipped[0].reason, "symbolic link")

    @unittest.skipUnless(hasattr(os, "mkfifo") and os.name != "nt", "FIFO creation is POSIX-specific")
    def test_special_file_is_skipped(self):
        fifo = self.assets / "events.pipe"
        os.mkfifo(fifo)
        manifest = create_snapshot(self.assets)
        self.assertEqual(manifest.skipped[0].reason, "special file")

    def test_unreadable_directory_is_an_error(self):
        with mock.patch("assetledger.snapshot.os.scandir", side_effect=PermissionError("denied")):
            with self.assertRaisesRegex(SnapshotError, "cannot read directory"):
                create_snapshot(self.assets)

    def test_changed_file_is_detected(self):
        path = self.assets / "changing.bin"
        path.write_bytes(b"stable bytes")
        stable = (12, 100, 1, 1)
        changed = (12, 101, 1, 1)
        with mock.patch("assetledger.snapshot._signature", side_effect=[stable, changed, changed]):
            with self.assertRaisesRegex(SnapshotError, "changed while hashing"):
                hash_file(path)

    def test_output_inside_scanned_root_is_rejected(self):
        (self.assets / "one.txt").write_text("one", encoding="utf-8")
        with self.assertRaisesRegex(SnapshotError, "outside"):
            snapshot_to_file(self.assets, self.assets / "inventory.json")
        self.assertFalse((self.assets / "inventory.json").exists())

    def test_existing_output_is_preserved(self):
        output = self.base / "manifest.json"
        output.write_text("sentinel", encoding="utf-8")
        with self.assertRaisesRegex(SnapshotError, "already exists"):
            snapshot_to_file(self.assets, output)
        self.assertEqual(output.read_text(encoding="utf-8"), "sentinel")

    def test_snapshot_does_not_change_source_contents(self):
        path = self.assets / "source.bin"
        original = bytes(range(256))
        path.write_bytes(original)
        snapshot_to_file(self.assets, self.base / "manifest.json")
        self.assertEqual(path.read_bytes(), original)


class ManifestTests(unittest.TestCase):
    def valid_data(self):
        return {
            "schema_version": 1,
            "hash_algorithm": "sha256",
            "files": [
                {"path": "a/file.txt", "size_bytes": 1, "sha256": "a" * 64},
            ],
            "skipped": [],
        }

    def test_deterministic_serialization_sorts_entries(self):
        manifest = Manifest(
            files=(
                FileEntry("z.txt", 1, "b" * 64),
                FileEntry("a.txt", 1, "a" * 64),
            )
        )
        first = serialize_manifest(manifest)
        second = serialize_manifest(manifest)
        self.assertEqual(first, second)
        self.assertLess(first.index(b'a.txt'), first.index(b'z.txt'))
        self.assertTrue(first.endswith(b"\n"))

    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "manifest.json"
            expected = manifest_from_data(self.valid_data())
            save_manifest(path, expected)
            self.assertEqual(load_manifest(path), expected)

    def test_duplicate_json_keys(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "manifest.json"
            path.write_text('{"schema_version":1,"schema_version":1}', encoding="utf-8")
            with self.assertRaisesRegex(ManifestError, "duplicate JSON key"):
                load_manifest(path)

    def test_validation_failures(self):
        cases = {}
        data = self.valid_data(); data["schema_version"] = 2; cases["schema"] = data
        data = self.valid_data(); data["hash_algorithm"] = "md5"; cases["algorithm"] = data
        data = self.valid_data(); data["files"][0]["sha256"] = "not-a-digest"; cases["digest"] = data
        data = self.valid_data(); data["files"][0]["size_bytes"] = -1; cases["negative"] = data
        data = self.valid_data(); data["files"][0]["size_bytes"] = True; cases["boolean-size"] = data
        data = self.valid_data(); data["files"][0]["path"] = "../escape"; cases["parent"] = data
        data = self.valid_data(); data["files"][0]["path"] = "/absolute"; cases["absolute"] = data
        data = self.valid_data(); data["files"][0]["path"] = "a\\file.txt"; cases["backslash"] = data
        data = self.valid_data(); data["extra"] = 1; cases["unknown"] = data
        for name, invalid in cases.items():
            with self.subTest(name=name):
                with self.assertRaises(ManifestError):
                    manifest_from_data(invalid)

    def test_duplicate_file_paths(self):
        data = self.valid_data()
        data["files"].append(dict(data["files"][0]))
        with self.assertRaisesRegex(ManifestError, "duplicate file path"):
            manifest_from_data(data)

    def test_existing_manifest_is_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "manifest.json"
            path.write_text("sentinel", encoding="utf-8")
            with self.assertRaisesRegex(ManifestError, "already exists"):
                save_manifest(path, Manifest())
            self.assertEqual(path.read_text(encoding="utf-8"), "sentinel")


if __name__ == "__main__":
    unittest.main()
