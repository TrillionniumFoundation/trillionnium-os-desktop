/* Pure source compiler. No filesystem/network/process/device/ref API.
 * Only compileActual exports source bundles; it requires complete actual raw
 * baseline and qualification receipts plus externally verified original pins.
 */
function createCurrentBaselineForkCompiler02(h) {
  "use strict";
  const need=(v,c)=>{if(!v)throw Error(c);};
  const digest=s=>{need(typeof s==="string","EXACT_UTF8_STRING_REQUIRED");return h.sha(s);};
  const size=s=>h.utf8(s).length;
  const shaPattern=/^[0-9a-f]{64}$/;
  const oldEpoch="48cb65c93ff81edbf160455af6506f5c703f0958363f15de4a80ece57c37e93f";
  const schema="pocket4-main-current-baseline-v1";
  const expectedBaselineSource="9bc710444bff9d90cb3375fd5acb155e0438e2a71a65348b23d4483cf81d00f9";
  const oldHostManifest="52b95328e2f07aaf4416b7f48c9046ffa465337cad7a410ea3a7027512720dc1";
  const oldCoordinator="e2769eeeae2d620456a67959dfaff3b07545f2352cd9a60692450451004c39fd";
  const specs={
    bili:{old:8,next:9,target:"tv.danmaku.bili",manifest:"8e3454bcc9ebe1ff55dcaf62706ce1176cfa1d0f0ede7099cbbfa46f4ad53f1e"},
    ihg:{old:1,next:2,target:"com.ihg.apps.android",manifest:"ab971f5b361f1d97b8036c954a6b88734b7faedbeed6349b873ead85fa79d5f3"},
    amazon:{old:2,next:3,target:"com.amazon.mShop.android.shopping",manifest:"32be752c72fc4cfe7f50a73bba54cd6444e9ed3990b4f0cd809cb7023b540b98"},
    bestbuy:{old:2,next:3,target:"com.bestbuy.android",manifest:"f7f13e75bf38518581581a2851714a3bb67a169dddeec1d444de2150398f01f9"}
  };
  const exactPin=(raw,pin)=>{
    need(pin&&Number.isSafeInteger(pin.bytes)&&pin.bytes>0&&shaPattern.test(pin.sha256),"EXTERNAL_RAW_PIN_REQUIRED");
    need(size(raw)===pin.bytes&&digest(raw)===pin.sha256,"EXTERNAL_RAW_PIN_MISMATCH");
    return JSON.parse(raw);
  };
  const pin=raw=>({bytes:size(raw),sha256:digest(raw)});
  const fdClosed=row=>row&&Number.isSafeInteger(row.acquired)&&row.acquired>0&&
    row.acquired===row.close_attempts&&row.acquired===row.closed&&row.remaining===0&&
    Array.isArray(row.errors)&&row.errors.length===0;
  function actualBinding(input) {
    need(input&&Object.keys(input).sort().join(",")==="current_guard_raw,qualification_raw,result_pin,result_raw","EXACT_ACTUAL_INPUT_SET");
    const r=exactPin(input.result_raw,input.result_pin);
    need(r.schema==="pocket4-main-current-baseline-result-v1"&&r.ok===true&&r.identity_qualified===true&&
      r.error===null&&Array.isArray(r.secondary_errors)&&r.secondary_errors.length===0&&
      r.final_fixed_identity_equal===true&&r.historical_inputs_and_boot_unchanged===true,
      "ACTUAL_COMPLETE_BASELINE_RESULT_REQUIRED");
    need(r.source_manifest_sha256===expectedBaselineSource&&r.source_basis.runtime_R4_manifest_sha256===oldHostManifest,
      "EXACT_REVIEWED_BASELINE_SOURCE_REQUIRED");
    need(r.namespace_entry===false&&r.deployment_performed===false&&r.automatic_retry===false&&
      r.old_epoch_reauthorized===false&&r.framework_exit_cause_resolved===false&&r.whole_app_production_ready===false&&
      ["Android_commands","UI_actions","App_launches","helper_installs"].every(k=>r[k]===0),
      "BASELINE_SCOPE_OR_PRODUCTION_BOUNDARY_CHANGED");
    need(fdClosed(r.observation_fds)&&fdClosed(r.publication_fds),"ACTUAL_BASELINE_FDS_NOT_CLOSED");
    need(r.controls&&r.controls.all_passed===true&&r.controls.count===32&&r.controls.cases.length===32&&
      r.controls.cases.every(c=>c.passed===true)&&new Set(r.controls.cases.map(c=>c.name)).size===32&&
      r.controls.compiled_sources.length===7&&r.controls.guard_template_values_are_syntax_only===true,
      "ACTUAL_BASELINE_CONTROLS_REQUIRED");
    need(r.double_sample_count===3&&Number.isSafeInteger(r.explicit_observation_span_ns)&&
      r.explicit_observation_span_ns>=10000000000&&r.explicit_observation_span_ns<=90000000000,
      "ACTUAL_BOUNDED_IDENTITY_OBSERVATION_REQUIRED");
    need(shaPattern.test(r.new_epoch_sha256)&&r.new_epoch_sha256!==oldEpoch,"NEW_ACTUAL_EPOCH_REQUIRED");
    const q=exactPin(input.qualification_raw,r.qualification);
    need(q.schema==="pocket4-main-current-baseline-qualification-v1"&&q.identity_qualified===true&&
      q.epoch_sha256===r.new_epoch_sha256&&q.source_manifest_sha256===expectedBaselineSource&&
      q.historical_deployment_revalidated===true&&q.new_deployment_performed===false&&q.old_epoch_reauthorized===false&&
      q.three_double_samples_equal===true&&q.final_seven_role_identity_equal===true&&
      q.all_owned_service_children_joined===true&&q.framework_exit_cause_resolved===false&&
      q.production_ready===false&&q.UI_or_install_runtime_admitted===false&&
      JSON.stringify(q.baseline)===JSON.stringify(r.baseline)&&fdClosed(q.observation_fds),
      "ACTUAL_QUALIFICATION_PARENT_BINDING_REQUIRED");
    need(r.baseline.path==="/home/alex/work/pocket4-main-current-baseline-01/baseline.private.json"&&
      r.qualification.path==="/home/alex/work/pocket4-main-current-baseline-01/qualification.json"&&
      r.generated_current_guard.path==="/home/alex/work/pocket4-main-current-baseline-01/current_baseline_guard.py"&&
      shaPattern.test(r.baseline.sha256),"FIXED_CURRENT_BASELINE_OUTPUT_PATHS_REQUIRED");
    need(size(input.current_guard_raw)===r.generated_current_guard.bytes&&
      digest(input.current_guard_raw)===r.generated_current_guard.sha256,"ACTUAL_GENERATED_GUARD_PIN_REQUIRED");
    const g=input.current_guard_raw;
    for(const s of [
      'BASELINE_SHA="'+r.baseline.sha256+'"','QUALIFICATION_SHA="'+r.qualification.sha256+'"',
      'MAIN_EPOCH="'+r.new_epoch_sha256+'"','SOURCE_MANIFEST_SHA="'+expectedBaselineSource+'"',
      'BASELINE_BYTES='+r.baseline.bytes,'QUALIFICATION_BYTES='+r.qualification.bytes])
      need(g.split(s).length===2,"ACTUAL_GUARD_LITERAL_MISMATCH");
    need(!g.includes("@@"),"UNBOUND_CURRENT_GUARD_TEMPLATE");
    const uids=r.selected_package_uids;
    const packages=[...Object.values(specs).map(x=>x.target),"local.pocket4.actions.v2"];
    need(uids&&Object.keys(uids).sort().join(",")===packages.sort().join(",")&&
      Object.values(uids).every(v=>Number.isSafeInteger(v)&&v>=10000&&v<100000)&&
      new Set(Object.values(uids)).size===5,"ACTUAL_SELECTED_UID_SET_REQUIRED");
    return {epoch:r.new_epoch_sha256,baseline:r.baseline,qualification:r.qualification,
      guard:r.generated_current_guard,result:input.result_pin,guard_raw:g,uids,
      unresolved_framework_exit_cause:true,helper_installed_uid:null,APK_sha256:null,signer_sha256:null};
  }
  function checkOld(raw,files,wantedManifest) {
    need(digest(raw)===wantedManifest,"FROZEN_PARENT_MANIFEST_CHANGED");
    const m=JSON.parse(raw);
    need(m.files&&typeof files==="object"&&!Array.isArray(files),"FROZEN_PARENT_SOURCE_SET");
    for(const[name,text]of Object.entries(files)){
      need(m.files[name]&&size(text)===m.files[name].bytes&&digest(text)===m.files[name].sha256,
        "FROZEN_PARENT_SOURCE_CHANGED:"+name);
    }
    return m;
  }
  function editor(original,name) {
    let text=original;const edits=[];
    return {get text(){return text;},edits,
      one(a,b){need(a!==b&&text.split(a).length===2,"EXACT_SINGLE_PATCH_SITE:"+name);text=text.replace(a,b);edits.push({old:a,next:b,count:1});},
      all(a,b){if(a===b)return;const n=text.split(a).length-1;if(!n)return;text=text.split(a).join(b);edits.push({old:a,next:b,count:n});},
      inverse(){let r=text;for(const e of [...edits].reverse()){need(r.split(e.next).length-1===e.count,"PATCH_INVERSE_SITE_COLLISION:"+name);r=r.split(e.next).join(e.old);}need(r===original,"PATCH_INVERSE_NOT_EXACT:"+name);return true;}}
  }
  function helperScopeControlSource() { return "\"\"\"Current-baseline scope controls using this generated production parser.\"\"\"\nimport ast,copy,hashlib,json,types\nfrom pathlib import Path\nHERE=Path(__file__).resolve().parent\ndef run_controls():\n    raw=(HERE/'qa_contract.py').read_bytes()\n    qa=types.ModuleType('actual_current_baseline_qa')\n    qa.__file__=str(HERE/'qa_contract.py')\n    exec(compile(raw,qa.__file__,'exec'),qa.__dict__)\n    base={'package':qa.PACKAGE,'uid':qa.UID,'user':0,'display':0,\n          'activity':qa.PACKAGE+'/Fixture','window_token':'1234',\n          'main_epoch_sha256':qa.MAIN_EPOCH,'main_baseline_schema':qa.MAIN_BASELINE_SCHEMA,\n          'main_baseline_sha256':qa.MAIN_BASELINE_SHA,\n          'main_baseline_qualification_sha256':qa.MAIN_BASELINE_QUALIFICATION_SHA}\n    rows=[]\n    def ok(name,value):\n        qa.require(qa.scope(value)==base,'CURRENT_SCOPE_POSITIVE_FAILED')\n        rows.append({'name':name,'passed':True})\n    def no(name,change):\n        v=copy.deepcopy(base);change(v)\n        try:qa.scope(v)\n        except qa.ProtocolError:pass\n        else:raise RuntimeError('CURRENT_SCOPE_NEGATIVE_ACCEPTED')\n        rows.append({'name':name,'passed':True})\n    ok('exact_new_current_scope',copy.deepcopy(base))\n    for key in ('main_baseline_schema','main_baseline_sha256','main_baseline_qualification_sha256'):\n        no('missing_'+key,lambda v,k=key:v.pop(k))\n    no('old_epoch',lambda v:v.update(main_epoch_sha256='48cb65c93ff81edbf160455af6506f5c703f0958363f15de4a80ece57c37e93f'))\n    no('old_baseline_schema',lambda v:v.update(main_baseline_schema='pocket4-framework-epoch-v1'))\n    no('wrong_baseline_digest',lambda v:v.update(main_baseline_sha256='0'*64))\n    no('wrong_qualification_digest',lambda v:v.update(main_baseline_qualification_sha256='0'*64))\n    no('extra_scope_field',lambda v:v.update(unbound=True))\n    no('wrong_target_uid',lambda v:v.update(uid=qa.UID+1))\n    no('foreign_package',lambda v:v.update(package='example.unrelated'))\n    no('wrong_display',lambda v:v.update(display=1))\n    adapter_raw=(HERE/'qa_adapter.py').read_bytes()\n    tree=ast.parse(adapter_raw)\n    original_session=next(x for x in tree.body if isinstance(x,ast.ClassDef) and x.name=='Session')\n    selected_init=[x for x in original_session.body if isinstance(x,ast.FunctionDef) and x.name=='__init__']\n    qa.require(len(selected_init)==1,'EXACT_PRODUCTION_SESSION_CONSTRUCTOR_REQUIRED')\n    session_class=copy.deepcopy(original_session);session_class.body=copy.deepcopy(selected_init)\n    selected=[x for x in tree.body if\n              (isinstance(x,ast.FunctionDef) and x.name=='require') or\n              (isinstance(x,ast.Assign) and len(x.targets)==1 and isinstance(x.targets[0],ast.Name) and\n               x.targets[0].id=='RECORDER_MANIFEST_SHA')]+[session_class]\n    qa.require(len(selected)==3,'EXACT_PRODUCTION_SESSION_GUARD_SELECTION_REQUIRED')\n    session_scope={}\n    exec(compile(ast.Module(body=selected,type_ignores=[]),'actual_session_constructor','exec'),session_scope)\n    host_sha=session_scope['RECORDER_MANIFEST_SHA']\n    def fixture():\n        return types.SimpleNamespace(contract=types.SimpleNamespace(sha256=host_sha),_private_backend_transport=False,\n            scope={'schema':'pocket4-current-recorder-scope-v1','current_baseline_schema':qa.MAIN_BASELINE_SCHEMA,\n                   'epoch_sha256':qa.MAIN_EPOCH,'current_baseline_sha256':qa.MAIN_BASELINE_SHA,\n                   'current_baseline_qualification_sha256':qa.MAIN_BASELINE_QUALIFICATION_SHA,\n                   'package':qa.PACKAGE,'uid':qa.UID})\n    session_scope['Session'](fixture(),None,qa,{},99999)\n    rows.append({'name':'actual_R5_session_scope_positive','passed':True})\n    def host_no(name,change):\n        flow=fixture();change(flow)\n        try:session_scope['Session'](flow,None,qa,{},99999)\n        except RuntimeError:pass\n        else:raise RuntimeError('CURRENT_HOST_SESSION_NEGATIVE_ACCEPTED')\n        rows.append({'name':name,'passed':True})\n    host_no('old_R4_recorder_rejected',lambda f:setattr(f.contract,'sha256','52b95328e2f07aaf4416b7f48c9046ffa465337cad7a410ea3a7027512720dc1'))\n    host_no('missing_typed_flow_schema',lambda f:f.scope.pop('schema'))\n    host_no('wrong_current_baseline_schema',lambda f:f.scope.update(current_baseline_schema='old-activation'))\n    host_no('old_host_epoch',lambda f:f.scope.update(epoch_sha256='48cb65c93ff81edbf160455af6506f5c703f0958363f15de4a80ece57c37e93f'))\n    host_no('wrong_host_baseline',lambda f:f.scope.update(current_baseline_sha256='0'*64))\n    host_no('wrong_host_qualification',lambda f:f.scope.update(current_baseline_qualification_sha256='0'*64))\n    host_no('foreign_host_package',lambda f:f.scope.update(package='example.unrelated'))\n    host_no('bool_host_uid',lambda f:f.scope.update(uid=True))\n    qa.require(len(rows)==21,'EXACT_CURRENT_BASELINE_SCOPE_CASES')\n    return {'schema':'pocket4-current-baseline-scope-controls-v1','all_passed':True,'count':21,\n            'cases':rows,'production_contract_sha256':hashlib.sha256(raw).hexdigest(),\n            'production_adapter_sha256':hashlib.sha256(adapter_raw).hexdigest(),'host_recorder_manifest_sha256':host_sha,\n            'main_epoch_sha256':qa.MAIN_EPOCH,'main_baseline_schema':qa.MAIN_BASELINE_SCHEMA,\n            'main_baseline_sha256':qa.MAIN_BASELINE_SHA,\n            'main_baseline_qualification_sha256':qa.MAIN_BASELINE_QUALIFICATION_SHA,\n            'Android_commands':0,'UI_actions':0,'helper_installed_uid':None}\nif __name__=='__main__':print(json.dumps(run_controls(),sort_keys=True))\n"; }
  function helperFork(app,parent,b) {
    const spec=specs[app];need(spec,"CLOSED_HELPER_SET_REQUIRED");
    const old=parent.files,m=checkOld(parent.manifest_raw,old,spec.manifest);
    need(Object.keys(old).sort().join("|")===Object.keys(m.files).sort().join("|"),"COMPLETE_PARENT_HELPER_BUNDLE_REQUIRED");
    const oldPkg="org.droidloom.qa."+app+".r"+spec.old,newPkg="org.droidloom.qa."+app+".r"+spec.next;
    const oldProto="pocket4-owned-"+app+"-qa-v"+spec.old,newProto="pocket4-owned-"+app+"-qa-v"+spec.next;
    const oldPath=oldPkg.replaceAll(".","/"),newPath=newPkg.replaceAll(".","/");
    const uid=b.uids[spec.target];
    need(Number.isSafeInteger(uid),"ACTUAL_TARGET_UID_PENDING");
    const files={},proof={};
    const mappings=[[oldPkg,newPkg],[oldPath,newPath],[oldProto,newProto],
      ["owned-"+app+"-qa-r"+spec.old,"owned-"+app+"-qa-r"+spec.next]];
    for(const[name,original]of Object.entries(old)) {
      if(name==="README.md")continue;
      if(name.endsWith(".json")){files[name]=original;proof[name]={historical_reference_unchanged:true};continue;}
      const e=editor(original,name);
      for(const[a,z]of mappings)e.all(a,z);
      if(name.endsWith("ActionRunner.java")) {
        e.one('    static final String MAIN_EPOCH = "'+oldEpoch+'";',
          '    static final String MAIN_EPOCH = "'+b.epoch+'";\n'+
          '    static final String MAIN_BASELINE_SCHEMA = "'+schema+'";\n'+
          '    static final String MAIN_BASELINE_SHA = "'+b.baseline.sha256+'";\n'+
          '    static final String MAIN_BASELINE_QUALIFICATION_SHA = "'+b.qualification.sha256+'";');
        const oldUid=/    static final int TARGET_UID = ([0-9]+);/.exec(e.text);
        need(oldUid,"EXACT_JAVA_TARGET_UID_SITE");
        if(Number(oldUid[1])!==uid)e.one(oldUid[0],'    static final int TARGET_UID = '+uid+';');
        e.one('keys(scope, "package", "uid", "user", "display", "activity", "window_token", "main_epoch_sha256");',
          'keys(scope, "package", "uid", "user", "display", "activity", "window_token", "main_epoch_sha256", "main_baseline_schema", "main_baseline_sha256", "main_baseline_qualification_sha256");');
        const epochGuard='        need(MAIN_EPOCH.equals(string(scope, "main_epoch_sha256", 64)), "HOST_EPOCH_ATTESTATION_REQUIRED");';
        e.one(epochGuard,epochGuard+'\n'+
          '        need(MAIN_BASELINE_SCHEMA.equals(string(scope, "main_baseline_schema", 64))\n'+
          '            && MAIN_BASELINE_SHA.equals(string(scope, "main_baseline_sha256", 64))\n'+
          '            && MAIN_BASELINE_QUALIFICATION_SHA.equals(string(scope, "main_baseline_qualification_sha256", 64)),\n'+
          '            "HOST_CURRENT_BASELINE_ATTESTATION_REQUIRED");');
      }
      if(name==="qa_contract.py") {
        e.one("MAIN_EPOCH = '"+oldEpoch+"'","MAIN_EPOCH = '"+b.epoch+"'\n"+
          "MAIN_BASELINE_SCHEMA = '"+schema+"'\nMAIN_BASELINE_SHA = '"+b.baseline.sha256+
          "'\nMAIN_BASELINE_QUALIFICATION_SHA = '"+b.qualification.sha256+"'");
        const oldUid=/^UID = ([0-9]+)$/m.exec(e.text);need(oldUid,"EXACT_PYTHON_TARGET_UID_SITE");
        if(Number(oldUid[1])!==uid)e.one(oldUid[0],"UID = "+uid);
        e.one("'window_token', 'main_epoch_sha256'}","'window_token', 'main_epoch_sha256', 'main_baseline_schema', 'main_baseline_sha256', 'main_baseline_qualification_sha256'}");
        e.one("value['display'] == 0 and value['main_epoch_sha256'] == MAIN_EPOCH,",
          "value['display'] == 0 and value['main_epoch_sha256'] == MAIN_EPOCH and\n"+
          "            value['main_baseline_schema'] == MAIN_BASELINE_SCHEMA and\n"+
          "            value['main_baseline_sha256'] == MAIN_BASELINE_SHA and\n"+
          "            value['main_baseline_qualification_sha256'] == MAIN_BASELINE_QUALIFICATION_SHA,");
      }
      if(["build_candidate.py","stage_build.py","make_build_request.py"].includes(name)){
        const previous=app==="bestbuy"?"02":"01",next=app==="bestbuy"?"03":"02";
        e.all("/home/alex/work/pocket4-owned-"+app+"-qa-r"+spec.next+"-source-"+previous,
              "/home/alex/work/pocket4-owned-"+app+"-qa-r"+spec.next+"-source-"+next);
        e.all("/home/alex/work/pocket4-owned-"+app+"-qa-r"+spec.next+"-build-"+previous,
              "/home/alex/work/pocket4-owned-"+app+"-qa-r"+spec.next+"-build-"+next);
      }
      if(name==="qa_adapter.py"){
        e.one("RECORDER_MANIFEST_SHA = '"+oldHostManifest+"'",
              "RECORDER_MANIFEST_SHA = '"+b.host_manifest.sha256+"'");
        const originalGate="        require(flow.contract.sha256 == RECORDER_MANIFEST_SHA and not flow._private_backend_transport,\n"+
                           "                'FROZEN_PUBLIC_RECORDER_TRANSPORT_REQUIRED')";
        e.one(originalGate,originalGate+"\n"+
          "        require(flow.scope.get('schema') == 'pocket4-current-recorder-scope-v1' and\n"+
          "                flow.scope.get('current_baseline_schema') == qa.MAIN_BASELINE_SCHEMA and\n"+
          "                flow.scope.get('epoch_sha256') == qa.MAIN_EPOCH and\n"+
          "                flow.scope.get('current_baseline_sha256') == qa.MAIN_BASELINE_SHA and\n"+
          "                flow.scope.get('current_baseline_qualification_sha256') == qa.MAIN_BASELINE_QUALIFICATION_SHA and\n"+
          "                flow.scope.get('package') == qa.PACKAGE and type(flow.scope.get('uid')) is int and\n"+
          "                flow.scope['uid'] == qa.UID,\n"+
          "                'TYPED_CURRENT_HOST_SCOPE_AND_HELPER_BINDING_REQUIRED')");
      }
      if(name==="qa_adapter.py")e.one("'main_epoch_sha256':self.qa.MAIN_EPOCH})",
        "'main_epoch_sha256':self.qa.MAIN_EPOCH, 'main_baseline_schema':self.qa.MAIN_BASELINE_SCHEMA,\n"+
        "            'main_baseline_sha256':self.qa.MAIN_BASELINE_SHA,\n"+
        "            'main_baseline_qualification_sha256':self.qa.MAIN_BASELINE_QUALIFICATION_SHA})");
      if(name==="check_idle_contract.py"||name==="controls/check_deep_tree.py") {
        const target=/'main_epoch_sha256':\s*qa\.MAIN_EPOCH/.exec(e.text);
        need(target,"PARENT_CONTROL_CURRENT_SCOPE_FIXTURE_REQUIRED");
        e.one(target[0],target[0]+", 'main_baseline_schema':qa.MAIN_BASELINE_SCHEMA,\n"+
          "                      'main_baseline_sha256':qa.MAIN_BASELINE_SHA,\n"+
          "                      'main_baseline_qualification_sha256':qa.MAIN_BASELINE_QUALIFICATION_SHA");
      }
      if(name==="build_candidate.py") {
        const hook="        source_java = HERE/'src/"+newPath+"/ActionRunner.java'";
        const addition=[
          "        baseline_scope={'__file__':str(HERE/'check_current_baseline.py'),'__name__':'owned_current_baseline_scope_controls'}",
          "        exec(compile((HERE/'check_current_baseline.py').read_bytes(),str(HERE/'check_current_baseline.py'),'exec'),baseline_scope)",
          "        baseline_controls=baseline_scope['run_controls']()",
          "        require(baseline_controls['all_passed'] is True and baseline_controls['count']==21 and",
          "                len(baseline_controls['cases'])==21 and all(x['passed'] is True for x in baseline_controls['cases']) and",
          "                baseline_controls['production_contract_sha256']==source['qa_contract.py']['sha256'] and",
          "                baseline_controls['production_adapter_sha256']==source['qa_adapter.py']['sha256'] and",
          "                baseline_controls['host_recorder_manifest_sha256']=='"+b.host_manifest.sha256+"' and",
          "                baseline_controls['main_epoch_sha256']=='"+b.epoch+"' and",
          "                baseline_controls['main_baseline_schema']=='"+schema+"' and",
          "                baseline_controls['main_baseline_sha256']=='"+b.baseline.sha256+"' and",
          "                baseline_controls['main_baseline_qualification_sha256']=='"+b.qualification.sha256+"',",
          "                'ACTUAL_CURRENT_BASELINE_SCOPE_CONTROLS_REQUIRED')",
          "        result['current_baseline_scope_controls']={'source_sha256':source['check_current_baseline.py']['sha256'],'report':baseline_controls}",""].join("\n");
        e.one(hook,addition+hook);
      }
      if(name==="make_build_request.py") {
        const key=/^KEY='[^'\r\n]+'$/m.exec(e.text);need(key,"EXACT_BUILD_KEY_SITE");
        e.one(key[0],"KEY='pocket4-owned-"+app+"-qa-r"+spec.next+"-current-"+b.baseline.sha256.slice(0,16)+"-host-"+b.host_manifest.sha256.slice(0,12)+"-build"+(app==="bestbuy"?"03":"02")+"'");
      }
      const newName=name.split(oldPath).join(newPath);
      e.inverse();files[newName]=e.text;
      proof[newName]={parent_path:name,parent:pin(original),generated:pin(e.text),inverse_byte_exact:true,
        edits:e.edits.map(x=>({old:x.old,next:x.next,count:x.count}))};
    }
    files["check_current_baseline.py"]=helperScopeControlSource();
    const binding={schema:"pocket4-current-baseline-helper-source-binding-v1",state:"STATIC_SOURCE_ONLY_ANDROID_UNRUN",
      app,target_package:spec.target,target_uid:uid,helper_package:newPkg,protocol:newProto,
      current_baseline_schema:schema,current_epoch_sha256:b.epoch,current_baseline:b.baseline,
      current_qualification:b.qualification,actual_baseline_result:b.result,host_recorder_source_manifest:b.host_manifest,
      parent_source_manifest_sha256:spec.manifest,owned_helper_uid:null,APK_sha256:null,signer_sha256:null,
      helper_built:false,helper_installed:false,UI_actions:0,unresolved_framework_exit_cause:true,
      whole_app_production_ready:false};
    files["current-baseline-binding.json"]=JSON.stringify(binding,null,2)+"\n";
    files["README.md"]="# "+app+" current-baseline helper source\n\n"+
      "Generated only from a complete pinned current-baseline result. The parent source manifest is "+
      spec.manifest+". All original action, full-tree, window, refresh, once-only, idle and restore logic is retained "+
      "outside the explicit scope binding additions. Parent historical JSON references retain their original bytes.\n\n"+
      "New package "+newPkg+"; protocol "+newProto+". Target UID "+uid+" was read in the new baseline. "+
      "The new helper UID, signed APK bytes and signer remain unknown until actual build/install. "+
      "This source does not authorize UI or installation and does not resolve the framework exit cause.\n";
    const sourceManifest={schema:1,artifact:"pocket4-current-baseline-helper-source-v1",current_baseline_binding:binding,
      files:Object.fromEntries(Object.entries(files).sort().map(([n,s])=>[n,pin(s)]))};
    files["SOURCE_PINS.json"]=JSON.stringify(sourceManifest,null,2)+"\n";
    return {files,binding,proof,manifest_sha256:digest(files["SOURCE_PINS.json"])};
  }
  function makeBuildRequest(app,helper,binding) {
    const files=helper.files;
    const rawManifest=files["SOURCE_PINS.json"];
    need(digest(rawManifest)===helper.manifest_sha256,"GENERATED_HELPER_MANIFEST_CHANGED");
    const manifest=JSON.parse(rawManifest);
    for(const[name,p]of Object.entries(manifest.files))
      need(size(files[name])===p.bytes&&digest(files[name])===p.sha256,"GENERATED_HELPER_SOURCE_CHANGED");
    const packet={schema:1,stage_source:files["stage_build.py"],source_manifest_sha256:helper.manifest_sha256,files};
    const wire=JSON.stringify(packet,null,2)+"\n";
    need(size(wire)<=524288,"STATIC_BUILD_PACKET_BOUND");
    const wrapper="import sys,json,hashlib;raw=sys.stdin.buffer.read(524289);"+
      "assert len(raw)<=524288 and hashlib.sha256(raw).hexdigest()=="+JSON.stringify(digest(wire))+";"+
      "packet=json.loads(raw);source=packet['stage_source'];"+
      "assert hashlib.sha256(source.encode()).hexdigest()=="+JSON.stringify(digest(files["stage_build.py"]))+";"+
      "scope={'__name__':'__main__','__file__':'<verified-owned-"+app+"-qa-build-stage>','PACKET':packet};"+
      "exec(compile(source,'stage_build.py','exec'),scope,scope)";
    return {host:"pocket4",executable:"/usr/bin/python3",args:["-I","-c",wrapper],
      cwd:"/home/alex/work",env:{PYTHONDONTWRITEBYTECODE:"1"},stdin:wire,
      idempotency_key:"pocket4-owned-"+app+"-qa-r"+specs[app].next+"-current-"+binding.baseline.sha256.slice(0,16)+"-host-"+binding.host_manifest.sha256.slice(0,12)+"-build"+(app==="bestbuy"?"03":"02"),
      timeout_seconds:300,cpu_quota_percent:100,memory_max_bytes:536870912,nice:10};
  }
  function compileHelpersActual(actual,parents,host) {
    const binding=actualBinding(actual);
    need(host&&Object.keys(host).sort().join(",")==="manifest_pin,manifest_raw","EXACT_CURRENT_HOST_SOURCE_INPUT");
    const hm=exactPin(host.manifest_raw,host.manifest_pin);
    need(host.manifest_pin.sha256==="6d99374e1580083fd0f30b7f9b3c520306680760c97ad0d5400798fda427fb6e"&&
      hm.schema===2&&hm.artifact==="pocket4-bilibili-current-recorder-held-r5"&&hm.revision===5&&
      hm.parent_R4_manifest_sha256===oldHostManifest&&
      hm.current_baseline.schema===schema&&hm.current_baseline.epoch_sha256===binding.epoch&&
      hm.current_baseline.baseline_sha256===binding.baseline.sha256&&
      hm.current_baseline.qualification_sha256===binding.qualification.sha256&&
      hm.current_baseline.guard_sha256===binding.guard.sha256&&
      hm.files["current_baseline_guard.py"].sha256===binding.guard.sha256&&Object.keys(hm.files).length===14&&
      hm.source_fork_is_not_deployment===true&&hm.old_flows_reauthorized===false&&hm.whole_app_production_ready===false,
      "EXACT_CURRENT_HOST_AND_BASELINE_CLOSURE_REQUIRED");
    binding.host_manifest=host.manifest_pin;
    need(parents&&Object.keys(parents).sort().join(",")==="amazon,bestbuy,bili,ihg","EXACT_FOUR_PARENT_HELPERS");
    const helpers={};
    for(const app of Object.keys(specs)){
      helpers[app]=helperFork(app,parents[app],binding);
      helpers[app].build_request=makeBuildRequest(app,helpers[app],binding);
    }
    return {schema:"pocket4-current-baseline-helper-source-fork-bundle-v1",state:"SOURCE_FORK_ONLY_RUNTIME_NOT_ADMITTED",
      actual_binding:{...binding,guard_raw:undefined},helpers,
      APK_builds_executed:0,helper_installs_executed:0,UI_actions:0,
      all45_app_production_ready_count:0,unresolved_framework_exit_cause:true};
  }
  return {compileHelpersActual};
}
