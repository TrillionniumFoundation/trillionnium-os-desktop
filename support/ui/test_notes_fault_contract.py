"""The external observer may act only before the first exact Applied body."""
import copy
import importlib.util
import json
from pathlib import Path
import py_compile
import shutil
import subprocess
import sys
import tempfile
import unittest

from notes_fault_contract import Refused, Transaction, digest


class PartialReplyBoundary(unittest.TestCase):
    def setUp(self):
        self.target = {"session_instance": "a" * 32, "task_id": 3, "incarnation": "b" * 32}
        self.text = "原线程恢复验收"
        self.request = {"schema_version": 1, "action": "replace_note", "operation_id": "original:op-1",
                        "destination_id": "trill.notes:" + "a" * 32 + ":3:" + "b" * 32,
                        "target": self.target, "expected_revision": 5, "text": self.text}
        self.raw = self.encode(self.request)
        self.reply = {"schema_version": 1, "target": self.target, "operation_id": "original:op-1",
                      "payload_sha256": digest(self.raw), "result": {"status": "applied",
                      "previous_revision": 5, "revision": 6, "text_sha256": digest(self.text.encode())}}

    @staticmethod
    def encode(value):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()

    def observer(self, raw=None):
        value = Transaction(copy.deepcopy(self.target), 5, digest(self.text.encode()))
        raw = self.raw if raw is None else raw
        frame = len(raw).to_bytes(4, "big") + raw
        # Actual read_exact framing can be fragmented at any byte.
        for start in range(0, len(frame), 3):
            value.received(frame[start:start + 3])
        return value

    def header_sent(self, observer, reply):
        header = len(reply).to_bytes(4, "big")
        self.assertIsNone(observer.write_entry(header))
        observer.write_exit(1)
        self.assertIsNone(observer.write_entry(header[1:]))
        observer.write_exit(3)

    def test_real_header_full_request_and_first_applied_body_are_required(self):
        observer = self.observer()
        reply = self.encode(self.reply)
        self.header_sent(observer, reply)
        evidence = observer.write_entry(reply)
        self.assertEqual(evidence["payload_sha256"], digest(self.raw))
        self.assertEqual(evidence["boundary"], "four_real_header_bytes_zero_body_bytes")
        self.assertFalse(evidence["authoritative_owner_receipt"])
        self.assertNotIn("text", evidence)

    def test_header_entry_cannot_claim_applied_before_body_is_available(self):
        observer = self.observer()
        self.assertIsNone(observer.write_entry(len(self.encode(self.reply)).to_bytes(4, "big")))
        with self.assertRaisesRegex(Refused, "reply_without_complete_request"):
            observer.write_entry(self.encode(self.reply))

    def test_already_sent_body_cannot_be_faulted_on_a_later_write(self):
        observer = self.observer()
        reply = self.encode(self.reply)
        self.header_sent(observer, reply)
        observer.write_entry(reply)
        observer.write_exit(1)
        with self.assertRaisesRegex(Refused, "reply_body_already_sent"):
            observer.write_entry(reply[1:])

    def test_short_body_buffer_cannot_be_guessed_or_read_past_syscall_length(self):
        observer = self.observer()
        reply = self.encode(self.reply)
        self.header_sent(observer, reply)
        with self.assertRaisesRegex(Refused, "incomplete_applied_body_buffer"):
            observer.write_entry(reply[:4])

    def test_wrong_target_revision_text_and_duplicate_fields_refuse_before_reply(self):
        mutations = []
        for key, value in (("expected_revision", 4), ("text", "different"), ("target", dict(self.target, task_id=4))):
            request = dict(self.request, **{key: value})
            mutations.append(self.encode(request))
        mutations.append(self.raw[:-1] + b',"expected_revision":5}')
        for raw in mutations:
            with self.subTest(raw_sha=digest(raw)), self.assertRaises(Refused):
                self.observer(raw)

    def test_not_applied_unknown_and_mismatched_receipts_are_not_fault_boundaries(self):
        mutations = [dict(self.reply, result={"status": "not_applied", "reason": "revision_conflict", "current_revision": 6}),
                     dict(self.reply, result={"status": "unknown", "current_revision": 6}),
                     dict(self.reply, operation_id="other"), dict(self.reply, payload_sha256="f" * 64),
                     dict(self.reply, result=dict(self.reply["result"], revision=7)),
                     dict(self.reply, result=dict(self.reply["result"], text_sha256="0" * 64))]
        for value in mutations:
            with self.subTest(value=value):
                observer = self.observer()
                reply = self.encode(value)
                self.header_sent(observer, reply)
                with self.assertRaises(Refused):
                    observer.write_entry(reply)

    def test_payload_digest_is_original_bytes_not_reserialized_json(self):
        raw = json.dumps(self.request, ensure_ascii=False, indent=2).encode()
        observer = self.observer(raw)
        reply = self.encode(self.reply)
        self.header_sent(observer, reply)
        with self.assertRaisesRegex(Refused, "reply_payload_mismatch"):
            observer.write_entry(reply)

    def test_partial_start_and_multiple_request_frames_are_refused(self):
        for raw in (self.raw, (len(self.raw).to_bytes(4, "big") + self.raw) * 2):
            observer = Transaction(self.target, 5, digest(self.text.encode()))
            with self.subTest(raw_sha=digest(raw)), self.assertRaises(Refused):
                observer.received(raw)

    def test_root_entry_ignores_unchecked_source_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = Path(__file__).resolve().parent
            for name in ("notes_fault_contract.py", "notes_fault_linux.py", "notes_fault_controller.py"):
                shutil.copyfile(source / name, root / name)
            poison = root / "untrusted.py"
            poison.write_text('raise RuntimeError("ignored-cache-must-not-execute")\n')
            cached = Path(importlib.util.cache_from_source(str(root / "notes_fault_linux.py")))
            cached.parent.mkdir(parents=True)
            py_compile.compile(str(poison), cfile=str(cached), doraise=True,
                               invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH)
            cache_flags = ["-X", "pycache_prefix=" + sys.pycache_prefix] if sys.pycache_prefix is not None else []
            command = [sys.executable, "-I", "-B", *cache_flags, *(["-O"] * sys.flags.optimize),
                       str(root / "notes_fault_controller.py"), "--help"]
            actual = subprocess.run(command, capture_output=True)
            self.assertEqual(actual.returncode, 0, actual.stderr)
            # In the isolated negative copy, -B alone still reads the poison.
            entry = root / "notes_fault_controller.py"
            entry.write_text(entry.read_text().replace("sys.pycache_prefix = _source_cache",
                                                       "sys.pycache_prefix = _old_cache"))
            negative = subprocess.run(command, capture_output=True)
            self.assertNotEqual(negative.returncode, 0)
            self.assertIn(b"ignored-cache-must-not-execute", negative.stderr)


if __name__ == "__main__":
    unittest.main()
