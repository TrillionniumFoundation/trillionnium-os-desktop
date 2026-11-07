function(H,input) {
 const require=(v,m)=>{if(!v)throw new Error(m)};
 const pin=s=>{const b=H.utf8(s);return{bytes:b.length,sha256:H.sha256(b),git_blob_sha1:H.gitBlob(b)}};
 const small=p=>({bytes:p.bytes,sha256:p.sha256});
 const recovered=Function("return ("+input.source_deriver+")")()(H,input.baseline_android,input.baseline_manifest,input.consumer);
 require(recovered.android===input.android&&recovered.manifest===input.manifest&&recovered.production_diff===input.source_patch,"durable source exact reproduction");
 const prior=JSON.parse(input.checkpoint_proof), source=recovered;
 const proof={
 schema:1,state:"SOURCE_ONLY_FIXED_AUDIOCONTROL_EXAMPLE_PROJECTION_NOT_COMPILED",
 baseline:{builder_revision:471,android:pin(input.baseline_android),manifest:pin(input.baseline_manifest),compile_result:pin(input.actual471),compile_source_tree:"d37d18acdaa7fb236ef6683dd33cadeca044ffdd",source_checkpoint_tree:"9e2ae3c424af394e598067ce5ea0fbc4a64d34b9"},
 candidate:{manifest:source.manifest_pin,android:source.pins.android,source_delta:Object.keys(source.delta).sort(),source_files:501,unchanged:499,changed_existing:["tools/droidloom-update/src/android.rs"],added:["android/native-role-ingress/provider-fixtures/audiocontrol-example.Android.bp"]},
 scope:{source_path:"hardware/interfaces/automotive/audiocontrol/aidl/default/Android.bp",original:source.pins.fixture,projected:source.projected_pin,excluded_modules:["android.hardware.automotive.audiocontrol-service.example"],excluded_module_types:["cc_binary"],observed_defaults:prior.consumer.defaults,targets:["framework-minus-apex","libandroid_runtime"],dependency_mode:"Strict",ALLOW_MISSING_DEPENDENCIES:"false",no_find_ignore_added:true,only_original_typed_branch:true,original_package_license_metadata_retained:true,parent_AIDL_providers_unchanged:true,sibling_implementation_unchanged:true,SystemUI471_projection_retained:true,original_projection_journal_restore_unchanged:true},
 source_lock:{path:"android/manifest/m2-role-ingress-hal-provider-source-lock.json",bytes:96957,sha256:"72848909e4931d712a3d59f344904ae8642b32c35a01cf520a51afce4c56b50d",projects:225,links:8,unchanged:true,writer:"UNKNOWN"},
 consumer_provenance:prior.consumer,actual_failure:prior.actual_failure,
 validation:{full_inverse_to_actual471:true,new_focused_tests:source.test_names,existing_updater_focused:21,existing_source_resume_focused:9,new_updater_focused:3,expected_updater_registered:214,expected_source_registered:20,expected_commands:71,host_compile_performed:false,Rust_controls_executed:false,normal_Soong_run:false,complete_generated_variant_graph_proved:false},
 adjacent_automotive_audit:{status:"PENDING_FIXED_LEAF_AUDIT",not_inferred_from_audiocontrol_single_leaf:true},
 limitations:{static_scope_reasoning_only:true,no_current_installed_Main_version_claim:true,normal08_failure_preserved:true,Java_or_Android_JNI_artifacts_qualified:false,production_ready:false},
 cache_recovery:prior.cache_recovery};
 const proofRaw=JSON.stringify(proof,null,2)+"\n",proofPin=pin(proofRaw);
 const baseline=input.baseline_compiler;
 require(pin(baseline).sha256==="5b4e7d699b6ca82c9a60ff28cd49cf7d101fd6b92608fe70a92380182f3aac4f","compiler471 pin");
 let text=baseline;const edits=[];
 function one(oldValue,newValue,label){require(text.split(oldValue).length===2,"once "+label);const offset=text.indexOf(oldValue);edits.push({label,offset,old:oldValue,new:newValue});text=text.slice(0,offset)+newValue+text.slice(offset+oldValue.length);}
 function all(oldValue,newValue,label){const count=text.split(oldValue).length-1;require(count>0,label);for(let i=0;i<count;i++){const offset=text.indexOf(oldValue);require(offset>=0,label);edits.push({label:label+" "+i,offset,old:oldValue,new:newValue});text=text.slice(0,offset)+newValue+text.slice(offset+oldValue.length);}}
 const parentRoot="/home/alex/work/pocket4-native-typed-ingress-builder471-systemui-test-projection-compile-01-20261106";
 const root="/home/alex/work/pocket4-native-typed-ingress-builder473-audiocontrol-example-projection-compile-01-20261106";
 one('"""Compile builder471 fixed SystemUI test projection with 21 updater and 9 source controls; no platform execution."""',
     '"""Compile builder473 fixed Audiocontrol example projection with 24 updater and 9 source controls; no platform execution."""',"doc scope");
 one("BASE_SOURCE = Path('/home/alex/work/pocket4-native-typed-ingress-builder470-published-lock-alignment-compile-01-20261106/builder-source')","BASE_SOURCE = Path('"+parentRoot+"/builder-source')","actual parent source");
 one("ROOT = Path('"+parentRoot+"')","ROOT = Path('"+root+"')","fresh root");
 one("MANIFEST_PARENT = 'd87ab919c015a8739011a83add768db28c7f7296a7be9683a0516b28808c1057'","MANIFEST_PARENT = '"+pin(input.baseline_manifest).sha256+"'","actual parent map");
 all("MANIFEST_471","MANIFEST_473","candidate manifest symbol");
 one("MANIFEST_473 = 'c29c7b05fcfdf3def918d2bc963c6fe0c25a0430c87249f3de781d5d8bf68ae0'","MANIFEST_473 = '"+source.manifest_pin.sha256+"'","new 501 map");
 one("TESTS = ORIGINAL_TESTS + TYPED_INGRESS_TESTS + PROVIDER_CLOSURE_TESTS + HAL_PROVIDER_TESTS + SYSTEMUI_PROJECTION_TESTS",
   "AUDIOCONTROL_PROJECTION_TESTS = "+JSON.stringify(source.test_names)+"\n"+
   "PROJECTION_TAIL_TESTS = SYSTEMUI_PROJECTION_TESTS + AUDIOCONTROL_PROJECTION_TESTS\n"+
   "TESTS = ORIGINAL_TESTS + TYPED_INGRESS_TESTS + PROVIDER_CLOSURE_TESTS + HAL_PROVIDER_TESTS + PROJECTION_TAIL_TESTS","three focused tests");
 one('FIXED_PROVIDER_DELTA = ["android/native-role-ingress/provider-fixtures/SystemUI-tests.Android.bp","tools/droidloom-update/src/android.rs"]','FIXED_PROVIDER_DELTA = '+JSON.stringify(Object.keys(source.delta).sort()),"exact source delta");
 one("SYSTEMUI_PROJECTION_PROOF_SHA = '17fe54cebd452ef14258461f0817b9cbc753ccb0619f28e7274e61879a89d762'","AUDIOCONTROL_PROJECTION_PROOF_SHA = '"+proofPin.sha256+"'","new proof pin");
 one("fresh builder471 fixed five-module SystemUI test projection compile01, 500 source files, 18 original plus 3 new updater controls and 9 unchanged source-resume controls; no real published source/staging/Soong/Java/Android/service execution",
     "fresh builder473 fixed one-module Audiocontrol example projection compile01, 501 source files, 21 prior plus 3 new updater controls and 9 unchanged source-resume controls; no real published source/staging/Soong/Java/Android/service execution","report scope");
 one("'compiled-parent470-manifest.json'","'compiled-parent471-manifest.json'","parent manifest filename");
 one("'expected-builder471-manifest.json'","'expected-builder473-manifest.json'","candidate manifest filename");
 one("require(len(expected)==499 and len(copied_expected)==500,'source manifest count changed')","require(len(expected)==500 and len(copied_expected)==501,'source manifest count changed')","map counts");
 const begin=text.indexOf("        parent_raw,parent_pin=pinned_packet('compiled-parent470-result.json',");
 const end=text.indexOf("        roots_raw,roots_pin=pinned_packet(",begin);require(begin>=0&&end>begin,"parent block");
 one(text.slice(begin,end),String.raw`        parent_raw,parent_pin=pinned_packet('compiled-parent471-result.json',
            '466d01e56fa6579636be8e82eedbc4276c31ce3e6b390dc985fe3bc454ead1e9')
        parent=json.loads(parent_raw)
        require(parent_pin['bytes']==181273 and parent['state']=='PASS' and
                parent['focused_tests_passed']==30 and parent['updater_focused_tests_passed']==21 and
                parent['source_resume_tests_passed']==9 and parent['provider_closure_tests_passed']==6 and
                parent['hal_provider_tests_passed']==3 and parent['systemui_test_projection_tests_passed']==3 and
                parent['actual_registered_test_count']==211 and parent['source_actual_registered_test_count']==20 and
                len(parent['commands'])==68 and all(row['returncode']==0 and not row['timed_out'] for row in parent['commands']) and
                parent['copied_manifest']['bytes']==99548 and parent['copied_manifest']['sha256']==MANIFEST_PARENT and
                parent['builder_elf']['bytes']==34770528 and
                parent['builder_elf']['sha256']=='2ea23bbeee47e8404fc6d9b91a5b3c3fdc4e7afd70820fd8b388f1dd6ead19be' and
                parent['owned_resource_gate']['pass'] is True and not parent['dependency_changes'] and
                not parent['tool_changes'] and not parent['cleanup']['errors'] and not parent['cleanup']['remaining'] and
                not parent['cleanup']['forced_cleanup'] and parent['copied_source_unchanged_after'] is True and
                parent['original_source_unchanged_after'] is True and parent['cargo_configs_unchanged_after'] is True and
                parent['source_delta']['actual_source_file_count']==500 and
                parent['source_delta']['current_hal_source_lock_unchanged'] is True and
                parent['source_lock_writer']=='UNKNOWN' and
                parent['unchanged_225_project_lock_authority']['bytes']==96957 and
                parent['unchanged_225_project_lock_authority']['sha256']=='72848909e4931d712a3d59f344904ae8642b32c35a01cf520a51afce4c56b50d' and
                parent['systemui_test_original_fixture_authority']['bytes']==3392 and
                parent['systemui_test_original_fixture_authority']['sha256']=='f1b2422c693a8f8c52034369ded585a3a93ac861f9dd6dd73f0801a77e6be4da' and
                parent['SystemUI_application_and_test_modules_qualified'] is False and
                parent['framework_Java_and_Android_JNI_compiled'] is False and
                parent['runtime_authorization_enabled'] is False,
                'actual compiled parent471 qualification differs')
        report['actual_parent471_compile_authority']=parent_pin
`,"actual parent471 full qualification");
 const pb=text.indexOf("        projection_raw,projection_pin=pinned_packet('systemui-test-projection-proof.json'"),pe=text.indexOf("        lock_name=",pb);
 require(pb>=0&&pe>pb,"projection block");
 one(text.slice(pb,pe),String.raw`        projection_raw,projection_pin=pinned_packet('audiocontrol-example-projection-proof.json',AUDIOCONTROL_PROJECTION_PROOF_SHA)
        projection=json.loads(projection_raw)
        require(projection['state']=='SOURCE_ONLY_FIXED_AUDIOCONTROL_EXAMPLE_PROJECTION_NOT_COMPILED' and
                projection['baseline']['manifest']['sha256']==MANIFEST_PARENT and
                projection['baseline']['compile_result']['sha256']==parent_pin['sha256'] and
                projection['candidate']['manifest']['sha256']==MANIFEST_473 and
                projection['candidate']['source_delta']==FIXED_PROVIDER_DELTA and
                projection['candidate']['source_files']==501 and projection['candidate']['unchanged']==499 and
                projection['candidate']['changed_existing']==['tools/droidloom-update/src/android.rs'] and
                projection['candidate']['added']==['android/native-role-ingress/provider-fixtures/audiocontrol-example.Android.bp'] and
                projection['scope']['source_path']=='hardware/interfaces/automotive/audiocontrol/aidl/default/Android.bp' and
                projection['scope']['excluded_modules']==['android.hardware.automotive.audiocontrol-service.example'] and
                projection['scope']['excluded_module_types']==['cc_binary'] and
                projection['scope']['targets']==['framework-minus-apex','libandroid_runtime'] and
                projection['scope']['dependency_mode']=='Strict' and
                projection['scope']['ALLOW_MISSING_DEPENDENCIES']=='false' and
                projection['scope']['no_find_ignore_added'] is True and
                projection['scope']['SystemUI471_projection_retained'] is True and
                projection['validation']['new_focused_tests']==AUDIOCONTROL_PROJECTION_TESTS and
                projection['validation']['host_compile_performed'] is False,
                'fixed one-module Audiocontrol example projection proof does not bind this candidate')
`,"exact new proof qualification");
 one("fixture_name='android/native-role-ingress/provider-fixtures/SystemUI-tests.Android.bp'","fixture_name='android/native-role-ingress/provider-fixtures/audiocontrol-example.Android.bp'","actual new fixture");
 const fb=text.indexOf("        fixture_raw,fixture_pin=pinned_packet('delta/'+fixture_name,"),fe=text.indexOf("        report['unchanged_225_project_lock_authority']",fb);
 require(fb>=0&&fe>fb,"fixtureblock");
 one(text.slice(fb,fe),String.raw`        fixture_raw,fixture_pin=pinned_packet('delta/'+fixture_name,
            '9c8a0aecfa46ce0f1874362fa9dfff6a34326f9bf569b6fe7206dd6db1b3c9a6')
        require(fixture_pin['bytes']==copied_expected[fixture_name]['bytes']==1869 and
                fixture_pin['sha256']==copied_expected[fixture_name]['sha256']==
                    projection['scope']['original']['sha256'],
                'complete observed Audiocontrol example fixture differs')
        report['audiocontrol_example_projection_authority']=projection_pin
        report['audiocontrol_example_original_fixture_authority']=fixture_pin
        report['systemui_test_projection_retained_from_parent471']=True
`,"actual fixture authority");
 one("'SystemUI projection delta is not exactly one Rust replacement and one original fixture addition'","'Audiocontrol example delta is not exactly one Rust replacement and one original fixture addition'","delta diagnostic");
 one("'actual copied 500-file builder471 manifest differs'","'actual copied 501-file builder473 manifest differs'","map diagnostic");
 one("'unchanged_existing':498,'actual_source_file_count':500","'unchanged_existing':499,'actual_source_file_count':501","source delta counts");
 one("'builder_revision_name':'471-fixed-systemui-test-projection'","'builder_revision_name':'473-fixed-audiocontrol-example-projection'","revision diagnostic");
 one("'current_hal_source_lock_unchanged':True,'fixed_SystemUI_tests_BP_original_fixture_added':True,",
     "'current_hal_source_lock_unchanged':True,'fixed_Audiocontrol_example_BP_original_fixture_added':True,\n                                'SystemUI471_projection_and_fixture_unchanged':True,","scope report fields");
 one("                len(SYSTEMUI_PROJECTION_TESTS)==3 and len(TESTS)==len(set(TESTS))==21 and\n",
     "                len(SYSTEMUI_PROJECTION_TESTS)==3 and len(AUDIOCONTROL_PROJECTION_TESTS)==3 and\n                len(PROJECTION_TAIL_TESTS)==6 and len(TESTS)==len(set(TESTS))==24 and\n","test count gates");
 one("                    PARENT_TESTS+PROVIDER_CLOSURE_TESTS+HAL_PROVIDER_TESTS+SYSTEMUI_PROJECTION_TESTS),",
     "                    PARENT_TESTS+PROVIDER_CLOSURE_TESTS+HAL_PROVIDER_TESTS+PROJECTION_TAIL_TESTS),","all exact registrations");
 one("'original 26 registrations, nine provider controls or three SystemUI projection controls absent/duplicated'",
     "'original 26 registrations, nine provider controls or six exact projection controls absent/duplicated'","registration diagnostic");
 one("require(len(listed_names)==211 and len(listed_names)==len(set(listed_names)) and",
     "require(len(listed_names)==214 and len(listed_names)==len(set(listed_names)) and","registered count");
 one("for index,name in enumerate(TESTS[:-len(SYSTEMUI_PROJECTION_TESTS)]):",
     "for index,name in enumerate(TESTS[:-len(PROJECTION_TAIL_TESTS)]):","keep original 0 through17 labels");
 one("for index,name in enumerate(SYSTEMUI_PROJECTION_TESTS,start=200):",
     "for index,name in enumerate(PROJECTION_TAIL_TESTS,start=200):","keep200through202 and add203through205");
 one("        report['systemui_test_projection_tests_passed']=len(SYSTEMUI_PROJECTION_TESTS)\n",
     "        report['systemui_test_projection_tests_passed']=len(SYSTEMUI_PROJECTION_TESTS)\n"+
     "        report['audiocontrol_example_projection_tests_passed']=len(AUDIOCONTROL_PROJECTION_TESTS)\n"+
     "        report['Automotive_audiocontrol_vendor_example_qualified']=False\n","focused result fields");
 one("report['parent_targeted_tests_passed_historically']=27","report['parent_targeted_tests_passed_historically']=30","parent history");
 one("require(len(report['commands'])==68 and all(row['returncode']==0 and not row['timed_out'] for row in report['commands']),",
     "require(len(report['commands'])==71 and all(row['returncode']==0 and not row['timed_out'] for row in report['commands']),","commands");
 one("'source_files':500,","'source_files':501,","plan only count");
 let inverse=text;
 for(const e of [...edits].reverse()){require(inverse.slice(e.offset,e.offset+e.new.length)===e.new,"inverse "+e.label);inverse=inverse.slice(0,e.offset)+e.old+inverse.slice(e.offset+e.new.length);}
 require(inverse===baseline,"complete compiler inverse");
 const functions=s=>{const lines=s.split("\n"),out={};for(let i=0;i<lines.length;i++){const m=/^def ([A-Za-z0-9_]+)\(/.exec(lines[i]);if(!m)continue;let j=i+1;while(j<lines.length&&(!lines[j].trim()||/^\s/.test(lines[j])))j++;out[m[1]]=lines.slice(i,j).join("\n").trimEnd()+"\n";}return out;};
 const bf=functions(baseline),nf=functions(text),unchanged=Object.keys(bf).filter(n=>bf[n]===nf[n]),changed=Object.keys(bf).filter(n=>bf[n]!==nf[n]);
 require(unchanged.length===34&&JSON.stringify(changed)===JSON.stringify(["execute"]),"helper unchanged");
 return{root,parent_root:parentRoot,compiler:text,compiler_edits:edits,compiler_pin:pin(text),compiler_inverse:true,unchanged_functions:unchanged,changed_functions:changed,proof,proof_raw:proofRaw,proof_pin:proofPin,source};
}
