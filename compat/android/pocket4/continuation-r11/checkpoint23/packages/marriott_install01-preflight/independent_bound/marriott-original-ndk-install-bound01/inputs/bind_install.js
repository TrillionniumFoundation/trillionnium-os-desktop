// Source-only actual binder. No network, filesystem, process, Main or Android IO.
// Pass the two complete future actual originals plus their advertised whole pins
// and the independently known job_id. Missing/failed originals produce no request.
// utilitySource is immutable Git blob 443e39b58cd6fe72faa1cb1d1c7b0a813fa0032d.
const EXPECTED = {
  "base_packet": {
    "bytes": 232975,
    "sha256": "05d80d6473fd35bc172aab79a0eaa4c96afe038bc8187c7baf2399637529dcb7"
  },
  "wrapper_template": {
    "bytes": 4710,
    "sha256": "2edb2be25dbe6db762634c2b926022348a6940210f264d8fda8ed67dd06a65c7"
  },
  "source_manifest": {
    "bytes": 1054,
    "sha256": "50dce3c5572a40562c1928264219173a61d92fb9f39a96be9feb956695ba8c2e"
  },
  "controls": {
    "check_external_manifest.py": {
      "bytes": 4681,
      "sha256": "1bd278bd296084e46dd43b6dfc45420b85568a02c05e3823b11704fa14bd9e06"
    },
    "check_fixture.py": {
      "bytes": 17942,
      "sha256": "cd367e402119d2f353acfd66e1e5431a149f6e38b5d6a28a630995c8dc795852"
    },
    "check_install_lease.py": {
      "bytes": 15887,
      "sha256": "76cc5152605ab09abfb69b274cca003c4d36ed9ba5e3a40d222448ebf586a1b0"
    }
  },
  "cases": {
    "fixture": [
      "three_separate_fixed_fixture_scopes",
      "scope_rejects_commercial_package",
      "scope_rejects_old_epoch",
      "scope_rejects_old_baseline",
      "scope_rejects_inherited_scope",
      "scope_rejects_automatic_retry",
      "install_rejects_adopted_old_UID",
      "actual_instrumentation_supplies_complete23_and_exact12_filter",
      "empty_VerifyTestList_cannot_be_admitted",
      "actual_phase_plans_keep_install_run_retirement_separate",
      "run_scope_cannot_invoke_retirement_plan",
      "install_must_start_from_all_user_absence",
      "package_parser_uses_new_UID_and_rejects_protected_UID",
      "numeric_process_parser_projects_only_fixed_UID",
      "actual_instrumentation_parser_requires_one_original_testMain",
      "failed_instrumentation_status_cannot_pass",
      "actual_XML_parser_requires_exact12_without_runtime_inference",
      "XML_rejects_failures",
      "XML_rejects_disabled",
      "XML_rejects_skipped",
      "XML_rejects_errors",
      "XML_rejects_duplicate_test_body",
      "XML_rejects_missing_test_body",
      "XML_rejects_unexecuted_test_body",
      "XML_entity_definitions_are_rejected",
      "source_only_install_stops_before_any_IO",
      "source_only_run_stops_before_any_IO",
      "source_only_retire_stops_before_any_IO",
      "source_only_context_stops_before_any_IO",
      "source_only_source_loader_stops_before_any_IO",
      "real_install_constructor_separates_tuple_from_scope_authority",
      "install_constructor_rejects_equal_but_old_Main_pair",
      "install_constructor_rejects_wrong_source_manifest",
      "install_constructor_rejects_unreleased_held_binding",
      "install_constructor_rejects_incomplete_staging_cleanup",
      "install_constructor_rejects_wrong_built_APK",
      "install_constructor_rejects_scope_fields_in_exact_tuple",
      "install_constructor_rejects_wrong_observed_UID"
    ],
    "manifest": [
      "unbound_source_root_stops_before_read",
      "external_pin_qualifies_own_phase_and_is_copied",
      "self_embedded_manifest_authority_is_rejected",
      "wrong_external_manifest_hash_is_rejected"
    ],
    "lease": [
      "install_worker_unbound_stops_before_OS_or_Main",
      "real_lease_claims_three_locks_and_exact_seven_sources",
      "same_lease_cannot_enter_install_twice",
      "install_lease_cannot_authorize_retirement_scope",
      "install_lease_rejects_changed_external_manifest",
      "real_renamed_shared_ancestor_is_rejected_before_command",
      "real_lock_contention_and_failed_acquire_FD_remain_accounted",
      "unlock_failure_stays_failed_and_all_owned_FDs_close"
    ]
  },
  "root": "/home/alex/work/pocket4-original-ndk-fixture-APK03-install-01",
  "install_nonce": "e4b5a1bdac8be04ff2ea3188a6d946d6",
  "source_tree": "6b603c7628c9f8337dcb7201e99bbdc28ef60305",
  "controls_tree": "ef693568e1dea410d33f78cc6fa271b2e2ceebf8",
  "controls_request": {
    "bytes": 254147,
    "sha256": "2e03b049bbfedd03c2ac64e5f2a553d74e4451be0c6b220582e9c91c8567cfb2"
  }
};

