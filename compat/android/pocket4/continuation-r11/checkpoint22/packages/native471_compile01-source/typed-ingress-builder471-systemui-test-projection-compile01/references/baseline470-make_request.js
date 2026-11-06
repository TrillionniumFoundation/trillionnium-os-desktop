"use strict";
// Exact frozen host compiler source carrier. Pure function: no I/O or dispatch.
// H is the independently verified UTF-8/SHA256 helper; it is not fetched or executed here.
const FILE_ORDER = ["compile_builder.py","expected-builder470-manifest.json","lock-alignment-proof.json","observed-published225-manifest.json","delta/tools/droidloom-update/src/native_role_ingress.rs","delta/android/manifest/m2-role-ingress-hal-provider-source-lock.json"];
const EXPECTED = {"compile_builder.py":{"bytes":86321,"sha256":"63bad2f9323b6f3881d883a792afd49b2472e43f35740253c01534dca91913cc"},"expected-builder470-manifest.json":{"bytes":99327,"sha256":"d87ab919c015a8739011a83add768db28c7f7296a7be9683a0516b28808c1057"},"lock-alignment-proof.json":{"bytes":7697,"sha256":"4b74519eee1909efa3ee0283fe67fa6432525a80bff5049bae29e159ad1ea222"},"observed-published225-manifest.json":{"bytes":109252,"sha256":"5ae96f8d2bc32986fdbf8fea12f54dbcb02b1ed1601894b2b23998f61aba0d7d"},"delta/tools/droidloom-update/src/native_role_ingress.rs":{"bytes":39648,"sha256":"43cbfceac6f2a5dbcaea93fa6848e0f8740c096cf5412361f42ab86d22c219f3"},"delta/android/manifest/m2-role-ingress-hal-provider-source-lock.json":{"bytes":96957,"sha256":"72848909e4931d712a3d59f344904ae8642b32c35a01cf520a51afce4c56b50d"}};
const STAGE = {"bytes":10959,"sha256":"8510804bba86aa6b6b4730ef2fedb2037af6ab596fa5e0e3f6e9303e1299a522"};
const WIRE = {"bytes":481879,"sha256":"b6856cb45e7738441b6d83ab80496b18de7f3b36074857da0e2242296e0606e7"};
const REQUEST = {"bytes":535566,"sha256":"e9c16afd57dfe5f5e8f5d29dbdb2596fa0140a48a08732a0a1106ade367426c9"};
const BOUNDARY = "import hashlib,json,sys\nEXPECTED={\"bytes\":481879,\"sha256\":\"b6856cb45e7738441b6d83ab80496b18de7f3b36074857da0e2242296e0606e7\"}\nSTAGE={\"bytes\":10959,\"sha256\":\"8510804bba86aa6b6b4730ef2fedb2037af6ab596fa5e0e3f6e9303e1299a522\"}\nwire=sys.stdin.buffer.read(EXPECTED['bytes']+1)\nif len(wire)!=EXPECTED['bytes'] or hashlib.sha256(wire).hexdigest()!=EXPECTED['sha256']:\n    raise RuntimeError('fixed provider compiler transport length/hash mismatch')\nvalue=json.loads(wire)\nif type(value) is not dict or set(value)!={'schema','stage','packet'} or value['schema']!=1 or type(value['stage']) is not str:\n    raise RuntimeError('fixed provider compiler envelope differs')\nstage=value['stage'].encode('utf-8')\nif len(stage)!=STAGE['bytes'] or hashlib.sha256(stage).hexdigest()!=STAGE['sha256']:\n    raise RuntimeError('fixed provider compiler stage pin differs')\nscope={'__name__':'__stage__','__file__':'<fixed-provider-stage>'}\nexec(compile(stage,'<fixed-provider-stage>','exec'),scope,scope)\nscope['main'](value['packet'])\n";
const BASE = {"host":"pocket4","executable":"/usr/bin/python3","cwd":"/","cpu_quota_percent":100,"memory_max_bytes":1073741824,"nice":15,"timeout_seconds":600,"idempotency_key":"pocket4-native-typed-ingress-builder470-published-lock-alignment-compile-01-20261106"};
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
