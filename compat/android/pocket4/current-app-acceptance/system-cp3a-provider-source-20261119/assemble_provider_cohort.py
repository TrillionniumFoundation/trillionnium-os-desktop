#!/usr/bin/env python3
"""Verify retained actual CP3A provider evidence and materialize source-only metadata."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

PREFIX='compat/android/pocket4/current-app-acceptance/'
PACKAGE_PREFIX=PREFIX+'system-cp3a-provider-source-20261119/'
BASE_PIN=(PREFIX+'system-cp3a-source-adapter-20261119/successor-r1/CURRENT-CP3A-COHORT.json',65110,'78b8beaae7505370f59c20d50a1b8b378253f5ab090712e94ed32628b96f718b')
RESULT_PIN=('actual/RESULT.json',52071,'4ed0d43a0331e20e33b0ac62bf4d0e48e9d76fd29285b6c8268e79d394cefd91')
PROVIDERS={
 'com.android.providers.calendar':(336615,'1ae37944b4f5f24d8d7bc849c76bd80c678d19cc3f5647ccaebd1254d8508744','a40da80a59d170caa950cf15c18c454d47a39b26989d8b640ecd745ba71bf5dc',16169,'dbbac2c144ad77a88c41f322452f26393c103dbcdfabc3d0f390f2a2ec967f4c'),
 'com.android.providers.contacts':(942497,'196cf184ca743601469dc235a4c7a163ac8ca9442cfdbd033bdaf109f5a9fd14','28bbfe4a7b97e74681dc55c2fbb6ccb8d6c74963733f6af6ae74d8c3a6e879fd',14903,'40b35f49755c7ee3c08c439cff9cc124583e5119b1a756ec3487ec1c3a26c1df'),
 'com.android.externalstorage':(57567,'00cf8db78a3f8846e34fd3e6b7f1c811a9393b7c2e6227c083e27e5cdb0fa515','c8a2e9bccf597c2fb6dc66bee293fc13f2fc47ec77bc6b2b0d52c11f51192ab8',14196,'dada6f8c4377991b058a815e6c3c2ada685e09684c9220c8dd49b8f48fa4d8ed'),
 'com.android.providers.media.module':(13826854,'aff897cc1f56583cd71c4cf48330eb4514fdefbd54f069e55223bd31e7af305b','465983f7791f2abeb43ea2cbdc7f21a8260b72bc08a55c839fc1a43bc741a81e',379038,'a4928bf3986ce13a766daa55a3c3ba7a7369b9ab73690642ee26e0da9efb1d4c'),
}
FALSE=('installed','runtime_qualified','business_qualified','production_ready','semantic_cleanup_qualified')

def need(ok,message):
    if not ok: raise ValueError(message)

def unique(pairs):
    d={}
    for k,v in pairs:
        need(k not in d,'duplicate JSON key');d[k]=v
    return d

def f9(s):
    return (s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid,s.st_nlink,s.st_size,s.st_mtime_ns,s.st_ctime_ns)

def raw(path,size,sha):
    for p in [path,*path.parents]: need(not p.is_symlink(),'symlink input')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    with os.fdopen(fd,'rb') as stream:
        old=f9(os.fstat(stream.fileno()))
        need(stat.S_ISREG(old[2]) and old[5]==1 and old[6]==size,'exact regular evidence size')
        b=stream.read(size+1)
        need(len(b)==size and hashlib.sha256(b).hexdigest()==sha,'evidence SHA256 mismatch')
        need(f9(os.fstat(stream.fileno()))==old==f9(path.lstat()),'evidence identity changed')
    return b,old

def doc(path,size,sha):
    b,identity=raw(path,size,sha)
    return json.loads(b,object_pairs_hook=unique,parse_constant=lambda v:(_ for _ in ()).throw(ValueError('non-finite JSON'))),identity

def load_inputs(repo,here):
    before={}
    base,before['base']=doc(repo/BASE_PIN[0],BASE_PIN[1],BASE_PIN[2])
    result,before['result']=doc(here/RESULT_PIN[0],RESULT_PIN[1],RESULT_PIN[2])
    receipts={}
    for package,(_,_,_,size,sha) in PROVIDERS.items():
        receipts[package],before[package]=doc(here/'actual/receipts'/(package+'.json'),size,sha)
    for command in result['commands']:
        for key in ('stdout','stderr'):
            pin=command[key]
            rel='actual/logs/'+Path(pin['path']).name
            _,before[rel]=raw(here/rel,pin['bytes'],pin['sha256'])
    for key in ('capex_member_proof','apex_payload_proof'):
        pin=result['media_source_chain'][key]
        rel='actual/evidence/'+Path(pin['path']).name
        value,before[rel]=doc(here/rel,pin['bytes'],pin['sha256'])
        receipts[key]=value
    return {'base':base,'result':result,'receipts':receipts},before

def validate(d):
    base,result,receipts=d['base'],d['result'],d['receipts']
    need(result['success'] is True and result['source_identity_verified'] is True and result['source_APK_pass_count']==4,'actual source run incomplete')
    need(all(result[k] is False for k in FALSE),'source result promotes runtime')
    need(result['Android_starts']==result['Android_actions']==result['new_downloads']==result['privileged_mounts']==result['C_or_Rust_compilations']==0,'unexpected host/device action')
    need(result['total_APK_bytes']==15163533 and len(result['bookends'])==26 and all(x['F9_and_SHA_equal'] is True for x in result['bookends']),'actual full source bookends')
    need(result['remaining_children']=='' and len(result['commands'])==24,'actual command lifecycle scope')
    need(all(x['exit']==0 and x['actual_child_reaped'] and x['after_reap_echild'] and
             x['original_pidfd_held_until_reaped'] and x['output_complete'] and not x.get('termination') for x in result['commands']),'actual command failure or unreaped child')
    need(len(result['actual_evidence_negative_controls'])==6 and all(x['rejected'] is True for x in result['actual_evidence_negative_controls']),'actual source negative controls')
    need(base['full_GSI']==result['full_system_image'],'whole GSI identity mismatch')
    need(result['build_identity']['id']=='CP3A.260905.010' and result['build_identity']['sdk']==37,'current GSI build')
    rows={x['package']:x for x in result['providers']}
    need(set(rows)==set(PROVIDERS) and len(result['providers'])==4 and set(base['provider_cohort'])==set(PROVIDERS),'exact four provider set')
    for package,(size,sha,signer,receipt_size,receipt_sha) in PROVIDERS.items():
        row=rows[package];receipt=receipts[package]
        need((row['apk']['bytes'],row['apk']['sha256'])==(size,sha),'provider APK identity mismatch')
        need(row['apk']==receipt['apk'] and row['image_path']==receipt['original_image_path'],'source record APK/path mismatch')
        need(receipt['package']==package and receipt['version_code']==row['version_code']==37 and receipt['version_name']==row['version_name']=='17','provider package/version')
        need(receipt['signer_certificate_sha256']==row['signer_certificate_sha256']==[signer] and
             receipt['selected_signing_scheme']['certificate_sha256']==[signer],'exact distinct provider signer')
        need(receipt['signature_verified_for_api']==37 and receipt['source_identity_verified'] is True and receipt['full_CRC_and_SHA_verified'] is True,'API37 source verification missing')
        need(receipt['full_system_image']==result['full_system_image'],'receipt bound to another GSI')
        need(all(receipt[k] is False for k in FALSE) and receipt['actual_UID'] is None and receipt['framework_epoch'] is None,'receipt cannot invent runtime identity')
        need(receipt['individual_APK_install_authorized'] is False and receipt['install_mode']=='coherent_full_GSI_only','individual provider installation forbidden')
        need(all(x['complete_eof_crc_verified'] is True for x in receipt['complete_zip_members']) and
             len(receipt['complete_zip_members'])==row['zip_members'],'incomplete APK ZIP coverage')
        need(all(x['exit']==0 for x in receipt['commands']) and len([x for x in receipt['commands'] if x['name'].endswith(('-signature','-badging','-manifest'))])==3,'missing actual SDK commands')
    chain=result['media_source_chain'];cap=receipts['capex_member_proof'];apex=receipts['apex_payload_proof']
    need((chain['capex']['bytes'],chain['capex']['sha256'])==(17256448,'a15084a3dcf7eca1fa0344625226b4600c3020cce3bdda9749bcb77d76c7ad95'),'current CAPEX identity')
    need(cap['parent']==chain['capex'] and cap['extracted']==chain['original_apex'] and cap['selected_member']['name']=='original_apex','CAPEX exact-member chain')
    need(apex['parent']==chain['original_apex'] and apex['extracted']==chain['payload'] and apex['selected_member']['name']=='apex_payload.img','APEX exact-member chain')
    need(all(x['complete_eof_crc_verified'] is True for p in (cap,apex) for x in p['complete_members']),'archive chain incomplete')
    need(chain['container_signature_or_AVB_qualified'] is False and chain['image_member_path']=='/priv-app/MediaProvider@CP3A.260905.010/MediaProvider.apk','Media exact current path')
    need(receipts['com.android.providers.media.module']['container_chain']==chain,'Media receipt does not bind complete original chain')
    return rows

def build(d):
    rows=validate(d)
    cohort=copy.deepcopy(d['base'])
    for package,row in rows.items():
        p=cohort['provider_cohort'][package]
        need(p['current_APK'] is None and p['current_signer'] is None and p['actual_UID'] is None,'historical source block changed')
        p['current_APK']=copy.deepcopy(row['apk'])
        p['current_signer']=copy.deepcopy(row['signer_certificate_sha256'])
        p['current_source_receipt']={'path':PACKAGE_PREFIX+'actual/receipts/'+package+'.json',
                                   'bytes':row['source_receipt']['bytes'],'sha256':row['source_receipt']['sha256']}
        p['current_source_origin']=copy.deepcopy(row['source_receipt'])
        p['source_identity_verified']=True
        p['status']='CURRENT_CP3A_APK_SOURCE_VERIFIED_SEMANTICS_AND_RUNTIME_PENDING'
        p['semantic_cleanup_qualified']=False
        p['runtime_qualified']=False
        p['business_qualified']=False
        p['production_ready']=False
    cohort['schema']='pocket4-current-cp3a-provider-source-cohort-v1'
    cohort['state']='PROVIDER_SOURCE_IDENTITIES_VERIFIED_RUNTIME_BLOCKED'
    cohort['prior_cohort']={'path':BASE_PIN[0],'bytes':BASE_PIN[1],'sha256':BASE_PIN[2]}
    cohort['actual_provider_source_run']={'path':PACKAGE_PREFIX+RESULT_PIN[0],'bytes':RESULT_PIN[1],'sha256':RESULT_PIN[2]}
    cohort['provider_source_verified_count']=4
    cohort['provider_runtime_qualified_count']=0
    cohort['provider_semantic_cleanup_qualified_count']=0
    cohort['current_provider_source_only']=True
    return cohort

def write_new(path,value):
    b=(json.dumps(value,sort_keys=True,indent=2)+'\n').encode()
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as stream:stream.write(b);stream.flush();os.fsync(stream.fileno())
    return {'path':str(path),'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}

def main(argv=None):
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--repo-root',type=Path,required=True)
    ap.add_argument('--packet-dir',type=Path,default=Path(__file__).resolve().parent)
    ap.add_argument('--out',type=Path,required=True)
    a=ap.parse_args(argv)
    try:
        d,before=load_inputs(a.repo_root,a.packet_dir)
        cohort=build(d)
        _,after=load_inputs(a.repo_root,a.packet_dir)
        need(before==after,'evidence F9 changed before publication')
        out=write_new(a.out,cohort)
        print(json.dumps({'output':out,'recorded_actual_provider_sources':4,'recorded_actual_commands':24,
            'local_metadata_files_checked':len(before),'SDK_commands_reexecuted_here':0,'runtime_qualified':False,
            'semantic_cleanup_qualified':False,'business_qualified':False,'production_ready':False},sort_keys=True))
        return 0
    except (OSError,ValueError,KeyError,TypeError) as error:
        print(json.dumps({'state':'REFUSED','error':str(error),'production_ready':False}),file=sys.stderr)
        return 2

if __name__=='__main__':
    raise SystemExit(main())
