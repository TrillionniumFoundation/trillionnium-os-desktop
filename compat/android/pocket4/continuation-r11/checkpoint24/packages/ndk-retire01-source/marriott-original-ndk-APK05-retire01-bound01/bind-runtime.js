// Pure V8 actual-result binder. No device, filesystem, network or mutation.
// Every authority body remains its original string; unsafe JSON integers use BigInt.
const EXPECTED = {
  "source_manifest": {
    "bytes": 1050,
    "sha256": "7ea8d117de4a6c4cbeceebc4d5d4cf56fd7f075f3cb068b8f3610be4283df582"
  },
  "sources": {
    "current_discovery.py": {
      "bytes": 8332,
      "sha256": "9ed0069897faebba50cec3d93b08da54f1c791d6e2e775d26ec798c38b227886"
    },
    "fixture_context.py": {
      "bytes": 22014,
      "sha256": "8d544b38250c3994bea62f5b00c5a9a1f8999d951643f4fe06133861a362b9d4"
    },
    "fixture_contract.py": {
      "bytes": 25331,
      "sha256": "1b027dc076f0ee5d89df1e95ae76fddeacab1adaafb5e77e4b05b63f47593261"
    },
    "fixture_phases.py": {
      "bytes": 25716,
      "sha256": "b62970bc45d109ccde774c6bad158b9f4623e2619901a2e209d58f6469b6d845"
    },
    "fixture_transport.py": {
      "bytes": 14639,
      "sha256": "8430f9384f61ad1b59534d7cc3d2006c5aa848bc404a067680d8b20845027fe6"
    },
    "phase_lease.py": {
      "bytes": 22026,
      "sha256": "eda443631a8487502a97758e3d72b9ae1cd65b0f17298055c8fd2bbdfcf01389"
    },
    "phase_worker.py": {
      "bytes": 33969,
      "sha256": "6bc5f7d0bdca28a7275d6eeb97f4889e40b66788437af806ac5e5d6daa43d83e"
    }
  },
  "controls": {
    "check_fixture.py": {
      "bytes": 17942,
      "sha256": "cd367e402119d2f353acfd66e1e5431a149f6e38b5d6a28a630995c8dc795852"
    },
    "check_external_manifest.py": {
      "bytes": 4681,
      "sha256": "1bd278bd296084e46dd43b6dfc45420b85568a02c05e3823b11704fa14bd9e06"
    },
    "check_phase_lease.py": {
      "bytes": 18085,
      "sha256": "0e33f8435b715061f6e174d7d569894207b0feb914026efa2eebbff397d6a2ac"
    },
    "check_phase_wiring.py": {
      "bytes": 22424,
      "sha256": "c2fc807e9fa658466815134b4a9e81dff1474584776d119e426556b1f2f44b1d"
    }
  },
  "references": {
    "static-build.original.json": {
      "bytes": 4893,
      "sha256": "c59318c119e43afc810debc6dbfd7367d37f1f9c154313572f732cc645124bae"
    },
    "build-terminal.original.json": {
      "bytes": 729,
      "sha256": "7df30068ee3849645f69085f9c16f1bc1094744fbacc26d765a09be0c21ded3d"
    },
    "build-stdout.original.json": {
      "bytes": 228,
      "sha256": "7e22891b785542a355a55f67b2235180d1dd216d176871338e88ebd6a2d706f6"
    },
    "readonly38.original.json": {
      "bytes": 6407,
      "sha256": "7ff0ed239e77335b04c1b4197eab194ed108d75d2deff8673185a3ee0c7d5256"
    },
    "readonly38-terminal.original.json": {
      "bytes": 731,
      "sha256": "8f02badd8c546fb2aba3e58a2ceab3f23d99811d8c1e6e142d92d1f93b3ad804"
    },
    "install-result.original.json": {
      "bytes": 11271,
      "sha256": "e17df04e2eda0e0f489ec6fee992bcca2c5ae1fd584e9fc4e57a20334fb16143"
    },
    "install-summary.original.json": {
      "bytes": 455,
      "sha256": "8910ed011d65439e3e7d315e4b8f31b928ee892427fa0c8a5789eea5ae823d19"
    },
    "install-terminal.original.json": {
      "bytes": 729,
      "sha256": "80e7fce35bfa39535e0fa0513d10f3e2d4f9e0bfba6a618a0c17426f249951bf"
    },
    "global924.original.json": {
      "bytes": 35115,
      "sha256": "8a718803f7dc905e5c92c3609164c19caf1b213d88b235511554e39403568e25"
    },
    "phase-nonce.original.json": {
      "bytes": 989,
      "sha256": "1c625b299ba3067436b13e12a3bdc89ef29296f571ec43452ee214d77a7cd7bf"
    },
    "phase-nonce-terminal.original.json": {
      "bytes": 729,
      "sha256": "e958d89377f8a3fcc6fdaa13948a721d63fea2b07afde768324eb7a09a33e95b"
    }
  },
  "controls_request": {
    "bytes": 338495,
    "sha256": "671e038e1171a871fc238d405685eade41d9cc953979f304abaa9564a9a3576b"
  },
  "controls_stdin": {
    "bytes": 337839,
    "sha256": "64c9e2e88664befd74cce8b03e054e857661d28614fa92f7e160adeaf5cb9f98"
  },
  "wrapper_template": {
    "bytes": 4961,
    "sha256": "09408c678a9a9909ceecf4d09b9a5b256a1ec75e581636751d9eb0d5441db649"
  },
  "case_names": {
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
      "runtime_worker_unbound_stops_before_OS_or_Main",
      "retire_constructor_binds_own_fixed_root_without_IO",
      "runtime_lease_rejects_install_phase_before_IO",
      "runtime_lease_rejects_other_UID_before_IO",
      "runtime_lease_rejects_consumed_install_nonce_before_IO",
      "real_lease_claims_three_locks_and_exact_seven_sources",
      "same_lease_cannot_enter_run_twice",
      "run_lease_cannot_authorize_retirement_scope",
      "phase_lease_rejects_changed_external_manifest",
      "real_renamed_shared_ancestor_is_rejected_before_command",
      "real_lock_contention_and_failed_acquire_FD_remain_accounted",
      "unlock_failure_stays_failed_and_all_owned_FDs_close"
    ],
    "wiring": [
      "production_run_forwards_one_admission_and_all_five_commands",
      "production_retirement_requires_independent_scope_and_exact_XML",
      "failed_testMain_retirement_does_not_upgrade_native_tests",
      "production_phase_wrong_UID_stops_before_admission_or_context",
      "production_retirement_reused_attempt_stops_before_context",
      "production_open_context_verifies_phase_at_entry_and_each_guard"
    ]
  },
  "installation_job": "1a1b2e3bcfa-fc05-8021",
  "nonce_job": "1a1b2ff0950-fc05-8068"
};


