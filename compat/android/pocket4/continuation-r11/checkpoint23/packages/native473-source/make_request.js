"use strict";
// Exact frozen host compiler source carrier. Pure function: no I/O or dispatch.
// H is the independently verified UTF-8/SHA256 helper; it is not fetched or executed here.
const FILE_ORDER = ["compile_builder.py","expected-builder473-manifest.json","audiocontrol-example-projection-proof.json","delta/tools/droidloom-update/src/android.rs","delta/android/native-role-ingress/provider-fixtures/audiocontrol-example.Android.bp"];
const EXPECTED = {"compile_builder.py":{"bytes":87186,"sha256":"efe59bf47a15825c607782f9d0956eaa2a1a2588ba8477bb305670fcd7b913c8"},"expected-builder473-manifest.json":{"bytes":99775,"sha256":"a3426e40f9446b85931c82e8ba08335e72cd9bd0ac4a3f70aa01d54200d1ae13"},"audiocontrol-example-projection-proof.json":{"bytes":6453,"sha256":"c642e886b77adeb07d8f38a3dd10d042218e8e6582d6fd523be751ef1317b2e5"},"delta/tools/droidloom-update/src/android.rs":{"bytes":309074,"sha256":"88732b10c27bb0891cf0cac26bbe876b5ff4b134ee7048d073542fb052878cad"},"delta/android/native-role-ingress/provider-fixtures/audiocontrol-example.Android.bp":{"bytes":1869,"sha256":"9c8a0aecfa46ce0f1874362fa9dfff6a34326f9bf569b6fe7206dd6db1b3c9a6"}};
const STAGE = {"bytes":10752,"sha256":"b636adcaf13c3d54cb75ddb6cc099986fde1c63fc138d3283f45eba8caadcf97"};
const WIRE = {"bytes":541674,"sha256":"138fbd5a1f9b41c4f0825a229c2e8328ccff9f6deee26f17616fcf2a277040c3"};
const REQUEST = {"bytes":585148,"sha256":"ac7776afdd6b4ff02059b51439c15b74c921a6a214f1ed5c6e6bc36b2744d5fe"};
const BOUNDARY = "import hashlib,json,sys\nEXPECTED={\"bytes\":541674,\"sha256\":\"138fbd5a1f9b41c4f0825a229c2e8328ccff9f6deee26f17616fcf2a277040c3\"}\nSTAGE={\"bytes\":10752,\"sha256\":\"b636adcaf13c3d54cb75ddb6cc099986fde1c63fc138d3283f45eba8caadcf97\"}\nwire=sys.stdin.buffer.read(EXPECTED['bytes']+1)\nif len(wire)!=EXPECTED['bytes'] or hashlib.sha256(wire).hexdigest()!=EXPECTED['sha256']:\n    raise RuntimeError('fixed provider compiler transport length/hash mismatch')\nvalue=json.loads(wire)\nif type(value) is not dict or set(value)!={'schema','stage','packet'} or value['schema']!=1 or type(value['stage']) is not str:\n    raise RuntimeError('fixed provider compiler envelope differs')\nstage=value['stage'].encode('utf-8')\nif len(stage)!=STAGE['bytes'] or hashlib.sha256(stage).hexdigest()!=STAGE['sha256']:\n    raise RuntimeError('fixed provider compiler stage pin differs')\nscope={'__name__':'__stage__','__file__':'<fixed-provider-stage>'}\nexec(compile(stage,'<fixed-provider-stage>','exec'),scope,scope)\nscope['main'](value['packet'])\n";
const BASE = {"host":"pocket4","executable":"/usr/bin/python3","cwd":"/","cpu_quota_percent":100,"memory_max_bytes":1073741824,"nice":15,"timeout_seconds":600,"idempotency_key":"pocket4-native-typed-ingress-builder473-audiocontrol-example-projection-compile-01-20261106"};
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
