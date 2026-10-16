"""Host-only safety regression tests for the in-memory diagnostic archive."""
import unittest
from run_guest_probe import pack, unpack, require

def entry(name="init", content=b"test"):
    return (name, [1,0o100755,0,0,1,0,len(content),0,0,0,0,len(name.encode())+1,0],content)

class ArchiveTests(unittest.TestCase):
    def test_roundtrip(self):
        e=[entry()]
        self.assertEqual(unpack(pack(e)),e)
    def test_truncated_header(self):
        with self.assertRaises(ValueError): unpack(b"070701")
    def test_duplicate_name(self):
        with self.assertRaises(ValueError): unpack(pack([entry(),entry()]))
    def test_traversal_rejected_without_extraction(self):
        with self.assertRaises(ValueError): unpack(pack([entry("../outside")]))
    def test_guard_works_without_assert(self):
        with self.assertRaises(ValueError): require(False,"must refuse")

if __name__ == "__main__": unittest.main()
