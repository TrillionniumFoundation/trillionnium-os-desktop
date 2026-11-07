function bindPreparedVendorActual(template,actual,H) {
    const require=(v,m)=>{if(!v)throw Error(m);};
    const pin=s=>{const b=H.utf8(s);return {bytes:b.length,sha256:H.sha256(b)};};
    const names=["vendor-prep-result.json","prepared-vendor-manifest.json","prepared-vendor-config.toml"];
    require(JSON.stringify(Object.keys(actual).sort())===JSON.stringify([...names].sort()),"three raw actual inputs required");
    for(const name of names)require(typeof actual[name]==="string","raw UTF-8 original required");
    const p=Object.fromEntries(names.map(n=>[n,pin(actual[n])]));
    require(p[names[0]].bytes>0&&p[names[0]].bytes<=4*1024*1024&&
            p[names[1]].bytes>0&&p[names[1]].bytes<=32*1024*1024&&
            p[names[2]].bytes>0&&p[names[2]].bytes<=4096,"actual input byte bounds");
    // Parse only finite counters/state/pin strings here. Preserve all raw actual
    // strings byte-for-byte; never reserialize nanosecond/file-identity numbers.
    const report=JSON.parse(actual[names[0]]),manifest=JSON.parse(actual[names[1]]);
    const prepRoot="/home/alex/work/p4-retirement-wayland-vendor-prep01-20261106/attempt01";
    require(report.state==="PASS"&&report.collection_complete===true&&report.offline_vendor_prepared_qualified===true&&
        report.fixed_registry_packages===193&&report.packages.length===193&&report.Main_actions===0&&
        report.Cargo_executed===false&&report.crate_code_executed===false&&report.commands_executed===0&&
        report.shared_cache_writes===0&&report.workspace_or_lock_modified===false&&report.production_sources_modified===false&&
        report.metadata_or_compile_qualified===false&&report.production_ready===false&&
        report.secondary_errors.length===0&&report.observed_signals.length===0&&
        report.owned_resource_gate.pass===true&&report.owned_resource_fd_closed===true&&
        report.own_children_before.observed_empty===true&&report.own_children_after.observed_empty===true&&
        report.explicit_owned_descriptor_journal.remaining.length===0&&report.explicit_owned_descriptor_journal.close_errors.length===0,
        "actual prep success/input/resource/closure gates incomplete");
    for(const [name,field,suffix]of [[names[1],"vendor_manifest","vendor-manifest.json"],[names[2],"source_config","vendor-config.toml"]]){
        require(report[field].path===prepRoot+"/"+suffix&&report[field].bytes===p[name].bytes&&report[field].sha256===p[name].sha256,
                "actual parent pin differs: "+name);
    }
    require(manifest.schema===1&&manifest.registry_packages===193&&manifest.packages.length===193&&
        manifest.vendor_root===prepRoot+"/vendor"&&manifest.archive_root===prepRoot+"/archives"&&
        manifest.original_lock.bytes===51836&&
        manifest.original_lock.sha256==="c1dfa6f13f789cf40435d0d72973d029d0e264b27bd833eabb5a727492127f62"&&
        manifest.metadata_or_compilation_executed===false,
        "actual manifest scope differs");
    const expectedConfig='[source.crates-io]\nreplace-with = "pocket4-locked-vendor"\n\n[source.pocket4-locked-vendor]\ndirectory = "'+
        prepRoot+'/vendor"\n\n[net]\noffline = true\n';
    require(actual[names[2]]===expectedConfig,"actual source replacement config differs");
    const anchors={
        '"__ACTUAL_PREP_RESULT_BYTES__"':String(p[names[0]].bytes),
        '"__ACTUAL_PREP_RESULT_SHA256__"':JSON.stringify(p[names[0]].sha256),
        '"__ACTUAL_VENDOR_MANIFEST_BYTES__"':String(p[names[1]].bytes),
        '"__ACTUAL_VENDOR_MANIFEST_SHA256__"':JSON.stringify(p[names[1]].sha256),
        '"__ACTUAL_VENDOR_CONFIG_BYTES__"':String(p[names[2]].bytes),
        '"__ACTUAL_VENDOR_CONFIG_SHA256__"':JSON.stringify(p[names[2]].sha256)
    };
    let source=template;
    for(const [before,after]of Object.entries(anchors)){
        require(source.split(before).length===2,"binding literal is absent or duplicated: "+before);
        source=source.replace(before,after);
    }
    require(!source.includes("__ACTUAL_"),"unbound future literal remains");
    let inverse=source;
    const bindingLine=source.split("\n").find(line=>line.startsWith("VENDOR_BINDING = "));
    require(bindingLine!==undefined,"bound VENDOR_BINDING absent");
    const templateLine=template.split("\n").find(line=>line.startsWith("VENDOR_BINDING = "));
    inverse=inverse.replace(bindingLine,templateLine);
    require(inverse===template,"more than exact actual pins changed");
    return {source,source_pin:pin(source),actual_raw:actual,actual_pins:p,future_pins_bound:true,
        original_lock_unchanged:true,production_sources_changed:0,actual_preparation_only:true,
        metadata_check_or_link_qualified:false};
}
