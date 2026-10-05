"""Finite API mutations; actual Linux corpus independently supplies behavior."""
import copy
import json
from pathlib import Path
import subprocess
import re
import unittest
from tools.verify_approved_request_binding import ROOT, CONTRACT, EXPECTED, check, inputs
from tools.verify_approved_native_startup import tokens

class ApprovedRequestBindingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.value=json.loads((ROOT/CONTRACT).read_text())
        cls.texts=inputs()
    def test_closed_contract_and_actual_source_API(self):
        check(self.value,self.texts)
    def test_contract_every_field_and_typed_leaf_is_closed(self):
        def visit(node,path):
            if isinstance(node,dict):
                for key,item in node.items():
                    mutant=copy.deepcopy(self.value); part=mutant
                    for step in path: part=part[step]
                    del part[key]
                    with self.assertRaises((ValueError,KeyError)): check(mutant,self.texts)
                    if type(item) in (bool,int):
                        for bad in ([int(item),None] if type(item) is bool else [True,float(item),str(item),item+1]):
                            mutant=copy.deepcopy(self.value);part=mutant
                            for step in path: part=part[step]
                            part[key]=bad
                            with self.assertRaises((ValueError,KeyError)):check(mutant,self.texts)
                    visit(item,path+[key])
                mutant=copy.deepcopy(self.value); part=mutant
                for step in path: part=part[step]
                part['caller_approved']=True
                with self.assertRaises((ValueError,KeyError)): check(mutant,self.texts)
        visit(self.value,[])
    def mutate(self,path,old,new):
        texts=dict(self.texts)
        if old in texts[path]: texts[path]=texts[path].replace(old,new)
        else:
            pattern=r'\s*'.join(re.escape(part) for part in tokens(old))
            texts[path]=re.sub(pattern,lambda _:new,texts[path])
        self.assertNotEqual(texts[path],self.texts[path])
        with self.assertRaises((ValueError,KeyError)): check(self.value,texts)
    def test_root_binding_snapshot_principal_and_Clone_mutations_refuse(self):
        p=EXPECTED['sources'][0]
        for old,new in [('self.guard.state.entries != session.guard.state.entries','self.guard.state.entries[1] != session.guard.state.entries[1]'),('self.deadline > session.deadline','self.deadline < session.deadline'),('self.control.verify_pair_current(&self.original.verifier())','self.control.ensure_alive()'),('self.attested.request_custody()','self.attested.fake_custody()'),('pub fn start_session(&self)','pub fn start_session(&self, principal: String)'),('original: PeerRequestCustody','original: PeerRuntimeSnapshot'),('self.consume_before(','self.consumer_without_custody(')]:
            self.mutate(p,old,new)
        for name in EXPECTED['opaque_types']:
            self.mutate(p,'pub struct '+name,'#[derive(Clone)]\npub struct '+name)
            self.mutate(p,'pub struct '+name+' {','pub struct '+name+' {\n pub authority: bool,')
    def test_no_partial_binding_or_prepared_authority_mutations(self):
        p=EXPECTED['sources'][2]
        for old,new in [('self.ensure_prepared_request_owner()?','Ok::<(), AgentPortError>(())?'),('!self.cancellation_tokens.is_empty()','false'),('self.request_authority.borrow().is_some()','false'),('self.control_authority.borrow().is_some()','false'),('self.binding.principal.clone()','caller_principal.clone()')]:self.mutate(p,old,new)
        texts=dict(self.texts)
        needle='request.verify_for_session(session)'
        # Formatting may add line breaks before the field call.
        original=texts[p]
        texts[p]=re.sub(r'request\s*\.verify_for_session\(session\)', 'request.skip_verify_for_session(session)', original,count=1)
        self.assertNotEqual(texts[p],original)
        with self.assertRaises(ValueError):check(self.value,texts)
    def test_product_history_and_raw_dispatch_mutations(self):
        p='apps/hepta-browserd/src/product_dispatch/product_approved_policy.rs'
        for old,new in [('self.state != RuntimeState::Ready','false'),('self.pending_reconciliation.is_some()','false'),('.has_unresolved_receipts()','.has_no_unresolved_receipts()'),('.consume_with_request_binding(','.consume_before(')]:self.mutate(p,old,new)
        p='crates/hepta-browser-actor/src/servo_runtime.rs'
        self.mutate(p,'self.refuse_uncontrolled_approved_request()?','self.ensure_approved_request()?')
        p=EXPECTED['sources'][1]
        self.mutate(p,'self.approved_session.as_ref()','caller_approved_session.as_ref()')
        self.mutate(p,'context.effective_deadline > ceiling','context.effective_deadline < ceiling')
        p=EXPECTED['sources'][0]
        self.mutate(p,'self.original.original_attested_peer()','self.original.caller_attested_peer()')
        self.mutate(p,'consumer(&ProcfsPeerAttestor::default(), original, &self.control','consumer(caller_attestor, original, caller_control')
    def test_original_native_kernel_bytes_and_CLI(self):
        path=next(iter(EXPECTED['preserved_sources']))
        texts=dict(self.texts);texts[path]+='\n'
        with self.assertRaises(ValueError):check(self.value,texts)
        result=subprocess.run(['python3',str(ROOT/'tools/verify_approved_request_binding.py')],cwd=ROOT,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('runtime/native/installed qualification separate',result.stdout)

if __name__=='__main__':unittest.main()
