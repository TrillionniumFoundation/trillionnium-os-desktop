function buildBiliR9Player02Controls(h,source,bound,helperFiles,previousPacket,failed01Files){
 const need=(v,m)=>{if(!v)throw Error(m)},pin=s=>({bytes:h.utf8(s).length,sha256:h.sha(s)});
 function canonical(v){return v===null?"null":Array.isArray(v)?"["+v.map(canonical).join(",")+"]":typeof v==="object"?"{"+Object.keys(v).sort().map(k=>JSON.stringify(k)+":"+canonical(v[k])).join(",")+"}":JSON.stringify(v);}
 const p=previousPacket.payload;
 need(h.sha(helperFiles["qa_contract.py"])===p.pins.qa.sha256,"SAME_ACTUAL_R9_QA_SOURCE");
 const runtime=Object.fromEntries(Object.entries(bound.files).filter(([n])=>n.endsWith(".py")));
 const failed=Object.fromEntries(["controls_reveal.py","playback_controls.py"].map(n=>[n,failed01Files[n]]));
 const payload={old_files:p.old_files,new_files:runtime,qa_source:helperFiles["qa_contract.py"],adapter_source:helperFiles["qa_adapter.py"],
  failed01_validators:failed,pins:{old:p.pins.old,new:Object.fromEntries(Object.entries(runtime).map(([n,s])=>[n,pin(s)])),
    qa:pin(helperFiles["qa_contract.py"]),adapter:pin(helperFiles["qa_adapter.py"]),
    failed01_validators:Object.fromEntries(Object.entries(failed).map(([n,s])=>[n,pin(s)]))},binding_proof:bound.proof};
 const packet={schema:1,control_source:source,control_sha256:h.sha(source),payload},raw=canonical(packet)+"\n";
 need(h.utf8(raw).length<=524288,"ORIGINAL_PURE_CONTROL_PACKET_LIMIT");
 const wrapper="import hashlib,json,sys,types\nraw=sys.stdin.buffer.read(524289)\n"+
  "assert 0<len(raw)<=524288 and hashlib.sha256(raw).hexdigest()=='"+h.sha(raw)+"'\n"+
  "p=json.loads(raw)\nassert set(p)=={'schema','control_source','control_sha256','payload'} and p['schema']==1\n"+
  "source=p['control_source'].encode('utf-8')\nassert hashlib.sha256(source).hexdigest()==p['control_sha256']=='"+h.sha(source)+"'\n"+
  "module=types.ModuleType('pure_bili_r9_player02_component_controls');module.__file__='<check_current_flow.py>'\n"+
  "exec(compile(source,module.__file__,'exec'),module.__dict__)\nresult=module.run_controls(p['payload'])\n"+
  "assert result['all_passed'] is True and result['count']==21 and len(result['cases'])==21 and all(x['passed'] is True for x in result['cases'])\n"+
  "manifest=(json.dumps({'files':p['payload']['pins']['new'],'schema':1},sort_keys=True,separators=(',',':'))+'\\n').encode('utf-8')\n"+
  "assert hashlib.sha256(manifest).hexdigest()=='"+bound.manifest_sha256+"'\n"+
  "result['new_source_manifest_sha256']=hashlib.sha256(manifest).hexdigest()\n"+
  "result['control_source_sha256']=p['control_sha256']\nresult['packet_sha256']=hashlib.sha256(raw).hexdigest()\n"+
  "result['actual_install_binding']=p['payload']['binding_proof']\n"+
  "encoded=json.dumps(result,sort_keys=True,separators=(',',':'))\nassert len(encoded.encode())<=32768\nprint(encoded,flush=True)\n";
 return {source,packet,raw,request:{host:"pocket4",executable:"/usr/bin/python3",args:["-I","-B","-c",wrapper],
  cwd:"/home/alex/work",env:{},stdin:raw,idempotency_key:"pocket4-bili-r9-player02-component-controls01-20261106",
  timeout_seconds:90,cpu_quota_percent:100,memory_max_bytes:268435456,nice:10},
  planned_controls:21,Python_controls_executed:false,UI_actions:0};
}
