"use strict";
function reproduceResourceObservation(source,H) {
  const b=H.utf8(source),s=H.sha256(b);
  if(b.length!==6267||s!=="6dee89953c17e7823717360d2dde0f2f85e99a0a6d3ee7e65dba7afccc6e43d3")
    throw Error("EXACT_FIXED_SOURCE_REQUIRED");
  const wrapper="import hashlib,sys\nraw=sys.stdin.buffer.read("+(b.length+1)+")\nif len(raw)!="+b.length+" or hashlib.sha256(raw).hexdigest()!="+JSON.stringify(s)+":\n    raise RuntimeError('fixed resource observation source differs')\nif sys.argv[1:] != ['--execute-once']:\n    raise RuntimeError('explicit one-time observation required')\nexec(compile(raw,'<normal05-fixed-resource-observation01>','exec'),{'__name__':'__main__'})\n";
  return JSON.stringify({
    host:"pocket4",executable:"/usr/bin/python3",args:["-I","-B","-c",wrapper,"--execute-once"],
    cwd:"/home/alex/work",env:{PYTHONDONTWRITEBYTECODE:"1"},
    stdin:source,idempotency_key:"pocket4-native-normal05-fixed-resource-observation-01-20261106",
    timeout_seconds:3,cpu_quota_percent:25,memory_max_bytes:67108864,nice:19
  },null,2)+"\n";
}
