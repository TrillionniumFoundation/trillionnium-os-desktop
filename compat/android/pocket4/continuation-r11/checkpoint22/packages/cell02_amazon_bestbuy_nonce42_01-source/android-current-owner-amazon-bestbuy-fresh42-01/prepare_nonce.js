function prepareCurrentOwnerTwoAppFresh42(h,templates,excludedRaw,excludedPin){
 const need=(x,m)=>{if(!x)throw Error(m);},pin=s=>({bytes:h.utf8(s).length,sha256:h.sha(s)});
 const canon=v=>v===null?'null':Array.isArray(v)?'['+v.map(canon).join(',')+']':typeof v==='object'?
  '{'+Object.keys(v).sort().map(k=>JSON.stringify(k)+':'+canon(v[k])).join(',')+'}':JSON.stringify(v);
 const excluded=JSON.parse(excludedRaw);
 need(h.utf8(excludedRaw).length===excludedPin.bytes&&h.sha(excludedRaw)===excludedPin.sha256&&
  excluded.length>=699&&excluded.length===new Set(excluded).size&&
  canon(excluded)===canon([...excluded].sort())&&excluded.every(v=>/^[0-9a-f]{32}$/.test(v)),
  'COMPLETE_CURRENT_GLOBAL_AFTER_LONDON40_EXCLUSIONS');
 const mapping=[],templatePins={};
 for(const app of ['amazon','bestbuy']){
  const t=templates[app];
  need(t.app===app&&t.actual_binding.install_retired===true&&t.actual_binding.source_controls===68&&
   t.template.owner_discovery_revision===2&&t.requires_actual_fresh_nonces===true,'ACTUAL_INSTALL_BOUND_CURRENT_TEMPLATE');
  templatePins[app]=t.source_pins;
  need(t.nonce_labels.length===(app==='amazon'?32:10),'EXACT_NONCE_COUNTS');
  for(const local of t.nonce_labels)mapping.push({app,label:app+'.'+local,local_label:local,
   slot:'__FRESH_'+local.toUpperCase().replaceAll('.','_')+'__'});
 }
 const spec={schema:'pocket4-current-amazon-bestbuy-fresh-flow-nonce-spec-v1',count:42,
  labels:mapping.map(x=>x.label),mapping,exclude_count:excluded.length,exclude_values:excluded,
  exclusion_source:excludedPin,template_pins:templatePins,source_only:true,Android_actions:0,UI_requests_created:false,
  exact_one_draw_per_value:true,no_redraw:true,actual_helper_uids:Object.fromEntries(Object.entries(templates).map(([k,t])=>[k,t.actual_binding.UID]))};
 const raw=canon(spec)+'\n';
 const source="import hashlib,json,os,re,secrets,sys\nraw=sys.stdin.buffer.read(131073)\n"+
  "assert 0<len(raw)<=131072 and hashlib.sha256(raw).hexdigest()=='"+h.sha(raw)+"'\n"+
  "p=json.loads(raw)\nassert p['schema']=='pocket4-current-amazon-bestbuy-fresh-flow-nonce-spec-v1'\n"+
  "assert os.getuid()==os.geteuid()==1000\n"+
  "assert p['count']==42 and len(p['labels'])==len(set(p['labels']))==42\n"+
  "assert len(p['mapping'])==42 and [x['label'] for x in p['mapping']]==p['labels']\n"+
  "assert [x['app'] for x in p['mapping']]==['amazon']*32+['bestbuy']*10\n"+
  "assert len(p['exclude_values'])==len(set(p['exclude_values']))==p['exclude_count']=="+excluded.length+"\n"+
  "assert all(type(x) is str and re.fullmatch('[0-9a-f]{32}',x) for x in p['exclude_values'])\n"+
  "assert p['source_only'] is True and p['Android_actions']==0 and p['UI_requests_created'] is False\n"+
  "assert p['exact_one_draw_per_value'] is True and p['no_redraw'] is True\n"+
  "pool=[secrets.token_hex(16) for _ in range(42)]\n"+
  "assert len(pool)==len(set(pool))==42 and not set(pool)&set(p['exclude_values'])\n"+
  "print(json.dumps({'schema':'pocket4-current-amazon-bestbuy-fresh-flow-nonce-v1',\n"+
  "    'spec':{'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()},\n"+
  "    'count':42,'labels':p['labels'],'nonces':dict(zip(p['labels'],pool)),\n"+
  "    'exclude_count':p['exclude_count'],'all_distinct_and_old_values_excluded':True,\n"+
  "    'generator':'secrets.token_hex(16)','uid':os.getuid(),'no_redraw':True,\n"+
  "    'actual_helper_uids':p['actual_helper_uids'],\n"+
  "    'source_only_nonce_generation':True,'file_writes':0,'child_processes':0,\n"+
  "    'Android_commands':0,'App_launches':0,'UI_actions':0},sort_keys=True,separators=(',',':')),flush=True)\n";
 need(h.utf8(raw).length<=131072,'SPEC_BOUND');
 return{spec,specRaw:raw,source,request:{host:'pocket4',executable:'/usr/bin/python3',
  args:['-I','-B','-c',source],cwd:'/home/alex/work',env:{},stdin:raw,
  idempotency_key:'pocket4-current-amazon-bestbuy-r4-owner-fresh42-01-20261106',
  timeout_seconds:30,cpu_quota_percent:50,memory_max_bytes:134217728,nice:10},
  nonce_values_generated:false,UI_request_created:false};
}
function bindCurrentOwnerTwoAppNonces(h,templates,specRaw,actualRaw,expected){
 const need=(x,m)=>{if(!x)throw Error(m);},pin=s=>({bytes:h.utf8(s).length,sha256:h.sha(s)});
 const canon=v=>v===null?'null':Array.isArray(v)?'['+v.map(canon).join(',')+']':typeof v==='object'?
  '{'+Object.keys(v).sort().map(k=>JSON.stringify(k)+':'+canon(v[k])).join(',')+'}':JSON.stringify(v),eq=(a,b)=>canon(a)===canon(b);
 need(eq(pin(specRaw),expected.spec)&&eq(pin(actualRaw),expected.actual),'EXACT_FRESH42_ORIGINAL_PINS');
 const s=JSON.parse(specRaw),n=JSON.parse(actualRaw),labels=s.labels;
 need(s.schema==='pocket4-current-amazon-bestbuy-fresh-flow-nonce-spec-v1'&&
  n.schema==='pocket4-current-amazon-bestbuy-fresh-flow-nonce-v1'&&s.count===42&&n.count===42&&
  s.exclude_count>=699&&s.exclude_values.length===s.exclude_count&&new Set(s.exclude_values).size===s.exclude_count&&
  eq(n.spec,expected.spec)&&eq(n.labels,labels)&&labels.length===new Set(labels).size&&labels.length===42&&
  eq(Object.keys(n.nonces).sort(),[...labels].sort())&&n.no_redraw===true&&
  n.generator==='secrets.token_hex(16)'&&n.uid===1000&&n.all_distinct_and_old_values_excluded===true&&
  n.source_only_nonce_generation===true&&n.file_writes===0&&n.child_processes===0&&
  n.Android_commands===0&&n.App_launches===0&&n.UI_actions===0&&n.exclude_count===s.exclude_count,
  'ACTUAL_FRESH42_CURRENT_OWNER_GENERATION');
 const values=labels.map(k=>n.nonces[k]);
 need(values.every(v=>typeof v==='string'&&/^[0-9a-f]{32}$/.test(v)&&!s.exclude_values.includes(v))&&
  new Set(values).size===42,'ACTUAL_FRESH42_EXCLUDES_ALL_CURRENT_GLOBAL_VALUES');
 const bound={};
 for(const app of ['amazon','bestbuy']){
  const t=templates[app],sources={...t.sources},rows=s.mapping.filter(x=>x.app===app),edits=[...t.install_binding_edits];
  need(eq(t.source_pins,s.template_pins[app])&&n.actual_helper_uids[app]===t.actual_binding.UID&&
   eq(rows.map(x=>x.local_label),t.nonce_labels)&&rows.length===(app==='amazon'?32:10),'EXACT_CURRENT_APP_SOURCE_AND_LABELS');
  for(const row of rows){
   for(const name of ['coordinator',...(row.local_label==='flow'?['stage']:[])]){
    need(sources[name].split(row.slot).length===2,'ONE_FRESH_NONCE_SLOT:'+name+':'+row.label);
    sources[name]=sources[name].replace(row.slot,n.nonces[row.label]);
    edits.push({file:name,from:row.slot,to:n.nonces[row.label],why:'actual-fresh-nonce-'+row.label,count:1});}
  }
  for(const [name,raw]of Object.entries(sources))need(!raw.includes('__FRESH_')&&h.utf8(raw).length<=65536,'NO_UNBOUND_RUNTIME_SOURCE:'+name);
  const restore={...sources};for(const e of [...edits].reverse()){
   need(restore[e.file].split(e.to).length===2,'EXACT_FULL_BINDING_INVERSE:'+e.why);
   restore[e.file]=restore[e.file].replace(e.to,e.from);}
  need(Object.keys(restore).every(k=>restore[k]===t.template.sources[k]),'ALL_SOURCE_INSTALL_AND_NONCE_INVERSE');
  bound[app]={...t,sources,source_pins:Object.fromEntries(Object.entries(sources).map(([k,v])=>[k,pin(v)])),
   binding_edits:edits,nonce_map:Object.fromEntries(rows.map(x=>[x.local_label,n.nonces[x.label]])),
   fresh_nonce_values:rows.map(x=>n.nonces[x.label]),nonce_actual:{...expected.actual,job_id:expected.job_id},
   nonce_spec:expected.spec,nonce_excluded_count:s.exclude_count,nonces_bound:true,complete_binding_inverse:true,UI_request_created:false};
 }
 return bound;
}

