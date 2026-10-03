"""Native Git and rebound-data attacks on the portable D1 source binding."""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests/d1"))
import d1_source_provenance as source
import test_artifact_evidence as fixture
import verify_d1_artifact as verifier


def rebind(root: Path, receipt: dict) -> None:
    receipt["source_provenance"] = {
        "schema": "trillionnium.desktop.d1-source-provenance.v1",
        "archive_sha256": hashlib.sha256((root / source.ARCHIVE).read_bytes()).hexdigest(),
        "commit_sha256": hashlib.sha256((root / source.COMMIT).read_bytes()).hexdigest(),
    }
    fixture.bind(root, receipt, verifier.RECEIPT_PATH.as_posix(), sized=False)


class SourceProvenanceTests(unittest.TestCase):
    def test_contract_has_exact_bounds_and_false_authority(self):
        contract = json.loads((ROOT / "contracts/d1-source-provenance.v1.json").read_text())
        self.assertEqual(contract["limits"], {"archive_bytes": source.MAX_ARCHIVE_BYTES,
            "commit_bytes": source.MAX_COMMIT_BYTES, "source_file_bytes": source.MAX_FILE_BYTES,
            "source_files": source.MAX_FILES, "path_utf8_bytes": 4096, "path_components": 64})
        for key in ("archive_extraction", "execute_payloads", "old_v3_accepted_as_qualified",
                    "external_run_or_repository_authenticity_proven", "hardware_or_release_qualification", "production_ready"):
            self.assertIs(contract[key], False)

    def test_actual_git_stage_and_tree_accept_executable_and_utf8_names(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); repo = root / "repo"; repo.mkdir()
            for name, data, mode in (("file", b"data", 0o644), ("执行/脚本", b"#!/bin/sh\n", 0o755), ("foo.bar", b"order", 0o644)):
                path = repo / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data); path.chmod(mode)
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            subprocess.run(["git", "add", "."], cwd=repo, check=True)
            subprocess.run(["git", "-c", "user.name=Evidence test", "-c", "user.email=evidence@example.invalid", "commit", "-qm", "SOURCE_FIXTURE_ONLY"], cwd=repo, check=True)
            packet = root / "packet"; packet.mkdir()
            proof = source.stage_source(repo, packet)
            receipt = {"tested_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip(),
                "tree_sha": subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], cwd=repo, text=True).strip(),
                "evidence_role": "exact_main_push", "base_sha": "0" * 40, "source_provenance": proof}
            digests = {str(p.relative_to(repo)): hashlib.sha256(p.read_bytes()).hexdigest() for p in repo.rglob('*') if p.is_file() and '.git' not in p.relative_to(repo).parts}
            source.verify_source(packet, receipt, digests)

    def test_changed_receipt_tree_is_rejected_without_local_git_or_network(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); receipt = fixture.d1_fixture(root); receipt["tree_sha"] = "0" * 40
            fixture.write(root, verifier.RECEIPT_PATH.as_posix(), receipt)
            with patch.object(source.subprocess, "check_output", side_effect=AssertionError("offline reader called Git")):
                with self.assertRaisesRegex(ValueError, "declared tree"):
                    verifier.verify_artifact(root)

    def test_rebound_commit_tree_cannot_change_the_tested_oid(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); receipt = fixture.d1_fixture(root)
            raw = (root / source.COMMIT).read_bytes().replace(receipt["tree_sha"].encode(), b"0" * 40, 1)
            (root / source.COMMIT).write_bytes(raw); receipt["tree_sha"] = "0" * 40; rebind(root, receipt)
            with self.assertRaisesRegex(ValueError, "tested SHA"):
                verifier.verify_artifact(root)

    def test_rebound_tested_oid_cannot_change_the_archive_tree(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); receipt = fixture.d1_fixture(root)
            raw = (root / source.COMMIT).read_bytes().replace(receipt["tree_sha"].encode(), b"0" * 40, 1)
            (root / source.COMMIT).write_bytes(raw); receipt["tree_sha"] = "0" * 40
            receipt["tested_sha"] = source._oid(b"commit", raw).hex(); receipt["candidate_head_sha"] = receipt["tested_sha"]
            receipt["producer_workflow"]["workflow_sha"] = receipt["tested_sha"]; rebind(root, receipt)
            with self.assertRaisesRegex(ValueError, "declared Git tree"):
                verifier.verify_artifact(root)

    def test_rebound_archive_modes_cannot_change_the_declared_tree(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); receipt = fixture.d1_fixture(root)
            self.archive(root, executable="src.txt"); rebind(root, receipt)
            with self.assertRaisesRegex(ValueError, "declared Git tree"):
                verifier.verify_artifact(root)

    def test_rebound_archive_and_manifest_bytes_cannot_change_the_declared_tree(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); receipt = fixture.d1_fixture(root)
            entries = {**fixture.SOURCE_FILES, "src.txt": b"changed"}; self.archive(root, entries=entries)
            files = {p: hashlib.sha256(data).hexdigest() for p, data in entries.items()}
            aggregate = hashlib.sha256(json.dumps(files, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
            manifest = fixture.write(root, "evidence/source-input-digests.json", {"schema": "trillionnium.desktop.source-input-digests.v1", "file_count": len(files), "files": files, "files_sha256": aggregate})
            receipt.update(source_input_manifest_sha256=fixture.evidence.digest(manifest), source_input_files_sha256=aggregate); rebind(root, receipt)
            with self.assertRaisesRegex(ValueError, "declared Git tree"):
                verifier.verify_artifact(root)

    def test_old_v3_has_no_qualified_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); receipt = fixture.d1_fixture(root); receipt["schema"] = "trillionnium.desktop.d1-final-qualification.v3"
            fixture.write(root, verifier.RECEIPT_PATH.as_posix(), receipt)
            with self.assertRaisesRegex(ValueError, "schema"):
                verifier.verify_artifact(root)

    def test_merge_raw_commit_requires_exact_two_ordered_parents(self):
        for parents, okay in ((["a" * 40, "b" * 40], True), (["b" * 40, "a" * 40], False), (["a" * 40], False), ([], False), (["a" * 40, "b" * 40, "c" * 40], False)):
            with self.subTest(parents=parents), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); receipt = fixture.d1_fixture(root)
                raw = fixture.fixture_git_commit()[1].replace(b"author ", b"".join(b"parent " + p.encode() + b"\n" for p in parents) + b"author ", 1)
                (root / source.COMMIT).write_bytes(raw)
                receipt.update(event_name="pull_request", ref="refs/pull/152/merge", evidence_role="pr_synthetic_merge", promotion_authoritative=False,
                               base_sha="a" * 40, candidate_head_sha="b" * 40, tested_sha=source._oid(b"commit", raw).hex())
                receipt["producer_workflow"]["workflow_sha"] = receipt["tested_sha"]; rebind(root, receipt)
                if okay:
                    verifier.verify_artifact(root)
                else:
                    with self.assertRaisesRegex(ValueError, "ordered base/head"):
                        verifier.verify_artifact(root)

    def test_missing_or_unbound_proof_is_rejected(self):
        for operation in ("missing", "extra", "hash"):
            with self.subTest(operation=operation), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); receipt = fixture.d1_fixture(root)
                if operation == "missing": del receipt["source_provenance"]
                elif operation == "extra": receipt["source_provenance"]["trusted"] = True
                else: receipt["source_provenance"]["commit_sha256"] = "0" * 64
                fixture.write(root, verifier.RECEIPT_PATH.as_posix(), receipt)
                with self.assertRaisesRegex(ValueError, "provenance binding"):
                    verifier.verify_artifact(root)

    def test_unsafe_duplicate_or_undeclared_archive_members_are_rejected(self):
        for name, kind in (("src.txt", "duplicate"), ("../escape", "file"), ("src-link", "symlink"), ("other", "file"), ("src.txt", "hardlink")):
            with self.subTest(name=name, kind=kind), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); receipt = fixture.d1_fixture(root)
                self.archive(root, extra=(name, kind)); rebind(root, receipt)
                with self.assertRaises(ValueError): verifier.verify_artifact(root)

    def test_commit_and_source_file_size_bounds_are_enforced(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); receipt = fixture.d1_fixture(root)
            with (root / source.COMMIT).open("wb") as stream: stream.truncate(source.MAX_COMMIT_BYTES + 1)
            rebind(root, receipt)
            with self.assertRaisesRegex(ValueError, "byte bound"): verifier.verify_artifact(root)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); receipt = fixture.d1_fixture(root)
            with patch.object(source, "MAX_FILE_BYTES", 1), self.assertRaisesRegex(ValueError, "file size"):
                verifier.verify_artifact(root)

    def test_hardlinked_source_commit_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); receipt = fixture.d1_fixture(root)
            os.link(root / source.COMMIT, root / "alias")
            with self.assertRaisesRegex(ValueError, "hard link"): source.verify_source(root, receipt, fixture.SOURCE_FILES)

    def test_optimized_actual_cli_preserves_refusal(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); receipt = fixture.d1_fixture(root); receipt["tree_sha"] = "0" * 40
            fixture.write(root, verifier.RECEIPT_PATH.as_posix(), receipt)
            run = subprocess.run([sys.executable, "-O", str(ROOT / "tools/verify_d1_artifact.py"), str(root)], capture_output=True)
            self.assertNotEqual(run.returncode, 0); self.assertEqual(run.stdout, b"")

    def test_directory_below_regular_file_is_refused_in_either_order(self):
        for before in (True, False):
            with self.subTest(directory_first=before), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); receipt = fixture.d1_fixture(root)
                self.directory_archive(root, "src.txt/child", before=before); rebind(root, receipt)
                with self.assertRaisesRegex(ValueError, "file/directory conflict"):
                    verifier.verify_artifact(root)

    def test_pax_directory_raw_name_bound_and_canonical_spelling_precede_normalization(self):
        for name in (".github" + "/" * 8192, ".github//", ".github/../other"):
            with self.subTest(raw_name=name[:32]), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); receipt = fixture.d1_fixture(root)
                self.directory_archive(root, name, pax=True); rebind(root, receipt)
                with self.assertRaises(ValueError): verifier.verify_artifact(root)

    def test_only_declared_directory_ancestors_are_accepted(self):
        for name, okay in ((".github", True), (".github/workflows", True), ("untracked-empty", False)):
            with self.subTest(directory_name=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); receipt = fixture.d1_fixture(root)
                self.directory_archive(root, name); rebind(root, receipt)
                if okay: verifier.verify_artifact(root)
                else:
                    with self.assertRaisesRegex(ValueError, "declared file ancestor"):
                        verifier.verify_artifact(root)

    def test_raw_ustar_gnu_extensions_sparse_and_hidden_tail_are_refused(self):
        for case in ("ustar-repeated-directory-terminator", "gnu-longname", "sparse", "hidden-tail"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); receipt = fixture.d1_fixture(root)
                path = root / source.ARCHIVE
                if case == "hidden-tail":
                    path.write_bytes(path.read_bytes() + b"X" * 512)
                else:
                    format = tarfile.GNU_FORMAT if case == "gnu-longname" else tarfile.USTAR_FORMAT
                    with tarfile.open(path, "w", format=format) as archive:
                        member = tarfile.TarInfo(".github//" if case != "gnu-longname" else "d/" + "x" * 200)
                        member.type, member.mode = (tarfile.GNUTYPE_SPARSE if case == "sparse" else tarfile.DIRTYPE), 0o755
                        archive.addfile(member)
                        for name, payload in fixture.SOURCE_FILES.items():
                            item = tarfile.TarInfo(name); item.mode, item.size = 0o644, len(payload)
                            archive.addfile(item, io.BytesIO(payload))
                rebind(root, receipt)
                with self.assertRaises(ValueError): verifier.verify_artifact(root)

    def test_pax_sparse_metadata_local_and_global_are_refused_before_decoding(self):
        for global_header in (False, True):
            with self.subTest(global_header=global_header), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); receipt = fixture.d1_fixture(root)
                sparse = {"GNU.sparse.map": "0,6", "GNU.sparse.size": "6", "GNU.sparse.name": "src.txt"}
                with tarfile.open(root / source.ARCHIVE, "w", format=tarfile.PAX_FORMAT,
                                  pax_headers=sparse if global_header else None) as archive:
                    for name, payload in fixture.SOURCE_FILES.items():
                        member = tarfile.TarInfo(name); member.mode, member.size = 0o644, len(payload)
                        if name == "src.txt" and not global_header: member.pax_headers = sparse
                        archive.addfile(member, io.BytesIO(payload))
                rebind(root, receipt)
                with self.assertRaisesRegex(ValueError, "PAX sparse"):
                    verifier.verify_artifact(root)

    @staticmethod
    def directory_archive(root: Path, name: str, *, before=False, pax=False):
        with tarfile.open(root / source.ARCHIVE, "w", format=tarfile.PAX_FORMAT) as archive:
            def add_directory():
                member = tarfile.TarInfo(".github" if pax else name)
                member.type, member.mode = tarfile.DIRTYPE, 0o755
                if pax: member.pax_headers = {"path": name}
                archive.addfile(member)
            if before: add_directory()
            for path, payload in fixture.SOURCE_FILES.items():
                member = tarfile.TarInfo(path); member.mode, member.size = 0o644, len(payload)
                archive.addfile(member, io.BytesIO(payload))
            if not before: add_directory()

    @staticmethod
    def archive(root: Path, *, entries=None, executable=None, extra=None):
        with tarfile.open(root / source.ARCHIVE, "w") as archive:
            for name, payload in (entries or fixture.SOURCE_FILES).items():
                member = tarfile.TarInfo(name); member.size = len(payload); member.mode = 0o755 if name == executable else 0o644
                archive.addfile(member, io.BytesIO(payload))
            if extra:
                name, kind = extra; member = tarfile.TarInfo(name); member.mode = 0o644
                if kind in {"symlink", "hardlink"}:
                    member.type = tarfile.SYMTYPE if kind == "symlink" else tarfile.LNKTYPE; member.linkname = "src.txt"
                    archive.addfile(member)
                else:
                    member.size = 1; archive.addfile(member, io.BytesIO(b"x"))


if __name__ == "__main__":
    unittest.main()
