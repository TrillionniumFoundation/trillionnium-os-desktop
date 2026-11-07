"use strict";
// Exact frozen host compiler source carrier. Pure function: no I/O or dispatch.
// H is the independently verified UTF-8/SHA256 helper; it is not fetched or executed here.
const FILE_ORDER = ["compile_builder.py","expected-builder471-manifest.json","systemui-test-projection-proof.json","delta/tools/droidloom-update/src/android.rs","delta/android/native-role-ingress/provider-fixtures/SystemUI-tests.Android.bp"];
const EXPECTED = {"compile_builder.py":{"bytes":85579,"sha256":"5b4e7d699b6ca82c9a60ff28cd49cf7d101fd6b92608fe70a92380182f3aac4f"},"expected-builder471-manifest.json":{"bytes":99548,"sha256":"c29c7b05fcfdf3def918d2bc963c6fe0c25a0430c87249f3de781d5d8bf68ae0"},"systemui-test-projection-proof.json":{"bytes":6531,"sha256":"17fe54cebd452ef14258461f0817b9cbc753ccb0619f28e7274e61879a89d762"},"delta/tools/droidloom-update/src/android.rs":{"bytes":301533,"sha256":"7bbe16d118fe610ae42e9c1b906b65aee5ceeb0804cdbaee93ee61ab5b271629"},"delta/android/native-role-ingress/provider-fixtures/SystemUI-tests.Android.bp":{"bytes":3392,"sha256":"f1b2422c693a8f8c52034369ded585a3a93ac861f9dd6dd73f0801a77e6be4da"}};
const STAGE = {"bytes":10719,"sha256":"a3bc0bfb910c35c8adf1ab9f2661fd648ad71aea479dd8a8c0c474453e7c962a"};
const WIRE = {"bytes":533704,"sha256":"ba151e0e4ce8f0443d5a6fcb350d68f69235fa97e18227251eebbd4e528b051b"};
const REQUEST = {"bytes":576961,"sha256":"82fad9cb3da572d593bfe49e67069bb6b7f28460c112d3ac2a5ff4398583e220"};
const BOUNDARY = "import hashlib,json,sys\nEXPECTED={\"bytes\":533704,\"sha256\":\"ba151e0e4ce8f0443d5a6fcb350d68f69235fa97e18227251eebbd4e528b051b\"}\nSTAGE={\"bytes\":10719,\"sha256\":\"a3bc0bfb910c35c8adf1ab9f2661fd648ad71aea479dd8a8c0c474453e7c962a\"}\nwire=sys.stdin.buffer.read(EXPECTED['bytes']+1)\nif len(wire)!=EXPECTED['bytes'] or hashlib.sha256(wire).hexdigest()!=EXPECTED['sha256']:\n    raise RuntimeError('fixed provider compiler transport length/hash mismatch')\nvalue=json.loads(wire)\nif type(value) is not dict or set(value)!={'schema','stage','packet'} or value['schema']!=1 or type(value['stage']) is not str:\n    raise RuntimeError('fixed provider compiler envelope differs')\nstage=value['stage'].encode('utf-8')\nif len(stage)!=STAGE['bytes'] or hashlib.sha256(stage).hexdigest()!=STAGE['sha256']:\n    raise RuntimeError('fixed provider compiler stage pin differs')\nscope={'__name__':'__stage__','__file__':'<fixed-provider-stage>'}\nexec(compile(stage,'<fixed-provider-stage>','exec'),scope,scope)\nscope['main'](value['packet'])\n";
const BASE = {"host":"pocket4","executable":"/usr/bin/python3","cwd":"/","cpu_quota_percent":100,"memory_max_bytes":1073741824,"nice":15,"timeout_seconds":600,"idempotency_key":"pocket4-native-typed-ingress-builder471-systemui-test-projection-compile-01-20261106"};
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
