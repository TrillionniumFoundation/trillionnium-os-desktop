// Pure actual-result qualification only. No future job, nonce or runtime request.
const EXPECTED = {
  "members": {
    "fixture_context.py": {
      "bytes": 42038,
      "sha256": "368c68728c9af2feb280661731879545bcdbd1f8d363b8a153fcf8e1d7087b4c"
    },
    "fixture_transport.py": {
      "bytes": 15455,
      "sha256": "8c4aa937cbc56f3d0eaf104da1782704ce3578256dd8b1fbb0963650a6d08692"
    },
    "fixture_contract.py": {
      "bytes": 25331,
      "sha256": "1b027dc076f0ee5d89df1e95ae76fddeacab1adaafb5e77e4b05b63f47593261"
    },
    "recorder.py": {
      "bytes": 41689,
      "sha256": "c63cbdca615a609ebb41bcb25db6b770f43c4488c46a8f7b1dbee4bc462b4e64"
    },
    "check_bounded_output.py": {
      "bytes": 29153,
      "sha256": "6e553b8eff7dc48446ac626190df13af67c96566777f137f011b229c1d71b619"
    }
  },
  "packet": {
    "bytes": 205865,
    "sha256": "bb5695f3f478d342d442d723966215ae10b1b6c4f5b156a59eaf81b9d969449c"
  },
  "real_names": [
    "own_artifact_larger_than_log_cap",
    "both_streams_exactly_at_cap",
    "stdout_overflow_preserves_primary",
    "stderr_overflow_preserves_primary",
    "timeout_retires_own_child"
  ],
  "pure_names": [
    "capture_error_before_cleanup_rc_is_primary",
    "observed_nonzero_exit_precedes_late_capture_error"
  ]
};


