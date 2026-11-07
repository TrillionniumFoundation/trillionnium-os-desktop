"use strict";
function makeStatusCompileRequest(inputFiles, stage, H) {
  const FILE_ORDER = ["compile_status.py","expected-status-manifest.json","build-scope.json","delta/runtime/droidloom-supervisor/src/control.rs","delta/runtime/droidloom-supervisor/src/development.rs","delta/runtime/droidloom-supervisor/src/bin/droidloomctl.rs","delta/runtime/droidloom-supervisor/tests/cli_lifecycle.rs","delta/runtime/droidloom-supervisor/src/control_status_tests.rs"];
  const EXPECTED = {"compile_status.py":{"bytes":90731,"sha256":"f836097a5fea8ca1629c9d862d0bd73102e7ecd4b853f6b692cb79ce76384b5e"},"expected-status-manifest.json":{"bytes":99958,"sha256":"d8f6213f73726bd3766645e7decb5ebfac852f49852c49545e511a54b689d16e"},"build-scope.json":{"bytes":5474,"sha256":"a5548924d139354315e4ff93bdd7a780472758c89abe41bff81aa075d9b0b2c2"},"delta/runtime/droidloom-supervisor/src/control.rs":{"bytes":71588,"sha256":"50d7bc3abd94f83233ef7d461f93cb714f843cacb3fd5c0e929d06671a95f89b"},"delta/runtime/droidloom-supervisor/src/development.rs":{"bytes":101645,"sha256":"37645978b33d443313694609625a97ac9dd7f6e14053664a48d02ff6d8daea90"},"delta/runtime/droidloom-supervisor/src/bin/droidloomctl.rs":{"bytes":20606,"sha256":"3733dd7586ebf534aef3d4a5d176a76b8822dd0c6a6b8b39fb64adf8e70cd484"},"delta/runtime/droidloom-supervisor/tests/cli_lifecycle.rs":{"bytes":11717,"sha256":"5310bfdb21b006ae1432b584c03fbbfb4c1f3a7cbd3ce226b54770ff4bbca317"},"delta/runtime/droidloom-supervisor/src/control_status_tests.rs":{"bytes":11843,"sha256":"0bafad33112df280c73ceedf675305236275bb043d0909fc4a71f6366c0a6727"}};
  const STAGE = {"bytes":9483,"sha256":"d2968e7d2337ede050a7d95b8528b3a1a3f8cad2c103891e0f4c0940f7ab5b5f"};
  const WIRE = {"bytes":444342,"sha256":"ba58dc5a921e413c2c59bf6eb77577590a154342af95fd3b2fb04d7e8aa3ed6c"};
  const REQUEST = {"bytes":476954,"sha256":"7505b58ec2c17765a5b7832edd161091a9c400f4aa6ef8f8073f09f93b8ba722"};
  const BOUNDARY = "import hashlib,json,sys\nEXPECTED={\"bytes\":444342,\"sha256\":\"ba58dc5a921e413c2c59bf6eb77577590a154342af95fd3b2fb04d7e8aa3ed6c\"}\nSTAGE={\"bytes\":9483,\"sha256\":\"d2968e7d2337ede050a7d95b8528b3a1a3f8cad2c103891e0f4c0940f7ab5b5f\"}\nwire=sys.stdin.buffer.read(EXPECTED['bytes']+1)\nif len(wire)!=EXPECTED['bytes'] or hashlib.sha256(wire).hexdigest()!=EXPECTED['sha256']:\n    raise RuntimeError('fixed provider compiler transport length/hash mismatch')\nvalue=json.loads(wire)\nif type(value) is not dict or set(value)!={'schema','stage','packet'} or value['schema']!=1 or type(value['stage']) is not str:\n    raise RuntimeError('fixed provider compiler envelope differs')\nstage=value['stage'].encode('utf-8')\nif len(stage)!=STAGE['bytes'] or hashlib.sha256(stage).hexdigest()!=STAGE['sha256']:\n    raise RuntimeError('fixed provider compiler stage pin differs')\nscope={'__name__':'__stage__','__file__':'<fixed-provider-stage>'}\nexec(compile(stage,'<fixed-provider-stage>','exec'),scope,scope)\nscope['main'](value['packet'])\n";
  function need(value, message) { if (!value) throw new Error(message); }
  function pin(value) { return {bytes:H.utf8(value).length,sha256:H.sha(value)}; }
  function same(left,right) { return JSON.stringify(left) === JSON.stringify(right); }
  need(same(Object.keys(inputFiles).sort(), [...FILE_ORDER].sort()), "exact source members");
  const packet={};
  for(const name of FILE_ORDER) {
    need(typeof inputFiles[name]==="string" && same(pin(inputFiles[name]), EXPECTED[name]), "source pin: "+name);
    packet[name]=inputFiles[name];
  }
  need(same(pin(stage),STAGE),"exact stage");
  const stdin=JSON.stringify({schema:1,stage,packet});
  need(same(pin(stdin),WIRE) && WIRE.bytes<=1024*1024,"exact bounded packet");
  const request={host:"pocket4",executable:"/usr/bin/python3",args:["-I","-B","-c",BOUNDARY],stdin,cwd:"/",
    cpu_quota_percent:100,memory_max_bytes:1073741824,nice:15,timeout_seconds:600,
    idempotency_key:"pocket4-native-status-lifecycle-readiness-release-01-20261106"};
  const raw=JSON.stringify(request,null,2)+"\n";
  need(same(pin(raw),REQUEST),"exact request");
  return {request,raw,stdin};
}
