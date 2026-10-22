"""Offline regressions: unsafe repair must refuse before preparing/installing anything."""
import concurrent.futures
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).with_name('repara_registru_procedura.py')
SHELL = Path(__file__).with_name('repara-registru.sh')
# Synthetic input deliberately satisfies the old replacement anchor. No live source.
COADA = '''import os
BAZA = '/unused'
def delegare_rol(s):
    try:
        RD = s
        rol = subrol = None; ales = ''
        efectiv, prefix = RD.delegare(rol, subrol, BAZA)
        return efectiv + ales, prefix
    except Exception:
        return 'fallback', ''
'''


def snapshot(root):
    return {str(p.relative_to(root)): p.read_bytes()
            for p in root.rglob('*') if p.is_file()}


class Teste(unittest.TestCase):
    def test_refuses_without_changing_criteria_or_preparing_prompt_only_stop(self):
        for procedure in (None, '', 'Synthetic procedure'):
            with self.subTest(procedure=procedure), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                source = root / 'source'
                (source / 'cerinte').mkdir(parents=True)
                (source / 'coada-lucru.py').write_text(COADA)
                (source / 'cerinte/registru-zi.json').write_text(json.dumps({
                    'cerinte': [{'id': i, 'verifica': {'original': i}, 'dovada': 'preserve'}
                                for i in ('R5', 'R17', 'R20', 'R33', 'A4', 'A12', 'R1')]}))
                if procedure is not None:
                    (source / 'cerinte/procedura-nou.md').write_text(procedure)
                before = snapshot(root)
                result = subprocess.run([sys.executable, '-B', str(SCRIPT), str(source),
                                         str(root / 'output')], capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn('OPRIT', result.stderr)
                self.assertEqual(snapshot(root), before)
                self.assertFalse((root / 'output').exists())

    def test_refuses_missing_inputs_without_creating_destination(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = subprocess.run([sys.executable, '-B', str(SCRIPT), str(root / 'missing'),
                                     str(root / 'output')], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((root / 'output').exists())

    def test_repeated_and_concurrent_calls_preserve_existing_destination(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'cerinte').mkdir()
            (root / 'coada-lucru.py').write_text(COADA)
            (root / 'cerinte/registru-zi.json').write_text(json.dumps({'cerinte': [
                {'id': i, 'verifica': {'original': i}}
                for i in ('R5', 'R17', 'R20', 'R33', 'A4', 'A12')]}))
            before = snapshot(root)
            def invoke(_):
                return subprocess.run([sys.executable, '-B', str(SCRIPT), str(root), str(root)],
                                      capture_output=True, text=True)
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                results = list(pool.map(invoke, range(8)))
            self.assertTrue(all(r.returncode != 0 for r in results))
            self.assertEqual(snapshot(root), before)

    def test_shell_refuses_before_download_backup_install_or_cleanup(self):
        # All external operations in the old wrapper are intercepted. Its absolute
        # destination is redirected ONLY in the test copy, never in production code.
        # Failure injection proves the previous backup/cleanup false-success paths.
        for failure in ('none', 'backup', 'cleanup', 'install', 'compile', 'download'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / 'cerinte').mkdir()
                (root / 'cerinte/procedura-nou.md').write_text('fixture')
                script = root / 'wrapper.sh'
                script.write_text(SHELL.read_text().replace('DIR=/opt/kelion-brain',
                                                            'DIR="$TEST_ROOT"'))
                trace = root / 'trace'
                driver = r'''
id() { echo 0; }
date() { echo fixed; }
curl() { echo download >> "$TRACE"; [[ "$FAIL" != download ]]; }
chmod() { echo chmod >> "$TRACE"; }
cp() { echo cp >> "$TRACE"; }
install() { echo install >> "$TRACE"; [[ "$FAIL" != install ]]; }
grep() { echo 1; }
runuser() { shift 3; "$@"; }
python3() {
  echo "python $*" >> "$TRACE"
  if [[ "$*" == *'import sqlite3'* && "$FAIL" == backup ]]; then return 7; fi
  if [[ "$*" == *'/o.py'* && "$FAIL" == cleanup ]]; then return 8; fi
  if [[ "$*" == *'py_compile'* && "$FAIL" == compile ]]; then return 9; fi
  return 0
}
source "$TEST_ROOT/wrapper.sh"
'''
                env = dict(os.environ, TEST_ROOT=str(root), TRACE=str(trace), FAIL=failure,
                           KELION_REF='5e900371d3b4b3b3089112e59b0ddd2cecebbb4e')
                r = subprocess.run(['bash', '-c', driver], env=env, capture_output=True, text=True)
                self.assertNotEqual(r.returncode, 0, r.stdout)
                self.assertIn('OPRIT', r.stderr)
                self.assertNotIn('GATA', r.stdout)
                self.assertFalse(trace.exists(), trace.read_text() if trace.exists() else '')

    def test_shell_also_refuses_without_ref(self):
        env = dict(os.environ)
        env.pop('KELION_REF', None)
        r = subprocess.run(['bash', str(SHELL)], env=env, capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('OPRIT', r.stderr)


if __name__ == '__main__':
    unittest.main()
