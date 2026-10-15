import unittest,tempfile,pathlib,hashlib,json,os
import deploy_files as d

def sha(b):return hashlib.sha256(b).hexdigest()
class DeployTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.p=pathlib.Path(self.tmp.name);self.live=self.p/'live';self.src=self.p/'src';self.live.mkdir();self.src.mkdir();(self.live/'app.js').write_bytes(b'old');(self.src/'app.js').write_bytes(b'new');self.back=self.p/'backup';self.m=[{'path':'app.js','source_sha256':sha(b'new'),'expected_current_sha256':sha(b'old')}]
 def tearDown(self):self.tmp.cleanup()
 def test_apply_and_rollback(self):
  d.apply(self.live,self.src,self.m,self.back);self.assertEqual((self.live/'app.js').read_bytes(),b'new');d.rollback(self.live,self.back);self.assertEqual((self.live/'app.js').read_bytes(),b'old')
 def test_source_mismatch_no_changes(self):
  self.m[0]['source_sha256']='0'*64
  with self.assertRaises(ValueError):d.apply(self.live,self.src,self.m,self.back)
  self.assertEqual((self.live/'app.js').read_bytes(),b'old');self.assertFalse(self.back.exists())
 def test_live_drift_refused(self):
  (self.live/'app.js').write_bytes(b'other')
  with self.assertRaises(ValueError):d.apply(self.live,self.src,self.m,self.back)
  self.assertEqual((self.live/'app.js').read_bytes(),b'other')
 def test_path_escape_refused(self):
  self.m[0]['path']='../outside'
  with self.assertRaises(ValueError):d.apply(self.live,self.src,self.m,self.back)
 def test_symlink_refused(self):
  (self.live/'app.js').unlink();(self.live/'app.js').symlink_to(self.src/'app.js')
  with self.assertRaises(ValueError):d.apply(self.live,self.src,self.m,self.back)
 def test_rollback_drift_refused(self):
  d.apply(self.live,self.src,self.m,self.back);(self.live/'app.js').write_bytes(b'other')
  with self.assertRaises(ValueError):d.rollback(self.live,self.back)
  self.assertEqual((self.live/'app.js').read_bytes(),b'other')
 def test_mode_preserved(self):
  (self.live/'app.js').chmod(0o640);d.apply(self.live,self.src,self.m,self.back);self.assertEqual((self.live/'app.js').stat().st_mode&0o777,0o640)
 def test_new_file_rollback(self):
  (self.live/'app.js').unlink();self.m[0]['expected_current_sha256']=None;d.apply(self.live,self.src,self.m,self.back);d.rollback(self.live,self.back);self.assertFalse((self.live/'app.js').exists())
 def test_existing_backup_refused(self):
  self.back.mkdir()
  with self.assertRaises(FileExistsError):d.apply(self.live,self.src,self.m,self.back)
if __name__=='__main__':unittest.main()
