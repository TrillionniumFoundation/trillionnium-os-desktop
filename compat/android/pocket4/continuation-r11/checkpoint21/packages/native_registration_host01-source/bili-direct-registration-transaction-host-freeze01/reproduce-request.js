function reproduceComposerTransactionRequest(files, H) {
    const require = (ok, message) => { if (!ok) throw new Error(message); };
    const pin = s => { const b=H.utf8(s); return {bytes:b.length,sha256:H.sha256(b)}; };
    const settings=JSON.parse(files["runtime-settings.json"]);
    const packet={};
    for(const name of settings.packet_names) {
        require(typeof files["packet/"+name] === "string", "missing packet source "+name);
        packet[name]=files["packet/"+name];
    }
    require(Object.keys(packet).length===6, "fixed packet count differs");
    const transferred=Object.fromEntries(Object.entries(packet).map(([name,raw])=>[name,pin(raw)]));
    const reused=JSON.parse(files["reused-authority.json"]);
    require(Object.keys(reused).length===5 && !Object.keys(reused).some(k=>k in packet),"authority partition differs");
    const expected={...transferred,...Object.fromEntries(Object.entries(reused).map(([name,p])=>[name,{bytes:p.bytes,sha256:p.sha256}]))};
    const old=files["stage-base.py"];
    const offset=old.indexOf("def require(ok,message):");
    require(offset>=0,"stage baseline body missing");
    let body=old.slice(offset);
    const once=(oldText,newText)=>{
        require(body.split(oldText).length===2,"stage edit not unique");
        body=body.replace(oldText,newText);
    };
    once("len(TRANSFERRED)==13 and len(REUSED_AUTHORITY)==11 and len(EXPECTED)==24",
         "len(TRANSFERRED)==6 and len(REUSED_AUTHORITY)==5 and len(EXPECTED)==11");
    once("All eleven immutable actual inputs","All five immutable actual inputs");
    once("source/'compile_builder.py'","source/'compile_fixture.py'");
    const stage="import hashlib,json,os,stat\nfrom pathlib import Path,PurePosixPath\nROOT=Path("+
        JSON.stringify(settings.root)+")\nTRANSFERRED="+JSON.stringify(transferred)+
        "\nREUSED_AUTHORITY="+JSON.stringify(reused)+"\nEXPECTED="+JSON.stringify(expected)+"\n"+body;
    const wire=JSON.stringify({schema:1,stage,packet});
    require(pin(wire).bytes < 1048576,"tool stdin one MiB bound");
    let boundary=files["transport-base.py"]
        .replace(/EXPECTED=\{[^\n]+\}/,"EXPECTED="+JSON.stringify(pin(wire)))
        .replace(/STAGE=\{[^\n]+\}/,"STAGE="+JSON.stringify(pin(stage)))
        .replaceAll("fixed provider compiler","fixed composer transaction host")
        .replaceAll("<fixed-provider-stage>","<fixed-composer-transaction-stage>");
    const request=JSON.parse(files["request-template.json"]);
    require(request.stdin==="__STDIN__"&&request.args[3]==="__BOUNDARY__","request placeholders differ");
    require(request.host==="pocket4"&&request.executable==="/usr/bin/python3"&&
            request.cwd==="/"&&request.cpu_quota_percent===100&&request.memory_max_bytes===1073741824&&
            request.nice===15&&request.timeout_seconds===600&&
            request.idempotency_key===settings.key,"fixed request profile differs");
    request.args[3]=boundary;
    request.stdin=wire;
    return {request:JSON.stringify(request,null,2)+"\n",stdin:wire,stage,boundary,expected};
}
