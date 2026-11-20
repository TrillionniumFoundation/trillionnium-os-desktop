"""Reproduce the narrow live ownership change without rewriting old receipts."""
import hashlib
from pathlib import Path

ROOT=Path(__file__).resolve().parent
COHORT='/usr/libexec/droidloom/native-application-leaves/cohorts/cp3a-20261120-apps-r1'
source=ROOT.parent/'p4_apps_executor_audit/support/business_data.py'
raw=source.read_bytes()
assert hashlib.sha256(raw).hexdigest()=='2f86b90b1ca0a3993387163ce2169d17b67841a6c3e65f5a59dd9c8557a7a25a'
s=raw.decode()

def replace(old,new):
    global s
    assert s.count(old)==1,(old[:100],s.count(old))
    s=s.replace(old,new)

replace("EPOCH_PATH=FINAL/'qualification/framework_epoch.py'", "EPOCH_PATH=Path("+repr(COHORT+'/source/main/framework_epoch.py')+")")
replace("EPOCH_SHA='f43f766f19a151d7d33ecd0c99c2e81f832fce7dcb1804e5c774e833066a6288'",
        'EPOCH_SHA='+repr(hashlib.sha256((ROOT/'source/framework_epoch.py').read_bytes()).hexdigest()))
replace("READER_PATH=FINAL/'qualification/held_runtime.py'", "READER_PATH=Path("+repr(COHORT+'/source/main/held_runtime.py')+")")

replace("READER_SHA='72cf33399ca3c280fc0c9288669f7d6c13d387e41b5fb930cf477f2b940f16b4'", """READER_SHA='72cf33399ca3c280fc0c9288669f7d6c13d387e41b5fb930cf477f2b940f16b4'
USERNS_PATH=Path(COHORT_MAIN)/'main_user_namespace.py'
USERNS_SHA=USERNS_SOURCE_SHA
_userns_module=None

def userns_module():
    global _userns_module
    if _userns_module is None:
        _userns_module=load(USERNS_PATH,USERNS_SHA,'canonical_actual_main_user_namespace')
    return _userns_module
""")
userns=(ROOT/'source/main_user_namespace.py').read_bytes()
s=s.replace('COHORT_MAIN',repr(COHORT+'/source/main')).replace('USERNS_SOURCE_SHA',repr(hashlib.sha256(userns).hexdigest()))
reader=(ROOT/'source/held_runtime.py').read_bytes()
replace("READER_SHA='72cf33399ca3c280fc0c9288669f7d6c13d387e41b5fb930cf477f2b940f16b4'",
        'READER_SHA='+repr(hashlib.sha256(reader).hexdigest())+'\nREADER_BYTES='+str(len(reader)))
replace("        'package_uids':proof['package_uids'],", "        'package_uids':proof['package_uids'],'main_user_namespace':proof['main_user_namespace'],")
replace('def validate_live(preimage,proof):','def validate_live(preimage,proof,main_mapping):')
replace("proof.get('schema')=='pocket4-live-data-continuity-v1'", "proof.get('schema')=='pocket4-live-data-continuity-v2'")
replace("         'NEW_LIVE_DATA_PROOF_REQUIRED')", """         'NEW_LIVE_DATA_PROOF_REQUIRED')
    need(proof.get('main_user_namespace')==main_mapping,'DATA_PROOF_AND_ORIGINAL_MAIN_MAPPING_DIFFER')
    mapping=userns_module()
    # This pure validator compares evidence only. The caller validates the
    # mapping against the authenticated Main owner/epoch, while measure holds
    # the exact live namespace lease across the complete directory observation.
    mapping.validate_map(main_mapping['uid_map']);mapping.validate_map(main_mapping['gid_map'])""")
replace("""        need(all(type(row[k]) is int and row[k]==expected[k] for k in ('inode','uid','gid')),
             'DATA_DIRECTORY_IDENTITY_REPLACED')
        need(row['uid']==preimage['packages'][package],'LIVE_DIRECTORY_UID_CHANGED')""", """        need(type(row['inode']) is int and row['inode']==expected['inode'],
             'DATA_DIRECTORY_IDENTITY_REPLACED')
        need(type(row['uid']) is int and type(row['gid']) is int
             and row['uid']==mapping.mapped_id(main_mapping['uid_map'],expected['uid'])
             and row['gid']==mapping.mapped_id(main_mapping['gid_map'],expected['gid']),
             'DATA_DIRECTORY_LIVE_MAPPED_OWNER_DIFFERS_FROM_PREIMAGE')
        need(row['uid']==mapping.mapped_id(main_mapping['uid_map'],preimage['packages'][package]),
             'LIVE_DIRECTORY_MAPPED_UID_CHANGED')""")
replace('def measure(init_identity,preimage,pool,proc_fd,root_fd,deadline):',
        'def measure(init_identity,preimage,pool,proc_fd,root_fd,deadline,main_user_namespace):')
replace("    epoch=load(EPOCH_PATH,EPOCH_SHA,'business_data_epoch')", """    need(type(main_user_namespace) is userns_module().HeldMainUserNamespace,
         'ACTUAL_HELD_MAIN_USER_NAMESPACE_LEASE_REQUIRED')
    main_mapping=main_user_namespace.guard()
    need(main_mapping['init']=={key:init_identity[key] for key in
         ('host_pid','parent_host_pid','start_ticks','namespace_pids')}
         and main_mapping['root_uids']==init_identity['uids'],
         'DATA_MAPPING_MUST_BELONG_TO_THIS_EXACT_INIT')
    epoch=load(EPOCH_PATH,EPOCH_SHA,'business_data_epoch')""")
replace("        check();need(epoch.process_identity(init_identity['host_pid'])==init_identity,'DATA_INIT_GENERATION_CHANGED')", """        check();need(epoch.process_identity(init_identity['host_pid'])==init_identity,'DATA_INIT_GENERATION_CHANGED')
        need(main_user_namespace.guard()==main_mapping,'DATA_MAIN_USER_NAMESPACE_OR_MAP_CHANGED')""")
replace("proof={'schema':'pocket4-live-data-continuity-v1','preimage':PREIMAGE", "proof={'schema':'pocket4-live-data-continuity-v2','main_user_namespace':main_mapping,'preimage':PREIMAGE")
replace('    validate_live(preimage,proof)','    validate_live(preimage,proof,main_mapping)')
compile(s,'business_data.py','exec')
(ROOT/'source/business_data.py').write_text(s)
print('business_data',len(s.encode()),hashlib.sha256(s.encode()).hexdigest())
