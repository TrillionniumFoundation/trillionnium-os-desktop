"use strict";
// Exact frozen host compiler source carrier. Pure function: no I/O or dispatch.
// H is the independently verified UTF-8/SHA256 helper; it is not fetched or executed here.
const FILE_ORDER = ["compile_builder.py","expected-builder472-manifest.json","composer-entry-proof.json","build-scope.json","delta/tools/droidloom-update/src/android.rs","delta/tools/droidloom-update/src/main.rs"];
const EXPECTED = {"compile_builder.py":{"bytes":90451,"sha256":"a1e24b06b89c96c4d818d62b0394653c56e10fed6e3793c88ce11af19d6bd907"},"expected-builder472-manifest.json":{"bytes":99523,"sha256":"fcbf72b891d9a9bbbcd015777e50cc3ade436f25732a603b51de261eab9cb27a"},"composer-entry-proof.json":{"bytes":11586,"sha256":"3bc022c9924dc13f7e2ad8d6ed85a079af1dec61733433b88c2c76d0df0c60da"},"build-scope.json":{"bytes":6535,"sha256":"f43cd778b75e484d53899eab543680e6b32ae5e54d6eca373b34223dcfcc8af9"},"delta/tools/droidloom-update/src/android.rs":{"bytes":321919,"sha256":"0be2c4d9607c719a8e2bec337d0f23caced603381b0823659559844f77eea996"},"delta/tools/droidloom-update/src/main.rs":{"bytes":24381,"sha256":"f6be56d7f64144c0be40b3c6c519a966b9d733ef3e5f857d8140bef1be3a8ace"}};
const STAGE = {"bytes":14834,"sha256":"51559fe3bc57d75e0668d9bdec451cf9bf551ccdb6ac9a4eef9839bd38033643"};
const WIRE = {"bytes":598552,"sha256":"2ff3b81084eff5835d0948091c226f557fc01e0a77e6acd2137a866843dd894a"};
const REQUEST = {"bytes":646415,"sha256":"ddb7f892a6c5b5278260d459989a10900d04fdea64a1d762e3333caac6244bf8"};
const BOUNDARY = "import hashlib,json,sys\nEXPECTED={\"bytes\":598552,\"sha256\":\"2ff3b81084eff5835d0948091c226f557fc01e0a77e6acd2137a866843dd894a\"}\nSTAGE={\"bytes\":14834,\"sha256\":\"51559fe3bc57d75e0668d9bdec451cf9bf551ccdb6ac9a4eef9839bd38033643\"}\nwire=sys.stdin.buffer.read(EXPECTED['bytes']+1)\nif len(wire)!=EXPECTED['bytes'] or hashlib.sha256(wire).hexdigest()!=EXPECTED['sha256']:\n    raise RuntimeError('fixed provider compiler transport length/hash mismatch')\nvalue=json.loads(wire)\nif type(value) is not dict or set(value)!={'schema','stage','packet'} or value['schema']!=1 or type(value['stage']) is not str:\n    raise RuntimeError('fixed provider compiler envelope differs')\nstage=value['stage'].encode('utf-8')\nif len(stage)!=STAGE['bytes'] or hashlib.sha256(stage).hexdigest()!=STAGE['sha256']:\n    raise RuntimeError('fixed provider compiler stage pin differs')\nscope={'__name__':'__stage__','__file__':'<fixed-provider-stage>'}\nexec(compile(stage,'<fixed-provider-stage>','exec'),scope,scope)\nscope['main'](value['packet'])\n";
const BASE = {"host":"pocket4","executable":"/usr/bin/python3","cwd":"/","cpu_quota_percent":100,"memory_max_bytes":1073741824,"nice":15,"timeout_seconds":600,"idempotency_key":"pocket4-native-builder472-composer-retirement-entry-compile-01-20261106"};
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
