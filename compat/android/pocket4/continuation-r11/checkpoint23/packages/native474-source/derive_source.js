function deriveBuilder474Source(input,H,ud){
"use strict";
const need=(x,m)=>{if(!x)throw Error(m);},pin=s=>{const b=H.utf8(s);return{bytes:b.length,sha256:H.sha256(b),git_blob_sha1:H.gitBlob(b)};};
need(pin(input.android).git_blob_sha1==="b19deb72a9b8e47918b01cecc0a51ca636be26d2"&&pin(input.android).bytes===321919,"actual472 android");
need(pin(input.manifest).git_blob_sha1==="fb2f8303d265c0497171545c1a9356beb213d873","actual472 map");
need(pin(input.typed473).git_blob_sha1==="516598053f62351ed04b3c405b91905c9cbbfc04","actual473 source");
need(pin(input.fixture).bytes===1869&&pin(input.fixture).sha256==="9c8a0aecfa46ce0f1874362fa9dfff6a34326f9bf569b6fe7206dd6db1b3c9a6","observed consumer");
need(pin(input.actual472).bytes===185025&&pin(input.actual472).sha256==="4c2f97bee3d6dbcc742f736c46fa18e9dc869830fe82211fb83c0afed6dfdbf4","actual472 report");
let source=input.android;const edits=[];function edit(before,after){const at=source.indexOf(before);need(at>=0&&source.indexOf(before,at+before.length)<0,"source preimage "+before.slice(0,100));edits.push({at,before,after});source=source.slice(0,at)+after+source.slice(at+before.length);}
const helper=`const COMPOSER_RETIREMENT_AUDIOCONTROL_EXAMPLE_BLUEPRINT: &str =
    "hardware/interfaces/automotive/audiocontrol/aidl/default/Android.bp";

fn project_composer_retirement_audiocontrol_example(
    p: &mut Projection, source: &Path,
) -> Result<()> {
    use sha2::{Digest, Sha256};
    // Only the separately validated two-target Composer service/AIDL-test route
    // calls this projection. Keep the typed-ingress route and its own builder
    // unchanged. The observed automotive example is not one of these targets.
    // Preserve its package/license and entire journal preimage; do not change
    // parent AIDL providers, sibling code, source locks, or global discovery.
    let path = source.join(COMPOSER_RETIREMENT_AUDIOCONTROL_EXAMPLE_BLUEPRINT);
    let original = fs::read_to_string(&path)?;
    if original.len() != 1869
        || format!("{:x}", Sha256::digest(original.as_bytes()))
            != "9c8a0aecfa46ce0f1874362fa9dfff6a34326f9bf569b6fe7206dd6db1b3c9a6"
    {
        return fail(format!("Composer retirement exact Audiocontrol example Blueprint changed: {COMPOSER_RETIREMENT_AUDIOCONTROL_EXAMPLE_BLUEPRINT}"));
    }
    p.put(&path, metadata_only(&original)?)
}

`;
edit("fn composer_retirement_record(path: &Path, value: serde_json::Value) -> Result<()> {",helper+"fn composer_retirement_record(path: &Path, value: serde_json::Value) -> Result<()> {");
edit("    if composer_retirement {\n        project_composer_retirement_systemui_tests(&mut p, source)?;\n    }","    if composer_retirement {\n        project_composer_retirement_systemui_tests(&mut p, source)?;\n        project_composer_retirement_audiocontrol_example(&mut p, source)?;\n    }");
const start="    #[test]\n    fn typed_audiocontrol_example_projection_keeps_metadata_and_sibling_sources() {";
const end="    #[test]\n    fn native_engine_mode_rejects_widening_before_command_mutation() {";
const begin=input.typed473.indexOf(start),last=input.typed473.indexOf(end,begin);
need(begin>=0&&last>begin,"actual473 test block");
let tests=input.typed473.slice(begin,last)
.replaceAll("typed_audiocontrol_example_projection_","composer_retirement_audiocontrol_example_projection_")
.replaceAll("project_typed_ingress_audiocontrol_example","project_composer_retirement_audiocontrol_example")
.replaceAll("TYPED_INGRESS_AUDIOCONTROL_EXAMPLE_BLUEPRINT","COMPOSER_RETIREMENT_AUDIOCONTROL_EXAMPLE_BLUEPRINT")
.replaceAll("typed ingress shared provider source changed","Composer retirement exact Audiocontrol example Blueprint changed");
const positive="    fn composer_retirement_audiocontrol_example_projection_keeps_metadata_and_sibling_sources() {\n";
need(tests.split(positive).length===2,"single positive");
tests=tests.replace(positive,positive+`        validate_composer_retirement_route(SoongDependencyMode::Strict,
            COMPOSER_RETIREMENT_TARGETS, "droidloom_x86_64", None, false, None).unwrap();
        assert_eq!(COMPOSER_RETIREMENT_TARGETS, &[
            "android.hardware.graphics.composer3-service.droidloom",
            "droidloom-composer-aidl-tests",
        ]);
`);
edit("    #[test]\n    fn composer_retirement_route_is_strict_and_disjoint_from_framework() {",tests+"    #[test]\n    fn composer_retirement_route_is_strict_and_disjoint_from_framework() {");
edit("// existing vendor rsync list and is not invented as an Android source output.","// existing vendor rsync list and is not invented as an Android source output.");
// The line above is an exact no-op authority check, not a production change.
edits.pop();
edit("// checkout remains an independent compiler/controller input authority.","// checkout remains an independent compiler/controller input authority.");
edits.pop();
edit("// Read only the explicit production or metadata list. The complete 500-entry\n// checkout remains an independent compiler/controller input authority.","// Read only the explicit production or metadata list. The complete checkout\n// remains an independent compiler/controller input authority.");
let back=source;for(const e of [...edits].reverse()){need(back.slice(e.at,e.at+e.after.length)===e.after,"inverse offset");back=back.slice(0,e.at)+e.before+back.slice(e.at+e.after.length);}need(back===input.android,"full source inverse");
const old=JSON.parse(input.manifest);need(Object.keys(old).length===500,"parent500");
const candidate=JSON.parse(input.manifest),path="android/native-role-ingress/provider-fixtures/audiocontrol-example.Android.bp";
need(!Object.hasOwn(candidate,path),"new fixture absent before");
candidate["tools/droidloom-update/src/android.rs"]={bytes:pin(source).bytes,kind:"file",mode:420,sha256:pin(source).sha256};
candidate[path]={bytes:pin(input.fixture).bytes,kind:"file",mode:420,sha256:pin(input.fixture).sha256};
const sorted=x=>Array.isArray(x)?x.map(sorted):x&&typeof x==="object"?Object.fromEntries(Object.keys(x).sort().map(k=>[k,sorted(x[k])])):x;
const manifest=JSON.stringify(sorted(candidate),null,2)+"\n";
const unchanged=Object.keys(old).filter(k=>JSON.stringify(old[k])===JSON.stringify(candidate[k]));
need(unchanged.length===499&&Object.keys(candidate).length===501,"501 exact delta");
const oldFunctionStart=input.android.indexOf("fn project_blueprints("),oldFunctionEnd=input.android.indexOf("\npub ",oldFunctionStart);
need(oldFunctionStart>=0&&oldFunctionEnd>oldFunctionStart&&source.includes(input.android.slice(oldFunctionStart,oldFunctionEnd)),"typed/common projection body unchanged");
const testNames=[...tests.matchAll(/    fn ([a-zA-Z0-9_]+)\(\)/g)].map(m=>"android::tests::"+m[1]);need(testNames.length===3,"new3");
const production=ud(input.android,source,"tools/droidloom-update/src/android.rs")+ud("",input.fixture,path);
return{source,manifest,map:candidate,edits,production,testNames,fixture:input.fixture,unchanged,
pins:{android:pin(source),manifest:pin(manifest),fixture:pin(input.fixture),patch:pin(production)},
scope:{entry:"composer-retirement-build",targets:["android.hardware.graphics.composer3-service.droidloom","droidloom-composer-aidl-tests"],source_lock_sha256:"72848909e4931d712a3d59f344904ae8642b32c35a01cf520a51afce4c56b50d",projects:225,only_path:"hardware/interfaces/automotive/audiocontrol/aidl/default/Android.bp",only_module:"android.hardware.automotive.audiocontrol-service.example",metadata_bytes:346,metadata_sha256:"d73b00f17a80375d2d59e408088c5e875c3311bd0f7487b117d4b8d28f7cff93",typed473_branch_unmodified:true,all_parent500_other_sources_unchanged:true,ACK9_byte_identical:true,Strict_preserved:true,journal_restore_preserved:true,global_find_ignore_not_added:true,whole_generated_variant_graph_qualified:false,host_compile_performed:false}};
}
