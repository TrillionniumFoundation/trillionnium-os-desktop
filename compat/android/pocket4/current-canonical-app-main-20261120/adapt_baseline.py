"""Prepare the source successor; never mutate or authorize a prior baseline."""
import hashlib
from pathlib import Path

ROOT=Path(__file__).resolve().parent
COHORT='/usr/libexec/droidloom/native-application-leaves/cohorts/cp3a-20261120-apps-r1'
QUAL='/var/lib/droidloom/qualification/pocket4'
raw=(ROOT.parent/'p4_apps_executor_audit/support/business_baseline.py').read_bytes()
assert hashlib.sha256(raw).hexdigest()=='0d26c720f2d349b97c192a2f18d7db9d62f5421944a50ae31d6499188e5bdcff'
s=raw.decode()

def replace(old,new,count=1):
    global s
    assert s.count(old)==count,(old[:140],s.count(old),count)
    s=s.replace(old,new)

replace("FINAL=Path('/home/alex/work/pocket4-android-final')", "FINAL=Path('/home/alex/work/pocket4-android-final')\nQUALIFICATION=Path("+repr(QUAL)+")\nMAIN_SOURCE=Path("+repr(COHORT+'/source/main')+")")
data=(ROOT/'source/business_data.py').read_bytes()
replace("DATA_SHA='2f86b90b1ca0a3993387163ce2169d17b67841a6c3e65f5a59dd9c8557a7a25a'",'DATA_SHA='+repr(hashlib.sha256(data).hexdigest()))
replace("ANCESTRY=Path('/home/alex/work/pocket4-main-current-baseline-02/source/cell_ancestry.py')", "ANCESTRY=MAIN_SOURCE/'cell_ancestry.py'")
replace("CAPTURE=FINAL/'qualification/capture_main.py'", "CAPTURE=MAIN_SOURCE/'capture_main.py'")
replace("CAPTURE_SHA='1a1a9122744eb83b047da9562daf9930883684a4f11d0de76e3e4154a91e9e69'", 'CAPTURE_SHA='+repr(hashlib.sha256((ROOT/'source/capture_main.py').read_bytes()).hexdigest()))
replace("SCHEMA='pocket4-final-business-baseline-v1'", "SCHEMA='pocket4-final-business-baseline-v2'")
replace("QUAL_SCHEMA='pocket4-final-business-qualification-v1'", "QUAL_SCHEMA='pocket4-final-business-qualification-v2'")
replace("ROLES=('daemon','launcher','owner_intermediary','presenter','init','zygote64','system_server','surfaceflinger')", "ROLES=('daemon','presenter','init','zygote64','system_server','surfaceflinger')")
replace("plan.get('schema')=='pocket4-final-business-capture-plan-v1'", "plan.get('schema')=='pocket4-final-business-capture-plan-v2'")
replace("need(set(ref)=={'path','bytes','sha256'} and ref['path'].startswith(str(FINAL)+'/') and", "need(set(ref)=={'path','bytes','sha256'} and\n             ((name=='source_manifest' and ref['path'] in (str(HERE/'source-manifest.json'),str(HERE/'clock-source-manifest.json')))\n              or (name!='source_manifest' and ref['path'].startswith(str(QUALIFICATION)+'/'))) and")
replace("base.get('schema')=='pocket4-final-main-baseline-v1'", "base.get('schema')=='pocket4-final-main-baseline-v2'")
replace("    epoch=base['main_epoch']", """    need(base.get('capture_output_path')==plan['final_baseline']['path'],
         'ACTUAL_FRESH_MAIN_CAPTURE_OUTPUT_REQUIRED')
    contract=load(MAIN_SOURCE/'helper_contract.py',HELPER_CONTRACT_SHA,'same_Main_readonly_entry_contract')
    contract.verify_main_receipt(base)
    epoch=base['main_epoch']""")
replace("need(set(base['host_processes'])=={'daemon','launcher','owner_intermediary','presenter'},'FINAL_HOST_ROLE_SET_CHANGED')", "need(set(base['host_processes'])=={'daemon','presenter'},'EXACT_NATIVE_HOST_ROLE_SET_REQUIRED')")
replace("'SEVEN_MAIN_ROLES_AND_ORIGINAL_OWNER_INTERMEDIARY_REQUIRED'", "'SIX_ACTUAL_MAIN_AND_HOST_ROLES_REQUIRED'")
replace("    need(transaction.get('schema')=='pocket4-final-deployment-result-v1'", """    scope=load(MAIN_SOURCE/'deployment_scope.py',DEPLOYMENT_SCOPE_SHA,'independent_app_and_data_retention_scope')
    scope.validate_transaction(transaction)
    need(transaction.get('schema')=='pocket4-final-deployment-result-v2'""")
