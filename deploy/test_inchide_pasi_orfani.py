"""Synthetic SQLite fixtures, never a live journal or real process probe."""
import concurrent.futures
import importlib.util
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

SCRIPT = Path(__file__).with_name('inchide_pasi_orfani.py')
spec = importlib.util.spec_from_file_location('orphan_repair', SCRIPT)
o = importlib.util.module_from_spec(spec)
spec.loader.exec_module(o)


class Teste(unittest.TestCase):
    def fixture(self, path):
        with sqlite3.connect(path) as db:
            db.execute('CREATE TABLE pasi(id INTEGER PRIMARY KEY, cerere TEXT, stare TEXT, '
                       't_sfarsit REAL, dovada TEXT, pid INTEGER, amprenta TEXT, t_start REAL)')
            db.executemany('INSERT INTO pasi VALUES(?,?,?,?,?,?,?,?)', [
                (1, 'missing-pid', 'in executie', None, 'original evidence 1', None, None, 1),
                (2, 'absent-process', 'in executie', None, 'original evidence 2', 99999999, '99999999:unverified', 1),
                (3, 'reused-pid', 'in executie', None, 'original evidence 3', 123, '123:unverified', 1),
                (4, 'completed', 'gata', 10, 'original evidence 4', 99999999, '99999999:unverified', 1)])

    def test_rejects_unknown_process_identity_preserving_all_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'journal.sqlite3'
            self.fixture(path)
            before = path.read_bytes()
            # Simulated absence is insufficient evidence of ownership or an orphan.
            with mock.patch('os.path.exists', return_value=False):
                with self.assertRaisesRegex(RuntimeError, 'OPRIT'):
                    o.inchide(str(path), acum=0)
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(sorted(p.name for p in Path(tmp).iterdir()), ['journal.sqlite3'])

    def test_existing_pid_is_not_accepted_as_process_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'journal.sqlite3'
            self.fixture(path)
            before = path.read_bytes()
            with mock.patch('os.path.exists', return_value=True):
                with self.assertRaisesRegex(RuntimeError, 'OPRIT'):
                    o.inchide(str(path))
            self.assertEqual(path.read_bytes(), before)

    def test_does_not_open_or_create_database(self):
        with mock.patch('sqlite3.connect', side_effect=AssertionError('must not open')) as connect:
            with self.assertRaisesRegex(RuntimeError, 'OPRIT'):
                o.inchide('/not-an-authorized-journal')
            connect.assert_not_called()

    def test_cli_unknown_schema_or_missing_database_has_no_side_effects(self):
        for content in (None, b'', b'not sqlite'):
            with self.subTest(content=content), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / 'journal.sqlite3'
                if content is not None:
                    path.write_bytes(content)
                r = subprocess.run([sys.executable, '-B', str(SCRIPT), str(path)],
                                   capture_output=True, text=True)
                self.assertNotEqual(r.returncode, 0)
                self.assertIn('OPRIT', r.stderr)
                self.assertNotIn('pași orfani închiși', r.stdout)
                self.assertEqual(path.read_bytes() if path.exists() else None, content)

    def test_locked_database_and_concurrent_retries_leave_no_partial_updates(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'journal.sqlite3'
            self.fixture(path)
            before = path.read_bytes()
            db = sqlite3.connect(path)
            try:
                db.execute('BEGIN IMMEDIATE')
                def invoke(_):
                    # Ensure rejection never waits for SQLite's timeout or writer lock.
                    with self.assertRaisesRegex(RuntimeError, 'OPRIT'):
                        o.inchide(str(path))
                with mock.patch('sqlite3.connect', side_effect=AssertionError('must not open')):
                    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                        list(pool.map(invoke, range(8)))
            finally:
                db.rollback()
                db.close()
            self.assertEqual(path.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
