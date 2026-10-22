"""Mutate copied original logs, rehash them, and require semantic rejection."""

import contextlib
import gzip
import hashlib
import io
import json
from pathlib import Path
import runpy
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent
VERIFY = runpy.run_path(str(ROOT / "verify.py"))["main"]
JOBS = {224: 118984639491, 225: 119118562629}


class NativeLogVerificationTests(unittest.TestCase):
    def check_changed_log(self, number, transform, error):
        with tempfile.TemporaryDirectory(prefix="owner-audit-negative-") as temporary:
            root = Path(temporary) / "evidence"
            shutil.copytree(ROOT, root)
            name = f"kernel/pr{number}-kernel-job-{JOBS[number]}.log.gz"
            path = root / name
            original = gzip.decompress(path.read_bytes()).decode("utf-8")
            changed = transform(original)
            self.assertNotEqual(changed, original)
            decoded = changed.encode("utf-8")
            stored = gzip.compress(decoded, mtime=0)
            path.write_bytes(stored)
            manifest_path = root / "manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["files"][name] = {
                "bytes": len(stored),
                "sha256": hashlib.sha256(stored).hexdigest(),
                "uncompressed_bytes": len(decoded),
                "uncompressed_sha256": hashlib.sha256(decoded).hexdigest(),
            }
            manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
            with (
                self.assertRaisesRegex(ValueError, error),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                VERIFY(root)

    def change_record(self, log, predicate, transform):
        lines = log.splitlines(keepends=True)
        matches = 0
        for index, line in enumerate(lines):
            timestamp, separator, payload = line.partition("Z ")
            if not separator or not payload.startswith("{"):
                continue
            try:
                record = json.loads(payload)
            except json.JSONDecodeError:
                continue
            if predicate(record):
                matches += 1
                lines[index] = timestamp + separator + transform(record) + "\n"
        self.assertEqual(matches, 1)
        return "".join(lines)

    def guest(self, record):
        return (
            isinstance(record.get("verdict"), dict)
            and record["verdict"].get("guest") is True
        )

    def test_original_complete_evidence_passes(self):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            VERIFY(ROOT)
        self.assertIn(
            "both native log identities/results; desktop unassigned", output.getvalue()
        )

    def test_wrong_candidate_run_or_artifact_cannot_pass_after_rehashing(self):
        manifest = json.loads((ROOT / "manifest.json").read_text())
        assessment = json.loads((ROOT / "kernel/assessment.json").read_text())
        for number in JOBS:
            gate = assessment[f"pr{number}_native_gate"]
            replacements = [
                (
                    manifest["tree_commits"][str(number)],
                    "a" * 40,
                    "candidate checkout identity",
                ),
                (str(gate["run_id"]), str(gate["run_id"] + 1), "run/artifact identity"),
                (
                    str(gate["artifact_id"]),
                    str(gate["artifact_id"] + 1),
                    "run/artifact identity",
                ),
            ]
            for old, new, error in replacements:
                with self.subTest(number=number, field=error, old=old):
                    self.check_changed_log(
                        number, lambda log: log.replace(old, new), error
                    )

    def test_command_echo_is_not_a_guest_result_marker(self):
        for number in JOBS:
            with self.subTest(number=number):
                self.check_changed_log(
                    number,
                    lambda log: self.change_record(
                        log,
                        self.guest,
                        lambda record: (
                            "\x1b[36;1mprintf '%s\\n' '"
                            + json.dumps(record)
                            + "'\x1b[0m"
                        ),
                    ),
                    "exactly one guest verdict",
                )

    def test_failure_and_success_require_the_actual_guest_conditions(self):
        for number in JOBS:

            def inconsistent(record):
                record["verdict"]["failed_conditions"] = ["fabricated marker"]
                return json.dumps(record)

            with self.subTest(number=number):
                self.check_changed_log(
                    number,
                    lambda log: self.change_record(log, self.guest, inconsistent),
                    "guest failure/success markers",
                )

    def test_success_requires_executed_production_mutation_output(self):
        self.check_changed_log(
            225,
            lambda log: self.change_record(
                log,
                lambda record: record.get("schema") == "a06.exfat-one-line-negative.v1",
                lambda record: "echo " + json.dumps(record),
            ),
            "exactly one production mutation result",
        )


if __name__ == "__main__":
    unittest.main()