replace("         transaction.get('preimages_retention')=='retained until original45 whole-app final acceptance' and\n", '')
replace("""    need(base['init_host_pid']==rows['init']['host_pid'] and base['daemon_status']['host_pid']==rows['launcher']['host_pid'],
         'FINAL_OWNER_DISCOVERY_CHANGED')
    for child,parent in (('launcher','daemon'),('owner_intermediary','launcher'),('init','owner_intermediary'),
                         ('zygote64','init'),('system_server','zygote64'),('surfaceflinger','init')):""", """    need(base['init_host_pid']==rows['init']['host_pid'] and base['daemon_status']['host_pid']==rows['init']['host_pid'],
         'ACTUAL_NATIVE_INIT_OBSERVATION_CHANGED')
    native=load(MAIN_SOURCE/'native_main_observation.py',NATIVE_OBSERVATION_SHA,'pure_current_main_observation')
    image=load(MAIN_SOURCE/'native_image_observation.py',IMAGE_OBSERVATION_SHA,'pure_current_image_observation')
    native.validate_record(base['native_main_observation'],rows['daemon'],base['installed_payloads']['/usr/bin/droidloomd'],image.validate_response)
    native.validate_record(base['native_final_status_observation'],rows['daemon'],base['installed_payloads']['/usr/bin/droidloomd'],None,_status_init=rows['init'])
    need(base.get('native_execution_authority_transferred') is False and
         base['native_final_status_observation']['started_monotonic_ns']>=base['native_main_observation']['finished_monotonic_ns'],
         'ORDERED_READ_ONLY_NATIVE_MAIN_OBSERVATIONS_REQUIRED')
    need(base['daemon_status']==base['native_main_observation']['response'],
         'NATIVE_DAEMON_RESPONSE_NOT_THIS_AUTHENTICATED_OBSERVATION')
    owner=base['daemon_status']['image_custody']['owner']
    ns=[row for row in owner['namespaces'] if row['name']=='user']
    need(len(ns)==1 and owner['cell_host_pid']==rows['init']['host_pid']
         and owner['cell_start_ticks']==rows['init']['start_ticks'], 'NATIVE_OWNER_AND_ACTUAL_INIT_EPOCH_DIFFER')
    owner_user={'link':'user:['+str(ns[0]['inode'])+']','device':ns[0]['device'],'inode':ns[0]['inode']}
    data_module().userns_module().validate_observation(base['main_user_namespace'],owner_user,rows['init'],epoch['binding']['boot_id'])
    for child,parent in (('init','daemon'),('zygote64','init'),('system_server','zygote64'),('surfaceflinger','init')):""")
replace("for role in ('daemon','launcher','owner_intermediary'):", "for role in ('daemon',):")
replace("tx=FINAL/'deployment/transactions'/txid", "tx=QUALIFICATION/'deployment/transactions'/txid")
replace("for directory in (FINAL/'deployment',tx.parent,tx,pre):", "for directory in (QUALIFICATION/'deployment',tx.parent,tx,pre):")
replace("need(reference['path'].startswith(str(FINAL)+'/'),'FINAL_PROOF_OUTSIDE_PROJECT')", "need(reference['path'].startswith(str(QUALIFICATION)+'/'),'FRESH_PROOF_OUTSIDE_CANONICAL_QUALIFICATION')")
replace("        self.preimage=data.load_preimage()", "        self.preimage=data.load_preimage();self.main_user_namespace=None")
replace("        self.policy=load(POLICY,POLICY_SHA,'business_legacy_pure_validators')", """        self.policy=load(POLICY,POLICY_SHA,'business_legacy_pure_validators')
        self.native=load(MAIN_SOURCE/'native_main_observation.py',NATIVE_OBSERVATION_SHA,'business_same_native_peer')
        self.main_factory=load(CAPTURE,CAPTURE_SHA,'business_current_main_factory_read_helpers')
        self.android_environment=None""")
replace("""        self.identities()
    def artifact(self,fd,limit=268435456):""", """        self.identities()
        host=self.pool.own(os.open('/proc/self/ns/user',os.O_RDONLY|os.O_CLOEXEC),'original_host_user_namespace')
        mapping=self.base['main_user_namespace']
        self.main_user_namespace=self.data.userns_module().HeldMainUserNamespace(
            self.rows['init'],self.handles['init'],mapping['user_namespace'],host,
            self.base['main_epoch']['binding']['boot_id'],self.identities)
        need(self.main_user_namespace.guard()==mapping,'HELD_MAIN_NAMESPACE_DIFFERS_FROM_AUTHENTICATED_BASELINE')
    def artifact(self,fd,limit=268435456):""")