function bindOriginalNdkInstall(utilitySource,basePacketRaw,wrapperTemplateRaw,actual){
  function need(v,m){if(!v)throw Error(m);}
  need(actual!==null&&typeof actual==="object","ACTUAL_FIFTY_CONTROLS_UNBOUND");
  const U=Function(utilitySource+"\nreturn {utf8,sha1,sha256,gitBlob};")();
  need(U.gitBlob(U.utf8(utilitySource))==="443e39b58cd6fe72faa1cb1d1c7b0a813fa0032d","UTILITY_GIT_BLOB");
  function sorted(v){
    if(Array.isArray(v))return v.map(sorted);
    if(v!==null&&typeof v==="object")return Object.fromEntries(Object.keys(v).sort().map(k=>[k,sorted(v[k])]));
    return v;
  }
  const equal=(a,b)=>JSON.stringify(sorted(a))===JSON.stringify(sorted(b));
  function exactKeys(v,names){return v!==null&&typeof v==="object"&&!Array.isArray(v)&&equal(Object.keys(v).sort(),[...names].sort());}
  function rawPin(raw){
    need(typeof raw==="string","EXACT_RAW_UTF8_REQUIRED");
    const b=U.utf8(raw);
    return{bytes:b.length,sha256:U.sha256(b)};
  }
  function whole(raw,p,maximum){
    need(exactKeys(p,["bytes","sha256"])&&Number.isSafeInteger(p.bytes)&&p.bytes>0&&p.bytes<=maximum&&
      /^[0-9a-f]{64}$/.test(p.sha256)&&equal(rawPin(raw),p),"ACTUAL_WHOLE_INPUT_PIN");
    return JSON.parse(raw);
  }
  function encoded(bytes){
    need(bytes instanceof Uint8Array,"BASE64_REQUIRES_UTF8_BYTES");
    const alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let value="";
    for(let i=0;i<bytes.length;i+=3){
      const count=Math.min(3,bytes.length-i),n=(bytes[i]<<16)|((count>1?bytes[i+1]:0)<<8)|(count>2?bytes[i+2]:0);
      value+=alphabet[(n>>>18)&63]+alphabet[(n>>>12)&63]+(count>1?alphabet[(n>>>6)&63]:"=")+(count>2?alphabet[n&63]:"=");
    }
    return value;
  }
  function decoded(text){
    need(/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(text),"BASE64_GRAMMAR");
    const alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    const size=text.length/4*3-(text.endsWith("==")?2:text.endsWith("=")?1:0),result=new Uint8Array(size);
    let at=0;
    for(let i=0;i<text.length;i+=4){
      const n=(alphabet.indexOf(text[i])<<18)|(alphabet.indexOf(text[i+1])<<12)|
        ((text[i+2]==="="?0:alphabet.indexOf(text[i+2]))<<6)|(text[i+3]==="="?0:alphabet.indexOf(text[i+3]));
      if(at<size)result[at++]=(n>>>16)&255;if(at<size)result[at++]=(n>>>8)&255;if(at<size)result[at++]=n&255;
    }
    return result;
  }
  function member(raw){return{body:raw,...rawPin(raw)};}
  const base=whole(basePacketRaw,EXPECTED.base_packet,524288);
  need(equal(rawPin(wrapperTemplateRaw),EXPECTED.wrapper_template),"EXACT_UNBOUND_WRAPPER_TEMPLATE");
  need(exactKeys(base,["schema","sources","manifest","references"])&&base.schema===1,"EXACT_BASE_PACKET");
  const manifest=whole(base.manifest.body,EXPECTED.source_manifest,65536);
  need(exactKeys(manifest,["schema","files"])&&manifest.schema==="pocket4-original-ndk-fixture-source-v1","MANIFEST_SCHEMA");
  need(equal(Object.keys(manifest.files).sort(),Object.keys(base.sources).sort()),"SEVEN_SOURCE_SET");
  for(const [name,v] of Object.entries(base.sources)){
    need(exactKeys(v,["body","bytes","sha256"])&&equal(rawPin(v.body),manifest.files[name])&&
      equal(rawPin(v.body),{bytes:v.bytes,sha256:v.sha256}),"SOURCE_MEMBER_"+name);
  }
  need(exactKeys(actual,["stdout_raw","stdout_pin","terminal_raw","terminal_pin","job_id"])&&
    typeof actual.job_id==="string"&&/^[0-9a-f]+-[0-9a-f]{4}-[0-9a-f]{4}$/.test(actual.job_id),"EXACT_FUTURE_ACTUAL_INPUTS");
  const entry=whole(actual.stdout_raw,actual.stdout_pin,262144);
  const terminal=whole(actual.terminal_raw,actual.terminal_pin,32768);
  need(terminal.job_id===actual.job_id&&terminal.state==="succeeded"&&terminal.exit_code===0&&
    terminal.output_complete===true&&terminal.output_durable===true&&terminal.terminal_publication_confirmed===true&&
    terminal.timed_out===false&&terminal.cancelled===false&&terminal.automatic_retry===false&&
    equal(terminal.log_bytes,{stdout:{seen:actual.stdout_pin.bytes,stored:actual.stdout_pin.bytes},stderr:{seen:0,stored:0}})&&
    ["stdout","stderr"].every(k=>terminal.log_synced[k]===true&&terminal.log_truncated[k]===false&&terminal.log_errors[k]===null),
    "COMPLETE_INDEPENDENT_FIFTY_CONTROL_TERMINAL");
  need(entry.schema===1&&entry.kind==="pocket4-original-ndk-install-entry-controls01"&&entry.ok===true&&
    equal(entry.errors,[])&&equal(entry.source_manifest,EXPECTED.source_manifest)&&
    equal(entry.sources,manifest.files)&&equal(entry.controls,EXPECTED.controls)&&
    equal(entry.counts,{fixture:38,manifest:4,lease:8}),"ACTUAL_FIFTY_SOURCE_AND_CONTROL_PINS");
  const allNames=[...EXPECTED.cases.fixture,...EXPECTED.cases.manifest,...EXPECTED.cases.lease];
  need(Array.isArray(entry.cases)&&entry.cases.length===50&&new Set(entry.cases.map(x=>x.name)).size===50&&
    equal(entry.cases.map(x=>x.name),allNames)&&entry.cases.every(x=>x.passed===true),"ACTUAL_EXACT_FIFTY_CASES");
  need(exactKeys(entry.groups,["fixture","manifest","lease"]),"THREE_ACTUAL_CONTROL_GROUPS");
  for(const [name,expected] of Object.entries(EXPECTED.cases)){
    const group=entry.groups[name];
    need(group.ok===true&&group.count===expected.length&&Array.isArray(group.cases)&&
      equal(group.cases.map(x=>x.name),expected)&&group.cases.every(x=>x.passed===true),"ACTUAL_GROUP_"+name);
  }
  const f=entry.groups.fixture,m=entry.groups.manifest,l=entry.groups.lease;
  need(f.runtime_qualified===false&&f.child_processes===0&&f.Main_namespace_reads===0&&f.Android_commands===0&&
    f.explicit_fixture_filesystem_reads===0&&f.explicit_fixture_filesystem_writes===0&&
    f.original_source_only_barrier_retained===true&&f.actual_APK_or_UID_bound===false,"ORIGINAL_38_BOUNDARIES");
  need(m.real_FixedSources_constructor_and_verify_called===true&&m.source_barriers_restored===true&&
    m.actual_files_read===0&&m.children===0&&m.Main_or_Android===0&&m.runtime_qualified===false,"EXTERNAL_MANIFEST_BOUNDARIES");
  need(l.all_owned_control_FDs_closed===true&&l.all_owned_control_files_removed===true&&l.seams_restored===true&&
    l.expected_unlock_failure_preserved===true&&l.synthetic_scope_only===true&&l.actual_install_nonce_consumed===false&&
    l.Main_reads===0&&l.Android_commands===0&&l.children===0&&l.runtime_qualified===false&&
    Number.isSafeInteger(l.real_own_fd_count)&&l.real_own_fd_count>0,"REAL_LEASE_FD_AND_FAILURE_BOUNDARIES");
  need(entry.all_owned_control_FDs_closed===true&&entry.all_owned_control_files_removed===true&&
    entry.Main_reads===0&&entry.Android_commands===0&&entry.children===0&&entry.namespace_entry===false&&
    entry.actual_install_nonce_consumed===false&&entry.installed_UID===null&&entry.runtime_qualified===false&&
    entry.automatic_retry===false&&entry.original_source_only_barriers_retained===true&&
    entry.standard_library_import_IO_included_in_counters===false&&entry.ambient_FD_equality_asserted===false&&
    entry.whole_invocation_resource_observed===false&&entry.signal_handler_restored===true&&entry.umask_restored===true&&
    entry.work_deadline_seconds===45&&entry.outer_timeout_seconds===60&&
    typeof entry.elapsed_seconds==="number"&&Number.isFinite(entry.elapsed_seconds)&&entry.elapsed_seconds>=0&&entry.elapsed_seconds<45,
    "ACTUAL_CONTROL_SCOPE_AND_RETIRED_OWN_STATE");
  const oldNonce=JSON.parse(base.references["install-nonce.original.json"].body);
  const globalBefore=JSON.parse(base.references["global890.original.json"].body);
  const globalAfter=JSON.parse(base.references["global891.original.json"].body);
  need(oldNonce.nonce===EXPECTED.install_nonce&&oldNonce.ok===true&&oldNonce.draw_count===1&&
    oldNonce.phase==="install"&&oldNonce.package==="com.example.ndk_tests"&&oldNonce.runtime_authorized===false&&
    globalBefore.length===890&&new Set(globalBefore).size===890&&!globalBefore.includes(EXPECTED.install_nonce)&&
    globalAfter.length===891&&new Set(globalAfter).size===891&&equal([...globalBefore,EXPECTED.install_nonce].sort(),globalAfter),
    "ONE_ACTUAL_UNCONSUMED_INSTALL_NONCE");
  const binding={schema:1,kind:"pocket4-original-ndk-install-binding-v1",root:EXPECTED.root,
    source_manifest:EXPECTED.source_manifest,entry_controls:actual.stdout_pin,
    entry_controls_terminal:actual.terminal_pin,entry_controls_job:actual.job_id,
    entry_controls_stdout_bytes:actual.stdout_pin.bytes};
  const packet=JSON.parse(basePacketRaw);
  packet.references["entry-controls.original.json"]=member(actual.stdout_raw);
  packet.references["entry-controls-terminal.original.json"]=member(actual.terminal_raw);
  const packetRaw=JSON.stringify(packet,null,2)+"\n";
  const transportRaw=JSON.stringify({binding,packet},null,2)+"\n";
  const bytes=U.utf8(transportRaw),payload=encoded(bytes),roundtrip=decoded(payload);
  need(bytes.length<=1048576&&roundtrip.length===bytes.length&&roundtrip.every((v,i)=>v===bytes[i]),"INSTALL_TRANSPORT_WHOLE_ROUNDTRIP");
  let stdin=wrapperTemplateRaw;
  for(const [key,value] of Object.entries({
    "__PACKET_BYTES__":String(bytes.length),"__PACKET_SHA256__":U.sha256(bytes),"__PACKET_B64__":payload})){
    need(stdin.split(key).length===2,"ONE_WRAPPER_SLOT_"+key);stdin=stdin.replace(key,value);
  }
  const request={args:["-n","/usr/bin/python3","-I","-B","-"],cpu_quota_percent:100,cwd:"/home/alex/work",
    executable:"/usr/bin/sudo",host:"pocket4",idempotency_key:"p4-ndk-fixture-APK03-install01-"+U.sha256(U.utf8(stdin)).slice(0,16),
    memory_max_bytes:536870912,nice:15,stdin,timeout_seconds:240};
  const proof={schema:1,kind:"pocket4-original-ndk-single-install-actual-binding-v1",
    source_tree:EXPECTED.source_tree,controls_tree:EXPECTED.controls_tree,controls_request:EXPECTED.controls_request,
    source_manifest:EXPECTED.source_manifest,actual_entry_job:actual.job_id,
    actual_entry_stdout:actual.stdout_pin,actual_entry_terminal:actual.terminal_pin,
    actual_fifty_controls_qualified:true,actual_install_nonce:EXPECTED.install_nonce,
    install_nonce_original:rawPin(base.references["install-nonce.original.json"].body),
    install_nonce_terminal:rawPin(base.references["install-nonce-terminal.original.json"].body),
    global891_original:rawPin(base.references["global891.original.json"].body),
    binding:rawPin(JSON.stringify(binding,null,2)+"\n"),packet:rawPin(packetRaw),transport:rawPin(transportRaw),
    base64_roundtrip_exact:true,reference_bodies_byte_identical:true,
    exact_seven_sources_unmodified:true,installed_UID:null,installed:false,
    instrumentation_dispatched:false,original_NdkTests_runtime_qualified:false,
    run_or_retire_request_generated:false,automatic_retry:false,
    Root_dispatch_still_required:true,worker_work_seconds:175,outer_timeout_seconds:240,
    target_sdk:23,target_sdk_bypass:false,commercial_App_readiness_qualified:false};
  return{bindingRaw:JSON.stringify(binding,null,2)+"\n",packetRaw,transportRaw,stdin,
    requestRaw:JSON.stringify(request,null,2)+"\n",proofRaw:JSON.stringify(proof,null,2)+"\n",
    entryRaw:actual.stdout_raw,terminalRaw:actual.terminal_raw};
}
