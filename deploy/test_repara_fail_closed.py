"""Execute the real deploy scripts against temporary files and mocked services.

No network, root privileges, live files, patcher, or systemd calls. This tests
shell failure propagation, not WhatsApp acceptance or guest isolation.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

MOCK = r"""
import json, os, pathlib, subprocess, sys
name = pathlib.Path(sys.argv[0]).name
args = sys.argv[1:]
root = pathlib.Path(os.environ['FIXTURE'])
fail = os.environ.get('FAIL_STAGE', '')
with (root/'commands.jsonl').open('a') as f:
    f.write(json.dumps([name, *args])+'\n')
stage = ''
if name == 'mktemp':
    stage = 'mktemp'
elif name == 'cp':
    if 'backup-' in args[-1]:
        stage = 'css_backup' if 'portal.css' in args[-1] else 'html_backup' if 'portal.html' in args[-1] else 'pod_backup'
    elif any('backup-' in a for a in args[:-1]):
        stage = 'rollback_copy'
elif name == 'mkdir' and 'backup-' in args[-1]:
    stage = 'backup_dir'
elif name == 'install':
    stage = 'install_' + pathlib.Path(args[-1]).name
elif name == 'systemctl' and args[0] == 'restart':
    stage = 'restart'
elif name == 'curl':
    url = next(x for x in args if x.startswith('http'))
    if 'companion-layout.css' in url:
        stage = 'css_download'
    elif 'repara_' in url:
        stage = 'patch_download'
if stage and fail == stage:
    sys.exit(73)
if name == 'mktemp' and fail == 'mktemp_empty':
    pass
elif name == 'mktemp' and fail == 'mktemp_missing':
    print(root/'not-created')
elif name == 'id':
    print('0')
elif name == 'curl':
    if '-o' in args:
        out = pathlib.Path(args[args.index('-o')+1])
        out.write_text('KELION_COMPANION_LAYOUT_20261021\nKELION_COMPANION_LAYOUT_20261021_END\n'
                       if stage == 'css_download' else '# mock patcher\n')
    else:
        print('{"apel_in_curs": false, "ok": true}')
elif name == 'python3':
    dest = pathlib.Path(args[-1])
    (dest/'pod_locuri').mkdir(parents=True)
    for f in ['executor_server.py', 'locuri.py', 'resurse.py']:
        (dest/'pod_locuri'/f).write_text('patched\n')
    (dest/'kelion_pod.py').write_text('necunoscut_pe_ruta_invitat\n')
    (dest/'apel_invitat.py').write_text('patched\n')
elif name == 'systemctl':
    if args[0] == 'is-active' and fail in ('rollback_copy', 'health'):
        sys.exit(1)
elif name == 'sleep':
    pass
else:
    sys.exit(subprocess.call(['/usr/bin/'+name, *args]))
