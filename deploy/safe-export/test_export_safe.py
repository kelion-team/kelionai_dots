import contextlib, io, json, os, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
import export_safe as e

class ExportTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name)/'source'; self.out=Path(self.temp.name)/'out'; self.out.mkdir()
        for root in (*e.ROOTS,'etc/systemd/system'): (self.base/root).mkdir(parents=True)
        self.put('opt/kelion-pod/app.py','print("hello")\n')
    def put(self,p,s):
        q=self.base/p;q.parent.mkdir(parents=True,exist_ok=True);q.write_bytes(s if isinstance(s,bytes) else s.encode());return q
    def prepare(self):
        with contextlib.redirect_stdout(io.StringIO()): return e.prepare(self.base,self.out)
    def test_allowlist_and_no_network(self):
        for p in ['opt/kelion-pod/venv/lib.py','opt/kelion-pod/data.json','opt/kelion-pod/data.md','opt/kelion-pod/.env','opt/kelion-lucru/x.py']: self.put(p,'harmless')
        self.put('opt/kelion-pod/locuri.json','{}')
        with patch.object(e,'private_repo',side_effect=AssertionError('network')),patch.object(e.subprocess,'run',side_effect=AssertionError('process')):
            work,h=self.prepare()
        self.assertEqual([x['path'] for x in e.verify(work,h)],['opt/kelion-pod/app.py','opt/kelion-pod/locuri.json'])
    def test_redact_comments_and_credentials(self):
        text='[Service]\nEnvironment="A=secretAlpha" \\\n# comment\n; comment\n "B=secret Beta"\nUnsetEnvironment=HOME X=secretUnset\nSetCredential=gh:secretCredential\nSetCredentialEncrypted=abc:secretEncrypted\nPassEnvironment=HOME\nExecStart=/bin/true \\\n --flag\n'
        out=e.redact(text)
        for val in ['secretAlpha','secret Beta','secretUnset','secretCredential','secretEncrypted','# comment','; comment']: self.assertNotIn(val,out)
        self.assertIn('A=<redactat> B=<redactat>',out); self.assertIn('ExecStart=/bin/true \\\n --flag',out)
    def test_duplicate_secret_elsewhere_stops(self):
        with self.assertRaises(e.Stop): e.redact('Environment=A=secretAlpha\nExecStart=/bin/x secretAlpha\n')
    def test_ambiguous_escape_stops(self):
        with self.assertRaises(e.Stop): e.redact(r'Environment="A=hello\x20world"'+'\n')
    def test_invalid_utf8_unreadable_and_secret_excluded(self):
        self.put('opt/kelion-pod/bad.py',b'\xff')
        self.put('opt/kelion-pod/secret.py','token="ghp_'+'A'*36+'"')
        self.put('opt/kelion-pod/unreadable.py','hello').chmod(0)
        work,h=self.prepare(); self.assertEqual(len(e.verify(work,h)),1)
        self.assertEqual(len(json.loads((work/'excluse.json').read_text())),3)
    def test_unreadable_systemd_stops(self):
        self.put('etc/systemd/system/kelion-app.service',b'\xff')
        with self.assertRaises(e.Stop): self.prepare()
    def test_excluded_directories_pruned_before_type_checks(self):
        self.put('opt/kelion-pod/venv/bin/placeholder.py','ignored')
        (self.base/'opt/kelion-pod/venv/bin/python').symlink_to('/fictional/python')
        (self.base/'opt/kelion-pod/node_modules').mkdir()
        os.mkfifo(self.base/'opt/kelion-pod/node_modules/fifo')
        work,h=self.prepare();self.assertEqual(len(e.verify(work,h)),1)
    def test_symlink_source_stops(self):
        (self.base/'opt/kelion-pod/link.py').symlink_to('app.py')
        with self.assertRaises(e.Stop): self.prepare()
    def test_special_source_stops(self):
        os.mkfifo(self.base/'opt/kelion-pod/pipe.py')
        with self.assertRaises(e.Stop): self.prepare()
    def test_traversal_error_stops(self):
        with patch.object(e.os,'scandir',side_effect=PermissionError('fixture')):
            with self.assertRaises(PermissionError): self.prepare()
    def test_manifest_tamper_stops(self):
        work,h=self.prepare(); (work/'inventar.json').write_text('[]\n')
        with self.assertRaises(e.Stop): e.verify(work,h)
    def test_file_tamper_stops(self):
        work,h=self.prepare(); (work/'server/opt/kelion-pod/app.py').write_text('changed')
        with self.assertRaises(e.Stop): e.verify(work,h)
    def test_same_count_different_path_stops(self):
        work,h=self.prepare(); (work/'server/opt/kelion-pod/app.py').rename(work/'server/opt/kelion-pod/other.py')
        with self.assertRaises(e.Stop): e.verify(work,h)
    def test_same_bytes_symlink_stops(self):
        work,h=self.prepare(); p=work/'server/opt/kelion-pod/app.py'; other=work/'same'; other.write_bytes(p.read_bytes());p.unlink();p.symlink_to(other)
        with self.assertRaises(e.Stop): e.verify(work,h)
    def test_repeat_unique(self):
        a,_=self.prepare();b,_=self.prepare();self.assertNotEqual(a,b)
    def test_verified_copy(self):
        work,h=self.prepare(); approved=e.verify(work,h); dest=work/'new'
        e.copy_verified(work/'server',dest,approved); self.assertEqual(e.manifest(dest),approved)
    def test_copy_tampered_source_rejected(self):
        work,h=self.prepare(); approved=e.verify(work,h)
        (work/'server/opt/kelion-pod/app.py').write_text('changed')
        with self.assertRaises(e.Stop): e.copy_verified(work/'server',work/'new',approved)
    def test_publish_cancel_no_token_or_network(self):
        work,h=self.prepare()
        with patch('builtins.input',return_value='NU'),patch.object(e.getpass,'getpass',side_effect=AssertionError('token')),patch.object(e,'private_repo',side_effect=AssertionError('network')),contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(e.Stop): e.publish(work,h)
    def test_tamper_after_confirmation_before_token(self):
        work,h=self.prepare()
        def approval(_):
            (work/'server/opt/kelion-pod/app.py').write_text('changed');return 'DA'
        with patch('builtins.input',side_effect=approval),patch.object(e.getpass,'getpass',side_effect=AssertionError('token')),contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(e.Stop): e.publish(work,h)
    def test_private_repo_checked(self):
        import urllib.request
        for value in [dict(private=False,full_name=e.TARGET,permissions={'push':True}),dict(private=True,full_name='other/repo',permissions={'push':True}),dict(private=True,full_name=e.TARGET,permissions={'push':False})]:
            response=io.BytesIO(json.dumps(value).encode())
            with patch.object(urllib.request,'build_opener') as b:
                b.return_value.open.return_value=response
                with self.assertRaises(e.Stop): e.private_repo('fictional-only')
    def test_publish_end_to_end_local_git_only(self):
        import subprocess
        real_run=subprocess.run
        remote=Path(self.temp.name)/'remote.git'; seed=Path(self.temp.name)/'seed'
        def local(*args):
            return real_run(['git',*map(str,args)],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        local('init','--bare',remote);local('init','-b','main',seed)
        (seed/'README.md').write_text('Fictional fixture only')
        local('-C',seed,'add','.');local('-C',seed,'-c','user.name=Fixture','-c','user.email=fixture@localhost','commit','-m','initial')
        local('-C',seed,'push',remote,'main');local('--git-dir',remote,'symbolic-ref','HEAD','refs/heads/main')
        before=local('--git-dir',remote,'rev-parse','main').stdout
        work,h=self.prepare(); calls=[]; fake='fictional-test-token-not-a-real-credential'
        def intercepted(cmd,**kw):
            calls.append(cmd)
            self.assertNotIn(fake,' '.join(cmd))
            # The only transport is substituted with our local synthetic bare repository.
            args=cmd[1:]
            while args and args[0]=='-c': args=args[2:]
            args=[str(remote) if x==e.URL else x for x in args]
            env=kw['env'].copy();env.pop('KELION_EXPORT_TOKEN',None)
            return real_run(['git',*args],**{**kw,'env':env})
        output=io.StringIO()
        with patch('builtins.input',return_value='DA'),patch.object(e.sys.stdin,'isatty',return_value=True),patch.object(e.getpass,'getpass',return_value=fake),patch.object(e,'private_repo',return_value='main') as api,patch.object(e.subprocess,'run',side_effect=intercepted),contextlib.redirect_stdout(output):
            e.publish(work,h)
        self.assertEqual(api.call_count,2)
        self.assertEqual(before,local('--git-dir',remote,'rev-parse','main').stdout)
        branches=local('--git-dir',remote,'for-each-ref','--format=%(refname)','refs/heads/copie/').stdout.decode().strip().splitlines()
        self.assertEqual(len(branches),1)
        blob=local('--git-dir',remote,'show',branches[0]+':server/opt/kelion-pod/app.py').stdout
        self.assertEqual(blob,b'print("hello")\n')
        self.assertNotIn(fake,output.getvalue())
        self.assertTrue(any('push' in c for c in calls))

    def test_systemd_override(self):
        self.put('etc/systemd/system/kelion-app.service.d/test.conf','[Service]\nEnvironment="TEST=fictionalSecret"\n')
        w,h=self.prepare(); self.assertNotIn('fictionalSecret',(w/'server/etc/systemd/system/kelion-app.service.d/test.conf').read_text());e.verify(w,h)

if __name__=='__main__': unittest.main(verbosity=2)
