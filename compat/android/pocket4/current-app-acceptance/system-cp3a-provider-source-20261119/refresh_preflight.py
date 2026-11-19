#!/usr/bin/env python3
"""Reconcile the existing required39 plan with the qualified United3622 source."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

BASE='compat/android/pocket4/current-app-acceptance/'
UNITED='com.united.mobile.android'
PINS={
 'plan':(BASE+'system-cp3a-source-adapter-20261119/successor-r1/PLAN.json',143601,'9e622b0941a909f7ed2a887a3b6970b17c78ab72a9f05cec00030b68a1fb91e3'),
 'state':(BASE+'source-refresh-20261119/united/actual/CURRENT-SOURCE-STATE.json',169275,'79a3b9063fa9140d2eff7709632378e7ed2c0520aa28293993ec389d3f5b7b31'),
 'registry':(BASE+'source-refresh-20261119/united/actual/current-source-inputs.json',116810,'62df07622afa60960863dd9721cfd8b46a67b74076355c150534052f1f58abb1'),
 'freshness':(BASE+'source-refresh-20261119/united/actual/current-source-freshness.json',109341,'459a5fd3b74ac186bb0bd19d30874b36ba9b54e2453824b38410843e24289918'),
 'receipt':(BASE+'source-refresh-20261119/united/inputs/source-receipt.json',31632,'1023f326cc86f256fef91e873dcc8613b213d5ada5f692193fe41b747a5fb306'),
}
FALSE_FIELDS=('installed','runtime_qualified','business_qualified','production_ready','native_compatibility_qualified')
EXEMPT={'com.enflick.android.TextNow','com.pinger.textfree','com.ubercab'}

def need(value,message):
    if not value: raise ValueError(message)

def unique_json(pairs):
    value={}
    for key,item in pairs:
        need(key not in value,'duplicate JSON key')
        value[key]=item
    return value

def f9(s):
    return (s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid,s.st_nlink,s.st_size,s.st_mtime_ns,s.st_ctime_ns)

def read_fixed(root):
    result={};bookends={}
    for key,(rel,size,sha) in PINS.items():
        p=root/rel
        need(p.is_absolute(),'absolute repository root required')
        for parent in [p,*p.parents]:
            need(not parent.is_symlink(),'symlink input component')
        fd=os.open(p,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW)
        with os.fdopen(fd,'rb') as stream:
            before=f9(os.fstat(stream.fileno()))
            need(stat.S_ISREG(before[2]) and before[5]==1 and before[6]==size,'regular size-pinned input required')
            body=stream.read(size+1)
            need(len(body)==size and hashlib.sha256(body).hexdigest()==sha,'source input pin mismatch: '+key)
            need(f9(os.fstat(stream.fileno()))==f9(p.lstat())==before,'input changed while read')
        result[key]=json.loads(body,object_pairs_hook=unique_json,parse_constant=lambda x:(_ for _ in ()).throw(ValueError('non-finite JSON')))
        bookends[key]=before
    return result,bookends

def index(rows):
    result={}
    for row in rows:
        need(row['package'] not in result,'duplicate package')
        result[row['package']]=row
    return result

def small(key):
    path,size,sha=PINS[key]
    return {'path':path,'bytes':size,'sha256':sha}

def validate_inputs(d):
    plan,state,registry,fresh,receipt=[d[k] for k in ('plan','state','registry','freshness','receipt')]
    old=index(plan['packages']);apps=index(state['applications']);reg=index(registry['applications']);fr=index(fresh['rows'])
    need(len(old)==39 and set(old)==set(apps),'exact required39 scope')
    need({x['package'] for x in plan['exemptions']}==EXEMPT and plan['exemptions']==state['exemptions'],'only original three exemptions')
    need(plan['required_before_installation']==state['required_before_installation'],'installation prerequisites changed')
    need(plan['counts']['packages_without_selected_business_executor']==32 and
         plan['counts']['runtime_acceptance_count']==plan['counts']['business_acceptance_count']==0,'original acceptance counts')
    for row in list(old.values())+[plan,state]:
        need(all(row[k] is False for k in FALSE_FIELDS),'runtime or production promotion in input')
    app=apps[UNITED];record=app['current_registry_record'];historical=app['historical_state_record']['unchanged_current_registry_record']
    need(record==reg[UNITED],'current state and registry disagree')
    need(record['version_name']=='4.2.104' and record['version_code']==3622,'exact current United identity')
    need(record['source_identity_verified'] is True and record['signature_verified'] is True,'unverified United source')
    need(old[UNITED]['source_version']=='4.2.103' and old[UNITED]['source_version_code']==3621,'historical plan identity')
    need(old[UNITED]['source_body_pin_metadata']==historical['input'],'historical source input mismatch')
    need(fr[UNITED]['selected_input_version']=='4.2.104' and fr[UNITED]['selected_input_version_code']==3622 and
         fr[UNITED]['source_input_selected'] is True and fr[UNITED]['latest_release_recheck_required_before_activation'] is True,'current freshness join')
    need(record['proofs']['source-receipt.json']==small('receipt'),'current receipt pin mismatch')
    need(receipt['all_original_delivery_apks_verified'] is True and len(receipt['identities'])==4,'complete original four-APK source qualification')
    need(all(x['package']==UNITED and x['long_version_code']==3622 and x['signature_verified'] is True and
             x['verification_SDK_range']==[37,37] and all(v==0 for v in x['tool_exits'].values()) and x['executed'] is False
             for x in receipt['identities']),'real SDK37 source result join')
    expected={x['name']:(x['bytes'],x['sha256']) for x in record['expected_input']['apks']}
    observed={x['filename']:(x['bytes'],x['sha256']) for x in receipt['identities']}
    need(expected==observed and len(expected)==4,'four current APK identities differ')
    need(all(all(p[k] is None for k in p) for p in [row['actual_runtime_bindings'] for row in old.values()]),'invented runtime bindings')
    return old,record,fr[UNITED]

def build_plan(d):
    old,current,fresh=validate_inputs(d)
    result=copy.deepcopy(d['plan'])
    rows=index(result['packages']);row=rows[UNITED]
    row['historical_source_selection']={
        'source_version':row['source_version'],'source_version_code':row['source_version_code'],
        'source_body_pin_metadata':copy.deepcopy(row['source_body_pin_metadata']),
        'latest_input_status':row['latest_input_status'],
        'latest_update_pending':row.pop('latest_update_pending'),
    }
    row['source_version']=current['version_name'];row['source_version_code']=current['version_code']
    row['source_body_pin_metadata']=copy.deepcopy(current['input'])
    row['latest_input_status']='SOURCE_QUALIFIED_4.2.104_3622_ACTIVATION_RECHECK_REQUIRED'
    row['current_source_receipt']=small('receipt')
    row['latest_release_recheck_required_before_activation']=True
    row['source_verified_utc']=current['source_verified_utc']
    result['schema']='pocket4-required39-business-plan-current-united-source-successor-v1'
    result['prior_CP3A_source_adapter_plan']=small('plan')
    result['current_source_successor']={
        'source_state':small('state'),'registry':small('registry'),'freshness':small('freshness'),
        'changed_packages':[UNITED],'other38_package_rows_unchanged':True,
        'scope':'Existing actual source metadata joined into the preflight; no source host or APK body reopened here.',
        'remaining_latest_release_recheck_before_activation':True,
    }
    validate_output(result,d)
    return result

def validate_output(result,d):
    original,current,fresh=validate_inputs(d)
    rows=index(result['packages'])
    need(set(rows)==set(original),'output scope changed')
    for package,row in original.items():
        if package!=UNITED: need(rows[package]==row,'another package row changed')
    need(result['counts']==d['plan']['counts'],'acceptance counts changed')
    need(result['required_before_installation']==d['plan']['required_before_installation'],'installation prerequisites changed')
    need(result['common_gate_definitions']==d['plan']['common_gate_definitions'],'common gates changed')
    need(result['exemptions']==d['plan']['exemptions'],'exemptions changed')
    for key in ('source_preservation','global_unresolved_gates','finite_prepared_case_source_count_semantics','prior_preflight_plan','source_snapshots'):
        need(result[key]==d['plan'][key],'historical plan field changed: '+key)
    new=rows[UNITED]
    excluded={'source_version','source_version_code','source_body_pin_metadata','latest_input_status','latest_update_pending'}
    need({k:v for k,v in original[UNITED].items() if k not in excluded}==
         {k:v for k,v in new.items() if k not in excluded|{'historical_source_selection','current_source_receipt','latest_release_recheck_required_before_activation','source_verified_utc'}},
         'United business or runtime gate changed')
    need(new['source_version']=='4.2.104' and new['source_version_code']==3622 and new['source_body_pin_metadata']==current['input'],'United current source output mismatch')
    need(new['historical_source_selection']['source_body_pin_metadata']==original[UNITED]['source_body_pin_metadata'],'historical source lost')
    need(new['current_source_receipt']==small('receipt') and new['latest_release_recheck_required_before_activation'] is True,'current source prerequisites omitted')
    for row in list(rows.values())+[result]:
        need(all(row[k] is False for k in FALSE_FIELDS),'output acceptance promoted')

def write_new(path,data):
    body=(json.dumps(data,sort_keys=True,indent=2)+'\n').encode()
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_CLOEXEC|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as stream:
        stream.write(body);stream.flush();os.fsync(stream.fileno())
    return {'path':str(path),'bytes':len(body),'sha256':hashlib.sha256(body).hexdigest()}

def main(argv=None):
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--repo-root',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args(argv)
    try:
        d,before=read_fixed(args.repo_root)
        result=build_plan(d)
        _,after=read_fixed(args.repo_root)
        need(before==after,'source F9 bookends changed')
        pin=write_new(args.out,result)
        print(json.dumps({'state':'CURRENT_SOURCE_PLAN_PREPARED_RUNTIME_BLOCKED','output':pin,
            'other38_package_rows_unchanged':True,'all_original_installation_prerequisites_unchanged':True,
            'United_version':'4.2.104','United_version_code':3622,'Android_calls':0,
            'runtime_qualified':False,'business_qualified':False,'production_ready':False},sort_keys=True))
        return 0
    except (OSError,ValueError,KeyError,TypeError) as error:
        print(json.dumps({'state':'REFUSED_NO_ACCEPTANCE','reason':str(error),'production_ready':False}),file=sys.stderr)
        return 2

if __name__=='__main__':
    raise SystemExit(main())
