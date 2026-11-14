#!/usr/bin/env python3
"""Replay all public producer files into a new independent recipe checkout."""
import argparse,hashlib,json,os,stat,subprocess,time
from pathlib import Path
def need(v,m):
 if not v:raise RuntimeError(m)
def digest(b):return hashlib.sha256(b).hexdigest()
def blob(b):return hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()
def verify(b,row):need(len(b)==row['bytes']and digest(b)==row['sha256']and blob(b)==row['git_blob'],'whole original Git blob mismatch: '+row['path'])
def safe(name):
 p=Path(name);need(not p.is_absolute()and str(p)==name and '..'not in p.parts and '.git'not in p.parts,'source path escapes exact recipe');return p
def install(root,row,raw):
 p=root/safe(row['path']);p.parent.mkdir(parents=True,exist_ok=True)
 if row['mode']=='120000':
  target=raw.decode();need(not Path(target).is_absolute()and os.path.commonpath([str(root),os.path.normpath(str(p.parent/target))])==str(root),'source alias escapes exact recipe');p.symlink_to(target)
 else:
  need(row['mode']in('100644','100755'),'unexpected source mode')
  with p.open('xb')as f:f.write(raw)
  p.chmod(int(row['mode'],8)&0o777)
def actual(root,row):
 p=root/safe(row['path']);st=p.lstat();need(st.st_nlink==1,'unexpected source hardlink')
 if row['mode']=='120000':need(stat.S_ISLNK(st.st_mode),'source alias kind differs');b=os.readlink(p).encode()
 else:need(stat.S_ISREG(st.st_mode)and stat.S_IMODE(st.st_mode)==int(row['mode'],8)&0o777,'source mode differs');b=p.read_bytes()
 verify(b,row)
def fresh_destination(path,protected):
 path=path.absolute();need(path.resolve()==path,'output or parent is an alias');need(not os.path.lexists(path),'output must be absent')
 for root in protected:
  root=root.resolve();need(path!=root and root not in path.parents,'output is inside protected input')
 return path
def run(capsule,work,report):
 capsule=capsule.resolve();work=fresh_destination(work,[capsule]);report=fresh_destination(report,[capsule,work]);need(report not in work.parents,'work cannot be inside report');m=json.loads((capsule/'manifest.json').read_bytes());base=json.loads((capsule/'base-files.json').read_bytes());head=json.loads((capsule/'head-files.json').read_bytes());contract=m['replay_contract'];need(len(base)==contract['base_files'] and len(head)==contract['head_files'] and len(m['files'])==contract['changed_files'],'complete actual recipe inventory required');need(len(base)==len({x['path']for x in base}) and len(head)==len({x['path']for x in head}),'unique exact source paths required')
 for key in('base','head'):
  raw=m[key]['raw_commit'].encode();need(hashlib.sha1(b'commit '+str(len(raw)).encode()+b'\0'+raw).hexdigest()==m[key]['commit']and raw.splitlines()[0]==('tree '+m[key]['tree']).encode(),'original commit tree identity differs')
 changed={r['path']:r for r in m['files']};work.mkdir(mode=0o700,parents=True)
 env=dict(os.environ,GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL='/dev/null',GIT_CONFIG_SYSTEM='/dev/null',GIT_OPTIONAL_LOCKS='0')
 def git(args):
  p=subprocess.run(['git','-c','core.hooksPath=/dev/null',*args],cwd=work,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=120,umask=0o022);need(p.returncode==0,'replay Git failed '+str(args)+': '+p.stderr.decode(errors='replace'));return p.stdout
 for row in base:
  location='preimages'if row['path']in changed else'base-support';raw=(capsule/location/safe(row['path'])).read_bytes();verify(raw,row);install(work,row,raw)
 git(['init','--quiet','--template=']);git(['config','core.filemode','true']);git(['add','--force','--all']);before_tree=git(['write-tree']).decode().strip();need(before_tree==m['base']['tree'],'complete base root tree did not reconstruct')
 patch=(capsule/safe(m['patch']['path'])).read_bytes();need(len(patch)==m['patch']['bytes']and digest(patch)==m['patch']['sha256'],'complete patch differs');git(['apply','--check',str(capsule/safe(m['patch']['path']))]);git(['apply',str(capsule/safe(m['patch']['path']))])
 for row in head:actual(work,row)
 names={str(p.relative_to(work))for p in work.rglob('*')if p.relative_to(work).parts[0]!='.git' and(p.is_file()or p.is_symlink())};need(names=={r['path']for r in head},'complete head file set differs');git(['add','--force','--all']);after_tree=git(['write-tree']).decode().strip();need(after_tree==m['head']['tree'],'complete current head root tree did not reconstruct')
 result={'schema':'audio-current-complete-public-producer-replay-v2','state':'EXACT_BASE_AND_CURRENT_HEAD_ROOT_TREES_REPLAYED','base_files':len(base),'head_files':len(head),'changed_files':len(changed),'preimages':sum(x['pre']is not None for x in changed.values()),'base_root_tree':before_tree,'head_root_tree':after_tree,'original_commit_objects_verified':True,'full_repository_root_tree_reconstructed':True,'Git_history_graph_reconstructed':False,'patch_sha256':m['patch']['sha256'],'Rust_tests_run':False,'Android_starts':0,'runtime_qualified':False,'production_ready':False,'finished_ns':time.time_ns()}
 report.parent.mkdir(parents=True,exist_ok=True)
 with report.open('x')as f:json.dump(result,f,sort_keys=True,indent=2);f.write('\n')
 print(json.dumps(result,sort_keys=True));return result
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--capsule',type=Path,required=True);p.add_argument('--work',type=Path,required=True);p.add_argument('--report',type=Path,required=True);a=p.parse_args();run(a.capsule,a.work,a.report)
