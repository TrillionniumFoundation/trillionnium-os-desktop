"""Mutation guards for explicit offline copy. Runtime evidence is separate."""
from __future__ import annotations
import copy
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('receipt_migration_under_test', ROOT/'tools/audit_receipt_migration.py')
assert SPEC and SPEC.loader
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)

class ReceiptMigrationAuditTests(unittest.TestCase):
    def setUp(self):
        self.inputs = {key:(ROOT/path).read_text() for key,path in AUDIT.INPUTS.items()}
        self.contract = (ROOT/AUDIT.CONTRACT).read_text()
    def rejects(self,key,old,new):
        self.assertIn(old,self.inputs[key])
        mutated=dict(self.inputs);mutated[key]=mutated[key].replace(old,new,1)
        self.assertTrue(AUDIT.audit(mutated,self.contract),(key,old))
    def test_exact_sources_and_contract(self):
        self.assertEqual(AUDIT.audit(self.inputs,self.contract),[])
    def test_missing_inputs_cannot_use_repository_fallback(self):
        for key in self.inputs:
            changed=dict(self.inputs);del changed[key]
            self.assertTrue(AUDIT.audit(changed,self.contract),key)
    def test_contract_rejects_type_drift_duplicate_keys_and_authority(self):
        for key,value in [('maximum_segments',True),('process_cut_cases',16.0),('source_repair',True),('source_deletion',True),('automatic_replay',True),('automatic_service_cutover',True),('physical_power_loss_qualified',True),('promotion_authoritative',True)]:
            changed=json.loads(self.contract);changed[key]=value
            self.assertTrue(AUDIT.audit(self.inputs,json.dumps(changed)),key)
        for malformed in ['[]','{"bad":NaN}',self.contract.replace('{','{"status":"SOURCE_CANDIDATE",',1)]:
            self.assertTrue(AUDIT.audit(self.inputs,malformed))
    def test_readonly_strict_source_and_inode_locks_are_required(self):
        self.rejects('source','open_existing_file_checked(&path, false, identity)?','open_existing_file_checked(&path, true, identity)?')
        self.rejects('source','chain::validate_reports(&inspected, false)?','chain::validate_reports(&inspected, true)?')
        self.rejects('source','lock_file(&file)?;','/* lock_file(&file)?; */')
        self.rejects('source','!identities.insert(identity)','false')
    def test_source_and_staging_digest_checks_cannot_be_removed(self):
        self.rejects('source','sha256(&bytes) != self.digests[index]','false')
        self.rejects('source','actual != expected','false')
        self.rejects('source','bytes != marker_bytes(id)','false')
        self.rejects('source','sha256(&read_segment_bytes(&mut copy.file)?) != *expected','false')
    def test_sync_and_publication_order_cannot_be_removed(self):
        self.rejects('source','marker_file.sync_all().map_err(map_io_error)?;','/* marker_file.sync_all().map_err(map_io_error)?; */')
        self.rejects('source','fs::rename(&marker.path, root.join(MARKER)).map_err(map_io_error)?;','ignored();')
        self.rejects('source','guard.verify_current()?;','ignored();')
    def test_pending_import_refuses_legacy_writer_entrypoints(self):
        self.rejects('managed','[MARKER, migration::MIGRATION_PENDING]','[MARKER]')
        self.rejects('managed','mod migration;','// mod migration;')
    def test_fault_case_inventory_is_fixed_and_hooks_are_test_only(self):
        for key in ['tests','process']:
            self.rejects(key,'"migration_segment_1.partial_write",','')
        self.rejects('source','#[cfg(test)]\n        persistence_tests::point("migration.before_publish")?;','persistence_tests::point("migration.before_publish")?;')
    def test_process_uses_actual_source_and_real_sigkill(self):
        self.rejects('process','#[path = "../src/receipt_journal.rs"]','#[path = "copied_impl.rs"]')
        self.rejects('process','child.0.kill().unwrap();','ignored();')
        self.rejects('cargo','name = "journal_migration_process"','name = "disabled_migration"')
    def test_no_added_execution_or_source_repair_authority(self):
        for code in ['std::process::Command::new("x");','file.set_len(0);','fs::remove_file(source);','WriterLease::acquire(source);']:
            mutated=dict(self.inputs);mutated['source']+='\nfn bad(){ '+code+' }\n'
            self.assertTrue(AUDIT.audit(mutated,self.contract),code)
    def test_document_registry_and_ci_inputs_are_reachable(self):
        self.assertTrue((ROOT/AUDIT.DOCUMENT).is_file())
        registry=json.loads((ROOT/'manifests/modules.v1.json').read_text())
        module=next(m for m in registry['modules'] if m['id']=='hepta-session-core')
        self.assertIn(AUDIT.DOCUMENT,module['architecture'])
        self.assertIn(AUDIT.CONTRACT,module['contracts'])
        self.assertIn('tests/test_receipt_migration.py',module['tests'])
        self.assertIn('crates/hepta-session-core/tests/journal_migration_process.rs',module['tests'])
        workflow=(ROOT/'.github/workflows/receipt-journal.yml').read_text()
        required=[AUDIT.DOCUMENT,AUDIT.CONTRACT,'tools/audit_receipt_migration.py','tests/test_receipt_migration.py']
        for item in required:
            self.assertGreaterEqual(workflow.count('"'+item+'"'),2,item)
        gates=json.loads((ROOT/'manifests/gates.v1.json').read_text())
        gate=next(g for g in gates['gates'] if g['id']=='D0C-06')
        for item in required:
            self.assertIn(item,gate['invalidation_paths'],item)
        main=(ROOT/'tools/verify_receipt_journal.py').read_text()
        self.assertIn('audit_receipt_migration.audit(migration_inputs, migration_contract)',main)

if __name__=='__main__': unittest.main()
