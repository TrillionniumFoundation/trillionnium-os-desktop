"""Mutation tests for the managed store's source-quality gate, not runtime proof."""
from __future__ import annotations
import copy
import json
import unittest
from tests.test_verify_receipt_journal import ROOT, VALIDATOR


class ManagedReceiptAuditTests(unittest.TestCase):
    def setUp(self):
        self.inputs = {key: (ROOT / path).read_text(encoding='utf-8')
                       for key, path in VALIDATOR.MANAGED_INPUTS.items()}
        VALIDATOR.ERRORS.clear()

    def rejects(self, key, old, new):
        inputs = self.inputs.copy()
        self.assertIn(old, inputs[key])
        inputs[key] = inputs[key].replace(old, new, 1)
        VALIDATOR.ERRORS.clear()
        VALIDATOR.audit_managed_source(inputs)
        self.assertTrue(VALIDATOR.ERRORS, (key, old))

    def test_current_sources_and_contract_are_aligned(self):
        VALIDATOR.audit_managed_source(self.inputs)
        VALIDATOR.audit_contract(json.loads((ROOT/'contracts/receipt-journal.v1.json').read_text()))
        self.assertEqual(VALIDATOR.ERRORS, [])

    def test_missing_source_input_is_not_replaced_by_hidden_filesystem_reads(self):
        for key in self.inputs:
            with self.subTest(key=key):
                reduced=self.inputs.copy(); del reduced[key]
                VALIDATOR.ERRORS.clear(); VALIDATOR.audit_managed_source(reduced)
                self.assertTrue(VALIDATOR.ERRORS)

    def test_durability_and_lock_calls_cannot_be_replaced_with_comments(self):
        for old in ['next.file.sync_all()', 'fs::rename(&next.path, &final_path)',
                    'self.directory.sync_all()', 'lock_file(&directory)',
                    'validate_existing_path_identity(&entry.path())']:
            with self.subTest(old=old):
                self.rejects('managed', old, '/* '+old+' */ Ok(())')

    def test_publication_order_and_pending_strictness_are_mandatory(self):
        self.rejects('managed','next.file.sync_all()', 'self.directory.sync_all()')
        self.rejects('managed','OpenPolicy::STRICT, false', 'policy.journal, false')
        self.rejects('managed','!policy.complete_pending_rotation', 'false')
        self.rejects('managed','!report.records.is_empty()', 'false')
        self.rejects('managed','next.end_offset != SEGMENT_HEADER_LEN as u64', 'false')

    def test_head_identity_inventory_and_bounds_cannot_be_relaxed(self):
        for old in ['bytes != self.marker_bytes','paths.len() != self.segments',
                    '*name != segment_name(index + 1)','count >= MAX_CHAIN_SEGMENTS + 2']:
            with self.subTest(old=old): self.rejects('managed', old, 'false')

    def test_default_off_storage_and_live_service_wiring_are_required(self):
        self.rejects('storage','journal_present || predecessors_present','false')
        self.rejects('storage','ReceiptJournal::open_managed(', 'ignored(')
        self.rejects('service','storage::open_configured()', 'ignored()')
        self.rejects('service','rotate_quiescent_store(&mut state)?','ignored()')
        self.rejects('observer','self.journal.rotate_managed(now_unix_ms)?','ignored()')
        self.rejects('source','managed::reject_unmanaged_access(path.as_ref())?', 'ignored()')
        self.rejects('chain','managed::reject_unmanaged_access(path)?','ignored()')

    def test_runtime_regressions_cannot_be_replaced_by_comments(self):
        for key, name in [('disk_tests','malformed_pending_is_never_discarded_or_truncated'),
                          ('process_tests','managed_sigkill_preserves_dispatched_external_facts_and_never_replays'),
                          ('storage_tests','managed_storage_reopens_latest_head_and_reconciles_without_replaying')]:
            with self.subTest(key=key): self.rejects(key, 'fn '+name+'(', '// fn '+name+'(')

    def test_contract_types_bounds_and_claim_ceiling_are_exact(self):
        source=json.loads((ROOT/'contracts/receipt-journal.v1.json').read_text())
        for key, value in [('opt_in',1),('maximum_segments',True),('automatic_rotation_threshold_bytes',1),
                           ('automatic_pruning',True),('independent_exact_image_qualified',True),
                           ('authenticated_offline_rollback_protection',True)]:
            with self.subTest(key=key):
                contract=copy.deepcopy(source);contract['managed_store'][key]=value
                VALIDATOR.ERRORS.clear();VALIDATOR.audit_contract(contract)
                self.assertTrue(any('managed receipt' in error for error in VALIDATOR.ERRORS))

    def test_managed_helper_cannot_acquire_new_execution_authority(self):
        self.rejects('managed','use super::*;', 'use super::*; fn forbidden() { std::process::Command::new("x"); }')

if __name__ == '__main__':
    unittest.main()