function qualifyActualBoundedControls(input,U) {
  const need=(v,m)=>{if(!v)throw Error(m);};
  const stable=v=>{
    if(typeof v==='bigint')return '#exact-integer:'+v;
    if(v===null||typeof v!=='object')return JSON.stringify(v);
    if(Array.isArray(v))return '['+v.map(stable).join(',')+']';
    return '{'+Object.keys(v).sort().map(k=>JSON.stringify(k)+':'+stable(v[k])).join(',')+'}';
  };
  const equal=(a,b)=>stable(a)===stable(b);
  const pin=raw=>{
    need(typeof raw==='string','raw original text required');
    const bytes=U.utf8(raw);return{bytes:bytes.length,sha256:U.sha256(bytes)};
  };
  const parse=raw=>JSON.parse(raw,(_key,v,c)=>{
    if(typeof v==='number'&&Number.isInteger(v)&&!Number.isSafeInteger(v)){
      need(c&&/^-?[0-9]+$/.test(c.source),'lossless integer token required');
      return BigInt(c.source);
    }return v;
  });
  need(input&&typeof input==='object'&&
    /^[0-9a-f]+-[0-9a-f]{4}-[0-9a-f]{4}$/.test(input.job),
    'one actual job required');
  const stdoutPin=pin(input.stdoutRaw),terminalPin=pin(input.terminalRaw);
  need(stdoutPin.bytes>0&&stdoutPin.bytes<=131072&&
       terminalPin.bytes>0&&terminalPin.bytes<=32768,'bounded actual originals required');
  const v=parse(input.stdoutRaw),terminal=parse(input.terminalRaw);
  need(terminal.job_id===input.job&&terminal.state==='succeeded'&&terminal.exit_code===0&&
    terminal.timed_out===false&&terminal.cancelled===false&&terminal.automatic_retry===false&&
    terminal.output_complete===true&&terminal.output_durable===true&&
    terminal.terminal_publication_confirmed===true&&
    equal(terminal.log_bytes,{stdout:{seen:stdoutPin.bytes,stored:stdoutPin.bytes},
                             stderr:{seen:0,stored:0}})&&
    ['stdout','stderr'].every(k=>terminal.log_synced[k]===true&&
      terminal.log_truncated[k]===false&&terminal.log_errors[k]===null),
    'independent complete durable successful terminal required');
  need(v.schema===1&&v.kind==='pocket4-ndk-bounded-output-host-controls01'&&
    v.ok===true&&v.error===null&&equal(v.cleanup_errors,[])&&
    equal(v.exact_packet,EXPECTED.packet)&&equal(v.five_source_members,EXPECTED.members)&&
    equal(v.sources,Object.fromEntries(Object.entries(EXPECTED.members)
      .filter(([name])=>name!=='check_bounded_output.py'))),
    'exact actual candidate and controls source chain required');
  need(v.expected_real_child_controls===5&&v.expected_pure_controls===2&&
    Array.isArray(v.real_host_child_controls)&&Array.isArray(v.pure_transport_order_controls)&&
    equal(v.real_host_child_controls.map(r=>r.name),EXPECTED.real_names)&&
    equal(v.pure_transport_order_controls.map(r=>r.name),EXPECTED.pure_names)&&
    new Set([...v.real_host_child_controls,...v.pure_transport_order_controls].map(r=>r.name)).size===7,
    'five real and two pure unique controls required');
  const integer=n=>Number.isSafeInteger(n)&&n>=0;
  const finite=n=>typeof n==='number'&&Number.isFinite(n);
  const exactPin=(p,max)=>p&&equal(Object.keys(p).sort(),['bytes','sha256'])&&
    integer(p.bytes)&&p.bytes<=max&&typeof p.sha256==='string'&&/^[0-9a-f]{64}$/.test(p.sha256);
  const lifeRoles=['selector','stdout_log','stderr_log','stdout_pipe','stderr_pipe','leader_pidfd'];
  for(let i=0;i<5;i++){
    const r=v.real_host_child_controls[i],c=r.capture,l=r.owned_lifecycle;
    need(r.passed===true&&r.actual_host_child===true&&r.Main_or_Android_executed===false&&
      r.synthetic_guard_calls===1&&Number.isSafeInteger(r.returncode)&&
      exactPin(r.command_receipt,65536)&&exactPin(r.stdout,262144)&&exactPin(r.stderr,262144),
      'real child receipt and original log pins required '+i);
    need(c&&c.policy==='per-stream-private-prefix-v1'&&c.maximum_bytes===262144&&
      c.RLIMIT_FSIZE_modified===false&&equal(c.RLIMIT_FSIZE_before,c.RLIMIT_FSIZE_after)&&
      Array.isArray(c.RLIMIT_FSIZE_before)&&c.RLIMIT_FSIZE_before.length===2&&
      c.RLIMIT_FSIZE_before.every(n=>n===-1||(Number.isSafeInteger(n)&&n>=1048593))&&
      equal(c.stored_bytes,{stdout:r.stdout.bytes,stderr:r.stderr.bytes})&&
      ['stdout','stderr'].every(k=>integer(c.observed_bytes[k])&&
        c.observed_bytes[k]<=262145&&c.observed_bytes[k]>=c.stored_bytes[k]&&
        typeof c.EOF[k]==='boolean')&&
      c.no_stream_reads_after_first_failure===true,
      'actual per-stream bounds and unchanged ambient file-size limit required '+i);
    need(l&&l.all_tracked_FDs_closed===true&&l.direct_child_reaped===true&&
      l.waitid_uses_WNOWAIT===true&&l.group_signals_after_reap_started===false&&
      l.retirement_deadline_met===true&&
      l.escaped_sessions_or_Binder_descendants_qualified===false&&
      ['observation_deadline','retirement_started','retirement_deadline',
        'reap_started_at','reaped_at','retired_at'].every(k=>finite(l[k]))&&
      l.retirement_deadline-l.retirement_started<=5.001&&
      l.retirement_started<=l.reap_started_at&&l.reap_started_at<=l.reaped_at&&
      l.reaped_at<=l.retired_at&&l.retired_at<=l.retirement_deadline&&
      Array.isArray(l.FDs)&&equal(l.FDs.map(x=>x.role),lifeRoles)&&
      l.FDs.every(x=>integer(x.fd)&&x.fd>=3&&x.close_attempted===true&&x.closed===true)&&
      Array.isArray(l.session_observations)&&l.session_observations.length>=1&&
      l.session_observations[0].stage==='after_spawn'&&
      l.session_observations.every(x=>integer(x.pid)&&x.pid>1&&
        x.pid===x.process_group&&x.pid===x.session&&x.pidfd_open===true&&
        x.reap_started===false&&finite(x.observed_monotonic))&&
      Array.isArray(l.signal_observations),
      'unreaped-session, direct-child and exact FD retirement required '+i);
    if(i<2){
      need(r.returncode===0&&r.timed_out===false&&c.complete===true&&
        c.limit_exceeded===false&&equal(c.EOF,{stdout:true,stderr:true})&&
        l.signal_observations.length===0,'successful EOF without forced retirement required '+i);
      if(i===1)need(r.stdout.bytes===262144&&r.stderr.bytes===262144,
        'both actual full-cap streams required');
    }else{
      need(r.returncode!==0&&c.complete===false&&
        l.session_observations.some(x=>x.stage==='before_group_signal')&&
        l.signal_observations.some(x=>x.kind==='own_process_group'&&x.attempted===true&&
          (x.sent===true||x.not_found===true))&&
        l.signal_observations.filter(x=>x.kind==='own_process_group')
          .every(x=>x.reap_started===false&&finite(x.observed_monotonic)&&
                    x.observed_monotonic<=l.reap_started_at),
        'failed capture must retain pre-reap own-session retirement '+i);
      if(i===2||i===3){
        const k=i===2?'stdout':'stderr';
        need(r.timed_out===false&&c.limit_exceeded===true&&
          c.stored_bytes[k]===262144&&c.observed_bytes[k]===262145&&
          c.observed_failure_preceded_capture_error===false,
          'overflow prefix and first-error order required '+i);
      }else need(r.timed_out===true&&c.limit_exceeded===false,'actual timeout required');
    }
  }
  need(v.pure_transport_order_controls.every(x=>x.passed===true&&x.real_children===0&&
       x.explicit_CompletedProcess_seam===true),'pure order controls must retain their seams');
  const events=[['authority_FD_events',7],['test_read_FD_events',16],['own_directory_FD_events',7]];
  for(const [key,count]of events)
    need(Array.isArray(v[key])&&v[key].length===count&&v[key].every(x=>integer(x.fd)&&x.fd>=3&&
         x.closed===true),'all exact test-owned FD events closed '+key);
  need(v.all_owned_test_FDs_closed===true&&v.ambient_FD_equality===true&&
    equal(v.ambient_FD_baseline_before_production_load,v.ambient_FD_final)&&
    v.host_namespaces_credentials_and_fsize_unchanged===true&&
    v.private_fixture_root_removed===true&&v.alarm_restored===true&&v.umask_restored===true&&
    ['Main_reads','Android_commands','namespace_entries','network_calls','shared_source_mutations',
     'controller_Main_Android_or_namespace_actions'].every(k=>v[k]===0)&&
    v.runtime_nonce_consumed===false&&v.production_Android_execution_qualified===false&&
    v.original_run01_status==='FAILED_OUTCOME_UNKNOWN_PRESERVED'&&
    v.signal_25_or_file_size_cause_qualified===false&&
    v.whole_invocation_resource_qualified===false,
    'host-only closure and all runtime qualification limits preserved');
  return{schema:1,kind:'pocket4-ndk-bounded-output-actual-host-qualification01',
    job:input.job,stdout:stdoutPin,terminal:terminalPin,
    exact_packet:EXPECTED.packet,five_sources:EXPECTED.members,
    real_host_children:5,pure_order_controls:2,actual_host_controls_qualified:true,
    per_stream_prefix_cap:262144,maximum_stream_observation:262145,
    Android_runtime_qualified:false,original_run01_status:'FAILED_OUTCOME_UNKNOWN_PRESERVED',
    original_rc153_cause_qualified:false,whole_invocation_resource_qualified:false};
}
