#!/usr/bin/env python3
"""Host tests of the actual C emitter; never Agentd/native evidence."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import run_agentd_runtime as gate

NONCE = "a" * 64


class RuntimeEmitterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if shutil.which("gcc") is None:
            raise unittest.SkipTest("gcc is required for the real C emitter regression")
        cls.directory = tempfile.TemporaryDirectory()
        cls.root = Path(cls.directory.name)
        source = (Path(__file__).parent / "agentd_runtime_probe.c").resolve()
        # Only the I/O calls are controlled; compile the real production test
        # emitter unchanged. A 127-byte success and EINTR are ordinary I/O.
        text = '''#define _GNU_SOURCE
#include <unistd.h>
#include <errno.h>
static int io_mode, reads, writes;
static ssize_t controlled_read(int fd, void *data, size_t length);
static ssize_t controlled_write(int fd, const void *data, size_t length);
#define read controlled_read
#define write controlled_write
#define main original_launcher_main
#include SOURCE
#undef main
#undef read
#undef write
static ssize_t controlled_read(int fd, void *data, size_t length) {
    reads++;
    if (io_mode == 1 && reads == 1) { errno = EINTR; return -1; }
    if (io_mode == 2 && reads > 1) { errno = EIO; return -1; }
    if (io_mode != 0 && length > 127) length = 127;
    return read(fd, data, length);
}
static ssize_t controlled_write(int fd, const void *data, size_t length) {
    writes++;
    if (io_mode == 1 && writes == 1) { errno = EINTR; return -1; }
    if (io_mode == 3 && writes > 1) { errno = EIO; return -1; }
    if (io_mode != 0 && length > 127) length = 127;
    return write(fd, data, length);
}
int main(int argc, char **argv) {
    if (argc != 5) return 2;
    io_mode = atoi(argv[4]);
    return emit(argv[1], argv[2], NONCE, strtoul(argv[3], NULL, 10)) == 0 ? 0 : 1;
}
'''.replace('#include SOURCE', '#include ' + json.dumps(str(source))).replace('NONCE,', '"' + NONCE + '",')
        (cls.root / "probe.c").write_text(text)
        cls.binary = cls.root / "probe"
        subprocess.run(["gcc", "-std=c11", "-Wall", "-Wextra", "-Werror", str(cls.root / "probe.c"),
                        "-o", str(cls.binary)], check=True, capture_output=True, timeout=30)

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def execute(self, content, limit, name="STDOUT", mode=0):
        path = self.root / "input"
        path.write_bytes(content)
        return subprocess.run([str(self.binary), name, str(path), str(limit), str(mode)],
                              capture_output=True, timeout=30)

    def expected(self, name, content):
        return f"HEPTA_RUNTIME_{name} nonce={NONCE} hex=".encode() + content.hex().encode() + b"\n"

    def test_stdout_at_full_512kib_capacity(self):
        content = bytes(range(256)) * 2048
        result = self.execute(content, gate.STDOUT_LIMIT)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, self.expected("STDOUT", content))

    def test_stderr_at_full_64kib_capacity(self):
        content = bytes(range(256)) * 256
        result = self.execute(content, gate.STDERR_LIMIT, name="STDERR")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, self.expected("STDERR", content))

    def test_empty_output_has_one_complete_record(self):
        result = self.execute(b"", gate.STDERR_LIMIT, name="STDERR")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, self.expected("STDERR", b""))

    def test_short_reads_writes_and_eintr_preserve_complete_multiread_record(self):
        content = bytes(range(256)) * 33
        result = self.execute(content, gate.STDOUT_LIMIT, mode=1)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, self.expected("STDOUT", content))
        self.assertEqual(result.stderr, b"")

    def test_excess_stdout_or_stderr_has_no_partial_record(self):
        for name, limit in (("STDOUT", gate.STDOUT_LIMIT), ("STDERR", gate.STDERR_LIMIT)):
            with self.subTest(name=name):
                result = self.execute(b"a" * (limit + 1), limit, name=name)
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout, b"")

    def test_symlink_and_nonregular_input_rejected_before_prefix(self):
        regular = self.root / "regular"
        regular.write_bytes(b"inert")
        link = self.root / "link"
        link.symlink_to(regular)
        for path in (link, self.root):
            with self.subTest(path=path.name):
                result = subprocess.run([str(self.binary), "STDOUT", str(path), "512", "0"],
                                        capture_output=True, timeout=10)
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout, b"")

    def test_read_failure_after_partial_read_has_no_record(self):
        result = self.execute(b"a" * 8192, gate.STDOUT_LIMIT, mode=2)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, b"")

    def test_write_failure_never_returns_success_or_complete_record(self):
        result = self.execute(b"a" * 8192, gate.STDOUT_LIMIT, mode=3)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(len(result.stdout), 127)
        self.assertFalse(result.stdout.endswith(b"\n"))

    def test_warning_filter_is_explicit(self):
        argv = gate.qemu_argv("qemu", Path("/ordinary-fixture"), 4096)
        boot = argv[argv.index("-append") + 1]
        self.assertEqual([token for token in boot.split() if token.startswith("loglevel=")], ["loglevel=warn"])


if __name__ == "__main__":
    unittest.main()
