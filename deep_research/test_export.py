"""Tests for one-click report export (ux-05): export.export_report_file."""
import os
import tempfile
import time
import unittest

import export
from export import export_report_file


class ExportReportFileTest(unittest.TestCase):
    def tearDown(self):
        # Remove any export files created by the test; keep the suite hermetic.
        export_dir = os.path.join(
            tempfile.gettempdir(), export.EXPORT_DIR_NAME
        )
        if os.path.isdir(export_dir):
            for entry in os.listdir(export_dir):
                if entry.startswith(export.EXPORT_FILENAME_PREFIX):
                    try:
                        os.remove(os.path.join(export_dir, entry))
                    except OSError:
                        pass

    def test_round_trips_report_content(self):
        report = "# Findings\n\nSome **results** with a [source](https://example.com)."
        path = export_report_file(report)
        self.assertTrue(os.path.isfile(path))
        self.assertTrue(path.endswith(".md"))
        with open(path, encoding="utf-8") as handle:
            self.assertEqual(handle.read(), report + "\n")

    def test_none_report_yields_placeholder_markdown(self):
        path = export_report_file(None)
        with open(path, encoding="utf-8") as handle:
            content = handle.read()
        self.assertTrue(content.startswith("#"))
        self.assertIn("No report content", content)

    def test_empty_report_yields_placeholder_markdown(self):
        path = export_report_file("   \n  ")
        with open(path, encoding="utf-8") as handle:
            content = handle.read()
        self.assertIn("No report content", content)

    def test_filename_is_fixed_and_user_input_free(self):
        path = export_report_file("# hi")
        dirname, basename = os.path.split(path)
        self.assertTrue(basename.startswith(export.EXPORT_FILENAME_PREFIX + "-"))
        self.assertTrue(basename.endswith(".md"))
        self.assertEqual(
            os.path.basename(dirname).rstrip(os.sep), export.EXPORT_DIR_NAME
        )

    def test_repeated_exports_get_unique_paths(self):
        first = export_report_file("# one")
        second = export_report_file("# two")
        self.assertNotEqual(first, second)
        self.assertTrue(os.path.isfile(first))
        self.assertTrue(os.path.isfile(second))

    def test_stale_exports_are_pruned(self):
        stale = os.path.join(
            tempfile.gettempdir(),
            export.EXPORT_DIR_NAME,
            export.EXPORT_FILENAME_PREFIX + "-20000101-000000.md",
        )
        os.makedirs(os.path.dirname(stale), exist_ok=True)
        with open(stale, "w", encoding="utf-8") as handle:
            handle.write("# stale\n")
        old_mtime = time.time() - (export.EXPORT_MAX_AGE_SECONDS + 60)
        os.utime(stale, (old_mtime, old_mtime))
        export_report_file("# fresh")
        self.assertFalse(os.path.exists(stale))

    def test_unrelated_files_are_not_pruned(self):
        other = os.path.join(
            tempfile.gettempdir(),
            export.EXPORT_DIR_NAME,
            "notes.txt",
        )
        os.makedirs(os.path.dirname(other), exist_ok=True)
        with open(other, "w", encoding="utf-8") as handle:
            handle.write("keep me\n")
        old_mtime = time.time() - (export.EXPORT_MAX_AGE_SECONDS + 60)
        os.utime(other, (old_mtime, old_mtime))
        try:
            export_report_file("# fresh")
            self.assertTrue(os.path.exists(other))
        finally:
            os.remove(other)


if __name__ == "__main__":
    unittest.main()
