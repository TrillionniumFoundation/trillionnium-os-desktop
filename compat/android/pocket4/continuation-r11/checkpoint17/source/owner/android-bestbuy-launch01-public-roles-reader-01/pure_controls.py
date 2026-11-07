#!/usr/bin/env python3
"""Local count/privacy/pin controls; no private retained assessment is read."""
from pathlib import Path
import ast,copy,hashlib,json,types
HERE=Path(__file__).resolve().parent
ROOT=HERE.parent

def load(path,name):
    m=types.ModuleType(name);m.__file__=str(path);exec(compile(path.read_bytes(),str(path),'exec'),m.__dict__);return m

def main():
    r=load(HERE/'read_roles.py','public_counts')
    p=ROOT/'owned-bestbuy-qa-r1-build01/source/qa_contract.py';raw=p.read_bytes()
    assert len(raw)==28173 and hashlib.sha256(raw).hexdigest()==r.QA_SHA
    qa=load(p,'production_bestbuy_contract');cases=[]
    def passed(name):cases.append({'case':name,'passed':True})
    def reject(name,call,expected):
        try:call()
        except RuntimeError as e:assert str(e)==expected,(name,str(e));passed(name);return
        raise AssertionError(name+' accepted')
    def function_ast(path):
        source=path.read_text().replace('FIXED_SIX_FILE_ALLOWLIST_REQUIRED','FIXED_COMMON_FILE_ALLOWLIST_REQUIRED').replace('FIXED_SEVEN_FILE_ALLOWLIST_REQUIRED','FIXED_COMMON_FILE_ALLOWLIST_REQUIRED').replace("helper.get('self_uid')==10196","helper.get('self_uid')==10184").replace("helper.get('self_uid')==10198","helper.get('self_uid')==10184")
        return {x.name:ast.dump(x,include_attributes=False) for x in ast.parse(source).body if isinstance(x,(ast.FunctionDef,ast.ClassDef))}
    a=function_ast(ROOT/'android-ihg-launch01-public-roles-reader-01/read_roles.py');b=function_ast(HERE/'read_roles.py')
    for key in ('Reader','need','sha','no_raw_ui','validated_assessment'):assert a[key]==b[key],key
    passed('reviewed_reader_privacy_and_wire_validator_AST_preserved')
    def node(path,kind,resource,label='',clickable=False):
        return {'path':path,'package':qa.PACKAGE,'class':kind,'class_truncated':False,
            'resource_id':resource,'resource_id_truncated':False,'visible':True,'enabled':True,'password':False,
            'editable':kind=='android.widget.EditText','supports_set_text':kind=='android.widget.EditText',
            'clickable':clickable,'text':label,'text_sha256':qa.sha(label.encode()),'text_truncated':False,
            'content_desc':'','content_desc_sha256':qa.sha(b''),'content_desc_truncated':False,'bounds':[0,0,100,100],'child_count':0}
    def refresh(value):
        for n in value['nodes']:
            n.pop('node_sha256',None);n['node_sha256']=qa.sha(qa.canonical(n))
        value['tree_sha256']=qa.sha(qa.canonical(value['nodes']));value['window_sha256']=qa.sha(qa.canonical(value['window']));return value
    rows=[node('0','android.widget.FrameLayout',''),
          node('0/0','android.widget.Button',qa.PACKAGE+':id/search_button','  SEARCH ',True),
          node('0/1','android.widget.TextView','PRIVATE_RESOURCE_FIXTURE','PRIVATE_USER_CONTENT_FIXTURE'),
          node('0/2','PRIVATE_CLASS_FIXTURE',''),
          node('0/3','android.widget.FrameLayout','',clickable=True),
          node('0/3/0','android.widget.TextView','','Continue')]
    value=refresh({'complete':True,'traversal':'visible-non-password-subtrees','nodes':rows,
        'window':{'package':qa.PACKAGE,'focused':True,'type':1,'display':0,'bounds':[0,0,100,100]},
        'observed_elapsed_ms':100,'connection_scoped_window_id':12})
    counts=r.public_role_counts(qa,value);r.no_raw_ui(counts);encoded=json.dumps(counts)
    assert all(x not in encoded for x in ('PRIVATE_RESOURCE_FIXTURE','PRIVATE_USER_CONTENT_FIXTURE','PRIVATE_CLASS_FIXTURE'))
    assert counts['fixed_public_role_queries']['search_tab']['eligible_clickable_self_count']==1
    assert counts['fixed_public_role_queries']['continue']['eligible_direct_clickable_parent_count']==1
    assert counts['fixed_public_role_queries']['continue']['distinct_self_or_direct_parent_candidates']==1
    assert counts['other_class_count']==1
    passed('public_labels_self_parent_counts_and_unknown_content_omission')
    duplicate=copy.deepcopy(value);duplicate['nodes'].append(node('0/4','android.widget.Button','','Search',True));refresh(duplicate)
    out=r.public_role_counts(qa,duplicate)['fixed_public_role_queries']['search_tab']
    assert out['distinct_self_or_direct_parent_candidates']==2 and out['current_or_future_action_authority'] is False
    passed('duplicate_public_label_stays_a_count_without_target_selection')
    bad=copy.deepcopy(value);bad['nodes'][1]['text_sha256']='0'*64;refresh(bad)
    reject('bad_public_label_digest_rejected',lambda:r.public_role_counts(qa,bad),'PUBLIC_LABEL_DIGEST_MISMATCH')
    partial=copy.deepcopy(value);partial['complete']=False
    reject('partial_tree_rejected_by_original_contract',lambda:r.public_role_counts(qa,partial),'COMPLETE_INSPECTION_REQUIRED')
    reject('private_nested_field_export_rejected',lambda:r.no_raw_ui({'nested':{'text':'PRIVATE'}}),'RAW_UI_EXPORT_FORBIDDEN')
    e=ROOT/'root-recovery-20261104-02/evidence/bestbuy-launch-five-results-read01';records=[]
    for name,path in (('coordinator',r.ROOT/'result.json'),('stage',r.ROOT/'stage-result.json'),('launch',r.FLOW/'steps/launch-01/result.json'),('inspect',r.STEP/'result.json'),('cleanup',r.FLOW/'steps/cleanup-01/result.json')):
        raw=(e/(name+'.json')).read_bytes();assert (len(raw),hashlib.sha256(raw).hexdigest())==r.PINS[path];records.append(json.loads(raw))
    scope,meta,state=r.validate_retained(*records);assert meta['node_count']==12 and scope['uid']==10130
    passed('five_actual_safe_originals_and_retired_scope_match')
    changed=copy.deepcopy(records);changed[0]['nonce']='0'*32
    reject('foreign_flow_rejected',lambda:r.validate_retained(*changed),'EXACT_COMPLETED_BESTBUY_FLOW_REQUIRED')
    changed=copy.deepcopy(records);changed[0]['launch_result']['sha256']='0'*64
    reject('wrong_launch_child_pin_rejected',lambda:r.validate_retained(*changed),'EXACT_PARENT_CHILD_RESULT_PINS_REQUIRED')
    changed=copy.deepcopy(records);changed[2]['target_FD_cleanup']['held_APK_FDs_closed']=1
    reject('incomplete_three_APK_FD_cleanup_rejected',lambda:r.validate_retained(*changed),'EXACT_THREE_APK_AND_HELPER_PHASE_IDENTITIES_REQUIRED')
    helper={'protocol':qa.PROTOCOL,'nonce':r.INSPECT_NONCE,'op':'inspect','self_uid':10198,'ok':True,
        'error':None,'secondary_errors':[],'action_attempted':False,'outcome_unknown':False,
        'claim_persistence_completed':True,'helper_work_completed':True,'automatic_retry':False,'business_success_verified':False}
    assessed={'helper':helper,'held_transport_returned_after_post_guard':True,'actual_command_returncode':0,
        'actual_instrumentation_finish_code':-1,'wire_sha256':r.INSPECT_WIRE}
    reject('unbound_canonical_helper_wire_rejected',lambda:r.validated_assessment(qa,assessed,r.INSPECT_NONCE,r.INSPECT_WIRE,scope),'ACTUAL_CANONICAL_HELPER_WIRE_PIN_REQUIRED')
    print(json.dumps({'schema':1,'ok':True,'count':len(cases),'cases':cases,'production_BESTBUY_inspect_record_executed':True,
        'private_assessment_or_raw_UI_read':False,'synthetic_public_tree_counts':True,'actual_safe_parents_checked':True,
        'Android_Hepta_process_or_UI_calls':0},sort_keys=True,indent=2))
if __name__=='__main__':main()
