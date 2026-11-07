function deriveAPK04(U, I) {
  function need(v,m){if(!v)throw Error(m);}
  function pin(s){const b=U.utf8(s);return {bytes:b.length,sha256:U.sha256(b),git_blob_sha:U.gitBlob(b)};}
  const expected={
    template:[84416,"7c8b48c44c39e04bf39e70601475546cbc18e00dbed48cc77f5682d51664b6ef","4324abf0f3f3c62cb88ca5bd14c89a17deaefc08"],
    config:[380560,"bb7c58a719e15737318a6958077d25e125c3a46065565338e2220a74e5bfb331","bedd1854f329934044260c33ed36f6c9cc14f2c0"],
    build:[464932,"da85a0f27af0d2b1e89554d60279b95465b798ffc67f63747afdbc44043a75cb","7ada7eb105b06e2520411e5e45dc4606b106281e"],
    request:[470162,"84bbf18c42cf89f87c308a8bfd4eae47a2091093e84426c3061e124432fb10ff","6aa0018407844ea93200cd470607f983074d6067"],
    failed_result:[8994,"0c3669215137fc4b8fce1603c586a6e8d8451777a359c926a29e9b43200cf202","055af604d46464e7755a74c5fb34e5798ceee5b1"],
    failed_command:[443,"0b04b1ee2d79fdfe56833d6cb6172b1ec13d5446964043e914f4488e8f675f72","0f7c924a9850caaaed27fc8283df78dfd48df9fd"],
    failed_stdout:[111,"c93c16f3c1199574fa44e070358f7292da1ed55e3c4eea13d97d47270cbc191c","e6990d74126df4f412cbfde7b28d902a460944cc"]
  };
  for(const [k,p]of Object.entries(expected)){const a=pin(I[k]);need(a.bytes===p[0]&&a.sha256===p[1]&&a.git_blob_sha===p[2],"original pin "+k);}
  function one(s,a,b){need(s.split(a).length===2,"unique replacement "+a);return s.replace(a,b);}
  function b64(b){
    need(b instanceof Uint8Array,"base64 needs UTF8 bytes");
    const a="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";let s="";
    for(let i=0;i<b.length;i+=3){const n=b[i]*65536+(b[i+1]||0)*256+(b[i+2]||0);
      s+=a[n>>>18]+a[(n>>>12)&63]+(i+1<b.length?a[(n>>>6)&63]:"=")+(i+2<b.length?a[n&63]:"=");}
    return s;
  }
  function unb64(s){
    need(s.length%4===0&&/^[A-Za-z0-9+/]*={0,2}$/.test(s),"base64 shape");
    const a="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/",o=[];
    for(let i=0;i<s.length;i+=4){const c=s.slice(i,i+4),v=[...c].map(x=>x==="="?0:a.indexOf(x));
      need(v.every(x=>x>=0),"base64 alphabet");const n=v[0]*262144+v[1]*4096+v[2]*64+v[3];
      o.push((n>>>16)&255);if(c[2]!=="=")o.push((n>>>8)&255);if(c[3]!=="=")o.push(n&255);}
    const b=Uint8Array.from(o);need(b64(b)===s,"canonical base64");return b;
  }
  function ascii(b){need(b.every(x=>x<128),"ASCII source");return Array.from(b,x=>String.fromCharCode(x)).join("");}
  function parse(s){return JSON.parse(s,(k,v,c)=>typeof v==="number"?JSON.rawJSON(c.source):v);}
  function q(s){return JSON.stringify(s).replace(/[\u007f-\uffff]/g,c=>"\\u"+c.charCodeAt(0).toString(16).padStart(4,"0"));}
  function emit(v,n=0){
    if(JSON.isRawJSON(v))return v.rawJSON;if(v===null)return"null";
    if(typeof v==="string")return q(v);if(typeof v==="number"||typeof v==="boolean")return JSON.stringify(v);
    const p=" ".repeat(n+2),e=" ".repeat(n);
    if(Array.isArray(v))return v.length?"[\n"+v.map(x=>p+emit(x,n+2)).join(",\n")+"\n"+e+"]":"[]";
    need(typeof v==="object","JSON object");const keys=Object.keys(v).sort();
    return keys.length?"{\n"+keys.map(k=>p+q(k)+": "+emit(v[k],n+2)).join(",\n")+"\n"+e+"}":"{}";
  }
  const stringify=v=>emit(v)+"\n",oldC=parse(I.config),oldQ=parse(I.request);
  need(stringify(oldC)===I.config&&stringify(oldQ)===I.request,"original lossless serializer equality");
  const slot="CFG = None  # The immutable packet generator fills this exactly once.";
  const render=(t,c)=>one(t,slot,"CFG = json.loads(r'''"+c+"''')");
  need(render(I.template,I.config)===I.build&&oldQ.stdin===I.build,"actual03 source/config/request equality");
  const failure=JSON.parse(I.failed_result),cmd=JSON.parse(I.failed_command);
  need(failure.ok===false&&failure.outcome_unknown===true&&failure.install_attempted===true&&
       failure.scope.package==="com.example.ndk_tests"&&failure.scope.uid===null&&failure.exact_command_count===2&&
       failure.scope.attempt_nonce==="e4b5a1bdac8be04ff2ea3188a6d946d6"&&!failure.owned_install_qualified,"preserved failed install");
  need(cmd.returncode===1&&cmd.spawned&&cmd.owned_command_joined&&!cmd.timed_out&&
       cmd.stdout_sha256===expected.failed_stdout[1]&&
       cmd.stderr_sha256==="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855","actual command2 failure");
  need(I.failed_stdout==="Failure [INSTALL_FAILED_DEPRECATED_SDK_VERSION: App package must target at least SDK version 24, but found 23]\n","exact PM rejection");
  const oldManifest=ascii(unb64(oldC.sources["AndroidManifest.xml"].base64));
  need(pin(oldManifest).bytes===1238&&pin(oldManifest).sha256==="40d1e4565ab9a54f0bab8790c2b578f296a306fbeb9b4cca247f82004876ea6b","original manifest");
  let manifest=one(oldManifest,'<uses-sdk android:minSdkVersion="14" android:targetSdkVersion="23" />',
                                '<uses-sdk android:minSdkVersion="14" android:targetSdkVersion="24" />');
  manifest=one(manifest,
    '    <!-- Note: we MUST use targetSdkVersion="23" (or less) here - otherwise shared libraries\n         greylist is permanently disabled -->',
    '    <!-- Upstream target 23 supports legacy shared-library greylist tests.\n         This fixture targets 24 after the actual PackageManager rejection of 23.\n         Shared tests remain registered; only ProcSelfMaps.* is selected for this fixture. -->');
  const changes=[
    ["{attr+'minSdkVersion':'14',attr+'targetSdkVersion':'23'}","{attr+'minSdkVersion':'14',attr+'targetSdkVersion':'24'}"],
    ["'original NDK min14/target23 contract changed'","'approved fixture min14/target24 contract changed'"],
    ["# The original APK keeps native libraries compressed and the target23 extraction behavior.","# Native libraries remain compressed; extraction is handled by the platform."],
    ['"targetSdkVersion:\'23\'"','"targetSdkVersion:\'24\'"'],
    ["'min_sdk':14,'target_sdk':23","'min_sdk':14,'target_sdk':24"],
    ["p4-marriott-real-arm64-ndk-apk-build03","p4-marriott-real-arm64-ndk-apk-build04"],
    ["/home/alex/work/pocket4-marriott-real-arm64-ndk-apk-03-20261106","/home/alex/work/pocket4-marriott-real-arm64-ndk-apk-04-20261106"],
    ["'manifest_min_sdk':14,'manifest_target_sdk':23","'manifest_min_sdk':14,'manifest_target_sdk':24"]
  ];
  let template=I.template;for(const[a,b]of changes)template=one(template,a,b);
  let inv=template;for(const[a,b]of changes.slice().reverse())inv=one(inv,b,a);need(inv===I.template,"template exact inverse");
  const oldRoot="/home/alex/work/pocket4-marriott-real-arm64-ndk-apk-03-20261106",newRoot=oldRoot.replace("-03-","-04-");
  let cfgRaw=one(I.config,'"kind": "p4-marriott-real-arm64-ndk-apk-build03"','"kind": "p4-marriott-real-arm64-ndk-apk-build04"');
  need(cfgRaw.split(oldRoot).length===5,"four exact own root fields");cfgRaw=cfgRaw.split(oldRoot).join(newRoot);
  const cfg=parse(cfgRaw),m={base64:b64(U.utf8(manifest)),bytes:U.utf8(manifest).length,sha256:U.sha256(U.utf8(manifest))};
  cfg.sources["AndroidManifest.xml"]=m;cfgRaw=stringify(cfg);
  const back=parse(cfgRaw);back.kind=oldC.kind;back.root=oldC.root;back.sources["AndroidManifest.xml"]=oldC.sources["AndroidManifest.xml"];
  for(const i of [7,8,9]){need(oldC.apk_input_specifications[i].path.startsWith(oldRoot+"/source/prebuilts/ndk/"),"three own source paths");back.apk_input_specifications[i].path=oldC.apk_input_specifications[i].path;}
  need(stringify(back)===I.config,"config exact inverse");
  for(const k of Object.keys(oldC.sources))if(k!=="AndroidManifest.xml")need(stringify(cfg.sources[k])===stringify(oldC.sources[k]),"real source unchanged "+k);
  need(ascii(unb64(m.base64))===manifest,"new source byte encoding");
  const build=render(template,cfgRaw),req=parse(I.request);req.stdin=build;
  req.idempotency_key="p4-marriott-real-arm64-ndk-apk-build04-"+pin(build).sha256.slice(0,16);
  const request=stringify(req),backQ=parse(request);backQ.stdin=oldQ.stdin;backQ.idempotency_key=oldQ.idempotency_key;
  need(stringify(backQ)===I.request,"envelope exact inverse");
  return {template,config:cfgRaw,build,request,manifest,baseline_manifest:oldManifest,changes,
    proof:{schema:1,state:"SOURCE_AND_ACTUAL_INPUTS_BOUND_UNRUN",inputs:expected,
      outputs:{template:pin(template),config:pin(cfgRaw),build:pin(build),request:pin(request),manifest:pin(manifest)},
      template_and_config_exact_inverse:true,all_15_other_sources_identical:true,all_50_commands_and_cleanup_paths_unchanged:true,
      semantic_change:"Manifest targetSdkVersion 23 to 24; min14 and original permissions/components unchanged",
      native_SDK_values_and_ARM64_flags_unchanged:true,registry23_focus12_unchanged:true,
      historical_greylist_behavior_qualified:false,old_install_UNKNOWN_preserved:true,old_install_nonce_reused:false,
      future_install_UID:null,future_install_nonce:null,bypass_or_testOnly_added:false,feature_default_zero_unchanged:true,
      Main_or_Android_actions:0,Python_or_build_executed:false,Root_only_dispatch:true,request_key:req.idempotency_key}};
}
