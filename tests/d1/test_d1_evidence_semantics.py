"""Complete, rehashed decoder fixtures; these never qualify disks or guests."""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_artifact_evidence import d1_fixture, d2i_fixture, bind, write, evidence, d1, d2i
import d1_evidence_semantics as semantics


class D1SemanticEvidenceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.receipt = d1_fixture(self.root)

    def document(self, name):
        return evidence.load(self.root / name)

    def rebind(self):
        bind(self.root, self.receipt, d1.RECEIPT_PATH.as_posix(), sized=False)

    def replace(self, name, document, field=None):
        write(self.root, name, document)
        if field is not None:
            self.receipt[field] = document
        self.rebind()

    def test_complete_metadata_fixture_passes_without_absent_disk_payloads(self):
        self.assertFalse((self.root / "builds/build-a/trillionnium-d1.ext4").exists())
        self.assertEqual(d1.verify_artifact(self.root)["status"], "PASS")
        semantics.validate_contract()

    def test_fixture_separation_and_repro_scope_promotions_or_type_aliases_fail(self):
        for section in ("product_fixture_separation", "reproducibility_scope"):
            original = copy.deepcopy(self.receipt[section])
            for field, value in original.items():
                alternatives = (not value, int(value)) if type(value) is bool else ("production", None)
                for hostile in alternatives:
                    with self.subTest(section=section, field=field, hostile=hostile):
                        self.receipt[section] = {**original, field: hostile}
                        self.rebind()
                        with self.assertRaisesRegex(ValueError, section): d1.verify_artifact(self.root)
            for operation in ("omit", "extra"):
                self.receipt[section] = copy.deepcopy(original)
                if operation == "omit": self.receipt[section].pop(next(iter(original)))
                else: self.receipt[section]["production_ready"] = True
                self.rebind()
                with self.assertRaisesRegex(ValueError, section): d1.verify_artifact(self.root)
            self.receipt[section] = original

    def test_pipeline_failed_exit_missing_stage_or_claim_cannot_keep_overall_pass(self):
        baseline = self.document("pipeline/pipeline-result.json")
        for mutation in ("failed", "float_exit", "true_exit", "missing", "extra", "failed_stage", "authority", "reverse_time"):
            hostile = copy.deepcopy(baseline)
            if mutation == "failed": hostile["stages"]["build_first"] = {"exit_code": 1, "status": "FAIL"}
            elif mutation == "float_exit": hostile["stages"]["qemu_acceptance"]["exit_code"] = 0.0
            elif mutation == "true_exit": hostile["stages"]["qemu_acceptance"]["exit_code"] = False
            elif mutation == "missing": del hostile["stages"]["build_second"]
            elif mutation == "extra": hostile["stages"]["invented"] = {"status": "PASS", "exit_code": 0}
            elif mutation == "failed_stage": hostile["failed_stage"] = "build_first"
            elif mutation == "authority": hostile["authority"]["release_qualified"] = True
            else: hostile["finished_unix"] = 0
            self.replace("pipeline/pipeline-result.json", hostile, "pipeline")
            with self.subTest(mutation=mutation), self.assertRaisesRegex(ValueError, "pipeline"):
                d1.verify_artifact(self.root)

    def test_fixture_free_flags_cannot_override_carried_graph_or_string_contradictions(self):
        paths = {
            "evidence/product-cargo-tree.txt": b"hepta-agent-portd v0.1.0\nhepta-browser-codec v0.1.0\n",
            "evidence/qualification-cargo-tree.txt": b"hepta-agent-portd v0.1.0\n",
            "raw-evidence/product-daemon.strings": b"agent_port_ready\n",
            "raw-evidence/qualification-fixture.strings": b"no qualification handler markers\n",
        }
        for name, payload in paths.items():
            path = self.root / name; original = path.read_bytes(); path.write_bytes(payload); self.rebind()
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "graph|strings"):
                d1.verify_artifact(self.root)
            path.write_bytes(original)

    def test_binary_digest_path_size_and_types_bind_both_rootfs_manifests(self):
        baseline = self.document("evidence/binary-digests.json")
        for key in ("product", "qualification"):
            for field, value in (("sha256", "f" * 64), ("bytes", baseline[key]["bytes"] + 1),
                ("bytes", float(baseline[key]["bytes"])), ("bytes", True), ("path", "target/release/other")):
                hostile = copy.deepcopy(baseline); hostile[key][field] = value
                self.replace("evidence/binary-digests.json", hostile)
                with self.subTest(binary=key, field=field, value=value), self.assertRaises(ValueError):
                    d1.verify_artifact(self.root)

    def test_rootfs_digest_count_path_duplication_and_actual_binary_metadata_fail(self):
        name = "builds/build-a/rootfs-content-manifest.json"
        baseline = self.document(name)
        for mutation in ("hash", "float_count", "duplicate", "escaping", "missing_binary", "wrong_binary", "unsafe_mode"):
            hostile = copy.deepcopy(baseline)
            if mutation == "hash": hostile["entries_sha256"] = "f" * 64
            elif mutation == "float_count": hostile["entry_count"] = float(hostile["entry_count"])
            elif mutation == "duplicate": hostile["entries"].append(copy.deepcopy(hostile["entries"][0]))
            elif mutation == "escaping": hostile["entries"][0]["path"] = "./../outside"
            elif mutation == "missing_binary": hostile["entries"][0]["path"] = "./usr/libexec/other"
            elif mutation == "wrong_binary": hostile["entries"][0]["sha256"] = "f" * 64
            else: hostile["entries"][0]["mode"] = "4755"
            if mutation not in {"hash", "float_count"}:
                hostile["entry_count"] = len(hostile["entries"])
                hostile["entries_sha256"] = hashlib.sha256(semantics.canonical(hostile["entries"])).hexdigest()
            # Rebind the build's own manifest declaration too; the rejection must
            # come from path/binary/count semantics, not just an old file digest.
            write(self.root, name, hostile)
            build = self.document("builds/build-a/build-result.json")
            build["rootfs_manifest"].update(sha256=evidence.digest(self.root / name),
                entries=hostile["entry_count"], entries_sha256=hostile["entries_sha256"])
            self.replace("builds/build-a/build-result.json", build)
            with self.subTest(mutation=mutation), self.assertRaises(ValueError): d1.verify_artifact(self.root)

    def test_reproducible_true_cannot_override_divergent_sha_lengths_or_diff(self):
        baseline = self.document("reproducibility/reproducibility-result.json")
        for mutation in ("disk_sha", "disk_bytes", "disk_float_bytes", "carried_manifest_sha", "equal", "difference", "claim", "extra"):
            hostile = copy.deepcopy(baseline)
            if mutation == "disk_sha": hostile["artifact_comparisons"]["trillionnium-d1.ext4"]["second_sha256"] = "f" * 64
            elif mutation == "disk_bytes": hostile["artifact_comparisons"]["trillionnium-d1.ext4"]["second_bytes"] += 1
            elif mutation == "disk_float_bytes": hostile["artifact_comparisons"]["trillionnium-d1.ext4"]["second_bytes"] = 42.0
            elif mutation == "carried_manifest_sha": hostile["artifact_comparisons"]["rootfs-content-manifest.json"]["first_sha256"] = "f" * 64
            elif mutation == "equal": hostile["artifact_comparisons"]["vmlinuz"]["equal"] = 1
            elif mutation == "difference": hostile["rootfs_manifest_diff"]["changed_count"] = 1
            elif mutation == "claim": hostile["claims"]["product_ready"] = True
            else: hostile["artifact_comparisons"]["unknown"] = {}
            self.replace("reproducibility/reproducibility-result.json", hostile, "reproducibility")
            with self.subTest(mutation=mutation), self.assertRaisesRegex(ValueError, "artifact|reproducibility|comparison"):
                d1.verify_artifact(self.root)

    def test_boot_acceptance_digest_exit_and_tested_image_cannot_be_detached(self):
        baseline = self.document("qemu/boot-result.json")
        for field, value in (("guest_acceptance_sha256", "f" * 64), ("pre_boot_image_sha256", "f" * 64),
            ("qemu_exit_status", False), ("qemu_exit_status", 0.0), ("qemu_exit_status", 1), ("network", "user")):
            hostile = copy.deepcopy(baseline); hostile[field] = value
            self.replace("qemu/boot-result.json", hostile, "boot")
            with self.subTest(field=field, value=value), self.assertRaisesRegex(ValueError, "boot"):
                d1.verify_artifact(self.root)

    def test_build_package_bytes_and_prepared_digest_are_actual_carried_bindings(self):
        lock = self.root / "builds/build-a/package-lock.tsv"
        lock.write_bytes(b"different-package\t2.0\tall\n")
        self.rebind()
        with self.assertRaisesRegex(ValueError, "actual build package bytes"):
            d1.verify_artifact(self.root)
        lock.write_bytes((self.root / "inputs/expected-package-lock.tsv").read_bytes())
        prepared = self.document("inputs/prepared-inputs.json"); prepared["source_date_epoch"] += 1
        self.replace("inputs/prepared-inputs.json", prepared)
        with self.assertRaisesRegex(ValueError, "prepared manifest"):
            d1.verify_artifact(self.root)

    def test_rebound_acceptance_pid1_service_agent_or_self_check_contradictions_fail(self):
        baseline = self.document("qemu/acceptance.json")
        original_boot = self.document("qemu/boot-result.json")
        for mutation in ("pid1", "service", "default_disabled", "unauthorized", "authorized", "recovery", "marker", "selfcheck"):
            hostile = copy.deepcopy(baseline)
            if mutation == "pid1": hostile["pid1"] = "bash"
            elif mutation == "service": hostile["dbus"] = "failed"
            elif mutation == "selfcheck": hostile["agent_port"]["product_self_check_sha256"] = "f" * 64
            else:
                field = {"default_disabled": "default_disabled", "unauthorized": "unauthorized_peer_denied",
                    "authorized": "authorized_request_completed", "recovery": "connection_kill_recovered",
                    "marker": "marker_created_at_runtime_only"}[mutation]
                hostile["agent_port"][field] = False
            path = write(self.root, "qemu/acceptance.json", hostile)
            self.receipt["acceptance"] = hostile
            boot = {**original_boot, "guest_acceptance_sha256": evidence.digest(path)}
            write(self.root, "qemu/boot-result.json", boot); self.receipt["boot"] = boot; self.rebind()
            with self.subTest(mutation=mutation), self.assertRaisesRegex(ValueError, "acceptance"):
                d1.verify_artifact(self.root)

    def test_nested_d2i_reader_refuses_semantic_escalation_with_all_outer_hashes_rebound(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); outer = d2i_fixture(root)
            receipt = evidence.load(root / "d1" / d1.RECEIPT_PATH)
            receipt["product_fixture_separation"]["product_handler_connected"] = True
            bind(root / "d1", receipt, d1.RECEIPT_PATH.as_posix(), sized=False)
            outer["d1_receipt_sha256"] = evidence.digest(root / "d1" / d1.RECEIPT_PATH)
            bind(root, outer, d2i.RECEIPT, sized=True)
            with self.assertRaisesRegex(ValueError, "product_fixture_separation"):
                d2i.verify_artifact(root)

    def test_complete_readback_detects_predecessor_rewrite_during_last_open(self):
        first = write(self.root, "first.json", {"value": 1})
        last = write(self.root, "last.json", {"value": 2})
        snapshot = semantics._Snapshot(self.root, {name: evidence.digest(path)
            for name, path in (("first.json", first), ("last.json", last))})
        snapshot.document("first.json"); snapshot.document("last.json")
        real_open = semantics.open_managed_file
        def rewrite(path):
            descriptor = real_open(path)
            if path == last:
                first.write_bytes(first.read_bytes() + b" ")
            return descriptor
        with patch.object(semantics, "open_managed_file", side_effect=rewrite):
            with self.assertRaisesRegex(ValueError, "complete readback changed"):
                snapshot.finish()

    def test_snapshot_rejects_actual_alias_ancestor_and_hardlinked_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); actual = root / "actual"; actual.mkdir(); case = actual / "case"; case.mkdir()
            path = write(case, "fact.json", {"source_fixture_only": True})
            alias = root / "alias"; alias.symlink_to(actual, target_is_directory=True)
            with self.assertRaises(ValueError):
                semantics._Snapshot(alias / "case", {"fact.json": evidence.digest(path)}).document("fact.json")
            digest = evidence.digest(path); os.link(path, case / "other.json")
            with self.assertRaises(ValueError): semantics._Snapshot(case, {"fact.json": digest}).document("fact.json")

    def test_contract_cannot_promote_absent_payload_or_installed_qualification(self):
        path = Path(semantics.__file__).parents[1] / "contracts/d1-portable-evidence.v1.json"
        baseline = json.loads(path.read_text())
        for field in ("default_product_activation", "execute_artifact_payloads", "full_disk_rehash_claimed",
            "cross_run_identity_claimed", "hermetic_build_claimed", "installed_qualification_created_by_reader", "production_ready"):
            hostile = copy.deepcopy(baseline); hostile[field] = True
            with self.subTest(field=field), self.assertRaises(ValueError): semantics.validate_contract(hostile)
        hostile = copy.deepcopy(baseline); hostile["absent_payloads_metadata_bound_only"].remove("trillionnium-d1.ext4")
        with self.assertRaises(ValueError): semantics.validate_contract(hostile)

    def rebind_rootfs(self, entries):
        """Rebind both carried manifests and every related producer record."""
        manifest = {"schema": "trillionnium.desktop.d1-rootfs-manifest.v1", "entries": entries,
            "entry_count": len(entries), "entries_sha256": hashlib.sha256(semantics.canonical(entries)).hexdigest()}
        for build in ("build-a", "build-b"):
            prefix = f"builds/{build}/"
            path = write(self.root, prefix + "rootfs-content-manifest.json", manifest)
            result = self.document(prefix + "build-result.json")
            result["rootfs_manifest"] = {"path": "rootfs-content-manifest.json", "entries": len(entries),
                "entries_sha256": manifest["entries_sha256"], "sha256": evidence.digest(path)}
            write(self.root, prefix + "build-result.json", result)
        path = self.root / "builds/build-a/rootfs-content-manifest.json"
        repro = self.document("reproducibility/reproducibility-result.json")
        repro["artifact_comparisons"]["rootfs-content-manifest.json"] = {"equal": True,
            "first_sha256": evidence.digest(path), "second_sha256": evidence.digest(path),
            "first_bytes": path.stat().st_size, "second_bytes": path.stat().st_size}
        repro["rootfs_manifest_diff"].update(first_entry_count=len(entries), second_entry_count=len(entries))
        self.replace("reproducibility/reproducibility-result.json", repro, "reproducibility")

    def test_complete_rebound_root_and_directory_parent_contradictions_fail(self):
        original = self.document("builds/build-a/rootfs-content-manifest.json")["entries"]
        for mutation in ("missing_root", "root_file", "missing_parent", "missing_ancestor", "parent_file", "parent_symlink"):
            entries = copy.deepcopy(original)
            target = "." if mutation.startswith("root") or mutation == "missing_root" else (
                "./usr" if mutation == "missing_ancestor" else "./usr/libexec")
            if mutation.startswith("missing"):
                entries = [item for item in entries if item["path"] != target]
            else:
                item = next(item for item in entries if item["path"] == target)
                if mutation.endswith("file"):
                    item.update(type="file", sha256="c" * 64)
                else:
                    item.update(type="symlink", target="elsewhere")
            self.rebind_rootfs(entries)
            with self.subTest(mutation=mutation), self.assertRaisesRegex(ValueError, "root directory|directory parent"):
                d1.verify_artifact(self.root)

    def test_complete_rebound_hardlink_cycles_noncanonical_heads_or_impossible_count_fail(self):
        original = self.document("builds/build-a/rootfs-content-manifest.json")["entries"]
        pair = [{**copy.deepcopy(original[0]), "path": path, "nlink": 3, "hardlink_head": "./usr/libexec/link-a"}
            for path in ("./usr/libexec/link-a", "./usr/libexec/link-z")]
        # Two carried members can have a third inode link outside the root.
        self.rebind_rootfs(copy.deepcopy(original) + copy.deepcopy(pair))
        self.assertEqual(d1.verify_artifact(self.root)["status"], "PASS")
        for mutation in ("cycle", "noncanonical", "too_many", "different_head", "missing_head", "single_link_head"):
            links = copy.deepcopy(pair)
            if mutation == "cycle":
                links[0]["hardlink_head"] = links[1]["path"]
                links[1]["hardlink_head"] = links[0]["path"]
            elif mutation == "noncanonical":
                for item in links: item["hardlink_head"] = links[1]["path"]
            elif mutation == "too_many":
                for item in links: item["nlink"] = 2
                links.append({**copy.deepcopy(links[0]), "path": "./usr/libexec/link-b"})
            elif mutation == "different_head":
                links[1]["hardlink_head"] = links[1]["path"]
                links[0]["hardlink_head"] = links[1]["path"]
            elif mutation == "missing_head":
                links[0]["hardlink_head"] = "./usr/libexec/absent"
            else:
                links[0]["nlink"] = 1
                links[0].pop("hardlink_head")
            self.rebind_rootfs(copy.deepcopy(original) + links)
            with self.subTest(mutation=mutation), self.assertRaisesRegex(ValueError, "hardlink"):
                d1.verify_artifact(self.root)

    def test_actual_producer_partial_hardlink_inventory_obeys_reader_structure(self):
        import sys
        sys.path.insert(0, str(Path(semantics.__file__).parent))
        import d1_rootfs_manifest as producer
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary); root = directory / "carried"; root.mkdir()
            first = root / "a"; first.write_bytes(b"ordinary host manifest fixture only")
            os.link(first, root / "z"); os.link(first, directory / "outside-carried-root")
            manifest = producer.build_manifest(root)
            parsed = semantics.rootfs(manifest)
            self.assertEqual(parsed["."]["type"], "directory")
            self.assertEqual(parsed["./a"]["nlink"], 3)
            self.assertEqual(parsed["./z"]["hardlink_head"], "./a")
            self.assertEqual(len([item for item in parsed.values() if "hardlink_head" in item]), 2)

    def test_rootfs_contract_is_closed_and_cannot_claim_complete_inode_or_payload_custody(self):
        baseline = json.loads((Path(semantics.__file__).parents[1] / "contracts/d1-portable-evidence.v1.json").read_text())
        for mutation in ("extra", "missing", "payload", "inventory", "integer_false", "count_equals"):
            hostile = copy.deepcopy(baseline); scope = hostile["rootfs_manifest_consistency"]
            if mutation == "extra": scope["production_ready"] = False
            elif mutation == "missing": scope.pop("parents")
            elif mutation == "payload": scope["actual_rootfs_payload_inspected"] = True
            elif mutation == "inventory": scope["complete_inode_link_inventory_claimed"] = True
            elif mutation == "integer_false": scope["complete_inode_link_inventory_claimed"] = 0
            else: scope["hardlink_member_count"] = "exactly nlink"
            with self.subTest(mutation=mutation), self.assertRaises(ValueError): semantics.validate_contract(hostile)


    def test_complete_rebound_symlink_byte_length_and_empty_target_fail(self):
        original = self.document("builds/build-a/rootfs-content-manifest.json")["entries"]
        target = "目标/路径"
        link = {**copy.deepcopy(original[0]), "path": "./usr/libexec/symlink",
            "type": "symlink", "mode": "0777", "nlink": 1,
            "size": len(target.encode("utf-8")), "target": target}
        link.pop("sha256")
        self.rebind_rootfs(copy.deepcopy(original) + [copy.deepcopy(link)])
        self.assertEqual(d1.verify_artifact(self.root)["status"], "PASS")
        for mutation in ("byte_mismatch", "character_count", "empty", "unrepresentable"):
            hostile = copy.deepcopy(link)
            if mutation == "byte_mismatch": hostile["size"] += 1
            elif mutation == "character_count": hostile["size"] = len(target)
            elif mutation == "empty": hostile.update(target="", size=0)
            else: hostile.update(target="\ud800", size=1)
            self.rebind_rootfs(copy.deepcopy(original) + [hostile])
            with self.subTest(mutation=mutation), self.assertRaisesRegex(ValueError, "symlink"):
                d1.verify_artifact(self.root)

    def test_actual_producer_symlink_unicode_and_non_utf8_bytes_match_size(self):
        import sys
        sys.path.insert(0, str(Path(semantics.__file__).parent))
        import d1_rootfs_manifest as producer
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            targets = {"unicode": "目标/路径".encode("utf-8"), "raw-byte": b"\x80/not-present"}
            for name, target in targets.items():
                os.symlink(target, os.fsencode(root / name))
            parsed = semantics.rootfs(producer.build_manifest(root))
            for name, target in targets.items():
                item = parsed["./" + name]
                self.assertEqual(item["size"], (root / name).lstat().st_size)
                self.assertEqual(item["size"], len(target))
                self.assertEqual(item["target"].encode("utf-8", "surrogateescape"), target)


if __name__ == "__main__":
    unittest.main()
