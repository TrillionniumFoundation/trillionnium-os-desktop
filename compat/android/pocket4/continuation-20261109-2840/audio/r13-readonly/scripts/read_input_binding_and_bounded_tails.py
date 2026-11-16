import pathlib,json,hashlib,subprocess,os,datetime
R=pathlib.Path('/data/pocket4-audio-source316-offload-20261108-8b88-r1')
C=R/'control/full-desktop-r13';Q=R/'qualification/full-desktop-r13';S=R/'work/aosp-source';recipe=R/'recipe-sdk33-zygote-r1'
expected=json.loads("[{\"relative\":\"prebuilts/sdk/33/module-lib/android.jar\",\"bytes\":64100854,\"sha256\":\"97dd121af27c9181e853cc4bfa636b5f5780c4776d6fe51b02fb23d8263b046a\",\"git_blob\":\"c6b9097eb2581a2f9037677cc3c752146e3603d7\"},{\"relative\":\"prebuilts/sdk/33/module-lib/core-for-system-modules.jar\",\"bytes\":1416118,\"sha256\":\"2f8ee35dfec8e2212700e76acb321ebc182d09c323096f8f1b451625c2982bb0\",\"git_blob\":\"932b33b485d344ff9ebfcaaaf82fb38d42981073\"},{\"relative\":\"system/zygote/zygote-proc-macros/src/lib.rs\",\"bytes\":2099,\"sha256\":\"f6d969824bc83e2e36c525ee7dbbf0416f68f31018ddf83764983fe7c7e79752\",\"git_blob\":\"bbabb3a21850e54039e7344ae607d8fa2a718d20\"},{\"relative\":\"system/zygote/zygote-proc-macros/src/marshal.rs\",\"bytes\":12515,\"sha256\":\"4b729a37edf7c502192be467b102e1bbc7e8537ae3e65809c7b9363d874ad507\",\"git_blob\":\"5e5cae79e8ec32e6ac4542592bac0cdd26e8b46d\"},{\"relative\":\"system/zygote/zygote-proc-macros/src/unmarshal.rs\",\"bytes\":14730,\"sha256\":\"ba1ba8608bf208ec82597abdbb51fd417bf5db920e99355a376c7d22f0491e1d\",\"git_blob\":\"d28ab3d7a3d42f35ed7a852c516509ac03aed174\"},{\"relative\":\"system/zygote/zygote-proc-macros/src/utils.rs\",\"bytes\":2255,\"sha256\":\"a54d250213d0caa452736c73c3b346c1d17b537c3747defd44c3f01ad45bce22\",\"git_blob\":\"1b9ec49955c93ed240ef62ec86a3bd526eb9a76c\"},{\"relative\":\"system/zygote/zygote-sys/src/android.rs\",\"bytes\":3493,\"sha256\":\"9150fb7df27014d5f74e9185d74dceec4781e1b8bf551095893982e5ba81ff87\",\"git_blob\":\"0e4117588942250f215cdc905024d2d4a32ee316\"},{\"relative\":\"system/zygote/zygote-sys/src/lib.rs\",\"bytes\":70506,\"sha256\":\"404195052722d7134c667bd9bfdce0630af44cb17040e06db81bb8544f64a259\",\"git_blob\":\"4f85d0c67e65ea0889e33aa8ba8aee330addacb7\"},{\"relative\":\"system/zygote/zygote-sys/src/libc_fill.rs\",\"bytes\":6003,\"sha256\":\"c1ee40f84d867e81d465c61b14604dd2dc2f2aab7aec939e194d6137c02c9ca2\",\"git_blob\":\"73ce292cd64527d7c62d9648593043267db79e6a\"},{\"relative\":\"system/zygote/zygote-sys/src/procfs.rs\",\"bytes\":9726,\"sha256\":\"c489f93454daa7ad680e907083177db13bac55ec9a2ec8497174bacca1187e2d\",\"git_blob\":\"18e0a6e9be661b512decb26afc21970d907557d6\"}]")
def ref(p):
 st=p.stat();h=hashlib.sha256();g=hashlib.sha1();g.update(b'blob '+str(st.st_size).encode()+bytes([0]))
 with p.open('rb') as f:
  while True:
   b=f.read(1024*1024)
   if not b:break
   h.update(b);g.update(b)
 return {'path':str(p),'bytes':st.st_size,'sha256':h.hexdigest(),'git_blob':g.hexdigest()}
