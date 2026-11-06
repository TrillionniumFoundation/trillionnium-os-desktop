from pathlib import Path
import hashlib,json,re,difflib,shutil
r=Path('/workspace/scratch/265e5bca485a/pocket4_eight_apps/framework_provider_repair/normal06')
base=r/'candidate/tools/droidloom-update/src/android.rs';old=base.read_text();assert hashlib.sha256(old.encode()).hexdigest()=='9357aa8c0e0ab511278dcb24df57e5cb29f1570811019c501703fa387229c9e3'
root=(r/'reference/SystemUI.Android.bp').read_text();wm=(r/'reference/upstream-go/WindowManager-Shell.Android.bp').read_text()
closure=json.loads((r/'systemui-all-loaded-source-closure-r2.json').read_text());needed=closure['root_modules_required_by_this_static_recursive_union_not_in_two_defaults_candidate']
pairs=[('soong_config_module_type','systemui_optimized_java_defaults'),('systemui_optimized_java_defaults','SystemUI_optimized_defaults'),('java_defaults','systemui-non-platform-apis-defaults'),('java_defaults','SystemUI_compile_dagger')]+[(x['module_type'],x['name']) for x in needed]+[('filegroup','sysui_proguard_common_and_kotlin')]
assert len(pairs)==19 and len(set(pairs))==19
wm_pairs=[]
for m in re.finditer(r'(?m)^([a-z_]+) \{\n    name: "([^"]+)",',wm):wm_pairs.append((m.group(1),m.group(2)))
assert len(wm_pairs)==9,len(wm_pairs)
def project(s,ps):
 meta=[];take=False
 for l in s.splitlines():
  if l.startswith('package {') or l.startswith('license {'):take=True
  if take:
   meta.append(l+'\n')
   if l=='}':take=False
 out=''.join(meta)
 for typ,name in ps:
  marker=f'{typ} {{\n    name: "{name}",';assert s.count(marker)==1,(typ,name);i=s.index(marker);j=s.index('\n}\n',i)+3;out+='\n'+s[i:j]
 return out
projected=project(root,pairs);wm_projected=project(wm,wm_pairs);sha=lambda s:hashlib.sha256(s.encode()).hexdigest()
start=old.index('        "frameworks/base/packages/SystemUI/Android.bp" => ');end=old.index('        "platform_testing/libraries/motion/Android.bp" => ',start)
def tuple_body(path,s,ps):
 lines=[f'        "{path}" => ({len(s.encode())},',f'            "{sha(s)}",']
 lines.append('            &['+','.join(f'("{k}", "{n}")' if i==0 else f'\n              ("{k}", "{n}")' for i,(k,n) in enumerate(ps))+']),')
 return '\n'.join(lines)+'\n'
