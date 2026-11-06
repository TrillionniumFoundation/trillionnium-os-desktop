function reproduceRetirementHostRequest(files,H) {
    const require=(ok,message)=>{if(!ok)throw new Error(message);};
    const pin=s=>{const b=H.utf8(s);return {bytes:b.length,sha256:H.sha256(b)};};
    const settings=JSON.parse(files["runtime-settings.json"]);
    const packet={};
    for(const name of settings.packet_names) {
        require(typeof files["packet/"+name]==="string","missing packet source "+name);
        packet[name]=files["packet/"+name];
    }
    require(Object.keys(packet).length===15,"fixed fifteen-source packet differs");
    const transferred=Object.fromEntries(Object.entries(packet).map(([name,raw])=>[name,pin(raw)]));
    const reused=JSON.parse(files["reused-authority.json"]);
    require(Object.keys(reused).length===6&&!Object.keys(reused).some(k=>k in packet),"six-actual-authority partition differs");
    const expected={...transferred,...Object.fromEntries(Object.entries(reused).map(([name,p])=>[name,{bytes:p.bytes,sha256:p.sha256}]))};
    const old=files["stage-base.py"],offset=old.indexOf("def require(ok,message):");
    require(offset>=0,"stage body absent");
    let body=old.slice(offset);
    const once=(a,b)=>{require(body.split(a).length===2,"stage inverse anchor differs");body=body.replace(a,b);};
    once("len(TRANSFERRED)==13 and len(REUSED_AUTHORITY)==11 and len(EXPECTED)==24",
         "len(TRANSFERRED)==15 and len(REUSED_AUTHORITY)==6 and len(EXPECTED)==21");
    once("All eleven immutable actual inputs","All six immutable actual inputs");
    once("source/'compile_builder.py'","source/'compile_fixture.py'");
    const stage="import hashlib,json,os,stat\nfrom pathlib import Path,PurePosixPath\nROOT=Path("+
        JSON.stringify(settings.root)+")\nTRANSFERRED="+JSON.stringify(transferred)+
        "\nREUSED_AUTHORITY="+JSON.stringify(reused)+"\nEXPECTED="+JSON.stringify(expected)+"\n"+body;
    const stdin=JSON.stringify({schema:1,stage,packet});
    require(pin(stdin).bytes<1048576,"process_start exact stdin exceeds one MiB");
    const boundary=files["transport-base.py"]
        .replace(/EXPECTED=\{[^\n]+\}/,"EXPECTED="+JSON.stringify(pin(stdin)))
        .replace(/STAGE=\{[^\n]+\}/,"STAGE="+JSON.stringify(pin(stage)))
        .replaceAll("fixed provider compiler","fixed retirement host compiler")
        .replaceAll("<fixed-provider-stage>","<fixed-retirement-host-stage>");
    const request=JSON.parse(files["request-template.json"]);
    require(request.stdin==="__STDIN__"&&request.args[3]==="__BOUNDARY__","request placeholders differ");
    require(request.host==="pocket4"&&request.executable==="/usr/bin/python3"&&request.cwd==="/"&&
        JSON.stringify(request.args.slice(0,3))===JSON.stringify(["-I","-B","-c"])&&
        request.cpu_quota_percent===100&&request.memory_max_bytes===1073741824&&request.nice===15&&
        request.timeout_seconds===600&&request.idempotency_key===settings.key,
        "fixed host-only resource/entrypoint profile differs");
    request.args[3]=boundary;request.stdin=stdin;
    return {request:JSON.stringify(request,null,2)+"\n",stdin,stage,boundary,expected,transferred};
}
