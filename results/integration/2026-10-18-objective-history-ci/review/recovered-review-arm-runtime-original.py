import collections,hashlib,importlib,json,pathlib,struct,sys,zipfile
from datetime import datetime,timezone
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.exceptions import InvalidSignature
import cryptography
sys.dont_write_bytecode=True
B=pathlib.Path('/workspace/scratch/499c7902de8e'); D=B/'r9-integration'
OUT=pathlib.Path('/tmp/r9-arm-history-review')
prior=json.loads((OUT/'source.json').read_text()); binding=prior['source_binding']['compiled_source_binding']
def need(v,m):
 if not v:raise RuntimeError(m)
def sha(b):return hashlib.sha256(b).hexdigest()
def wire(v):return json.dumps(v,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()
def now():return datetime.now(timezone.utc).isoformat()
started=now()
P=pathlib.Path(prior['zip']['path']);need(sha(P.read_bytes())==prior['zip']['sha256'],'zip identity')
with zipfile.ZipFile(P) as z:raw={n:z.read(n) for n in z.namelist()}
def J(n):return json.loads(raw[n])
def E(n):return 'work/runtime-evidence/'+n
report=J('work/report.json')
lines=raw['work/runtime.log'].splitlines();need(len(lines)==38 and all(l.startswith(b'{') and l.endswith(b'}') for l in lines),'raw38 strictJSON')
records=[json.loads(l) for l in lines]
need(records==report['runtime_records'],'rawreport exact records')
counts=collections.Counter(r['event'] for r in records)
need(dict(counts)=={'owner_running':4,'submission_observed':4,'history_query_observed':13,'objective_history_check':15,'objective_response_discarded':1,'acceptance_pass':1},'event counts')
for n in ['run_objective_history.py','run_original_agentd.py','run_original_objective.py']:
 need(sha((D/'tests/integration/hepta'/n).read_bytes())==binding['probe_inputs'][n],'frozen validator source '+n)
sys.path.insert(0,str(D/'tests/integration/hepta'));history=importlib.import_module('run_objective_history')
history.verify_records(records,binding)
owners=[(i+1,r) for i,r in enumerate(records) if r['event']=='owner_running']
lifecycle=[];owner_by_spawn={}
for i,row in owners:
 v=row['observation'];s=row['spawn_generation'];h=v['health']
 need(s==v['spawn_generation'] and h['ready'] is True and h['promotion_ready'] is True and h['fenced'] is False and h['lifecycle']=='running','owner ready')
 need({'id':'objective.admission.read','major':1,'minor':0} in v['capabilities'],'owner history capability')
 owner_by_spawn[s]=v
 lifecycle.append({'raw_line':i,'spawn_generation':s,'current_generation':v['current_generation'],'pid':h['process_id'],'agent_id':v['agent_id']})
need([v['spawn_generation'] for v in lifecycle]==[1,5,9,13] and len({v['pid'] for v in lifecycle})==4,'3 restarts')
agent=lifecycle[0]['agent_id'];need(all(v['agent_id']==agent for v in lifecycle),'same agent')
trust=J(E('initial-public-trust.json'));revoked=J(E('revoked-public-trust.json'))
need(trust['agent_id']==agent and trust['revoked'] is False and revoked=={**trust,'revoked':True},'only revocation changed')
pubkey=Ed25519PublicKey.from_public_bytes(bytes.fromhex(trust['public_key_hex']))
scope=hashlib.sha256(b'hepta:agentd:signed-objective:v1\0'+agent.encode()).digest()
def sid(s):
 b=s.encode();return struct.pack('>I',len(b))+b
def claims(q):
 return b'hepta.authbus.signed-message.v1\0'+sid(q['issuer_id'])+struct.pack('>Q',q['key_epoch'])+sid(q['message_id'])+sid(agent)+scope+hashlib.sha256(wire(q['body'])).digest()+struct.pack('>QQ',q['sequence'],q['expires_at_ms'])
request_paths=['01-compiled-request.json','02-abstain-request.json','03-lost-response-request.json','05-postpublication-capacity-request.json','14-revoked-negative-request.json']
requests=[];request_reviews=[]
for i,name in enumerate(request_paths,1):
 q=J(E(name));need(wire(q)==raw[E(name)],'exact request serde roundtrip '+name)
 need(q['issuer_id']==trust['issuer_id'] and q['key_epoch']==trust['key_epoch'] and q['sequence']==i,'request issuer/sequence')
 pubkey.verify(bytes.fromhex(q['signature_hex']),claims(q))
 body=q['body'];source=json.loads(body['source_envelope_json'])
 need(source['requestId']=='request.'+body['run_id'] and body['authority_epoch']==1 and body['objective_revision']==1,'request body identity')
 need(source['structuredIntent']['resources']['externalEffectCount']==0 and source['structuredIntent']['resources']['tokenCount']==0 and source['structuredIntent']['resources']['networkBytes']==0,'isolated budget')
 need(body['spawn_generation']==(1 if i<=4 else 13),'original/current submission spawn')
 requests.append(q)
 request_reviews.append({'file':E(name),'request_sha256':sha(raw[E(name)]),'bytes':len(raw[E(name)]),'run_id':body['run_id'],'message_id':q['message_id'],
 'message_sequence':i,'original_spawn_generation':body['spawn_generation'],'expires_at_ms':q['expires_at_ms'],
 'source_observed_at':source['observedAt'],'source_deadline':source['deadline'],'signed_body_digest':sha(wire(body)),
 'signature_hex':q['signature_hex'],'ed25519_valid':True,'claims_sha256':sha(claims(q)),
 'attempt_type':'harness_original_protocol_discarded_response' if i==3 else 'hepta_submit_cli',
 'purpose':'distinct_revoked_negative_not_recovery_retry' if i==5 else 'distinct_initial_objective_request'})
need(len({q['body']['run_id'] for q in requests})==len({q['message_id'] for q in requests})==5,'5 distinct objective identities')
changed=J(E('08-changed-signature-query-input.json'))
need({k:v for k,v in changed.items() if k!='signature_hex'}=={k:v for k,v in requests[0].items() if k!='signature_hex'}
     and changed['signature_hex']!=requests[0]['signature_hex'],'changed signature only')
try:pubkey.verify(bytes.fromhex(changed['signature_hex']),claims(changed))
except InvalidSignature: pass
else:raise RuntimeError('changed signature unexpectedly valid')
submissions=[(i+1,r) for i,r in enumerate(records) if r['event']=='submission_observed']
sub_reviews=[]
for (line,row),qid,q in zip(submissions,[101,102,104,105],[requests[0],requests[1],requests[3],requests[4]],strict=True):
 label=row['label'];result=row['result'];ident=result['identity']
 need(J(E(label+'-stdout.json'))==result and raw[E(label+'-stderr.log')]==b'','actual CLI stdout/stderr '+label)
 need(ident['request_id']==qid and ident['run_id']==q['body']['run_id'] and ident['message_id']==q['message_id'] and ident['sequence']==q['sequence']
      and ident['issuer_id']==q['issuer_id'] and ident['key_epoch']==q['key_epoch'] and ident['expires_at_ms']==q['expires_at_ms'],'CLI original identity '+label)
 for k,v in q['body'].items():
  if k in ident:need(ident[k]==v,'CLI body '+k)
 need(raw[E(label+'-request.json')]==wire(q),'CLI original stdin bytes '+label)
 need(ident['agent_id']==agent and ident['peer_uid']==1001 and ident['peer_pid']==owner_by_spawn[ident['spawn_generation']]['health']['process_id'],'CLI peer')
 frame={'schema_version':2,'request_id':qid,'spawn_generation':ident['spawn_generation'],'method':{'type':'objective_start','request':q}}
 need(len(wire(frame)+b'\n')==result['bytes_written']==result['request_frame_bytes'],'CLI full frame length')
 need(row['exit_code']==(0 if result['status']=='admitted' else 12),'CLI exit')
 sub_reviews.append({'raw_line':line,'label':label,'request_id':qid,'run_id':ident['run_id'],'status':result['status'],'issue':result.get('issue'),
 'exit_code':row['exit_code'],'frame_bytes':len(wire(frame)+b'\n'),'stdout_file':E(label+'-stdout.json'),'input_file':E(label+'-request.json'),
 'peer_pid':ident['peer_pid'],'peer_uid':ident['peer_uid'],'matches_request_and_full_frame':True})
loss_line,loss=next((i+1,r['evidence']) for i,r in enumerate(records) if r['event']=='objective_response_discarded')
loss_frame={'schema_version':2,'request_id':103,'spawn_generation':1,'method':{'type':'objective_start','request':requests[2]}}
actual_loss_frame=raw[E('03-lost-response-frame.jsonl')]
need(json.loads(actual_loss_frame)==loss_frame and actual_loss_frame.endswith(b'\n') and actual_loss_frame.count(b'\n')==1,'saved original loss frame')
need(wire(loss_frame)+b'\n'==actual_loss_frame and len(actual_loss_frame)==loss['bytes_written']==loss['request_frame_bytes']==2815,'loss exact frame')
need(loss['response_bytes_read']==0 and loss['response_discarded_by_harness'] is True and loss['hepta_submit_cli_loss_case'] is False
     and loss['peer_uid']==1001 and loss['peer_pid']==lifecycle[0]['pid'] and loss['run_id']==requests[2]['body']['run_id'],'loss scope')
queries=[(i+1,r) for i,r in enumerate(records) if r['event']=='history_query_observed']
qlabels=['01-compiled','02-abstain','03-covered-by-second','04-lost-response','05-postpublication-capacity','06-wrong-anchor','07-earlier-anchor','08-changed-signature','09-after-restart','10-expired-history','11-rollback-anchor','12-truncated-anchor','13-revoked-history']
qrequest=[0,1,0,2,3,0,1,'changed',2,1,0,3,0]
qids=[201,202,203,204,205,301,302,303,304,308,305,306,307]
qpubs=[1,2,1,3,4,None,None,None,3,2,None,None,1]
qjournal=[1,2,2,3,4,4,4,4,4,4,1,3,3]
journal_names=['01-compiled-journal.bin','02-abstain-journal.bin','03-lost-response-journal.bin','04-full-journal.bin']
journals=[raw[E(n)] for n in journal_names]
pubs={}
for _,row in queries:
 p=row['result'].get('publication')
 if p:
  seq=p['publication_sequence']
  if seq in pubs:need(pubs[seq]==p,'publication content drift')
  else:pubs[seq]=p
need(set(pubs)=={1,2,3,4},'4 publications')
for seq,p in pubs.items():
 q=requests[seq-1];body=q['body']
 need(p['run_id']==body['run_id'] and p['original_spawn_generation']==body['spawn_generation']
      and p['issuer_id']==q['issuer_id'] and p['key_epoch']==q['key_epoch']
      and p['message_id']==q['message_id'] and p['message_sequence']==q['sequence'] and p['expires_at_ms']==q['expires_at_ms']
      and p['signed_body_digest']==sha(wire(body)),'published request exact identity')
 need(p['outcome']['type']==('explicit_abstain' if seq==2 else 'compiled'),'published disposition')
qreviews=[]
for (line,row),label,qi,qid,pseq,jnum in zip(queries,qlabels,qrequest,qids,qpubs,qjournal,strict=True):
 need(row['label']==label,'query ordering');q=changed if qi=='changed' else requests[qi]
 result=row['result'];ident=result['identity'];owner=owner_by_spawn[ident['spawn_generation']]
 need(raw[E(label+'-query-input.json')]==wire(q) and J(E(label+'-query-output.json'))==result and raw[E(label+'-query-stderr.log')]==b'','saved query input/output')
 need(ident['request_id']==qid and ident['agent_id']==agent and ident['peer_uid']==1001 and ident['peer_pid']==owner['health']['process_id'],'query peer/ID')
 need(ident['original_spawn_generation']==q['body']['spawn_generation'] and ident['run_id']==q['body']['run_id']
      and ident['message_id']==q['message_id'] and ident['message_sequence']==q['sequence'] and ident['issuer_id']==q['issuer_id']
      and ident['key_epoch']==q['key_epoch'] and ident['expires_at_ms']==q['expires_at_ms'],'query exact request identity')
 frame={'schema_version':2,'request_id':qid,'spawn_generation':ident['spawn_generation'],'method':{'type':'objective_admission','query':{'request':q,'anchor':result['anchor']}}}
 nbytes=len(wire(frame)+b'\n')
 need(nbytes==result['bytes_written']==result['request_frame_bytes'] and nbytes<=65536,'query complete frame')
 need(row['journal_unchanged'] is True and row['journal_sha256']==sha(journals[jnum-1]),'query readonly journal hash')
 if pseq:
  need(result['status']=='historical_publication' and row['exit_code']==0 and result['publication']==pubs[pseq] and result['response_generation']==owner['current_generation'],'query publication')
  if result['anchor'] is None:need(result['anchor_coverage']=='current_owner_journal','unanchored coverage')
  else:
   anchor=result['anchor'];need(result['anchor_coverage']=='retained_anchor' and anchor['chain_digest']==pubs[anchor['sequence']]['chain_digest'] and anchor['sequence']>=pseq,'retained coverage')
 else:need(result['status']=='unknown' and row['exit_code']==12 and 'publication' not in result and 'response_generation' not in result,'unknown no promotion')
 qreviews.append({'raw_line':line,'label':label,'request_id':qid,'run_id':ident['run_id'],'status':result['status'],'issue':result.get('issue'),
 'publication_sequence':pseq,'anchor':result['anchor'],'anchor_coverage':result.get('anchor_coverage'),'current_spawn':ident['spawn_generation'],
 'original_spawn':ident['original_spawn_generation'],'peer_pid':ident['peer_pid'],'peer_uid':ident['peer_uid'],'response_generation':result.get('response_generation'),
 'full_frame_bytes':nbytes,'journal_sha256':row['journal_sha256'],'journal_unchanged':True,
 'input_file':E(label+'-query-input.json'),'output_file':E(label+'-query-output.json')})
need([q['issue'] for q in qreviews if q['status']=='unknown']==['anchor_mismatch','publication_outside_anchor','no_matching_publication','anchor_missing','anchor_missing'],'5 unknown reasons')
retained=J(E('retained-anchor.json'))
need(retained=={'sequence':4,'chain_digest':pubs[4]['chain_digest']},'saved anchor4')
need([len(j) for j in journals]==[4203,8264,12410,16589] and all(journals[-1].startswith(j) for j in journals),'actual journal prefixes')
class Reader:
 def __init__(self,b):self.b=b;self.pos=0
 def take(self,n):
  need(self.pos+n<=len(self.b),'payload bounds');v=self.b[self.pos:self.pos+n];self.pos+=n;return v
 def u32(self):return int.from_bytes(self.take(4),'big')
 def u64(self):return int.from_bytes(self.take(8),'big')
 def sid(self):return self.take(self.u32()).decode()
 def dig(self):return self.take(32).hex()
def parse_journal(data):
 need(data[:8]==b'HEPTRS01' and hashlib.sha256(data[:40]).digest()==data[40:72],'journal header checksum')
 pos=72;prev=bytes(32);frames=[]
 while pos<len(data):
  size,complement=struct.unpack_from('>II',data,pos);need(size>0 and (size^complement)==0xffffffff,'frame length complement')
  end=pos+size+112;need(end<=len(data),'complete frame')
  frame=data[pos:end];seq=struct.unpack_from('>Q',frame,8)[0];need(seq==len(frames)+1 and frame[16:48]==prev,'frame sequence/chain predecessor')
  payload=frame[48:48+size];chain=frame[48+size:80+size];checksum=frame[-32:]
  need(hashlib.sha256(frame[:-32]).digest()==checksum,'frame checksum')
  pd=hashlib.sha256(payload).digest()
  need(hashlib.sha256(b'hepta.run-start-chain.v1'+prev+struct.pack('>Q',seq)+pd).digest()==chain,'frame chain digest')
  rd=Reader(payload);need(rd.take(len(b'hepta.run-start-record.v2'))==b'hepta.run-start-record.v2','payload v2')
  auth={'issuer_id':rd.sid(),'key_epoch':rd.u64(),'message_id':rd.sid(),'sequence':rd.u64(),'expires_at_ms':rd.u64(),
        'scope_digest':rd.dig(),'signed_body_digest':rd.dig(),'signature_hex':rd.take(64).hex()}
  admission={'profile_id':rd.sid(),'profile_revision':rd.u64(),'profile_digest':rd.dig(),'supplied_source_digest':rd.dig(),
  'intent_digest':rd.dig(),'admitted_source_digest':rd.dig(),'observed_at_unix_micros':rd.u64(),'deadline_unix_micros':rd.u64(),'authority_flags':list(rd.take(8))}
  disposition=rd.u64();run_id=rd.sid()
  snap={k:rd.dig() for k in ['objective_digest','hard_constraint_digest','preference_state_digest','model_tuple_digest','prompt_registry_digest','artifact_set_digest']}
  snap.update(authority_epoch=rd.u64(),generation=rd.u64(),fence_digest=rd.dig(),runtime_body_digest=rd.dig())
  semantic=rd.take(rd.u32());protocol_digest=rd.dig();protocol=rd.take(rd.u32())
  need(rd.pos==len(payload) and sha(semantic)==snap['objective_digest'] and sha(protocol)==protocol_digest,'semantic/protocol digest')
  q=requests[seq-1];p=pubs[seq]
  need(auth=={'issuer_id':q['issuer_id'],'key_epoch':q['key_epoch'],'message_id':q['message_id'],'sequence':q['sequence'],'expires_at_ms':q['expires_at_ms'],
      'scope_digest':scope.hex(),'signed_body_digest':sha(wire(q['body'])),'signature_hex':q['signature_hex']},'persisted exact auth')
  need(p['publication_digest']==pd.hex() and p['chain_digest']==chain.hex() and run_id==p['run_id'] and p['profile_digest']==admission['profile_digest']
       and snap['generation']==owner_by_spawn[q['body']['spawn_generation']]['current_generation'] and p['outcome']['objective_digest']==snap['objective_digest']
       and p['outcome']['hard_constraint_digest']==snap['hard_constraint_digest'],'persisted publication/anchor')
  need(disposition==(1 if seq==2 else 0) and not any(admission['authority_flags']),'persisted deny-all disposition')
  for k in ['preference_state_digest','model_tuple_digest','prompt_registry_digest','artifact_set_digest','authority_epoch','runtime_body_digest']:
   need(snap[k]==q['body'][k],'persisted snapshot '+k)
  source=json.loads(q['body']['source_envelope_json'])
  need(admission['intent_digest']==source['intentDigest'],'admitted intent')
  frames.append({'sequence':seq,'start_byte':pos,'end_byte_exclusive':end,'payload_bytes':size,'publication_digest':pd.hex(),'chain_digest':chain.hex(),
                 'predecessor_chain_digest':prev.hex(),'frame_checksum':checksum.hex(),'run_id':run_id,'authentication':auth,'admission':admission,
                 'snapshot':snap,'disposition':'explicit_abstain' if disposition else 'compiled','semantic_sha256':sha(semantic),
                 'objective_function_protocol_sha256':protocol_digest,'protocol_bytes':len(protocol),'all_cross_bindings_passed':True})
  pos=end;prev=chain
 return frames
frames=parse_journal(journals[3]);need([f['end_byte_exclusive'] for f in frames]==[len(j) for j in journals],'prefixes complete frame ends')
need(len(frames)==4,'four exact journal publications')
for i,j in enumerate(journals,1):need(len(parse_journal(j))==i,'prefix frame count')
faults={}
for label,prefix,before_bytes,injected,recovered in [
 ('rollback_retained_anchor_unknown','11-rollback-prefix',journals[3],journals[0],journals[0]),
 ('truncated_tail_retained_anchor_unknown','12-truncated-tail',journals[0],journals[3][:-1],journals[2])]:
 core=next(r['evidence'] for r in records if r.get('check')==label);fault=core['fault']
 for suffix,value in [('before',before_bytes),('injected',injected),('recovered',recovered)]:
  name=E(prefix+'-'+suffix+'-journal.bin')
  need(raw[name]==value and sha(value)==fault[suffix+'_sha256'],'fault exact bytes '+name)
 need(fault['injected_bytes']==len(injected) and fault['recovered_bytes']==len(recovered) and fault['owner_confirmed_stopped_before_fault'] is True and fault['recovery_owner']=='original_agentd','fault bytes/stop')
 need(fault['new_pid']==owner_by_spawn[fault['new_spawn']]['health']['process_id'],'fault restart PID')
 faults[label]={'raw_check_evidence':core,'before_file':E(prefix+'-before-journal.bin'),'injected_file':E(prefix+'-injected-journal.bin'),
 'recovered_file':E(prefix+'-recovered-journal.bin'),'injected_matches_exact_expected_bytes':True,'recovered_matches_complete_original_prefix':True}
cores={r['check']:r['evidence'] for r in records if r['event']=='objective_history_check'}
expiry=cores['expired_request_history_still_published']
need(expiry['expires_at_ms']==requests[1]['expires_at_ms']==1792322893326 and expiry['observed_at_ms']==1792322893335
     and expiry['observed_at_ms']-expiry['expires_at_ms']==9 and expiry['wait_elapsed_ms']==24360 and expiry['wait_bound_ms']==30000,'actual expiry clock values')
need(raw[E('10-expired-history-query-input.json')]==raw[E('02-abstain-request.json')],'expiry unchanged envelope')
post=cores['postpublication_submit_unknown_history_published']
need(post['submission']['status']=='submit_unknown' and post['submission']['issue']=='objective_owner_request_rejected' and post['run_status'] is None
     and post['history']['publication']==pubs[4] and post['specific_original_error_bytes_observed'] is False,'postpub direct observations')
need(post['active_run_ids']==[requests[0]['body']['run_id'],requests[2]['body']['run_id']]
     and all(r['phase']=='admitted' and r['terminal_observed'] is False and r['generation']==2 for r in post['active_runs_before_submission']),'postpub two active')
restart=cores['restart_projection_missing_history_published']
need(restart['old_spawn']==1 and restart['new_spawn']==5 and restart['old_pid']==lifecycle[0]['pid'] and restart['new_pid']==lifecycle[1]['pid'],'normal restart')
need(cores['revoked_issuer_history_still_published']['history']['publication']==pubs[1] and cores['revoked_issuer_history_still_published']['issuer_restored'] is False
     and cores['revoked_new_submission_rejected']['journal_unchanged'] is True and cores['controlled_stop']['active'] is False,'revoke/no append/stop')
profile=raw[E('admission-profile.json')]
need(profile==raw['work/probe/src/original_objective_profile.json'],'profile bytes unchanged')
accept=records[-1];need(accept['event']=='acceptance_pass' and accept['recovery_resubmissions']==0 and accept['objective_request_attempts']==5 and accept['published_objective_requests']==4,'final scope counts')
need(sha(P.read_bytes())==prior['zip']['sha256'],'archive mutated')
review={'schema_version':1,'review_part':'actual_runtime_signatures_journal','started_at_utc':started,'completed_at_utc':now(),
 'raw_record_identity':{'report_member':'work/report.json','report_sha256':sha(raw['work/report.json']),'runtime_member':'work/runtime.log','runtime_bytes':len(raw['work/runtime.log']),
 'runtime_sha256':sha(raw['work/runtime.log']),'strict_json_line_count':38,'all_38_raw_records_equal_report':True,
 'per_line':[{'line':i+1,'event':r['event'],'check':r.get('check'),'label':r.get('label'),'line_sha256':sha(lines[i])} for i,r in enumerate(records)]},
 'frozen_python_verify_records':{'result':'passed','source_sha256':binding['probe_inputs']['run_objective_history.py'],'entrypoint':'verify_records(records, expected_binding)','runtime_replayed':False},
 'counts':{'raw_records':38,**counts,'original_objective_request_attempts':5,'distinct_objective_run_ids':5,'distinct_objective_message_ids':5,'publications':4,'compiled_publications':3,'explicit_abstain_publications':1,
 'controlled_supervisor_restarts':3,'recovery_resubmissions':0,'history_positive_results':8,'history_unknown_results':5},
 'checks':[{'raw_line':i+1,'name':r['check'],'result':'passed','evidence_source':'work/runtime.log'} for i,r in enumerate(records) if r['event']=='objective_history_check'],
 'owner_lifecycle':lifecycle,'requests':request_reviews,'cli_submissions':sub_reviews,'history_queries':qreviews,'publications':[pubs[i] for i in range(1,5)],
 'signature_verification':{'cryptography_version':cryptography.__version__,'method':'Ed25519 canonical hepta.authbus.signed-message.v1 preimage from pinned source; public key only',
 'initial_public_trust_file':E('initial-public-trust.json'),'public_key_hex':trust['public_key_hex'],'subject_agent_id':agent,'scope_digest':scope.hex(),
 'all_five_saved_requests_verify':True,'exact_saved_request_bytes_roundtrip':True,'changed_signature_alone_invalid':True,
 'references':['codex-rs/hepta-authbus/src/signed.rs:38-49','codex-rs/hepta-authbus/src/lib.rs:228-231','tests/integration/hepta/original_objective_fixture.rs:149-165'],
 'private_signing_key_read':False,'meaning':'Independent offline byte verification corroborates the recorded isolated requests; it grants no authority.'},
 'journal':{'magic':'HEPTRS01','header_bytes':72,'header_binding_digest':journals[3][8:40].hex(),'header_checksum_valid':True,
 'frame_encoding_reference':'codex-rs/hepta-learning-ledger/src/run_start.rs:675-719,895-914,918-1023,1049-1080',
 'publication_frames':frames,'frame_lengths_complements_checksums_and_chains_all_valid':True,'persisted_authentication_exactly_matches_all_four_signed_requests':True,
 'all_four_publication_digests_and_anchors_match_decoded_journal':True,'generation_semantics':'The authenticated request body retains original spawn_generation 1; the durable run snapshot generation is current owner generation 2. These are distinct source-defined fields.','deny_all_authority_flags_for_all_four':True,
 'saved_prefixes':[{'member':E(n),'bytes':len(j),'sha256':sha(j),'complete_frames':i+1} for i,(n,j) in enumerate(zip(journal_names,journals,strict=True))],
 'retained_anchor_file':E('retained-anchor.json'),'retained_anchor':retained,'stopped_storage_faults':faults},
 'harness_response_loss':{'raw_line':loss_line,'evidence':loss,'saved_frame_file':E('03-lost-response-frame.jsonl'),'saved_frame_sha256':sha(actual_loss_frame),'decoded_request_id':103,
 'history_query_attempts':cores['harness_lost_response_then_history']['history_query_attempts'],'resubmission_count':0,
 'scope':'Harness verified peer identity, wrote one complete original request frame, then intentionally discarded the response without reading any bytes. This is not a hepta-submit CLI lost-reply execution against the original owner.'},
 'postpublication_case':{'observed_generic_submission':post['submission'],'observed_history_publication_sequence':4,'observed_current_run_status':post['run_status'],
 'observed_prior_active_runs':post['active_runs_before_submission'],'specific_original_error_bytes_observed':False,
 'source_inference':post['source_inference'],'inference_scope':'Fixed original default run capacity is two. The third fresh compiled Objective publishes before run admission; CapacityExceeded is a source-supported attribution, not a captured CLI error string.','resubmission_count':0},
 'expiry_case':{'expires_at_ms':expiry['expires_at_ms'],'expires_at_utc':datetime.fromtimestamp(expiry['expires_at_ms']/1000,timezone.utc).isoformat(),
 'observed_at_ms':expiry['observed_at_ms'],'observed_at_utc':datetime.fromtimestamp(expiry['observed_at_ms']/1000,timezone.utc).isoformat(),'observed_after_expiry_ms':9,
 'wait_elapsed_ms':24360,'wait_bound_ms':30000,'original_envelope_bytes_and_signature_unchanged':True,'query_publication_sequence':2,'anchor_sequence':4,
 'admitted_before_expiry':'Actual initial CLI admitted and matching publication #2; fixed probe checks before first submission after re-signing the shortened expiry.',
 'resubmission_count':0},
 'revocation_case':{'only_public_trust_revoked_flag_changed':True,'original_history_remained_publication':1,'retained_anchor_sequence':1,'issuer_restored':False,
 'new_negative_request':request_reviews[4]['run_id'],'new_request_has_valid_original_fixture_signature':True,'new_request_current_spawn':13,
 'new_request_status':sub_reviews[-1]['status'],'new_request_issue':sub_reviews[-1]['issue'],'journal_unchanged':True,'purpose':'distinct_revoked_negative_not_recovery_retry'},
 'acceptance_scope':accept,
 'limits':['Three controlled Supervisor restarts: one normal restart and two stopped-owner journal mutations. Abrupt process death, power loss and storage durability faults were not executed.',
 'The record logs contain probe observations guarded by the pinned compiled source; individual raw RunStatus and stop-control replies are not separately archived.',
 'Retained caller anchors were preserved independently of owner rollback/truncation. Joint rollback of caller anchor and owner journal was not executed.',
 'Historical publication is not current run liveness, new authorization, resumption or proof of a device effect.',
 'The run uses an isolated issuer and no model turn, Operations dispatch, device effect, canonical intelligence or kernel G1/G2 execution.',
 'The five Objective request identities must not be described as Operations K or D.'],
 'review_actions':{'rust_executed':False,'runtime_replayed':False,'downloaded_elf_executed':False,'downloaded_scripts_executed':False,'source_modified':False,'prior_artifact_modified':False}}
(OUT/'runtime.json').write_text(json.dumps(review,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'status':'passed_actual_arm_runtime_review','counts':review['counts'],'expiry_case':review['expiry_case'],'journal_frame_digest_binding':True,'five_signature_valid':True,'temporary_section':str(OUT/'runtime.json')},ensure_ascii=False))