replace("'host_user_namespace':os.readlink('/proc/self/ns/user'),'limits':{}}", "'host_user_namespace':os.readlink('/proc/self/ns/user'),'limits':{},\n               'main_user_namespace':self.main_user_namespace.guard(),'role_user_namespaces':{}}")
replace("            need(value['namespaces'][role]['user']['link']==value['host_user_namespace'],'USER_NAMESPACE_MAPPING_CHANGED')", """            fact=self.main_user_namespace.observe_role(h,self.rows[role],role)
            need(fact['user_namespace']==value['namespaces'][role]['user'],
                 'ROLE_NAMESPACE_HANDLE_AND_CREDENTIAL_OBSERVATION_DIFFER')
            value['role_user_namespaces'][role]=fact""")
replace("for parent,child in (('daemon','launcher'),('launcher','owner_intermediary'),('owner_intermediary','init')):", "for parent,child in (('daemon','init'),):",count=2)
replace("self.policy.validate_child_table(second,self.rows[parent]['host_pid'],self.rows[child]['host_pid'])", "validate_broker_child_table(second,self.rows[parent]['host_pid'],self.rows[child]['host_pid'])")
replace("        self.identities();return value", "        self.identities();need(self.main_user_namespace.guard()==value['main_user_namespace'],'MAIN_MAPPING_CHANGED_DURING_OBSERVATION');return value")
replace("        values=self.reader.selected_classpaths(raw);del raw", """        values=self.reader.selected_classpaths(raw)
        self.android_environment=self.data.userns_module().android_environment(raw);del raw
        need(self.android_environment==self.base['android_env'],'ACTUAL_HELD_ANDROID_ENVIRONMENT_CHANGED')""")
replace("return self.data.measure(self.rows['init'],self.preimage,self.pool,h['proc'],h['root'],self.deadline)", "return self.data.measure(self.rows['init'],self.preimage,self.pool,h['proc'],h['root'],self.deadline,self.main_user_namespace)")
replace("    def payloads(self,expected=None):", """    def native_status(self):
        def guard():
            identities=self.identities()
            unit=self.main_factory.show(self.main_factory.SYSTEM,'droidloomd.service',seconds=3)
            need(unit==self.base['systemd_units']['daemon'],'ORIGINAL_NATIVE_DAEMON_SERVICE_INVOCATION_CHANGED')
            return {'identities':identities,'unit':unit}
        result=self.native.status(self.rows['daemon'],self.base['installed_payloads']['/usr/bin/droidloomd'],
                                  self.epoch,guard,self.rows['init'])
        self.check();return result
    def payloads(self,expected=None):""")
replace("""    def close(self):
        self.pool.close_all();self.pool.require_clean();return self.pool.summary()""", """    def close(self):
        mapping=None;primary=None
        try:
            if self.main_user_namespace is not None:mapping=self.main_user_namespace.close()
        except BaseException as error:primary=error
        finally:self.pool.close_all()
        self.pool.require_clean()
        if primary is not None:raise primary
        result=self.pool.summary()
        if mapping is not None:
            need(mapping['remaining']==0 and not mapping['errors'] and
                 mapping['acquired']==mapping['closed']==mapping['close_attempts'],'MAIN_USER_NAMESPACE_FDS_UNCLOSED')
            for key in ('acquired','closed','close_attempts'):result[key]+=mapping[key]
        return result""")
replace('def validate_observation(value,rows,policy):', 'def validate_observation(value,rows,policy,main_mapping):')
replace("'host_user_namespace','limits'},'EXACT_NEW_OBSERVATION_REQUIRED')", "'host_user_namespace','limits','main_user_namespace','role_user_namespaces'},'EXACT_NEW_OBSERVATION_REQUIRED')")
replace("    need(value['roles']==rows and value['limits']==LIMITS,'ACTUAL_ROLE_AND_RESOURCE_FACTS_REQUIRED')", """    need(value['roles']==rows and value['limits']==LIMITS,'ACTUAL_ROLE_AND_RESOURCE_FACTS_REQUIRED')
    need(value['main_user_namespace']==main_mapping and set(value['role_user_namespaces'])==set(ROLES),
         'EXACT_MAIN_AND_PER_ROLE_USER_NAMESPACE_FACTS_REQUIRED')
    mapping=data_module().userns_module()
    host_namespace=main_mapping['parent_user_namespace']
    need(value['host_user_namespace']==host_namespace['link'],'ORIGINAL_HOST_USER_NAMESPACE_CHANGED')""")