new=old[:start]+tuple_body('frameworks/base/packages/SystemUI/Android.bp',root,pairs)+tuple_body('frameworks/base/libs/WindowManager/Shell/Android.bp',wm,wm_pairs)+old[end:]
assert new.count('025d58f766940a96ab6557b523456162201f393c9277abde86ad5030b52448cc')==1
new=new.replace('025d58f766940a96ab6557b523456162201f393c9277abde86ad5030b52448cc',sha(projected))
fixture_marker='    const SHARED_PROVIDER_FIXTURES: &[(&str, &str, &str)] = &[\n'
insert=f'        ("frameworks/base/libs/WindowManager/Shell/Android.bp",\n         include_str!("../../../android/native-role-ingress/provider-fixtures/WindowManager-Shell.Android.bp"),\n         "{sha(wm_projected)}"),\n'
# Preserve SystemUI at index zero, used by the existing defaults regression.
next_marker='        ("platform_testing/libraries/motion/Android.bp",\n         include_str!'
assert new.count(next_marker)==1;new=new.replace(next_marker,insert+next_marker)
old_assert='            assert!(!projected.contains("name: \\\"SystemUI-core\\\""));'
assert old_assert in new
new=new.replace(old_assert,'            if *relative == "frameworks/base/packages/SystemUI/Android.bp" {\n                assert!(projected.contains("name: \\\"SystemUI-core\\\""));\n            } else {\n                assert!(!projected.contains("name: \\\"SystemUI-core\\\""));\n            }')
newtest='''    #[test]
    fn typed_systemui_projection_preserves_loaded_ordinary_dependencies() {
        let original = SHARED_PROVIDER_FIXTURES[0].1;
        let projected = typed_ingress_shared_blueprint(
            "frameworks/base/packages/SystemUI/Android.bp", original).unwrap();
        let consumer = include_str!("../../../android/native-role-ingress/provider-fixtures/SystemUI-tests.Android.bp");
        // Already discovered child modules refer to these real root providers.
        // Match full upstream stanzas, retaining every transitive dependency;
        // this checks projection fidelity, not whole-graph build qualification.
        for (kind, name) in [
            ("android_library", "SystemUI-tests"),
            ("android_library", "SystemUI-application"),
            ("java_library", "kosmos"),
        ] {
            assert!(consumer.contains(&format!("\\\"{name}\\\"")));
            let marker = format!("{kind} {{\\n    name: \\\"{name}\\\",");
            let start = original.find(&marker).unwrap();
            let end = start + original[start..].find("\\n}\\n").unwrap() + 3;
            assert_eq!(projected.matches(&original[start..end]).count(), 1);
        }
        assert!(projected.contains("name: \\\"SystemUI-res\\\""));
        assert!(projected.contains("\\\"dagger2-compiler\\\""));
        assert!(projected.contains("\\\"WindowManager-Shell\\\""));
    }

'''
marker='    #[test]\n    fn typed_shared_provider_projection_rejects_changed_missing_or_duplicate_stanzas() {';assert new.count(marker)==1;new=new.replace(marker,newtest+marker)
out=r/'candidate-r2';p=out/'tools/droidloom-update/src/android.rs';p.parent.mkdir(parents=True,exist_ok=True);assert not p.exists();p.write_text(new)
fixtures=out/'android/native-role-ingress/provider-fixtures';fixtures.mkdir(parents=True,exist_ok=True)
for original in (r/'candidate/android/native-role-ingress/provider-fixtures').glob('*.bp'):shutil.copyfile(original,fixtures/original.name)
(fixtures/'WindowManager-Shell.Android.bp').write_text(wm)
(r/'reference/SystemUI.candidate-r2-projection.bp').write_text(projected);(r/'reference/WindowManager-Shell.candidate-r2-projection.bp').write_text(wm_projected)
diff=''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='candidate/tools/droidloom-update/src/android.rs',tofile='candidate-r2/tools/droidloom-update/src/android.rs'))
(r/'candidate-r2-from-r1.patch').write_text(diff)
manifest={'schema':'pocket4-normal06-source-candidate-r2-in-progress','state':'SOURCE_ONLY_EXTERNAL_CLOSURE_NOT_SEALED','parent_source_sha256':sha(old),'candidate_source_bytes':len(new.encode()),'candidate_source_sha256':sha(new),'systemui_full_root_modules':pairs,'systemui_projection_bytes':len(projected.encode()),'systemui_projection_sha256':sha(projected),'window_manager_full_root_modules':wm_pairs,'window_manager_projection_bytes':len(wm_projected.encode()),'window_manager_projection_sha256':sha(wm_projected),'basis':'Exact normal05 loaded 68 SystemUI and 24 WindowManager Blueprint paths; restore genuine complete providers, preserve all loaded child consumers. External source lock amendments still under analysis.','source_lock_parent_sha256':'72848909e4931d712a3d59f344904ae8642b32c35a01cf520a51afce4c56b50d','source_lock_sealed':False,'rust_compile_executed':False,'rust_tests_executed':False,'soong_executed':False,'all_transitive_source_dependencies_qualified':False,'allow_missing_dependencies':False,'existing_consumers_or_tests_deleted':False,'targets':['framework-minus-apex','libandroid_runtime'],'memory_max_bytes':10*1024**3,'swap_max_bytes':0,'fresh_mem_available_min_bytes':15*1024**3,'build_submitted':False,'runtime_actions':False,'production_ready':False,'cleanup_eligible':False}
b=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode();(out/'SOURCE_CANDIDATE.json').write_bytes(b)
print(json.dumps({'source_bytes':len(new.encode()),'source_sha256':sha(new),'patch_bytes':len(diff.encode()),'patch_sha256':sha(diff),'manifest_bytes':len(b),'manifest_sha256':hashlib.sha256(b).hexdigest(),'systemui_projection':[len(projected.encode()),sha(projected)],'wm_projection':[len(wm_projected.encode()),sha(wm_projected)]}))
