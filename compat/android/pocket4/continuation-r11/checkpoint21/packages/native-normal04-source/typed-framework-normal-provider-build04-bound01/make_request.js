"use strict";
// Reproduce only this frozen normal request. No I/O, Git, network, or execution.
const FILE_ORDER = ["main_snapshot.py","frozen-work-inventory.py","actual-work-preparation.json","expected-builder469-manifest.json","prior-framework-inner-terminal.json","prior-framework-outer-terminal.json","actual-published-source-manifest.json","actual-native-prebuilt-Android.bp","actual-hal-provider-source-lock.json","framework_build.py","fenced_build.py","actual-builder469-result.json","pure_controls.py","capture_lifecycle.py","root_snapshot_supervisor.py","prior-normal02-outer-terminal.json","actual-resource-observation01.json"];
const EXPECTED = {"main_snapshot.py":{"bytes":14294,"sha256":"1fd614b6e7b4900feff1a114c0cd221a1fb00fc0cea9878db1f3ae5672d561cf"},"frozen-work-inventory.py":{"bytes":48443,"sha256":"203dd7f4efdac01891a4c31fd79f2eb3204e3c8c2be5702988f0875307cce9ab"},"actual-work-preparation.json":{"bytes":11091,"sha256":"ab286f3939acfeb648a716ca15e5df348fef6b7007eb5651735fe8a7bda96b1c"},"expected-builder469-manifest.json":{"bytes":99327,"sha256":"88dc3c8020c436009862800ffdc5af97f50f6ae7efff832562c2784d66794701"},"prior-framework-inner-terminal.json":{"bytes":5239,"sha256":"6a525b9838f43579bc41b1106891f2f734a0c2d92b0c5cc355f7ab02b39eb2a8"},"prior-framework-outer-terminal.json":{"bytes":24689,"sha256":"273ba8a236253ee3873074a26f568144397044ebcfdd6f153ab8712b29ff70cf"},"actual-published-source-manifest.json":{"bytes":108555,"sha256":"afb23d210fda970a09482a14b9b38af1c92b5be505edd0eda2b76ce5ffc6067f"},"actual-native-prebuilt-Android.bp":{"bytes":1017,"sha256":"d1eca99403572ee9d481e777febac8d4e062f44fd8844285ffc452b17beb531a"},"actual-hal-provider-source-lock.json":{"bytes":96934,"sha256":"c7154e445c2bf1a4539418c68a04731538f9ac11050132571b911e706084f8fd"},"framework_build.py":{"bytes":62492,"sha256":"73184ded80fbc33238713a47f4a4fa81e442b1e72d1cb464bd716529c410d227"},"fenced_build.py":{"bytes":25481,"sha256":"b293ae22809eaa9c02482d1383bcb0c7c702604757d798be2f50aff12db44e7e"},"actual-builder469-result.json":{"bytes":170316,"sha256":"3636057b9a20fc895657064da3fb66d8ded7e69ebfa5a5b92072a51b33f29fd5"},"pure_controls.py":{"bytes":10970,"sha256":"f9f29b3b31c06967657b02efb291f3c31ab80e3ba77e197733be63bd81c60647"},"capture_lifecycle.py":{"bytes":25227,"sha256":"4ffc5a7d6a54ad2cd4351ef30f90a12143614206953e97219f3d6cf5c6e1fc28"},"root_snapshot_supervisor.py":{"bytes":12041,"sha256":"f493a324cb5694f618d0fed3d5ed17ff90aa64924b671ea99550622f6090b5b7"},"prior-normal02-outer-terminal.json":{"bytes":24722,"sha256":"42b2d7b8749047df9e1d40ddf9b70b3f3e187c39ce6a15dd0f5721610e814c00"},"actual-resource-observation01.json":{"bytes":399,"sha256":"feb95f82087d7c68a8c8c42b54cf267b8f9c343ce41e49bb8193e96f49f050da"}};
const STAGE = {"bytes":5448,"sha256":"99d8cfd98574507082bee004e29bff73211db711292610f6e83d54a8487f85c5"};
const WIRE = {"bytes":797035,"sha256":"6ac7b58b840da8333d2e0a14870f5b75fe89e970f57b1294e3e297dbb1d77568"};
const REQUEST = {"bytes":880329,"sha256":"1ab6ec792b013929f6780237a481c38fdf0d53400929c7f7e534d458ac63fd33"};
const BOUNDARY = "import hashlib,json,sys\nWIRE_BYTES = 797035\nWIRE_SHA256 = \"6ac7b58b840da8333d2e0a14870f5b75fe89e970f57b1294e3e297dbb1d77568\"\nSTAGE_BYTES = 5448\nSTAGE_SHA256 = \"99d8cfd98574507082bee004e29bff73211db711292610f6e83d54a8487f85c5\"\nif sys.argv[1:] != ['--execute-once']:\n    print(json.dumps({'state':'PLAN_ONLY','source_only':True,'submitted':False,'Main_actions':0,'Android_actions':0,'old_QA_epoch_invalid':True,'new_QA_epoch_qualified':False}))\n    raise SystemExit(0)\nraw=sys.stdin.buffer.read(WIRE_BYTES+1)\nif len(raw)!=WIRE_BYTES or hashlib.sha256(raw).hexdigest()!=WIRE_SHA256:\n    raise RuntimeError('normal framework exact source packet changed')\npacket=json.loads(raw.decode('utf-8','strict'))\nif set(packet)!={'schema','stage','files'} or type(packet['schema']) is not int or packet['schema']!=1:\n    raise RuntimeError('normal framework source packet shape changed')\nstage=packet['stage'].encode('utf-8')\nif len(stage)!=STAGE_BYTES or hashlib.sha256(stage).hexdigest()!=STAGE_SHA256:\n    raise RuntimeError('normal framework stage source changed')\nscope={'__name__':'frozen_normal_framework_stage','__file__':'<frozen-normal-framework-stage>'}\nexec(compile(stage,'stage.py','exec'),scope,scope)\nscope['main'](packet['files'])\n";
const BASE = {"host":"pocket4","executable":"/usr/bin/python3","cwd":"/home/alex/work","env":{"PYTHONDONTWRITEBYTECODE":"1"},"idempotency_key":"pocket4-native-typed-ingress-framework-strict-provider-two-target-build-04-20261106","timeout_seconds":6400,"cpu_quota_percent":200,"memory_max_bytes":10737418240,"nice":10};
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
