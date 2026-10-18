#!/usr/bin/env python3
"""Posthoc evidence packaging only; never installs or invokes a guest."""
import datetime, hashlib, json, lzma, os, platform, shutil, socket
from pathlib import Path

BASE=Path('/workspace/scratch/ae1a8cf05419')
REPO=BASE/'trillionnium-os-desktop'
SRC=BASE/'native-tools-restore'
DST=REPO/'support/build/evidence/2026-10-17-private-toolchain'
RUST=BASE/'round2-restore'
def digest(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as s:
  for b in iter(lambda:s.read(1048576),b''):h.update(b)
 return h.hexdigest()
def write(p,v):
 p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,indent=2)+'\n')
def copy(a,b):
 b.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(a,b)
def record(p):return {'path':str(p),'bytes':p.stat().st_size,'sha256':digest(p)}
DST.mkdir(parents=True,exist_ok=True)
# Preserve controller receipts and logs byte-for-byte; omitted binary paths are indexed separately.
for name in ['restore.py','controller-environment.json','controller.jsonl','controller-cwd-correction.json',
             'extractions.json','native-environment.json','package-plan.json','signed-indexes.json','sources.list',
             'validation-results.json','validation-results.before-resource-classification.json','verified-downloads.json']:
 copy(SRC/name,DST/'experimental-native'/name)
for p in sorted((SRC/'logs').iterdir()):
 if p.is_file():copy(p,DST/'experimental-native/logs'/p.name)
for p in sorted((SRC/'validation').iterdir()):
 if p.is_file() and p.suffix in ('.log','.c'):copy(p,DST/'experimental-native/validation'/p.name)
