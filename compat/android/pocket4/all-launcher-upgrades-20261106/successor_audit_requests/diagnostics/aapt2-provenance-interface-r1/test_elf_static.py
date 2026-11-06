#!/usr/bin/env python3
"""Local borrowed-FD parser controls; no network, loader execution, APK or Main."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("elf_static_local", HERE/"elf_static.py")
parser = importlib.util.module_from_spec(spec)
spec.loader.exec_module(parser)
BASE = 0x400000

def fixture(extra_loader=False):
    raw = bytearray(1024)
    strings = b"\0libfixture.so\0$ORIGIN/lib\0/usr/lib\0auditfixture.so\0"
    interp = b"/lib64/ld-linux-x86-64.so.2\0"
    entries = [(5, BASE+768), (10, len(strings)), (1, strings.index(b"libfixture.so")),
               (15, strings.index(b"$ORIGIN/lib")), (29, strings.index(b"/usr/lib"))]
    if extra_loader:
        entries.append((0x6ffffefc, strings.index(b"auditfixture.so")))
    entries.append((0, 0))
    ident = b"\x7fELF" + bytes([2,1,1,0,0]) + bytes(7)
    struct.pack_into("<16sHHIQQQIHHHHHH", raw, 0, ident, 3, 62, 1, 0, 64, 0, 0, 64, 56, 3, 0, 0, 0)
    def ph(index, kind, offset, address, n, mem=None, align=1):
        struct.pack_into("<IIQQQQQQ", raw, 64+index*56, kind, 4, offset, address, address, n,
                         n if mem is None else mem, align)
    ph(0, 1, 0, BASE, 1024, align=4096)
    ph(1, 2, 512, BASE+512, len(entries)*16)
    ph(2, 3, 384, BASE+384, len(interp))
    raw[384:384+len(interp)] = interp
    raw[768:768+len(strings)] = strings
    for i, pair in enumerate(entries):
        struct.pack_into("<qQ", raw, 512+i*16, *pair)
    return raw

def census():
    rows = {}
    for name in os.listdir("/proc/self/fd"):
        try:
            fd = int(name); st = os.fstat(fd)
            rows[fd] = (os.readlink("/proc/self/fd/"+name), st.st_dev, st.st_ino, st.st_mode)
        except FileNotFoundError:
            continue
        except OSError as e:
            if e.errno == 9:
                continue
            raise
    return rows

class Controls(unittest.TestCase):
    events = []
    def setUp(self):
        self.before = census()
    def tearDown(self):
        self.assertEqual(self.before, census())
    def inspect_fixture(self, raw, supplied_size=None):
        with tempfile.TemporaryFile() as f:
            f.write(raw); f.flush()
            fd = f.fileno()
            os.lseek(fd, 17, os.SEEK_SET)
            before = os.fstat(fd)
            try:
                return parser.inspect_elf_fd(fd, len(raw) if supplied_size is None else supplied_size)
            finally:
                self.assertEqual(os.lseek(fd, 0, os.SEEK_CUR), 17)
                self.assertEqual(os.fstat(fd), before)
    def reject(self, raw, reason, supplied_size=None):
        with self.assertRaisesRegex(parser.ELFError, "^"+reason+"$"):
            self.inspect_fixture(raw, supplied_size)

    def test_complete_fixture_raw_strings_and_borrowed_lifetime(self):
        row = self.inspect_fixture(fixture())
        self.assertEqual(row["interpreter"], "/lib64/ld-linux-x86-64.so.2")
        self.assertEqual(row["needed"], ["libfixture.so"])
        self.assertEqual(row["rpath"], "$ORIGIN/lib")
        self.assertEqual(row["runpath"], "/usr/lib")
        self.assertEqual(row["additional_loader_directives"], [])
        self.assertFalse(row["is_loader_resolution_proof"])
        self.assertEqual(row["dynamic"]["load_segment_index"], 0)
        self.assertEqual(row["string_table"]["offset"], 768)
        self.events.append({"name":"fixture_metadata_and_borrowed_fd_offset","result":"PASS"})

    def test_actual_local_system_elf_pread_only(self):
        path = Path(sys.executable).resolve()
        fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
        try:
            initial = os.fstat(fd)
            os.lseek(fd, 23, os.SEEK_SET)
            row = parser.inspect_elf_fd(fd, initial.st_size)
            self.assertEqual(os.lseek(fd, 0, os.SEEK_CUR), 23)
            self.assertEqual(os.fstat(fd), initial)
            self.assertEqual(row["machine"], "EM_X86_64")
            self.assertEqual(row["format"], "ELF64LE")
            self.assertFalse(row["is_loader_resolution_proof"])
            sha = hashlib.sha256()
            at = 0
            while at < initial.st_size:
                b = os.pread(fd, min(1048576, initial.st_size-at), at)
                self.assertTrue(b)
                sha.update(b); at += len(b)
            self.events.append({"name":"actual_local_system_elf_not_executed","path":str(path),
                                "bytes":initial.st_size,"sha256":sha.hexdigest(),
                                "interpreter":row["interpreter"],"needed":row["needed"],
                                "offset_unchanged":True,"fd_retained_by_caller":True,"result":"PASS"})
        finally:
            os.close(fd)

    def test_header_and_file_bounds(self):
        raw = fixture(); raw[4] = 1
        self.reject(raw, "ELF64_LITTLE_ENDIAN_VERSION1_REQUIRED")
        raw = fixture(); struct.pack_into("<H",raw,18,183)
        self.reject(raw, "X86_64_EXEC_OR_DYN_REQUIRED")
        raw = fixture(); struct.pack_into("<Q",raw,32,1000)
        self.reject(raw, "FILE_SPAN_OUT_OF_BOUNDS")
        raw = fixture(); struct.pack_into("<H",raw,56,0xffff)
        self.reject(raw, "NORMAL_BOUNDED_PHNUM_REQUIRED")
        raw = fixture(); struct.pack_into("<Q",raw,64+32,1025)
        self.reject(raw, "FILE_SPAN_OUT_OF_BOUNDS")
        self.reject(fixture()[:64], "SHORT_PREAD", 1024)
        self.events.append({"name":"malformed_class_machine_phnum_file_extent_and_short_pread","result":"PASS"})

    def test_unique_mapping_and_dynamic_rejections(self):
        raw = fixture(); struct.pack_into("<H",raw,56,4)
        struct.pack_into("<IIQQQQQQ",raw,64+3*56,1,4,776,BASE+776,BASE+776,8,8,1)
        self.reject(raw, "VIRTUAL_MAPPING_NOT_UNIQUE")
        raw = fixture(); struct.pack_into("<Q",raw,512+8,BASE-1)
        self.reject(raw, "VIRTUAL_MAPPING_NOT_UNIQUE")
        raw = fixture(); struct.pack_into("<Q",raw,512+16+8,parser.MAX_STRTAB_BYTES+1)
        self.reject(raw, "STRING_TABLE_SIZE_BOUND")
        raw = fixture(); struct.pack_into("<qQ",raw,512+3*16,5,BASE+768)
        self.reject(raw, "DUPLICATE_DYNAMIC_SINGLETON")
        raw = fixture(); struct.pack_into("<qQ",raw,512+5*16,1,1)
        self.reject(raw, "DYNAMIC_TABLE_UNTERMINATED")
        raw = fixture(); struct.pack_into("<Q",raw,512+2*16+8,999)
        self.reject(raw, "NEEDED_OFFSET_OUT_OF_BOUNDS")
        raw = fixture(); struct.pack_into("<H",raw,56,4)
        raw[64+3*56:64+4*56] = raw[64+56:64+2*56]
        self.reject(raw, "DUPLICATE_DYNAMIC_OR_INTERPRETER")
        self.events.append({"name":"partial_overlap_missing_mapping_dynamic_bounds_duplicates_and_missing_null","result":"PASS"})

    def test_unique_strtab_spans_two_loads_with_disjoint_file_ranges(self):
        raw = fixture()
        string_bytes = struct.unpack_from("<Q", raw, 512+16+8)[0]
        original = bytes(raw[768:768+string_bytes])
        split = 5
        struct.pack_into("<H",raw,56,4)
        struct.pack_into("<Q",raw,64+32,768+split)
        struct.pack_into("<Q",raw,64+40,768+split)
        struct.pack_into("<IIQQQQQQ",raw,64+3*56,1,4,944,BASE+768+split,BASE+768+split,
                         string_bytes-split,string_bytes-split,1)
        raw[944:944+string_bytes-split] = original[split:]
        row = self.inspect_fixture(raw)
        self.assertEqual(row["needed"], ["libfixture.so"])
        self.assertEqual(row["rpath"], "$ORIGIN/lib")
        self.assertEqual(row["runpath"], "/usr/lib")
        self.assertEqual(len(row["string_table"]["mappings"]), 2)
        self.assertIsNone(row["string_table"]["offset"])
        self.assertFalse(row["is_loader_resolution_proof"])
        self.events.append({"name":"unique_piecewise_file_backed_string_mapping","result":"PASS"})

    def test_interpreter_and_loader_directives_remain_explicit(self):
        raw = fixture(); raw[384] = ord("x")
        self.reject(raw, "ABSOLUTE_INTERPRETER_REQUIRED")
        raw = fixture(); raw[385] = 0
        self.reject(raw, "INTERPRETER_TERMINATION")
        row = self.inspect_fixture(fixture(extra_loader=True))
        self.assertEqual(row["additional_loader_directives"],
            [{"tag":0x6ffffefc,"name":"DT_AUDIT","value":"auditfixture.so"}])
        raw = fixture(); struct.pack_into("<Q",raw,512+3*16+8,0)
        row = self.inspect_fixture(raw)
        self.assertEqual(row["rpath"], "")
        self.assertIsNotNone(row["rpath"])
        self.assertFalse(row["is_loader_resolution_proof"])
        self.events.append({"name":"interpreter_rejected_and_extra_loader_or_empty_path_not_hidden","result":"PASS"})

if __name__ == "__main__":
    initial = census()
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Controls))
    final = census()
    report = {"schema":"pocket4-static-elf-local-controls-v1","success":result.wasSuccessful() and initial==final,
              "tests_run":result.testsRun,"failures":len(result.failures),"errors":len(result.errors),
              "skips":len(result.skipped),"cases":Controls.events,"fd_before":len(initial),"fd_after":len(final),
              "full_fd_identity_restored":initial==final,"Main_actions":0,"network_requests":0,
              "elf_executions":0,"APK_reads":0,
              "source_sha256":hashlib.sha256((HERE/"elf_static.py").read_bytes()).hexdigest()}
    print(json.dumps(report,ensure_ascii=False,indent=2))
    raise SystemExit(0 if report["success"] else 1)

