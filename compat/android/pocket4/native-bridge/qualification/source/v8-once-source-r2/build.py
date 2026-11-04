"""Build an owned V8 probe with durable default-signal nonce claim; no Android install or Main changes."""
from pathlib import Path
import hashlib,json,os,re,resource,struct,subprocess,zipfile,sys
ROOT=Path(__file__).resolve().parent
WORK=Path('/srv/pocket4-native-inputs/probe-preconditions')
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def main():
 os.umask(0o077);os.sched_setaffinity(0,{6});resource.setrlimit(resource.RLIMIT_CORE,(0,0))
 attempt=int(sys.argv[1]) if len(sys.argv)>1 else 1;assert 1<=attempt<=4
 B=ROOT/('build-attempt-'+str(attempt));B.mkdir(mode=0o700)
 commands=[];report={'state':'BUILDING','commands':commands,'actual_android_executed':False,'CPU':[6]}
 def save():(B/'build-result.json').write_text(json.dumps(report,indent=2)+'\n')
 try:
  old=WORK/'native-jni-oracle-v6/build.py';assert sha(old)=='0e77ac152e7fd91cb6e5171e189394fbdd4c30f6e62af919c7ca31dcab5ceb59'
  scope={'__name__':'pinned_v6_definitions','__file__':str(old)};exec(compile(old.read_bytes(),str(old),'exec'),scope)
  pins=scope['TOOL_PINS'];assert all(sha(p)==h for p,h in pins.items())
  assert sha(scope['TEST_KEY'])==scope['TEST_KEY_SHA'] and sha(scope['LIBC'])==scope['LIBC_SHA']
  helperpath=WORK/'native-jni-oracle-v7-r2/static_helpers.py';assert sha(helperpath)=='9e2fcbdf7ded4db0dcbd2bbe25b50884a238329d7afcbd34c680d9a3d2044f0b'
  helper={};exec(compile(helperpath.read_bytes(),'pinned-static-helper','exec'),helper)
  source_names=['native_probe.c','src/local/pocket4/nativeoraclev8/MainActivity.java','AndroidManifest.xml','build.py']
  initial={n:sha(ROOT/n) for n in source_names}
  controls={
   'native-jni-oracle-v4/build-attempt-1/nativeoraclev4.apk':'74c566cefda4877e1b156394a5f8a38e043db95cd33780fd8a45021f9cb6704a',
   'native-jni-oracle-v5/build-attempt-1/nativeoraclev5.apk':'4cea86be78ba70aba56f5a37bbfe73be9ab10af958cd528a0015fba45f4ced95',
   'native-jni-oracle-v6/build-attempt-2/nativeoraclev6.apk':'8706242bc7d24bb2f4fc1c0b7358d3c1839b36b8be71470e6f323c5c1b5b43fe'}
  # Prior APKs are read only; no rebuild or mutation of previous controls.
  for p,h in controls.items():assert sha(WORK/p)==h,(p,sha(WORK/p),h)
  clang=scope['CLANG_DIR'];jdk=scope['JDK'];sdk=scope['SDK'];r8=scope['R8'];aapt=scope['AAPT'];align=scope['ALIGN'];signer=scope['SIGNER']
  for n in ['classes','dex','res','lib/arm64-v8a']:(B/n).mkdir(mode=0o700,parents=True)
  env={'PATH':str(jdk)+':/usr/bin:/bin','LANG':'C','LC_ALL':'C','TMPDIR':str(B)}
  def run(name,args,timeout=90):
   args=list(map(str,args));p=subprocess.run(args,cwd=B,env=env,capture_output=True,timeout=timeout)
   (B/(name+'.stdout')).write_bytes(p.stdout);(B/(name+'.stderr')).write_bytes(p.stderr)
   commands.append({'name':name,'argv':args,'returncode':p.returncode,'stdout_sha256':sha(B/(name+'.stdout')),'stderr_sha256':sha(B/(name+'.stderr'))});save()
   assert p.returncode==0,(name,p.stderr.decode(errors='replace')[-4000:]);return p.stdout.decode()
  lib=B/'lib/arm64-v8a/libnativeoraclev8.so'
  run('compile-arm64',[clang/'clang','-target','aarch64-linux-android24','-shared','-nostdlib','-fPIC','-fuse-ld=lld','-Wl,--build-id=sha1,--no-undefined,--allow-shlib-undefined,--no-as-needed,--soname,libnativeoraclev8.so,-z,noexecstack,-z,relro,-z,now','-ffreestanding','-fno-builtin','-fno-stack-protector','-fvisibility=hidden','-mno-outline-atomics','-Wall','-Wextra','-Werror','-O1',ROOT/'native_probe.c',scope['LIBC'],'-o',lib])
  run('compile-host-control',[clang/'clang','-DHOST_CONTROL','-Wall','-Wextra','-Werror','-O1',ROOT/'native_probe.c','-o',B/'host-control'])
  rows=[json.loads(x) for x in run('host-control',[B/'host-control'],10).splitlines()]
  assert len(rows)==6
  for c,row in enumerate(rows[:5]):assert row['case']==c and row['status']==0 and row['fields'][0:2]==[1,c] and row['fields'][3]==os.getuid()
  assert rows[5]=={'default_child_signaled':1,'default_child_signal':14}
  report['host_control']={'cases':5,'all_pass':True,'default_child_signal':14,'actual_android_proof':False,'data':rows}
  java=ROOT/'src/local/pocket4/nativeoraclev8/MainActivity.java'
  run('javac',[jdk/'javac','-J-XX:ActiveProcessorCount=1','-J-XX:+UseSerialGC','-J-Xmx512m','-source','8','-target','8','-bootclasspath',sdk,'-d',B/'classes',java])
  run('d8',[jdk/'java','-XX:ActiveProcessorCount=1','-XX:+UseSerialGC','-Xmx512m','-cp',r8,'com.android.tools.r8.D8','--lib',sdk,'--min-api','24','--output',B/'dex',*sorted((B/'classes').rglob('*.class'))])
  run('aapt-package',[aapt,'package','-f','-M',ROOT/'AndroidManifest.xml','-S',B/'res','-I',sdk,'-F',B/'unsigned.apk'])
  with zipfile.ZipFile(B/'unsigned.apk','a',compression=zipfile.ZIP_STORED) as z:z.write(B/'dex/classes.dex','classes.dex');z.write(lib,'lib/arm64-v8a/libnativeoraclev8.so')
  run('align',[align,'-f','4',B/'unsigned.apk',B/'aligned.apk']);apk=B/'nativeoraclev8.apk'
  run('sign',[signer,'sign','--ks',scope['TEST_KEY'],'--ks-pass','env:DROIDLOOM_OWNED_TEST_KEY_PASSWORD','--out',apk,B/'aligned.apk'])
  sig=run('signature',[signer,'verify','--verbose','--print-certs',apk]);run('alignment',[align,'-c','4',apk]);badging=run('badging',[aapt,'dump','badging',apk]);permissions=run('permissions',[aapt,'dump','permissions',apk]);run('manifest',[aapt,'dump','xmltree',apk,'AndroidManifest.xml'])
  info=run('ELF',['/usr/bin/readelf','-h','-d','--dyn-syms','-l','-r','-V','--wide',lib]);run('disassembly',[clang/'llvm-objdump','-d',lib])
  data=lib.read_bytes();sections=helper['elf_sections'](data);tables=helper['elf_symbols'](data,sections)
  assert sha(ROOT/'native_probe.c')=='be03493895ef5f6296837cb591eb93f7621f4b9fbdef390e39a6de2d15a0ed22'
  assert sha(lib)=='ee3152f3edb1a86dea09ee9e6446a1cdada8586ab826d3c72de6f0085c08839a', 'native probe ELF changed; Java lifecycle fix must be isolated'
  assert data[:6]==b'\x7fELF\x02\x01' and struct.unpack_from('<H',data,16)[0]==3 and struct.unpack_from('<H',data,18)[0]==183
  exports=[s for s in tables['.dynsym'] if s['bind'] in [1,2] and s['index']];imports=[s for s in tables['.dynsym'] if s['bind'] in [1,2] and not s['index']]
  symbols=['Java_local_pocket4_nativeoraclev8_MainActivity_'+x for x in ['runCase','readField','queryAlarm']]
  needed=re.findall(r'\(NEEDED\).*Shared library: \[(.*?)\]',info)
  assert sorted(x['name'] for x in exports)==sorted(symbols) and [x['name'] for x in imports]==['sigaction'] and needed==['libc.so']
  assert re.search(r'\bUND\s+sigaction@LIBC\b',info) and 'BIND_NOW' in info
  po=struct.unpack_from('<Q',data,32)[0];ps,pc=struct.unpack_from('<HH',data,54);ph=[struct.unpack_from('<IIQQQQQQ',data,po+i*ps) for i in range(pc)]
  assert not any(p[0]==1 and p[1]&3==3 for p in ph) and any(p[0]==0x6474e551 and p[1]==6 for p in ph) and any(p[0]==0x6474e552 for p in ph)
  with zipfile.ZipFile(apk) as z:
   entries=z.namelist();assert [x for x in entries if x.startswith('lib/')]==['lib/arm64-v8a/libnativeoraclev8.so'] and z.read('lib/arm64-v8a/libnativeoraclev8.so')==data
   assert all(x in ['AndroidManifest.xml','classes.dex','lib/arm64-v8a/libnativeoraclev8.so'] or x.startswith('META-INF/') for x in entries)
   dex=z.read('classes.dex');d=helper['dex_native_methods'](dex)
   assert d['classes']==['Llocal/pocket4/nativeoraclev8/MainActivity;'] and {m['name']:m['signature'] for m in d['native_methods']}=={'runCase':'(I)J','readField':'(I)J','queryAlarm':'()J'}
   assert all(m['access']&0x108==0x108 and m['code_offset']==0 for m in d['native_methods'])
  assert 'uses-permission:' not in permissions and "package: name='local.pocket4.nativeoraclev8' versionCode='8'" in badging and "native-code: 'arm64-v8a'" in badging
  assert 'Signer #1 certificate SHA-256 digest: '+scope['SIGNER_CERT_SHA'] in sig and 'Verified using v2 scheme (APK Signature Scheme v2): true' in sig and 'Verified using v3 scheme (APK Signature Scheme v3): true' in sig
  assert all(sha(ROOT/n)==h for n,h in initial.items()) and all(sha(p)==h for p,h in pins.items()) and all(sha(WORK/p)==h for p,h in controls.items())
  report.update(state='BUILT_STATIC_AND_REAL_HOST_CONTROLS_PASS_ANDROID_UNRUN',APK={'path':str(apk),'sha256':sha(apk),'bytes':apk.stat().st_size},ELF={'sha256':sha(lib),'DT_NEEDED':needed,'imports':imports,'exports':exports,'NX_RELRO_NOW_no_WX':True},DEX={'sha256':hashlib.sha256(dex).hexdigest(),**d},source_sha256=initial,tools_sha256={str(p):h for p,h in pins.items()},stock_libc={'path':str(scope['LIBC']),'sha256':scope['LIBC_SHA'],'packaged':False},prior_controls=controls,prior_controls_unchanged=True,JNI_env_functions_used=False)
 except Exception as e:report.update(state='FAILED',error=repr(e))
 save();print(json.dumps({'state':report['state'],'error':report.get('error'),'APK':report.get('APK')}),flush=True)
 return 0 if report['state'].startswith('BUILT_') else 1
if __name__=='__main__':raise SystemExit(main())
