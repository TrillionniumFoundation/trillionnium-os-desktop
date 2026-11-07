function deriveAPK05(U,I){
 function need(v,m){if(!v)throw Error(m);}
 function pin(s){const b=U.utf8(s);return{bytes:b.length,sha256:U.sha256(b),git_blob_sha:U.gitBlob(b)};}
 const expected={
  template:[84406,"9c27ff74141e6bb1e39ea027acdbafb9a1d17ffa4db87c6b41f2b4355074a519","3a0fa2e766e2674027fa1c55880f777921d16c4d"],
  config:[380712,"cae37d2a4432205af5d979482d72cde4532a1cedcc7fa039843272512c9cb5b2","68b7cb3417046f4a938b2c43264c006a428f7aa7"],
  build:[465074,"61d25aeddde8832265055422bf38d0457eb60ed9db093142bfc3d157f1dd7dc5","ffa95ef00e6667513cde1136573789d752ba480c"],
  request:[470304,"d6ce059d74fbd9d7bce54482de9a287cce9df1b67ac077aa0720ea08d1673d66","7a79e9560062dcd703b5567f5d988db452f4a25f"],
  failed04:[38359,"d1bb6a63340810e6fbabe61ebeefd4df9026acd51a1ec65542967dd3c76bcdc0","54c5016fdd9610ba72be9264330f59ea1cc6a31b"]
 };
 for(const[k,p]of Object.entries(expected)){const a=pin(I[k]);need(a.bytes===p[0]&&a.sha256===p[1]&&a.git_blob_sha===p[2],"exact original "+k);}
 function one(s,a,b){need(s.split(a).length===2,"unique replacement "+a);return s.replace(a,b);}
 const A="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
 function enc(b){need(b instanceof Uint8Array,"base64 UTF8 bytes");let s="";for(let i=0;i<b.length;i+=3){const n=b[i]*65536+(b[i+1]||0)*256+(b[i+2]||0);s+=A[n>>>18]+A[(n>>>12)&63]+(i+1<b.length?A[(n>>>6)&63]:"=")+(i+2<b.length?A[n&63]:"=");}return s;}
 function dec(s){need(s.length%4===0&&/^[A-Za-z0-9+/]*={0,2}$/.test(s),"base64 shape");const o=[];for(let i=0;i<s.length;i+=4){const c=s.slice(i,i+4),v=[...c].map(x=>x==="="?0:A.indexOf(x));need(v.every(x=>x>=0),"base64 alphabet");const n=v[0]*262144+v[1]*4096+v[2]*64+v[3];o.push((n>>>16)&255);if(c[2]!=="=")o.push((n>>>8)&255);if(c[3]!=="=")o.push(n&255);}const b=Uint8Array.from(o);need(enc(b)===s,"base64 canonical");return b;}
 function ascii(b){need(b.every(x=>x<128),"ASCII source");return Array.from(b,x=>String.fromCharCode(x)).join("");}
 function parse(s){return JSON.parse(s,(k,v,c)=>typeof v==="number"?JSON.rawJSON(c.source):v);}
 function quote(s){return JSON.stringify(s).replace(/[\u007f-\uffff]/g,c=>"\\u"+c.charCodeAt(0).toString(16).padStart(4,"0"));}
 function emit(v,n=0){if(JSON.isRawJSON(v))return v.rawJSON;if(v===null)return"null";if(typeof v==="string")return quote(v);if(typeof v==="number"||typeof v==="boolean")return JSON.stringify(v);const p=" ".repeat(n+2),e=" ".repeat(n);if(Array.isArray(v))return v.length?"[\n"+v.map(x=>p+emit(x,n+2)).join(",\n")+"\n"+e+"]":"[]";need(typeof v==="object","JSON type");const ks=Object.keys(v).sort();return ks.length?"{\n"+ks.map(k=>p+quote(k)+": "+emit(v[k],n+2)).join(",\n")+"\n"+e+"}":"{}";}
 const stringify=v=>emit(v)+"\n";
 const oldC=parse(I.config),oldQ=parse(I.request);
 need(stringify(oldC)===I.config&&stringify(oldQ)===I.request,"lossless original serialization");
 const slot="CFG = None  # The immutable packet generator fills this exactly once.";
 const render=(t,c)=>one(t,slot,"CFG = json.loads(r'''"+c+"''')");
 need(render(I.template,I.config)===I.build&&oldQ.stdin===I.build,"actual04 source render join");
 const actual=JSON.parse(I.failed04);
 need(actual.success===false&&actual.kind==="p4-marriott-real-arm64-ndk-apk-build04"&&
      actual.commands.length===0&&actual.errors.length===1&&actual.errors[0].stage==="build"&&
      actual.errors[0].error==="RuntimeError('original thirteen input scope/bound differs')",
      "preserved actual04 source binding failure");
 const root04="/home/alex/work/pocket4-marriott-real-arm64-ndk-apk-04-20261106";
 const root03=root04.replace("-04-","-03-"),root05=root04.replace("-04-","-05-");
 const oldObserver=ascii(dec(oldC.apk13_observer.base64));
 need(pin(oldObserver).bytes===21569&&pin(oldObserver).sha256==="73bf1862ac8a5c18c9aed8e97bd93b70a177e623aae1cd28c71ea541447be567","exact embedded observer source");
 function specs(s){const hits=[...s.matchAll(/^INPUTS = json\.loads\(r'''([^\n]*)'''\)$/gm)];need(hits.length===1,"one literal observer INPUTS");const value=JSON.parse(hits[0][1]);need(Array.isArray(value)&&value.length===13&&new Set(value.map(x=>x.role)).size===13,"closed13 INPUTS");return value;}
 const normal=v=>JSON.stringify(v,(k,x)=>x&&typeof x==="object"&&!Array.isArray(x)?Object.fromEntries(Object.entries(x).sort(([a],[b])=>a<b?-1:a>b?1:0)):x);
 const beforeSpecs=specs(oldObserver),oldPublic=JSON.parse(I.config).apk_input_specifications;
 need(normal(beforeSpecs)!==normal(oldPublic),"actual04 mismatch must remain reproduced");
 const mismatched=[];for(let i=0;i<13;i++)if(normal(beforeSpecs[i])!==normal(oldPublic[i]))mismatched.push(i);
 need(JSON.stringify(mismatched)==="[7,8,9]","only three original mismatches");
 for(const i of mismatched){const x={...beforeSpecs[i],path:beforeSpecs[i].path.replace(root03,root04)};need(normal(x)===normal(oldPublic[i]),"only own source root mismatch");}
 need(oldObserver.split(root03).length===4,"three observer own root occurrences");
 const observer=oldObserver.split(root03).join(root05);
 need(observer.split(root05).length===4&&observer.split(root05).join(root03)===oldObserver,"observer byte inverse");
 need(observer.includes("MAX_TOTAL = 230686720\n")&&observer.includes("WORK_END = START + 40.0\n")&&observer.includes("END = START + 45.0\n"),"original fixed limits preserved");
 let template=one(I.template,"p4-marriott-real-arm64-ndk-apk-build04","p4-marriott-real-arm64-ndk-apk-build05");
 template=one(template,root04,root05);
 let cfgRaw=one(I.config,'"kind": "p4-marriott-real-arm64-ndk-apk-build04"','"kind": "p4-marriott-real-arm64-ndk-apk-build05"');
 need(cfgRaw.split(root04).length===5,"four fixed outer root occurrences");cfgRaw=cfgRaw.split(root04).join(root05);
 const cfg=parse(cfgRaw),observerPin=pin(observer);
 cfg.apk13_observer={...cfg.apk13_observer,base64:enc(U.utf8(observer)),bytes:observerPin.bytes,sha256:observerPin.sha256};
 cfgRaw=stringify(cfg);
 const decodedAgain=ascii(dec(JSON.parse(cfgRaw).apk13_observer.base64));
 need(decodedAgain===observer,"observer byte base64 equality");
 const afterSpecs=specs(decodedAgain),afterPublic=JSON.parse(cfgRaw).apk_input_specifications;
 need(normal(afterSpecs)===normal(afterPublic),"all13 embedded INPUTS must equal all13 outer specifications");
 const restore=parse(cfgRaw);restore.kind=oldC.kind;restore.root=oldC.root;restore.apk13_observer=oldC.apk13_observer;
 for(const i of [7,8,9])restore.apk_input_specifications[i].path=oldC.apk_input_specifications[i].path;
 need(stringify(restore)===I.config,"config complete inverse");
 need(one(one(template,root05,root04),"p4-marriott-real-arm64-ndk-apk-build05","p4-marriott-real-arm64-ndk-apk-build04")===I.template,"template complete inverse");
 const build=render(template,cfgRaw),q=parse(I.request);q.stdin=build;q.idempotency_key="p4-marriott-real-arm64-ndk-apk-build05-"+pin(build).sha256.slice(0,16);
 const request=stringify(q),restoreQ=parse(request);restoreQ.stdin=oldQ.stdin;restoreQ.idempotency_key=oldQ.idempotency_key;
 need(stringify(restoreQ)===I.request,"request complete inverse");
 return{template,config:cfgRaw,build,request,observer,baseline_observer:oldObserver,
 proof:{schema:1,state:"SOURCE_AND_ACTUAL_INPUTS_BOUND_UNRUN",inputs:expected,
 outputs:{template:pin(template),config:pin(cfgRaw),build:pin(build),request:pin(request),observer:pin(observer)},
 actual04_mismatch_reproduced_at_only_indices:mismatched,all13_embedded_outer_specifications_exact:true,
 observer_only_three_fixed_paths_changed:true,observer_all_functions_limits_and_historical_kind_literal_unchanged:true,
 all16_native_Java_manifest_sources_exact04:true,targetSdk24_min14_unchanged:true,
 registry23_focus12_and50commands_unchanged:true,SDK_tool_resource_FD_child_guards_unchanged:true,
 failed04_commands0_preserved:true,failed_install_UNKNOWN_preserved:true,new_APK_UID_signature_and_nonce:null,
 Python_or_remote_controls_executed:false,Main_Android_actions:0,Root_only_dispatch:true,request_key:q.idempotency_key}};
}
