#!/usr/bin/env python3
"""
Schema validation tests for dhg-hw-spec-collector.
Runs the Linux collector and validates CSV output structure.
"""

import csv
import os
import platform
import subprocess
import sys
import tempfile
import unittest


REQUIRED_COLUMNS = {'category', 'key', 'value', 'unit', 'source'}
REQUIRED_CATEGORIES = {'OS', 'CPU', 'RAM', 'Storage', 'Network'}


class TestCollectorOutput(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """Run the appropriate collector and capture the output CSV."""
        script_dir = os.path.join(os.path.dirname(__file__), '..', 'scripts')
        os_type = platform.system()
        script_map = {
            'Linux':   'collect_linux.py',
            'Windows': 'collect_windows.py',
            'Darwin':  'collect_macos.py',
        }
        script = script_map.get(os_type, 'collect_linux.py')
        script_path = os.path.join(script_dir, script)

        with tempfile.TemporaryDirectory() as tmpdir:
            result = subprocess.run(
                [sys.executable, script_path],
                capture_output=True, text=True, cwd=tmpdir
            )
            # Find the CSV
            csvs = [f for f in os.listdir(tmpdir) if f.endswith('.csv')]
            if not csvs:
                cls.rows = []
                cls.run_failed = True
                return

            cls.run_failed = False
            csv_path = os.path.join(tmpdir, csvs[0])
            with open(csv_path, newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                cls.rows = list(reader)

    def test_collector_ran(self):
        self.assertFalse(self.run_failed, "Collector script failed to produce a CSV")

    def test_output_not_empty(self):
        self.assertGreater(len(self.rows), 0, "CSV has no data rows")

    def test_required_columns_present(self):
        if not self.rows:
            self.skipTest("No rows to validate")
        actual = set(self.rows[0].keys())
        self.assertTrue(
            REQUIRED_COLUMNS.issubset(actual),
            f"Missing columns: {REQUIRED_COLUMNS - actual}"
        )

    def test_no_empty_category(self):
        for row in self.rows:
            self.assertNotEqual(row.get('category', '').strip(), '',
                                f"Empty category in row: {row}")

    def test_no_empty_key(self):
        for row in self.rows:
            self.assertNotEqual(row.get('key', '').strip(), '',
                                f"Empty key in row: {row}")

    def test_required_categories_present(self):
        if not self.rows:
            self.skipTest("No rows to validate")
        found = {row['category'] for row in self.rows}
        for cat in REQUIRED_CATEGORIES:
            self.assertIn(cat, found, f"Required category '{cat}' not found in output")

    def test_os_hostname_present(self):
        os_rows = {row['key']: row['value'] for row in self.rows
                   if row['category'] == 'OS'}
        self.assertIn('hostname', os_rows, "OS.hostname not collected")
        self.assertNotEqual(os_rows['hostname'], '', "OS.hostname is empty")

    def test_cpu_cores_present(self):
        cpu_rows = {row['key']: row['value'] for row in self.rows
                    if row['category'] == 'CPU'}
        self.assertIn('logical_cores', cpu_rows, "CPU.logical_cores not collected")

    def test_ram_total_present(self):
        ram_rows = {row['key']: row['value'] for row in self.rows
                    if row['category'] == 'RAM'}
        self.assertIn('total', ram_rows, "RAM.total not collected")
        total = float(ram_rows['total'])
        self.assertGreater(total, 0, "RAM total should be > 0")

    def test_source_never_empty(self):
        for row in self.rows:
            self.assertNotEqual(row.get('source', '').strip(), '',
                                f"Empty source in row: {row}")


if __name__ == '__main__':
    unittest.main()
