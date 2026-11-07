function reproduceVendorWaylandCheckRequest(files,H,bound) {
    const require=(v,m)=>{if(!v)throw Error(m);};
    const pin=s=>{const b=H.utf8(s);return {bytes:b.length,sha256:H.sha256(b)};};
    require(bound.future_pins_bound===true&&bound.production_sources_changed===0&&
        bound.metadata_check_or_link_qualified===false,"actual preparation binding required");
    const settings=JSON.parse(files["runtime-settings.json"]),packet={};
    require(settings.root==="/home/alex/work/p4-retirement-wayland-check02-20261106"&&
        settings.key==="pocket4-denial-retirement-wayland-check-02-20261106",
        "fresh isolated checker root/key differs");
    for(const name of settings.packet_names){
        packet[name]=name==="check_wayland.py"?bound.source:files["packet/"+name];
        require(typeof packet[name]==="string","packet source absent: "+name);
    }
    require(Object.keys(packet).length===11,"unchanged nine-production-plus-manifest packet differs");
    const transferred=Object.fromEntries(Object.entries(packet).map(([name,raw])=>[name,pin(raw)]));
    const reused=JSON.parse(files["reused-authority-base.json"]);
    require(Object.keys(reused).length===5,"five original fixed authorities differ");
    const root="/home/alex/work/p4-retirement-wayland-vendor-prep01-20261106/attempt01";
    for(const [name,suffix,mode]of [
        ["vendor-prep-result.json","result.json",384],
        ["prepared-vendor-manifest.json","vendor-manifest.json",292],
        ["prepared-vendor-config.toml","vendor-config.toml",292]]){
        require(!(name in reused)&&!(name in packet),"duplicate prepared authority");
        reused[name]={path:root+"/"+suffix,...bound.actual_pins[name],mode};
    }
    const expected={...transferred,...Object.fromEntries(Object.entries(reused).map(([name,p])=>
        [name,{bytes:p.bytes,sha256:p.sha256}]))};
    const base=files["stage-base.py"],offset=base.indexOf("def require(ok,message):");
    require(offset>=0,"original checked stage body absent");
    let body=base.slice(offset);
    const once=(a,b)=>{require(body.split(a).length===2,"stage exact inverse anchor differs");body=body.replace(a,b);};
    once("len(TRANSFERRED)==11 and len(REUSED_AUTHORITY)==5 and len(EXPECTED)==16",
         "len(TRANSFERRED)==11 and len(REUSED_AUTHORITY)==8 and len(EXPECTED)==19");
    once("All five immutable actual inputs","All eight immutable actual inputs");
    once("before.st_size==wanted['bytes'] and 0<before.st_size<=1024*1024,",
         "before.st_size==wanted['bytes'] and 0<before.st_size<=(32*1024*1024 if name=='prepared-vendor-manifest.json' else 4*1024*1024 if name=='vendor-prep-result.json' else 1024*1024),");
    const stage="import hashlib,json,os,stat\nfrom pathlib import Path,PurePosixPath\nROOT=Path("+
        JSON.stringify(settings.root)+")\nTRANSFERRED="+JSON.stringify(transferred)+
        "\nREUSED_AUTHORITY="+JSON.stringify(reused)+"\nEXPECTED="+JSON.stringify(expected)+"\n"+body;
    const stdin=JSON.stringify({schema:1,stage,packet});
    require(pin(stdin).bytes<1048576,"exact stdin exceeds one MiB");
    const boundary=files["transport-base.py"]
        .replace(/EXPECTED=\{[^\n]+\}/,"EXPECTED="+JSON.stringify(pin(stdin)))
        .replace(/STAGE=\{[^\n]+\}/,"STAGE="+JSON.stringify(pin(stage)));
    const request=JSON.parse(files["request-template.json"]);
    require(request.stdin==="__STDIN__"&&request.args[3]==="__BOUNDARY__"&&
        request.host==="pocket4"&&request.executable==="/usr/bin/python3"&&request.cwd==="/"&&
        JSON.stringify(request.args.slice(0,3))===JSON.stringify(["-I","-B","-c"])&&
        request.cpu_quota_percent===100&&request.memory_max_bytes===2147483648&&
        request.nice===15&&request.timeout_seconds===1020&&request.idempotency_key===settings.key,
        "unchanged 2GiB/oneCPU Wayland checker resource/entrypoint profile differs");
    request.args[3]=boundary;request.stdin=stdin;
    return {request:JSON.stringify(request,null,2)+"\n",stdin,stage,boundary,reused,expected,transferred};
}
