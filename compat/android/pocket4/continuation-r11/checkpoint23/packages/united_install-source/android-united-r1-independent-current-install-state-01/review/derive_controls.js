function deriveIndependentInstallControls(slug,parent,fragment,h) {
  const edits=[];
  let source=parent;
  function edit(old,replacement,label) {
    const at=source.indexOf(old);
    if(at<0 || source.indexOf(old,at+old.length)>=0) throw Error(label+": exact occurrence");
    source=source.slice(0,at)+replacement+source.slice(at+old.length);
    edits.push({label,offset:at,old,replacement});
  }
  edit("CONTROL_COUNT = 68","CONTROL_COUNT = 75","retain 68 controls plus seven independent-target routes");
  edit("rejected('previous_actual_helper_uid_rejected',lambda:entry.uid_from(\n        ('package:'+entry.SELF+' uid:'+str(entry.PREVIOUS_HELPER_UID)+'\\n').encode()))",
       "rejected('actual_parent_helper_uid_rejected',lambda:entry.uid_from(\n        ('package:'+entry.SELF+' uid:'+str(entry.PARENT_HELPER_UID)+'\\n').encode()))","historical parent helper is exclusion only");
  edit("    scope=context.baseline_scope(ref,baseline)",
       "    authority=context.qualify_target_metadata(json.loads(files['actual-target-metadata.json']),\n        json.loads(files['target-artifact-reference.json']))\n    scope=context.baseline_scope(ref,baseline,authority)","actual separate target authority");
  edit("yes('actual_baseline_projects_own_target_scope')","yes('actual_metadata_projects_separate_target_scope_without_changing_baseline')","truthful scope control name");
  edit("rejected(name,lambda:context.baseline_scope(ref,value))","rejected(name,lambda:context.baseline_scope(ref,value,authority))","baseline rejection retains target authority");
  edit("    base_no('wrong_target_uid',lambda v:v['packages'].update({context.PACKAGE:10117}))\n    base_no('bool_target_uid',lambda v:v['packages'].update({context.PACKAGE:True}))\n    base_no('missing_current_target_directory',lambda v:v['app_directories'].pop('user_de/0/'+context.PACKAGE))\n    base_no('foreign_current_target_directory_owner',lambda v:v['app_directories']['user/0/'+context.PACKAGE].update(uid=10117))",
       "    def authority_no(name,change):\n        value=copy.deepcopy(authority);change(value)\n        rejected(name,lambda:context.baseline_scope(ref,baseline,value))\n    def both_metadata(value,uid):\n        for key in ('metadata_before','metadata_after'):value[key]['uid']=uid\n    def both_directories(value,change):\n        for key in ('data_directories_before','data_directories_after'):change(value[key])\n    authority_no('wrong_target_uid',lambda v:both_metadata(v,10117))\n    authority_no('bool_target_uid',lambda v:both_metadata(v,True))\n    authority_no('missing_current_target_directory',lambda v:both_directories(v,lambda rows:rows.pop()))\n    authority_no('foreign_current_target_directory_owner',lambda v:both_directories(v,lambda rows:rows[0].update(uid=10117)))","same four controls now reach real separate authority");
  edit("lambda wrong=wrong:context.baseline_scope(wrong,baseline)","lambda wrong=wrong:context.baseline_scope(wrong,baseline,authority)","reference pin rejection with separate authority");
  edit("'bestbuy_r4_install_plan_contract'","'"+slug+"_r1_install_plan_contract'","actual own helper module label");
  edit("entry.SELF=='org.droidloom.qa.bestbuy.r4' and\n                  qa.PROTOCOL=='pocket4-owned-bestbuy-qa-v4','EXACT_R4_PLAN_CONTRACT')",
       "entry.SELF=='org.droidloom.qa."+slug+".r1' and\n                  qa.PROTOCOL=='pocket4-owned-"+slug+"-qa-v1','EXACT_INDEPENDENT_R1_PLAN_CONTRACT')","real actual helper protocol");
  edit("'ACTUAL_R4_ORDERED_INSTALL_STATE_PLAN'","'ACTUAL_INDEPENDENT_R1_ORDERED_INSTALL_STATE_PLAN'","own plan qualification label");
  edit("yes('production_ordered_commands_actual_R4_contract_positive')","yes('production_ordered_commands_actual_independent_R1_contract_positive')","own plan positive name");
  edit("rejected('production_ordered_commands_previous_R3_package_rejected',lambda:context.ordered_commands(\n        qa,'org.droidloom.qa.bestbuy.r3',entry.GUEST_APK,entry.STATE_NONCE))",
       "rejected('production_ordered_commands_parent_helper_package_rejected',lambda:context.ordered_commands(\n        qa,'org.droidloom.qa.bestbuy.r4',entry.GUEST_APK,entry.STATE_NONCE))","actual parent package refused");
  const route = "    rows.extend(discovery_controls.run_context_route_controls(context,files,baseline,legacy_source,source_manifest_sha256))";
  edit(route,route+"\n    rows.extend(run_independent_target_controls(entry,context,transport,baseline,ref,files,\n        source_manifest_sha256,discovery_controls,legacy_source,manifest))","production authority loader and held route invoked");
  edit("'legacy_discover_failure_reproduced_in_memory':True}","'legacy_discover_failure_reproduced_in_memory':True,\n            'independent_target_authority_and_held_route_controls':7,\n            'immutable_baseline_packages_modified':False,\n            'new_target_held_IO_is_explicit_synthetic_seam':True}","controlled IO boundary disclosed");
  edit("    return rows\n","    return rows\n"+fragment,"append exact seven independent controls"); // only run_source_controls has this at parent
  let inverse=source;
  for (const e of [...edits].reverse()) {
    if(inverse.slice(e.offset,e.offset+e.replacement.length)!==e.replacement)throw Error("inverse:"+e.label);
    inverse=inverse.slice(0,e.offset)+e.old+inverse.slice(e.offset+e.replacement.length);
  }
  if(inverse!==parent)throw Error("inverse parent");
  return {source,edits,proof:{parent:{bytes:h.utf8(parent).length,sha256:h.sha(parent),blob:h.git(parent)},candidate:{bytes:h.utf8(source).length,sha256:h.sha(source),blob:h.git(source)},fragment:{bytes:h.utf8(fragment).length,sha256:h.sha(fragment),blob:h.git(fragment)},edits:edits.length,inverse_exact:true,control_count:75,Python_executed:false}};
}
