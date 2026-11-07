function bindIHG877IndependentRetirement02(material,h){
 const expected={"inputs":{"bytes":18382,"sha256":"72e1dad8443b91ea32a1cd186d23287693de06f4255e4583904cbc0e8c0e4ca3"},"controller":{"bytes":60788,"sha256":"f7144a719220248318dacab1062c12514b0fedb9d75438d0e8d790b86f3c2321"},"context":{"bytes":10020,"sha256":"5aa84393992f76ef04f781dcbb141a9f1cf84d544f9556d89055921d934a9fd3"},"historical":{"bytes":27352,"sha256":"01efab63ac15390b9a67863ba80eb489e4f2961e47fc00bc0e1a6f6a73bbec2d"},"priorRequest":{"bytes":103629,"sha256":"b18fe0f952e652dd5f0b576ced7615531f4b9be5f6fd3a801ea032ad3d553620"}};
 function require(x,code){if(!x)throw Error(code);}
 function pinned(name){const raw=material[name];require(typeof raw==="string","MISSING_"+name);
  require(h.utf8(raw).length===expected[name].bytes&&h.sha(raw)===expected[name].sha256,"PIN_"+name);return raw;}
 const inputs=pinned("inputs"),controller=pinned("controller"),context=pinned("context"),historical=pinned("historical");
 const prior=JSON.parse(pinned("priorRequest"));
 const parsed=JSON.parse(inputs);
 require(parsed.schema==="pocket4-independent-current-IHG877-retirement-input-v1"&&parsed.task===877&&
  parsed.native_reported_task_id===null&&parsed.original_launch_outcome==="unknown_retained"&&
  parsed.current_retirement02_baseline.schema==="pocket4-independent-current-IHG877-retirement02-baseline-v1"&&
  JSON.stringify(parsed.current_retirement02_baseline.current_tasks)==="[875,877,878]"&&
  JSON.stringify(parsed.current_retirement02_baseline.preserved_current_tasks)==="[875,878]","INDEPENDENT_SCOPE_INPUTS");
 const source="INPUTS=json.loads("+JSON.stringify(inputs)+")\n"+
  "HISTORICAL_PARSER_SOURCE="+JSON.stringify(historical)+"\n"+
  "HISTORICAL_PARSER_PIN="+JSON.stringify(expected.historical)+"\n"+
  "OWNED_CONTEXT_SOURCE="+JSON.stringify(context)+"\n"+
  "OWNED_CONTEXT_PIN="+JSON.stringify(expected.context)+"\n";
 // Python imports must precede the literal INPUTS=json.loads statement.
 const complete="import json\n"+source+"\n"+controller;
 const bytes=h.utf8(complete).length,digest=h.sha(complete);
 require(bytes>0&&bytes<=131072,"SOURCE_BOUND");
 require(prior.host==="pocket4"&&prior.executable==="/usr/bin/sudo"&&prior.cwd==="/home/alex/work"&&
  JSON.stringify(prior.env)===JSON.stringify({PYTHONDONTWRITEBYTECODE:"1"})&&prior.args[0]==="-n"&&
  prior.args[1]==="/usr/bin/python3","EXACT_PRIOR_ENVELOPE");
 const bootstrap="import sys,hashlib;raw=sys.stdin.buffer.read(131073);assert len(raw)=="+bytes+
  " and hashlib.sha256(raw).hexdigest()=="+JSON.stringify(digest)+
  ";scope={'__name__':'fixed_independent_current_IHG877_retirement02','__file__':'<verified-independent-current-IHG877-retirement02>'};"+
  "exec(compile(raw,scope['__file__'],'exec'),scope);raise SystemExit(scope['run']("+JSON.stringify(digest)+"))";
 const request={...prior,args:["-n","/usr/bin/python3","-I","-B","-c",bootstrap],
  stdin:complete,timeout_seconds:240,memory_max_bytes:536870912,
  idempotency_key:"pocket4-ihg-r4-london877-current-Android-leaf-retirement02-20261106"};
 require(request.cpu_quota_percent===100&&request.nice===10,"UNCHANGED_CPU_NICE");
 return {source:complete,request,requestRaw:JSON.stringify(request,null,2)+"\n",
  sourcePin:{bytes,sha256:digest},inputPins:expected};
}
