function verifyMemeventsPropertyBranch(actual, stacks) {
  function need(value, message) { if (!value) throw new Error(message); }
  const d=actual.image_ELF_diagnosis;
  need(actual.collection_complete===true && actual.first_error===null &&
       actual.errors.length===0 && actual.held_fds_closed===true &&
       actual.held_named_unchanged===true &&
       actual.ELF_read_validated_after_final_checks===true, "complete exact ELF collection required");
  need(actual.commands.length===3 && actual.commands.every(x =>
       x.returncode===0 && x.joined===true && x.capture_complete===true &&
       x.forced_kill===false && x.first_error===null && x.errors.length===0), "three clean joined commands");
  need(d.build_id==="b7076ba103f2a4aeb7cad5b97f45fd17" &&
       d.matches_crash_stack_build_id===true && d.machine==="x86_64" &&
       d.bytes===68968 && d.sha256==="26b20973292206cb73715872d48a4b27db670604a2175e9864f8929c84b25d18",
       "actual image ELF identity");
  const code=d.code_windows.find(x=>x.name==="actual_crash_function_range");
  const plt=d.code_windows.find(x=>x.name===".plt");
  function decoded(w) {
    const key=Object.keys(w).find(k=>/hex/.test(k));
    need(key && /^[a-f0-9]+$/.test(w[key]) && w[key].length===w.bytes*2, "exact bounded hex");
    return w[key].match(/../g).map(x=>parseInt(x,16));
  }
  const cb=decoded(code), pb=decoded(plt);
  need(code.start_vaddr===0x40b0 && code.bytes===4997 &&
       plt.start_vaddr===0x95a0 && plt.bytes===944, "fixed code windows");
  const hex=a=>a.map(v=>v.toString(16).padStart(2,"0")).join("");
  const word=(a,i)=>(a[i]|a[i+1]<<8|a[i+2]<<16|a[i+3]<<24);
  const at=(addr,len)=>{const i=addr-code.start_vaddr;need(i>=0&&i+len<=cb.length,"code range");return cb.slice(i,i+len);};
  function exact(addr, expected) {
    const got=hex(at(addr,expected.length/2)); need(got===expected,"opcode mismatch at "+addr.toString(16)); return got;
  }
  function relCall(addr, symbol) {
    const b=at(addr,5); need(b[0]===0xe8,"fixed rel32 call");
    const target=addr+5+word(b,1), pi=target-plt.start_vaddr;
    need(pi>=0&&pi+6<=pb.length && pb[pi]===0xff&&pb[pi+1]===0x25,"PLT RIP indirect jump");
    const got=target+6+word(pb,pi+2);
    const matches=d.dynamic_relocations.filter(r=>r.offset===got&&r.type===7&&r.table===".rela.plt");
    need(matches.length===1&&matches[0].symbol===symbol,"exact R_X86_64_JUMP_SLOT symbol");
    return {call_vaddr:addr,call_hex:hex(b),return_vaddr:addr+5,plt_vaddr:target,
            plt_jump_hex:hex(pb.slice(pi,pi+6)),got_vaddr:got,relocation:matches[0]};
  }
  const deviceApi=relCall(0x42ed,"android_get_device_api_level");
  exact(0x42f2,"83f823"); exact(0x42f5,"7f08");
  const lea=at(0x4302,7);need(hex(lea.slice(0,3))==="488d3d","RIP LEA to RDI");
  const keyAddr=0x4302+7+word(lea,3);
  const key=d.selected_rodata_strings.filter(r=>r.vaddr===keyAddr);
  need(key.length===1&&key[0].text==="ro.build.version.sdk_full","exact property string");
  const property=relCall(0x433a,"__system_property_get");
  exact(0x433f,"85c0");
  const branch=at(0x4341,6); need(hex(branch.slice(0,2))==="0f8e","signed JLE opcode");
  const abortAddress=0x4341+6+word(branch,2);need(abortAddress===0x5411,"precise fatal branch");
  const abort=relCall(abortAddress,"abort");
  need(d.reported_crash_pc===0x5415&&d.reported_crash_pc>=abortAddress&&
       d.reported_crash_pc<abort.return_vaddr,"reported PC lies in exact abort call");
  need(d.initializers.length===1 &&
       d.initializers[0].raw_pointer_values_before_dynamic_relocation.includes(0x40b0),
       "ELF init-array points at constructor range");
  const fatal=stacks.fatal_records.filter(r=>r.process_name==="lmkd");
  need(fatal.length===5&&fatal.every(r=>r.signal===6&&r.packet_uid===1069),"five actual LMKD fatalities");
  const reports=fatal.map(f=>{
    const rs=stacks.debugger_reports.filter(r=>r.observed_crashing_pid===f.process_pid);
    need(rs.length===1,"unique matching DEBUG report");
    const r=rs[0],frame=r.frames.find(x=>x.index===1);
    need(r.abi==="x86_64"&&r.signal.number===6&&frame&&
       frame.system_elf==="/system/lib64/libmemevents.so"&&
       frame.build_id===d.build_id&&parseInt(frame.pc_hex,16)===0x5415&&
       frame.symbol==="_GLOBAL__sub_I_memevents.cpp+4965", "same actual frame for every LMKD");
    return {pid:f.process_pid,uid:f.packet_uid,reporter_pid:r.reporter_pid,
            frame,reported_fingerprint:r.build_fingerprint};
  });
  return {device_api_gate:{call:deviceApi,cmp_hex:"83f823",branch_hex:"7f08",
      interpretation:"The full-SDK property branch executes when android_get_device_api_level returns greater than 35."},
    property_argument:{lea_vaddr:0x4302,lea_hex:hex(lea),target_vaddr:keyAddr,record:key[0]},
    property_call:property,return_test:{vaddr:0x433f,hex:"85c0",interpretation:"test eax,eax"},
    conditional:{vaddr:0x4341,hex:hex(branch),target_vaddr:abortAddress,
      interpretation:"signed jle after test: property getter return value is <= 0"},
    abort_call:abort,reported_pc:0x5415,actual_lmkd_reports:reports,
    method:"Direct decoding of these exact fixed x86-64 instructions and ELF PLT/GOT relocation; no pattern-only scan or external disassembler.",
    scope:"This proves the conditional failure selected by the observed matching-build frame; it does not by itself prove which configuration file omitted the property or whether property access failed."};
}
