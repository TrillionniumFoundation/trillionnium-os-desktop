import os,sys,pathlib,json,hashlib,subprocess,stat,datetime,time,resource
P=pathlib.Path
parent=P('/home/alex/work/pocket4-signal-mask-r11-build-memory-01')
root=parent/'attempt04'
destination=parent/'builder-source'
builder=P('/home/alex/work/pocket4-signal-semantics-r15-20261104/cargo-target/debug/droidloom-update')
engine_source=P('/home/alex/work/pocket4-signal-mask-r11-build-01/source')
work=P('/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1')
out=P('/home/alex/work/pocket4-signal-mask-r11-build-01/android-out')
def sha(p):
 with P(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def save(p,j):
 fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
 with os.fdopen(fd,'w') as f:json.dump(j,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
def inventory(base):
 rows={}
 for directory,dirs,files in os.walk(base,followlinks=False):
  d=P(directory)
  for name in sorted(dirs+files):
   p=d/name; rel=str(p.relative_to(base)); s=p.lstat()
   if stat.S_ISREG(s.st_mode):rows[rel]={'kind':'file','sha256':sha(p),'bytes':s.st_size,'mode':stat.S_IMODE(s.st_mode)}
   elif stat.S_ISLNK(s.st_mode):rows[rel]={'kind':'symlink','target':os.readlink(p)}
   elif not stat.S_ISDIR(s.st_mode):raise RuntimeError('unexpected source object '+rel)
 return rows

assert os.getuid()!=0
os.umask(0o077);resource.setrlimit(resource.RLIMIT_CORE,(0,0))
assert not root.exists() and not root.is_symlink()
assert sha(builder)=='16df26d88391c22c9f076917531f022907ec5608bd31e58e05c898605db9dcc4'
assert sha(parent/'builder-source-after.json')=='e7c225bd2842c260d9f4149aca3c4483ed31c569efb31068b6d787892bd17017'
expected=json.loads((parent/'builder-source-after.json').read_text())
assert inventory(destination)==expected
for row in json.loads("[{\"path\":\"guest_os_primitives/arm64/guest_context_arch.h\",\"preimage_sha256\":\"ca4daaa682994ad830180291f3cef07375c5d938aa0ab9f58b45c5e15fff34cf\",\"sha256\":\"c4234d83ce70c526d96cbd9b843dbca1e0645c18d7f371654552d2a8e2f07140\",\"bytes\":8640},{\"path\":\"guest_os_primitives/guest_signal_handling.cc\",\"preimage_sha256\":\"8c4052082617327c3c52126eb3124fa0a3259c4b36a380e61e7b20503277bbeb\",\"sha256\":\"7ca556ea512b2262e2bf28709bbb7962d4ef5cb7e4c53c012437b6603fd9623a\",\"bytes\":28870},{\"path\":\"guest_os_primitives/guest_signal_handling_arch.cc\",\"preimage_sha256\":\"6097d09a396d77c516cf91c5b75abb3b0cbd1e7fccbcc1e1555b84e7d1292963\",\"sha256\":\"5fc077ed8538255bac2ac921b1231a3bf60314659f85c79237d724c41f0460b5\",\"bytes\":6274},{\"path\":\"guest_os_primitives/include/berberis/guest_os_primitives/guest_signal.h\",\"preimage_sha256\":\"8a343fa094ac83a0411cbcfe82372881ff77f32f08cc5d5a8ae15cdf8ec11877\",\"sha256\":\"ebcc5ac4e092c50916a0f9668c94d3cb2266cece0ff728bc19513e8f7eb218ca\",\"bytes\":3611},{\"path\":\"guest_os_primitives/include/berberis/guest_os_primitives/guest_thread.h\",\"preimage_sha256\":\"4b27ba2f90bee2c9e92c49d3f3b2beb6a07fb7ee27087d9e8e04d369603fa737\",\"sha256\":\"90a35d504656e32520ab84968ae8a3b586264c835489d13f85f42444cb0764c0\",\"bytes\":6115},{\"path\":\"guest_os_primitives/scoped_guest_signal_mask.h\",\"preimage_sha256\":null,\"sha256\":\"52c18a437a05e00be80420c39ef03d24b4ec86a2470b66b548c29d8888eecde9\",\"bytes\":2869}]"):assert sha(engine_source/row['path'])==row['sha256']
memory={a:int(b.split()[0])*1024 for a,b in [s.split(':',1) for s in P('/proc/meminfo').read_text().splitlines()]}
assert memory['MemAvailable']>=15*1024**3,('insufficient host headroom',memory['MemAvailable'])
before_affinity=sorted(os.sched_getaffinity(0));assert len(before_affinity)>=4
cpus=set(before_affinity[-2:]);os.sched_setaffinity(0,cpus)
cg=P('/proc/self/cgroup').read_text().strip()
assert cg.startswith('0::/user.slice/user-1000.slice/user@1000.service/app.slice/hepta-runtime-job-')
cgroup=P('/sys/fs/cgroup')/cg[3:].lstrip('/')
unit=cgroup.name
assert (cgroup/'memory.max').read_text().strip()==str(11*1024**3)
assert (cgroup/'cpu.max').read_text().strip()=='200000 100000'
assert 'hepta-runtime-job-' in unit and unit.endswith('.service')
# Tighten swap for this exact current job only; no Main or sibling resource change.
subprocess.run(['systemctl','--user','set-property','--runtime',unit,'MemorySwapMax=1073741824'],check=True,capture_output=True,timeout=15)
assert (cgroup/'memory.swap.max').read_text().strip()=='1073741824'
root.mkdir(mode=0o700)
claim={'schema':1,'state':'STARTING_FULL_BUILD_ATTEMPT04','started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'builder_sha256':sha(builder),'source_manifest_sha256':sha(parent/'builder-source-after.json'),'soong_soft_memory_budget':'6GiB','memory_max_bytes':11*1024**3,'memory_swap_max_bytes':1024**3,'mem_available_before_bytes':memory['MemAvailable'],'host_headroom_required_bytes':4*1024**3,'cpu_affinity_before':before_affinity,'cpu_affinity':sorted(cpus),'cpu_quota_percent':200,'unit':unit,'no_automatic_retry':True,'normal_builder_lock_and_recovery':True,'main_resource_settings_changed':False}
save(root/'claim.json',claim);print(json.dumps(claim),flush=True)
env=os.environ.copy();env['DROIDLOOM_NATIVE_BRIDGE_SOURCE']=str(engine_source)
argv=[str(builder),'--source',str(destination),'--jobs','1','native-engine-build','--work',str(work),'--tests','--out',str(out)]
start=time.monotonic()
with (root/'build.stdout').open('xb') as stdout,(root/'build.stderr').open('xb') as stderr:
 result=subprocess.run(argv,env=env,stdout=stdout,stderr=stderr,timeout=6100)
terminal={'returncode':result.returncode,'seconds':time.monotonic()-start,'finished_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'stdout_sha256':sha(root/'build.stdout'),'stderr_sha256':sha(root/'build.stderr'),'builder_source_unchanged':inventory(destination)==expected,'memory_events':(cgroup/'memory.events').read_text(),'memory_peak':(cgroup/'memory.peak').read_text().strip(),'memory_swap_peak':(cgroup/'memory.swap.peak').read_text().strip()}
receipt=out/'target/product/droidloom_x86_64/droidloom-native-engine-source.json'
terminal['final_engine_receipt']={'path':str(receipt),'exists':receipt.is_file(),'sha256':sha(receipt) if receipt.is_file() else None}
save(root/'terminal.json',terminal);print(json.dumps(terminal),flush=True)
sys.exit(result.returncode)
