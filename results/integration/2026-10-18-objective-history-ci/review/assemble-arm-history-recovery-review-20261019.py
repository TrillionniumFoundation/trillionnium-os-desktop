import hashlib,json,pathlib
from datetime import datetime,timezone
B=pathlib.Path('/workspace/scratch/499c7902de8e')
T=pathlib.Path('/tmp/r10-arm-history-review')
E=B/'r9-evidence/ci'
def sha(v):return hashlib.sha256(v).hexdigest()
def read(name):return json.loads((E/name).read_text())
def rec(path):
 value=path.read_bytes()
 return {'path':str(path),'bytes':len(value),'sha256':sha(value)}
a=json.loads((T/'source.json').read_text())
b=json.loads((T/'runtime.json').read_text())
acquisition=read('arm-history-recovery-acquisition-20261019.json')
if (a['zip']['sha256']!=acquisition['sha256'] or a['zip']['bytes']!=acquisition['bytes']
    or a['source_binding']['compiled_source_binding']!=b['acceptance_scope']['source_binding']):
 raise RuntimeError('reconstruction input binding mismatch')
a['elf_byte_review_scope']='This new recovery review binds the five reported binary identities to the restored runtime/build receipts. It does not newly read or execute the large ELF archive; root handles that separate recovery and byte review.'
scripts=[rec(E/n) for n in [
 'recovered-review-arm-source-original.py','recovered-review-arm-runtime-original.py',
 'review-arm-source-recovery-20261019.py','review-arm-runtime-recovery-20261019.py',
 'assemble-arm-history-recovery-review-20261019.py']]
metadata_inputs=[rec(E/n) for n in ['arm-history-recovery-acquisition-20261019.json',
 'arm-history-recovery-github-metadata-20261019.json','arm-history-recovery-jobs-20261019.json']]
