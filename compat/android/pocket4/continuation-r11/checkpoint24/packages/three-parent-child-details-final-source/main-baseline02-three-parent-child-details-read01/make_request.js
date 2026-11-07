function makeThreeParentChildDetailsRequest(source,h){
 const pin={bytes:h.utf8(source).length,sha256:h.sha(source)};
 if(pin.bytes!==33703||pin.sha256!=="93153ae726e2ad1bef35b8785fdf0eaacf3f3070768e919b5271e988b62860f3")throw Error("EXACT_FROZEN_DIAGNOSTIC_SOURCE_REQUIRED");
 const wrapper='import signal,sys,hashlib\n'+
  'old=signal.signal(signal.SIGALRM,lambda signum,frame:(_ for _ in ()).throw(TimeoutError("DIAGNOSTIC_SELF_WATCHDOG")))\n'+
  'signal.setitimer(signal.ITIMER_REAL,12)\n'+
  'try:\n'+
  ' raw=sys.stdin.buffer.read(65537)\n'+
  ' assert len(raw)=='+pin.bytes+' and hashlib.sha256(raw).hexdigest()=="'+pin.sha256+'"\n'+
  ' ns={"__name__":"fixed_three_parent_child_details","__file__":"<verified-fixed-three-parent-child-details>","SOURCE_SHA256":"'+pin.sha256+'"}\n'+
  ' exec(compile(raw,"read_parent_children.py","exec"),ns)\n'+
  ' rc=ns["main"]()\n'+
  'finally:\n'+
  ' signal.setitimer(signal.ITIMER_REAL,0)\n'+
  ' signal.signal(signal.SIGALRM,old)\n'+
  'raise SystemExit(rc)\n';
 return {executable:"/usr/bin/sudo",args:["-n","/usr/bin/python3","-I","-B","-c",wrapper],
  host:"pocket4",cwd:"/home/alex/work",env:{PYTHONDONTWRITEBYTECODE:"1"},stdin:source,
  timeout_seconds:15,memory_max_bytes:134217728,cpu_quota_percent:100,nice:10,
  idempotency_key:"pocket4-baseline02-three-parent-child-details-read01-20261106"};
}
