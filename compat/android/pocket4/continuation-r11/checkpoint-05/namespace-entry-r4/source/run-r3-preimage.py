#!/usr/bin/env python3
"""Run exact owned headless probes without changing commercial apps or policies."""
from pathlib import Path
import argparse, datetime, fcntl, hashlib, json, os, re, stat, subprocess, types
ACT = Path('/home/alex/work/pocket4-app-production-20261104-r10/deployment-preparation/activation-after-01.json')
ACT_SHA = '7e490c14586d891f6b121341f879f41c955414c9122e3a68053f04665c12e615'
PINS = {
 '/home/alex/work/pocket4-framework-epoch-20261104-r10/framework_epoch.py': 'f43f766f19a151d7d33ecd0c99c2e81f832fce7dcb1804e5c774e833066a6288',
 '/usr/local/bin/android-app': 'eb24b1b0eefb275025d10647ccf218f9395b1f74cf6d912aaabf384210d1aa66'}
PROBES = {
 'owner': ('local.pocket4.fdownerprobe.r11', 'local.pocket4.fdownerprobe.ProbeInstrumentation', 'x86_64', 11),
 'signal': ('org.droidloom.signalprobe', 'org.droidloom.signalprobe.SignalProbeInstrumentation', 'arm64-v8a', 1),
 'signal-r3': ('org.droidloom.signalprobe.r3', 'org.droidloom.signalprobe.r3.SignalProbeInstrumentation', 'arm64-v8a', 3)}
