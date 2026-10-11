import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ExportGateTests(unittest.TestCase):
    def test_incomplete_or_failed_agents_never_produce_a_package(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'scripts').mkdir()
            (root / 'catalog').mkdir()
            shutil.copyfile(ROOT / 'scripts/export_agent.py', root / 'scripts/export_agent.py')
            complete = {'id': 'candidate', 'import_ready': True, 'live_model_verified': True, 'passed': 10, 'failures': 0, 'errors': 0, 'skipped': 0}
            cases = [[], [complete | {'live_model_verified': False}], [complete | {'import_ready': False}], [complete | {'known_upstream_check_errors': True}], [complete | {'passed': 0}], [complete | {'failures': 1}], [complete | {'errors': 1}], [complete | {'skipped': 1}]]
            for catalog in cases:
                with self.subTest(catalog=catalog):
                    (root / 'catalog/import-ready.json').write_text(json.dumps(catalog))
                    output = root / 'agent.zip'
                    result = subprocess.run([sys.executable, str(root / 'scripts/export_agent.py'), 'candidate', '--output', str(output)], capture_output=True, text=True)
                    self.assertEqual(result.returncode, 2, result.stderr)
                    self.assertIn('Export refused:', result.stderr)
                    self.assertFalse(output.exists())

    def test_missing_approval_catalog_is_a_controlled_refusal(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'scripts').mkdir()
            shutil.copyfile(ROOT / 'scripts/export_agent.py', root / 'scripts/export_agent.py')
            result = subprocess.run([sys.executable, str(root / 'scripts/export_agent.py'), 'candidate', '--output', str(root / 'agent.zip')], capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertNotIn('Traceback', result.stderr)


if __name__ == '__main__':
    unittest.main()
