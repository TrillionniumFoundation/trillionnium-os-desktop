"""Pure install current-host binding controls; all fixtures remain non-device evidence."""
import copy
import types
def run_controls(entry,actual_host,manifest,files,baseline,recorder):
    rows=[]
    entry.qualify_host_stage(actual_host,manifest)
    rows.append({'name':'complete_actual_host_stage_accepted','passed':True})
    def no(name,change):
        value=copy.deepcopy(actual_host);change(value)
        try:entry.qualify_host_stage(value,manifest)
        except RuntimeError:pass
        else:raise RuntimeError('HOST_STAGE_NEGATIVE_ACCEPTED')
        rows.append({'name':name,'passed':True})
    no('host_stage_error',lambda v:v.update(ok=False))
    no('old_host_manifest',lambda v:v.update(source_manifest_sha256='52b95328e2f07aaf4416b7f48c9046ffa465337cad7a410ea3a7027512720dc1'))
    no('missing_final_Main',lambda v:v.pop('Main_final'))
    no('wrong_final_epoch',lambda v:v['Main_final'].update(Main_epoch_sha256='48cb65c93ff81edbf160455af6506f5c703f0958363f15de4a80ece57c37e93f'))
    no('FD_close_incomplete',lambda v:v['source_fds'].update(closed=v['source_fds']['closed']-1))
    no('partial_source',lambda v:v.update(all_staged_sources_unchanged=False))
    no('controls_count_changed',lambda v:v['controls'].update(count=37))
    no('production_claim',lambda v:v.update(whole_app_production_ready=True))
    def host_no_exact(name,change,code):
        value=copy.deepcopy(actual_host);change(value)
        try:entry.qualify_host_stage(value,manifest)
        except RuntimeError as error:entry.require(str(error)==code,'R6_HOST_CONTROL_WRONG_FIRST_ERROR')
        else:raise RuntimeError('R6_HOST_NEGATIVE_ACCEPTED:'+name)
        rows.append({'name':name,'passed':True})
    host_no_exact('previous_host_stage_schema_rejected',lambda v:v.update(schema='pocket4-current-host-source-stage-result-v1'),
                  'ACTUAL_COMPLETE_R6_HOST_SOURCE_STAGE_REQUIRED')
    host_no_exact('publication_FD_close_incomplete',lambda v:v['publication_fds'].update(closed=v['publication_fds']['closed']-1),
                  'ACTUAL_CURRENT_HOST_SOURCE_FDS_NOT_RETIRED')
    host_no_exact('published_source_leaf_drift',lambda v:v['source_pins']['recorder.py'].update(sha256='0'*64),
                  'ACTUAL_R6_PUBLISHED_SOURCE_PINS_REQUIRED')
    host_no_exact('unauthenticated_owner_chain',lambda v:v['Main_before'].update(authenticated_owner_chain_matches=False),
                  'CURRENT_HOST_STAGE_MAIN_FENCES_CHANGED')
    host_no_exact('current_user_namespace_mismatch',lambda v:v['Main_final'].update(current_user_namespaces_match=False),
                  'CURRENT_HOST_STAGE_MAIN_FENCES_CHANGED')
    host_no_exact('durable_host_stage_pin_drift',lambda v:v['stage_result'].update(sha256='0'*64),
                  'ACTUAL_R6_DURABLE_STAGE_PIN_REQUIRED')
    host_no_exact('compiled_source_name_changed',lambda v:v['controls']['compiled_sources'].__setitem__(0,'foreign.py'),
                  'ACTUAL_38_CURRENT_HOST_CONTROLS_REQUIRED')
    fixture=('package:'+entry.SELF+' uid:99999\n').encode()
    entry.require(entry.uid_from(fixture)==99999,'SYNTHETIC_UID_PARSER_POSITIVE')
    rows.append({'name':'synthetic_uid_positive_not_actual_identity','passed':True})
    try:entry.uid_from(('package:'+entry.SELF+' uid:10204\n').encode())
    except RuntimeError:pass
    else:raise RuntimeError('OLD_R8_HELPER_UID_ACCEPTED')
    rows.append({'name':'old_actual_R8_uid_rejected','passed':True})
    try:entry.uid_from(('package:'+entry.SELF+' uid:10152\n').encode())
    except RuntimeError:pass
    else:raise RuntimeError('OLD_R9_HELPER_UID_ACCEPTED')
    rows.append({'name':'old_actual_R9_uid_rejected','passed':True})
    discovery_controls = types.ModuleType('production_current_discovery_controls')
    exec(compile(files['check_current_discovery.py'],'<current-discovery-controls>','exec'),discovery_controls.__dict__)
    legacy_source = entry.read(entry.BASE_HOST_ROOT/'references/android_app.py',131072,
                               discovery_controls.LEGACY_SHA)
    rows.extend(discovery_controls.run_discovery_controls(files['current_discovery.py'],baseline,legacy_source))
    rows.extend(discovery_controls.run_bili_route_controls(entry,files,baseline,legacy_source,recorder))
    entry.require(len(rows)==37,'EXACT_INSTALL_BINDING_CONTROL_COUNT')
    return {'schema':'pocket4-R10-install-current-host-controls-v2','all_passed':True,'count':37,'cases':rows,
            'synthetic_UID_is_not_installed_UID':True,'Android_commands':0,'UI_actions':0,'children':0,
            'new_owner_discovery_controls':18,'production_discovery_and_Bili_bind_route_used':True,
            'legacy_discover_failure_reproduced_in_memory':True}
