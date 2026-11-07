"use strict";
// Reproduce only this frozen normal request. No I/O, Git, network, or execution.
const FILE_ORDER = ["main_snapshot.py","frozen-work-inventory.py","actual-work-preparation.json","expected-builder468-manifest.json","prior-framework-inner-terminal.json","prior-framework-outer-terminal.json","actual-published-source-manifest.json","actual-native-prebuilt-Android.bp","actual-provider-source-lock.json","framework_build.py","fenced_build.py","actual-builder468-result.json","pure_controls.py"];
const EXPECTED = {"main_snapshot.py":{"bytes":14294,"sha256":"1fd614b6e7b4900feff1a114c0cd221a1fb00fc0cea9878db1f3ae5672d561cf"},"frozen-work-inventory.py":{"bytes":48443,"sha256":"203dd7f4efdac01891a4c31fd79f2eb3204e3c8c2be5702988f0875307cce9ab"},"actual-work-preparation.json":{"bytes":11091,"sha256":"ab286f3939acfeb648a716ca15e5df348fef6b7007eb5651735fe8a7bda96b1c"},"expected-builder468-manifest.json":{"bytes":97525,"sha256":"e06522400f746b62016f82dfd3ec913b39cd9a8f33f9bca4f61a19a2787684ee"},"prior-framework-inner-terminal.json":{"bytes":2246,"sha256":"80f3508bab1884421af6db2f6d87537fd950100be009265b7e2efabc9b97fcdc"},"prior-framework-outer-terminal.json":{"bytes":1150,"sha256":"2c36ab1cc9ff6f181855f195f9c5b7bc0f58e7fb99d9c76e4871e64b143bf059"},"actual-published-source-manifest.json":{"bytes":97784,"sha256":"73a4cc1da8371482164aab2bc149498d03f481f212bb85cb4fda22b6b10c958d"},"actual-native-prebuilt-Android.bp":{"bytes":1017,"sha256":"d1eca99403572ee9d481e777febac8d4e062f44fd8844285ffc452b17beb531a"},"actual-provider-source-lock.json":{"bytes":96322,"sha256":"5c28f77e998cb75fd04de121e43a36fc3d8515c18249930268a2ffb6e5e372f7"},"framework_build.py":{"bytes":55314,"sha256":"26c69c112f3f4a255d5e8d7c6105e956d78f0ab91c791c6acbe5f3750844cff6"},"fenced_build.py":{"bytes":10273,"sha256":"c30bb4938087b61b66995bf6c3880c192e50fdb2ed231a5c8b13eeb319c4dbd0"},"actual-builder468-result.json":{"bytes":161423,"sha256":"871e78f7ad8f3f3a12c165297e4fe566d96cfe3a2ce64a0d0010cffdb647b6b8"},"pure_controls.py":{"bytes":9573,"sha256":"5c7139c4d21181d742cd43feb272cc14cc1f837b18804e633fa8c77836100c38"}};
const STAGE = {"bytes":4733,"sha256":"d9e054b910fa8f6ad7b80ef9504e978dc490198b3129389747f427e7fc6c3319"};
const WIRE = {"bytes":653752,"sha256":"b05def30391b38aa68e71c2283a779b651255c1ea09a4888a8eb07e47a5d3b75"};
const REQUEST = {"bytes":724917,"sha256":"48669f0e461bd4b07f74e7c1f3ed1d36ee20a6afce341b09bfe9aa0500773919"};
const BOUNDARY = "import hashlib,json,sys\nWIRE_BYTES = 653752\nWIRE_SHA256 = \"b05def30391b38aa68e71c2283a779b651255c1ea09a4888a8eb07e47a5d3b75\"\nSTAGE_BYTES = 4733\nSTAGE_SHA256 = \"d9e054b910fa8f6ad7b80ef9504e978dc490198b3129389747f427e7fc6c3319\"\nif sys.argv[1:] != ['--execute-once']:\n    print(json.dumps({'state':'PLAN_ONLY','source_only':True,'submitted':False,'Main_actions':0,'Android_actions':0,'old_QA_epoch_invalid':True,'new_QA_epoch_qualified':False}))\n    raise SystemExit(0)\nraw=sys.stdin.buffer.read(WIRE_BYTES+1)\nif len(raw)!=WIRE_BYTES or hashlib.sha256(raw).hexdigest()!=WIRE_SHA256:\n    raise RuntimeError('normal framework exact source packet changed')\npacket=json.loads(raw.decode('utf-8','strict'))\nif set(packet)!={'schema','stage','files'} or type(packet['schema']) is not int or packet['schema']!=1:\n    raise RuntimeError('normal framework source packet shape changed')\nstage=packet['stage'].encode('utf-8')\nif len(stage)!=STAGE_BYTES or hashlib.sha256(stage).hexdigest()!=STAGE_SHA256:\n    raise RuntimeError('normal framework stage source changed')\nscope={'__name__':'frozen_normal_framework_stage','__file__':'<frozen-normal-framework-stage>'}\nexec(compile(stage,'stage.py','exec'),scope,scope)\nscope['main'](packet['files'])\n";
const BASE = {"host":"pocket4","executable":"/usr/bin/python3","cwd":"/home/alex/work","env":{"PYTHONDONTWRITEBYTECODE":"1"},"idempotency_key":"pocket4-native-typed-ingress-framework-strict-provider-two-target-build-01-20261106","timeout_seconds":6400,"cpu_quota_percent":200,"memory_max_bytes":10737418240,"nice":10};
function generate(inputFiles, stage, H) {
  function require(value, reason) { if (!value) throw new Error(reason); }
  function pin(value) {const b=H.utf8(value); return {bytes:b.length,sha256:H.sha256(b)};}
  function equal(a,b) {return JSON.stringify(a)===JSON.stringify(b);}
  require(equal(Object.keys(inputFiles).sort(), [...FILE_ORDER].sort()), "exact file set");
  const files={};
  for(const name of FILE_ORDER) {
    require(typeof inputFiles[name]==="string" && equal(pin(inputFiles[name]),EXPECTED[name]), "source pin: "+name);
    files[name]=inputFiles[name];
  }
  require(typeof stage==="string" && equal(pin(stage),STAGE), "stage pin");
  const wire=JSON.stringify({schema:1,stage,files})+"\n";
  require(equal(pin(wire),WIRE) && WIRE.bytes<=1024*1024, "wire pin or one MiB bound");
  const req={...BASE,args:["-I","-B","-c",BOUNDARY,"--execute-once"],stdin:wire};
  // Preserve the historical request's field order for exact serialized readback.
  const ordered={host:req.host,executable:req.executable,args:req.args,cwd:req.cwd,env:req.env,
    stdin:req.stdin,idempotency_key:req.idempotency_key,timeout_seconds:req.timeout_seconds,
    cpu_quota_percent:req.cpu_quota_percent,memory_max_bytes:req.memory_max_bytes,nice:req.nice};
  const raw=JSON.stringify(ordered,null,2)+"\n";
  require(equal(pin(raw),REQUEST), "request pin");
  return {request:raw,stdin:wire,request_object:ordered};
}
