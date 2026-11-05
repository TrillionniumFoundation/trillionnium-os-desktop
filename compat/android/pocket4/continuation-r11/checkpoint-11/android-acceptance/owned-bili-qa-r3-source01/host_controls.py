#!/usr/bin/env python3
"""Actual Python contract/sequence controls with explicit owned synthetic data.

No Android API, app/UI input, device process, or public/private service is used.
"""
import base64
import copy
import gzip
import hashlib
import json
from pathlib import Path
import types

HERE=Path(__file__).resolve().parent

def load(path,name):
 m=types.ModuleType(name);m.__file__=str(path);exec(compile(path.read_bytes(),str(path),'exec'),m.__dict__);return m

def run():
 q=load(HERE/'source/qa_contract.py','actual_r3_contract')
 a=load(HERE/'source/qa_adapter.py','actual_r3_adapter')
 old=load(HERE.parent/'owned-bili-qa-r2-window-01/source/qa_contract.py','actual_r2_contract')
 results=[]
 def passed(name,**extra):results.append({'control':name,'passed':True,**extra})
 def reject(call,code=None):
  try:call()
  except (q.ProtocolError,old.ProtocolError,RuntimeError) as e:
   if code:assert str(e)==code,(code,str(e))
   return
  raise AssertionError('accepted malformed input')
 def node(path='0',editable=False):
  n={'package':q.PACKAGE,'path':path,'class':'android.widget.EditText' if editable else 'android.view.View',
     'resource_id':'tv.danmaku.bili:id/owned_fixture_search' if editable else '',
     'text':'','content_desc':'','enabled':True,'visible':True,'password':False,'clickable':True,
     'editable':editable,'supports_set_text':editable,'focused':False,'selected':False,'checked':False,
     'child_count':0,'bounds':[0,0,100,100]}
  for key in ['class','resource_id','text','content_desc']:
   n[key+'_truncated']=False;n[key+'_sha256']=q.sha(n[key].encode())
  n['node_sha256']=q.sha(q.canonical(n));return n
 def inspection(count=1,depth=None,editable=False):
  rows=[node('0' if i==0 else '0/'+str(i//64)+'/'+str(i%64),editable and i==0) for i in range(count)]
  if depth is not None:rows[-1]=node('0'+'/0'*depth,False)
  win={'package':q.PACKAGE,'display':0,'type':1,'focused':True,'bounds':[0,0,100,100]}
  return {'complete':True,'traversal':'visible-non-password-subtrees','window':win,'window_sha256':q.sha(q.canonical(win)),
    'nodes':rows,'tree_sha256':q.sha(q.canonical(rows)),'observed_elapsed_ms':10,'connection_scoped_window_id':7}
 # Full source parser, not a mirror of its length/depth logic.
 fixture=inspection(129);reject(lambda:old.inspect_record(fixture),'COMPLETE_TREE_HASH_FAILED');q.inspect_record(fixture)
 passed('actual_r2_129_nodes_rejected_r3_accepts_complete_owned_fixture')
 q.inspect_record(inspection(512,32));reject(lambda:q.inspect_record(inspection(513)),'COMPLETE_TREE_HASH_FAILED')
 reject(lambda:q.inspect_record(inspection(2,33)),'NODE_SCOPE_OR_PATH_FAILED')
 passed('actual_r3_512_nodes_depth32_boundaries_and_overflow_rejections')
 def wire(raw):return base64.b64encode(gzip.compress(raw,mtime=0)).decode()
 raw=b'X'*q.MAX_RESULT;assert q.decode_wire(wire(raw))==raw
 reject(lambda:q.decode_wire(wire(raw+b'X')),'SINGLE_BOUNDED_COMPLETE_GZIP_MEMBER_REQUIRED')
 passed('actual_decoder_exact_512KiB_and_512KiB_plus_one')
 z=gzip.compress(b'owned-fixture',mtime=0)
 malformed=[z[:-1],z[:-5]+bytes([z[-5]^1])+z[-4:],z+b'trailing',z+z,b'not gzip']
 for value in malformed:reject(lambda value=value:q.decode_wire(base64.b64encode(value).decode()))
 reject(lambda:q.decode_wire(base64.b64encode(b'Z'*(q.MAX_COMPRESSED_WIRE+1)).decode()))
 passed('actual_decoder_crc_truncation_multimember_tail_non_gzip_and_compressed_bound')
 req={'protocol':q.PROTOCOL,'nonce':'1'*32,'op':'state'}
 state={'accessibility_enabled':False,'touch_exploration_enabled':False,'enabled_service_count':0,'enabled_services_sha256':q.sha(b'[]')}
 value={'protocol':q.PROTOCOL,'nonce':req['nonce'],'op':'state','request_sha256':q.sha(q.canonical(req)),
  'wire_codec':'gzip-canonical-json-v1','self_uid':12000,'self_pid':1234,'ok':True,'error':None,'secondary_errors':[],
  'claim_persistence_completed':True,'helper_work_completed':True,'automatic_retry':False,'business_success_verified':False,
  'accessibility_mode_restoration_verified':None,'started_elapsed_ms':10,'finished_elapsed_ms':11,
  'restoration':{'service_info_verified':True,'service_info_captured':False},'action_attempted':False,'outcome_unknown':False,
  'ui_automation_connected':False,'requires_post_termination_state_check':False,'state':state,'window_observation':{},'tree_observations':[]}
 def stdout(finish=-1,key='owned_qa_result_gzip_base64'):
  return ('INSTRUMENTATION_RESULT: '+key+'='+wire(q.canonical(value))+'\nINSTRUMENTATION_CODE: '+str(finish)+'\n').encode()
 assessed=q.parse_completed(stdout(),b'',0,req,12000);assert assessed['wire_sha256']==q.sha(q.canonical(value))
 reject(lambda:q.parse_completed(stdout(0),b'',0,req,12000),'EXACT_SUCCESSFUL_FINISH_REQUIRED')
 reject(lambda:q.parse_completed(stdout(key='owned_qa_result_base64'),b'',0,req,12000),'EXACT_SUCCESSFUL_FINISH_REQUIRED')
 reject(lambda:q.parse_completed(stdout(),b'',0,req,10165),'INSTALLED_HELPER_IDENTITY_REQUIRED')
 passed('actual_gzip_state_parser_strict_finish_no_old_wire_or_old_UID_fallback')
 scope={'package':q.PACKAGE,'uid':q.UID,'user':0,'display':0,'activity':'tv.danmaku.bili/OwnedFixture',
        'window_token':'123','main_epoch_sha256':q.MAIN_EPOCH}
 edit=inspection(editable=True);selector={'resource_id':'tv.danmaku.bili:id/owned_fixture_search','class':'android.widget.EditText'}
 target=q.select_unique_editable(edit,selector)
 request={'protocol':q.PROTOCOL,'nonce':'2'*32,'op':'set_text','scope':scope,'inspection_nonce':'3'*32,
          'inspection_sha256':'4'*64,'value':q.PUBLIC_SEARCH_QUERY,**target}
 q.validate_request(request)
 for key,bad in [('value','another query'),('node_resource_id','other.package:id/search')]:
  altered={**request,key:bad};reject(lambda altered=altered:q.validate_request(altered))
 passed('actual_set_text_contract_only_fixed_public_query_and_bili_resource')
 for flag in ['editable','supports_set_text','visible','enabled']:
  altered=copy.deepcopy(edit);altered['nodes'][0][flag]=False
  if flag=='visible':
   n=altered['nodes'][0];n['content_redacted']=True
   for k in ['text','content_desc']:
    for suffix in ['', '_sha256','_truncated']:n.pop(k+suffix,None)
  n=altered['nodes'][0];n['node_sha256']=q.sha(q.canonical({k:v for k,v in n.items() if k!='node_sha256'}))
  altered['tree_sha256']=q.sha(q.canonical(altered['nodes']))
  reject(lambda altered=altered:q.select_unique_editable(altered,selector),'EDIT_SELECTOR_NOT_UNIQUE_AND_ELIGIBLE')
 passed('actual_edit_selector_rejects_uneditable_unadvertised_hidden_disabled')
 counter={'capture':1,'purpose':'inspection','node_limit':512,'depth_limit':32,'child_limit':64,
  'json_byte_limit':q.MAX_RESULT-65536,'attempted_nodes':1,'emitted_nodes':1,'max_attempted_depth':0,
  'max_observed_children':0,'serialized_bytes':len(q.canonical(edit)),'complete':True,'began_elapsed_ms':10,'last_elapsed_ms':11}
 q.tree_observations([counter],'inspect',True)
 partial={**counter,'complete':False,'attempted_nodes':513,'emitted_nodes':512,'serialized_bytes':0}
 q.tree_observations([partial],'inspect',False)
 reject(lambda:q.tree_observations([partial],'inspect',True),'PARTIAL_TREE_CANNOT_QUALIFY')
 reject(lambda:q.tree_observations([{**counter,'ui_text':'private'}],'inspect',True),'EXACT_SAFE_TREE_COUNTERS_REQUIRED')
 passed('actual_safe_counter_parser_preserves_partial_failure_rejects_success_and_UI_fields')
 # Exercise the actual sequence method; only device interfaces are explicit seams.
 plan={'schema':1,'operation':'set_text','selector':selector,'value':q.PUBLIC_SEARCH_QUERY,
       'nonces':dict(before='5'*32,inspect='6'*32,action='7'*32,after='8'*32)}
 a.validate_plan(plan,q)
 for fail_action in [False,True]:
  session=a.Session.__new__(a.Session);session.qa=q
  session.installed=lambda:{'owned-fixture':True};session.task=lambda:{'owned-task':True};session.foreground=lambda:scope
  calls=[]
  def instrument(request):
   calls.append(request['op'])
   helper={'op':request['op'],'nonce':request['nonce'],'self_uid':12000,'state':state,
      'ui_automation_connected':False,'accessibility_state_before_connection':state,'restoration':{'service_info_verified':True}}
   if request['op']=='inspect':helper['inspection']=edit
   if request['op']=='set_text':
    assert request['value']==q.PUBLIC_SEARCH_QUERY and request['node_resource_id']==selector['resource_id']
    if fail_action:raise RuntimeError('OWNED_ACTION_FAILURE')
    helper['action_window']=edit['window']
   return {'helper':helper,'wire_sha256':q.sha(q.canonical(request))}
  session.instrument=instrument
  if fail_action:
   reject(lambda:session.sequence(plan),'OWNED_ACTION_FAILURE')
   assert session.sequence_observation['after_state_completed'] is True and session.sequence_observation['restoration_qualified'] is False
  else:
   result=session.sequence(plan);assert result['set_text_acknowledged'] is True and result['restoration_qualified'] is True
  assert calls==['state','inspect','set_text','state']
 passed('actual_Session_set_text_once_and_independent_after_state_on_failure',
        explicit_seams=['installed/task/foreground/instrument methods; no Android'],actual_operations_each=['state','inspect','set_text','state'])
 return {'schema':1,'status':'LOCAL_PYTHON_CONTROLS_PASS','controls':results,'count':len(results),
  'Java_compilation':'NOT_RUN','Android_execution':'NOT_RUN','private_commercial_UI_included':False,
  'source_sha256':{n:hashlib.sha256((HERE/'source'/n).read_bytes()).hexdigest() for n in ['qa_contract.py','qa_adapter.py']}}

if __name__=='__main__':print(json.dumps(run(),ensure_ascii=False,sort_keys=True,indent=2))
