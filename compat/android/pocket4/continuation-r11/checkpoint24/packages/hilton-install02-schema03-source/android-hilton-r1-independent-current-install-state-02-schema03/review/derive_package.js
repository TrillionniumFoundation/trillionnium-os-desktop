function deriveHelperArtifactSchema03(utilitySource,contextDeriverSource,artifactControlsFragment,label,originalRequestRaw) {
 const H=Function(utilitySource+"\nreturn {utf8,sha256,gitBlob};")(),need=(v,m)=>{if(!v)throw Error(m);};
 const pins={hilton:"1aad171f6d1106e0e156eef84a3068777a190158",united:"f645ae749a2d8460499bb6c29f04dab6e68b4109",ticket12306:"fc0ab355d59f946309e5b501a8917033bf408aee"};
 const pin=s=>({bytes:H.utf8(s).length,sha256:H.sha256(H.utf8(s))});
 const sorted=v=>Array.isArray(v)?v.map(sorted):v&&typeof v==="object"?Object.fromEntries(Object.keys(v).sort().map(k=>[k,sorted(v[k])])):v;
 const eq=(a,b)=>JSON.stringify(sorted(a))===JSON.stringify(sorted(b));
 const change=(s,a,b,n=1)=>{need(s.split(a).length-1===n,"EXACT_EDIT_COUNT:"+a);return s.split(a).join(b);};
 need(H.gitBlob(H.utf8(utilitySource))==="443e39b58cd6fe72faa1cb1d1c7b0a813fa0032d","UTILITY_PIN");
 need(H.gitBlob(H.utf8(originalRequestRaw))===pins[label],"FIXED_ORIGINAL_REQUEST");
 need(H.gitBlob(H.utf8(contextDeriverSource))==="94983135e4d482faad9142645ec359b5638d0d26","CONTEXT_DERIVER_PIN");
 need(H.gitBlob(H.utf8(artifactControlsFragment))==="6c609448f7d361c23bc0a4eb9cdd367743b814d0","TEN_CONTROLS_PIN");
 const deriveContext=Function(contextDeriverSource+"\nreturn deriveArtifactReference03;")();
 const original=JSON.parse(originalRequestRaw),packet=JSON.parse(original.stdin),oldFiles={...packet.files},
       manifest=JSON.parse(packet.files["SOURCE_PINS.json"]);
 need(original.stdin===JSON.stringify(sorted(packet))+"\n"&&Object.keys(manifest.files).length===15&&Object.keys(oldFiles).length===16,"ORIGINAL_EXACT_PACKET");
 need(pin(packet.files["SOURCE_PINS.json"]).sha256===packet.source_manifest_sha256,"ORIGINAL_MANIFEST");
 for(const [name,p]of Object.entries(manifest.files))need(eq(pin(oldFiles[name]),p),"ORIGINAL_MEMBER:"+name);
 const contextName=label+"_context.py";
 packet.files[contextName]=deriveContext(oldFiles[contextName],label);
 const oldControls=oldFiles["check_install_binding.py"];
 let controls=change(oldControls,"CONTROL_COUNT = 75","CONTROL_COUNT = 85");
 const tail="    entry.require(len(rows) == 7,'EXACT_SEVEN_INDEPENDENT_TARGET_CONTROLS')\n    return rows";
 const newTail="    entry.require(len(rows) == 7,'EXACT_SEVEN_INDEPENDENT_TARGET_CONTROLS')\n"+
  "    rows.extend(run_artifact_reference_controls(entry,context,files,artifact,open_fixture))\n    return rows";
 controls=change(controls,tail,newTail);
 const marker="            'independent_target_authority_and_held_route_controls':7,";
 const addition=marker+"\n"+
  "            'actual_artifact_reference_schema_controls':10,\n"+
  "            'artifact_route_hash_is_explicit_memory_seam':True,\n"+
  "            'original_stream_hash_method_uses_small_synthetic_bytes':True,";
 controls=change(controls,marker,addition)+artifactControlsFragment;
 const inverse=change(change(change(controls.slice(0,-artifactControlsFragment.length),addition,marker),
                         newTail,tail),"CONTROL_COUNT = 85","CONTROL_COUNT = 75");
 need(inverse===oldControls,"ORIGINAL_75_CONTROLS_BODY_INVERSE");
 packet.files["check_install_binding.py"]=controls;
 packet.files["stage_execute.py"]=change(change(oldFiles["stage_execute.py"],
   "controls['count']==75","controls['count']==85"),"len(controls['cases'])==75","len(controls['cases'])==85");
 packet.files["INPUTS.json"]=change(oldFiles["INPUTS.json"],'"source_qualification_controls": 75','"source_qualification_controls": 85');
 packet.files["README.md"]=change(oldFiles["README.md"],"The stage runs 75 controls:","The stage runs 85 controls: the original 75 below remain, followed by ten actual artifact-reference controls.");
 packet.files["README.md"]+="\nSchema03 uses the immutable artifact reference's top-level package/UID/user/version and current_artifacts rows. The ten added controls extend real open_context and its held record through ArtifactSet, use the original target metadata parsers, exercise before/after/held/named/close routing with an explicit hash return-value seam, and separately exercise the original streaming hash method on small synthetic bytes. These tests do not qualify actual APK contents, descriptors, Android execution or installation. The original 13-command plan, streaming/time limits and all Main/R6/FD/lock guards remain.\n";
 const oldKey=original.idempotency_key,oldRoot=oldFiles["make_request.py"].match(/^ROOT = '([^']+)'$/m)?.[1];
 need(oldRoot&&oldFiles["install_state.py"].includes("ROOT = Path('"+oldRoot+"')"),"EXACT_ORIGINAL_ROOT");
 const isHilton=label==="hilton",root=isHilton?oldRoot.replace(/-01$/,"-02"):oldRoot;
 need(!isHilton||root!==oldRoot,"FRESH_HILTON_ROOT");
 let newKey="pocket4-owned-"+label+"-qa-r1-current-r6-install-state-"+(label==="united"?"01":"02")+"-schema03-"+pin(packet.files[contextName]+controls).sha256.slice(0,16);
 packet.files["make_request.py"]=change(oldFiles["make_request.py"],"KEY = '"+oldKey+"'","KEY = '"+newKey+"'");
 if(isHilton){
  for(const name of["install_state.py","stage_execute.py","make_request.py"]){
   packet.files[name]=change(packet.files[name],oldRoot,root);
   packet.files[name]=change(packet.files[name],"\nNONCE = '"+packet.nonce+"'\n","\nNONCE = None\n");
  }
  const oldInputs=JSON.parse(oldFiles["INPUTS.json"]);
  packet.files["install_state.py"]=change(packet.files["install_state.py"],"\nSTATE_NONCE = '"+oldInputs.nonces.state+"'\n","\nSTATE_NONCE = None\n");
  packet.files["make_request.py"]=change(packet.files["make_request.py"],"KEY = '"+newKey+"'","KEY = None");
  const inputs=JSON.parse(packet.files["INPUTS.json"]);
  inputs.nonces={flow:null,state:null};inputs.actual_nonce_source=null;
  inputs.install_attempt_source_state="SOURCE_ONLY_FRESH_HILTON02_PAIR_PENDING";
  inputs.fresh_root=root;inputs.prior_failed_install={actual_tree:"f48f407da7689722180540c129d0fb86e5f8cf4c",
   worker:{bytes:6127,sha256:"93c44315465f2ab424db3a4695b199e38296ef2331ab48ba8bec4c3f02e65f22",git_blob_sha1:"601247da29f48b4e6cde076fc3499c702bdce036"},
   phase:"held_Main_binding",error_type:"KeyError",error_message:"'target'",Android_commands:0,old_pair_retired:true};
  packet.files["INPUTS.json"]=JSON.stringify(inputs,null,2)+"\n";
  packet.files["README.md"]+="\nHilton root01 failed at the former ArtifactSet schema read before any Android command. Its pair remains retired. This root02 package is a source-only template with None/null flow/state/key; it must be bound only to a newly qualified two-value nonce receipt before a request is generated.\n";
  packet.nonce=null;newKey=null;
 }
 const changed=Object.keys(oldFiles).filter(n=>n!=="SOURCE_PINS.json"&&packet.files[n]!==oldFiles[n]);
 for(const n of changed)manifest.files[n]=pin(packet.files[n]);
 packet.files["SOURCE_PINS.json"]=JSON.stringify(manifest,null,2)+"\n";
 packet.source_manifest_sha256=pin(packet.files["SOURCE_PINS.json"]).sha256;
 const unchanged=["actual-target-metadata.json","target-artifact-reference.json",label+"_transport.py",
  "references/target_metadata_parsers.py","current_discovery.py","check_current_discovery.py","host-stage-actual.json","host/source-manifest.json"];
 if(!isHilton)unchanged.push("install_state.py");
 for(const name of unchanged)need(oldFiles[name]===packet.files[name],"IMMUTABLE_SOURCE:"+name);
 need(packet.files[contextName].slice(0,packet.files[contextName].indexOf("class ArtifactSet:"))===oldFiles[contextName].slice(0,oldFiles[contextName].indexOf("class ArtifactSet:")),"ALL_CONTEXT_BEFORE_ARTIFACTSET_UNCHANGED");
 const payload=JSON.stringify(sorted(packet))+"\n";need(H.utf8(payload).length<=262144,"ORIGINAL_PACKET_BOUND");
 for(const [name,text]of Object.entries(packet.files))need(H.utf8(text).length<=65536,"ORIGINAL_LEAF_BOUND:"+name);
 let requestRaw=null;
 if(!isHilton){
  const wrapper="import hashlib,json,sys\nraw=sys.stdin.buffer.read(262145)\n"+
   "assert hashlib.sha256(raw).hexdigest()=='"+pin(payload).sha256+"'\n"+
   "p=json.loads(raw);src=p['files']['stage_execute.py'].encode('utf-8')\n"+
   "assert hashlib.sha256(src).hexdigest()=='"+manifest.files["stage_execute.py"].sha256+"'\n"+
   "scope={'__name__':'owned_qa_stage','__file__':'"+root+"/source/stage_execute.py'}\n"+
   "exec(compile(src,scope['__file__'],'exec'),scope)\nraise SystemExit(scope['main'](raw))\n";
  need(original.args.length===6&&eq(original.args.slice(0,5),["-n","/usr/bin/python3","-I","-B","-c"]),"ORIGINAL_WRAPPER");
  requestRaw=JSON.stringify(sorted({...original,args:[...original.args.slice(0,5),wrapper],stdin:payload,idempotency_key:newKey}),null,2)+"\n";
 }
 const proof={schema:1,label,status:isHilton?"SOURCE_ONLY_ACTUAL_NONCE_BINDING_PENDING":"EXACT_REQUEST_UNRUN",
  original_request:{...pin(originalRequestRaw),git_blob_sha1:pins[label]},root,old_key:oldKey,new_key:newKey,
  unused_pair_retained:!isHilton,old_hilton_pair_retired:isHilton,nonce_generated_here:false,
  production_changes:["ArtifactSet constructor and top-level identity/current_artifacts access"],
  controls:{original_75_body_inverse_exact:true,added:10,total:85,Python_executed:false,
    actual_installed_APK_contents_qualified:false,real_stream_hash_small_memory_fixture:true,
    route_hash_boundary_explicit:true},
  unchanged_members:unchanged,changed_members:changed,ordered_worker_Android_commands:13,
  Main_R6_B_Q_FD_lock_and_streaming_guards_unchanged:true,
  source_manifest:pin(packet.files["SOURCE_PINS.json"]),packet:pin(payload),
  request:requestRaw?pin(requestRaw):null,helper_uid:null,install_assumed_success:false,dispatch:false};
 return {sources:packet.files,packetRaw:payload,requestRaw,proofRaw:JSON.stringify(proof,null,2)+"\n",oldFiles};
}
