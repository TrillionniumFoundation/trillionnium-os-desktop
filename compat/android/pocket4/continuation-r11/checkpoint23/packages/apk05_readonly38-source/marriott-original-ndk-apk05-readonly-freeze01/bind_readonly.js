// Pure source/actual binder. No filesystem, network, process or Android operation.
// Unsafe integer JSON tokens are emitted with JSON.rawJSON, never rounded.
function bindAPK05Readonly(inputs,U,B) {
  const expectedSources={
  "current_discovery.py": {
    "bytes": 8332,
    "sha256": "9ed0069897faebba50cec3d93b08da54f1c791d6e2e775d26ec798c38b227886",
    "git_blob_sha": "d94308531ea7d6b014c79900a1c61f001e081717"
  },
  "fixture_context.py": {
    "bytes": 21898,
    "sha256": "bbf7000ed08182db3017e89c8e7e2f0a77b285c30dfaef3b759ce078e9d4a741",
    "git_blob_sha": "10a9f57a0c3d382433598c2593a5180dfd2e8f77"
  },
  "fixture_contract.py": {
    "bytes": 25331,
    "sha256": "1b027dc076f0ee5d89df1e95ae76fddeacab1adaafb5e77e4b05b63f47593261",
    "git_blob_sha": "6b76abcc871c4ba084f53e529d3dd96168e301aa"
  },
  "fixture_phases.py": {
    "bytes": 25021,
    "sha256": "a41ce080e4242053d4152753e577b7fc923e31d536d94d540c2bd2cb506d800a",
    "git_blob_sha": "c99046dc6eef35aa813fe2ffecede47bd64b6608"
  },
  "fixture_transport.py": {
    "bytes": 14639,
    "sha256": "8430f9384f61ad1b59534d7cc3d2006c5aa848bc404a067680d8b20845027fe6",
    "git_blob_sha": "9890dc83ff7a5a00a911fa995a7a9383671f1cfb"
  }
};
  const expectedOther={
  "template": {
    "bytes": 9982,
    "sha256": "0a079b9da1be0923188cccabfeebc05417d3266021056415d7e2562425dc441a",
    "git_blob_sha": "e4e7c8d17070d5dba0f33c67ecaab91fce831993"
  },
  "check": {
    "bytes": 17942,
    "sha256": "cd367e402119d2f353acfd66e1e5431a149f6e38b5d6a28a630995c8dc795852",
    "git_blob_sha": "cbf61ed89191886c532f992bb197fd9f19fd17d3"
  },
  "baseRequest": {
    "bytes": 174014,
    "sha256": "92036009bcee0e3311cdd616f37fcf650d62374d3055320a04ab2609122e4e68",
    "git_blob_sha": "e862cce86ee4ade73bd0ff30fecd4f1e01667849"
  },
  "terminal": {
    "bytes": 729,
    "sha256": "7df30068ee3849645f69085f9c16f1bc1094744fbacc26d765a09be0c21ded3d",
    "git_blob_sha": "58a7513006a1085082c0b2d4f94c0d6c492a0ec1"
  },
  "stdout": {
    "bytes": 228,
    "sha256": "7e22891b785542a355a55f67b2235180d1dd216d176871338e88ebd6a2d706f6",
    "git_blob_sha": "cb42b8b497a934e40aedd2c6e9c2d708edb7d6ea"
  },
  "review": {
    "bytes": 13272,
    "sha256": "e4f17eb9e6337997b0118fb29197bf79807c394b55ddd47639572840221d9cc7",
    "git_blob_sha": "2ec0849b331f9eb936a0ac07187bf7cfcb27dc8a"
  }
};
  const sourceNames=Object.keys(expectedSources).sort();
  const pin=s=>({bytes:U.utf8(s).length,sha256:U.sha256(U.utf8(s)),git_blob_sha:U.gitBlob(U.utf8(s))});
  const short=s=>{const p=pin(s);return {bytes:p.bytes,sha256:p.sha256};};
  const same=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
  const demand=(v,m)=>{if(!v)throw Error(m);};
  for(const name of sourceNames)demand(same(pin(inputs.sources[name]),expectedSources[name]),"exact source "+name);
  for(const name of Object.keys(expectedOther))demand(same(pin(inputs[name]),expectedOther[name]),"exact binder input "+name);
  demand(same(Object.keys(inputs.sources).sort(),sourceNames),"five sources only");
  const rawPin=pin(inputs.report);
  demand(rawPin.bytes===9811685&&rawPin.sha256==="d8eb53c924fa6a76bee19304bd8538bf2a57306b7e9bd6a55df8787d4ea33411"&&rawPin.git_blob_sha==="b9e554da10457c28186be38db3c8916bc7edb79f","complete actual05 original");
  demand(typeof JSON.rawJSON==="function","lossless raw numeric serialization required");
  const report=JSON.parse(inputs.report,(k,v,c)=>typeof v==="number"&&Number.isInteger(v)&&!Number.isSafeInteger(v)?JSON.rawJSON(c.source):v);
  const review=JSON.parse(inputs.review),terminal=JSON.parse(inputs.terminal),stdout=JSON.parse(inputs.stdout);
  demand(review.qualification.complete_static_APK_build===true&&review.checks.failures.length===0&&review.original.sha256===rawPin.sha256,"independent complete static review");
  demand(report.success===true&&report.errors.length===0&&report.kind==="p4-marriott-real-arm64-ndk-apk-build05"&&report.APK_contract.target_sdk===24&&report.installed===false&&report.ART_runtime_qualified===false,"actual static only");
  demand(terminal.job_id==="1a1b299fafc-fc05-7edb"&&terminal.exit_code===0&&terminal.output_complete===true&&terminal.output_durable===true,"actual successful terminal");
  const reportPath="/home/alex/work/pocket4-marriott-real-arm64-ndk-apk-05-20261106/build-result.json";
  demand(stdout.path===reportPath&&stdout.bytes===rawPin.bytes&&stdout.sha256===rawPin.sha256&&stdout.success===true&&stdout.first_error===null,"exact summary points to original");
  const manifest={files:Object.fromEntries(sourceNames.map(n=>[n,short(inputs.sources[n])])),schema:"pocket4-original-ndk-fixture-source-v1"};
  const manifestRaw=JSON.stringify(manifest,null,2)+"\n";
  const originalRegistry=Object.keys(report.linked_test_registry.linked_TestBody_symbols).sort();
  const focus=originalRegistry.filter(x=>x.startsWith("ProcSelfMaps."));
  demand(originalRegistry.length===23&&focus.length===12,"static23/exact12 shape");
  const binding={
    schema:1,kind:"pocket4-original-ndk-fixture-actual-APK05-static-binding",
    package:"com.example.ndk_tests",ABI:"arm64-v8a",
    actual_tree:"8a327ae27f0f50e4fcacbe63e8aa537f1bfcfaf1",
    build_result:{path:reportPath,...rawPin},
    APK:report.APK,signature_certificate_sha256:report.APK_contract.signature_certificate_sha256,
    native_members:report.APK_contract.native_members,manifest_min_sdk:14,manifest_target_sdk:24,
    original_registry23:originalRegistry,exact_focus12:focus,
    source_manifest:short(manifestRaw),
    independent_review:{...pin(inputs.review),tree:"91e0c2fccd66adaf1c011351d96d2077024f684b"},
    terminal:{...pin(inputs.terminal),job_id:terminal.job_id},stdout:pin(inputs.stdout),
    complete_static_build_qualified:true,installed_UID:null,install_run_retire_nonces:null,
    install_source_root:null,runtime_request_generated:false,
    Main_or_Android_action_authorized_by_this_binding:false,
    actual_original_NdkTests_runtime_qualified:false,commercial_45_App_readiness:false,
    typed_baseline_reference:{
      baseline_sha256:"633912ff4595ce898c4c0e0f9ac06c1f422203d90fbd2e583192f35ff7a04364",
      current_Main_read_or_runtime_admission:false,
      epoch:"7d927812392d30ab8cca43da87c0785e24695ca724da93b3b465122502b8045c",
      qualification_sha256:"ae8d54ee64fe23676d7f68f8092c0915d3f0f41662d8b7d4be86b85201071a6e"
    },
    historical_install01:"UNKNOWN; target23 PM denial original retained",
    historical_residual01:"FAILED before package/data reads; no absence inference"
  };
  const bindingRaw=JSON.stringify(binding,null,2)+"\n";
  demand(bindingRaw.includes('"mtime_ns": 1793997817893717337')&&bindingRaw.includes('"ctime_ns": 1793997817893717337'),"original unsafe numeric tokens retained");
  const files={...inputs.sources,"check_fixture.py":inputs.check,"SOURCE_PINS.json":manifestRaw,
    "actual-static-build.json":bindingRaw,"build-terminal.original.json":inputs.terminal,
    "build-stdout.original.json":inputs.stdout};
  const members=Object.fromEntries(Object.keys(files).sort().map(n=>[n,{...short(files[n]),body:files[n]}]));
  demand(Object.keys(members).length===10&&Object.values(members).every(x=>x.bytes>0&&x.bytes<=131072),"exact ten bounded members");
  const packet=JSON.stringify({schema:1,kind:"pocket4-original-ndk-fixture-APK05-readonly-controls",members},null,2)+"\n";
  demand(U.utf8(packet).length<=262144,"packet bound");
  const base64=B.enc(U.utf8(packet));
  demand(U.sha256(B.dec(base64))===short(packet).sha256,"UTF8 byte base64 exact roundtrip");
  let stdin=inputs.template;
  const replacements=[
    ["PACKET_B64 = None  # Exact UTF8-byte packet binding, not a runtime authority.","PACKET_B64 = "+JSON.stringify(base64)],
    ["PACKET_SHA256 = None","PACKET_SHA256 = "+JSON.stringify(short(packet).sha256)],
    ["PACKET_BYTES = None","PACKET_BYTES = "+short(packet).bytes]
  ];
  for(const[a,b]of replacements){demand(stdin.split(a).length===2,"one actual slot");stdin=stdin.replace(a,b);}
  let inverse=stdin;for(const[a,b]of replacements.toReversed())inverse=inverse.replace(b,a);
  demand(inverse===inputs.template,"bound stdin exact template inverse");
  const q=JSON.parse(inputs.baseRequest),before=JSON.parse(inputs.baseRequest);
  q.stdin=stdin;q.idempotency_key="p4-original-ndk-fixture-APK05-readonly-controls01-"+short(stdin).sha256.slice(0,16);
  demand(Object.keys(q).filter(k=>k!=="stdin"&&k!=="idempotency_key").every(k=>same(q[k],before[k])),"request only stdin/key changed");
  const request=JSON.stringify(q,null,2)+"\n";
  return {files,manifest:manifestRaw,binding:bindingRaw,packet,stdin,request,
    proof:{schema:1,kind:"APK05-actual-readonly-binding-proof",raw_original:rawPin,
      independent_review:pin(inputs.review),sources:expectedSources,manifest:pin(manifestRaw),
      binding:pin(bindingRaw),packet:pin(packet),stdin:pin(stdin),request:pin(request),
      base64_UTF8_roundtrip:true,template_inverse_exact:true,request_other_fields_unchanged:true,
      actual_installed_UID:null,attempt_nonce:null,Python_execution_performed:false,
      Main_or_Android_actions:0,runtime_admission:false}};
}
