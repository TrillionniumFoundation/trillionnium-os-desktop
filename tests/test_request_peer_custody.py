"""Source mutation regressions for request custody; not higher-tier evidence."""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('request_custody_audit', ROOT / 'tools/validate_d3_development_profile.py')
assert SPEC and SPEC.loader
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)

class RequestPeerCustodyTests(unittest.TestCase):
    def setUp(self):
        self.inputs = {k:(ROOT/p).read_text() for k,p in AUDIT.REQUEST_PEER_INPUTS.items()}
        self.contract = (ROOT/AUDIT.REQUEST_PEER_CONTRACT).read_text()
    def rejects(self, key, old, new):
        self.assertIn(old,self.inputs[key])
        changed=self.inputs.copy();changed[key]=changed[key].replace(old,new,1)
        self.assertTrue(AUDIT.audit_request_peer_sources(changed,self.contract),(key,old))
    def test_registered_sources_and_contract_pass(self):
        self.assertEqual(AUDIT.audit_request_peer_sources(self.inputs,self.contract),[])
    def test_missing_input_never_falls_back_to_current_repository(self):
        for key in self.inputs:
            d=self.inputs.copy();del d[key]
            self.assertTrue(AUDIT.audit_request_peer_sources(d,self.contract),key)
    def test_original_source_cannot_be_substituted_or_ignored(self):
        self.rejects('peer','attestor.proc_root != self.attestor.proc_root','false')
        self.rejects('lease','attestor: self.attestor.clone()','attestor: ProcfsPeerAttestor::default()')
        self.rejects('lease','executable_source: self.executable_source.clone()','executable_source: ExecutableSource::Live')
    def test_original_pidfd_must_be_duplicated_and_liveness_checked(self):
        self.rejects('lease','self.pidfd.try_clone().map_err(AttestationError::Pidfd)?','replacement_pidfd()')
        self.rejects('lease','self.state.peer.ensure_alive()','Ok::<(), AttestationError>(())')
    def test_custody_drop_and_one_way_latch_cannot_be_removed(self):
        self.rejects('lease','self.revoke();','/* self.revoke(); */')
        self.rejects('lease','self.state.revoked.store(true, Ordering::SeqCst);','self.state.revoked.store(false, Ordering::SeqCst);')
        self.rejects('lease','if let Err(error) = self.state.peer.refresh_snapshot(&self.state.peer.attestor)','if let Err(error) = Ok::<(), AttestationError>(())')
    def test_actor_scope_final_check_and_retirement_are_real_calls(self):
        self.rejects('actor','attested.request_custody()','pretend_custody()')
        self.rejects('actor','verifier.verify_current().is_err()','false')
        self.rejects('actor','*self.slot.borrow_mut() = self.previous.take();','/* scope cleanup missing */')
    def test_final_refresh_deadline_preserves_existing_reconciliation(self):
        self.rejects('actor','self.reconcile_after_final_deadline(context, request, page_was_present);','/* no reconciliation */')
        old='self.check_attested_return_deadline(context, request, page_was_present)?;'
        for offset in (i for i in range(len(self.inputs['actor'])) if self.inputs['actor'].startswith(old,i)):
            d=self.inputs.copy();s=d['actor'];d['actor']=s[:offset]+'context.remaining()?;'+s[offset+len(old):]
            self.assertTrue(AUDIT.audit_request_peer_sources(d,self.contract),offset)
    def test_queue_entry_and_return_checks_are_both_required(self):
        self.rejects('engine','if let Err(error) = call.control.ensure_current_peer()','if let Err(error) = call.control.ensure_active()')
        self.rejects('engine','.ensure_current_peer()\n            .and(result)','.ensure_active()\n            .and(result)')
    def test_cleanup_controls_cannot_drop_identity(self):
        self.rejects('actor','authority: self.request_authority.borrow().clone()','authority: None')
        # Test every constructor, not just the first occurrence.
        old='authority: self.request_authority.borrow().clone()'
        for offset in (i for i in range(len(self.inputs['actor'])) if self.inputs['actor'].startswith(old,i)):
            d=self.inputs.copy();s=d['actor'];d['actor']=s[:offset]+'authority: None'+s[offset+len(old):]
            self.assertTrue(AUDIT.audit_request_peer_sources(d,self.contract),offset)
    def test_uncertain_effect_is_not_reclassified_as_refused(self):
        self.rejects('actor','RuntimeFailure::PeerIdentityRevoked => failure(\n            BrowserErrorCode::Indeterminate','RuntimeFailure::PeerIdentityRevoked => failure(\n            BrowserErrorCode::PolicyDenied')
    def test_contract_rejects_wrong_types_duplicates_and_promotion(self):
        obj=json.loads(self.contract)
        for k,v in [('custody_owners',True),('pidfd_duplicates_per_request',1.0),('custody_drop_revokes',False),('servo_adapter',True),('promotion_authoritative',True),('atomic_with_process_exit_or_exec',True)]:
            self.assertTrue(AUDIT.audit_request_peer_sources(self.inputs,json.dumps(dict(obj,**{k:v}))),k)
        for text in ('[]','{"scope":0,"scope":0}','{"custody_owners":NaN}'):
            self.assertTrue(AUDIT.audit_request_peer_sources(self.inputs,text))
    def test_real_service_and_regression_wiring_cannot_be_removed(self):
        self.rejects('service','handle_attested(context, request, self.attestor, self.attested)','handle(context, request)')
        self.rejects('tests','#[test]\nfn queued_request_rechecks_cgroup_at_engine_boundary','#[test]\n#[ignore]\nfn queued_request_rechecks_cgroup_at_engine_boundary')
    def test_document_registry_and_workflow_inputs_remain_complete(self):
        doc='docs/architecture/REQUEST_PEER_CUSTODY.md'; contract=AUDIT.REQUEST_PEER_CONTRACT
        text=(ROOT/doc).read_text()
        for heading in ('## Scope and non-claims','## API and ownership','## Dispatch sequence','## Failure, uncertainty and recovery','## Resource and concurrency limits','## Tests and acceptance'):
            self.assertIn(heading,text)
        modules=json.loads((ROOT/'manifests/modules.v1.json').read_text())['modules']
        for m in modules:
            if m['id'] in ('hepta-peer-attestation','hepta-browser-actor','hepta-d3-development'):
                self.assertIn(doc,m['architecture']);self.assertIn(contract,m['contracts'])
        from tests.test_agent_port_custody_workflow import trigger_paths
        required=[doc,contract,'tests/test_request_peer_custody.py','crates/hepta-peer-attestation/**','crates/hepta-browser-actor/**']
        for wf in ('.github/workflows/receipt-journal.yml','.github/workflows/d3-integrated-runtime-evidence.yml','.github/workflows/agent-port-custody.yml'):
            s=(ROOT/wf).read_text()
            for event in ('pull_request','push'):
                for item in required:self.assertIn(item,trigger_paths(s,event),(wf,event,item))
        gates=json.loads((ROOT/'manifests/gates.v1.json').read_text())['gates']
        for g in gates:
            if g['id'] in ('D0C-05','D0C-06','D3-01'):
                for item in required[:3]:self.assertIn(item,g['invalidation_paths'])
        self.assertEqual(next(g for g in gates if g['id']=='D3-01')['status'],'BLOCKED_UPSTREAM')

if __name__=='__main__':unittest.main()
