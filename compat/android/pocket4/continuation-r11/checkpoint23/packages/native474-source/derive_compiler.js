function deriveCompiler474(input,D,H){
"use strict";
const need=(x,m)=>{if(!x)throw Error(m);},pin=s=>{const b=H.utf8(s);return{bytes:b.length,sha256:H.sha256(b),git_blob_sha1:H.gitBlob(b)};};
need(pin(input.compiler).git_blob_sha1==="a2cfd7735e59fe836589abbbedfeb0cb49255a55","compiler472");
need(pin(input.parentProof).git_blob_sha1==="c6d3d88a50e7dc73bfdf20d9f6941e723cd10190"&&pin(input.parentScope).git_blob_sha1==="c34b3453034ebd9b984c35fed490906c9850f2a9","parent proof scope");
need(pin(input.actual472).git_blob_sha1==="3eb5f300ed6016559fa02ce66d01a6e56da00416","actual472");
const parentProof=JSON.parse(input.parentProof),scope=JSON.parse(input.parentScope);
scope.status="SOURCE_ONLY_COMPOSER_AUDIOCONTROL_PROJECTION_NOT_COMPILED";
scope.manifest="expected-builder474-manifest.json";scope.map_entries=501;
delete scope.map_delta_from_actual470;
scope.map_delta_from_actual472={baseline_entries:500,candidate_entries:501,unchanged:499,replaced:["tools/droidloom-update/src/android.rs"],added:["android/native-role-ingress/provider-fixtures/audiocontrol-example.Android.bp"],ACK9_unchanged:true};
scope.fixed_Audiocontrol_example_projection={path:D.scope.only_path,original:D.pins.fixture,removed_exact_modules:[D.scope.only_module],package_license_retained:true,parent_AIDL_providers_and_siblings_unchanged:true,independent_composer_only_call:true,typed473_candidate_not_changed:true,whole_generated_variant_graph_qualified:false};
scope.focused_tests=[...scope.focused_tests,...D.testNames];
const scopeRaw=JSON.stringify(scope,null,2)+"\n";
const proof=JSON.parse(input.sourceProof);
proof.scope=scope;proof.source_checkpoint_tree="7508b3001234d2a8cc5ece5d858902583a18e1d4";
proof.parent472_entry_proof=pin(input.parentProof);proof.parent472_build_scope=pin(input.parentScope);
proof.candidate.source_delta=["android/native-role-ingress/provider-fixtures/audiocontrol-example.Android.bp","tools/droidloom-update/src/android.rs"];
proof.ACK_SOURCE_PINS=parentProof.ACK_SOURCE_PINS;
proof.typed473_projection_not_used_as_parent=true;proof.host_compile_performed=false;
const proofRaw=JSON.stringify(proof,null,2)+"\n";
let c=input.compiler;const edits=[];
function edit(before,after,count=1){const positions=[];for(let p=c.indexOf(before);p>=0;p=c.indexOf(before,p+before.length))positions.push(p);need(positions.length===count,"compiler preimage "+before.slice(0,120)+" found "+positions.length);edits.push({before,after,count,positions});for(const p of [...positions].reverse())c=c.slice(0,p)+after+c.slice(p+before.length);}
function line(prefix,after){const rows=c.split("\n").filter(s=>s.startsWith(prefix));need(rows.length===1,"compiler line "+prefix);edit(rows[0],after);}
function block(first,last,after){const a=c.indexOf(first),b=c.indexOf(last,a);need(a>=0&&b>a,"compiler block "+first);edit(c.slice(a,b),after);}
edit('"""Compile independent builder472 Composer/AIDL build-only entry with 23 updater and 9 source controls; no platform execution."""','"""Compile builder474 fixed Composer Audiocontrol example projection with 26 updater and 9 source controls; no platform execution."""');
edit("BASE_SOURCE = Path('/home/alex/work/pocket4-native-typed-ingress-builder470-published-lock-alignment-compile-01-20261106/builder-source')","BASE_SOURCE = Path('/home/alex/work/pocket4-native-builder472-composer-retirement-entry-compile-01-20261106/builder-source')");
edit("ROOT = Path('/home/alex/work/pocket4-native-builder472-composer-retirement-entry-compile-01-20261106')","ROOT = Path('/home/alex/work/pocket4-native-builder474-composer-audiocontrol-projection-compile-01-20261106')");
line("MANIFEST_PARENT = ","MANIFEST_PARENT = 'fcbf72b891d9a9bbbcd015777e50cc3ade436f25732a603b51de261eab9cb27a'");
line("MANIFEST_472 = ","MANIFEST_474 = '"+D.pins.manifest.sha256+"'");
line("TESTS = ORIGINAL_TESTS + ","COMPOSER_AUDIOCONTROL_TESTS = "+JSON.stringify(D.testNames)+"\nTESTS = ORIGINAL_TESTS + TYPED_INGRESS_TESTS + PROVIDER_CLOSURE_TESTS + HAL_PROVIDER_TESTS + COMPOSER_ENTRY_TESTS + COMPOSER_AUDIOCONTROL_TESTS");
const oldDelta=parentProof.candidate.source_delta;
line("FIXED_PROVIDER_DELTA = ","PARENT_PROVIDER_DELTA = "+JSON.stringify(oldDelta)+"\nFIXED_PROVIDER_DELTA = "+JSON.stringify(proof.candidate.source_delta));
line("COMPOSER_ENTRY_PROOF_SHA = ","COMPOSER_ENTRY_PROOF_SHA = '3bc022c9924dc13f7e2ad8d6ed85a079af1dec61733433b88c2c76d0df0c60da'\nCOMPOSER_AUDIOCONTROL_PROOF_SHA = '"+pin(proofRaw).sha256+"'\nCOMPOSER_BUILD_SCOPE_SHA = '"+pin(scopeRaw).sha256+"'");
edit("fresh builder472 independent Composer/AIDL strict build-only entry compile01, 500 source files, 18 original plus 5 new updater controls and 9 unchanged source-resume controls; no real published source/staging/Soong/Java/Android/service execution","fresh builder474 Composer exact Audiocontrol example projection compile01, 501 source files, 23 existing plus 3 new updater controls and 9 unchanged source-resume controls; no real published source/staging/Soong/Java/Android/service execution");
edit("compiled-parent470-manifest.json","compiled-parent472-manifest.json");
edit("expected-builder472-manifest.json","expected-builder474-manifest.json");
edit("MANIFEST_472","MANIFEST_474",3);
edit("len(expected)==499 and len(copied_expected)==500","len(expected)==500 and len(copied_expected)==501");
block("        parent_raw,parent_pin=pinned_packet('compiled-parent470-result.json',","        roots_raw,roots_pin=pinned_packet(",
`        parent_raw,parent_pin=pinned_packet('compiled-parent472-result.json',
            '4c2f97bee3d6dbcc742f736c46fa18e9dc869830fe82211fb83c0afed6dfdbf4')
        parent=json.loads(parent_raw)
        require(parent_pin['bytes']==185025 and parent['state']=='PASS' and
                parent['focused_tests_passed']==32 and parent['updater_focused_tests_passed']==23 and
                parent['source_resume_tests_passed']==9 and parent['provider_closure_tests_passed']==6 and
                parent['hal_provider_tests_passed']==3 and parent['composer_entry_tests_passed']==5 and
                parent['actual_registered_test_count']==213 and parent['source_actual_registered_test_count']==20 and
                parent['expected_test_names']==TESTS[:-len(COMPOSER_AUDIOCONTROL_TESTS)] and
                parent['expected_source_resume_test_names']==SOURCE_RESUME_TESTS and
                len(parent['commands'])==71 and all(row['returncode']==0 and not row['timed_out'] for row in parent['commands']) and
                parent['copied_manifest']['bytes']==99523 and parent['copied_manifest']['sha256']==MANIFEST_PARENT and
                parent['builder_elf']['bytes']==34883904 and
                parent['builder_elf']['sha256']=='db544d5d4fb3f8aabb37d4c41248bf19968dc015c16f7e65511a50486b017043' and
                parent['owned_resource_gate']['pass'] is True and not parent['dependency_changes'] and
                not parent['tool_changes'] and not parent['cleanup']['errors'] and not parent['cleanup']['remaining'] and
                not parent['cleanup']['forced_cleanup'] and parent['copied_source_unchanged_after'] is True and
                parent['original_source_unchanged_after'] is True and parent['cargo_configs_unchanged_after'] is True and
                parent['source_delta']['actual_source_file_count']==500 and
                parent['source_delta']['ACK_nine_production_sources_unchanged_from_actual_Wayland03'] is True and
                parent['source_delta']['current_hal_source_lock_unchanged'] is True and parent['source_lock_writer']=='UNKNOWN' and
                parent['Composer_Android_Binder_ABI_compiled'] is False and
                parent['Composer_service_or_AIDL_tests_executed'] is False and
                parent['framework_Java_and_Android_JNI_compiled'] is False and
                parent['runtime_authorization_enabled'] is False,
                'actual compiled parent472 qualification differs')
        report['actual_parent472_compile_authority']=parent_pin
`);
block("        proof_raw,proof_pin=pinned_packet('composer-entry-proof.json',","        lock_name='android/manifest/m2-role-ingress-hal-provider-source-lock.json'",
`        proof_raw,proof_pin=pinned_packet('parent472-entry-proof.json',COMPOSER_ENTRY_PROOF_SHA)
        proof=json.loads(proof_raw)
        require(proof['state']=='SOURCE_ONLY_COMPOSER_RETIREMENT_ENTRY_NOT_COMPILED' and
                proof['baseline']['manifest']['sha256']=='d87ab919c015a8739011a83add768db28c7f7296a7be9683a0516b28808c1057' and
                proof['baseline']['compile_result']['sha256']==parent['actual_parent470_compile_authority']['sha256'] and
                proof['candidate']['manifest']['sha256']==MANIFEST_PARENT and
                proof['candidate']['source_delta']==PARENT_PROVIDER_DELTA and
                proof['candidate']['source_files']==500 and proof['candidate']['unchanged']==489 and
                proof['candidate']['replaced']==[name for name in PARENT_PROVIDER_DELTA if name!='graphics/droidloom-wayland/src/retirement.rs'] and
                proof['candidate']['added']==['graphics/droidloom-wayland/src/retirement.rs'] and
                proof['new_focused_tests']==COMPOSER_ENTRY_TESTS and proof['host_compile_performed'] is False and
                proof['ACK_SOURCE_PINS']==ACK_SOURCE_PINS and proof['separate_from_typed_builder471'] is True,
                'compiled parent472 entry/source proof changed')
        parent_scope_raw,parent_scope_pin=pinned_packet('parent472-build-scope.json',
            'f43cd778b75e484d53899eab543680e6b32ae5e54d6eca373b34223dcfcc8af9')
        parent_scope=json.loads(parent_scope_raw)
        require(parent_scope==proof['scope'] and
                parent['composer_entry_proof_authority']['sha256']==proof_pin['sha256'] and
                parent['composer_build_scope_authority']['sha256']==parent_scope_pin['sha256'],
                'actual parent472 fixed entry scope differs')
        projection_raw,projection_pin=pinned_packet('composer-audiocontrol-proof.json',COMPOSER_AUDIOCONTROL_PROOF_SHA)
        projection=json.loads(projection_raw)
        require(projection['state']=='SOURCE_ONLY_COMPOSER_AUDIOCONTROL_EXAMPLE_NOT_COMPILED' and
                projection['baseline']['manifest']['sha256']==MANIFEST_PARENT and
                projection['baseline']['actual']['sha256']==parent_pin['sha256'] and
                projection['candidate']['manifest']['sha256']==MANIFEST_474 and
                projection['candidate']['source_files']==501 and projection['candidate']['unchanged']==499 and
                projection['candidate']['source_delta']==FIXED_PROVIDER_DELTA and
                projection['candidate']['replaced']==['tools/droidloom-update/src/android.rs'] and
                projection['candidate']['added']==['android/native-role-ingress/provider-fixtures/audiocontrol-example.Android.bp'] and
                projection['new_focused_tests']==COMPOSER_AUDIOCONTROL_TESTS and
                projection['host_compile_performed'] is False and projection['ACK_SOURCE_PINS']==ACK_SOURCE_PINS and
                projection['typed473_projection_not_used_as_parent'] is True,
                'fixed Composer Audiocontrol projection proof differs')
        fixture_raw,fixture_pin=pinned_packet(
            'delta/android/native-role-ingress/provider-fixtures/audiocontrol-example.Android.bp',
            '9c8a0aecfa46ce0f1874362fa9dfff6a34326f9bf569b6fe7206dd6db1b3c9a6')
        require(fixture_pin['bytes']==1869 and projection['fixture']['bytes']==1869 and
                projection['fixture']['sha256']==fixture_pin['sha256'],
                'observed full Audiocontrol example fixture changed')
        scope_raw,scope_pin=pinned_packet('build-scope.json',COMPOSER_BUILD_SCOPE_SHA)
        scope=json.loads(scope_raw)
        require(scope==projection['scope'] and scope['entry']=='composer-retirement-build' and
                scope['targets']==['android.hardware.graphics.composer3-service.droidloom','droidloom-composer-aidl-tests'] and
                scope['dependency_mode']=='Strict' and scope['ALLOW_MISSING_DEPENDENCIES'] is False and
                scope['map_entries']==501 and scope['read_fresh_every_project_before_reconcile'] is True and
                scope['work_locks']==['package-build.lock','aosp-source-update.lock'] and
                scope['projection_journal']=='source-projection.json' and
                scope['resume_or_prior_lock_fallback'] is False and
                scope['source_tests_executed'] is False and scope['android_tests_built'] is False and
                scope['Binder_ABI_qualified'] is False and scope['Main_actions']==0 and
                scope['fixed_SystemUI_child_projection']['independent_composer_only_call'] is True and
                scope['fixed_SystemUI_child_projection']['typed_471_candidate_not_changed'] is True and
                scope['fixed_Audiocontrol_example_projection']['independent_composer_only_call'] is True and
                scope['fixed_Audiocontrol_example_projection']['typed473_candidate_not_changed'] is True,
                'fixed Composer targets, exact example projection, strict lock or build-only scope differs')
`);
edit("        report['composer_build_scope_authority']=scope_pin","        report['parent472_build_scope_authority']=parent_scope_pin\n        report['composer_audiocontrol_projection_authority']=projection_pin\n        report['audiocontrol_example_original_fixture_authority']=fixture_pin\n        report['composer_build_scope_authority']=scope_pin");
edit("sum(name in expected for name in changes)==10","sum(name in expected for name in changes)==1");
edit("Composer entry delta is not exactly ten Rust replacements and one retirement source addition","Composer projection delta is not exactly one Rust replacement and one observed fixture addition");
edit("actual copied 500-file builder472 manifest differs","actual copied 501-file builder474 manifest differs");
block("        report['source_delta']={'changed_existing':","        env.update({'PATH':",
`        report['source_delta']={'changed_existing':[name for name in wanted if name in expected],
                                'added':[name for name in wanted if name not in expected],
                                'unchanged_existing':499,'actual_source_file_count':501,
                                'builder_revision_name':'474-composer-audiocontrol-example-projection','Rust_source_files_changed':1,
                                'Cargo_lock_or_dependency_manifest_changed':False,
                                'Go5_or_Blueprint_patch_changed':False,'engine_source_files_changed':0,
                                'typed_ingress_framework_patch_changed':False,'previous_source_locks_changed':False,
                                'new_exact_provider_source_lock_added':False,'new_exact_hal_provider_source_lock_added':False,
                                'current_hal_source_lock_unchanged':True,'ACK_nine_production_sources_unchanged_from_actual_Wayland03':True,
                                'typed_builder473_not_changed_or_used_as_baseline':True,
                                'Composer472_entry_and_SystemUI_projection_retained':True,
                                'fixed_Audiocontrol_example_BP_original_fixture_added':True,
                                'source_resume_library_changed':False,'real_published_source_accessed':False,
                                'real_source_staging_accessed':False,'framework_sources_executed_or_built':False,
                                'runtime_authorization_enabled':False}
`);
edit("len(COMPOSER_ENTRY_TESTS)==5 and len(TESTS)==len(set(TESTS))==23","len(COMPOSER_ENTRY_TESTS)==5 and len(COMPOSER_AUDIOCONTROL_TESTS)==3 and len(TESTS)==len(set(TESTS))==26");
edit("PARENT_TESTS+PROVIDER_CLOSURE_TESTS+HAL_PROVIDER_TESTS+COMPOSER_ENTRY_TESTS)","PARENT_TESTS+PROVIDER_CLOSURE_TESTS+HAL_PROVIDER_TESTS+COMPOSER_ENTRY_TESTS+COMPOSER_AUDIOCONTROL_TESTS)");
edit("original 26 registrations, nine provider controls or five Composer entry controls absent/duplicated","original registrations, nine provider, five Composer entry or three Audiocontrol controls absent/duplicated");
edit("len(listed_names)==213","len(listed_names)==216");
edit("enumerate(TESTS[:-len(COMPOSER_ENTRY_TESTS)])","enumerate(TESTS[:-len(COMPOSER_ENTRY_TESTS)-len(COMPOSER_AUDIOCONTROL_TESTS)])");
const loop=`        for index,name in enumerate(COMPOSER_ENTRY_TESTS,start=200):
            report['focused_result_gates'].append(focused_test(
                test_binary,name,index,len(listed_names),test_env,report['commands']))
`;
edit(loop,loop+`        for index,name in enumerate(COMPOSER_AUDIOCONTROL_TESTS,start=205):
            report['focused_result_gates'].append(focused_test(
                test_binary,name,index,len(listed_names),test_env,report['commands']))
`);
edit("        report['composer_entry_tests_passed']=len(COMPOSER_ENTRY_TESTS)","        report['composer_entry_tests_passed']=len(COMPOSER_ENTRY_TESTS)\n        report['composer_audiocontrol_projection_tests_passed']=len(COMPOSER_AUDIOCONTROL_TESTS)\n        report['Automotive_audiocontrol_vendor_example_qualified']=False");
edit("len(report['commands'])==71","len(report['commands'])==74");
edit("'source_files':500,","'source_files':501,");
let back=c;for(const e of [...edits].reverse()){for(let i=0;i<e.positions.length;i++){const p=e.positions[i];need(back.slice(p,p+e.after.length)===e.after,"inverse exact offset");back=back.slice(0,p)+e.before+back.slice(p+e.after.length);}}need(back===input.compiler,"complete compiler inverse");
function funcs(text){const markers=[...text.matchAll(/^def (\w+)\(/gm)];return Object.fromEntries(markers.map((m,i)=>[m[1],text.slice(m.index,markers[i+1]?.index??text.length)]));}
const oldF=funcs(input.compiler),newF=funcs(c),changed=Object.keys(oldF).filter(k=>oldF[k]!==newF[k]);
need(changed.every(k=>k==="execute"||k==="finish_resources"),"only execute and constants following finish_resources");
const unchanged=Object.keys(oldF).filter(k=>oldF[k]===newF[k]);
return{compiler:c,compiler_pin:pin(c),edits,unchanged,changed,proof,proofRaw,proofPin:pin(proofRaw),scope,scopeRaw,scopePin:pin(scopeRaw),root:"/home/alex/work/pocket4-native-builder474-composer-audiocontrol-projection-compile-01-20261106"};
}
