"""Source/contract mutation checks; not evidence of actual Servo or OS reboot."""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path
import unittest
ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('incarnation_audit', ROOT/'tools/validate_d3_development_profile.py')
assert SPEC and SPEC.loader
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)
class SessionIncarnationTests(unittest.TestCase):
    def setUp(self):
        self.inputs = {k:(ROOT/p).read_text() for k,p in AUDIT.SESSION_INCARNATION_INPUTS.items()}
        self.contract = (ROOT/AUDIT.SESSION_INCARNATION_CONTRACT).read_text()
    def rejects(self, key, old, replacement):
        self.assertIn(old, self.inputs[key])
        d=self.inputs.copy();d[key]=d[key].replace(old,replacement,1)
        self.assertTrue(AUDIT.audit_session_incarnation_sources(d,self.contract),(key,old))
    def test_current_sources_and_contract_pass(self):
        self.assertEqual(AUDIT.audit_session_incarnation_sources(self.inputs,self.contract),[])
    def test_missing_input_has_no_repository_fallback(self):
        for key in self.inputs:
            d=self.inputs.copy();del d[key]
            self.assertTrue(AUDIT.audit_session_incarnation_sources(d,self.contract),key)
    def test_namespace_is_used_for_both_runtime_identities(self):
        self.rejects('actor','self.binding.mechanism.peer.uid, namespace, next_session_counter','self.binding.mechanism.peer.uid, next_session_counter')
        self.rejects('actor','namespace, next_webview_counter','next_webview_counter')
        self.rejects('actor','self.incarnation.namespace()?','caller_namespace()')
    def test_entropy_failure_and_source_cannot_be_weakened(self):
        self.rejects('identity','OsNonceSource.next_nonce()','Ok([7; NONCE_BYTES])')
        self.rejects('identity','bytes != [0; NONCE_BYTES]','true')
        self.rejects('identity','self.failed = true;','self.failed = false;')
        self.rejects('identity','if self.failed','if false')
        self.rejects('identity','digest.update(ACTOR_DOMAIN);','/* missing domain */')
    def test_test_injection_never_becomes_production_configuration(self):
        for old in ('#[cfg(test)]\n    source:', '#[cfg(test)]\n    pub(super) fn with_source', '#[cfg(test)]\n        if let Some(source)'):
            self.rejects('identity',old,old.replace('#[cfg(test)]',''))
    def test_deadline_recheck_after_entropy_must_remain(self):
        self.rejects('actor','let namespace = self.incarnation.namespace()?;\n                    context.remaining()?;',
                     'let namespace = self.incarnation.namespace()?;')
    def test_frame_hash_is_bound_delimited_and_not_truncated(self):
        self.rejects('identity','digest.update(FRAME_DOMAIN);','/* missing frame domain */')
        self.rejects('identity','digest.update((value.len() as u32).to_be_bytes());','/* missing length */')
        self.rejects('runtime','&coordinates.webview_token,','"shared-view",')
        self.rejects('runtime','snapshot.target != *target','false')
    def test_disabled_behavioral_regressions_are_rejected(self):
        for key,name in [('tests','previous_incarnation_snapshot_is_rejected_before_dispatch'),
                         ('runtime_tests','stale_fixture_target_cannot_be_reparented_across_webviews'),
                         ('service_tests','recreated_service_reopens_journal_but_rejects_old_session_and_reparented_target')]:
            self.rejects(key,f'#[test]\nfn {name}',f'#[test]\n#[ignore]\nfn {name}')
    def test_contract_rejects_duplicates_wrong_types_and_promotions(self):
        obj=json.loads(self.contract)
        for k,v in [('entropy_bytes',True),('frame_id_bytes',64.0),('servo_adapter_implemented',True),('durable_anti_rollback',True),('promotion_authoritative',True)]:
            self.assertTrue(AUDIT.audit_session_incarnation_sources(self.inputs,json.dumps(dict(obj,**{k:v}))),k)
        for value in ('[]','{"scope":0,"scope":0}','{"entropy_bytes":NaN}'):
            self.assertTrue(AUDIT.audit_session_incarnation_sources(self.inputs,value))
    def test_paths_registries_and_claim_ceiling_are_consistent(self):
        from tests.test_agent_port_custody_workflow import trigger_paths
        doc='docs/architecture/SESSION_INCARNATION.md';contract=AUDIT.SESSION_INCARNATION_CONTRACT
        required=[doc,contract,'tests/test_session_incarnation.py']
        for wf in ('agent-port-custody.yml','receipt-journal.yml','d3-integrated-runtime-evidence.yml'):
            text=(ROOT/'.github/workflows'/wf).read_text()
            for event in ('pull_request','push'):
                for path in required:self.assertIn(path,trigger_paths(text,event),(wf,event,path))
        modules=json.loads((ROOT/'manifests/modules.v1.json').read_text())['modules']
        for m in modules:
            if m['id'] in ('hepta-browser-actor','hepta-d3-development','hepta-agent-portd'):
                self.assertIn(doc,m['architecture']);self.assertIn(contract,m['contracts'])
                self.assertIn(required[2],m['tests'])
        gates=json.loads((ROOT/'manifests/gates.v1.json').read_text())['gates']
        for g in gates:
            if g['id'] in ('D0C-05','D0C-06','D3-01'):
                for path in required:self.assertIn(path,g['invalidation_paths'])
        self.assertEqual(next(g for g in gates if g['id']=='D3-01')['status'],'BLOCKED_UPSTREAM')
        text=(ROOT/doc).read_text()
        for h in ('## Scope and non-claims','## Identity allocation and failure sequence','## Scoped frame identity API',
                  '## Durable receipts and service reconstruction','## Compatibility and operational diagnosis','## Residual risks and remaining gates'):
            self.assertIn(h,text)
if __name__=='__main__':unittest.main()
