#!/usr/bin/env python3
"""Read-only installed-app inventory bound to the verified Pocket4 R16 epoch."""
import datetime, hashlib, json, os, pathlib, re, subprocess, types
ROOT = pathlib.Path('/home/alex/work/pocket4-app-production-20261104-r11')
ACT = pathlib.Path('/home/alex/work/pocket4-app-production-20261104-r10/deployment-preparation/activation-after-01.json')
ACT_SHA = '7e490c14586d891f6b121341f879f41c955414c9122e3a68053f04665c12e615'
PINS = {
 '/home/alex/work/pocket4-framework-epoch-20261104-r10/framework_epoch.py': 'f43f766f19a151d7d33ecd0c99c2e81f832fce7dcb1804e5c774e833066a6288',
 '/usr/local/bin/android-app': 'eb24b1b0eefb275025d10647ccf218f9395b1f74cf6d912aaabf384210d1aa66',
}
def sha(data): return hashlib.sha256(data).hexdigest()
def write(path, raw):
 raw = raw if isinstance(raw, bytes) else (json.dumps(raw,ensure_ascii=False,indent=2)+'\n').encode()
 fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
 with os.fdopen(fd,'wb') as f: f.write(raw);f.flush();os.fsync(f.fileno())
 return sha(raw)
def load(path):
 raw=pathlib.Path(path).read_bytes()
 if sha(raw)!=PINS[path]: raise RuntimeError('SOURCE_CHANGED:'+path)
 mod=types.ModuleType('p4_inventory_'+str(len(path)));mod.__file__=path
 exec(compile(raw,path,'exec'),mod.__dict__)
 return mod
def main():
 if os.geteuid()!=0: raise RuntimeError('ROOT_REQUIRED_FOR_NAMESPACE')
 os.umask(0o077)
 ROOT.mkdir(mode=0o700,exist_ok=True)
 out=ROOT/'inventory-01';out.mkdir(mode=0o700)
 raw=ACT.read_bytes()
 if sha(raw)!=ACT_SHA: raise RuntimeError('ACTIVATION_CHANGED')
 act=json.loads(raw)
 ep=load('/home/alex/work/pocket4-framework-epoch-20261104-r10/framework_epoch.py')
 app=load('/usr/local/bin/android-app')
 ep.require_unchanged(act['framework_epoch'],action_attempted=False)
 init,env,status=app.discover()
 if init!=act['framework_epoch']['binding']['processes']['init']['host_pid'] or status['host_pid']!=act['status']['host_pid']: raise RuntimeError('DISCOVERY_CHANGED')
 base=['/usr/bin/nsenter','-t',str(init),'-m','-p','-u','-i','/system/bin/env']+[k+'='+env[k] for k in sorted(env)]+['/system/xbin/su','2000','/system/bin/timeout','-k','2','18','/system/bin/cmd','package']
 queries={
  'installed':['list','packages','-U','--show-versioncode','--user','0'],
  'third_party':['list','packages','-3','--user','0'],
  'disabled':['list','packages','-d','--user','0'],
  'launchers':['query-activities','--brief','--user','0','-a','android.intent.action.MAIN','-c','android.intent.category.LAUNCHER'],
 }
 results={};receipts={}
 for name,args in queries.items():
  ep.require_unchanged(act['framework_epoch'],action_attempted=False)
  started=datetime.datetime.now(datetime.timezone.utc).isoformat()
  p=subprocess.run(base+args,capture_output=True,timeout=25)
  receipts[name]={'returncode':p.returncode,'stdout_sha256':write(out/(name+'.stdout'),p.stdout),'stderr_sha256':write(out/(name+'.stderr'),p.stderr),'started_utc':started}
  if p.returncode!=0: raise RuntimeError('PACKAGE_QUERY_FAILED:'+name)
  results[name]=p.stdout.decode('utf-8','strict')
  ep.require_unchanged(act['framework_epoch'],action_attempted=False)
 installed=[]
 for line in results['installed'].splitlines():
  m=re.fullmatch(r'package:([^ ]+) versionCode:(\d+) uid:(\d+)',line.strip())
  if not m: raise RuntimeError('UNPARSED_INSTALLED_ROW:'+line[:160])
  installed.append({'package':m[1],'version_code':int(m[2]),'uid':int(m[3])})
 if len({p['package'] for p in installed})!=len(installed): raise RuntimeError('DUPLICATE_INSTALLED_PACKAGE')
 components=[]
 for line in results['launchers'].splitlines():
  line=line.strip()
  if re.fullmatch(r'[A-Za-z0-9_.]+/[A-Za-z0-9_.$]+',line):components.append(line)
 launcher_packages=sorted({x.split('/')[0] for x in components})
 if not launcher_packages: raise RuntimeError('NO_PARSED_LAUNCHERS')
 known={x['package']:x for x in installed}
 if not set(launcher_packages)<=set(known):raise RuntimeError('LAUNCHER_PACKAGE_NOT_INSTALLED')
 third_party=sorted(l.removeprefix('package:') for l in results['third_party'].splitlines() if l.startswith('package:'))
 disabled=sorted(l.removeprefix('package:') for l in results['disabled'].splitlines() if l.startswith('package:'))
 summary={'schema':'pocket4-current-installed-inventory-v1','observed_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'read_only':True,'framework_epoch_sha256':act['framework_epoch']['sha256'],'activation_sha256':ACT_SHA,'installed_package_count':len(installed),'installed_packages':installed,'launcher_component_count':len(components),'launcher_packages':launcher_packages,'launcher_components':components,'third_party_packages':third_party,'disabled_packages':disabled,'query_receipts':receipts,'complete_package_manager_queries':True,'whole_app_production_ready_inferred':False}
 receipt_sha=write(out/'inventory.json',summary)
 print(json.dumps({'ok':True,'inventory_path':str(out/'inventory.json'),'inventory_sha256':receipt_sha,'summary':summary},ensure_ascii=False))
if __name__=='__main__':main()

