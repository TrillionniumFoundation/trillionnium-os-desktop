"""Closed source correspondence only; actual /proc/rights/fork live in Rust."""
import copy
import json
from pathlib import Path
import re
import tomllib
import unittest
ROOT=Path(__file__).resolve().parents[1]
API={
'ControlOwnerPolicy::new':'(PeerPolicy, PeerRuntimePolicy, String) -> Result<ControlOwnerPolicy, ControlOwnerError>',
'AttestedHandoffSender::from_accepted':'(OwnedFd, UnixStream, &Path, ControlOwnerPolicy, Duration) -> Result<AttestedHandoffSender, ControlOwnerError>',
'AttestedHandoffSender::ensure_current':'(&mut self) -> Result<Instant, ControlOwnerError>',
'AttestedHandoffSender::send':'(&mut self) -> Result<(), ControlOwnerError>',
'AttestedHandoffSender::cancel':'(&mut self) -> Result<(), ControlOwnerError>',
'AttestedHandoffReceiver::from_control':'(OwnedFd, ControlOwnerPolicy, &Path, Duration) -> Result<AttestedHandoffReceiver, ControlOwnerError>',
'AttestedHandoffReceiver::ensure_current':'(&mut self) -> Result<Instant, ControlOwnerError>',
'AttestedHandoffReceiver::receive':'(&mut self) -> Result<ReceivedAcceptedStream, ControlOwnerError>',
'AttestedHandoffReceiver::cancel':'(&mut self) -> Result<(), ControlOwnerError>'}
KEYS={'policy':{'source','kernel','runtime','executable_pin','refresh'},'budgets':{'maximum_seconds','accepted','receiver_control_wait','preemptive_procfs_timeout','pre_accept_wait_covered','cancellation','automatic_renewal'},'ownership':{'transaction_count_each_instance','raw_stream_extraction','sender_custody_return_on_error','send_success','failure','fork','returned'},'non_claims':{'approved_policy_provisioned','live_cross_uid_attestation_qualified','root_owned_control_path_custody','installed_daemon_owner','native_final_effect_gate','semantic_principal','fixture_or_static_substitution','product_ready','default_activation_changed'}}
def check(value):
 if type(value)is not dict or set(value)!={'schema','status','implementation','policy','budgets','ownership','public_api','non_claims'}:raise ValueError('closed top-level')
 if value['schema']!='trillionnium.desktop.control-owner-handoff.v1' or value['status']!='SOURCE_CANDIDATE_LIVE_CONTROL_INCARNATION_ONLY' or value['implementation']!='crates/hepta-peer-attestation/src/control_owner.rs':raise ValueError('source scope')
 for name,keys in KEYS.items():
  if type(value[name])is not dict or set(value[name])!=keys:raise ValueError('closed '+name)
 if value['public_api']!=API:raise ValueError('closed API')
 for group,key,number in [('budgets','maximum_seconds',20),('ownership','transaction_count_each_instance',1)]:
  if type(value[group][key])is not int or value[group][key]!=number:raise ValueError('fixed bound')
 for group,keys in [('budgets',['preemptive_procfs_timeout','pre_accept_wait_covered','automatic_renewal']),('ownership',['raw_stream_extraction','sender_custody_return_on_error']),('non_claims',KEYS['non_claims'])]:
  if any(value[group][key]is not False for key in keys):raise ValueError('false claim')
 for group in ['policy','budgets','ownership']:
  for key,item in value[group].items():
   if type(item)not in {bool,int} and (type(item)is not str or not item or len(item)>1024):raise ValueError('bounded description')
