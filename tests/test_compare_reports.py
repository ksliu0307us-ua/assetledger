import unittest

from assetledger.compare import compare_manifests
from assetledger.models import FileEntry, Manifest, SkippedEntry
from assetledger.reports import (
    comparison_text,
    duplicate_groups,
    inventory_summary,
)


def entry(path, size, marker):
    return FileEntry(path, size, marker * 64)


class ComparisonTests(unittest.TestCase):
    def test_all_classifications_and_stable_order(self):
        before = Manifest(
            files=(
                entry("removed.txt", 1, "a"),
                entry("modified-size.txt", 1, "b"),
                entry("modified-hash.txt", 2, "c"),
                entry("unchanged.txt", 3, "d"),
            )
        )
        after = Manifest(
            files=(
                entry("unchanged.txt", 3, "d"),
                entry("modified-hash.txt", 2, "e"),
                entry("modified-size.txt", 9, "b"),
                entry("added.txt", 4, "f"),
            )
        )
        result = compare_manifests(before, after)
        self.assertEqual([item.path for item in result.added], ["added.txt"])
        self.assertEqual([item.path for item in result.removed], ["removed.txt"])
        self.assertEqual([item.path for item in result.modified], ["modified-hash.txt", "modified-size.txt"])
        self.assertEqual([item.path for item in result.unchanged], ["unchanged.txt"])
        self.assertTrue(result.has_differences)

    def test_moved_file_is_removal_and_addition(self):
        before = Manifest(files=(entry("old.txt", 4, "a"),))
        after = Manifest(files=(entry("new.txt", 4, "a"),))
        result = compare_manifests(before, after)
        self.assertEqual(len(result.added), 1)
        self.assertEqual(len(result.removed), 1)
        self.assertEqual(len(result.modified), 0)

    def test_identical_manifests_have_no_differences(self):
        manifest = Manifest(files=(entry("same.txt", 4, "a"),))
        result = compare_manifests(manifest, manifest)
        self.assertFalse(result.has_differences)
        self.assertIn("No differences", comparison_text(result))

    def test_control_characters_are_escaped_in_text(self):
        result = compare_manifests(Manifest(), Manifest(files=(entry("line\nbreak.txt", 1, "a"),)))
        report = comparison_text(result)
        self.assertIn(r"line\nbreak.txt", report)
        self.assertNotIn("line\nbreak.txt", report)


class ReportTests(unittest.TestCase):
    def test_duplicate_groups_and_redundant_bytes(self):
        manifest = Manifest(
            files=(
                entry("a.bin", 10, "a"),
                entry("b.bin", 10, "a"),
                entry("c.bin", 10, "a"),
                entry("unique.bin", 10, "b"),
            )
        )
        groups = duplicate_groups(manifest)
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0].copies, 3)
        self.assertEqual(groups[0].redundant_bytes, 20)
        self.assertEqual(groups[0].paths, ("a.bin", "b.bin", "c.bin"))

    def test_duplicate_empty_files_are_included(self):
        groups = duplicate_groups(
            Manifest(files=(entry("empty-a", 0, "e"), entry("empty-b", 0, "e")))
        )
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0].redundant_bytes, 0)

    def test_inventory_summary(self):
        manifest = Manifest(
            files=(
                entry("a.TXT", 3, "a"),
                entry("nested/b.txt", 5, "b"),
                entry("no-extension", 7, "c"),
                entry("copy", 7, "c"),
            ),
            skipped=(SkippedEntry("node_modules", "excluded directory"),),
        )
        summary = inventory_summary(manifest)
        self.assertEqual(summary.file_count, 4)
        self.assertEqual(summary.total_bytes, 22)
        self.assertEqual(dict(summary.extension_counts), {".txt": 2, "[no extension]": 2})
        self.assertEqual(summary.duplicate_group_count, 1)
        self.assertEqual(summary.skipped_count, 1)


if __name__ == "__main__":
    unittest.main()
