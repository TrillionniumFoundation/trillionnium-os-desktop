"use strict";
function makeLockMetadataRequest(source,U) {
 const b=U.utf8(source);
 if (b.length!==18374 || U.sha256(b)!=="a8df6f66b30cfa9def85de494b781926cbccbd48784ca94068678c02e643b05f") throw new Error("exact diagnostic source required");
 const q={
  "args": [
    "-n",
    "/usr/bin/python3",
    "-I",
    "-B",
    "-"
  ],
  "cpu_quota_percent": 100,
  "cwd": "/home/alex/work",
  "executable": "/usr/bin/sudo",
  "host": "pocket4",
  "idempotency_key": "p4-ndk-residual-action-lock-metadata01-a8df6f66b30cfa9d",
  "memory_max_bytes": 134217728,
  "nice": 15,
  "timeout_seconds": 45
};
 q.stdin=source;
 const ordered={};
 for (const name of ["args","cpu_quota_percent","cwd","executable","host","idempotency_key","memory_max_bytes","nice","stdin","timeout_seconds"]) ordered[name]=q[name];
 return JSON.stringify(ordered,null,2)+"\n";
}