class ControlOwnerSourceTests(unittest.TestCase):
 def setUp(self):self.value=json.loads((ROOT/'contracts/control-owner-handoff.v1.json').read_text());self.source=(ROOT/'crates/hepta-peer-attestation/src/control_owner.rs').read_text()
 def test_closed_source_contract(self):check(self.value)
 def test_claim_missing_extra_bound_and_api_mutations_refuse(self):
  for group,keys in KEYS.items():
   for key in keys:
    v=copy.deepcopy(self.value);del v[group][key]
    with self.assertRaises(ValueError):check(v)
   v=copy.deepcopy(self.value);v[group]['unknown']=False
   with self.assertRaises(ValueError):check(v)
  for group,key in [('budgets','maximum_seconds'),('ownership','transaction_count_each_instance')]:
   for bad in [True,21,1.0,'20']:
    v=copy.deepcopy(self.value);v[group][key]=bad
    with self.assertRaises(ValueError):check(v)
  for key in self.value['non_claims']:
   for bad in [True,0,'false']:
    v=copy.deepcopy(self.value);v['non_claims'][key]=bad
    with self.assertRaises(ValueError):check(v)
  for key in API:
   v=copy.deepcopy(self.value);del v['public_api'][key]
   with self.assertRaises(ValueError):check(v)
 def test_actual_default_proc_live_source_and_public_inventory(self):
  self.assertIn('let attestor = ProcfsPeerAttestor::default();',self.source)
  self.assertIn('.attest(peer, &policy.runtime)',self.source)
  self.assertIn('attested.snapshot().executable_sha256 != policy.executable_sha256',self.source)
  self.assertIn('.refresh_snapshot(&self.attestor)',self.source)
  for forbidden in ['ProcfsPeerAttestor::new','attest_with_static','UnixListener','TcpListener','shutdown','std::env','pub stream:','pub channel:','pub fn renew']:
   # "shutdown" exists only in the cancellation doc comment.
   if forbidden=='shutdown':self.assertNotRegex(self.source,r'\.shutdown\s*\(')
   else:self.assertNotIn(forbidden,self.source)
  methods=re.findall(r'pub fn (\w+)\s*\(',self.source)
  self.assertEqual(sorted(methods),sorted(['new','from_accepted','ensure_current','send','cancel','from_control','ensure_current','receive','cancel']))
 def test_native_absolute_capture_and_one_shot_order(self):
  sender=self.source.split('pub fn from_accepted(',1)[1].split('pub fn ensure_current',1)[0]
  ordered=['fixed_deadline(budget)?','AcceptedStreamCustody::capture_before','ControlPeerOwner::admit','HandoffSender::from_control','owner.current()?;']
  positions=[sender.index(item)for item in ordered];self.assertEqual(positions,sorted(positions))
  send=self.source.split('pub fn send(',1)[1].split('pub fn cancel',1)[0]
  compact=''.join(send.split())
  self.assertLess(compact.index('self.custody.take()'),compact.index('.send(custody)'))
  self.assertIn('self.retire()?;',send)
  transport=(ROOT/'crates/hepta-agent-transport/src/accepted_handoff.rs').read_text().split('pub fn capture_before(',1)[1].split('pub fn capture(',1)[0]
  self.assertLess(transport.index('monotonic_nanos()?'),transport.index('Instant::now()'))
  self.assertNotIn('checked_add(budget)',transport)
  self.assertIn('deadline <= Instant::now()',transport)
 def test_default_graph_binaries_services_and_same_target_in_ci(self):
  cargo=tomllib.loads((ROOT/'crates/hepta-peer-attestation/Cargo.toml').read_text());self.assertEqual(cargo['features']['default'],[])
  target=next(t for t in cargo['test']if t['name']=='control_owner_kernel');self.assertIs(target['harness'],False)
  code=(ROOT/'crates/hepta-peer-attestation'/target['path']).read_text()
  for token in ['libc::SOCK_SEQPACKET','ProcfsPeerAttestor::default()','Command::new(std::env::current_exe()','libc::fork()','libc::_exit(0)','/usr/bin/sleep','original.deadline().unwrap()<=entry','inventory()']:
   self.assertIn(token,code.replace(' ','')if token=='original.deadline().unwrap()<=entry'else code)
  self.assertNotIn('#[ignore]',code)
  self.assertIn('ProductHandlerUnavailable',(ROOT/'apps/hepta-agent-portd/src/main.rs').read_text())
  self.assertNotIn('AttestedHandoff',(ROOT/'apps/hepta-agent-portd/src/main.rs').read_text())
  workflow=(ROOT/'.github/workflows/ci.yml').read_text();self.assertGreaterEqual(workflow.count('cargo test --workspace --all-targets --locked'),2)
  custody=(ROOT/'.github/workflows/agent-port-custody.yml').read_text();self.assertIn('apps/hepta-agent-portd crates/hepta-peer-attestation/src',custody)
if __name__=='__main__':unittest.main()
