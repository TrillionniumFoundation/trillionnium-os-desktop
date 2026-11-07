"use strict";
function makeStatusCompileRequest(inputFiles, stage, H) {
  const FILE_ORDER = ["compile_status.py","expected-status-manifest.json","build-scope.json","delta/runtime/droidloom-supervisor/src/control.rs","delta/runtime/droidloom-supervisor/src/development.rs","delta/runtime/droidloom-supervisor/src/bin/droidloomctl.rs","delta/runtime/droidloom-supervisor/tests/cli_lifecycle.rs","delta/runtime/droidloom-supervisor/src/control_status_tests.rs"];
  const EXPECTED = {"compile_status.py":{"bytes":84470,"sha256":"66757ecc000a401f0f3ba690982945301d330a54fc84ab855923dbb236abe025"},"expected-status-manifest.json":{"bytes":99958,"sha256":"d8f6213f73726bd3766645e7decb5ebfac852f49852c49545e511a54b689d16e"},"build-scope.json":{"bytes":4272,"sha256":"554d3eee89100697b69336ccad6b97ca983aed064a75a000bf1cfa175709437b"},"delta/runtime/droidloom-supervisor/src/control.rs":{"bytes":71588,"sha256":"50d7bc3abd94f83233ef7d461f93cb714f843cacb3fd5c0e929d06671a95f89b"},"delta/runtime/droidloom-supervisor/src/development.rs":{"bytes":101645,"sha256":"37645978b33d443313694609625a97ac9dd7f6e14053664a48d02ff6d8daea90"},"delta/runtime/droidloom-supervisor/src/bin/droidloomctl.rs":{"bytes":20606,"sha256":"3733dd7586ebf534aef3d4a5d176a76b8822dd0c6a6b8b39fb64adf8e70cd484"},"delta/runtime/droidloom-supervisor/tests/cli_lifecycle.rs":{"bytes":11717,"sha256":"5310bfdb21b006ae1432b584c03fbbfb4c1f3a7cbd3ce226b54770ff4bbca317"},"delta/runtime/droidloom-supervisor/src/control_status_tests.rs":{"bytes":11843,"sha256":"0bafad33112df280c73ceedf675305236275bb043d0909fc4a71f6366c0a6727"}};
  const STAGE = {"bytes":9210,"sha256":"b3c5d25e7994b158755055107e4c9e2f26a59cd18fcc09c59ad69cf5dee0a86c"};
  const WIRE = {"bytes":436387,"sha256":"6e5fc5de1c18d647cf71b23229d9953a077e4db928dfbeda3a1aba13d947b65a"};
  const REQUEST = {"bytes":468678,"sha256":"db32d3d7abb8821957bd41348784d0abe214b447bfb6962771b0a45c9c13facd"};
  const BOUNDARY = "import hashlib,json,sys\nEXPECTED={\"bytes\":436387,\"sha256\":\"6e5fc5de1c18d647cf71b23229d9953a077e4db928dfbeda3a1aba13d947b65a\"}\nSTAGE={\"bytes\":9210,\"sha256\":\"b3c5d25e7994b158755055107e4c9e2f26a59cd18fcc09c59ad69cf5dee0a86c\"}\nwire=sys.stdin.buffer.read(EXPECTED['bytes']+1)\nif len(wire)!=EXPECTED['bytes'] or hashlib.sha256(wire).hexdigest()!=EXPECTED['sha256']:\n    raise RuntimeError('fixed provider compiler transport length/hash mismatch')\nvalue=json.loads(wire)\nif type(value) is not dict or set(value)!={'schema','stage','packet'} or value['schema']!=1 or type(value['stage']) is not str:\n    raise RuntimeError('fixed provider compiler envelope differs')\nstage=value['stage'].encode('utf-8')\nif len(stage)!=STAGE['bytes'] or hashlib.sha256(stage).hexdigest()!=STAGE['sha256']:\n    raise RuntimeError('fixed provider compiler stage pin differs')\nscope={'__name__':'__stage__','__file__':'<fixed-provider-stage>'}\nexec(compile(stage,'<fixed-provider-stage>','exec'),scope,scope)\nscope['main'](value['packet'])\n";
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
    idempotency_key:"pocket4-native-status-lifecycle-readiness-compile-01-20261106"};
  const raw=JSON.stringify(request,null,2)+"\n";
  need(same(pin(raw),REQUEST),"exact request");
  return {request,raw,stdin};
}
