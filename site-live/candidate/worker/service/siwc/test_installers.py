"""Offline archive safety checks. No download, package install, OAuth or model."""
import io
from pathlib import Path
import tarfile
import tempfile
import unittest
from install_codex import extract_binary


class InstallerTests(unittest.TestCase):
    def archive(self, root, name, *, link=False):
        archive=root/'synthetic.tar.gz'
        with tarfile.open(archive,'w:gz') as out:
            member=tarfile.TarInfo(name)
            if link: member.type=tarfile.SYMTYPE;member.linkname='/private/secret';out.addfile(member)
            else: member.size=9;out.addfile(member,io.BytesIO(b'SYNTHETIC'))
        return archive

    def test_exact_regular_binary_only_no_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);archive=self.archive(root,'codex-x86_64-unknown-linux-musl')
            extract_binary(archive,root/'codex','codex')
            self.assertEqual((root/'codex').read_bytes(),b'SYNTHETIC')
            with self.assertRaises(FileExistsError):extract_binary(archive,root/'codex','codex')

    def test_traversal_and_symlinks_rejected_before_write(self):
        for name,link in [('../codex',False),('/codex',False),('codex',True)]:
            with self.subTest(name=name,link=link),tempfile.TemporaryDirectory() as temp:
                root=Path(temp);archive=self.archive(root,name,link=link)
                with self.assertRaises(ValueError):extract_binary(archive,root/'codex','codex')
                self.assertFalse((root/'codex').exists())


if __name__=='__main__':unittest.main()
