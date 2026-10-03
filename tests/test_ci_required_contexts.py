"""Source/FS adversarial variants for proposed context binding, not protection."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from tools import verify_ci_required_contexts as gate

ROOT = Path(__file__).resolve().parents[1]


class RequiredContextSourceTests(unittest.TestCase):
    def setUp(self):
        self.catalog = json.loads((ROOT / gate.CONTRACT).read_text())
        self.texts = {p: (ROOT / p).read_text() for p in self.catalog["workflows"]}

    def refuse(self, catalog=None, texts=None):
        with self.assertRaises(ValueError):
            gate.check(self.catalog if catalog is None else catalog, self.texts if texts is None else texts)

    def private_source(self, directory):
        root = Path(directory)
        (root / "contracts").mkdir()
        shutil.copyfile(ROOT / gate.CONTRACT, root / gate.CONTRACT)
        shutil.copytree(ROOT / ".github/workflows", root / ".github/workflows")
        return root

    def test_actual_closed_catalog_has_51_unique_contexts_and_no_execution_authority(self):
        result = gate.validate(ROOT)
        self.assertEqual((result["workflows"], result["jobs"], result["unique_contexts"]), (27, 47, 51))
        self.assertEqual((result["repository_source_contexts"], result["availability_diagnostic_contexts"]), (48, 3))
        for key in ("settings_applied", "hosted_names_observed", "G0_closed", "production_ready"):
            self.assertIs(result[key], False)

    def test_duplicate_cross_workflow_names_and_old_ambiguous_names_refuse(self):
        for path in self.texts:
            text = self.texts[path]
            first = next(line for line in text.splitlines() if line.startswith("    name:"))
            for wrong in ("    name: exact-head", "    name: ci / rust", "    name: qualify"):
                if first == wrong: continue
                texts = dict(self.texts); texts[path] = text.replace(first, wrong, 1)
                with self.subTest(path=path, wrong=wrong): self.refuse(texts=texts)

    def test_missing_duplicate_or_misplaced_display_name_refuse(self):
        path = ".github/workflows/ci.yml"; original = self.texts[path]
        line = "    name: ci / repository-contracts\n"
        for replacement in ("", line + line, "    runs-on: ubuntu-24.04\n" + line):
            texts = dict(self.texts); texts[path] = original.replace(line, replacement, 1)
            self.refuse(texts=texts)

    def test_original_job_id_and_job_catalog_must_match(self):
        path = ".github/workflows/ci.yml"
        for before, after in (("  rust:\n", "  rust-renamed:\n"),
                              ("  rust:\n", "  repository-contracts:\n")):
            texts = dict(self.texts); texts[path] = texts[path].replace(before, after, 1)
            self.refuse(texts=texts)
        value = copy.deepcopy(self.catalog); del value["workflows"][path]["jobs"]["rust"]
        self.refuse(catalog=value)

    def test_matrix_expression_lane_order_and_distinct_display_lane_refuse(self):
        path = ".github/workflows/authenticated-update-readback.yml"
        for before, after in ((gate.MATRIX_EXPRESSION, gate.MATRIX_EXPRESSION.replace('["head","prospective-merge"]', '["head"]')),
                              (gate.MATRIX_EXPRESSION, gate.MATRIX_EXPRESSION.replace('["head","prospective-merge"]', '["prospective-merge","head"]')),
                              (" / ${{ matrix.object }}\n", " / head\n"),
                              (" / ${{ matrix.object }}\n", " / ${{ github.sha }}\n")):
            texts = dict(self.texts); texts[path] = texts[path].replace(before, after, 1)
            self.refuse(texts=texts)

    def test_runs_guards_conditions_timeouts_and_flags_remain_digest_bound(self):
        cases = [(".github/workflows/ci.yml", "set -euo pipefail", "set -e"),
                 (".github/workflows/ci.yml", "python3 -B tools/verify_ci_source_identity.py", "true"),
                 (".github/workflows/ci.yml", "    if: github.event_name == 'pull_request'", "    if: false"),
                 (".github/workflows/servo-exact-pin.yml", "timeout-minutes: 300", "timeout-minutes: 1"),
                 (".github/workflows/ci.yml", "--locked", "--offline")]
        for path, before, after in cases:
            with self.subTest(path=path, before=before):
                self.assertIn(before, self.texts[path]); texts = dict(self.texts)
                texts[path] = texts[path].replace(before, after, 1); self.refuse(texts=texts)

    def test_catalog_missing_extra_and_unknown_fields_refuse(self):
        path = ".github/workflows/ci.yml"
        variants = []
        missing = copy.deepcopy(self.catalog); del missing["workflows"][path]; variants.append(missing)
        extra = copy.deepcopy(self.catalog); extra["workflows"][".github/workflows/new.yml"] = extra["workflows"][path]; variants.append(extra)
        for selected in (lambda c: c, lambda c: c["workflows"][path], lambda c: c["workflows"][path]["jobs"]["rust"]):
            value = copy.deepcopy(self.catalog); selected(value)["authority"] = False; variants.append(value)
        missing = copy.deepcopy(self.catalog); del missing["workflows"][path]["body_without_job_display_names_sha256"]; variants.append(missing)
        for value in variants: self.refuse(catalog=value)

    def test_catalog_context_application_and_integer_boolean_aliases_refuse(self):
        for wrong in (-1, 0, True, 15368.0, "15368"):
            value = copy.deepcopy(self.catalog); value["profile"]["expected_application"]["app_id"] = wrong
            self.refuse(catalog=value)
        value = copy.deepcopy(self.catalog); value["profile"]["expected_application"]["slug"] = "unrelated-app"
        self.refuse(catalog=value)
        for group in ("administration", "claims"):
            for key, original in self.catalog["profile"][group].items():
                if type(original) is not bool: continue
                for wrong in (not original, int(original), str(original).lower()):
                    value = copy.deepcopy(self.catalog); value["profile"][group][key] = wrong
                    with self.subTest(group=group, key=key, wrong=wrong): self.refuse(catalog=value)

    def test_forged_context_rows_matrix_flag_and_digest_refuse(self):
        path = ".github/workflows/authenticated-update-readback.yml"
        for key, wrong in (("contexts", ["actual-host-corpus"]), ("matrix_object", False),
                           ("kind", "availability_diagnostic")):
            value = copy.deepcopy(self.catalog); value["workflows"][path]["jobs"]["actual-host-corpus"][key] = wrong
            self.refuse(catalog=value)
        value = copy.deepcopy(self.catalog); value["workflows"][path]["body_without_job_display_names_sha256"] = "0" * 64
        self.refuse(catalog=value)

    def test_unlisted_yaml_files_and_missing_workflow_refuse_real_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.private_source(directory); extra = root / ".github/workflows/unlisted.yaml"
            extra.write_text("jobs: {}\n")
            with self.assertRaises(ValueError): gate.validate(root)
            extra.unlink(); (root / ".github/workflows/ci.yml").unlink()
            with self.assertRaises(ValueError): gate.validate(root)

    def test_real_duplicate_json_keys_and_bounded_source_refuse(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.private_source(directory); p = root / gate.CONTRACT
            p.write_text('{"schema":"one","schema":"two"}')
            with self.assertRaises(ValueError): gate.validate(root)
            p.write_bytes(b" " * (gate.MAX_FILE_BYTES + 1))
            with self.assertRaises(ValueError): gate.validate(root)

    def test_real_symlink_and_hardlink_cannot_supply_source_files(self):
        for relative in (gate.CONTRACT, ".github/workflows/ci.yml"):
            for shape in ("symlink", "hardlink"):
                with self.subTest(relative=relative, shape=shape), tempfile.TemporaryDirectory() as directory:
                    root = self.private_source(directory); p = root / relative; other = root / "same-bytes"
                    p.rename(other)
                    if shape == "symlink": p.symlink_to(other)
                    else: os.link(other, p)
                    with self.assertRaises((OSError, ValueError)): gate.validate(root)

    def test_same_byte_replacement_during_final_check_refuses_and_closes_all_readers(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.private_source(directory); p = root / ".github/workflows/ci.yml"
            old_check = gate.check; before = len(list(Path("/proc/self/fd").iterdir()))
            def replaced(catalog, texts):
                result = old_check(catalog, texts); replacement = p.with_suffix(".replacement")
                replacement.write_bytes(p.read_bytes()); replacement.replace(p); return result
            with patch.object(gate, "check", replaced):
                with self.assertRaises(ValueError): gate.validate(root)
            self.assertEqual(len(list(Path("/proc/self/fd").iterdir())), before)

    def test_finite_source_shape_refuses_tabs_crlf_duplicate_jobs_and_nontext(self):
        path = ".github/workflows/ci.yml"
        for value in (self.texts[path].replace("\n", "\r\n"), self.texts[path] + "\t", 1,
                      self.texts[path].replace("\njobs:\n", "\njobs:\njobs:\n")):
            texts = dict(self.texts); texts[path] = value; self.refuse(texts=texts)

    def test_in_check_added_unlisted_workflow_refuses_and_closes_all_readers(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.private_source(directory); old_check = gate.check
            before = len(list(Path("/proc/self/fd").iterdir()))
            def added(catalog, texts):
                result = old_check(catalog, texts)
                (root / ".github/workflows/unreviewed.yml").write_text("jobs: {}\n")
                return result
            with patch.object(gate, "check", added):
                with self.assertRaisesRegex(ValueError, "workflow directory changed"):
                    gate.validate(root)
            self.assertEqual(len(list(Path("/proc/self/fd").iterdir())), before)

    def test_in_check_removed_visible_non_yaml_entry_refuses(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.private_source(directory); extra = root / ".github/workflows/source-note"
            extra.write_text("visible entries count even without a YAML suffix\n")
            old_check = gate.check
            def removed(catalog, texts):
                result = old_check(catalog, texts); extra.unlink(); return result
            with patch.object(gate, "check", removed):
                with self.assertRaisesRegex(ValueError, "workflow directory changed"):
                    gate.validate(root)

    def test_in_check_removed_workflow_refuses_and_closes_all_readers(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.private_source(directory); old_check = gate.check
            before = len(list(Path("/proc/self/fd").iterdir()))
            def removed(catalog, texts):
                result = old_check(catalog, texts)
                (root / ".github/workflows/ci.yml").unlink(); return result
            with patch.object(gate, "check", removed):
                with self.assertRaises((OSError, ValueError)): gate.validate(root)
            self.assertEqual(len(list(Path("/proc/self/fd").iterdir())), before)

    def test_directory_replacement_after_leaf_checks_refuses_real_filesystem(self):
        # Mutate at the final inventory call, after all original leaf identity
        # checks, so this exercises the added directory check itself.
        for shape in ("real-directory", "symlink"):
            with self.subTest(shape=shape), tempfile.TemporaryDirectory() as directory:
                root = self.private_source(directory); workflow_dir = root / ".github/workflows"
                old_snapshot = gate.workflow_directory_snapshot; calls = []
                before = len(list(Path("/proc/self/fd").iterdir()))
                def replaced(path):
                    calls.append(path)
                    if len(calls) == 2:
                        saved = root / ".github/original-workflows"; workflow_dir.rename(saved)
                        if shape == "symlink": workflow_dir.symlink_to(saved, target_is_directory=True)
                        else: shutil.copytree(saved, workflow_dir)
                    return old_snapshot(path)
                with patch.object(gate, "workflow_directory_snapshot", replaced):
                    with self.assertRaisesRegex(ValueError, "workflow (?:directory changed|inventory requires a real directory)"):
                        gate.validate(root)
                self.assertEqual(len(calls), 2)
                self.assertEqual(len(list(Path("/proc/self/fd").iterdir())), before)

    def test_all_visible_entries_are_bounded_with_early_stop(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.private_source(directory); workflow_dir = root / ".github/workflows"
            for i in range(20): (workflow_dir / ("non-yaml-" + str(i))).write_text("entry\n")
            original_scandir = gate.os.scandir; advances = []; closed = []
            class CountedEntries:
                def __enter__(self):
                    self.entries = original_scandir(workflow_dir); self.entries.__enter__(); return self
                def __exit__(self, *args):
                    try: return self.entries.__exit__(*args)
                    finally: closed.append(True)
                def __iter__(self): return self
                def __next__(self):
                    entry = next(self.entries); advances.append(entry.name); return entry
            before = len(list(Path("/proc/self/fd").iterdir()))
            with patch.object(gate.os, "scandir", lambda path: CountedEntries()):
                with self.assertRaisesRegex(ValueError, "visible-entry bound"): gate.validate(root)
            self.assertEqual(len(advances), gate.MAX_DIRECTORY_ENTRIES + 1)
            self.assertEqual(closed, [True])
            self.assertEqual(len(list(Path("/proc/self/fd").iterdir())), before)

    def test_enumeration_itself_detects_actual_directory_entry_change(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.private_source(directory); workflow_dir = root / ".github/workflows"
            original_scandir = gate.os.scandir
            class AddedDuringIteration:
                def __enter__(self):
                    self.entries = original_scandir(workflow_dir); self.entries.__enter__(); return self
                def __exit__(self, *args): return self.entries.__exit__(*args)
                def __iter__(self): return self
                def __next__(self):
                    entry = next(self.entries)
                    (workflow_dir / "in-enumeration-note").write_text("changed directory\n")
                    return entry
            with patch.object(gate.os, "scandir", lambda path: AddedDuringIteration()):
                with self.assertRaisesRegex(ValueError, "directory changed during inventory enumeration"):
                    gate.validate(root)

    def test_visible_entry_bound_is_closed_and_rejects_numeric_aliases(self):
        for wrong in (29, 27, True, 28.0, "28"):
            value = copy.deepcopy(self.catalog)
            value["profile"]["limits"]["directory_visible_entries"] = wrong
            with self.subTest(wrong=wrong): self.refuse(catalog=value)


if __name__ == "__main__":
    unittest.main()
