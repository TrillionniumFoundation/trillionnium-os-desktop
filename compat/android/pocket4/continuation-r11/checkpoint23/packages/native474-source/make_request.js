"use strict";
// Exact frozen host compiler source carrier. Pure function: no I/O or dispatch.
// H is the independently verified UTF-8/SHA256 helper; it is not fetched or executed here.
const FILE_ORDER = ["compile_builder.py","expected-builder474-manifest.json","composer-audiocontrol-proof.json","build-scope.json","delta/tools/droidloom-update/src/android.rs","delta/android/native-role-ingress/provider-fixtures/audiocontrol-example.Android.bp"];
const EXPECTED = {"compile_builder.py":{"bytes":95194,"sha256":"cce160807e3466c98fd3fd43f4a1b7c25e160d94a0e05fc39ad8103508da398a"},"expected-builder474-manifest.json":{"bytes":99750,"sha256":"e18fe837795e9c3bd684592f3c91228604b2b21ca9d918ac56cebdb4b40754dd"},"composer-audiocontrol-proof.json":{"bytes":12564,"sha256":"2a3d0c6c6727e83aa8c325c63488e932774d8c9fa41e32065b5a5952b8f5a1ab"},"build-scope.json":{"bytes":7076,"sha256":"65f48507f685808728c1cd5a7f4a44e09e9b57f0588befbb97ba77a94a25da3d"},"delta/tools/droidloom-update/src/android.rs":{"bytes":329800,"sha256":"72fe8ba4dfec2422b5809fa5af8c84387537527245c35d0e3a13c10060a361cc"},"delta/android/native-role-ingress/provider-fixtures/audiocontrol-example.Android.bp":{"bytes":1869,"sha256":"9c8a0aecfa46ce0f1874362fa9dfff6a34326f9bf569b6fe7206dd6db1b3c9a6"}};
const STAGE = {"bytes":12034,"sha256":"289f02d283901ffb5959e318661271644d12d2c189493fc3274b05e8c72174b7"};
const WIRE = {"bytes":587141,"sha256":"ad47d2859540bec285c3f77c9a97d31c57c37018a4c1c44b9acd19f74e414d4e"};
const REQUEST = {"bytes":634292,"sha256":"6a6d89414b1fd3d529173a7d6b5a9f2f733a1e893438e0aa9243b8803669d29e"};
const BOUNDARY = "import hashlib,json,sys\nEXPECTED={\"bytes\":587141,\"sha256\":\"ad47d2859540bec285c3f77c9a97d31c57c37018a4c1c44b9acd19f74e414d4e\"}\nSTAGE={\"bytes\":12034,\"sha256\":\"289f02d283901ffb5959e318661271644d12d2c189493fc3274b05e8c72174b7\"}\nwire=sys.stdin.buffer.read(EXPECTED['bytes']+1)\nif len(wire)!=EXPECTED['bytes'] or hashlib.sha256(wire).hexdigest()!=EXPECTED['sha256']:\n    raise RuntimeError('fixed provider compiler transport length/hash mismatch')\nvalue=json.loads(wire)\nif type(value) is not dict or set(value)!={'schema','stage','packet'} or value['schema']!=1 or type(value['stage']) is not str:\n    raise RuntimeError('fixed provider compiler envelope differs')\nstage=value['stage'].encode('utf-8')\nif len(stage)!=STAGE['bytes'] or hashlib.sha256(stage).hexdigest()!=STAGE['sha256']:\n    raise RuntimeError('fixed provider compiler stage pin differs')\nscope={'__name__':'__stage__','__file__':'<fixed-provider-stage>'}\nexec(compile(stage,'<fixed-provider-stage>','exec'),scope,scope)\nscope['main'](value['packet'])\n";
const BASE = {"host":"pocket4","executable":"/usr/bin/python3","cwd":"/","cpu_quota_percent":100,"memory_max_bytes":1073741824,"nice":15,"timeout_seconds":600,"idempotency_key":"pocket4-native-builder474-composer-audiocontrol-projection-compile-01-20261106"};
const REQUEST_ORDER = ["host","executable","args","stdin","cwd","cpu_quota_percent","memory_max_bytes","nice","timeout_seconds","idempotency_key"];
function generate(inputFiles, stage, H) {
  function require(value, reason) { if (!value) throw new Error(reason); }
  function pin(value) {const b=H.utf8(value); return {bytes:b.length,sha256:H.sha256(b)};}
  function equal(a,b) {return JSON.stringify(a)===JSON.stringify(b);}
  require(equal(Object.keys(inputFiles).sort(), [...FILE_ORDER].sort()), "exact compiler source set");
  const packet={};
  for(const name of FILE_ORDER) {
    require(typeof inputFiles[name]==="string" && equal(pin(inputFiles[name]),EXPECTED[name]), "compiler source pin: "+name);
    packet[name]=inputFiles[name];
  }
  require(typeof stage==="string" && equal(pin(stage),STAGE), "compiler stage pin");
  const wire=JSON.stringify({schema:1,stage,packet});
  require(equal(pin(wire),WIRE) && WIRE.bytes<=1024*1024, "wire pin or actual one MiB tool bound");
  const req={...BASE,args:["-I","-B","-c",BOUNDARY],stdin:wire};
  const ordered={};for(const name of REQUEST_ORDER)ordered[name]=req[name];
  const raw=JSON.stringify(ordered,null,2)+"\n";
  require(equal(pin(raw),REQUEST), "compiler request pin");
  return {request:raw,stdin:wire,request_object:ordered};
}
