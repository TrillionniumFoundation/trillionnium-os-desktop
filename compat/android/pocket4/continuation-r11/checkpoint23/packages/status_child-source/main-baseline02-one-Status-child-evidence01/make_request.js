function makeStatusChildEvidenceRequest(source,h){
 const base={"executable":"/usr/bin/sudo","host":"pocket4","cwd":"/home/alex/work","env":{"PYTHONDONTWRITEBYTECODE":"1"},"timeout_seconds":30,"memory_max_bytes":134217728,"cpu_quota_percent":100,"nice":10};
 const pin={bytes:h.utf8(source).length,sha256:h.sha(source)};
 if(pin.bytes>65536)throw Error("source bound");
 const wrapper='import signal,sys,hashlib\n'+
  'old=signal.signal(signal.SIGALRM,lambda signum,frame:(_ for _ in ()).throw(TimeoutError("DIAGNOSTIC_SELF_WATCHDOG")))\n'+
  'signal.setitimer(signal.ITIMER_REAL,25)\n'+
  'try:\n'+
  ' raw=sys.stdin.buffer.read(65537)\n'+
  ' assert len(raw)=='+pin.bytes+' and hashlib.sha256(raw).hexdigest()=="'+pin.sha256+'"\n'+
  ' ns={"__name__":"fixed_Status_child_evidence","__file__":"<verified-fixed-Status-child-evidence>","SOURCE_SHA256":"'+pin.sha256+'"}\n'+
  ' exec(compile(raw,"read_status_child_evidence.py","exec"),ns)\n'+
  ' rc=ns["main"]()\n'+
  'finally:\n'+
  ' signal.setitimer(signal.ITIMER_REAL,0)\n'+
  ' signal.signal(signal.SIGALRM,old)\n'+
  'raise SystemExit(rc)\n';
 return {...base,idempotency_key:"pocket4-current-baseline02-one-Status-child-evidence01-20261106",
  args:["-n","/usr/bin/python3","-I","-B","-c",wrapper],stdin:source};
}
