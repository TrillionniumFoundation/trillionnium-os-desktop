function deriveNextFixedMetadata(item,base,lock,discovery,newFunctions,h){
 let source=base,edits=[];
 function rep(from,to,why,count=1){
  if(source.split(from).length-1!==count)throw Error(item.key+":"+why);
  let start=0;for(let i=0;i<count;i++){const at=source.indexOf(from,start);
   source=source.slice(0,at)+to+source.slice(at+from.length);edits.push({index:at,from,to,why});start=at+to.length;}
 }
 rep("One fixed 12306 metadata read, with the qualified held Main primitives.",
     "One fixed "+item.name+" metadata read on current cell02; no runtime authority yet.","doc");
 const oldHeader=source.slice(source.indexOf("ROOT = Path("),source.indexOf("LIST = "));
 const header="ROOT = Path('/home/alex/work/pocket4-current-cell02-"+item.key+"-metadata-01')\n"+
 "SOURCE_PATH = ROOT/'source/read_target.py'\nNONCE = '__FRESH_METADATA_NONCE__'\n"+
 "PACKAGE = '"+item.package+"'\nUSER = 0\nHISTORICAL_VERSION = "+item.version+"\n"+
 "RECORDER_ROOT = Path('/home/alex/work/pocket4-current-host-r6-source-01')\n"+
 "REFERENCE_SHA = '0a4a9f0d02b2a62f2b902983e43360c751a8f1952fb9ae7399850b112cb50a89'\n"+
 "RECORDER_MANIFEST = '002ee581a4bb399536dd7d594d01f050e2540d9c049b0cfb37e1c96954b6caff'\n"+
 "SOURCE_CONTRACT_SHA = 'f92d2598221c5bf65e783df39864879a2056da47f794680668b34df11f97da49'\n"+
 "CURRENT_EPOCH = '7d927812392d30ab8cca43da87c0785e24695ca724da93b3b465122502b8045c'\n"+
 "BASELINE_SHA = '633912ff4595ce898c4c0e0f9ac06c1f422203d90fbd2e583192f35ff7a04364'\n"+
 "QUALIFICATION_SHA = 'ae8d54ee64fe23676d7f68f8092c0915d3f0f41662d8b7d4be86b85201071a6e'\n"+
 "DISCOVERY_SHA = '9ed0069897faebba50cec3d93b08da54f1c791d6e2e775d26ec798c38b227886'\n"+
 "DISCOVERY_BYTES = 8332\nACTION_LOCK_WAIT_SECONDS = 5.0\nACTION_LOCK_POLL_SECONDS = 0.05\n";
 rep(oldHeader,header,"current-baseline-fixed-target-and-pending-nonce");
 rep("import argparse\n","import argparse\nimport errno\nimport fcntl\n","lock-imports");
 rep("def sha(raw):","require = need\n\n\n"+lock+"\n"+newFunctions+"\n\ndef sha(raw):","explicit-new-target-scope-and-directory-binding");
 rep("need(Path(__file__).resolve()==SOURCE_PATH and re.fullmatch('[0-9a-f]{64}',source_sha),",
     "need(Path(__file__).resolve()==SOURCE_PATH and re.fullmatch('[0-9a-f]{64}',source_sha) and\n         re.fullmatch('[0-9a-f]{32}',NONCE),","placeholder-cannot-run");
 rep("reference=load(INSTALLED_SOURCE/'references/readonly_r3_coordinator.py',REFERENCE_SHA,'ticket12306_main_reference')",
     "reference=load(RECORDER_ROOT/'current_coordinator.py',REFERENCE_SHA,'fixed_target_current_main_reference',7442)","current-public-reference");
 rep("'scope':'one exact 12306 user0 installed artifact and current launcher metadata read'",
     "'scope':'one exact "+item.name+" user0 current-cell02 metadata observation'","fixed-result-scope");
 rep("target=ctx=None;lock=None;opened=[];phase='source';started=time.monotonic();guard=None",
     "target=ctx=directories=None;lock=None;opened=[];phase='source';started=time.monotonic();guard=None","held-directory-lifetime");
 rep("        install=load(INSTALLED_SOURCE/'install_state.py',INSTALL_SHA,'ticket12306_lock_reference',INSTALL_BYTES)\n"+
     "        activation=json.loads(reference.read(reference.ACTIVATION,expected=reference.ACTIVATION_SHA))\n"+
     "        verified=json.loads(reference.read(reference.VERIFIED,expected=reference.VERIFIED_SHA))\n"+
     "        need(activation['main_deployed'] is True and verified['main_deployed'] is True and\n"+
     "             verified['framework_epoch_sha256']==reference.EPOCH,'ACTIVATION_NOT_VERIFIED')",
     "        activation=reference.current_baseline()\n        result['current_metadata_scope']=current_baseline_scope(reference,activation)","immutable-baseline-not-target-authority");
 rep("            read(INSTALLED_SOURCE/'references/readonly_r3_coordinator.py',expected=REFERENCE_SHA)\n"+
     "            read(INSTALLED_SOURCE/'install_state.py',expected=INSTALL_SHA,size=INSTALL_BYTES)",
     "            read(RECORDER_ROOT/'current_coordinator.py',expected=REFERENCE_SHA,size=7442)\n"+
     "            read(SOURCE_PATH.parent/'current_discovery.py',expected=DISCOVERY_SHA,size=DISCOVERY_BYTES)","every-guard-public-source-pins");
 rep("        lock=install.acquire_action_lock(recorder.ACTION_LOCK,result['action_lock'])",
     "        lock=acquire_action_lock(recorder.ACTION_LOCK,result['action_lock'])","exact-shared-action-lock-body");
 rep("        init,discovered,status=app.discover()","        init,discovered,status=discover_main(app,activation,epoch,guard)","actual-production-current-owner-discovery");
 rep("        need(activation['packages'].get(PACKAGE)==before['uid'],'TICKET12306_UID_CHANGED_FROM_FIXED_ACTIVATION')",
     "        phase='current_target_directory_observation'\n        directories=DataDirectories(target,before['uid'],binding,started+WORK_SECONDS)\n        result['data_directories_before']=directories.record()",
     "observe-new-UID-and-two-inodes-not-four-target-baseline");
 rep("        target.verify();guard()\n        result.update",
     "        result['data_directories_after']=directories.record()\n        need(result['data_directories_before']==result['data_directories_after'],\n             'CURRENT_TARGET_DATA_DIRECTORY_CHAIN_CHANGED')\n        target.verify();guard()\n        result.update","fresh-target-directory-revalidation");
 rep("        if target is not None:\n            try:target.close();result['held_binding_released']=True",
     "        if directories is not None:\n            try:result['target_directory_cleanup']=directories.close()\n            except BaseException as error:remember(result,'target_directory_fd_close',error)\n        if target is not None:\n            try:target.close();result['held_binding_released']=True","close-owned-directory-FDs-before-root-authority");
 rep("'UID_version_APK_paths_are_current_observations_not_historical_assumptions':True,",
     "'UID_version_APK_paths_are_current_observations_not_historical_assumptions':True,\n"+
     "            'target_data_directory_contents_read':False,'private_baseline_exported':False,\n"+
     "            'immutable_baseline_packages_modified':False,'business_action_authority':False,\n"+
     "            'future_install_or_UI_requires_separate_target_scope':True,","qualification-boundaries");
 let inverse=source;for(const e of [...edits].reverse()){
  if(inverse.slice(e.index,e.index+e.to.length)!==e.to)throw Error("INVERSE:"+e.why);
  inverse=inverse.slice(0,e.index)+e.from+inverse.slice(e.index+e.to.length);}
 if(inverse!==base)throw Error("FULL_ORIGINAL_INVERSE");
 return{...item,source,edits,pin:{bytes:h.utf8(source).length,sha256:h.sha(source)},
  complete_inverse_exact:true,discovery,source_only:true,packet_created:false};
}
