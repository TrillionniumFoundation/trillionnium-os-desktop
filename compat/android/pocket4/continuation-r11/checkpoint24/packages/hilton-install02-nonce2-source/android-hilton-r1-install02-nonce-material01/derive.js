function deriveHiltonInstall02Nonce(utilitySource,oldSource,oldRequestRaw,poolRaw){
 const H=Function(utilitySource+"\nreturn {utf8,sha256,gitBlob};")(),need=(v,m)=>{if(!v)throw Error(m);},pin=s=>({bytes:H.utf8(s).length,sha256:H.sha256(H.utf8(s)),git_blob_sha1:H.gitBlob(H.utf8(s))});
 need(H.gitBlob(H.utf8(utilitySource))==="443e39b58cd6fe72faa1cb1d1c7b0a813fa0032d","UTILITY_PIN");
 need(H.gitBlob(H.utf8(oldSource))==="d8c6f158c744b5998453c5ab55001b847e8adaca","ORIGINAL_MATERIAL_PIN");
 need(H.gitBlob(H.utf8(oldRequestRaw))==="53f7de33bd0b490f3a2b31b31fda823feae5f5dd","ORIGINAL_REQUEST_PIN");
 need(JSON.stringify(pin(poolRaw))===JSON.stringify({bytes:35191,sha256:"6da2b0b20dd7c1b109f7131ba253401843833b12fb27682a3f4bb18c6907e9d2",git_blob_sha1:"1a7c69c44fe893105f7125670dc889ca6127b097"}),"GLOBAL926_PIN");
 const pool=JSON.parse(poolRaw);need(pool.length===926&&new Set(pool).size===926&&pool.every((v,i)=>/^[a-f0-9]{32}$/.test(v)&&(!i||pool[i-1]<v)),"GLOBAL926_SHAPE");
 const oldPair=["2fd1a0e95fa54abae85ff1b6602a35c8","8e54b63f8b86beb3e07bbf4e1c19d768"];need(oldPair.every(v=>pool.includes(v)),"HILTON01_PAIR_RETIRED_EXCLUDED");
 let s=oldSource;
 function once(a,b){need(s.split(a).length===2,"ONE_LITERAL:"+a.slice(0,70));s=s.replace(a,b);}
 once('"""Two dedicated NDK run / independent retirement nonce draws.','"""Two dedicated Hilton root02 install flow / state nonce draws.');
 once("KIND = 'pocket4-original-ndk-fixture-run-retire-nonce01'","KIND = 'pocket4-hilton-install02-flow-state-nonce01'");
 once("PROFILE = 'pocket4-original-ndk-fixture-APK05-run-retire01'","PROFILE = 'pocket4-owned-hilton-qa-r1-install-state-02'");
 const begin=s.indexOf("POOL_RAW = r'''")+15,end=s.indexOf("'''",begin);
 need(begin>=15&&end>begin,"EXACT_POOL_LITERAL");const oldPool=s.slice(begin,end);
 need(H.gitBlob(H.utf8(oldPool))==="269194afb3b365ca4995f6ff69a2e6539cff6ff7","OLD_POOL_LITERAL_PIN");
 s=s.slice(0,begin)+poolRaw+s.slice(end);
 once("POOL_BYTES = 35115","POOL_BYTES = 35191");
 once("POOL_SHA256 = '8a718803f7dc905e5c92c3609164c19caf1b213d88b235511554e39403568e25'","POOL_SHA256 = '6da2b0b20dd7c1b109f7131ba253401843833b12fb27682a3f4bb18c6907e9d2'");
 once("POOL_GIT_BLOB = '269194afb3b365ca4995f6ff69a2e6539cff6ff7'","POOL_GIT_BLOB = '1a7c69c44fe893105f7125670dc889ca6127b097'");
 once("'package': 'com.example.ndk_tests', 'target_package': 'com.example.ndk_tests',","'package': 'org.droidloom.qa.hilton.r1', 'target_package': 'com.hilton.android.hhonors',");
 once("'phase': 'run_and_independent_retirement',","'phase': 'fresh_install_flow_and_state_root02',");
 s=s.replaceAll("'run_nonce'","'hilton_install02_flow'").replaceAll("'retire_nonce'","'hilton_install02_state'");
 once("'count': 924}", "'count': 926}");
 once("len(old) == 924 and len(set(old)) == 924", "len(old) == 926 and len(set(old)) == 926");
 once("'EXACT_GLOBAL_924_BYTES_REQUIRED'", "'EXACT_GLOBAL_926_BYTES_REQUIRED'");
 once("'EXACT_UNIQUE_GLOBAL_924_SHAPE_REQUIRED'", "'EXACT_UNIQUE_GLOBAL_926_SHAPE_REQUIRED'");
 once("require({'e4b5a1bdac8be04ff2ea3188a6d946d6',\n                 '06a571251aa6fcc77591494edda1f801'}.issubset(set(old)),\n                'BOTH_ACTUAL_INSTALL_ATTEMPTS_MUST_REMAIN_EXCLUDED')",
      "require({'2fd1a0e95fa54abae85ff1b6602a35c8',\n                 '8e54b63f8b86beb3e07bbf4e1c19d768'}.issubset(set(old)),\n                'ACTUAL_FAILED_HILTON01_FLOW_AND_STATE_MUST_REMAIN_EXCLUDED')");
 // Global numeric replacement must not touch the raw pool or its full digest.
 need(s.slice(s.indexOf("POOL_RAW = r'''")+15,s.indexOf("'''",s.indexOf("POOL_RAW = r'''")+15))===poolRaw,"POOL_BYTES_UNCHANGED");
 need(s.includes("5.0")&&s.includes("candidate = secrets.token_hex(16)")&&s.split("candidate = secrets.token_hex(16)").length===2,"ONE_DRAW_PER_LABEL_BODY");
 const q=JSON.parse(oldRequestRaw);need(q.stdin===oldSource&&q.timeout_seconds===20&&q.memory_max_bytes===67108864,"ORIGINAL_ENVELOPE");
 q.stdin=s;q.idempotency_key="p4-hilton-r1-install02-flow-state-nonce01-"+pin(s).sha256.slice(0,16);
 return {source:s,request:JSON.stringify(q,null,2)+"\n",proof:JSON.stringify({schema:1,status:"SOURCE_ONLY_UNRUN",source:pin(s),root:"/home/alex/work/pocket4-owned-hilton-qa-r1-install-state-02",labels:["hilton_install02_flow","hilton_install02_state"],global_pool:pin(poolRaw),old_failed_hilton_pair_excluded:true,one_draw_per_label:true,redraw:false,ordinary_uid:1000,ordinary_gid:1000,internal_seconds:5,outer_seconds:20,memory_max_bytes:67108864,Main_or_Android_or_child_or_explicit_filesystem_actions:0,nonce_generation_not_executed_here:true},null,2)+"\n"};
}