out={'observed_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'scope':'single follow-up for already-read Audio13 original input binding; no job polling'}
config=json.loads((C/'build-inputs.json').read_bytes());out['source_recipe_commit']=config['source_recipe_commit'];out['source_recipe_tree']=config['source_recipe_tree'];out['normal_tools']=config['normal_tools'];out['source_delta']=config.get('source_delta');out['sdk_file_count']=len(config['original_SDK_files']);out['zygote_file_count']=len(config['original_zygote_files'])
lockp=recipe/'android/manifest/audio-bridge-source-lock.json';out['lock']=ref(lockp);lock=json.loads(lockp.read_bytes());rows=sorted([{'path':x['path'],'name':x['name'],'commit':x['commit']} for x in lock['projects']],key=lambda x:x['path']);digest=hashlib.sha256(json.dumps(rows,sort_keys=True,separators=(',',':')).encode()).hexdigest();out['project_revisions']={'count':len(rows),'tuple_sha256':digest,'same_all_430_as_b555':digest=='c3bf812f91399620e069ada6f0fca323fae7de82c0fd5c2b05e900d1fce72d4a'}
needed={'prebuilts/sdk':['33/module-lib/android.jar','33/module-lib/core-for-system-modules.jar'],'system/zygote':['zygote-sys','zygote-proc-macros']}
out['original_provider_selector_check']=[]
for x in lock['projects']:
 if x['path'] in needed:
  out['original_provider_selector_check'].append({'path':x['path'],'commit':x['commit'],'required_selectors':needed[x['path']],'all_required_selectors_present':all(v in x['sparse_paths'] for v in needed[x['path']]),'selector_count':len(x['sparse_paths'])})
env={**os.environ,'GIT_OPTIONAL_LOCKS':'0','GIT_NO_LAZY_FETCH':'1','GIT_TERMINAL_PROMPT':'0'}
out['actual_heads']=[]
for p in [recipe,S/'prebuilts/sdk',S/'system/zygote']:
 r=subprocess.run(['/usr/bin/git','-C',str(p),'rev-parse','HEAD'],capture_output=True,text=True,timeout=15,env=env);out['actual_heads'].append({'path':str(p),'exit_code':r.returncode,'stdout':r.stdout.strip(),'stderr':r.stderr})
out['actual_provider_files']=[]
for e in expected:
 x=ref(S/e['relative']);x['relative']=e['relative'];x['matches_independent_original_pin']=all(x[k]==e[k] for k in ('bytes','sha256','git_blob'));out['actual_provider_files'].append(x)
manifest=S/'.droidloom-source-manifest.json';out['materialized_manifest']=ref(manifest)
for name in ('lib.rs','android.rs'):
 p=recipe/('tools/droidloom-source/src/lib.rs' if name=='lib.rs' else 'tools/droidloom-update/src/android.rs');text=p.read_text();out.setdefault('recipe_provider_gates',[]).append({'file':ref(p),'contains_sdk33_modulelib_path':'33/module-lib/android.jar' in text,'contains_zygote_sys':'zygote-sys' in text,'contains_zygote_proc_macros':'zygote-proc-macros' in text})
cmds=Q/'commands';out['command_files']=[]
if cmds.is_dir():
 for p in sorted(cmds.iterdir()):
  if p.is_file():
   st=p.stat();out['command_files'].append({'name':p.name,'bytes':st.st_size})
   if 'normal-full-audio-apex' in p.name and ('stdout' in p.name or 'stderr' in p.name):
    with p.open('rb') as f:f.seek(max(0,st.st_size-8192));b=f.read(8192)
    out.setdefault('bounded_normal_log_tails',[]).append({'path':str(p),'file_bytes_at_read':st.st_size,'tail_bytes':len(b),'tail_sha256':hashlib.sha256(b).hexdigest(),'text':b.decode('utf8','replace')})
print(json.dumps(out,ensure_ascii=False))