copy(Path('/usr/share/keyrings/ubuntu-archive-keyring.gpg'),DST/'signatures/ubuntu-archive-keyring.gpg')
releases=json.loads((SRC/'signed-indexes.json').read_text())
indexes=[]
for suite,data in releases.items():
 copy(SRC/'signed'/(suite+'-InRelease'),DST/'signatures'/(suite+'-InRelease'))
 for component,v in data['indexes'].items():
  p=SRC/'indexes'/(suite+'-'+component+'-Packages.xz')
  expected=v['expected']
  if p.stat().st_size != expected['bytes'] or digest(p)!=expected['sha256']:raise ValueError('index mismatch')
  parts=[]
  if p.stat().st_size>5*1024*1024:
   with p.open('rb') as s:
    i=0
    while True:
     b=s.read(2*1024*1024)
     if not b:break
     rel='indexes/'+p.name+'.part'+str(i).zfill(3)
     q=DST/rel;q.parent.mkdir(parents=True,exist_ok=True);q.write_bytes(b)
     parts.append({'path':rel,'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()});i+=1
  else:
   rel='indexes/'+p.name;copy(p,DST/rel)
   parts=[{'path':rel,'bytes':p.stat().st_size,'sha256':digest(p)}]
  indexes.append({'suite':suite,'component':component,'release_path':component+'/binary-amd64/Packages.xz',
                  'expected_bytes':expected['bytes'],'expected_sha256':expected['sha256'],'parts':parts})
write(DST/'index-storage.json',indexes)
# Retain exact signed package paragraphs with original final blank line.
plan=json.loads((SRC/'package-plan.json').read_text())
wanted={(p['suite'],p['component'],p['Package'],p['Version']):p for p in plan}
found={}
def parse(raw):
 result={};previous=None
 for line in raw.decode().splitlines():
  if line[:1].isspace() and previous:result[previous]+=' '+line.strip()
  elif ':' in line:previous,value=line.split(':',1);result[previous]=value.strip()
 return result
for i in indexes:
 with lzma.open(SRC/'indexes'/(i['suite']+'-'+i['component']+'-Packages.xz'),'rb') as s:
  raw=bytearray()
  for line in s:
   raw.extend(line)
   if line==b'\n':
    p=parse(raw);key=(i['suite'],i['component'],p.get('Package'),p.get('Version'))
    if key in wanted:
     if key in found:raise ValueError('duplicate exact signed stanza')
     selected=wanted[key];rel='selected-stanzas/'+selected['Package']+'.deb822'
     q=DST/rel;q.parent.mkdir(parents=True,exist_ok=True);q.write_bytes(raw)
     found[key]={**selected,'stanza_path':rel,'stanza_sha256':hashlib.sha256(raw).hexdigest()}
    raw=bytearray()
  if raw:raise ValueError('unexpected unterminated index paragraph')
if set(wanted)!=set(found):raise ValueError('missing selected stanza')
write(DST/'package-lock.json',{'count':len(plan),'entries':[found[(p['suite'],p['component'],p['Package'],p['Version'])] for p in plan]})
for name in ['controller.json','prepare-host.log']:copy(RUST/name,DST/'before'/name)
for name in ['restore-rust.py','rust-commands.json']:copy(RUST/name,DST/'rust-restore'/name)
rust_rows=json.loads((RUST/'rust-commands.json').read_text())
if len(rust_rows)!=8 or any(r['returncode']!=0 for r in rust_rows):raise ValueError('unexpected Rust receipts')
for row in rust_rows:copy(RUST/(row['name']+'.log'),DST/'rust-restore/logs'/(row['name']+'.log'))
installer=record(RUST/'rustup-init')
installer.update(url='https://static.rust-lang.org/rustup/dist/x86_64-unknown-linux-gnu/rustup-init',retained_in_archive=False,
 expected_sha256_in_executed_restore_script='dda7234360b7f578ca8b0ddcb80145646fa61a67c1720a5abc7051b35c9fcb71')
if installer['sha256']!=installer['expected_sha256_in_executed_restore_script']:raise ValueError('installer digest')
vdso=REPO/'support/build/out/linux-vdso/vdso_x86_64.so'
write(DST/'rust-restore/inputs.json',{
 'record_kind':'posthoc evidence packaging of original command receipts and retained inputs',
 'official_installer':installer,
 'fixed_nightly':{'channel':'nightly-2026-07-21','rustc_commit':'87e5904f5eb6398af6b22eac2802c78934260c48',
                  'explicitly_installed_target':'x86_64-unknown-none',
                  'components':'rust-src,rustc-dev,llvm-tools-preview,rustfmt,clippy'},
 'manifest_observation':{'record_kind':'posthoc transcription of an actual earlier tool result in this restoration session; not recorded by restore-rust.py',
   'url':'https://static.rust-lang.org/dist/2026-07-21/channel-rust-nightly.toml','http_status':200,'bytes':929653,
   'sha256':'c0b09f4e128768b2d6eab27050625a1ce974f8b39c07871370368cd82fbf8617',
   'raw_current_manifest_retained':False,
   'prior_archive_reference':'support/build/evidence/2026-10-16/host/channel-rust-nightly.toml.gz',
   'prior_archive_scope':'Earlier archived bytes are a reference, not substituted for missing current download.'},
 'cargo_binutils':{'version':'0.4.0','locked':True},
 'vdso':{'url':'https://github.com/asterinas/linux_vdso.git','commit':'8af571775a3d3a1df3e84fc9709b9d6b160c771a',
         'tree':'8e0a300d78c2a020ccc79f1253bc27a8301416e6','artifact':record(vdso),'binary_retained_in_archive':False},
 'environment_scope':'Original receipts save selected environment only. The executed script prepends CARGO_HOME/bin to inherited PATH; full inherited environment was not captured.'
})
status={}
for line in Path('/proc/self/status').read_text().splitlines():
 if line.startswith(('Uid:','Gid:','CapInh:','CapPrm:','CapEff:','CapBnd:','CapAmb:','NoNewPrivs:','Seccomp:','Seccomp_filters:','Cpus_allowed_list:')):
  k,v=line.split(':',1);status[k]=v.strip()
def read(p):
 p=Path(p);return p.read_text().strip() if p.is_file() else None
write(DST/'host-observation.json',{
 'record_kind':'posthoc read-only host observation at packaging time; not claimed as a pre-restoration snapshot',
 'observed_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'hostname':socket.gethostname(),
 'boot_id':read('/proc/sys/kernel/random/boot_id'),'platform':platform.platform(),'process_status':status,
 'cpu_max':read('/sys/fs/cgroup/cpu.max'),'memory_max':read('/sys/fs/cgroup/memory.max'),
 'dev_kvm_exists':Path('/dev/kvm').exists(),
 'prior_probe_observation':{'record_kind':'posthoc transcription of earlier actual environment probe',
  'af_unix_socket':{'operation':'socket(AF_UNIX, SOCK_STREAM)','errno':1,'name':'EPERM','bind_attempted':False},
  'cpu_virtualization_flags_absent':['vmx','svm','ept','vpid','npt'],'hypervisor_flag_present':True},
 'system_libc_replaced':False,'sandbox_configuration_changed':False,'namespace_privilege_changes':False
})
omit=[record(p) for p in sorted((SRC/'validation').iterdir()) if p.is_file() and p.suffix not in ('.log','.c')]
write(DST/'omitted-artifacts.json',{
 'reason':'No extracted native tools, .deb payloads, target/cache trees or executable toolchain payloads are committed.',
 'native_deb_count':len(plan),'native_deb_bytes':sum(p['Size'] for p in plan),
 'native_deb_bindings':'package-lock.json + authenticated full index data + verified-downloads/extractions receipts',
 'validation_generated_objects_and_executables':omit,
 'rustup_installer':'rust-restore/inputs.json records URL, SHA256 and size; executable omitted',
 'native_tool_and_firmware_hashes':'experimental-native/native-environment.json'
})
write(DST/'provenance.json',{
 'record_kind':'posthoc evidence archive assembled from retained restoration experiment outputs',
 'native_source_directory':str(SRC),'rust_source_directory':str(RUST),
 'private_native_prefix':str(BASE/'native-tools/root'),
 'archive_scope':'Only private-toolchain restoration; no new kernel build/boot claim is made by these paused-tool probes.',
 'native_restoration_commands':[{'argv':['python3',str(SRC/'restore.py')],'cwd':str(BASE)},
                                {'argv':['python3',str(SRC/'restore.py'),'--extract'],'cwd':str(BASE)}],
 'native_controller_scope':'Original command receipts are retained byte-for-byte. Initial prepare receipts have the cwd logging error documented in controller-cwd-correction.json. Final experimental restore.py includes the subsequent correction and is not claimed as identical to initial prepare source.',
 'validation_scope':'Actual argv, selected explicit environment, raw statuses, durations and logs retained in validation-results.json. Inline validation controller source was not separately retained.',
 'signed_snapshot':'https://snapshot.ubuntu.com/ubuntu/20260828T000000Z/',
 'signature_trust_root':{'system_public_keyring_original_path':'/usr/share/keyrings/ubuntu-archive-keyring.gpg',
  'archive_path':'signatures/ubuntu-archive-keyring.gpg','sha256':'80a36b0a6de2f69f49d2df75ef473ccde121e9e190b9ea01d20a4f63778d5c31',
  'validsig_fingerprint':'F6ECB3762474EDA9D21B7022871920D1991BC93C'},
 'package_install_method':'curl verified signed package metadata -> dpkg-deb --extract into task-private prefix; no maintainer scripts',
 'system_install_attempt':'before/ retains parent prepare-host --apt failure100; later private restoration did not retry/change sandbox',
 'source_script_status':'Experimental recovery evidence, not a production installer or guarantee of completeness on another host.'
})
copy(Path(__file__),DST/'package-evidence.py')
print(json.dumps({'archive':str(DST),'selected_packages':len(plan),'signed_indexes':len(indexes),'rust_commands':len(rust_rows),'native_deb_bytes':sum(p['Size'] for p in plan)},indent=2))
