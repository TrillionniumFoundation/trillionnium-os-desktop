function finalizeContext(h, wip, parent, app){
 const edits=[];
 const edit=(old,next,n=1)=>{const count=wip.split(old).length-1;if(count!==n)throw Error(app+":CONTEXT_ANCHOR:"+old.slice(0,80)+":"+count);wip=wip.split(old).join(next);edits.push({old,next,count});};
 const newFunctions = String.raw`
def baseline_scope(ref, baseline):
    require(baseline.get('schema') == 'pocket4-main-current-baseline-v1' and
            baseline.get('kind') == 'current-framework-generation' and
            'main_deployed' not in baseline and baseline.get('deployment_performed') is False and
            baseline['framework_epoch']['sha256'] == CURRENT_EPOCH == ref.EPOCH and
            ref.BASELINE_SHA == BASELINE_SHA and ref.QUALIFICATION_SHA == QUALIFICATION_SHA and
            type(baseline['packages'].get(PACKAGE)) is int and baseline['packages'][PACKAGE] == UID and
            baseline.get('framework_exit_cause_resolved') is False and
            baseline.get('whole_app_production_ready') is False,
            'TYPED_CURRENT_BASELINE_AND_ACTUAL_TARGET_UID_REQUIRED')
    for kind in ('user','user_de'):
        row = baseline['app_directories'][kind+'/0/'+PACKAGE]
        require(type(row) is dict and set(row) == {'device','inode','uid','gid'} and
                all(type(v) is int and v >= 0 for v in row.values()) and
                row['inode'] > 0 and row['uid'] == UID,
                'CURRENT_TARGET_DATA_DIRECTORY_BINDING_REQUIRED')
    return {'schema':'pocket4-current-recorder-scope-v1',
            'current_baseline_schema':baseline['schema'],
            'epoch_sha256':baseline['framework_epoch']['sha256'],
            'current_baseline_sha256':ref.BASELINE_SHA,
            'current_baseline_qualification_sha256':ref.QUALIFICATION_SHA,
            'package':PACKAGE,'uid':baseline['packages'][PACKAGE],'user':0}


def verify_target_data(target, baseline, binding):
    target.verify()
    raw, _ = target.read_file('/data/system/packages.list',1024*1024)
    binding.package_uids(raw,{PACKAGE:UID})
    del raw
    for kind in ('user','user_de'):
        relative = kind+'/0/'+PACKAGE
        expected = baseline['app_directories'][relative]
        fd = target.open_root('/data/'+relative,os.O_PATH|os.O_DIRECTORY|os.O_NOFOLLOW)
        primary = None
        try:
            value = os.fstat(fd)
            require(stat.S_ISDIR(value.st_mode) and
                    (value.st_dev,value.st_ino,value.st_uid,value.st_gid) ==
                    (expected['device'],expected['inode'],expected['uid'],expected['gid']),
                    'CURRENT_TARGET_DATA_DIRECTORY_IDENTITY_CHANGED')
        except BaseException as error:
            primary = error
            raise
        finally:
            try:
                os.close(fd)
            except BaseException as cleanup:
                if primary is None:
                    raise
                primary.add_note('current target directory close: '+type(cleanup).__name__)
    target.verify()


`;
 edit("\n\nclass Context:\n","\n"+newFunctions+"class Context:\n");
 edit("                 main_guard, step, plan, expected_init, deadline):\n        self.recorder = recorder",
      "                 main_guard, step, plan, expected_init, deadline, scope):\n        require(contract.sha256 == SHARED_MANIFEST and type(scope) is dict and scope == current_scope() and\n                type(scope.get('uid')) is int and type(scope.get('user')) is int,\n                'EXACT_TYPED_CURRENT_TARGET_CONTEXT_REQUIRED')\n        self.recorder = recorder");
 edit("        self.scope = current_scope()","        self.scope = dict(scope)");
 edit("        require(self.scope == current_scope(), 'TYPED_CURRENT_TARGET_SCOPE_CHANGED')",
      "        require(self.scope == current_scope() and type(self.scope.get('uid')) is int and\n                type(self.scope.get('user')) is int, 'TYPED_CURRENT_TARGET_SCOPE_CHANGED')");
 const oldBaseline="    require(activation.get('schema') == 'pocket4-main-current-baseline-v1' and\n"+
 "            activation.get('kind') == 'current-framework-generation' and\n"+
 "            'main_deployed' not in activation and activation.get('deployment_performed') is False and\n"+
 "            activation['framework_epoch']['sha256'] == CURRENT_EPOCH == ref.EPOCH and\n"+
 "            ref.BASELINE_SHA == BASELINE_SHA and ref.QUALIFICATION_SHA == QUALIFICATION_SHA and\n"+
 "            activation['packages'][PACKAGE] == UID,\n"+
 "            'TYPED_CURRENT_BASELINE_AND_ACTUAL_TARGET_UID_REQUIRED')";
 edit(oldBaseline,"    scope = baseline_scope(ref,activation)");
 edit("    def guard():\n        require(time.monotonic() < deadline,",
      "    target = None\n    def guard():\n        require(time.monotonic() < deadline,");
 edit("        return ref.main_guard(activation,epoch)\n    result['Main_before']",
      "        observation = ref.main_guard(activation,epoch)\n        if target is not None:\n            verify_target_data(target,activation,binding)\n        return observation\n    result['Main_before']");
 edit("    require(binding.same_epoch_identity(actual,expected),'FIXED_MAIN_INIT_IDENTITY_CHANGED')\n    target = None\n",
      "    require(binding.same_epoch_identity(actual,expected),'FIXED_MAIN_INIT_IDENTITY_CHANGED')\n");
 edit("ctx = Context(recorder,contract,target,environment,transport,guard,step,plan,expected['host_pid'],deadline)",
      "ctx = Context(recorder,contract,target,environment,transport,guard,step,plan,expected['host_pid'],deadline,scope)");
 edit("'Bili_Flow_instantiated':False})",
      "'Bili_Flow_instantiated':False,\n            'current_target_scope':scope,'current_target_data_directory_count':2})");
 edit("held Main/root/classpath primitives and R4 BoundArun body are reused; the new\ntransport has only its two target identity literals changed in a separate file.",
      "held Main/root/classpath primitives and the target-specific BoundArun body are reused.\nThe transport's current-epoch literal is rebound; all action/cleanup bodies are unchanged.");
 let normalized=wip;for(const e of [...edits].reverse())normalized=normalized.split(e.next).join(e.old);
 if(normalized!==parent)throw Error(app+":CONTEXT_FINAL_INVERSE");
 return {source:wip,edits,proof:{wip_inverse_exact:true,original_artifact_set_unchanged:true,scope_from_actual_current_baseline:true,Bili_Flow_or_MainBinding_instantiated:false,target_package_UID_and_both_data_directories_explicit:true,guard_owns_no_Android_commands:true}};
}

