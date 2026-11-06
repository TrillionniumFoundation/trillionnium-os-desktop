// Bind only two future complete actual receipts. No IO, entropy, device or install execution.
const EXPECTED={
  "preparation_tree": "efc51aba62e54e79ca8d2e67b33090adf535a2de",
  "files": {
    "source-template/fixture_contract.py": {
      "bytes": 25331,
      "sha256": "1b027dc076f0ee5d89df1e95ae76fddeacab1adaafb5e77e4b05b63f47593261",
      "git_blob_sha1": "6b76abcc871c4ba084f53e529d3dd96168e301aa"
    },
    "source-template/fixture_context.py": {
      "bytes": 21983,
      "sha256": "b81a06beb8a849d6b441b99872e8381356c79d48f7c274822722bbdf7356afc3",
      "git_blob_sha1": "bffb84c2a6e680e90bbede012e2bb22ec30a4227"
    },
    "source-template/fixture_phases.py": {
      "bytes": 25021,
      "sha256": "a41ce080e4242053d4152753e577b7fc923e31d536d94d540c2bd2cb506d800a",
      "git_blob_sha1": "c99046dc6eef35aa813fe2ffecede47bd64b6608"
    },
    "source-template/fixture_transport.py": {
      "bytes": 14639,
      "sha256": "8430f9384f61ad1b59534d7cc3d2006c5aa848bc404a067680d8b20845027fe6",
      "git_blob_sha1": "9890dc83ff7a5a00a911fa995a7a9383671f1cfb"
    },
    "source-template/current_discovery.py": {
      "bytes": 8332,
      "sha256": "9ed0069897faebba50cec3d93b08da54f1c791d6e2e775d26ec798c38b227886",
      "git_blob_sha1": "d94308531ea7d6b014c79900a1c61f001e081717"
    },
    "source-template/install_lease.py": {
      "bytes": 19771,
      "sha256": "7df03e2143f2e464784d99472ecaf7830c517232bc75e28362ac0b083595a50f",
      "git_blob_sha1": "2e9f4605c4ef49c926fa56b6b77a5a20fc08acc9"
    },
    "source-template/install_worker.py": {
      "bytes": 21023,
      "sha256": "8600ba7debacf2dbb6b294b1ed3f89e1b3dcb676db571ff76782ba4600ff59f6",
      "git_blob_sha1": "177470a45ffd4b1a0942770ff67945e3fff49244"
    },
    "controls/check_fixture.py": {
      "bytes": 17942,
      "sha256": "cd367e402119d2f353acfd66e1e5431a149f6e38b5d6a28a630995c8dc795852",
      "git_blob_sha1": "cbf61ed89191886c532f992bb197fd9f19fd17d3"
    },
    "controls/check_external_manifest.py": {
      "bytes": 4681,
      "sha256": "1bd278bd296084e46dd43b6dfc45420b85568a02c05e3823b11704fa14bd9e06",
      "git_blob_sha1": "07ba3d98dd020cef51819dd7550399b7bebde87f"
    },
    "controls/check_install_lease.py": {
      "bytes": 15887,
      "sha256": "ce8a1cac2bbde4f99319845914a7328e907c222a26a5ddc43e0540d8056510ae",
      "git_blob_sha1": "a1f676a7f6f5f823c771b6ea6448cdf0937dee87"
    },
    "controls/runner-template.py": {
      "bytes": 10043,
      "sha256": "ba7106b4407e6ee2ff91e0847df67c2dace0d59d7193654024cc2e762a571bdf",
      "git_blob_sha1": "064146ae8b8a59c0799ee19ffa9ab831b9289570"
    }
  },
  "known": {
    "static-build.original.json": {
      "bytes": 4893,
      "sha256": "c59318c119e43afc810debc6dbfd7367d37f1f9c154313572f732cc645124bae",
      "git_blob_sha1": "c1c099fc8b38b9e14ee8045bd856aa637097f293"
    },
    "build-terminal.original.json": {
      "bytes": 729,
      "sha256": "7df30068ee3849645f69085f9c16f1bc1094744fbacc26d765a09be0c21ded3d",
      "git_blob_sha1": "58a7513006a1085082c0b2d4f94c0d6c492a0ec1"
    },
    "build-stdout.original.json": {
      "bytes": 228,
      "sha256": "7e22891b785542a355a55f67b2235180d1dd216d176871338e88ebd6a2d706f6",
      "git_blob_sha1": "cb42b8b497a934e40aedd2c6e9c2d708edb7d6ea"
    },
    "global921.original.json": {
      "bytes": 35001,
      "sha256": "735f9acaf4100e82bf7bfdacbecf9510286b1099f8dee92bf668e942e8780bac",
      "git_blob_sha1": "ffda46203066f1fa704ab92071de8b86867c3589"
    }
  },
  "control_envelope": {
    "bytes": 254147,
    "sha256": "2e03b049bbfedd03c2ac64e5f2a553d74e4451be0c6b220582e9c91c8567cfb2",
    "git_blob_sha1": "b49aecee63e9b58ce89919594ecbef707f3a285a"
  },
  "readonly_source_pins": {
    "SOURCE_PINS.json": {
      "bytes": 777,
      "sha256": "e562e6744944d024448442f00f65913d87708fdc6211a6c5527a6d0044925b41"
    },
    "actual-static-build.json": {
      "bytes": 4893,
      "sha256": "c59318c119e43afc810debc6dbfd7367d37f1f9c154313572f732cc645124bae"
    },
    "build-stdout.original.json": {
      "bytes": 228,
      "sha256": "7e22891b785542a355a55f67b2235180d1dd216d176871338e88ebd6a2d706f6"
    },
    "build-terminal.original.json": {
      "bytes": 729,
      "sha256": "7df30068ee3849645f69085f9c16f1bc1094744fbacc26d765a09be0c21ded3d"
    },
    "check_fixture.py": {
      "bytes": 17942,
      "sha256": "cd367e402119d2f353acfd66e1e5431a149f6e38b5d6a28a630995c8dc795852"
    },
    "current_discovery.py": {
      "bytes": 8332,
      "sha256": "9ed0069897faebba50cec3d93b08da54f1c791d6e2e775d26ec798c38b227886"
    },
    "fixture_context.py": {
      "bytes": 21898,
      "sha256": "bbf7000ed08182db3017e89c8e7e2f0a77b285c30dfaef3b759ce078e9d4a741"
    },
    "fixture_contract.py": {
      "bytes": 25331,
      "sha256": "1b027dc076f0ee5d89df1e95ae76fddeacab1adaafb5e77e4b05b63f47593261"
    },
    "fixture_phases.py": {
      "bytes": 25021,
      "sha256": "a41ce080e4242053d4152753e577b7fc923e31d536d94d540c2bd2cb506d800a"
    },
    "fixture_transport.py": {
      "bytes": 14639,
      "sha256": "8430f9384f61ad1b59534d7cc3d2006c5aa848bc404a067680d8b20845027fe6"
    }
  },
  "fixture_cases": [
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
  "report": {
    "bytes": 9811685,
    "sha256": "d8eb53c924fa6a76bee19304bd8538bf2a57306b7e9bd6a55df8787d4ea33411"
  },
  "root": "/home/alex/work/pocket4-original-ndk-fixture-APK05-install-02",
  "nonce_material_tree": "feca957b7a9f896a71cf0538a6c78492c65e4649",
  "nonce_material_request": {
    "bytes": 41550,
    "sha256": "bdb0f9d5cfc9bcc7a13d307c695b5c8678ed6c5341e00454a1cb490b0c6dea47",
    "git_blob_sha1": "f3a0cd7b4e6faff8abfe479cd4578f25dcf78726"
  },
  "readonly_candidate_tree": "bc36737982dbb758b175fbb09580bfdae4296c14",
  "readonly_candidate_request": {
    "bytes": 176922,
    "sha256": "84227f87ad5612fc495001ca2c2df0d18a1bc8907ff88210e7d6db2267c619b7",
    "git_blob_sha1": "f43c527ca0ed3623f399f1bf0c9e586482061f3f"
  }
};
function b64tools(){const A="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";function enc(b){if(!(b instanceof Uint8Array))throw Error("bytes required");let s="";for(let i=0;i<b.length;i+=3){const n=b[i]*65536+(b[i+1]||0)*256+(b[i+2]||0);s+=A[n>>>18]+A[(n>>>12)&63]+(i+1<b.length?A[(n>>>6)&63]:"=")+(i+2<b.length?A[n&63]:"=");}return s;}function dec(s){if(s.length%4||!/^[A-Za-z0-9+/]*={0,2}$/.test(s))throw Error("b64 shape");const o=[];for(let i=0;i<s.length;i+=4){const c=s.slice(i,i+4),v=[...c].map(x=>x==="="?0:A.indexOf(x));if(v.some(x=>x<0))throw Error("b64 char");const n=v[0]*262144+v[1]*4096+v[2]*64+v[3];o.push((n>>>16)&255);if(c[2]!=="=")o.push((n>>>8)&255);if(c[3]!=="=")o.push(n&255);}const b=Uint8Array.from(o);if(enc(b)!==s)throw Error("b64 canonical");return b;}return{enc,dec};}

function prepareInstall02(utilitySource, files, known, oldControlsRequest, actual) {
  function need(v,m){if(!v)throw Error(m);}
  need(actual!==null&&typeof actual==="object","ACTUAL_READONLY38_AND_INSTALL_NONCE_UNBOUND");
  const U=Function(utilitySource+"\nreturn {utf8,sha256,gitBlob};")();
  need(U.gitBlob(U.utf8(utilitySource))==="443e39b58cd6fe72faa1cb1d1c7b0a813fa0032d","UTILITY_SOURCE_PIN");
  function parse(raw){
    return JSON.parse(raw,(_k,v,c)=>typeof v==="number"&&Number.isInteger(v)&&!Number.isSafeInteger(v)?c.source:v);
  }
  function sorted(v){
    if(Array.isArray(v))return v.map(sorted);
    if(v!==null&&typeof v==="object")return Object.fromEntries(Object.keys(v).sort().map(k=>[k,sorted(v[k])]));
    return v;
  }
  const equal=(a,b)=>JSON.stringify(sorted(a))===JSON.stringify(sorted(b));
  function keys(v,names){return v!==null&&typeof v==="object"&&!Array.isArray(v)&&equal(Object.keys(v).sort(),[...names].sort());}
  function rawPin(raw){need(typeof raw==="string","RAW_UTF8_REQUIRED");const b=U.utf8(raw);return{bytes:b.length,sha256:U.sha256(b)};}
  function fixed(raw,pin,maximum){
    need(typeof raw==="string"&&Number.isSafeInteger(pin.bytes)&&pin.bytes>0&&pin.bytes<=maximum&&
      /^[0-9a-f]{64}$/.test(pin.sha256)&&equal(rawPin(raw),{bytes:pin.bytes,sha256:pin.sha256}),"EXACT_WHOLE_PIN");
    if(pin.git_blob_sha1!==undefined)need(U.gitBlob(U.utf8(raw))===pin.git_blob_sha1,"EXACT_GIT_BLOB");
    return parse(raw);
  }
  function once(raw,old,value){need(raw.split(old).length===2,"ONE_BINDING_SLOT_"+old.slice(0,60));return raw.replace(old,value);}
  function member(body){return{body,...rawPin(body)};}
  function terminal(a,label){
    need(keys(a,["stdout_raw","stdout_pin","terminal_raw","terminal_pin","job_id"])&&
      /^[0-9a-f]+-[0-9a-f]{4}-[0-9a-f]{4}$/.test(a.job_id),"ACTUAL_RECEIPT_SHAPE_"+label);
    need(keys(a.stdout_pin,["bytes","sha256"])&&keys(a.terminal_pin,["bytes","sha256"]),"ACTUAL_PIN_FIELDS_"+label);
    const result=fixed(a.stdout_raw,a.stdout_pin,65536),t=fixed(a.terminal_raw,a.terminal_pin,32768);
    need(t.job_id===a.job_id&&t.state==="succeeded"&&t.exit_code===0&&t.output_complete===true&&t.output_durable===true&&
      t.terminal_publication_confirmed===true&&t.timed_out===false&&t.cancelled===false&&t.automatic_retry===false&&
      equal(t.log_bytes,{stdout:{seen:a.stdout_pin.bytes,stored:a.stdout_pin.bytes},stderr:{seen:0,stored:0}})&&
      ["stdout","stderr"].every(k=>t.log_synced[k]===true&&t.log_truncated[k]===false&&t.log_errors[k]===null),
      "INDEPENDENT_COMPLETE_TERMINAL_"+label);
    return result;
  }
  need(keys(files,Object.keys(EXPECTED.files))&&keys(known,Object.keys(EXPECTED.known)),"EXACT_FROZEN_INPUT_SETS");
  for(const [name,p]of Object.entries(EXPECTED.files)){
    need(equal(rawPin(files[name]),{bytes:p.bytes,sha256:p.sha256})&&U.gitBlob(U.utf8(files[name]))===p.git_blob_sha1,"TEMPLATE_PIN_"+name);
  }
  for(const [name,p]of Object.entries(EXPECTED.known))fixed(known[name],p,131072);
  fixed(oldControlsRequest,EXPECTED.control_envelope,524288);
  need(keys(actual,["readonly","nonce","global_after_raw","global_after_pin"]),"EXACT_TWO_ACTUALS_AND_POOL");
  const r=terminal(actual.readonly,"readonly38"),n=terminal(actual.nonce,"nonce02");
  need(actual.readonly.job_id!==actual.nonce.job_id,"DISTINCT_ACTUAL_JOBS");
  const b=parse(known["static-build.original.json"]);
  need(b.kind==="pocket4-original-ndk-fixture-actual-APK05-static-binding"&&b.package==="com.example.ndk_tests"&&
    b.ABI==="arm64-v8a"&&b.complete_static_build_qualified===true&&b.actual_original_NdkTests_runtime_qualified===false&&
    b.installed_UID===null&&b.install_run_retire_nonces===null&&b.runtime_request_generated===false&&
    b.manifest_min_sdk===14&&b.manifest_target_sdk===24&&
    equal({bytes:b.build_result.bytes,sha256:b.build_result.sha256},EXPECTED.report),"EXACT_STATIC_APK05_BINDING");
  need(r.schema===1&&r.kind==="pocket4-original-ndk-fixture-APK05-readonly-controls01"&&r.ok===true&&equal(r.errors,[])&&
    equal(r.source_pins,EXPECTED.readonly_source_pins)&&equal(r.report_pin,EXPECTED.report)&&
    r.complete_static_APK_report_qualified===true&&r.report_two_full_reads_completed===true&&
    r.report_read_functions_returned_after_close===true&&r.runtime_source_barriers_retained===true,
    "ACTUAL_READONLY38_COMPLETE_SOURCE_AND_REPORT");
  need(equal(r.report_identity_before,r.report_identity_after)&&r.report_identity_before.uid===1000&&
    r.report_identity_before.gid===1000&&r.report_identity_before.mode===33024&&
    r.report_identity_before.nlink===1&&r.report_identity_before.bytes===EXPECTED.report.bytes,
    "ACTUAL_REPORT_TWO_IDENTICAL_METADATA_ROWS");
  const q=r.qualified_static_build;
  need(q&&q.ABI==="arm64-v8a"&&q.min_sdk===14&&q.target_sdk===24&&q.runtime_qualified===false&&
    equal(q.build_result,EXPECTED.report)&&equal(q.APK,b.APK)&&q.signer_sha256===b.signature_certificate_sha256&&
    equal(q.native_members,b.native_members),"ACTUAL_READONLY_STATIC_APK05_NOT_RUNTIME");
  const c=r.controls;
  need(c&&c.schema===1&&c.ok===true&&c.count===38&&Array.isArray(c.cases)&&c.cases.length===38&&
    equal(c.cases.map(x=>x.name),EXPECTED.fixture_cases)&&c.cases.every(x=>x.passed===true)&&
    new Set(c.cases.map(x=>x.name)).size===38&&c.runtime_qualified===false&&c.actual_APK_or_UID_bound===false&&
    c.child_processes===0&&c.Main_namespace_reads===0&&c.Android_commands===0&&c.explicit_fixture_filesystem_reads===0&&
    c.explicit_fixture_filesystem_writes===0&&c.original_source_only_barrier_retained===true&&
    c.synthetic_IO_only===true&&c.pure_production_parsers_and_plans_called===true&&
    c.XML_fixture_not_an_actual_test_result===true&&c.standard_library_import_IO_included_in_counters===false,
    "ACTUAL_ORIGINAL38_EXACT_NAMES_AND_LIMITS");
  need(r.actual_installed_UID===null&&r.fixture_attempt_nonces===null&&r.runtime_dispatch_authorized===false&&
    r.Main_reads===0&&r.Android_commands===0&&r.child_processes===0&&r.namespace_entries===0&&
    r.explicit_fixture_files_written===0&&r.global_ambient_FD_equality_asserted===false&&
    r.standard_library_import_IO_included_in_counters===false&&r.whole_invocation_resource_observed===false&&
    equal(r.configured_envelope,{cpu_quota_percent:100,memory_max_bytes:268435456,nice:15,outer_timeout_seconds:60})&&
    typeof r.elapsed_seconds==="number"&&Number.isFinite(r.elapsed_seconds)&&r.elapsed_seconds>=0&&r.elapsed_seconds<35,
    "ACTUAL_READONLY_BOUNDARIES");
  const before=parse(known["global921.original.json"]);
  need(keys(actual.global_after_pin,["bytes","sha256"]),"ACTUAL_GLOBAL_AFTER_PIN");
  const after=fixed(actual.global_after_raw,actual.global_after_pin,131072);
  need(Array.isArray(before)&&before.length===921&&new Set(before).size===921&&equal(before,[...before].sort())&&
    before.every(x=>typeof x==="string"&&/^[0-9a-f]{32}$/.test(x))&&before.includes("e4b5a1bdac8be04ff2ea3188a6d946d6"),
    "COMPLETE_921_WITH_PRIOR_CONSUMED_NONCE");
  need(n.schema===1&&n.kind==="pocket4-original-ndk-fixture-install-nonce02"&&
    n.profile==="pocket4-original-ndk-fixture-APK05-install02"&&n.package==="com.example.ndk_tests"&&n.phase==="install"&&
    n.generator==="secrets.token_hex(16)"&&n.draw_count===1&&n.redraw_attempted===false&&n.ok===true&&
    n.error===null&&n.fresh_against_exact_pool===true&&n.uid===1000&&n.gid===1000&&n.runtime_authorized===false&&
    n.Main_reads===0&&n.Android_commands===0&&n.child_processes===0&&n.explicit_filesystem_reads===0&&
    n.explicit_filesystem_writes===0&&n.standard_library_and_entropy_IO_included_in_counters===false&&
    equal(n.exclusion_pool,{bytes:EXPECTED.known["global921.original.json"].bytes,
      sha256:EXPECTED.known["global921.original.json"].sha256,
      git_blob_sha:EXPECTED.known["global921.original.json"].git_blob_sha1,count:921})&&
    typeof n.nonce==="string"&&/^[0-9a-f]{32}$/.test(n.nonce)&&n.nonce!=="0".repeat(32)&&!before.includes(n.nonce),
    "ONE_ACTUAL_INSTALL_ONLY_DRAW_AGAINST921");
  need(Array.isArray(after)&&after.length===922&&new Set(after).size===922&&
    equal(after,[...before,n.nonce].sort()),"EXACT_922_ONE_DRAW_EXTENSION");
  const references={
    "static-build.original.json":known["static-build.original.json"],
    "build-terminal.original.json":known["build-terminal.original.json"],
    "build-stdout.original.json":known["build-stdout.original.json"],
    "readonly38.original.json":actual.readonly.stdout_raw,
    "readonly38-terminal.original.json":actual.readonly.terminal_raw,
    "install-nonce.original.json":actual.nonce.stdout_raw,
    "install-nonce-terminal.original.json":actual.nonce.terminal_raw,
    "global921.original.json":known["global921.original.json"],
    "global922.original.json":actual.global_after_raw
  };
  const referencePins=Object.fromEntries(Object.entries(references).map(([name,raw])=>[name,rawPin(raw)]));
  need(Object.keys(referencePins).length===9,"NINE_ORIGINAL_REFERENCES");
  const replacements=[
    ["INSTALL_NONCE = None  # Await the single actual install02 nonce; never reuse install01.",
     "INSTALL_NONCE = '"+n.nonce+"'"],
    ["REFERENCE_PINS = None  # Future actual readonly38/nonce originals must bind all nine rows.",
     "REFERENCE_PINS = json.loads(r'''"+JSON.stringify(referencePins)+"''')"],
    ["REFERENCE_PINS['readonly38-terminal.original.json'],None,None)",
     "REFERENCE_PINS['readonly38-terminal.original.json'],'"+actual.readonly.job_id+"',"+actual.readonly.stdout_pin.bytes+")"],
    ["REFERENCE_PINS['install-nonce-terminal.original.json'],None,None)",
     "REFERENCE_PINS['install-nonce-terminal.original.json'],'"+actual.nonce.job_id+"',"+actual.nonce.stdout_pin.bytes+")"]
  ];
  let worker=files["source-template/install_worker.py"];
  for(const [old,next]of replacements)worker=once(worker,old,next);
  let inverse=worker;for(const [old,next]of [...replacements].reverse())inverse=once(inverse,next,old);
  need(inverse===files["source-template/install_worker.py"],"WORKER_FOUR_SLOT_EXACT_INVERSE");
  need(worker.includes("PENDING_BINDING = None")&&worker.endsWith("    run_install(PENDING_BINDING,None)\n"),
    "INSTALL_ENTRY_REMAINS_UNBOUND_UNTIL_NEW50");
  const sources=Object.fromEntries(Object.keys(EXPECTED.files).filter(p=>p.startsWith("source-template/")).sort()
    .map(p=>[p.slice("source-template/".length),p.endsWith("/install_worker.py")?worker:files[p]]));
  need(Object.keys(sources).length===7,"SEVEN_SOURCES");
  const sourcePins=Object.fromEntries(Object.entries(sources).map(([name,raw])=>[name,rawPin(raw)]));
  const manifestRaw=JSON.stringify({schema:"pocket4-original-ndk-fixture-source-v1",files:sourcePins},null,2)+"\n";
  const sourceMembers=Object.fromEntries(Object.entries(sources).map(([name,raw])=>[name,member(raw)]));
  const basePacketRaw=JSON.stringify({schema:1,sources:sourceMembers,manifest:member(manifestRaw),
    references:Object.fromEntries(Object.entries(references).map(([name,raw])=>[name,member(raw)]))},null,2)+"\n";
  const controls=Object.fromEntries(["check_fixture.py","check_external_manifest.py","check_install_lease.py"]
    .map(name=>[name,files["controls/"+name]]));
  const controlsPacketRaw=JSON.stringify({schema:1,kind:"pocket4-original-ndk-install-entry-controls02",
    sources:sourceMembers,manifest:member(manifestRaw),
    controls:Object.fromEntries(Object.entries(controls).map(([name,raw])=>[name,member(raw)]))},null,2)+"\n";
  const B=b64tools(),bytes=U.utf8(controlsPacketRaw);
  need(bytes.length<=524288&&U.utf8(basePacketRaw).length<=524288,"BOUNDED_CONTROL_AND_INSTALL_PACKETS");
  const encoded=B.enc(bytes),decoded=B.dec(encoded);
  need(decoded.length===bytes.length&&decoded.every((x,i)=>x===bytes[i]),"UTF8_BYTE_BASE64_ROUNDTRIP");
  let controlsStdin=files["controls/runner-template.py"];
  const slots=[["__PACKET_SHA256__",U.sha256(bytes)],["__PACKET_BYTES__",String(bytes.length)],["__PACKET_B64__",encoded]];
  for(const [a,z]of slots)controlsStdin=once(controlsStdin,a,z);
  let unrender=controlsStdin;for(const [a,z]of [...slots].reverse())unrender=once(unrender,z,a);
  need(unrender===files["controls/runner-template.py"],"CONTROLS_THREE_SLOT_EXACT_INVERSE");
  const request=parse(oldControlsRequest),oldEnvelope={...request};delete oldEnvelope.stdin;delete oldEnvelope.idempotency_key;
  request.stdin=controlsStdin;request.idempotency_key="p4-ndk-fixture-install-entry-controls02-"+U.sha256(U.utf8(controlsStdin)).slice(0,16);
  const newEnvelope={...request};delete newEnvelope.stdin;delete newEnvelope.idempotency_key;
  need(equal(oldEnvelope,newEnvelope)&&request.timeout_seconds===60&&request.memory_max_bytes===268435456&&
    request.cpu_quota_percent===100&&request.nice===15&&request.executable==="/usr/bin/sudo"&&
    equal(request.args,["-n","/usr/bin/python3","-I","-B","-"]),"ORIGINAL_HOST50_RESOURCE_AND_ARGS");
  const controlsRequestRaw=JSON.stringify(request,null,2)+"\n";
  const proof={
    schema:1,kind:"pocket4-original-ndk-APK05-install02-source-binding-v1",
    preparation_tree:EXPECTED.preparation_tree,readonly_candidate_tree:EXPECTED.readonly_candidate_tree,
    readonly_candidate_request:EXPECTED.readonly_candidate_request,nonce_material_tree:EXPECTED.nonce_material_tree,
    nonce_material_request:EXPECTED.nonce_material_request,
    readonly_job:actual.readonly.job_id,readonly_stdout:actual.readonly.stdout_pin,readonly_terminal:actual.readonly.terminal_pin,
    nonce_job:actual.nonce.job_id,nonce_stdout:actual.nonce.stdout_pin,nonce_terminal:actual.nonce.terminal_pin,
    global_before:rawPin(known["global921.original.json"]),global_after:actual.global_after_pin,
    new_install_nonce:n.nonce,old_install_nonce_excluded:true,
    original_install01_status:"UNKNOWN",residual02_not_a_PM_absence_authority:true,
    source_manifest:rawPin(manifestRaw),references:referencePins,base_packet:rawPin(basePacketRaw),
    controls_packet:rawPin(controlsPacketRaw),controls_stdin:rawPin(controlsStdin),controls_request:rawPin(controlsRequestRaw),
    worker_four_binding_slots_inverse_equal:true,controls_three_render_slots_inverse_equal:true,base64_roundtrip_exact:true,
    original_38_plus_4_plus_8_preserved:true,current_fifty_controls_executed:false,
    installed:false,installed_UID:null,install_execution_request_generated:false,run_request_generated:false,retire_request_generated:false,
    pending_worker_binding:null,old_failure_retained:true,Root_dispatch_required:true,Main_or_Android_actions:0
  };
  return{sources,controls,manifestRaw,references,basePacketRaw,controlsPacketRaw,controlsStdin,controlsRequestRaw,
    proofRaw:JSON.stringify(proof,null,2)+"\n",substitutionsRaw:JSON.stringify(replacements,null,2)+"\n"};
}
