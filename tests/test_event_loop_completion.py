"""Mutation/inventory guard for callback scheduling, not native engine evidence."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('callback_audit_tests', ROOT/'tools/audit_event_loop_completion.py')
assert SPEC and SPEC.loader
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


class CallbackCompletionTests(unittest.TestCase):
    def setUp(self):
        self.inputs = {key:(ROOT/name).read_text() for key,name in AUDIT.INPUTS.items()}
        self.contract = (ROOT/AUDIT.CONTRACT).read_text()

    def rejects(self, key, old, new):
        self.assertIn(old, self.inputs[key])
        inputs = self.inputs.copy()
        inputs[key] = inputs[key].replace(old, new, 1)
        self.assertTrue(AUDIT.audit(inputs, self.contract), (key, old))

    def test_actual_sources_pass(self):
        self.assertEqual(AUDIT.audit(self.inputs, self.contract), [])

    def test_missing_input_is_not_replaced_with_repository_copy(self):
        for key in self.inputs:
            inputs = self.inputs.copy(); del inputs[key]
            self.assertTrue(AUDIT.audit(inputs,self.contract),key)

    def test_contract_types_duplicates_and_promotions_are_rejected(self):
        contract = json.loads(self.contract)
        for key in ['servo_adapter','production_listener_enabled','external_effect_authority','promotion_authoritative','native_event_loop_exercised','queued_is_durable_success']:
            changed = dict(contract); changed[key] = True
            self.assertTrue(AUDIT.audit(self.inputs,json.dumps(changed)),key)
        for key in ['request_queue_limit','active_call_limit','completion_queue_limit']:
            changed = dict(contract); changed[key] = True
            self.assertTrue(AUDIT.audit(self.inputs,json.dumps(changed)),key)
        self.assertTrue(AUDIT.audit(self.inputs,self.contract.replace('{','{"status":"SOURCE_CANDIDATE",',1)))
        self.assertTrue(AUDIT.audit(self.inputs,'{"value":NaN}'))

    def test_owner_does_not_wait_for_engine_callback(self):
        self.rejects('owner','self.active.is_some()','{ receiver.recv_timeout(timeout); self.active.is_some() }')
        self.rejects('owner','self.active.is_some()','{ thread::spawn(f); self.active.is_some() }')
        self.rejects('owner','PhantomData<Rc<()>>','PhantomData<()>')

    def test_completion_is_linear_and_sender_not_exposed(self):
        self.rejects('owner','pub fn complete(mut self,','pub fn complete(&mut self,')
        self.rejects('owner','pub struct EngineCompletion {','#[derive(Clone)]\npub struct EngineCompletion {')
        self.rejects('owner','    sender: Option<','    pub sender: Option<')

    def test_missing_final_peer_recheck_not_hidden_by_other_checks(self):
        # Match the poll_active-specific full check, not callback preflight.
        self.rejects('owner','let result = active\n            .call\n            .control\n            .ensure_current_peer()', 'let result = active\n            .call\n            .control\n            .ensure_active()')
        self.rejects('owner','let (sender, completion) = mpsc::sync_channel(1);','let (sender, completion) = mpsc::sync_channel(16);')

    def test_retirement_wakes_are_required_in_both_destructors(self):
        self.rejects('dispatch','notify_engine(self.waker);','ignored(self.waker);')
        self.rejects('dispatch','notify_engine(self.waker.as_ref());','ignored(self.waker.as_ref());')

    def test_lost_callback_does_not_become_success(self):
        self.rejects('owner','let _ = sender.try_send(Err(RuntimeFailure::BrowserCrashed));','let _ = sender.try_send(Ok(default_reply()));')
        self.rejects('owner','active.valid.store(false, Ordering::SeqCst);','active.valid.store(true, Ordering::SeqCst);')

    def test_no_generic_action_fallback_or_repeat_start(self):
        self.rejects('owner','self.runtime.start_page_act(','self.runtime.start(')
        self.rejects('owner','Err(TryRecvError::Empty) => return CallbackPumpResult::Pending,','Err(TryRecvError::Empty) => return self.restart(),')
        self.rejects('owner','ordinary_message(&active.call)','caller_message(&active.call)')

    def test_named_host_regressions_cannot_be_disabled(self):
        for key,name in [('tests','buffered_callback_success_is_rechecked_against_current_request_identity'),('transport','attested_host_chain_yields_for_native_callbacks_and_preserves_twelve_receipts')]:
            self.rejects(key,'#[test]\nfn '+name,'#[ignore]\nfn '+name)

    def test_inventory_workflows_and_invalidation_include_exact_inputs(self):
        module = next(x for x in json.loads((ROOT/'manifests/modules.v1.json').read_text())['modules'] if x['id']=='hepta-browser-actor')
        self.assertIn(AUDIT.CONTRACT,module['contracts']);self.assertIn(AUDIT.DOCUMENT,module['architecture'])
        for name in [AUDIT.INPUTS['tests'],AUDIT.INPUTS['transport'],'tests/test_event_loop_completion.py']:
            self.assertIn(name,module['tests'])
        inputs=[AUDIT.DOCUMENT,AUDIT.CONTRACT,'tests/test_event_loop_completion.py','tools/audit_event_loop_completion.py']
        workflows=['.github/workflows/d3-integrated-runtime-evidence.yml','.github/workflows/agent-port-custody.yml','.github/workflows/receipt-journal.yml']
        for name in inputs:
            for workflow in workflows:
                self.assertGreaterEqual((ROOT/workflow).read_text().count('"'+name+'"'),2,(workflow,name))
            for gate in json.loads((ROOT/'manifests/gates.v1.json').read_text())['gates']:
                if gate['id'] in ['D0C-05','D0C-06','D3-01']:
                    self.assertIn(name,gate['invalidation_paths'],(gate['id'],name))
        facade=(ROOT/'tools/validate_d3_development_profile.py').read_text()
        self.assertIn('_callback_audit.audit(callback_inputs,',facade)
        self.assertIn('cargo test --locked -p hepta-browser-actor --doc',(ROOT/'.github/workflows/ci.yml').read_text())

    def test_document_retains_real_integration_and_deadline_limits(self):
        document=(ROOT/AUDIT.DOCUMENT).read_text()
        for phrase in ['not a Servo adapter','not a real-time guarantee','panic hook','original Instant','twelve checked receipt','synchronous','independent security review']:
            self.assertIn(phrase,document)
        self.assertEqual(self.inputs['owner'].count('```compile_fail'),4)


if __name__ == '__main__':
    unittest.main()