function makeCurrentAppStage(biliStage, app, root, nonce, contextName, transportName) {
 let s=biliStage;
 const edit=(a,b,n=1)=>{const found=s.split(a).length-1;if(found!==n)throw Error("STAGE_ANCHOR:"+a.slice(0,80)+":"+found);s=s.split(a).join(b);};
 edit('Exact root-owned R9 install/state staging on the actual current host R5 source.',
      'Exact '+app+' current-baseline install/state staging with its own target context.');
 edit("ROOT=Path('/home/alex/work/pocket4-owned-bili-qa-r9-install-state-01')","ROOT=Path('"+root+"')");
 edit("NONCE='d327cfd21d7b59df0c45a68efdd74c98'","NONCE='"+nonce+"'");
 edit("FILES={'install_state.py','stage_execute.py','make_request.py','INPUTS.json','README.md',\n       'host/source-manifest.json','host-stage-actual.json','session_binding.py','check_install_binding.py'}",
      "FILES={'install_state.py','"+contextName+"','"+transportName+"','stage_execute.py',\n       'make_request.py','INPUTS.json','README.md','host/source-manifest.json','host-stage-actual.json',\n       'check_install_binding.py','references/read_"+app+".py','target-artifact-reference.json'}");
 const start=s.indexOf("def stage_recorder_r5("),end=s.indexOf("def main(raw=None):",start);
 if(start<0||end<0)throw Error("STAGE_COPY_FUNCTION");
 s=s.slice(0,start)+s.slice(end);
 const before="    controls_module=load_text(files['check_install_binding.py'],SOURCE/'check_install_binding.py','current_install_pure_controls')\n"+
 "    controls=controls_module.run_controls(entry,actual_host,host_manifest)\n"+
 "    require(controls['all_passed'] is True and controls['count']==11 and\n"+
 "            len(controls['cases'])==11 and all(x['passed'] is True for x in controls['cases']),\n"+
 "            'ACTUAL_CURRENT_INSTALL_SOURCE_CONTROLS_REQUIRED')\n"+
 "    ref,original,manifest=load_original_host(files)\n"+
 "    baseline=ref.current_baseline()";
 const after="    ref,original,manifest=load_original_host(files)\n"+
 "    baseline=ref.current_baseline()\n"+
 "    context=load_text(files['"+contextName+"'],SOURCE/'"+contextName+"','current_target_context_controls')\n"+
 "    transport=load_text(files['"+transportName+"'],SOURCE/'"+transportName+"','current_target_transport_controls')\n"+
 "    controls_module=load_text(files['check_install_binding.py'],SOURCE/'check_install_binding.py','current_install_pure_controls')\n"+
 "    controls=controls_module.run_controls(entry,actual_host,host_manifest,context,transport,baseline,ref)\n"+
 "    require(controls['all_passed'] is True and controls['count']==33 and\n"+
 "            len(controls['cases'])==33 and all(x['passed'] is True for x in controls['cases']),\n"+
 "            'ACTUAL_CURRENT_APP_CONTEXT_CONTROLS_REQUIRED')";
 edit(before,after);
 edit("        result['private_current_recorder_r5']=stage_recorder_r5(ref,files,original,manifest)\n",
      "        result['shared_current_host_source_verified']=True\n        result['Bili_Flow_or_MainBinding_instantiated']=False\n");
 return s;
}

