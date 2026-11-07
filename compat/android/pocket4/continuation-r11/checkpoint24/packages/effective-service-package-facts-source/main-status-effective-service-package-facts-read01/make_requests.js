function makeDeploymentFactRequests(){
 const common={host:"pocket4",cwd:"/home/alex/work",env:{LC_ALL:"C",LANG:"C"},stdin:"",
  timeout_seconds:15,memory_max_bytes:134217728,cpu_quota_percent:25,nice:10};
 const properties=["Id","LoadState","ActiveState","SubState","MainPID","InvocationID","FragmentPath","DropInPaths","ExecStart","User","Group","NeedDaemonReload","UnitFileState"];
 const units=[{"name":"droidloomd.service","scope":"system","prior_pid":"3588022","prior_invocation":"67cdc2375f394012ad9d7f39b0d77426","fragment":"/usr/lib/systemd/system/droidloomd.service","key":"system-daemon"},{"name":"droidloom.service","scope":"user","prior_pid":"3588024","prior_invocation":"4f9049c783be4359b69523d88ab81d63","fragment":"/usr/lib/systemd/user/droidloom.service","key":"user-session"},{"name":"droidloom-applications.service","scope":"user","prior_pid":"3588091","prior_invocation":"c1113ca849d345b5a728205f7132427d","fragment":"/usr/lib/systemd/user/droidloom-applications.service","key":"user-applications"}];
 const requests={};
 for(const u of units)requests[u.key]={...common,executable:"/usr/bin/systemctl",
  args:["--"+u.scope,"--no-pager","--no-ask-password","--full","show","--all",
        "--property="+properties.join(","),"--",u.name],
  idempotency_key:"pocket4-status-effective-"+u.key+"-show01-20261106"};
 requests["package-ownership"]={...common,executable:"/usr/bin/dpkg-query",
  args:["--search","--",...["/usr/bin/droidloom-supervisor","/usr/bin/droidloomd","/usr/bin/droidloomctl","/usr/bin/droidloom-applications","/usr/lib/systemd/system/droidloomd.service","/usr/lib/systemd/user/droidloom.service","/usr/lib/systemd/user/droidloom-applications.service"]],
  idempotency_key:"pocket4-status-seven-installed-files-dpkg-search01-20261106"};
 return requests;
}
