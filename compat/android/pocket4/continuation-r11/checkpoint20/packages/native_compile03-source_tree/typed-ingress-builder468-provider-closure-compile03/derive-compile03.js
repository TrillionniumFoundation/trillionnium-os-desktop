function deriveCompile03(baselineRequestText,H) {
  const assert=(ok,msg)=>{if(!ok)throw new Error(msg);};
  const pin=text=>{const b=H.utf8(text);return {bytes:b.length,sha256:H.sha256(b),git_blob_sha1:H.gitBlob(b)};};
  const compact=p=>({bytes:p.bytes,sha256:p.sha256});
  const json=x=>JSON.stringify(x,null,2)+"\n";
  const count=(s,x)=>s.split(x).length-1;
  const replaceExact=(s,oldValue,newValue,n,label)=>{
    assert(count(s,oldValue)===n,label+" original occurrence count");
    const result=s.split(oldValue).join(newValue);
    assert(count(result,newValue)===n,label+" replacement occurrence count");
    assert(result.split(newValue).join(oldValue)===s,label+" exact inverse");
    return result;
  };
  function diffEqualLineCount(a,b,name) {
    assert(a.endsWith("\n")&&b.endsWith("\n"),"diff final newline");
    const x=a.slice(0,-1).split("\n"),y=b.slice(0,-1).split("\n");
    assert(x.length===y.length,"fixed replacement changed line count");
    const changed=[];for(let i=0;i<x.length;i++)if(x[i]!==y[i])changed.push(i);
    const groups=[];for(const i of changed){const lo=Math.max(0,i-3),hi=Math.min(x.length,i+4);const g=groups[groups.length-1];if(g&&lo<=g[1])g[1]=Math.max(hi,g[1]);else groups.push([lo,hi]);}
    let out="--- a/"+name+"\n+++ b/"+name+"\n";
    for(const [lo,hi] of groups){
      out+="@@ -"+(lo+1)+","+(hi-lo)+" +"+(lo+1)+","+(hi-lo)+" @@\n";
      for(let i=lo;i<hi;i++)out+=(x[i]===y[i]?" "+x[i]+"\n":"-"+x[i]+"\n+"+y[i]+"\n");
    }
    return {source:out,changed_lines:changed.map(i=>i+1),old_lines:x.length,new_lines:y.length};
  }
  const bp=pin(baselineRequestText);
  assert(bp.bytes===967650&&bp.sha256==="a6cc57696e19799531e47a2424313ac784ccb66a850a9da3ef25c178c3cef3f5"&&bp.git_blob_sha1==="247dd531f86374434a65c883b4129d4fed1e9a82","baseline request pin");
  const original=JSON.parse(baselineRequestText),wire02=JSON.parse(original.stdin);
  assert(JSON.stringify(Object.keys(wire02))===JSON.stringify(["schema","stage","packet"])&&wire02.schema===1,"baseline wire shape");
  assert(JSON.stringify(original,null,2)+"\n"===baselineRequestText,"baseline exact request serialization");
  assert(JSON.stringify(wire02)+"\n"===original.stdin,"baseline exact wire serialization");
  const wrapper02=original.args[3];
  assert(JSON.stringify(original.args.slice(0,3))===JSON.stringify(["-I","-B","-c"]),"original interpreter arguments");
  const parseLine=(source,name)=>{const matches=source.split("\n").filter(x=>x.startsWith(name+"="));assert(matches.length===1,"unique "+name);return JSON.parse(matches[0].slice(name.length+1));};
  const oldWirePin=pin(original.stdin),oldStagePin=pin(wire02.stage),oldCompilerPin=pin(wire02.packet["compile_builder.py"]);
  assert(oldWirePin.bytes===886381&&oldWirePin.sha256==="8834f2105f458bd33c5495e773f4c56ecc414b5043e74dd6f25732a4dfbbb3cb","baseline stdin");
  assert(oldStagePin.bytes===19294&&oldStagePin.sha256==="ed08b24d94e0f40f0888ccfca203ad7a63914cc19f8b9d0d1a678fce33db5603","baseline stage");
  assert(oldCompilerPin.bytes===83274&&oldCompilerPin.sha256==="e4a86b026e6c73891503c4556244a5caaed1c7bbb70cb0e19b7081f926ea420a","baseline compiler");
  assert(JSON.stringify(parseLine(wrapper02,"EXPECTED"))===JSON.stringify(compact(oldWirePin)),"baseline wrapper wire");
  assert(JSON.stringify(parseLine(wrapper02,"STAGE"))===JSON.stringify(compact(oldStagePin)),"baseline wrapper stage");
  const transfer02=parseLine(wire02.stage,"TRANSFERRED"),authority02=parseLine(wire02.stage,"REUSED_AUTHORITY"),expected02=parseLine(wire02.stage,"EXPECTED");
  assert(Object.keys(wire02.packet).length===30&&Object.keys(transfer02).length===30&&Object.keys(authority02).length===11&&Object.keys(expected02).length===41,"fixed member counts");
  assert(JSON.stringify(Object.keys(wire02.packet))===JSON.stringify(Object.keys(transfer02)),"original packet order");
  for(const [name,body]of Object.entries(wire02.packet)){
    assert(typeof body==="string","packet text");
    assert(JSON.stringify(compact(pin(body)))===JSON.stringify(transfer02[name]),"original transfer pin "+name);
    assert(JSON.stringify(transfer02[name])===JSON.stringify(expected02[name]),"original expected transfer "+name);
  }
  for(const [name,a]of Object.entries(authority02)){
    assert(!Object.hasOwn(wire02.packet,name),"authority also transferred");
    assert(JSON.stringify({bytes:a.bytes,sha256:a.sha256})===JSON.stringify(expected02[name]),"original authority pin "+name);
  }
  const oldKey="pocket4-native-typed-ingress-builder468-provider-closure-compile-02-20261106";
  const newKey="pocket4-native-typed-ingress-builder468-provider-closure-compile-03-20261106";
  const oldRoot="/home/alex/work/"+oldKey,newRoot="/home/alex/work/"+newKey;
  assert(original.idempotency_key===oldKey,"baseline key");
  const oldCompiler=wire02.packet["compile_builder.py"];
  const edits=[
    {label:"fresh owned root",old:oldRoot,new:newRoot,count:1},
    {label:"accurate attempt scope",old:"provider closure compile02, 491 source files",new:"provider closure compile03, 491 source files",count:1},
    {label:"remove hard-coded HOME",old:"'PATH':'/usr/bin:/bin','HOME':'/home/alex','CARGO_HOME':str(CARGO_HOME)",new:"'PATH':'/usr/bin:/bin','CARGO_HOME':str(CARGO_HOME)",count:1}
  ];
  let compiler=oldCompiler;
  for(const e of edits)compiler=replaceExact(compiler,e.old,e.new,e.count,e.label);
  assert(!compiler.includes("'HOME'")&&!compiler.includes('"HOME"'),"no HOME setting in candidate compiler");
  assert(compiler.includes("CARGO_HOME = Path('/home/alex/.cargo')"),"fixed CARGO_HOME retained");
  let inverse=compiler;
  for(const e of [...edits].reverse())inverse=replaceExact(inverse,e.new,e.old,e.count,"inverse "+e.label);
  assert(inverse===oldCompiler,"compiler whole inverse");
  const compilerPin=pin(compiler),packet={...wire02.packet,"compile_builder.py":compiler};
  const transfer={...transfer02,"compile_builder.py":compact(compilerPin)};
  const expected={...expected02,"compile_builder.py":compact(compilerPin)};
  let stage=replaceExact(wire02.stage,oldRoot,newRoot,1,"stage fresh root");
  stage=replaceExact(stage,"TRANSFERRED="+JSON.stringify(transfer02),"TRANSFERRED="+JSON.stringify(transfer),1,"stage transfer compiler pin");
  stage=replaceExact(stage,"EXPECTED="+JSON.stringify(expected02),"EXPECTED="+JSON.stringify(expected),1,"stage complete compiler pin");
  assert(JSON.stringify(parseLine(stage,"REUSED_AUTHORITY"))===JSON.stringify(authority02),"11 authority bindings unchanged");
  let stageInverse=stage;
  stageInverse=replaceExact(stageInverse,"EXPECTED="+JSON.stringify(expected),"EXPECTED="+JSON.stringify(expected02),1,"inverse expected");
  stageInverse=replaceExact(stageInverse,"TRANSFERRED="+JSON.stringify(transfer),"TRANSFERRED="+JSON.stringify(transfer02),1,"inverse transfer");
  stageInverse=replaceExact(stageInverse,newRoot,oldRoot,1,"inverse stage root");
  assert(stageInverse===wire02.stage,"stage whole inverse");
  const stagePin=pin(stage),wire=JSON.stringify({schema:1,stage,packet})+"\n",wirePin=pin(wire);
  assert(wirePin.bytes<=1048576,"tool stdin one MiB limit");
  let wrapper=replaceExact(wrapper02,"EXPECTED="+JSON.stringify(compact(oldWirePin)),"EXPECTED="+JSON.stringify(compact(wirePin)),1,"wrapper wire binding");
  wrapper=replaceExact(wrapper,"STAGE="+JSON.stringify(compact(oldStagePin)),"STAGE="+JSON.stringify(compact(stagePin)),1,"wrapper stage binding");
  let wrapperInverse=wrapper;
  wrapperInverse=replaceExact(wrapperInverse,"STAGE="+JSON.stringify(compact(stagePin)),"STAGE="+JSON.stringify(compact(oldStagePin)),1,"inverse wrapper stage");
  wrapperInverse=replaceExact(wrapperInverse,"EXPECTED="+JSON.stringify(compact(wirePin)),"EXPECTED="+JSON.stringify(compact(oldWirePin)),1,"inverse wrapper wire");
  assert(wrapperInverse===wrapper02,"wrapper whole inverse");
  const req={...original,args:[...original.args.slice(0,3),wrapper],stdin:wire,idempotency_key:newKey};
  const request=json(req),requestPin=pin(request);
  const normalized={...req,args:original.args,stdin:original.stdin,idempotency_key:original.idempotency_key};
  assert(json(normalized)===baselineRequestText,"all request fields except three bindings exact");
  const unchanged=[];
  for(const name of Object.keys(packet)){
    const p=pin(packet[name]);
    assert(JSON.stringify(compact(p))===JSON.stringify(transfer[name]),"new transfer pin "+name);
    assert(JSON.stringify(transfer[name])===JSON.stringify(expected[name]),"new expected pin "+name);
    if(name!=="compile_builder.py"){assert(packet[name]===wire02.packet[name],"source changed "+name);unchanged.push({path:name,...p});}
  }
  assert(unchanged.length===29,"29 unchanged packet sources");
  assert(JSON.parse(packet["expected-builder468-manifest.json"])&&Object.keys(JSON.parse(packet["expected-builder468-manifest.json"])).length===491,"source map count");
  const diffs={compiler:diffEqualLineCount(oldCompiler,compiler,"compile_builder.py"),stage:diffEqualLineCount(wire02.stage,stage,"stage.py"),transport:diffEqualLineCount(wrapper02,wrapper,"transport-boundary.py")};
  return {oldRoot,newRoot,oldKey,newKey,compiler,compilerPin,packet,transfer,authorities:authority02,expected,stage,stagePin,wire,wirePin,wrapper,wrapperPin:pin(wrapper),req,request,requestPin,diffs,edits,unchanged,oldPins:{request:bp,stdin:oldWirePin,compiler:oldCompilerPin,stage:oldStagePin,wrapper:pin(wrapper02)},inverse_checks:{compiler:true,stage:true,wrapper:true,request:true},all_29_noncompiler_packet_sources_identical:true,authority_count:11,transferred_count:30,complete_count:41,source_files:491,expected_commands:62,expected_gates:24,python_compiled:false,Rust_compiled:false,Soong_executed:false,Main_Android_actions:0};
}
