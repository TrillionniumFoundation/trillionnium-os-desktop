function deriveNext3MetadataStage(key,priorStage){
 const targets={ticket12306:{package:"com.MobileTicket",module:"ticket12306"},hilton:{package:"com.hilton.android.hhonors",module:"hilton"},united:{package:"com.united.mobile.android",module:"united"}};
 if(!Object.prototype.hasOwnProperty.call(targets,key))throw Error("FIXED_THREE_TARGETS_ONLY");
 const t=targets[key],edits=[];let raw=priorStage;
 function one(before,after){const at=raw.indexOf(before);if(at<0||raw.indexOf(before,at+before.length)>=0)throw Error("EXACT_STAGE_EDIT:"+before);raw=raw.slice(0,at)+after+raw.slice(at+before.length);edits.push({at,before,after});}
 one("ROOT=Path('/home/alex/work/pocket4-12306-artifact-launcher-readonly-01')","ROOT=Path('/home/alex/work/pocket4-current-cell02-"+key+"-metadata-01')");
 one("SOURCE=ROOT/'source/read_12306.py'","SOURCE=ROOT/'source/read_target.py'");
 one("NONCE='a08bcaaa2480f0aafcdaa0d5ac6c315a'","NONCE='__FRESH_METADATA_NONCE__'");
 one("REFERENCE=Path('/home/alex/work/pocket4-owned-bili-qa-r5-install-state-03/source/references/readonly_r3_coordinator.py')","REFERENCE=Path('/home/alex/work/pocket4-current-host-r6-source-01/current_coordinator.py')");
 one("REFERENCE_SHA='e2769eeeae2d620456a67959dfaff3b07545f2352cd9a60692450451004c39fd'",
     "REFERENCE_SHA='0a4a9f0d02b2a62f2b902983e43360c751a8f1952fb9ae7399850b112cb50a89'\nDISCOVERY_SHA='9ed0069897faebba50cec3d93b08da54f1c791d6e2e775d26ec798c38b227886'\nDISCOVERY_BYTES=8332");
 one("assert type(packet) is dict and set(packet)=={'schema','nonce','source'}","assert type(packet) is dict and set(packet)=={'schema','nonce','source','discovery'}\n    assert len(NONCE)==32 and all(c in '0123456789abcdef' for c in NONCE)");
 one("raw=packet['source'].encode('utf-8')","raw=packet['source'].encode('utf-8')\n    assert type(packet['discovery']) is str\n    discovery=packet['discovery'].encode('utf-8')\n    assert len(discovery)==DISCOVERY_BYTES and hashlib.sha256(discovery).hexdigest()==DISCOVERY_SHA");
 one("entry=types.ModuleType('ticket12306_metadata_fixed_entry');entry.__file__=str(SOURCE)","entry=types.ModuleType('"+t.module+"_metadata_fixed_entry');entry.__file__=str(SOURCE)");
 one("assert entry.ROOT==ROOT and entry.SOURCE_PATH==SOURCE and entry.NONCE==NONCE",
     "assert entry.ROOT==ROOT and entry.SOURCE_PATH==SOURCE and entry.NONCE==NONCE\n    assert entry.PACKAGE=="+JSON.stringify(t.package)+" and entry.DISCOVERY_SHA==DISCOVERY_SHA and entry.DISCOVERY_BYTES==DISCOVERY_BYTES");
 one("ref=entry.load(REFERENCE,REFERENCE_SHA,'ticket12306_stage_main_reference')",
     "ref=entry.load(REFERENCE,REFERENCE_SHA,'"+t.module+"_stage_main_reference',7442)");
 one("activation=json.loads(ref.read(ref.ACTIVATION,expected=ref.ACTIVATION_SHA))","activation=ref.current_baseline()");
 one("ref.EPOCH_SOURCE,'ticket12306_stage_epoch')","ref.EPOCH_SOURCE,'"+t.module+"_stage_epoch')");
 one("ref.write_new(SOURCE,raw,mode=0o444)","ref.write_new(SOURCE,raw,mode=0o444)\n        ref.write_new(SOURCE.parent/'current_discovery.py',discovery,mode=0o444)");
 one("'TICKET12306_METADATA_READ_NOT_QUALIFIED'","'"+t.module.toUpperCase()+"_METADATA_READ_NOT_QUALIFIED'");
 one("ref.read(SOURCE,32768,source_sha256)","ref.read(SOURCE,32768,source_sha256)\n            ref.read(SOURCE.parent/'current_discovery.py',DISCOVERY_BYTES,DISCOVERY_SHA)");
 let inverse=raw;for(const e of [...edits].reverse()){if(inverse.slice(e.at,e.at+e.after.length)!==e.after)throw Error("INVERSE");inverse=inverse.slice(0,e.at)+e.before+inverse.slice(e.at+e.after.length);}
 if(inverse!==priorStage)throw Error("INVERSE_PRIOR_STAGE");
 return{key,source:raw,edits,complete_prior_stage_inverse:true,runtime_nonce_pending:true};
}