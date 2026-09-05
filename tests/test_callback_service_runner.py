"""Callback service source/contract invariants, not installed image proof."""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('service_callback_audit_test',ROOT/'tools/audit_callback_service.py')
assert SPEC and SPEC.loader
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)

class CallbackServiceTests(unittest.TestCase):
    def setUp(self):
        self.inputs = {key:(ROOT/path).read_text() for key,path in AUDIT.INPUTS.items()}
        self.contract = (ROOT/AUDIT.CONTRACT).read_text()
    def rejects(self,key,old,new):
        self.assertIn(old,self.inputs[key])
        changed=self.inputs.copy();changed[key]=changed[key].replace(old,new,1)
        self.assertTrue(AUDIT.audit(changed,self.contract),(key,old))
    def test_exact_sources_and_contract(self):
        self.assertEqual(AUDIT.audit(self.inputs,self.contract),[])
    def test_missing_input_cannot_fall_back_to_repository(self):
        for key in self.inputs:
            changed=self.inputs.copy();del changed[key]
            self.assertTrue(AUDIT.audit(changed,self.contract),key)
    def test_types_duplicates_and_authority_flags_fail_closed(self):
        obj=json.loads(self.contract)
        for key,value in [('worker_count',True),('accept_poll_ms',5.0),('owner_idle_polling',True),('servo_adapter',True),('exact_image_qualified',True),('product_agent_port_enabled',True),('promotion_authoritative',True)]:
            changed=dict(obj);changed[key]=value
            self.assertTrue(AUDIT.audit(self.inputs,json.dumps(changed)),key)
        for bad in [self.contract.replace('{','{"status":"SOURCE_CANDIDATE",',1),'[]','{"x":NaN}']:
            self.assertTrue(AUDIT.audit(self.inputs,bad))
    def test_actual_service_route_uses_callback_bridge(self):
        self.rejects('entry','run_callback_on_owner(ImmediateCallbacks::new(runtime),','legacy_runner(runtime,')
    def test_finished_predicate_and_publication_are_required(self):
        self.rejects('runner','self.finished.store(true, Ordering::Release);','self.finished.store(false, Ordering::Release);')
        self.rejects('runner','while !finished.load(Ordering::Acquire)','while !worker.is_finished()')
        self.rejects('runner','if !finished.load(Ordering::Acquire) {\n                    wake.wait_until','if true {\n                    wake.wait_until')
    def test_wait_cannot_erase_notifications_after_drain(self):
        self.rejects('runner','while !*pending {','*pending = false; while !*pending {')
        self.rejects('runner','*pending = true;','*pending = false;')
        self.rejects('runner','wake.begin_cycle()?;','/* wake.begin_cycle()?; */')
    def test_spurious_wakes_cannot_skip_predicate_or_renew_timer(self):
        self.rejects('runner','while !*pending {','if !*pending {')
        self.rejects('runner','at.saturating_duration_since(Instant::now())','Duration::from_secs(20)')
    def test_driver_error_must_revoke_and_join_not_hide_failure(self):
        self.rejects('runner','failure = Some(error);\n                stop.retire();\n                owner.retire();','failure = Some(error);\n                stop.retire();')
        self.rejects('runner','let joined = worker\n            .join()','let joined = worker\n            .is_finished()')
        self.rejects('runner','return Err(error);\n        }\n        joined','return joined;\n        }\n        joined')
    def test_bridge_keeps_original_control_and_atomic_hook(self):
        self.rejects('bridge','&completion.control','&replacement_control')
        self.rejects('bridge','.dispatch_page_act(owner, target, action, &completion.control)','.dispatch(owner, target, &completion.control)')
        self.rejects('bridge','drop(self.runtime.take());','/* drop(self.runtime.take()); */')
    def test_new_regressions_and_self_check_nonclaims_are_preserved(self):
        self.rejects('tests','#[test]\nfn worker_completion_publishes_finished_before_wake','#[ignore]\nfn worker_completion_publishes_finished_before_wake')
        self.rejects('transport','#[test]\nfn deferred_fixture_uses_actual_callback_runner_and_preserves_fifteen_receipts','#[ignore]\nfn deferred_fixture_uses_actual_callback_runner_and_preserves_fifteen_receipts')
        self.rejects('main','\\"callback_service_runner_exercised\\":false','\\"callback_service_runner_exercised\\":true')
    def test_inventory_and_all_three_workflows_bind_inputs(self):
        inputs=[AUDIT.DOCUMENT,AUDIT.CONTRACT,'tools/audit_callback_service.py','tests/test_callback_service_runner.py',AUDIT.INPUTS['runner'],AUDIT.INPUTS['bridge'],AUDIT.INPUTS['tests']]
        for module in json.loads((ROOT/'manifests/modules.v1.json').read_text())['modules']:
            if module['id'] in ['hepta-browser-actor','hepta-d3-development']:
                self.assertIn(AUDIT.DOCUMENT,module['architecture'])
                self.assertIn(AUDIT.CONTRACT,module['contracts'])
                self.assertIn('tests/test_callback_service_runner.py',module['tests'])
        for gate in json.loads((ROOT/'manifests/gates.v1.json').read_text())['gates']:
            if gate['id'] in ['D0C-05','D0C-06','D3-01']:
                for path in inputs: self.assertIn(path,gate['invalidation_paths'],(gate['id'],path))
        from tests.test_agent_port_custody_workflow import trigger_paths
        for f in ['.github/workflows/agent-port-custody.yml','.github/workflows/receipt-journal.yml','.github/workflows/d3-integrated-runtime-evidence.yml']:
            text=(ROOT/f).read_text()
            for event in ['pull_request','push']:
                for path in inputs: self.assertIn(path,trigger_paths(text,event),(f,event,path))
        self.assertIn('_service_callback_audit.audit(service_callback_inputs,',(ROOT/'tools/validate_d3_development_profile.py').read_text())
    def test_document_distinguishes_callback_fixture_and_native_integration(self):
        text=(ROOT/AUDIT.DOCUMENT).read_text()
        for phrase in ['not a Servo adapter','NOT a replacement','same borrowed RequestControl','BEFORE draining','BEFORE notifying','no periodic main-thread polling','worker\'s inherited-listener','compatibility actor handler','D2I/D3']:
            self.assertIn(phrase,text)

if __name__=='__main__': unittest.main()