replace("""        need(namespaces['user']['link']==value['host_user_namespace'] and
             all(namespaces[name]['link']==row['namespaces'][name] for name in ('pid','mnt')),
             'ACTUAL_USER_AND_FINAL_PID_MNT_NAMESPACES_REQUIRED')""", """        fact=value['role_user_namespaces'][role]
        mapping.validate_role(fact,main_mapping,row,role,host_namespace)
        need(namespaces['user']==fact['user_namespace'] and
             all(namespaces[name]['link']==row['namespaces'][name] for name in ('pid','mnt')),
             'ACTUAL_USER_AND_FINAL_PID_MNT_NAMESPACES_REQUIRED')""")
replace("set(value['child_tables'])=={'daemon','launcher','owner_intermediary'},", "set(value['child_tables'])=={'daemon'},")
replace("'ALL_THREE_COMPLETE_OWNER_TABLES_REQUIRED'", "'COMPLETE_ACTUAL_NATIVE_BROKER_CHILD_TABLE_REQUIRED'")
replace("policy.validate_child_table(value['child_tables'][parent],rows[parent]['host_pid'],rows[child]['host_pid'])", "validate_broker_child_table(value['child_tables'][parent],rows[parent]['host_pid'],rows[child]['host_pid'])")
replace("validate_observation(value['observation'],rows,policy)", "validate_observation(value['observation'],rows,policy,docs['final_baseline']['main_user_namespace'])")
replace("data.validate_live(preimage,value['data_continuity'])", "data.validate_live(preimage,value['data_continuity'],docs['final_baseline']['main_user_namespace'])")
replace("output.parent==FINAL/'qualification'", "output.parent==QUALIFICATION")
replace("'schema':'pocket4-final-business-main-guard-v1'", "'schema':'pocket4-final-business-main-guard-v2'")
replace("        inputs(plan_ref)\n        value=", "        observer.native_status()\n        inputs(plan_ref)\n        value=")
replace("        observer=None;primary=None", "        observer=None;primary=None;self._current_native_discovery=None")
replace("            observer.check()\n        except BaseException as error:", """            native_status=observer.native_status()
            need(observer.android_environment==self.docs['final_baseline']['android_env'],'LIVE_ANDROID_ENVIRONMENT_CHANGED')
            self._current_native_discovery=(self.docs['final_baseline']['init_host_pid'],dict(observer.android_environment),
                                            dict(native_status['response']))
            observer.check()
        except BaseException as error:""")
replace("    @property\n    def protected_pids", """    def discover(self):
        # Only actual fresh guard observations are returned. There is no
        # retired unshare/compat-launcher scan and no PID execution interface.
        self.guard()
        need(self._current_native_discovery is not None,'FRESH_NATIVE_MAIN_DISCOVERY_REQUIRED')
        init,environment,status=self._current_native_discovery
        return init,dict(environment),dict(status)
    @property
    def protected_pids""")

# Preserve the original complete thread/per-thread union parser. Production's
# broker owns a keeper as well as init. Neither JSON nor this read-only table
# authorizes those other PIDs; the authenticated direct init must be present.
policy=(ROOT/'inputs/main/baseline_policy.py').read_text()
block=policy[policy.index('def validate_child_table('):policy.index('\ndef validate_cell_lineage(')]
block=block.replace('def validate_child_table(', 'def validate_broker_child_table(')
block=block.replace('need(children==[child] and parent!=child,"OWNER_SINGLE_DIRECT_CHILD_REQUIRED")',
                    'need(child in children and parent!=child,"AUTHENTICATED_INIT_MUST_BE_DIRECT_BROKER_CHILD")')
s=s.replace('\ndef validate_observation(value,rows,policy,main_mapping):','\n'+block+'\ndef validate_observation(value,rows,policy,main_mapping):')
pins=[]
for field,name in (('NATIVE_OBSERVATION_SHA','native_main_observation.py'),('IMAGE_OBSERVATION_SHA','native_image_observation.py'),
                   ('HELPER_CONTRACT_SHA','helper_contract.py'),('DEPLOYMENT_SCOPE_SHA','deployment_scope.py')):
    pins.append(field+'='+repr(hashlib.sha256((ROOT/'source'/name).read_bytes()).hexdigest()))
s=s.replace('SCHEMA=','\n'.join(pins)+'\nSCHEMA=',1)
compile(s,'business_baseline.py','exec')
(ROOT/'source/business_baseline.py').write_text(s)
print('business_baseline',len(s.encode()),hashlib.sha256(s.encode()).hexdigest())
