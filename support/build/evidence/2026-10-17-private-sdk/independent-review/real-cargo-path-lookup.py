import hashlib,json,os,pathlib,subprocess,sys
out=pathlib.Path(__file__).resolve().parent/'real-cargo-path-lookup';out.mkdir()
cargo=out.parents[1]/'toolchains/rustup/toolchains/nightly-2026-07-21-x86_64-unknown-linux-gnu/bin/cargo'
home=out/'cargo-home';private=out/'private/bin'; (home/'bin').mkdir(parents=True);private.mkdir(parents=True);(out/'placeholder').mkdir();(out/'home-link').symlink_to(home,target_is_directory=True)
def tool(p,marker,code=0):
 p.write_text('#!/usr/bin/python3\nimport json,sys\nprint(json.dumps('+repr({'selected':marker,'code':code})+'))\nraise SystemExit('+str(code)+')\n');p.chmod(0o755)
tool(home/'bin/cargo-osdk','GLOBAL');tool(private/'cargo-osdk','PRIVATE')
rows=[]
for name,cargohome in [('absolute',str(home)),('absolute-dot',str(home)+'/.'),('absolute-dotdot',str(out)+'/placeholder/../cargo-home'),('absolute-symlink',str(out/'home-link')),('absolute-trailing-slash',str(home)+'/')]:
 env=dict(os.environ,CARGO_HOME=cargohome,PATH=str(private)+':'+cargohome+'/bin:/usr/bin:/bin')
 p=subprocess.run([str(cargo),'osdk','--version'],cwd=out,env=env,capture_output=True,text=True)
 result=json.loads(p.stdout) if p.stdout.strip() else None; rows.append({'name':name,'cargo_home':cargohome,'path':env['PATH'],'code':p.returncode,'result':result,'stderr':p.stderr,'passed':p.returncode==0 and result['selected']=='PRIVATE'})
tool(private/'cargo-osdk','PRIVATE',47)
env=dict(os.environ,CARGO_HOME=str(home),PATH=str(private)+':'+str(home/'bin')+':/usr/bin:/bin');p=subprocess.run([str(cargo),'osdk','--version'],cwd=out,env=env,capture_output=True,text=True);result=json.loads(p.stdout);rows.append({'name':'private-sdk-exit-47-no-global-fallback','cargo_home':str(home),'path':env['PATH'],'code':p.returncode,'result':result,'stderr':p.stderr,'passed':p.returncode==47 and result['selected']=='PRIVATE'})
report={'scope':'real pinned Cargo custom subcommand path lookup only, fake SDKs, no compiler/SDK install/QEMU','cargo':str(cargo),'cargo_sha256':hashlib.sha256(cargo.read_bytes()).hexdigest(),'cases':rows,'all_passed':all(r['passed'] for r in rows)}
(out/'results.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n');print(json.dumps(report,indent=2,sort_keys=True));sys.exit(0 if report['all_passed'] else 1)
