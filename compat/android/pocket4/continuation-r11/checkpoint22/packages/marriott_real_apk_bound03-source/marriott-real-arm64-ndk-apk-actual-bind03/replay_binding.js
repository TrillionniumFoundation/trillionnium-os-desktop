/* Deterministic source-to-request replay for the already frozen APK03.
 * No filesystem, network, Python, process, Android or Main action.
 * Supply exact UTF8 strings and the checked pure-JS utf8/sha256 primitives.
 * This reproduces serialization and binding; it does not claim Python execution.
 */
function reproduceMarriottAPK03(input, primitive) {
  const need=(value, reason)=>{if(!value)throw new Error(reason);};
  const {utf8, sha256}=primitive;
  need(typeof utf8==="function"&&typeof sha256==="function","checked UTF8/SHA256 primitives required");
  const expect={
    template:[84416,"7c8b48c44c39e04bf39e70601475546cbc18e00dbed48cc77f5682d51664b6ef"],
    pending:[328810,"b8eb422baf687c9c8b86c5fd6054dd5d668b9d697fa35c0c8dd5da64ac5955d5"],
    binder:[6574,"0c0e4fceec5c965516affca1f0f7e61e49dc5549b5e5c50c86f8bbdb070d14fb"],
    sourcePins:[450,"25c4b0326fda5a1f9eed4ceae5c2c1382cb066c50f5c68124b182c9d35cb2ed6"],
    sdk:[37845,"a19ae18405d48fbba22a10996094d06abdf792aace5e7bdf90742cb27f83559f"],
    sdkTerminal:[733,"af8bb249d34ce0fcc4ed49c2d962c217ca1409643ae1668b8d66e92fb26a6e87"],
    actual01:[111417,"e6da9ff2059c14a176b2f3a55d60cfaebc22b4bc079ed01581c28406718065ba"],
    request01:[393604,"995316e1ecf66c3573d2073a2de5ec858bc9d6d99fe6aed50f2313a964e12618"]
  };
  function hashText(text) { return sha256(utf8(text)); }
  for(const [name,[size,sha]] of Object.entries(expect)){
    need(typeof input[name]==="string"&&utf8(input[name]).length===size&&hashText(input[name])===sha,
         "exact complete input differs: "+name);
  }
  function parseLossless(raw) {
    return JSON.parse(raw,(key,value,context)=>
      typeof value==="number"&&!Number.isSafeInteger(value)?JSON.rawJSON(context.source):value);
  }
  function pretty(value) {
    function sorted(v) {
      if(JSON.isRawJSON(v))return v;
      if(Array.isArray(v))return v.map(sorted);
      if(v&&typeof v==="object"){
        const out={}; for(const k of Object.keys(v).sort())out[k]=sorted(v[k]); return out;
      }
      return v;
    }
    return JSON.stringify(sorted(value),null,2)
      .replace(/[\u007f-\uffff]/g,c=>"\\u"+c.charCodeAt(0).toString(16).padStart(4,"0"))+"\n";
  }
  function b64(bytes) {
    need(bytes instanceof Uint8Array,"base64 requires UTF8 byte array");
    const alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let out="";
    for(let i=0;i<bytes.length;i+=3){
      const a=bytes[i],b=i+1<bytes.length?bytes[i+1]:0,c=i+2<bytes.length?bytes[i+2]:0;
      out+=alphabet[a>>>2]+alphabet[((a&3)<<4)|(b>>>4)]+
        (i+1<bytes.length?alphabet[((b&15)<<2)|(c>>>6)]:"=")+
        (i+2<bytes.length?alphabet[c&63]:"=");
    }
    return out;
  }
  const cfg=parseLossless(input.pending),pins=parseLossless(input.sourcePins);
  need(pins.schema===1&&pretty(Object.keys(pins.files).sort())===
       pretty(["bind_build.py","build-template.py","config-pending.json"]),"exact binder source set");
  for(const [path,name] of [["build-template.py","template"],["config-pending.json","pending"],
                            ["bind_build.py","binder"]]){
    need(pins.files[path].bytes===expect[name][0]&&pins.files[path].sha256===expect[name][1],
         "source manifest member differs: "+path);
  }
  need(cfg.kind==="p4-marriott-real-arm64-ndk-apk-build03"&&
       cfg.root==="/home/alex/work/pocket4-marriott-real-arm64-ndk-apk-03-20261106"&&
       cfg.script_only_pending_actuals===true&&cfg.actual_sdk_configuration===null&&
       typeof cfg.actual_sdk22_failed_original==="object"&&!("actual_apk13" in cfg),
       "fixed pending configuration differs");
  const status=parseLossless(input.sdkTerminal),sdk=parseLossless(input.sdk);
  need(status.job_id==="1a1b1af6f3a-fc05-7a45"&&status.state==="succeeded"&&status.exit_code===0&&
       status.output_complete===true&&status.output_durable===true&&
       status.terminal_publication_confirmed===true&&status.timed_out===false&&
       status.cancelled===false&&status.automatic_retry===false,"successful exact SDK terminal");
  for(const stream of ["stdout","stderr"]){
    need(status.log_synced[stream]===true&&status.log_truncated[stream]===false&&
         status.log_errors[stream]===null,"SDK stream integrity");
    const n=stream==="stdout"?expect.sdk[0]:0;
    need(status.log_bytes[stream].seen===n&&status.log_bytes[stream].stored===n,"SDK stream length");
  }
  need(sdk.collection_complete===true&&sdk.first_error===null&&sdk.errors.length===0&&
       sdk.all_tracked_owned_FDs_closed===true&&sdk.control_deadline_met===true&&
       sdk.own_resource_interval_qualified===true&&
       sdk.sdk_configuration_join.qualified_for_fixed_build_input_binding===true,
       "actual fixed SDK input qualifier differs");
  const old=parseLossless(input.actual01),rows=old.apk13_first_observation.rows;
  need(old.success===false&&old.commands.length===0&&old.objects.length===0&&rows.length===13,
       "preserve actual first build failure");
  const selections=[
    [3,"ndk_libcxx_static"],[4,"ndk_libcxxabi"],[5,"arm64_unwind"],[6,"arm64_builtins"],
    [10,"android_test_runner31"],[11,"android_test_base31"],[12,"android_test_mock31"]
  ];
  const provenance=[];
  for(const [index,role] of selections){
    const row=rows[index],spec=cfg.apk_input_specifications.find(s=>s.role===role);
    need(row.role===role&&spec&&row.path===spec.path&&row.full_reads===2&&
         row.whole_input_and_identity_unchanged===true&&row.owned_leaf_FDs_closed===true&&
         row.expected_matches===true&&row.bytes===spec.expected_bytes&&
         row.sha256===spec.expected_sha256,"actual complete whole pin: "+role);
    for(const field of ["named_before","named_after","held_after"])
      need(pretty(row[field])===pretty(row.before),"actual full identity: "+role+"/"+field);
    if(role==="android_test_runner31"){
      need(row.complete===false&&row.error.type==="RuntimeError"&&
           row.error.message==="required official class missing from fixed jar",
           "original runner class failure must remain");
    } else need(row.complete===true&&row.error===null,"other six input qualifications");
    provenance.push({role,index,bytes:row.bytes,sha256:row.sha256,
      full_reads:2,original_complete:row.complete,original_error:row.error});
  }
  cfg.actual_sdk_configuration={
    bytes:expect.sdk[0],sha256:expect.sdk[1],base64:b64(utf8(input.sdk)),
    terminal:{bytes:expect.sdkTerminal[0],sha256:expect.sdkTerminal[1],
      base64:b64(utf8(input.sdkTerminal)),job_id:status.job_id}
  };
  cfg.script_only_pending_actuals=false;
  const config=pretty(cfg),needle="CFG = None  # The immutable packet generator fills this exactly once.";
  need(input.template.split(needle).length===2&&!config.includes("'''"),"one exact CFG binding slot");
  const build=input.template.replace(needle,"CFG = json.loads(r'''"+config+"''')");
  const originalRequest=parseLossless(input.request01),requestValue={...originalRequest,
    stdin:build,idempotency_key:"p4-marriott-real-arm64-ndk-apk-build03-"+hashText(build).slice(0,16)};
  const request=pretty(requestValue);
  const expectedOutputs={
    config:[380560,"bb7c58a719e15737318a6958077d25e125c3a46065565338e2220a74e5bfb331"],
    build:[464932,"da85a0f27af0d2b1e89554d60279b95465b798ffc67f63747afdbc44043a75cb"],
    request:[470162,"84bbf18c42cf89f87c308a8bfd4eae47a2091093e84426c3061e124432fb10ff"]
  };
  for(const [name,body] of Object.entries({config,build,request}))
    need(utf8(body).length===expectedOutputs[name][0]&&hashText(body)===expectedOutputs[name][1],
         "published whole output differs: "+name);
  for(const key of Object.keys(originalRequest))
    if(!["stdin","idempotency_key"].includes(key))
      need(pretty(requestValue[key])===pretty(originalRequest[key]),"unchanged request field: "+key);
  return {config,build,request,proof:{
    exact_all_input_pins:true,exact_all_output_pins:true,all_seven_pins_from_full_actual01:true,
    provenance,request_key:requestValue.idempotency_key,
    old_runner_format_failure_preserved:true,base_Case_class_actual_still_required:true,
    Python_executed:false,Hepta_called:false,Android_actions:0,Main_actions:0
  }};
}
