import gzip, hashlib, importlib.util, json, os, pathlib, stat, tempfile, unittest
from unittest.mock import patch

MODULE=str(pathlib.Path(__file__).resolve().with_name('archive.py'))
spec=importlib.util.spec_from_file_location('a01_archive_candidate',MODULE)
arch=importlib.util.module_from_spec(spec);spec.loader.exec_module(arch)

class ArchiveTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.root=pathlib.Path(self.tmp.name);self.src=self.root/'source';self.src.mkdir();self.dest=self.root/'output'
 def test_roundtrip_and_sha_reproducible(self):
  d=self.src/'folder';d.mkdir();(d/'one.log').write_bytes(b'1234');(d/'two.json').write_bytes(b'{}')
  self.assertEqual(arch.archive(self.src,self.dest),2)
  self.assertEqual(gzip.decompress((self.dest/'folder/one.log.gz').read_bytes()),b'1234')
  self.assertFalse((self.dest/'.archive-incomplete').exists())
  manifest=json.loads((self.dest/'archive.json').read_text());self.assertEqual(len(manifest['files']),2)
  rows=(self.dest/'evidence.sha256').read_text().splitlines();self.assertEqual(len(rows),3)
  for line in rows:
   sha,name=line.split('  ');self.assertEqual(sha,hashlib.sha256((self.dest/name).read_bytes()).hexdigest())
 def test_empty_and_missing_never_create_fake_bundle(self):
  with self.assertRaises(ValueError):arch.archive(self.src,self.dest)
  self.assertFalse(self.dest.exists());self.src.rmdir()
  with self.assertRaises(ValueError):arch.archive(self.src,self.dest)
  self.assertFalse(self.dest.exists())
 def test_root_source_symlink_is_rejected(self):
  link=self.root/'link';link.symlink_to(self.src,target_is_directory=True)
  with self.assertRaises(ValueError):arch.archive(link,self.dest)
  self.assertFalse(self.dest.exists())
 def test_hardlinked_external_source_is_rejected(self):
  secret=self.root/'external.json';secret.write_text('private');os.link(secret,self.src/'copy.json')
  with self.assertRaises(ValueError):arch.archive(self.src,self.dest)
  self.assertFalse(self.dest.exists())
 def test_partial_output_is_quarantined_without_destructive_cleanup(self):
  def broken(_):
   yield pathlib.Path('one.json'),b'one';raise ValueError('injected read error')
  with patch.object(arch,'source_files',broken):
   with self.assertRaisesRegex(ValueError,'injected read error'):arch.archive(self.src,self.dest)
  self.assertTrue((self.dest/'.archive-incomplete').is_file())
  self.assertEqual((self.dest/'one.json').read_bytes(),b'one')
  self.assertEqual(stat.S_IMODE(self.dest.stat().st_mode),0o700)
 def test_swapped_destination_never_writes_into_substitute(self):
  held=self.root/'original-inode'
  def malicious(_):
   yield pathlib.Path('one.json'),b'one'
   self.dest.rename(held);self.dest.mkdir();(self.dest/'keep.txt').write_text('SAFE')
   yield pathlib.Path('two.json'),b'two'
  with patch.object(arch,'source_files',malicious):
   with self.assertRaisesRegex(ValueError,'replaced during write'):arch.archive(self.src,self.dest)
  self.assertEqual((self.dest/'keep.txt').read_text(),'SAFE')
  self.assertFalse((self.dest/'two.json').exists())
  self.assertTrue((held/'.archive-incomplete').exists())
  self.assertEqual((held/'one.json').read_bytes(),b'one')
  self.assertEqual((held/'two.json').read_bytes(),b'two')
 def test_existing_output_is_untouched(self):
  self.dest.mkdir();(self.dest/'keep.txt').write_text('SAFE');(self.src/'one.json').write_text('{}')
  with self.assertRaises(FileExistsError):arch.archive(self.src,self.dest)
  self.assertEqual((self.dest/'keep.txt').read_text(),'SAFE')
 def test_symlinked_nested_directory_rejected(self):
  other=self.root/'outside';other.mkdir();(other/'private.json').write_text('private')
  (self.src/'unsafe').symlink_to(other,target_is_directory=True)
  with self.assertRaises(ValueError):arch.archive(self.src,self.dest)
  self.assertFalse(self.dest.exists())
 def test_unexpected_output_symlink_is_refused(self):
  self.dest.symlink_to(self.src,target_is_directory=True)
  with self.assertRaises((FileExistsError,ValueError)):arch.archive(self.src,self.dest)
  self.assertTrue(self.dest.is_symlink())
if __name__=='__main__':unittest.main(verbosity=2)