function buildCurrentAppInstall(h,app,oldFiles,contextFinal,transportRaw,helper,materials,common){
 const need=(v,s)=>{if(!v)throw Error(app+":"+s)},size=s=>h.utf8(s).length,pin=s=>({bytes:size(s),sha256:h.sha(s)});
 const canonical=v=>v===null?"null":Array.isArray(v)?"["+v.map(canonical).join(",")+"]":typeof v==="object"?"{"+Object.keys(v).sort().map(k=>JSON.stringify(k)+":"+canonical(v[k])).join(",")+"}":JSON.stringify(v);
 for(const k of ["build","stage","host_stage","nonces"])need(materials[k].pin.bytes===size(materials[k].raw)&&materials[k].pin.sha256===h.sha(materials[k].raw),"ACTUAL_"+k+"_PIN");
 need(Number.isInteger(materials.previous_helper.uid)&&materials.previous_helper.uid>=10000&&materials.previous_helper.uid<100000,"PREVIOUS_ACTUAL_HELPER_UID_REQUIRED");
 const build=JSON.parse(materials.build.raw),stage=JSON.parse(materials.stage.raw),pool=JSON.parse(materials.nonces.raw),host=JSON.parse(common.host_manifest_raw);
 const source=JSON.parse(helper.files["SOURCE_PINS.json"]);
 need(h.sha(helper.files["SOURCE_PINS.json"])===helper.manifest_sha256&&build.source_manifest_sha256===helper.manifest_sha256,"ACTUAL_BUILT_HELPER_MANIFEST");
 need(build.state==="BUILT_STATIC_VERIFIED_ANDROID_UNRUN"&&build.error===null&&build.android_installed===false&&build.source_unchanged===true&&build.tools_unchanged===true,"ACTUAL_STATIC_BUILD_REQUIRED");
 need(build.commands.length===({ihg:11,amazon:13,bestbuy:12})[app]&&build.commands.every(x=>x.returncode===0&&x.owned_child_joined===true&&x.error===null&&x.secondary_errors.length===0),"ALL_BUILD_COMMANDS_JOINED");
 need(JSON.stringify(build.tools_before)===JSON.stringify(build.tools_after),"ACTUAL_TOOL_PINS_UNCHANGED");
 need(Object.keys(source.files).length===Object.keys(build.source_sha256).length,"ACTUAL_SOURCE_CLOSURE");
 for(const[n,p]of Object.entries(source.files))need(build.source_sha256[n]===p.sha256&&h.sha(helper.files[n])===p.sha256&&size(helper.files[n])===p.bytes,"ACTUAL_SOURCE_"+n);
 need(stage.state==="OWNED_QA_APK_STATIC_BUILD_PASS_ANDROID_UNRUN"&&stage.build_returncode===0&&stage.error===null&&stage.secondary_errors.length===0&&stage.source_manifest_sha256===helper.manifest_sha256&&stage.build_result.bytes===materials.build.pin.bytes&&stage.build_result.sha256===materials.build.pin.sha256,"ACTUAL_BUILD_STAGE");
 const scope=build.current_baseline_scope_controls,report=scope.report;
 need(scope.source_sha256===source.files["check_current_baseline.py"].sha256&&report.count===21&&report.all_passed===true&&report.cases.length===21&&report.cases.every(x=>x.passed===true)&&new Set(report.cases.map(x=>x.name)).size===21,"ACTUAL_21_SCOPE_CONTROLS");
 need(h.sha(common.host_manifest_raw)===report.host_recorder_manifest_sha256&&report.production_contract_sha256===source.files["qa_contract.py"].sha256&&report.production_adapter_sha256===source.files["qa_adapter.py"].sha256,"ACTUAL_HOST_HELPER_LINK");
 need(pool.generator==="secrets.token_hex(16)"&&Object.values(pool.nonces).length===8&&Object.values(pool.nonces).every(x=>typeof x==="string"&&/^[0-9a-f]{32}$/.test(x))&&new Set(Object.values(pool.nonces)).size===8,"EXACT_ACTUAL_32HEX_NONCE_POOL");
 const nonce=pool.nonces[app+"_flow"],stateNonce=pool.nonces[app+"_state"];
 need(nonce!==stateNonce,"DISTINCT_INSTALL_NONCES");
 const rev=({ihg:2,amazon:3,bestbuy:3})[app],target=({ihg:"com.ihg.apps.android",amazon:"com.amazon.mShop.android.shopping",bestbuy:"com.bestbuy.android"})[app],uid=({ihg:10137,amazon:10129,bestbuy:10130})[app];
 const self="org.droidloom.qa."+app+".r"+rev,root="/home/alex/work/pocket4-owned-"+app+"-qa-r"+rev+"-install-state-01",key="pocket4-owned-"+app+"-qa-r"+rev+"-current-r5-install-state-01-20261106";
 need(build.package===self&&build.APK.path===stage.output+"/owned-"+app+"-qa.apk","ACTUAL_OWN_PACKAGE_APK");
 let s=oldFiles["install_state.py"];const edits=[];
 const edit=(a,b,n=1)=>{const found=s.split(a).length-1;need(found===n,"INSTALL_ANCHOR:"+a.slice(0,90)+":"+found);s=s.split(a).join(b);edits.push({old:a,next:b,count:n});};
 const constant=(name,value)=>{const re=new RegExp("^"+name+"\\s*=.*$","m"),m=s.match(re);need(m,"CONSTANT_"+name);edit(m[0],name+" = "+value);};
 const py=x=>"'"+x+"'";
 constant("ROOT","Path("+py(root)+")");constant("NONCE",py(nonce));constant("STATE_NONCE",py(stateNonce));
 constant("SELF",py(self));constant("QA_ROOT","Path("+py(stage.source)+")");constant("QA_MANIFEST",py(build.source_manifest_sha256));
 constant("BUILD","Path("+py(stage.build_result.path)+")");constant("BUILD_SHA",py(materials.build.pin.sha256));constant("BUILD_BYTES",String(materials.build.pin.bytes));
 constant("STAGE","Path("+py(stage.root+"/stage-result.json")+")");constant("STAGE_SHA",py(materials.stage.pin.sha256));constant("STAGE_BYTES",String(materials.stage.pin.bytes));
 constant("APK","Path("+py(build.APK.path)+")");constant("APK_SHA",py(build.APK.sha256));constant("APK_BYTES",String(build.APK.bytes));constant("SIGNER_SHA",py(build.signer_certificate_sha256));
 constant("REFERENCE_SHA",py(host.files["current_coordinator.py"].sha256));
 edit("REFERENCE_SHA = "+py(host.files["current_coordinator.py"].sha256),
      "REFERENCE_SHA = "+py(host.files["current_coordinator.py"].sha256)+"\n"+
      "BASE_HOST_ROOT = Path('/home/alex/work/pocket4-current-host-r5-source-01')\n"+
      "RECORDER_MANIFEST = "+py(h.sha(common.host_manifest_raw))+"\n"+
      "HOST_STAGE_SHA = "+py(materials.host_stage.pin.sha256)+"\nHOST_STAGE_BYTES = "+materials.host_stage.pin.bytes+"\n"+
      "CURRENT_EPOCH = "+py(host.current_baseline.epoch_sha256)+"\n"+
      "BASELINE_SHA = "+py(host.current_baseline.baseline_sha256)+"\n"+
      "QUALIFICATION_SHA = "+py(host.current_baseline.qualification_sha256)+"\n"+
      "PREVIOUS_HELPER_UID = "+materials.previous_helper.uid);
 const sourceSet="EXPECTED_SOURCE_FILES = {'install_state.py','"+app+"_context.py','"+app+"_transport.py','stage_execute.py',\n"+
 "    'make_request.py','INPUTS.json','README.md','host/source-manifest.json','host-stage-actual.json',\n"+
 "    'check_install_binding.py','references/read_"+app+".py','target-artifact-reference.json'}";
 const setStart=s.indexOf("EXPECTED_SOURCE_FILES ="),setEnd=s.indexOf("\n\n",setStart);need(setStart>=0&&setEnd>setStart,"EXPECTED_SOURCE_SET");
 edit(s.slice(setStart,setEnd),sourceSet);
 const oldRef=s.match(/def references\(\):\n[\s\S]*?(?=\n\ndef )/)[0];
 edit(oldRef,"def references():\n    return module(BASE_HOST_ROOT/'current_coordinator.py',REFERENCE_SHA,'current_target_install_reference')");
 edit("    require(10000 <= uid < 100000 and uid not in ","    require(10000 <= uid < 100000 and uid != PREVIOUS_HELPER_UID and uid not in ");
 edit("def qualified_inputs():",""+common.qualify_host_stage+"\n\ndef qualified_inputs():\n"+
      "    host_manifest=json.loads(read(HERE/'host/source-manifest.json',131072,RECORDER_MANIFEST))\n"+
      "    qualify_host_stage(json.loads(read(HERE/'host-stage-actual.json',65536,HOST_STAGE_SHA,HOST_STAGE_BYTES)),host_manifest)");
 edit("    read(BUILD,expected=BUILD_SHA,size=BUILD_BYTES)","    build_receipt=json.loads(read(BUILD,expected=BUILD_SHA,size=BUILD_BYTES))");
 edit("    proof=adapter.qualified_build(args,manifest,builder)","    proof=adapter.qualified_build(args,manifest,builder)\n"+common.helper_binding_checks.trimEnd());
 edit("activation=json.loads(ref.read(ref.ACTIVATION,expected=ref.ACTIVATION_SHA))","activation=ref.current_baseline()",2);
 need(!s.includes("ref.ACTIVATION")&&!s.includes("ref.VERIFIED"),"OLD_CURRENT_ACTIVATION_FORBIDDEN");
 let normalized=s;for(const e of [...edits].reverse())normalized=normalized.split(e.next).join(e.old);
 need(normalized===oldFiles["install_state.py"],"INSTALL_COMPLETE_INVERSE");
 const stageSource=common.makeStage(common.bili_stage,app,root,nonce,app+"_context.py",app+"_transport.py");
 let make=oldFiles["make_request.py"];const cm=(name,v)=>{const r=new RegExp("^"+name+"\\s*=.*$","m");need(r.test(make),"MAKE_CONSTANT_"+name);make=make.replace(r,name+"="+v)};
 cm("KEY",py(key));cm("ROOT",py(root));cm("NONCE",py(nonce));
 const schemaOld="packet={'schema':1,";need(make.includes(schemaOld),"MAKE_PACKET_SCHEMA");make=make.replace(schemaOld,"packet={'schema':2,");
 const inputs={schema:2,state:"ACTUAL_CURRENT_BUILD_AND_HOST_BOUND_INSTALL_UNRUN",helper_package:self,helper_uid:null,
 target:{package:target,uid,user:0},commercial_artifact_reference:pin(oldFiles["target-artifact-reference.json"]),
 build:{path:stage.build_result.path,...materials.build.pin},build_stage:{path:stage.root+"/stage-result.json",...materials.stage.pin},
 APK:build.APK,signer_certificate_sha256:build.signer_certificate_sha256,qa_source_manifest_sha256:helper.manifest_sha256,
 current_host_source_root:"/home/alex/work/pocket4-current-host-r5-source-01",current_host_source_manifest_sha256:h.sha(common.host_manifest_raw),
 current_host_stage:materials.host_stage.pin,current_baseline:host.current_baseline,
 nonces:{flow:nonce,state:stateNonce},actual_nonce_source:{...materials.nonces.pin,fields:[app+"_flow",app+"_state"],generator:pool.generator},
 previous_helper_uid_exclusion:materials.previous_helper,
 ordered_worker_Android_commands:13,target_APK_count:app==="bestbuy"?3:1,
 target_APK_streaming_hashes_before_and_after:true,target_user_and_user_de_current_baseline_identity:true,
 own_package_absence_required_all_users_including_uninstalled:true,install_replace_existing:false,UiAutomation_requested:false,
 source_qualification_controls:33,Bili_Flow_or_MainBinding_instantiated:false,
 whole_process_tree_cleanup_qualified:false,framework_exit_cause_resolved:false,whole_app_production_ready:false};
 const files={"install_state.py":s,[app+"_context.py"]:contextFinal,[app+"_transport.py"]:transportRaw,
 "stage_execute.py":stageSource,"make_request.py":make,"check_install_binding.py":common.controls,
 "host/source-manifest.json":common.host_manifest_raw,"host-stage-actual.json":materials.host_stage.raw,
 ["references/read_"+app+".py"]:oldFiles["references/read_"+app+".py"],
 "target-artifact-reference.json":oldFiles["target-artifact-reference.json"],
 "INPUTS.json":JSON.stringify(inputs,null,2)+"\n",
 "README.md":"# "+app+" current-baseline first helper install and state\n\n"+
 "The exact newly built signed helper is installed once with -R/-t after all-users absence checks. "+
 "The target-specific Context preserves its 13-command plan, commercial APK streaming hashes, held namespace/classpath checks and cleanup. "+
 "Its new scope comes only from the actual typed current baseline, with independent target UID and both user/user_de directory identities checked through the held root. "+
 "The shared R5 source contract is a byte-verified source closure; no Bili Flow or Bili MainBinding is instantiated.\n\n"+
 "33 pure source controls run before root staging or any Android command. The helper UID remains unknown until actual installation. "+
 "State does not connect UiAutomation. No launch, inspect, click, text, permission or settings action is requested. "+
 "Failure is not automatically retried or uninstalled. Historical failed and unknown outcomes remain unchanged. "+
 "The unresolved framework exit cause and business acceptance remain production gates. "+
 "Only direct owned process join is inherited; whole-process-tree cleanup qualification remains false.\n"};
 const manifest={schema:2,artifact:"pocket4-owned-"+app+"-qa-r"+rev+"-current-install-source-v1",
 host_recorder_manifest_sha256:h.sha(common.host_manifest_raw),qa_source_manifest_sha256:helper.manifest_sha256,
 actual_build:materials.build.pin,actual_host_stage:materials.host_stage.pin,
 files:Object.fromEntries(Object.entries(files).sort().map(([n,v])=>[n,pin(v)]))};
 files["SOURCE_PINS.json"]=JSON.stringify(manifest,null,2)+"\n";
 const manifestSHA=h.sha(files["SOURCE_PINS.json"]),packet={schema:2,source_manifest_sha256:manifestSHA,nonce,files},stdin=canonical(packet)+"\n";
 need(size(stdin)<=262144&&Object.values(files).every(v=>size(v)>0&&size(v)<=65536),"STAGE_SOURCE_PACKET_BOUNDS");
 const wrapper="import hashlib,json,sys\nraw=sys.stdin.buffer.read(262145)\n"+
 "assert hashlib.sha256(raw).hexdigest()=='"+h.sha(stdin)+"'\n"+
 "p=json.loads(raw);src=p['files']['stage_execute.py'].encode('utf-8')\n"+
 "assert hashlib.sha256(src).hexdigest()=='"+h.sha(stageSource)+"'\n"+
 "scope={'__name__':'owned_qa_stage','__file__':'"+root+"/source/stage_execute.py'}\n"+
 "exec(compile(src,scope['__file__'],'exec'),scope)\nraise SystemExit(scope['main'](raw))\n";
 const request={host:"pocket4",executable:"/usr/bin/sudo",args:["-n","/usr/bin/python3","-I","-c",wrapper],cwd:"/home/alex/work",env:{PYTHONDONTWRITEBYTECODE:"1"},
 stdin,idempotency_key:key,timeout_seconds:300,cpu_quota_percent:100,memory_max_bytes:536870912,nice:10};
 return{app,files,request,inputs,manifest_sha256:manifestSHA,install_edits:edits,install_inverse_exact:true,
 local_Python_compile:false,local_Python_controls:false,installed_helper_uid:null,Hepta_dispatched:false};
}