def digest(data): return hashlib.sha256(data).hexdigest()
def write(path, value):
 raw=value if isinstance(value,bytes) else (json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode()
 fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
 with os.fdopen(fd,'wb') as f: f.write(raw);f.flush();os.fsync(f.fileno())
 return digest(raw)
def load_module(path):
 raw=Path(path).read_bytes();assert digest(raw)==PINS[path],'helper changed'
 module=types.ModuleType('owned_probe_'+str(len(path)));module.__file__=path
 exec(compile(raw,path,'exec'),module.__dict__);return module
def main():
 parser=argparse.ArgumentParser()
 parser.add_argument('phase',choices=('install','run','remove','reconcile'))
 parser.add_argument('--kind',choices=tuple(PROBES),required=True)
 for name in ('root','step'):parser.add_argument('--'+name,required=True)
 for name in ('apk','apk-sha256','nonce','case'):parser.add_argument('--'+name)
 args=parser.parse_args();assert os.geteuid()==0
 assert re.fullmatch(r'[a-z0-9_-]{2,64}',args.step)
 root=Path(args.root);assert root.parent==Path('/home/alex/work') and root.name.startswith('pocket4-owned-')
 os.umask(0o077);root.mkdir(mode=0o700,exist_ok=True)
 out=root/args.step;out.mkdir(mode=0o700)
 package,instrumentation,abi,version=PROBES[args.kind]
 report={'phase':args.phase,'kind':args.kind,'package':package,'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'action_attempted':False,'outcome_unknown':False,'commands':[]}
 write(out/'claim.json',report);lock=None
 try:
  lock=os.open('/run/lock/android-digitalis-actions.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
  info=os.fstat(lock);assert stat.S_ISREG(info.st_mode) and info.st_nlink==1 and info.st_uid==0
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  raw=ACT.read_bytes();assert digest(raw)==ACT_SHA,'activation changed'
  act=json.loads(raw);epoch=load_module('/home/alex/work/pocket4-framework-epoch-20261104-r10/framework_epoch.py');app=load_module('/usr/local/bin/android-app')
  epoch.require_unchanged(act['framework_epoch'],action_attempted=False)
  init,env,status=app.discover()
  assert init==act['framework_epoch']['binding']['processes']['init']['host_pid'] and status['host_pid']==act['status']['host_pid']
  base=['/usr/bin/nsenter','-t',str(init),'-m','-p','-u','-i','/system/bin/env']+[k+'='+env[k] for k in sorted(env)]+['/system/xbin/su','2000','/system/bin/timeout','-k','2']
  report.update(framework_epoch_sha256=act['framework_epoch']['sha256'],activation_sha256=ACT_SHA)
  def command(name,argv,data=None,mutation=False,timeout=25):
   epoch.require_unchanged(act['framework_epoch'],action_attempted=report['action_attempted'])
   if mutation:
    report.update(action_attempted=True,outcome_unknown=True)
    write(out/(name+'-attempt.json'),{'argv':argv,'time':datetime.datetime.now(datetime.timezone.utc).isoformat()})
   p=subprocess.run(base+[str(timeout)]+argv,input=data,capture_output=True,timeout=timeout+7)
   report['commands'].append({'name':name,'argv':argv,'returncode':p.returncode,'stdout_sha256':write(out/(name+'.stdout'),p.stdout),'stderr_sha256':write(out/(name+'.stderr'),p.stderr)})
   epoch.require_unchanged(act['framework_epoch'],action_attempted=report['action_attempted'])
   assert p.returncode==0,(name,p.returncode,p.stderr.decode(errors='replace')[-1200:])
   return p.stdout.decode('utf-8','strict')
  def packages(name):
   text=command(name,['/system/bin/cmd','package','list','packages','-U','--show-versioncode','--user','0']);rows={}
   for line in text.splitlines():
    m=re.fullmatch(r'package:([^ ]+) versionCode:(\d+) uid:(\d+)',line.strip())
    assert m and m[1] not in rows,'unparsed/duplicate package';rows[m[1]]={'version_code':int(m[2]),'uid':int(m[3])}
   return rows
  before=packages('packages-before');report['package_count_before']=len(before)
  if args.phase=='install':
   assert package not in before,'owned package exists; replacement prohibited'
   assert args.apk and re.fullmatch(r'[0-9a-f]{64}',args.apk_sha256 or '')
   data=Path(args.apk).read_bytes();assert digest(data)==args.apk_sha256,'APK changed'
   result=command('install',['/system/bin/cmd','package','install','-t','--user','0','--abi',abi,'-S',str(len(data))],data=data,mutation=True,timeout=40)
   assert result.strip()=='Success',('install not confirmed',result)
   after=packages('packages-after');assert after.get(package,{}).get('version_code')==version
   assert {k:v for k,v in after.items() if k!=package}==before
   report.update(installed_identity=after[package],apk_sha256=args.apk_sha256,all_preexisting_package_identities_preserved=True,outcome_unknown=False)
   write(root/'install-verified.json',report)
  else:
   install=json.loads((root/'install-verified.json').read_text())
   assert install['package']==package and before.get(package)==install['installed_identity']
   paths=command('package-path',['/system/bin/cmd','package','path',package]).splitlines()
   assert len(paths)==1 and paths[0].startswith('package:/data/app/')
   apk_path=paths[0][len('package:'):];assert '..' not in Path(apk_path).parts
   actual=digest((Path('/proc')/str(init)/'root'/apk_path.lstrip('/')).read_bytes());assert actual==install['apk_sha256'],'installed APK changed'
   report.update(installed_identity=install['installed_identity'],apk_sha256=actual)
   if args.phase=='run':
    assert re.fullmatch(r'[a-zA-Z0-9_-]{12,80}',args.nonce or '')
    argv=['/system/bin/am','instrument','-w','-r','-e','nonce',args.nonce]
    if args.case is not None:
     assert args.kind in ('signal','signal-r3') and args.case in ('svc','smc-handler','smc-default','smc-mask-edit')
     argv+=['-e','case',args.case]
    argv+=[package+'/'+instrumentation]
    result=command('instrument',argv,mutation=True,timeout=35)
    report['instrumentation_output']=result
    assert 'INSTRUMENTATION_CODE:' in result,'instrumentation completion unproven'
    assert packages('packages-after')==before,'package identities changed during probe'
    report['all_package_identities_preserved']=True
   elif args.phase=='remove':
    result=command('uninstall-owned-only',['/system/bin/cmd','package','uninstall','--user','0',package],mutation=True,timeout=40)
    assert result.strip()=='Success',('owned cleanup not confirmed',result)
    after=packages('packages-after');assert package not in after and after=={k:v for k,v in before.items() if k!=package}
    report['only_exact_owned_package_removed']=True
   else:report['application_exit_info']=command('exit-info',['/system/bin/dumpsys','activity','exit-info',package])
  report.update(ok=True,outcome_unknown=False)
 except Exception as error:report.update(ok=False,error=repr(error))
 finally:
  if lock is not None:os.close(lock)
 report['finished_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
 write(out/'result.json',report);print(json.dumps(report,ensure_ascii=False),flush=True)
 return 0 if report.get('ok') else 1
if __name__=='__main__':raise SystemExit(main())
