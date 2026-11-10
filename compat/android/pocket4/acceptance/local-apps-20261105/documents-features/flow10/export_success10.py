#!/usr/bin/python3 -I
"""Project only completed Docs10 identity and owned confirmation records; no Main calls."""
from pathlib import Path
import hashlib,json,os,re,stat
ROOT=Path('/home/alex/work/pocket4-documents-features-flow-20261105-r12-10')
RESULT_SHA='59860aba0b6e576b271566c92133e2233a1d3f14383a6183b1536c9198720853'
LABELS={'target-packages-before','target-packages-after','target-permissions-before','target-permissions-after',
 'delete-copies-dialog-or-result','delete-final-dialog-or-result','delete-copies-confirm-intent',
 'delete-copies-confirm-response','delete-final-confirm-intent','delete-final-confirm-response',
 'final-helper-grants-empty','released-grants-after-normal-reopen','final-task-set'}
def need(v,reason):
 if not v:raise RuntimeError(reason)
def digest(v):return hashlib.sha256(v).hexdigest()
def read(p,cap):
 fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
 try:
  a=os.fstat(fd);need(stat.S_ISREG(a.st_mode) and a.st_uid==0 and a.st_nlink==1 and 0<a.st_size<=cap,'BOUNDED_ROOT_RECORD')
  raw=b''
  while len(raw)<a.st_size:
   b=os.read(fd,min(65536,a.st_size-len(raw)));need(b,'SHORT_READ');raw+=b
  z=os.fstat(fd);need(all(getattr(a,k)==getattr(z,k) for k in ('st_dev','st_ino','st_mode','st_uid','st_gid','st_size','st_nlink','st_mtime_ns','st_ctime_ns')),'RECORD_CHANGED')
  return raw
 finally:os.close(fd)
def main():
 need(os.geteuid()==0 and ROOT.resolve()==ROOT,'FIXED_ROOT_REQUIRED')
 raw=read(ROOT/'result.json',65536);need(digest(raw)==RESULT_SHA,'EXACT_TERMINAL_REQUIRED');result=json.loads(raw)
 need(result['business_scope_completed'] and not result['outcome_unknown'] and result['task_set_restored']
  and not result['cleanup']['errors'],'ACTUAL_CLEAN_SUCCESS_REQUIRED')
 directory=ROOT/'ui';a=os.stat(directory,follow_symlinks=False)
 need(stat.S_ISDIR(a.st_mode) and a.st_uid==0 and not a.st_mode&0o022,'ROOT_OWNED_JOURNAL')
 names=os.listdir(directory);need(len(names)<=10000,'JOURNAL_BOUND');records={};original={};total=0
 for name in sorted(names):
  m=re.fullmatch(r'\d{3,5}-(.+)\.json',name)
  if m is None or m[1] not in LABELS:continue
  label=m[1];need(label not in records,'DUPLICATE_SELECTED_LABEL')
  raw=read(directory/name,262144);total+=len(raw);need(total<=1048576,'SELECTED_BYTES_BOUND')
  v=json.loads(raw);original[label]=v
  entry={'record_name':name,'original_bytes':len(raw),'original_sha256':digest(raw)}
  if label.endswith('dialog-or-result'):
   nodes=v.get('native',{}).get('nodes',[])
   selected=[n for n in nodes if n.get('resource-id') in ('com.android.documentsui:id/alertTitle','android:id/message','android:id/button1','android:id/button2','com.android.documentsui:id/buttonPanel')]
   need(4<=len(selected)<=6,'EXPECTED_OWNED_DIALOG_COMPONENTS')
   entry['value']={'ok':v.get('ok'),'outcome_unknown':v.get('outcome_unknown'),'scope':v.get('screenshot',{}).get('scope'),'nodes':selected}
  elif 'permissions' in label:entry['value']={'permissions_content_omitted':True}
  elif label.endswith('-confirm-intent'):
   entry['value']={'kind':v['kind'],'node':v['node'],'automatic_retry':v['automatic_retry'],
    'request':{k:v['request'][k] for k in ('op','package','display','window_token','frame_sha256','scope_sha256','context_token') if k in v['request']}}
  elif label=='final-task-set':entry['value']={'tasks':v['tasks']}
  else:entry['value']=v
  records[label]=entry
 need(set(records)==LABELS,'EXACT_SELECTED_RECORD_SET_REQUIRED')
 need(original['target-packages-before']==original['target-packages-after'],'PACKAGE_IDENTITY_CHANGED')
 need(original['target-permissions-before']==original['target-permissions-after'],'PERMISSION_STATE_CHANGED')
 need(original['final-task-set']['tasks']==[851] and original['final-helper-grants-empty']['empty'] is True
  and original['released-grants-after-normal-reopen']['empty'] is True,'FINAL_TASK_OR_GRANT_MISMATCH')
 z=os.stat(directory,follow_symlinks=False);need((a.st_dev,a.st_ino,a.st_uid,a.st_gid,a.st_mode)==(z.st_dev,z.st_ino,z.st_uid,z.st_gid,z.st_mode),'JOURNAL_REPLACED')
 need(digest(read(ROOT/'result.json',65536))==RESULT_SHA,'TERMINAL_CHANGED')
 out={'schema':'pocket4-documents10-saved-success-selection-v1','state':'ACTUAL_IDENTITY_AND_OWNED_DELETE_CONFIRMATIONS_COLLECTED',
  'original_result_sha256':RESULT_SHA,'records':records,'identities_equal':True,'permissions_equal':True,
  'Main_commands':0,'UI_actions':0,'provider_writes':0,'package_mutations':0,'image_or_user_document_export':False}
 encoded=json.dumps(out,sort_keys=True,indent=2);need(len(encoded.encode())<=65536,'OUTPUT_BOUND');print(encoded)
if __name__=='__main__':main()
