// Pure actual-only Hilton root02 binding; no dispatch or nonce generation.
const TEMPLATE_PINS = {
  "INPUTS.json": {
    "bytes": 6221,
    "sha256": "90339635112ba52a749c2270037a3e18a168f7e051e9d5273c3269e5afcdd931",
    "git_blob_sha1": "0a64d4798a00c74cd3bac8abb82a0b4f725b86b6"
  },
  "README.md": {
    "bytes": 3103,
    "sha256": "929485280b238d5e5117c4cd4b489ed1f0b70ebe100912bb207cd65d4c2f2b42",
    "git_blob_sha1": "8d76c7a255037857bbcab010dfbb9f005472da8d"
  },
  "SOURCE_PINS.json": {
    "bytes": 2860,
    "sha256": "edf1ca171ed4742c76e50cab8809451eb41435b8485e63a5f8804ea50793cc5c",
    "git_blob_sha1": "b87deb78aaaf9feffea1c5265734b34720ca3a50"
  },
  "actual-target-metadata.json": {
    "bytes": 13997,
    "sha256": "cd4f46876a1bd0b48289d6b6a9c8379b2480073b4a24849397f8d990cabeb0dd",
    "git_blob_sha1": "5e43bfe675aae41e387bc7752668eb08f1825a2d"
  },
  "check_current_discovery.py": {
    "bytes": 19061,
    "sha256": "063b9a02f1b8ca87d9b5d31ca8120bbd2599b6c63a89505cd3a1e557a962cdea",
    "git_blob_sha1": "39450df343dccb8c34bda9d67186f62841e5d3df"
  },
  "check_install_binding.py": {
    "bytes": 40388,
    "sha256": "cca385445459ba2df3c6ae428810d56577e2009aa08658faf436255cd215bc52",
    "git_blob_sha1": "fffed68d0d3dc4d033281f814d059179b605e975"
  },
  "current_discovery.py": {
    "bytes": 8332,
    "sha256": "9ed0069897faebba50cec3d93b08da54f1c791d6e2e775d26ec798c38b227886",
    "git_blob_sha1": "d94308531ea7d6b014c79900a1c61f001e081717"
  },
  "hilton_context.py": {
    "bytes": 26014,
    "sha256": "e10e8ec07eed076dd19065c77bd3de3665ef18cfe24b055bb706969882fb543d",
    "git_blob_sha1": "a295310c0efdf8b0de1acf95ada10da32718c858"
  },
  "hilton_transport.py": {
    "bytes": 15612,
    "sha256": "b4a70d691d987e2e7755ab7d8fd099dc3892097570e4fc4ce3d34c3dc6c4ae76",
    "git_blob_sha1": "d4e84d28b8009527f5dc216eba9bde09e1b82b26"
  },
  "host-stage-actual.json": {
    "bytes": 10016,
    "sha256": "e1718fcb3561488c88011f00de0d6e992ff51a64a355da87f1fcb867545fcba6",
    "git_blob_sha1": "797520d386fb48da30b709deeee35b041016aa8e"
  },
  "host/source-manifest.json": {
    "bytes": 3757,
    "sha256": "002ee581a4bb399536dd7d594d01f050e2540d9c049b0cfb37e1c96954b6caff",
    "git_blob_sha1": "c0a0a3d42dde0ee8c1d405aca5d220ce3fa33546"
  },
  "install_state.py": {
    "bytes": 40069,
    "sha256": "404ea6c07cd5926abf629a267faa9dc06c5b350aad59d8ef9dbaa201b5b5c778",
    "git_blob_sha1": "fd598c9fd4b0407b6a5b72137e809b8dabd4d418"
  },
  "make_request.py": {
    "bytes": 2974,
    "sha256": "31b5973a0dc57bc03a6a99b0539d1250501035aa8ecf69941a0b57774f968a93",
    "git_blob_sha1": "95656d8641925ba258adc17469e9d888f69a26f9"
  },
  "references/target_metadata_parsers.py": {
    "bytes": 1982,
    "sha256": "b30f1e5b9b13e1cd95cc52a9b38f86c2ec421764c956dca1412a977d807d2ea6",
    "git_blob_sha1": "93484bbf6b6c3ccd7476aef4ea7782c087400293"
  },
  "stage_execute.py": {
    "bytes": 9435,
    "sha256": "951b472c3cc90459bf8488f33d38183b97d7dcf989089daa97775323df6a645a",
    "git_blob_sha1": "3903d1440302a66e0eb673f7d3ba8ea815ff03a3"
  },
  "target-artifact-reference.json": {
    "bytes": 5083,
    "sha256": "a7ecc2530967eeb3d340b4d53cdab634223263b50e871382caaef8508c930f6a",
    "git_blob_sha1": "275b9350a6f7836978bd73f533aadca8a86af156"
  }
};
function bindHiltonArtifactSchema03(utilitySource,originalRequestRaw,templates,poolRaw,actual) {
 const H=Function(utilitySource+"\nreturn {utf8,sha256,gitBlob};")(),need=(v,m)=>{if(!v)throw Error(m);};
 const sorted=v=>Array.isArray(v)?v.map(sorted):v&&typeof v==="object"?Object.fromEntries(Object.keys(v).sort().map(k=>[k,sorted(v[k])])):v;
 const eq=(a,b)=>JSON.stringify(sorted(a))===JSON.stringify(sorted(b));
 const pin=s=>{need(typeof s==="string","RAW_UTF8_INPUT");return{bytes:H.utf8(s).length,sha256:H.sha256(H.utf8(s)),git_blob_sha1:H.gitBlob(H.utf8(s))};};
 const match=(s,p)=>{const q=pin(s);need(q.bytes===p.bytes&&q.sha256===p.sha256&&(!p.git_blob_sha1||q.git_blob_sha1===p.git_blob_sha1),"EXACT_RAW_PIN");};
 const keys=(v,w)=>v!==null&&typeof v==="object"&&!Array.isArray(v)&&eq(Object.keys(v).sort(),[...w].sort());
 const fill=(s,a,b)=>{need(s.split(a).length===2,"ONE_SOURCE_SLOT:"+a);return s.replace(a,b);};
 need(H.gitBlob(H.utf8(utilitySource))==="443e39b58cd6fe72faa1cb1d1c7b0a813fa0032d","UTILITY_PIN");
 need(H.gitBlob(H.utf8(originalRequestRaw))==="1aad171f6d1106e0e156eef84a3068777a190158","FAILED_HILTON01_ORIGINAL_REQUEST_PIN");
 need(keys(templates,Object.keys(TEMPLATE_PINS)),"EXACT_16_SOURCE_TEMPLATES");
 for(const[name,p]of Object.entries(TEMPLATE_PINS))match(templates[name],p);
 match(poolRaw,{bytes:35191,sha256:"6da2b0b20dd7c1b109f7131ba253401843833b12fb27682a3f4bb18c6907e9d2",git_blob_sha1:"1a7c69c44fe893105f7125670dc889ca6127b097"});
 const pool=JSON.parse(poolRaw);
 need(Array.isArray(pool)&&pool.length===926&&new Set(pool).size===926&&eq(pool,[...pool].sort())&&pool.every(v=>typeof v==="string"&&/^[a-f0-9]{32}$/.test(v)),"FIXED_GLOBAL926");
 need(pool.includes("2fd1a0e95fa54abae85ff1b6602a35c8")&&pool.includes("8e54b63f8b86beb3e07bbf4e1c19d768"),"FAILED_HILTON01_PAIR_REMAINS_RETIRED");
 need(keys(actual,["stdout_raw","stdout_pin","terminal_raw","terminal_pin","job_id"])&&/^[0-9a-f]+-[0-9a-f]{4}-[0-9a-f]{4}$/.test(actual.job_id),"ACTUAL_BINDING_INPUTS");
 for(const kind of["stdout","terminal"]){
  const p=actual[kind+"_pin"];
  need(keys(p,["bytes","sha256"])&&Number.isSafeInteger(p.bytes)&&p.bytes>0&&p.bytes<=8192&&/^[a-f0-9]{64}$/.test(p.sha256),"BOUNDED_ACTUAL_PIN");
  match(actual[kind+"_raw"],p);
 }
 const n=JSON.parse(actual.stdout_raw),t=JSON.parse(actual.terminal_raw);
 need(t.job_id===actual.job_id&&t.state==="succeeded"&&t.exit_code===0&&t.timed_out===false&&t.cancelled===false&&t.automatic_retry===false&&t.output_complete===true&&t.output_durable===true&&t.terminal_publication_confirmed===true&&eq(t.log_bytes,{stdout:{seen:actual.stdout_pin.bytes,stored:actual.stdout_pin.bytes},stderr:{seen:0,stored:0}})&&["stdout","stderr"].every(k=>t.log_synced[k]===true&&t.log_truncated[k]===false&&t.log_errors[k]===null),"FULL_DURABLE_ACTUAL_TERMINAL");
 need(n.schema===1&&n.kind==="pocket4-hilton-install02-flow-state-nonce01"&&n.profile==="pocket4-owned-hilton-qa-r1-install-state-02"&&n.package==="org.droidloom.qa.hilton.r1"&&n.target_package==="com.hilton.android.hhonors"&&n.phase==="fresh_install_flow_and_state_root02"&&n.generator==="secrets.token_hex(16)"&&n.draw_count===2&&n.requested_count===2&&n.redraw_attempted===false&&n.ok===true&&n.error===null&&n.fresh_against_exact_pool===true&&eq(n.labels,["hilton_install02_flow","hilton_install02_state"])&&keys(n.nonces,["hilton_install02_flow","hilton_install02_state"]),"ACTUAL_HILTON02_PAIR_RECEIPT");
 need(eq(n.exclusion_pool,{bytes:35191,sha256:"6da2b0b20dd7c1b109f7131ba253401843833b12fb27682a3f4bb18c6907e9d2",git_blob_sha:"1a7c69c44fe893105f7125670dc889ca6127b097",count:926}),"ACTUAL_FULL_EXCLUSION_POOL");
 need(n.uid===1000&&n.gid===1000&&n.Main_reads===0&&n.Android_commands===0&&n.child_processes===0&&n.explicit_filesystem_reads===0&&n.explicit_filesystem_writes===0&&n.standard_library_and_entropy_IO_included_in_counters===false&&n.runtime_authorized===false&&typeof n.elapsed_seconds==="number"&&Number.isFinite(n.elapsed_seconds)&&n.elapsed_seconds>=0&&n.elapsed_seconds<5,"MATERIAL_ONLY_ACTUAL_BOUNDARIES");
 const flow=n.nonces.hilton_install02_flow,state=n.nonces.hilton_install02_state;
 need([flow,state].every(v=>typeof v==="string"&&/^[a-f0-9]{32}$/.test(v)&&v!=="0".repeat(32)&&!pool.includes(v))&&flow!==state,"FRESH_DISTINCT_NONZERO_PAIR");
 const files={...templates},root="/home/alex/work/pocket4-owned-hilton-qa-r1-install-state-02";
 const key="pocket4-owned-hilton-qa-r1-current-r6-install-state-02-schema03-"+H.sha256(H.utf8(JSON.stringify({context:TEMPLATE_PINS["hilton_context.py"].sha256,flow,state}))).slice(0,16);
 for(const name of["install_state.py","stage_execute.py","make_request.py"]){
  files[name]=fill(files[name],"\nNONCE = None\n","\nNONCE = '"+flow+"'\n");
  if(name==="install_state.py")files[name]=fill(files[name],"\nSTATE_NONCE = None\n","\nSTATE_NONCE = '"+state+"'\n");
  if(name==="make_request.py")files[name]=fill(files[name],"\nKEY = None\n","\nKEY = '"+key+"'\n");
  need(files[name].includes(root)&&!files[name].includes("NONCE = None"),"BOUND_ROOT_AND_NONCE");
 }
 const inputs=JSON.parse(files["INPUTS.json"]);
 need(eq(inputs.nonces,{flow:null,state:null})&&inputs.actual_nonce_source===null&&inputs.fresh_root===root&&inputs.source_qualification_controls===85&&inputs.ordered_worker_Android_commands===13&&inputs.helper_uid===null,"EXACT_UNBOUND_INPUTS");
 inputs.nonces={flow,state};inputs.install_attempt_source_state="ACTUAL_NONCE_BOUND_INSTALL_UNRUN";
 inputs.actual_nonce_source={bytes:actual.stdout_pin.bytes,sha256:actual.stdout_pin.sha256,git_blob:H.gitBlob(H.utf8(actual.stdout_raw)),job_id:actual.job_id,
  terminal:{bytes:actual.terminal_pin.bytes,sha256:actual.terminal_pin.sha256,git_blob:H.gitBlob(H.utf8(actual.terminal_raw))},
  fields:["nonces.hilton_install02_flow","nonces.hilton_install02_state"],generator:"secrets.token_hex(16)",draws:2,no_redraw:true,exclusion_count:926,exclusion_sha256:n.exclusion_pool.sha256,global_count_after:928,
  producer_source:{bytes:39170,sha256:"372ce286bc86817d2f1226a23db5286f8da2e1a21eeef517cb0b30606cd2a0ee",git_blob:"9e4976067bc0746e6f7759b1b40f72bd0bd69c1f"}};
 files["INPUTS.json"]=JSON.stringify(inputs,null,2)+"\n";
 files["README.md"]=fill(files["README.md"],"The actual six-value source assigns only this target's flow/state pair; all 913 prior values were excluded with one draw per label.",
   "The actual dedicated two-value source assigns this fresh root02 flow/state pair; all 926 prior values, including the failed Hilton root01 pair, were excluded with one draw per label.");
 files["README.md"]=fill(files["README.md"],"This root02 package is a source-only template with None/null flow/state/key; it must be bound only to a newly qualified two-value nonce receipt before a request is generated.",
   "This root02 package is bound to the complete qualified two-value nonce receipt; installation remains unrun.");
 const manifest=JSON.parse(templates["SOURCE_PINS.json"]);
 for(const name of["install_state.py","stage_execute.py","make_request.py","INPUTS.json","README.md"]){const p=pin(files[name]);manifest.files[name]={bytes:p.bytes,sha256:p.sha256};}
 files["SOURCE_PINS.json"]=JSON.stringify(manifest,null,2)+"\n";
 const packet={schema:2,source_manifest_sha256:pin(files["SOURCE_PINS.json"]).sha256,nonce:flow,files};
 const payload=JSON.stringify(sorted(packet))+"\n";need(H.utf8(payload).length<=262144,"ORIGINAL_PACKET_BOUND");
 for(const raw of Object.values(files))need(H.utf8(raw).length<=65536,"ORIGINAL_LEAF_BOUND");
 const wrapper="import hashlib,json,sys\nraw=sys.stdin.buffer.read(262145)\n"+
  "assert hashlib.sha256(raw).hexdigest()=='"+pin(payload).sha256+"'\n"+
  "p=json.loads(raw);src=p['files']['stage_execute.py'].encode('utf-8')\n"+
  "assert hashlib.sha256(src).hexdigest()=='"+manifest.files["stage_execute.py"].sha256+"'\n"+
  "scope={'__name__':'owned_qa_stage','__file__':'"+root+"/source/stage_execute.py'}\n"+
  "exec(compile(src,scope['__file__'],'exec'),scope)\nraise SystemExit(scope['main'](raw))\n";
 const original=JSON.parse(originalRequestRaw);
 need(eq(original.args.slice(0,5),["-n","/usr/bin/python3","-I","-B","-c"])&&original.args.length===6&&original.timeout_seconds===300&&original.memory_max_bytes===536870912&&original.cpu_quota_percent===100,"ORIGINAL_ENVELOPE");
 const request={...original,args:[...original.args.slice(0,5),wrapper],stdin:payload,idempotency_key:key};
 const changed=new Set(["install_state.py","stage_execute.py","make_request.py","INPUTS.json","README.md","SOURCE_PINS.json"]);
 for(const name of Object.keys(templates))if(!changed.has(name))need(files[name]===templates[name],"FROZEN_SCHEMA_FIX_AND_CONTROLS_UNCHANGED:"+name);
 return {sources:files,packetRaw:payload,requestRaw:JSON.stringify(sorted(request),null,2)+"\n",
  nonceRaw:actual.stdout_raw,terminalRaw:actual.terminal_raw,global928Raw:JSON.stringify([...pool,flow,state].sort(),null,2)+"\n",
  proofRaw:JSON.stringify({schema:1,status:"ACTUAL_NONCE_BOUND_REQUEST_UNRUN",root,key,nonce_job:actual.job_id,nonce_stdout:pin(actual.stdout_raw),nonce_terminal:pin(actual.terminal_raw),all_926_excluded:true,failed_Hilton01_pair_retired:true,nonce_generation_here:false,
    schema03_context_controls_and_metadata_unchanged:true,original_75_controls_retained:true,controls:85,Python_executed_here:false,ordered_Android_commands:13,Main_R6_B_Q_FD_lock_and_APK_limits_unchanged:true,helper_uid:null,request_dispatched:false,source_manifest:pin(files["SOURCE_PINS.json"]),packet:pin(payload),request:pin(JSON.stringify(sorted(request),null,2)+"\n")},null,2)+"\n"};
}
