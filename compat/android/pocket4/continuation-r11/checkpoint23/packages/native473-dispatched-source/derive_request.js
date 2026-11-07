function(H,input,compiler,proofRaw){
 const require=(v,m)=>{if(!v)throw new Error(m)};
 const pin=s=>{const b=H.utf8(s);return{bytes:b.length,sha256:H.sha256(b),git_blob_sha1:H.gitBlob(b)}},small=s=>{const p=pin(s);return{bytes:p.bytes,sha256:p.sha256}};
 const root="/home/alex/work/pocket4-native-typed-ingress-builder473-audiocontrol-example-projection-compile-01-20261106",parentRoot="/home/alex/work/pocket4-native-typed-ingress-builder471-systemui-test-projection-compile-01-20261106";
 const sourceFiles={"compile_builder.py":compiler,"expected-builder473-manifest.json":input.manifest,"audiocontrol-example-projection-proof.json":proofRaw,"delta/tools/droidloom-update/src/android.rs":input.android,"delta/android/native-role-ingress/provider-fixtures/audiocontrol-example.Android.bp":input.consumer};
 const transferred=Object.fromEntries(Object.entries(sourceFiles).map(([p,s])=>[p,small(s)]));
 let stage=input.baseline_stage;const stageEdits=[];
 function line(name,newValue){const re=new RegExp("^"+name+"=(.*)$","m"),m=stage.match(re);require(!!m,name);const old=m[0],neu=name+"="+newValue;require(stage.split(old).length===2,"once "+name);stageEdits.push({old,new:neu});stage=stage.replace(old,neu);}
 const oldReuse=JSON.parse(stage.match(/^REUSED_AUTHORITY=(.*)$/m)[1]),reused={};
 for(const[k,v]of Object.entries(oldReuse))if(!k.startsWith("compiled-parent470-"))reused[k]=v;
 reused["compiled-parent471-manifest.json"]={path:parentRoot+"/attempt01/copied-builder-source-manifest.json",bytes:pin(input.baseline_manifest).bytes,sha256:pin(input.baseline_manifest).sha256,mode:384};
 reused["compiled-parent471-result.json"]={path:parentRoot+"/attempt01/result.json",bytes:pin(input.actual471).bytes,sha256:pin(input.actual471).sha256,mode:384};
 require(Object.keys(reused).length===11,"11 authorities");
 const expected={...transferred,...Object.fromEntries(Object.entries(reused).map(([k,v])=>[k,{bytes:v.bytes,sha256:v.sha256}]))};
 line("ROOT","Path("+JSON.stringify(root)+")");line("TRANSFERRED",JSON.stringify(transferred));line("REUSED_AUTHORITY",JSON.stringify(reused));line("EXPECTED",JSON.stringify(expected));
 let inverse=stage;for(const e of stageEdits.toReversed()){require(inverse.split(e.new).length===2,"inverse stage unique");inverse=inverse.replace(e.new,e.old);}require(inverse===input.baseline_stage,"whole stage inverse");
 const stdin=JSON.stringify({schema:1,stage,packet:sourceFiles});require(pin(stdin).bytes<=1048576,"tool stdin max");
 let transport=input.baseline_transport;const transportEdits=[];
 for(const[name,val]of [["EXPECTED",small(stdin)],["STAGE",small(stage)]]){const old=transport.match(new RegExp("^"+name+"=(.*)$","m"))[0],neu=name+"="+JSON.stringify(val);transportEdits.push({old,new:neu});transport=transport.replace(old,neu);}
 inverse=transport;for(const e of transportEdits.toReversed())inverse=inverse.replace(e.new,e.old);require(inverse===input.baseline_transport,"whole transport inverse");
 const key=root.slice(root.lastIndexOf("/")+1),requestObject={host:"pocket4",executable:"/usr/bin/python3",args:["-I","-B","-c",transport],stdin,cwd:"/",cpu_quota_percent:100,memory_max_bytes:1073741824,nice:15,timeout_seconds:600,idempotency_key:key},request=JSON.stringify(requestObject,null,2)+"\n";
 let generator=input.baseline_generator;const generatorEdits=[];
 const values={FILE_ORDER:Object.keys(sourceFiles),EXPECTED:transferred,STAGE:small(stage),WIRE:small(stdin),REQUEST:small(request),BOUNDARY:transport,BASE:{host:"pocket4",executable:"/usr/bin/python3",cwd:"/",cpu_quota_percent:100,memory_max_bytes:1073741824,nice:15,timeout_seconds:600,idempotency_key:key}};
 for(const[k,v]of Object.entries(values)){const re=new RegExp("^const "+k+" = .*;$","m"),m=generator.match(re);require(!!m,"generator constant "+k);const neu="const "+k+" = "+JSON.stringify(v)+";";generatorEdits.push({old:m[0],new:neu});generator=generator.replace(m[0],neu);}
 inverse=generator;for(const e of generatorEdits.toReversed()){require(inverse.split(e.new).length===2,"generator inverse");inverse=inverse.replace(e.new,e.old);}require(inverse===input.baseline_generator,"whole generator inverse");
 const result=Function(generator+"\nreturn generate;")()(sourceFiles,stage,H);
 require(result.request===request&&result.stdin===stdin,"full exact request reproduction");
 require(JSON.parse(request).args[2]==="-c"&&JSON.parse(request).args[3]===transport,"fixed boundary");
 return{root,key,sourceFiles,transferred,reused,expected,stage,stageEdits,transport,transportEdits,generator,generatorEdits,request,requestObject,stdin,pins:{stage:pin(stage),transport:pin(transport),request:pin(request),stdin:pin(stdin),generator:pin(generator)},all_reproduced:true};
}