function bindRuntimePhase(input,U,B) {
  const need=(value,message)=>{if(!value)throw Error(message);};
  const pin=raw=>{need(typeof raw==='string','original raw text required');
    const bytes=U.utf8(raw);return{bytes:bytes.length,sha256:U.sha256(bytes)};};
  const stable=value=>{
    if(typeof value==='bigint')return '#exact-integer:'+value.toString();
    if(value===null||typeof value!=='object')return JSON.stringify(value);
    if(Array.isArray(value))return '['+value.map(stable).join(',')+']';
    return '{'+Object.keys(value).sort().map(k=>JSON.stringify(k)+':'+stable(value[k])).join(',')+'}';
  };
  const equal=(a,b)=>stable(a)===stable(b);
  const parse=raw=>JSON.parse(raw,(_key,value,context)=>{
    if(typeof value==='number'&&Number.isInteger(value)&&!Number.isSafeInteger(value)){
      need(context&&/^-?[0-9]+$/.test(context.source),'lossless integer context required');
      return BigInt(context.source);
    }
    return value;
  });
  const exact=(raw,expected,label)=>{need(equal(pin(raw),expected),'exact original pin '+label);return raw;};
  const member=raw=>({body:raw,...pin(raw)});
  const terminal=(raw,stdout,job,label,allowFailed=false)=>{
    const value=parse(raw),count=U.utf8(stdout).length;
    need(value.job_id===job&&/^[0-9a-f]+-[0-9a-f]{4}-[0-9a-f]{4}$/.test(job),
         label+' actual job');
    const allowed=value.state==='succeeded'&&value.exit_code===0 ||
      allowFailed&&value.state==='failed'&&value.exit_code===1;
    need(allowed&&value.timed_out===false&&value.cancelled===false&&value.automatic_retry===false&&
      value.output_complete===true&&value.output_durable===true&&
      value.terminal_publication_confirmed===true&&
      equal(value.log_bytes,{stdout:{seen:count,stored:count},stderr:{seen:0,stored:0}})&&
      ['stdout','stderr'].every(k=>value.log_synced[k]===true&&
        value.log_truncated[k]===false&&value.log_errors[k]===null),label+' complete independent terminal');
    return value;
  };
  need(input&&typeof input==='object'&&['run','retire'].includes(input.phase),'one phase required');
  need(typeof input.actual_controls_stdout==='string'&&typeof input.actual_controls_terminal==='string'&&
       typeof input.controls_job==='string','actual new sixty controls are still unbound');
  const files=input.files;
  need(files&&typeof files==='object','fixed candidate files required');
  const sources={};
  for(const name of Object.keys(EXPECTED.sources).sort()){
    const raw=files['source/'+name];
    exact(raw,EXPECTED.sources[name],name);sources[name]=raw;
  }
  const manifestRaw=files['source/SOURCE_PINS.json'];
  const manifest=parse(exact(manifestRaw,EXPECTED.source_manifest,'runtime manifest'));
  need(manifest.schema==='pocket4-original-ndk-fixture-source-v1'&&equal(manifest.files,EXPECTED.sources),
       'complete seven runtime sources');
  for(const [name,expected]of Object.entries(EXPECTED.controls))
    exact(files['controls/'+name],expected,name);
  exact(files['requests/controls-request.json'],EXPECTED.controls_request,'exact controls request');
  exact(files['requests/controls-stdin.py'],EXPECTED.controls_stdin,'exact controls stdin');
  const wrapperRaw=input.wrapper_template;
  exact(wrapperRaw,EXPECTED.wrapper_template,'phase wrapper template');
  const refs={};
  for(const [name,expected]of Object.entries(EXPECTED.references)){
    const raw=files['references/'+name];exact(raw,expected,name);refs[name]=raw;
  }
  const original=parse(refs['install-result.original.json']);
  const originalSummary=parse(refs['install-summary.original.json']);
  terminal(refs['install-terminal.original.json'],refs['install-summary.original.json'],
           EXPECTED.installation_job,'original install');
  need(original.ok===true&&original.error===null&&equal(original.secondary_errors,[])&&
    original.owned_install_qualified===true&&original.exact_command_count===8&&
    original.installed_before.uid===10162&&original.owned_package_uid===10162&&
    equal(original.installed_before,original.artifact_after)&&
    original.outcome_unknown===false&&original.held_binding_released===true&&
    original.all_tracked_artifact_FDs_closed===true&&
    originalSummary.ok===true&&originalSummary.installed_UID===10162&&
    originalSummary.result.result_file_and_parent_FDs_closed===true&&
    originalSummary.result.bytes===EXPECTED.references['install-result.original.json'].bytes&&
    originalSummary.result.sha256===EXPECTED.references['install-result.original.json'].sha256,
    'complete qualified installation authority');
  const entry=parse(input.actual_controls_stdout);
  terminal(input.actual_controls_terminal,input.actual_controls_stdout,input.controls_job,'runtime entry controls');
  need(entry.schema===1&&entry.kind==='pocket4-original-ndk-runtime-entry-controls01'&&
    entry.ok===true&&equal(entry.errors,[])&&equal(entry.source_manifest,EXPECTED.source_manifest)&&
    equal(entry.sources,EXPECTED.sources)&&equal(entry.controls,EXPECTED.controls)&&
    equal(entry.counts,{fixture:38,manifest:4,lease:12,wiring:6})&&
    entry.all_owned_control_FDs_closed===true&&entry.all_owned_control_files_removed===true&&
    entry.Main_reads===0&&entry.Android_commands===0&&entry.children===0&&
    entry.namespace_entry===false&&entry.actual_install_nonce_consumed===false&&
    entry.actual_run_or_retire_nonce_consumed===false&&entry.runtime_qualified===false&&
    entry.automatic_retry===false&&entry.signal_handler_restored===true&&entry.umask_restored===true&&
    entry.ambient_FD_equality_asserted===false&&entry.whole_invocation_resource_observed===false,
    'new sixty actual host controls and closure');
  let names=[];
  for(const [group,expected]of Object.entries(EXPECTED.case_names)){
    const g=entry.groups[group];
    need(g&&g.ok===true&&g.count===expected.length&&Array.isArray(g.cases)&&
      equal(g.cases.map(x=>x.name),expected)&&g.cases.every(x=>x.passed===true),
      'actual named control group '+group);
    names.push(...expected);
  }
  need(names.length===60&&new Set(names).size===60&&equal(entry.cases.map(x=>x.name),names)&&
       entry.cases.every(x=>x.passed===true),'sixty unique actual production control results');
  need(entry.groups.lease.seams_restored===true&&entry.groups.lease.expected_unlock_failure_preserved===true&&
       entry.groups.lease.all_owned_control_FDs_closed===true&&entry.groups.lease.all_owned_control_files_removed===true&&
       entry.groups.wiring.seams_restored===true&&
       entry.groups.wiring.production_phase_bodies_and_joined_receipt_parser_called===true&&
       entry.groups.wiring.production_open_context_and_guard_closures_called===true,
       'actual production lease and phase/context seams closed');
  const refnames=['static-build.original.json','install-result.original.json',
                  'install-summary.original.json','install-terminal.original.json'];
  need(equal(entry.reference_pins,Object.fromEntries(refnames.map(n=>[n,EXPECTED.references[n]])))&&
    entry.original_install_reference.qualified_original_install_UID===10162&&
    equal(entry.original_install_reference.original_install_report,EXPECTED.references['install-result.original.json'])&&
    entry.original_install_reference.explicit_original_read_seam_calls===1&&
    entry.original_install_reference.read_seam_restored===true&&
    entry.original_install_reference.current_device_UID_observed===false&&
    entry.original_install_reference.runtime_qualified===false,'actual new worker original-install constructor');
  const material=parse(refs['phase-nonce.original.json']);
  terminal(refs['phase-nonce-terminal.original.json'],refs['phase-nonce.original.json'],
           EXPECTED.nonce_job,'phase nonce material');
  const pool=parse(refs['global924.original.json']);
  need(Array.isArray(pool)&&pool.length===924&&new Set(pool).size===924&&equal(pool,[...pool].sort())&&
    pool.every(x=>typeof x==='string'&&/^[0-9a-f]{32}$/.test(x)),'exact original global924 pool');
  need(material.kind==='pocket4-original-ndk-fixture-run-retire-nonce01'&&
    material.profile==='pocket4-original-ndk-fixture-APK05-run-retire01'&&
    material.package===material.target_package&&material.package==='com.example.ndk_tests'&&
    material.phase==='run_and_independent_retirement'&&material.generator==='secrets.token_hex(16)'&&
    material.requested_count===2&&material.draw_count===2&&material.redraw_attempted===false&&
    material.ok===true&&material.error===null&&material.fresh_against_exact_pool===true&&
    equal(material.labels,['run_nonce','retire_nonce'])&&
    equal(Object.keys(material.nonces).sort(),['retire_nonce','run_nonce'])&&
    material.uid===1000&&material.gid===1000&&material.runtime_authorized===false&&
    material.Main_reads===0&&material.Android_commands===0&&material.child_processes===0&&
    material.explicit_filesystem_reads===0&&material.explicit_filesystem_writes===0&&
    material.exclusion_pool.bytes===EXPECTED.references['global924.original.json'].bytes&&
    material.exclusion_pool.sha256===EXPECTED.references['global924.original.json'].sha256,
    'actual separate run and retirement material');
  need(Object.values(material.nonces).every(n=>/^[0-9a-f]{32}$/.test(n)&&n!=='0'.repeat(32)&&!pool.includes(n))&&
    material.nonces.run_nonce!==material.nonces.retire_nonce&&
    material.nonces.run_nonce!==original.scope.attempt_nonce&&
    material.nonces.retire_nonce!==original.scope.attempt_nonce,'distinct unused phase nonces');
  const phase=input.phase,root='/home/alex/work/pocket4-original-ndk-fixture-APK05-'+phase+'-01';
  const referenceRaw={...refs,
    'entry-controls.original.json':input.actual_controls_stdout,
    'entry-controls-terminal.original.json':input.actual_controls_terminal};
  const binding={schema:1,kind:'pocket4-original-ndk-runtime-binding-v1',phase,root,
    source_manifest:EXPECTED.source_manifest,
    entry_controls:pin(input.actual_controls_stdout),
    entry_controls_terminal:pin(input.actual_controls_terminal),
    entry_controls_job:input.controls_job,entry_controls_stdout_bytes:U.utf8(input.actual_controls_stdout).length,
    nonce_material:EXPECTED.references['phase-nonce.original.json'],
    nonce_terminal:EXPECTED.references['phase-nonce-terminal.original.json'],
    nonce_job:EXPECTED.nonce_job,nonce_stdout_bytes:U.utf8(refs['phase-nonce.original.json']).length,
    prior_run:null};
  if(phase==='run'){
    need(input.prior_run===undefined||input.prior_run===null,'run cannot adopt any prior run');
  }else{
    const prior=input.prior_run;
    need(prior&&typeof prior==='object'&&equal(Object.keys(prior).sort(),
      ['job','result_raw','summary_raw','terminal_raw']),'independent actual run material still unbound');
    need(U.utf8(prior.result_raw).length<=1048576&&U.utf8(prior.summary_raw).length<=8192&&
      U.utf8(prior.terminal_raw).length<=32768,'bounded prior run originals');
    const r=parse(prior.result_raw),sm=parse(prior.summary_raw);
    const tr=terminal(prior.terminal_raw,prior.summary_raw,prior.job,'original run',true);
    need(r.schema===1&&r.kind==='pocket4-original-ndk-fixture-run-v1'&&
      r.entry_kind==='pocket4-original-ndk-runtime-worker01'&&equal(r.source_manifest,EXPECTED.source_manifest)&&
      r.scope.phase==='run'&&r.scope.package==='com.example.ndk_tests'&&r.scope.uid===10162&&r.scope.user===0&&
      r.scope.attempt_nonce===material.nonces.run_nonce&&
      r.scope.Main_epoch===original.scope.Main_epoch&&r.scope.baseline_sha256===original.scope.baseline_sha256&&
      r.scope.qualification_sha256===original.scope.qualification_sha256&&
      equal(r.scope.build_result,original.scope.build_result)&&
      equal(r.install_result,EXPECTED.references['install-result.original.json'])&&
      equal(r.installed_before,original.installed_before)&&r.instrumentation_attempted===true&&
      r.retirement_required===true&&r.held_binding_released===true&&r.automatic_retry===false&&
      r.native_twelve_tests_qualified===false&&r.original_NdkTests_runtime_qualified===false&&
      r.commercial_App_readiness_qualified===false&&r.Main_deployment_or_restart===false,
      'same owned instrumentation run required for retirement');
    need(sm.schema===1&&sm.kind==='pocket4-original-ndk-runtime-worker-summary01'&&sm.phase==='run'&&
      sm.ok===r.ok&&equal(sm.error,r.error)&&sm.outcome_unknown===r.outcome_unknown&&
      sm.installed_UID===10162&&sm.original_NdkTests_runtime_qualified===false&&sm.automatic_retry===false&&
      equal(sm.result,{path:'/home/alex/work/pocket4-original-ndk-fixture-APK05-run-01/result.json',
        ...pin(prior.result_raw),result_file_and_parent_FDs_closed:true}),
      'exact complete run summary');
    if(r.ok===true)need(r.error===null&&equal(r.secondary_errors,[])&&tr.exit_code===0&&
      r.outcome_unknown===false&&r.instrumentation_verified===true&&r.exact_command_count===5&&
      r.current_Main_after_qualified===true,'successful run may not hide failure');
    else need(r.ok===false&&r.error!==null&&tr.exit_code===1,'failed run error retained');
    binding.prior_run={result:pin(prior.result_raw),summary:pin(prior.summary_raw),
      terminal:pin(prior.terminal_raw),job:prior.job,stdout_bytes:U.utf8(prior.summary_raw).length,
      source_manifest:EXPECTED.source_manifest};
    referenceRaw['run-result.original.json']=prior.result_raw;
    referenceRaw['run-summary.original.json']=prior.summary_raw;
    referenceRaw['run-terminal.original.json']=prior.terminal_raw;
  }
  const packet={schema:1,sources:Object.fromEntries(Object.keys(sources).sort().map(n=>[n,member(sources[n])])),
    manifest:member(manifestRaw),
    references:Object.fromEntries(Object.keys(referenceRaw).sort().map(n=>[n,member(referenceRaw[n])]))};
  const envelopeRaw=JSON.stringify({binding,packet},null,2)+'\n';
  need(U.utf8(envelopeRaw).length<=1048576,'fixed original wrapper packet bound');
  const encoded=B.enc(U.utf8(envelopeRaw));
  need(equal(pin(envelopeRaw),{bytes:B.dec(encoded).length,sha256:U.sha256(B.dec(encoded))}),
       'exact UTF8 bytes base64 roundtrip');
  let stdin=wrapperRaw;
  const slots={__PACKET_BYTES__:String(U.utf8(envelopeRaw).length),
    __PACKET_SHA256__:pin(envelopeRaw).sha256,__PACKET_B64__:encoded,
    __PHASE__:phase,__SOURCE_ROOT__:root+'/source'};
  for(const[slot,value]of Object.entries(slots)){
    need(stdin.split(slot).length===2,'unique wrapper slot '+slot);
    stdin=stdin.replace(slot,value);
  }
  const request={args:['-n','/usr/bin/python3','-I','-B','-'],cpu_quota_percent:100,
    cwd:'/home/alex/work',executable:'/usr/bin/sudo',host:'pocket4',
    idempotency_key:'p4-ndk-fixture-APK05-'+phase+'01-'+pin(stdin).sha256.slice(0,16),
    memory_max_bytes:536870912,nice:15,stdin,timeout_seconds:240};
  const requestRaw=JSON.stringify(request,null,2)+'\n';
  const proof={schema:1,phase,source_manifest:EXPECTED.source_manifest,controls:pin(input.actual_controls_stdout),
    controls_terminal:pin(input.actual_controls_terminal),controls_job:input.controls_job,
    original_install:EXPECTED.references['install-result.original.json'],installed_UID:10162,
    nonce_original:EXPECTED.references['phase-nonce.original.json'],nonce_job:EXPECTED.nonce_job,
    prior_run:binding.prior_run,envelope:pin(envelopeRaw),stdin:pin(stdin),request:pin(requestRaw),
    original_raw_reference_bytes_preserved:true,unsafe_integer_identity_compared_losslessly:true,
    strict_UTF8_base64_roundtrip:true,Python_or_device_executed_by_binder:false,
    runtime_already_qualified:false,Root_dispatch_still_required:true};
  return {binding,envelopeRaw,stdin,requestRaw,proof};
}
