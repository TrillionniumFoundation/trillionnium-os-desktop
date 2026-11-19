#!/usr/bin/env python3
"""Control current-source joins using recorded metadata, with no SDK or APK actions."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('pocket4_complete_source_refresh', ROOT / 'verify_refresh.py')
refresh = importlib.util.module_from_spec(spec)
spec.loader.exec_module(refresh)


class CurrentSourceSelection(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index = json.loads(refresh.read('SOURCE-REFRESH.json'))
        cls.previous = json.loads(refresh.read(cls.index['previous_united_refresh_index']['path']))
        cls.selected = refresh.current_szzc_source_inputs(cls.index, cls.previous)

    def test_actual_four_outputs_remain_source_only(self):
        self.assertEqual(self.selected['current_outputs_reconstructed'], 4)
        self.assertEqual(self.selected['native_inventory_diagnostic']['native_member_count'], 118)
        self.assertEqual(self.selected['native_inventory_diagnostic']['cross_ABI_member_count'], 4)
        self.assertEqual(self.selected['native_inventory_diagnostic']['selected_arm64_directory_cross_ABI_members'], 2)
        self.assertIs(self.selected['native_runtime_blocker_retained'], True)
        self.assertIs(self.selected['native_compatibility_qualified'], False)

    def test_old_registry_cannot_remain_current(self):
        index = copy.deepcopy(self.index)
        index['current_registry'] = self.previous['current_registry']
        with self.assertRaisesRegex(ValueError, 'actually selects the SZZC successor'):
            refresh.current_szzc_source_inputs(index, self.previous)

    def test_old_business_plan_cannot_remain_current(self):
        index = copy.deepcopy(self.index)
        index['current_business_preflight'] = self.previous['current_business_preflight']
        with self.assertRaisesRegex(ValueError, 'actually selects the SZZC successor'):
            refresh.current_szzc_source_inputs(index, self.previous)

    def test_current_four_provider_cohort_cannot_drift(self):
        index = copy.deepcopy(self.index)
        index['current_system_provider_cohort']['sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'exact verified predecessor cohort'):
            refresh.current_szzc_source_inputs(index, self.previous)

    def test_four_original_cross_abi_members_cannot_be_omitted(self):
        selected = copy.deepcopy(self.selected)
        selected['native_inventory_diagnostic']['members'].pop()
        with self.assertRaisesRegex(ValueError, 'four exact original cross-ABI members'):
            refresh.current_szzc_native_inventory(self.index, selected)

    def test_native_inventory_is_for_the_same_complete_apk(self):
        selected = copy.deepcopy(self.selected)
        selected['selected_source_identity']['APK']['sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'same unmodified APK'):
            refresh.current_szzc_native_inventory(self.index, selected)

    def test_native_blocker_cannot_be_promoted_to_acceptance(self):
        index = copy.deepcopy(self.index)
        index['current_SZZC_native_runtime_blocker']['native_compatibility_qualified'] = True
        with self.assertRaisesRegex(ValueError, 'exact unresolved native inventory blocker'):
            refresh.current_szzc_native_inventory(index, self.selected)

    def test_ordinary_oversized_member_is_rejected_before_body_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with (root / 'unexpected.json').open('wb') as stream:
                stream.truncate(2 * 1024 * 1024 + 1)
            with patch.object(refresh, 'ROOT', root), patch.object(Path, 'read_bytes') as read_body:
                with self.assertRaisesRegex(ValueError, 'bounded metadata member before read'):
                    refresh.read('unexpected.json')
                read_body.assert_not_called()

    def test_receipt_exception_requires_its_exact_size_before_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / 'szzc/inputs/source-receipt.json'
            path.parent.mkdir(parents=True)
            path.write_bytes(b'{}\n')
            with patch.object(refresh, 'ROOT', root), patch.object(Path, 'read_bytes') as read_body:
                with self.assertRaisesRegex(ValueError, 'exact complete SZZC source receipt size before read'):
                    refresh.read('szzc/inputs/source-receipt.json')
                read_body.assert_not_called()

    def test_receipt_exception_requires_complete_original_sha(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / 'szzc/inputs/source-receipt.json'
            path.parent.mkdir(parents=True)
            with path.open('wb') as stream:
                stream.truncate(4231750)
            with patch.object(refresh, 'ROOT', root):
                with self.assertRaisesRegex(ValueError, 'exact actual complete SZZC receipt'):
                    refresh.read('szzc/inputs/source-receipt.json')


if __name__ == '__main__':
    unittest.main(verbosity=2)
