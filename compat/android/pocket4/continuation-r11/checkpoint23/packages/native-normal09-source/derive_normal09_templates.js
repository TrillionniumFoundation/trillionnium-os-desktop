function deriveNormal09Templates(input,H){
"use strict";
const need=(x,m)=>{if(!x)throw Error(m);};
const pin=s=>{const b=H.utf8(s);return{bytes:b.length,sha256:H.sha256(b),git_blob_sha1:H.gitBlob(b)};};
const pins={
framework:[62692,"e1f89dfb673c905c6b672817c17e5725e4b2fff8ca501d64269803342ed6385e"],
fence:[25483,"7c24d472ef1adf37ff283d0760983fe570587bf8a3d52480caa5ce666b73bc35"],
request08:[1022914,"7ac74723eaff25849512943bfe25ec87ec0eff36807f5b787f44862c31033c65"],
map473:[99775,"a3426e40f9446b85931c82e8ba08335e72cd9bd0ac4a3f70aa01d54200d1ae13"],
prior08inner:[2898,"58a68cae2784bf401315c8016108304576e11d16bf3d5c64552698d4c3a2bb57"],
prior08outer:[24714,"2e10bdca3a1b88fe8e72f87dde5f38d972f8db41ce087386fa189c40ad231612"]
};
for(const[k,[bytes,sha]]of Object.entries(pins)){const p=pin(input[k]);need(p.bytes===bytes&&p.sha256===sha,"exact original "+k);}
const edits={framework:[],fence:[]};let source=input.framework;
function change(before,after,count=1){const found=source.split(before).length-1;need(found===count,"framework preimage "+before.slice(0,100)+": "+found);edits.framework.push({before,after,count});source=source.split(before).join(after);}
function line(prefix,after){const rows=source.split("\n").filter(x=>x.startsWith(prefix));need(rows.length===1,"unique line "+prefix);change(rows[0],after);}
const newTests=[
"android::tests::typed_audiocontrol_example_projection_keeps_metadata_and_sibling_sources",
"android::tests::typed_audiocontrol_example_projection_rejects_source_drift_before_write",
"android::tests::typed_audiocontrol_example_projection_recovers_full_observed_original"];
const oldTests=JSON.parse(source.split("\n").find(x=>x.startsWith("EXPECTED_TESTS = ")).slice(17));
need(oldTests.length===21,"old tests21");
const tests=[...oldTests,...newTests],indices=[...Array.from({length:18},(_,i)=>i),200,201,202,203,204,205];
const oldLabels=JSON.parse(source.split("\n").find(x=>x.startsWith("EXPECTED_COMPILE_LABELS = ")).slice(26));
need(oldLabels.length===68,"old labels68");
const labels=[...oldLabels];let pos=labels.indexOf("projection-test-202");need(pos>0,"old last SystemUI");
labels.splice(pos+1,0,"projection-test-203","projection-test-204","projection-test-205");
const delta={
Cargo_lock_or_dependency_manifest_changed:false,Go5_or_Blueprint_patch_changed:false,Rust_source_files_changed:1,
SystemUI471_projection_and_fixture_unchanged:true,actual_source_file_count:501,
added:["android/native-role-ingress/provider-fixtures/audiocontrol-example.Android.bp"],
builder_revision_name:"473-fixed-audiocontrol-example-projection",changed_existing:["tools/droidloom-update/src/android.rs"],
current_hal_source_lock_unchanged:true,engine_source_files_changed:0,fixed_Audiocontrol_example_BP_original_fixture_added:true,
framework_sources_executed_or_built:false,new_exact_hal_provider_source_lock_added:false,new_exact_provider_source_lock_added:false,
previous_source_locks_changed:false,real_published_source_accessed:false,real_source_staging_accessed:false,runtime_authorization_enabled:false,
source_resume_library_changed:false,typed_ingress_framework_patch_changed:false,unchanged_existing:499};
change("ROOT = OWNER / 'typed-ingress-framework-provider-build-08-20261106'","ROOT = OWNER / 'typed-ingress-framework-provider-build-09-20261106'");
change("PREVIOUS_ROOT = OWNER / 'typed-ingress-framework-provider-build-07-20261106'","PREVIOUS_ROOT = OWNER / 'typed-ingress-framework-provider-build-08-20261106'");
change("pocket4-native-typed-ingress-builder471-systemui-test-projection-compile-01-20261106","pocket4-native-typed-ingress-builder473-audiocontrol-example-projection-compile-01-20261106");
for(const token of ["BUILDER471_SHA256","BUILDER471_BYTES","COMPILE471_RESULT_SHA256","COMPILE471_RESULT_BYTES"])change("__ACTUAL_"+token+"__","__ACTUAL_"+token.replace("471","473")+"__");
change("c29c7b05fcfdf3def918d2bc963c6fe0c25a0430c87249f3de781d5d8bf68ae0","a3426e40f9446b85931c82e8ba08335e72cd9bd0ac4a3f70aa01d54200d1ae13");
change("7bb06799bc311b64541c1cb9fe23a5b0ce0796d0476e7eb1fcbc7ff37938f3a3","58a68cae2784bf401315c8016108304576e11d16bf3d5c64552698d4c3a2bb57");
change("58aa37d06c97d507556b9fa141b7870053e931b11b307bc03671e54c71342c21","2e10bdca3a1b88fe8e72f87dde5f38d972f8db41ce087386fa189c40ad231612");
line("EXPECTED_TESTS = ","EXPECTED_TESTS = "+JSON.stringify(tests));
line("EXPECTED_TEST_INDICES = ","EXPECTED_TEST_INDICES = "+JSON.stringify(indices));
line("EXPECTED_COMPILE_LABELS = ","EXPECTED_COMPILE_LABELS = "+JSON.stringify(labels));
line("EXPECTED_SOURCE_DELTA = ","EXPECTED_SOURCE_DELTA = json.loads("+JSON.stringify(JSON.stringify(delta))+")");
change("ACTUAL_BUILDER471_COMPILE01_REQUIRED","ACTUAL_BUILDER473_COMPILE01_REQUIRED");
change("actual-builder471-result.json","actual-builder473-result.json");
change("result['focused_tests_passed'] == 30 and result['updater_focused_tests_passed'] == 21","result['focused_tests_passed'] == 33 and result['updater_focused_tests_passed'] == 24");
change("result['actual_registered_test_count'] == 211","result['actual_registered_test_count'] == 214");
change("result['systemui_test_projection_tests_passed'] == 3,","result['systemui_test_projection_tests_passed'] == 3 and\n            result['audiocontrol_example_projection_tests_passed'] == 3,");
change("actual builder471 compile01 and exact 30-control qualification differs","actual builder473 compile01 and exact 33-control qualification differs");
change("(EXPECTED_TEST_INDICES, EXPECTED_TESTS, 211,","(EXPECTED_TEST_INDICES, EXPECTED_TESTS, 214,");
change("result['copied_manifest']['bytes'] == 99548","result['copied_manifest']['bytes'] == 99775");
change("delta['actual_source_file_count'] == 500 and delta['unchanged_existing'] == 498","delta['actual_source_file_count'] == 501 and delta['unchanged_existing'] == 499");
change("delta['added'] == ['android/native-role-ingress/provider-fixtures/SystemUI-tests.Android.bp']","delta['added'] == ['android/native-role-ingress/provider-fixtures/audiocontrol-example.Android.bp']");
change("delta['builder_revision_name'] == '471-fixed-systemui-test-projection'","delta['builder_revision_name'] == '473-fixed-audiocontrol-example-projection'");
change("builder source is not the exact reviewed 500-file SystemUI test projection successor","builder source is not the exact reviewed 501-file Audiocontrol example projection successor");
const oldAuthority=`    require(result['actual_parent470_compile_authority']['bytes'] == 172040 and
            result['actual_parent470_compile_authority']['sha256'] == 'f4e78f21dec485f59ff2149cb12298c070142dbad4e29b00a776729a376eea4c' and
            result['systemui_test_projection_authority']['bytes'] == 6531 and
            result['systemui_test_projection_authority']['sha256'] == '17fe54cebd452ef14258461f0817b9cbc753ccb0619f28e7274e61879a89d762' and
            result['systemui_test_original_fixture_authority']['bytes'] == 3392 and
            result['systemui_test_original_fixture_authority']['sha256'] == 'f1b2422c693a8f8c52034369ded585a3a93ac861f9dd6dd73f0801a77e6be4da' and`;
const newAuthority=`    require(result['actual_parent471_compile_authority']['bytes'] == 181273 and
            result['actual_parent471_compile_authority']['sha256'] == '466d01e56fa6579636be8e82eedbc4276c31ce3e6b390dc985fe3bc454ead1e9' and
            result['audiocontrol_example_projection_authority']['bytes'] == 6453 and
            result['audiocontrol_example_projection_authority']['sha256'] == 'c642e886b77adeb07d8f38a3dd10d042218e8e6582d6fd523be751ef1317b2e5' and
            result['audiocontrol_example_original_fixture_authority']['bytes'] == 1869 and
            result['audiocontrol_example_original_fixture_authority']['sha256'] == '9c8a0aecfa46ce0f1874362fa9dfff6a34326f9bf569b6fe7206dd6db1b3c9a6' and
            result['systemui_test_projection_retained_from_parent471'] is True and`;
change(oldAuthority,newAuthority);
change("builder471 actual parent, exact test projection and unchanged current lock are incomplete","builder473 actual parent, exact example projection and unchanged current lock are incomplete");
change("SOURCE_MANIFEST_SHA, 99548","SOURCE_MANIFEST_SHA, 99775",2);
change("expected-builder471-manifest.json","expected-builder473-manifest.json");
change("len(source_map) == 500","len(source_map) == 501");
change("            source_map['android/manifest/m2-role-ingress-source-lock.json']['sha256'] == PREVIOUS_TYPED_LOCK_SHA and",
`            source_map['android/native-role-ingress/provider-fixtures/audiocontrol-example.Android.bp'] == {
                'bytes': 1869, 'kind': 'file', 'mode': 420,
                'sha256': '9c8a0aecfa46ce0f1874362fa9dfff6a34326f9bf569b6fe7206dd6db1b3c9a6'} and
            source_map['android/manifest/m2-role-ingress-source-lock.json']['sha256'] == PREVIOUS_TYPED_LOCK_SHA and`);
change("PRIOR_OUTER_SHA, 24693","PRIOR_OUTER_SHA, 24714");
change('\\"pid\\":216529','\\"pid\\":1067696');
change("55402a33796cd7ab55fda66660b696eb871c72869d70fb2a3dda3f22d68daa82","b1432c4cbb985f2909b4325a235e7f4edd03afe91b5dc109cd90d74829732834");
change("a164f7eed58c21aa7e5f307d70deabdc092ab732e80b23dff78b32cbc80be965","cbbc3ea39583d9c3bdb10b7934bd4c568be1a269e336f9b3ce0f91cf25517c14");
change("actual 500-file builder source changed","actual 501-file builder source changed");
change("'builder_source_files': 500, 'actual_host_compile_commands': 68, 'actual_exact_controls': 30","'builder_source_files': 501, 'actual_host_compile_commands': 71, 'actual_exact_controls': 33");
let framework=source;
let fence=input.fence;
for(const[before,after]of [
["__BOUND_FRAMEWORK471_CONTROLLER_SHA256__","__BOUND_FRAMEWORK473_CONTROLLER_SHA256__"],
["typed-ingress-framework-provider-build-08-20261106","typed-ingress-framework-provider-build-09-20261106"]
]){need(fence.split(before).length===2,"fence preimage");edits.fence.push({before,after,count:1});fence=fence.replace(before,after);}
for(const[k,out]of [["framework",framework],["fence",fence]]){let s=out;for(const e of [...edits[k]].reverse()){need(s.split(e.after).length-1===e.count,"inverse count "+k);s=s.split(e.after).join(e.before);}need(s===input[k],"whole inverse "+k);}
const packet=JSON.parse(JSON.parse(input.request08).stdin),templateFiles={};
for(const[n,s]of Object.entries(packet.files)){
if(n==="actual-builder471-result.json")continue;
if(n==="expected-builder471-manifest.json")templateFiles["expected-builder473-manifest.json"]=input.map473;
else if(n==="framework_build.py")templateFiles[n]=framework;
else if(n==="fenced_build.py")templateFiles[n]=fence;
else if(n==="prior-framework-inner-terminal.json")templateFiles[n]=input.prior08inner;
else if(n==="prior-framework-outer-terminal.json")templateFiles[n]=input.prior08outer;
else templateFiles[n]=s;
}
need(Object.keys(templateFiles).length===17,"template17");
const unchanged=Object.entries(templateFiles).filter(([n,s])=>s===packet.files[n]).map(([n])=>n);
need(unchanged.length===12,"original12authority preserved");
return{framework,fence,templateFiles,edits,tests,indices,labels,delta,unchanged,
pins:{framework:pin(framework),fence:pin(fence),templateFiles:Object.fromEntries(Object.entries(templateFiles).map(([n,s])=>[n,(({bytes,sha256})=>({bytes,sha256}))(pin(s))]))}};
}
