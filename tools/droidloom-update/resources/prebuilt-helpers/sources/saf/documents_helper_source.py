"""Render original SAF helper with only a new package/RUN, label and derived SHA.

All Java business methods, literal payload expression, exported activity scope,
URI path, permissions, counters, unknown policy and lease clock are preserved.
This renderer does not build or install anything.
"""
import hashlib
import json

OLD_RUN='69814e80ea71f485'
OLD_LABEL='Pocket4 Owned SAF 69814e80'
OLD_PAYLOAD_SHA='5e8ee8b6e154ade076e1f62e1ff0bc206ae69ba41982ac1c7a048c303f0503e7'
ORIGIN_ROOT='/usr/libexec/droidloom/native-application-leaves/cohorts/cp3a-20261126-apps-r2/source/templates/documents-saf/'
TEMPLATES={
 'AndroidManifest.xml':(1137,'54266f3e8925e0451440515930e267110aecfab05f4c3cfe5fedb3e24c476ddf','AndroidManifest.xml'),
 'SafActivity.java':(16590,'1ab0eb0a2270de63ed642262b4e999102beafb5560355fe02f998ca4691d3099',
     'src/org/droidloom/qa/saf/r12/n69814e80ea71f485/SafActivity.java'),
 'ids.xml':(273,'96b43d2d226700a9d1b99a9575b6ab73f5ca245776165d1a05ef783579e9c1f7','res/values/ids.xml'),
 'contract.json':(612,'dd5d35810c9a6fc3e8e96b842a592e871996976d6d697d8f4316caf3c5856c26','contract.json')}

def need(value,reason):
    if not value:raise ValueError(reason)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def encoded(value):return (json.dumps(value,sort_keys=True,indent=2,ensure_ascii=False,allow_nan=False)+'\n').encode('utf-8')

def render(names,templates):
    names.require_kind('saf11')
    need(type(templates) is dict and set(templates)==set(TEMPLATES),'EXACT_ORIGINAL_SAF_HELPER_TEMPLATES')
    origins=[]
    for name,(size,digest,path) in TEMPLATES.items():
        raw=templates[name]
        need(type(raw) is bytes and len(raw)==size and sha(raw)==digest,'ORIGINAL_SAF_TEMPLATE_CHANGED:'+name)
        origins.append({'path':ORIGIN_ROOT+path,'bytes':size,'sha256':digest})
    java0=templates['SafActivity.java'];manifest0=templates['AndroidManifest.xml']
    old=OLD_RUN.encode();new=names.RUN.encode();old_sha=OLD_PAYLOAD_SHA.encode();new_sha=names.PAYLOAD_SHA.encode()
    need(new not in java0+manifest0 and new_sha not in java0 and names.APP_LABEL.encode() not in manifest0,
        'NEW_SAF_LITERALS_MUST_NOT_ALIAS_TEMPLATE_CONTENT')
    need(java0.count(old)==2 and java0.count(old_sha)==1 and manifest0.count(old)==3
        and manifest0.count(OLD_LABEL.encode())==1,'EXACT_ORIGINAL_SAF_NAME_AND_PAYLOAD_BINDINGS')
    java=java0.replace(old,new).replace(old_sha,new_sha)
    manifest=manifest0.replace(old,new).replace(OLD_LABEL.encode(),names.APP_LABEL.encode())
    need(java.replace(new_sha,old_sha).replace(new,old)==java0
        and manifest.replace(names.APP_LABEL.encode(),OLD_LABEL.encode()).replace(new,old)==manifest0,
        'ONLY_SAF_DECLARED_LITERAL_SUBSTITUTIONS')
    original=json.loads(templates['contract.json'])
    need(original['payload_bytes']==87 and original['payload_sha256']==OLD_PAYLOAD_SHA
        and original['temporary_package'] is True and original['launcher'] is False
        and original['network_permissions'] is False,'ORIGINAL_SAF_SCOPE_CHANGED')
    contract={**original,'run':names.RUN,'package':names.PACKAGE,'folder':names.FOLDER,
        'created_name':names.CREATED,'provider_name':names.PROVIDER,'ui_name':names.FILES,
        'payload_utf8':names.PAYLOAD.decode('utf-8'),'payload_bytes':87,'payload_sha256':names.PAYLOAD_SHA,
        'original_contract':origins[-1],'original_Java_lease_clock':'System.currentTimeMillis',
        'original_Java_lease_ms':1200000,'current_Main_authority_created':False,'built':False,'installed':False,
        'Android_UI_actions':0,'whole_app_business_accepted':False}
    files={'AndroidManifest.xml':manifest,'src/'+names.PACKAGE.replace('.','/')+'/SafActivity.java':java,
        'res/values/ids.xml':templates['ids.xml'],'contract.json':encoded(contract)}
    result={'schema':'pocket4-documents-saf-fresh-name-helper-source-v1','package':names.PACKAGE,'run_id':names.RUN,
        'files':{n:{'bytes':len(v),'sha256':sha(v)} for n,v in sorted(files.items())},'original_templates':origins,
        'original_Java_preserved_except_package_RUN_derived_payload_SHA':True,
        'original_manifest_preserved_except_package_label_and_same_owned_URI_path':True,
        'permissions':[],'launcher':False,'network':False,'runtime_authority_created':False,
        'built':False,'installed':False,'Android_UI_actions':0,'Main_actions':0,'whole_app_business_accepted':False}
    files['SOURCE_PINS.json']=encoded(result)
    return files,result