review={
 'schema':'r10.recovered-arm-history-artifact-review.v1','schema_version':1,
 'status':'passed_rebuilt_review_of_original_arm_history_artifact',
 'reviewer':'r9_g1_contract_independent_recovery_review',
 'recovery_review_date':'2026-10-19','started_at_utc':a['started_at_utc'],
 'completed_at_utc':datetime.now(timezone.utc).isoformat(),
 'original_execution_date':'2026-10-18','source_run_id':39115155092,'run_attempt':1,'source_job_id':117655596136,
 'source_evidence_class':'actual_original_ARM64_owner_objective_admission_history_under_isolated_test_issuer',
 'findings':[],'blocking_findings':[],
 'recovery_integrity':{
  'original_evidence_zip_recovered_byte_for_byte':True,
  'original_artifact_id':12134664375,'original_evidence_zip_bytes':852554,
  'original_evidence_zip_sha256':'2717d25e42c9a1329e07bce92459db89a3109f72313ebac3e6010ddc8f1accd4',
  'original_report_sha256':'703545addc305db4fb055a801b4b9bfa7b4e5cb088fb8179b92f9b106aef9ca3',
  'original_runtime_log_sha256':'6fc446ae2d0928c2c2096ee22b4cdb64442da3aa5c5c4f5ad82c11c1a022c48b',
  'original_review_scripts_recovered_from_functions_store_exactly':True,
  'lost_previous_final_receipt':{
   'former_path':'r9-evidence/ci/arm-history-artifact-review.json','bytes_as_recorded_in_prior_tool_output':144684,
   'sha256_as_recorded_in_prior_tool_output':'eb6e0e09077dfc337d09c28c8537d5d0a7f066a9c5b4e87d654363cc84bd7d26',
   'full_bytes_recovered':False,'old_digest_applied_to_this_new_receipt':False,
   'historical_reference_source':'Prior tool result in this conversation; this reference does not reconstruct or revalidate the lost final receipt bytes.'},
  'new_review_has_new_timestamps_and_digest':True,
  'prior_20261018_api_snapshot_bytes_recreated':False,
  'api_basis':'New 2026-10-19 read-only GitHub API observations for the same fixed run, attempt, job and artifact.'},
 'recovery_acquisition':acquisition,
 'summary':{'zip_entries':99,'desktop_pinned_blob_inputs':35,'owner_contract_pinned_blob_inputs':36,
  'probe_compiled_inputs':8,'shared_original_lock_identities':735,'resolved_metadata_packages':736,
  'raw_records':38,'checks':15,'history_queries':13,'history_positive_results':8,'history_unknown_results':5,
  'distinct_objective_requests':5,'cli_submissions':4,'harness_original_protocol_submissions':1,
  'publications':4,'compiled_publications':3,'explicit_abstain_publications':1,
  'controlled_supervisor_restarts':3,'recovery_resubmissions':0,
  'actual_expiry_wait_ms_in_original_run':24360,'history_observed_after_original_expiry_ms':9,
  'five_signatures_valid':True,'journal_frames_independently_decoded_and_bound':4,
  'peer_uid_in_original_run':1001,'official_original_job_success_steps':14},
 'source_and_archive_review':a,
 'actual_runtime_evidence_review':b,
 'recovered_and_adapted_review_scripts':scripts,
 'new_recovery_api_and_acquisition_inputs':metadata_inputs,
 'script_adaptations':{
  'original_store_scripts_preserved':True,
  'new_execution_copies_use_temporary_output':'/tmp/r10-arm-history-review',
  'new_source_execution_copy_uses_api_snapshots':['arm-history-recovery-github-metadata-20261019.json','arm-history-recovery-jobs-20261019.json'],
  'verification_logic_changed':False,
  'header_added':'Recovery date and explicit distinction from lost prior receipt',
  'source_and_old_pin_modified':False},
 'elf_recovery_scope':{
  'five_reported_identities_verified_against_original_build_and_runtime_paths':True,
  'new_read_of_large_elf_archive_by_this_agent':False,
  'new_actual_elf_byte_review_by_this_agent':False,
  'delegated_to':'root',
  'companion_needed_for_new_byte_level_ELF_recovery_claim':True},
 'review_operations':{
  'new_read_only_network_download_and_api_observations':True,
  'original_zip_crc_and_hash_reads':True,'fixed_git_blobs_read':True,
  'fixed_python_verify_records_called':True,
  'fixed_python_verify_runner_lock_called_on_temporary_copies_of_archived_locks':True,
  'metadata_logs_parsed_without_running_cargo':True,
  'public_key_only_ed25519_verification':True,'run_start_frame_decode_checksums_and_chains':True,
  'runtime_replayed':False,'rust_or_cargo_executed':False,'downloaded_scripts_or_elfs_executed':False,
  'source_repository_modified':False,'prior_published_artifacts_modified':False,
  'lost_old_file_claimed_as_originally_recovered':False,
  'new_delivery_addendum_text_reviewed':False},
 'non_claims':[
  'This is a new read-only review of the exact original ARM64 artifact. The 2026-10-18 runtime was not executed again on the recovery date.',
  'The 144684-byte prior final JSON was lost. Its digest is retained only as a historical reference; this newly assembled JSON has its own digest.',
  'Successful Objective publication history does not grant current authority, prove a live run, or demonstrate an Operations/device effect.',
  'The observed post-publication error is generic objective_owner_request_rejected. CapacityExceeded remains a source-supported inference from two active runs and the fixed default capacity.',
  'The lost response was discarded by the original-protocol harness, not by executing the original-owner hepta-submit CLI lost-reply fault.',
  'The three restarts and two storage mutations occurred after controlled owner stops. Abrupt crash, power loss and joint caller-anchor/journal rollback were not exercised.',
  'Production issuer, model turn, historical run resumption, Operations K/D, device effects, canonical intelligence and Asterinas G1/G2 were not exercised.',
  'Five binary identities are read from the restored original receipts here. Actual large-ELF byte recovery and its independent review remain separately owned by root.',
  'This review does not infer a new GitHub test execution, completion of unrelated required aggregates, or any PR merge.'
 ]}
out=E/'arm-history-artifact-review-rebuilt-20261019.json'
with out.open('x') as f:json.dump(review,f,ensure_ascii=False,indent=2);f.write('\n')
value=out.read_bytes()
print(json.dumps({'path':str(out),'bytes':len(value),'sha256':sha(value),'status':review['status'],'recovery_review_date':review['recovery_review_date'],'summary':review['summary']},ensure_ascii=False))
