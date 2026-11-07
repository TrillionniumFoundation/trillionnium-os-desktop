async function readJob(tools,v,ll,w,prefix,maxBytes=2097152) {
 const state=load(prefix+"_status_latest");
 v.assertThat(state&&state.output_complete===true&&state.output_durable===true&&state.terminal_publication_confirmed===true,"complete terminal required");
 v.assertThat(["succeeded","failed"].includes(state.state),"terminal state required");
 const sizes={stdout:state.log_bytes.stdout.stored,stderr:state.log_bytes.stderr.stored};
 for(const k of ["stdout","stderr"])v.assertThat(sizes[k]===state.log_bytes[k].seen&&sizes[k]<=maxBytes&&!state.log_truncated[k]&&state.log_synced[k]&&state.log_errors[k]===null,"terminal stream bound "+k);
 const offsets={stdout:0,stderr:0},outputs={stdout:"",stderr:""},originals=[];
 let count=0;
 do{
  v.assertThat(++count<=130,"process read chunk bound");
  const r=await tools.mcp__codex_apps__heptaruntime_mac_controller_process_read({host:"pocket4",job_id:load(prefix+"_job_id"),stdout_offset:offsets.stdout,stderr_offset:offsets.stderr,limit:16384});
  const raw=w.rawOf(r),x=ll(raw);originals.push(raw);store(prefix+"_log_chunk_originals",originals);
  v.assertThat(x.job_id===load(prefix+"_job_id"),"process read job");
  for(const k of ["stdout","stderr"]){const s=x[k],b=v.utf8(s.text),hex=Array.from(b,n=>n.toString(16).padStart(2,"0")).join("");
   v.assertThat(s.offset===offsets[k]&&s.next_offset===offsets[k]+b.length&&s.size===sizes[k]&&hex===s.bytes_hex,"exact process stream "+k);
   v.assertThat(s.eof===(s.next_offset===sizes[k])&&(b.length>0||s.eof),"eof/progress "+k);
   outputs[k]+=s.text;offsets[k]=s.next_offset;
  }
 }while(offsets.stdout<sizes.stdout||offsets.stderr<sizes.stderr);
 for(const k of ["stdout","stderr"]){v.assertThat(v.utf8(outputs[k]).length===sizes[k],"whole size "+k);store(prefix+"_"+k+"_raw",outputs[k]);}
 const receipt={job_id:load(prefix+"_job_id"),terminal:w.pin(load(prefix+"_status_latest_text")),stdout:w.pin(outputs.stdout),stderr:w.pin(outputs.stderr),chunks:originals.map(x=>w.pin(x)),complete_offsets_and_eof:true,whole_text_UTF8_equals_original_hex:true};
 store(prefix+"_log_read_receipt",receipt);return outputs;
}