"""

class DeployFailureTests(unittest.TestCase):
    def run_script(self, step, fail='', ref=True):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            pod, assets = root/'pod', root/'assets'
            (pod/'pod_locuri').mkdir(parents=True)
            assets.mkdir()
            for name in ['kelion_pod.py', 'apel_invitat.py']:
                (pod/name).write_text('original\n')
            for name in ['executor_server.py', 'locuri.py', 'resurse.py']:
                (pod/'pod_locuri'/name).write_text('original\n')
            (assets/'portal.css').write_text('original style\n')
            (assets/'portal.html').write_text('portal.css?v=original\n')
            journal = root/'pod.jsonl'
            journal.write_text('{"ev":"pornit","loc_stare":"pregatit"}\n')
            bindir = root/'bin'
            bindir.mkdir()
            wrapper = bindir/'mock'
            wrapper.write_text('#!'+sys.executable+'\n'+MOCK)
            wrapper.chmod(0o755)
            for name in ('cp', 'mkdir', 'install', 'systemctl', 'curl', 'python3', 'sleep', 'id', 'mktemp'):
                (bindir/name).symlink_to(wrapper)
            source = Path(__file__).with_name(f'repara-pas{step}.sh').read_text()
            source = source.replace('POD=/opt/kelion-pod', f'POD={pod}')
            source = source.replace('ASSETS=/opt/kelion-control/assets', f'ASSETS={assets}')
            source = source.replace('J=/var/lib/kelion-pod/pod.jsonl', f'J={journal}')
            script = root/'run.sh'
            script.write_text(source)
            env = dict(os.environ, PATH=str(bindir)+':'+os.environ['PATH'],
                       FIXTURE=td, FAIL_STAGE=fail, TMPDIR=td,
                       KELION_REF='0123456789abcdef0123456789abcdef01234567')
            if not ref: env.pop('KELION_REF')
            result = subprocess.run(['bash', str(script)], env=env, text=True,
                                    capture_output=True, timeout=15)
            log = root/'commands.jsonl'
            events = [json.loads(x) for x in log.read_text().splitlines()] if log.exists() else []
            files = {str(p.relative_to(root)): p.read_text() for p in
                     [pod/'kelion_pod.py', pod/'apel_invitat.py', *sorted((pod/'pod_locuri').glob('*.py'))] if p.exists()}
            return result, events, files

    def test_missing_commit_ref_stops_before_any_action(self):
        for step in (2, 3):
            with self.subTest(step=step):
                result, events, files = self.run_script(step, ref=False)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('KELION_REF', result.stdout)
                self.assertFalse(any(e[0] in ('curl', 'install', 'systemctl', 'cp') for e in events))

    def test_backup_failure_stops_before_install_and_restart(self):
        for step in (2, 3):
            for failure in ('backup_dir', 'pod_backup'):
                with self.subTest(step=step, failure=failure):
                    result, events, files = self.run_script(step, failure)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertFalse(any(e[0] == 'install' for e in events))
                    self.assertFalse(any(e[:2] == ['systemctl', 'restart'] for e in events))
                    self.assertTrue(all(v == 'original\n' for v in files.values()))
                    self.assertNotIn('GATA.', result.stdout)

    def test_each_install_failure_stops_remaining_installs_and_restart(self):
        for step, names in [(2, ['executor_server.py', 'locuri.py', 'resurse.py']),
                            (3, ['kelion_pod.py', 'apel_invitat.py'])]:
            for index, name in enumerate(names):
                with self.subTest(step=step, name=name):
                    result, events, _ = self.run_script(step, 'install_'+name)
                    self.assertNotEqual(result.returncode, 0)
                    installs = [Path(e[-1]).name for e in events if e[0] == 'install']
                    self.assertEqual(installs, names[:index+1])
                    self.assertFalse(any(e[:2] == ['systemctl', 'restart'] for e in events))
                    self.assertNotIn('GATA.', result.stdout)

    def test_download_failure_never_reaches_install_or_restart(self):
        for step, failure in [(2, 'css_download'), (2, 'patch_download'), (3, 'patch_download')]:
            with self.subTest(step=step, failure=failure):
                result, events, files = self.run_script(step, failure)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(any(e[0] == 'install' for e in events))
                self.assertFalse(any(e[:2] == ['systemctl', 'restart'] for e in events))
                self.assertTrue(all(v == 'original\n' for v in files.values()))
                self.assertNotIn('GATA.', result.stdout)
                if failure == 'css_download':
                    self.assertNotIn('B) Locuri', result.stdout)

    def test_companion_backup_failure_does_not_proceed_to_b(self):
        for failure in ('css_backup', 'html_backup'):
            with self.subTest(failure=failure):
                result, events, _ = self.run_script(2, failure)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn('B) Locuri', result.stdout)
                self.assertFalse(any(e[0] == 'install' for e in events))
                self.assertNotIn('GATA.', result.stdout)

    def test_restart_failure_does_not_report_success(self):
        for step in (2, 3):
            with self.subTest(step=step):
                result, _, _ = self.run_script(step, 'restart')
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn('GATA.', result.stdout)


    def test_invalid_temporary_directory_stops_before_download(self):
        for step in (2, 3):
            for failure in ('mktemp', 'mktemp_empty', 'mktemp_missing'):
                with self.subTest(step=step, failure=failure):
                    result, events, files = self.run_script(step, failure)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertFalse(any(e[0] in ('curl', 'install', 'systemctl') for e in events))
                    self.assertTrue(all(v == 'original\n' for v in files.values()))
                    self.assertNotIn('GATA.', result.stdout)

    def test_failed_rollback_copy_never_restarts_incomplete_restore(self):
        for step in (2, 3):
            with self.subTest(step=step):
                result, events, _ = self.run_script(step, 'rollback_copy')
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(sum(e[:2] == ['systemctl', 'restart'] for e in events), 1)
                self.assertIn('restaurare backup eșuată', result.stderr)
                self.assertNotIn('GATA.', result.stdout)

    def test_successful_restore_keeps_failure_exit_and_second_restart(self):
        for step in (2, 3):
            with self.subTest(step=step):
                result, events, files = self.run_script(step, 'health')
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(sum(e[:2] == ['systemctl', 'restart'] for e in events), 2)
                self.assertTrue(all(v == 'original\n' for v in files.values()))
                self.assertNotIn('GATA.', result.stdout)

    def test_success_path_preserved(self):
        for step, count in [(2, 3), (3, 2)]:
            with self.subTest(step=step):
                result, events, _ = self.run_script(step)
                self.assertEqual(result.returncode, 0, result.stderr+result.stdout)
                self.assertEqual(sum(e[0] == 'install' for e in events), count)
                self.assertEqual(sum(e[:2] == ['systemctl', 'restart'] for e in events), 1)
                self.assertIn('GATA.', result.stdout)

if __name__ == '__main__':
    unittest.main(verbosity=2)
