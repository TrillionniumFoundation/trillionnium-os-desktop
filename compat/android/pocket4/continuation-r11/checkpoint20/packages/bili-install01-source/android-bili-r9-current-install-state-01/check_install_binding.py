"""Pure install current-host binding controls; all fixtures remain non-device evidence."""
import copy
def run_controls(entry,actual_host,manifest):
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
    no('FD_close_incomplete',lambda v:v['owned_fds'].update(closed=v['owned_fds']['closed']-1))
    no('partial_source',lambda v:v.update(source_published=False))
    no('controls_count_changed',lambda v:v['controls'].update(count=25))
    no('production_claim',lambda v:v.update(whole_app_production_ready=True))
    fixture=('package:'+entry.SELF+' uid:99999\n').encode()
    entry.require(entry.uid_from(fixture)==99999,'SYNTHETIC_UID_PARSER_POSITIVE')
    rows.append({'name':'synthetic_uid_positive_not_actual_identity','passed':True})
    try:entry.uid_from(('package:'+entry.SELF+' uid:10204\n').encode())
    except RuntimeError:pass
    else:raise RuntimeError('OLD_R8_HELPER_UID_ACCEPTED')
    rows.append({'name':'old_actual_R8_uid_rejected','passed':True})
    entry.require(len(rows)==11,'EXACT_INSTALL_BINDING_CONTROL_COUNT')
    return {'schema':'pocket4-R9-install-current-host-controls-v1','all_passed':True,'count':11,'cases':rows,
            'synthetic_UID_is_not_installed_UID':True,'Android_commands':0,'UI_actions':0,'children':0}
