function makeInstalledProvenanceRequest(source,H) {
  const n=H.utf8(source).length, digest=H.sha(source);
  if(n>65536)throw Error("SOURCE_BOUND");
  const wrapper=[
    "import signal,sys,hashlib",
    "old=signal.signal(signal.SIGALRM,lambda signum,frame:(_ for _ in ()).throw(TimeoutError(\"INVENTORY_SELF_WATCHDOG\")))",
    "signal.setitimer(signal.ITIMER_REAL,55)",
    "try:",
    " raw=sys.stdin.buffer.read(65537)",
    " assert len(raw)=="+n+" and hashlib.sha256(raw).hexdigest()=="+JSON.stringify(digest),
    " ns={\"__name__\":\"fixed_installed_provenance\",\"__file__\":\"<verified-fixed-installed-provenance>\",\"SOURCE_SHA256\":"+JSON.stringify(digest)+"}",
    " exec(compile(raw,\"read_installed_provenance.py\",\"exec\"),ns)",
    " rc=ns[\"main\"]()",
    "finally:",
    " signal.setitimer(signal.ITIMER_REAL,0)",
    " signal.signal(signal.SIGALRM,old)",
    "raise SystemExit(rc)",
    ""
  ].join("\n");
  return {executable:"/usr/bin/sudo",host:"pocket4",cwd:"/home/alex/work",
    env:{PYTHONDONTWRITEBYTECODE:"1"},timeout_seconds:60,memory_max_bytes:134217728,
    cpu_quota_percent:25,nice:10,
    idempotency_key:"pocket4-current-baseline02-fixed-installed-provenance-read01-20261106",
    args:["-n","/usr/bin/python3","-I","-B","-c",wrapper],stdin:source};
}
