function (H, baseline, manifestRaw, observed) {
  const assert=(x,m)=>{if(!x)throw new Error(m)};
  const pin=raw=>{const b=H.utf8(raw);return{bytes:b.length,sha256:H.sha256(b),git_blob_sha1:H.gitBlob(b)}};
  assert(pin(baseline).sha256==="7bbe16d118fe610ae42e9c1b906b65aee5ceeb0804cdbaee93ee61ab5b271629","baseline471");
  assert(pin(observed).bytes===1869&&pin(observed).sha256==="9c8a0aecfa46ce0f1874362fa9dfff6a34326f9bf569b6fe7206dd6db1b3c9a6","actual consumer");
  const projected=observed.slice(observed.indexOf("package {"),observed.indexOf("\n}\n",observed.indexOf("package {"))+3);
  assert(pin(projected).bytes===346&&pin(projected).sha256==="d73b00f17a80375d2d59e408088c5e875c3311bd0f7487b117d4b8d28f7cff93","metadata exact");
  let android=baseline;
  const edits=[];
  function replace(oldText,newText,label){assert(android.split(oldText).length===2,label+" old once");assert(baseline.split(oldText).length===2,label+" original once");edits.push({label,old:oldText,new:newText});android=android.replace(oldText,newText);}
  const branch='        "platform_testing/libraries/motion/Android.bp" => (2098,\n';
  replace(branch,
    '        "hardware/interfaces/automotive/audiocontrol/aidl/default/Android.bp" => (1869,\n'+
    '            "9c8a0aecfa46ce0f1874362fa9dfff6a34326f9bf569b6fe7206dd6db1b3c9a6",\n'+
    '            &[]),\n'+branch,"fixed complete consumer before projection");
  const helper=String.raw`const TYPED_INGRESS_AUDIOCONTROL_EXAMPLE_BLUEPRINT: &str =
    "hardware/interfaces/automotive/audiocontrol/aidl/default/Android.bp";

fn project_typed_ingress_audiocontrol_example(p: &mut Projection, source: &Path) -> Result<()> {
    // This route requests framework-minus-apex and libandroid_runtime only.
    // The single observed vendor example binary is outside that fixed scope.
    // Preserve its package/license metadata and journal its entire preimage;
    // keep parent AIDL providers, sibling sources, and the source lock intact.
    // This fixed leaf does not assert a complete generated Soong variant graph.
    let path = source.join(TYPED_INGRESS_AUDIOCONTROL_EXAMPLE_BLUEPRINT);
    let original = fs::read_to_string(&path)?;
    p.put(&path, typed_ingress_shared_blueprint(
        TYPED_INGRESS_AUDIOCONTROL_EXAMPLE_BLUEPRINT, &original)?)
}

`;
  const helperAnchor="fn project_blueprints(p: &mut Projection, source: &Path, typed_ingress: bool) -> Result<()> {\n";
  replace(helperAnchor,helper+helperAnchor,"typed-only fixed leaf helper");
  const call='        project_typed_ingress_systemui_tests(p, source)?;\n';
  replace(call,call+'        project_typed_ingress_audiocontrol_example(p, source)?;\n',"only existing typed branch");
  const table='        ("platform_testing/libraries/motion/Android.bp",\n';
  replace(table,
    '        (TYPED_INGRESS_AUDIOCONTROL_EXAMPLE_BLUEPRINT,\n'+
    '         include_str!("../../../android/native-role-ingress/provider-fixtures/audiocontrol-example.Android.bp"),\n'+
    '         "d73b00f17a80375d2d59e408088c5e875c3311bd0f7487b117d4b8d28f7cff93"),\n'+table,"actual complete fixture table");
  replace("        assert_eq!(SHARED_PROVIDER_FIXTURES.len(), 30);\n","        assert_eq!(SHARED_PROVIDER_FIXTURES.len(), 31);\n","fixture inventory only");
  const expectedLines=projected.split("\n").slice(0,-1).map(l=>"            "+JSON.stringify(l+"\n")+",").join("\n");
  const tests=String.raw`    #[test]
    fn typed_audiocontrol_example_projection_keeps_metadata_and_sibling_sources() {
        let original = include_str!(
            "../../../android/native-role-ingress/provider-fixtures/audiocontrol-example.Android.bp");
        assert_eq!(original.matches("cc_binary {").count(), 1);
        assert_eq!(original.matches("    name: \"").count(), 1);
        assert_eq!(original.matches(
            "    name: \"android.hardware.automotive.audiocontrol-service.example\",").count(), 1);
        for name in [
            "latest_android_hardware_audio_common_ndk_shared",
            "latest_android_hardware_automotive_audiocontrol_ndk_shared",
            "powerpolicyclient_defaults",
            "car.audio.configuration.xsd.default",
            "car.fade.configuration.xsd.default",
        ] {
            assert_eq!(original.matches(&format!("        \"{name}\",")).count(), 1);
        }
        let expected = concat!(
__EXPECTED__
        );
        let fixture = tempfile::tempdir().unwrap();
        let source = fixture.path().join("aosp-source");
        let path = source.join(TYPED_INGRESS_AUDIOCONTROL_EXAMPLE_BLUEPRINT);
        let parent = source.join("hardware/interfaces/automotive/audiocontrol/aidl/Android.bp");
        let sibling = source.join("hardware/interfaces/automotive/audiocontrol/aidl/default/AudioControl.cpp");
        let manifest = source.join(".droidloom-source-manifest.json");
        let journal = fixture.path().join("projection.json");
        // Explicit sentinels test write scope, not the content of real providers.
        let sentinels = [
            (&parent, "unchanged parent AIDL provider sentinel\n"),
            (&sibling, "unchanged sibling implementation sentinel\n"),
            (&manifest, "unchanged source manifest sentinel\n"),
        ];
        write(&path, original).unwrap();
        for (p, value) in sentinels { write(p, value).unwrap(); }
        {
            let mut projection = Projection::new(journal.clone()).unwrap();
            project_typed_ingress_audiocontrol_example(&mut projection, &source).unwrap();
            assert_eq!(fs::read(&path).unwrap(), expected.as_bytes());
            for (p, value) in sentinels {
                assert_eq!(fs::read(p).unwrap(), value.as_bytes());
            }
            let originals: Vec<Original> =
                serde_json::from_slice(&fs::read(&journal).unwrap()).unwrap();
            assert_eq!(originals.len(), 1);
            assert_eq!(originals[0].path, path);
            assert_eq!(originals[0].bytes.as_deref(), Some(original.as_bytes()));
        }
        assert!(!journal.exists());
        assert_eq!(fs::read(&path).unwrap(), original.as_bytes());
        for (p, value) in sentinels { assert_eq!(fs::read(p).unwrap(), value.as_bytes()); }
    }

    #[test]
    fn typed_audiocontrol_example_projection_rejects_source_drift_before_write() {
        let original = include_str!(
            "../../../android/native-role-ingress/provider-fixtures/audiocontrol-example.Android.bp");
        for changed in [
            original.replacen("powerpolicyclient_defaults", "powerpolicyclient_changed", 1),
            original.replacen("car.fade.configuration.xsd.default", "car.fade.configuration.xsd.changed", 1),
            format!("{original}\n"),
        ] {
            assert_ne!(changed.as_bytes(), original.as_bytes());
            let fixture = tempfile::tempdir().unwrap();
            let source = fixture.path().join("aosp-source");
            let path = source.join(TYPED_INGRESS_AUDIOCONTROL_EXAMPLE_BLUEPRINT);
            let journal = fixture.path().join("projection.json");
            write(&path, &changed).unwrap();
            {
                let mut projection = Projection::new(journal.clone()).unwrap();
                let error = project_typed_ingress_audiocontrol_example(&mut projection, &source)
                    .unwrap_err().to_string();
                assert!(error.contains("typed ingress shared provider source changed"));
                assert!(error.contains(TYPED_INGRESS_AUDIOCONTROL_EXAMPLE_BLUEPRINT));
                assert!(projection.originals.is_empty());
                assert!(!journal.exists());
                assert_eq!(fs::read(&path).unwrap(), changed.as_bytes());
            }
            assert!(!journal.exists());
            assert_eq!(fs::read(&path).unwrap(), changed.as_bytes());
        }
    }

    #[test]
    fn typed_audiocontrol_example_projection_recovers_full_observed_original() {
        let original = include_str!(
            "../../../android/native-role-ingress/provider-fixtures/audiocontrol-example.Android.bp");
        let fixture = tempfile::tempdir().unwrap();
        let source = fixture.path().join("aosp-source");
        let path = source.join(TYPED_INGRESS_AUDIOCONTROL_EXAMPLE_BLUEPRINT);
        let journal = fixture.path().join("projection.json");
        write(&path, original).unwrap();
        let mut projection = Projection::new(journal.clone()).unwrap();
        project_typed_ingress_audiocontrol_example(&mut projection, &source).unwrap();
        assert_ne!(fs::read(&path).unwrap(), original.as_bytes());
        let originals: Vec<Original> =
            serde_json::from_slice(&fs::read(&journal).unwrap()).unwrap();
        assert_eq!(originals.len(), 1);
        assert_eq!(originals[0].path, path);
        assert_eq!(originals[0].bytes.as_deref(), Some(original.as_bytes()));
        std::mem::forget(projection);
        assert!(Projection::new(journal.clone()).is_err());
        recover(&journal, &source).unwrap();
        assert_eq!(fs::read(&path).unwrap(), original.as_bytes());
        assert!(!journal.exists());
    }

`.replace("__EXPECTED__",expectedLines);
  const testAnchor="    #[test]\n    fn native_engine_mode_rejects_widening_before_command_mutation() {\n";
  replace(testAnchor,tests+testAnchor,"three production projection regression tests");
  let inverse=android;
  for(const e of [...edits].reverse()){assert(inverse.split(e.new).length===2,"inverse "+e.label);inverse=inverse.replace(e.new,e.old);}
  assert(inverse===baseline,"complete inverse");
  const path="tools/droidloom-update/src/android.rs";
  let patch="--- a/"+path+"\n+++ b/"+path+"\n",shift=0;
  for(const e of [...edits].sort((x,y)=>baseline.indexOf(x.old)-baseline.indexOf(y.old))) {
    const offset=baseline.indexOf(e.old);
    assert(offset===0||baseline[offset-1]==="\n","line start");
    assert(e.old.endsWith("\n")&&e.new.endsWith("\n"),"line end");
    const line=baseline.slice(0,offset).split("\n").length;
    const oldLines=e.old.slice(0,-1).split("\n"),newLines=e.new.slice(0,-1).split("\n");
    patch+="@@ -"+line+","+oldLines.length+" +"+(line+shift)+","+newLines.length+" @@\n";
    patch+=oldLines.map(l=>"-"+l+"\n").join("")+newLines.map(l=>"+"+l+"\n").join("");
    shift+=newLines.length-oldLines.length;
  }
  const fp="android/native-role-ingress/provider-fixtures/audiocontrol-example.Android.bp";
  const fLines=observed.slice(0,-1).split("\n");
  patch+="--- /dev/null\n+++ b/"+fp+"\n@@ -0,0 +1,"+fLines.length+" @@\n"+fLines.map(l=>"+"+l+"\n").join("");
  const originalMap=JSON.parse(manifestRaw), map={...originalMap};
  assert(Object.keys(map).length===500&&map[path].sha256===pin(baseline).sha256,"parent map");
  map[path]={...map[path],bytes:pin(android).bytes,sha256:pin(android).sha256};
  assert(!(fp in map),"new fixture absent");
  map[fp]={bytes:pin(observed).bytes,kind:"file",mode:420,sha256:pin(observed).sha256};
  const sorted=Object.fromEntries(Object.keys(map).sort().map(k=>[k,map[k]]));
  const stable=v=>Array.isArray(v)?v.map(stable):v&&typeof v==="object"?Object.fromEntries(Object.keys(v).sort().map(k=>[k,stable(v[k])])):v;
  const manifest=JSON.stringify(stable(sorted),null,2)+"\n";
  assert(Object.keys(sorted).filter(k=>k in originalMap&&JSON.stringify(sorted[k])===JSON.stringify(originalMap[k])).length===499,"499 unchanged");
  return {state:"SOURCE_ONLY_RECOVERED_AFTER_CACHE_LOSS_NOT_COMPILED",base:baseline,android,edits,production_diff:patch,
    delta:{[path]:android,[fp]:observed},pins:{android:pin(android),fixture:pin(observed),patch:pin(patch)},projected,
    projected_pin:pin(projected),manifest,map:sorted,manifest_pin:pin(manifest),inverse_pass:true,
    test_names:["android::tests::typed_audiocontrol_example_projection_keeps_metadata_and_sibling_sources","android::tests::typed_audiocontrol_example_projection_rejects_source_drift_before_write","android::tests::typed_audiocontrol_example_projection_recovers_full_observed_original"],
    prior_memory_only_candidate_sha256:"be455b38d004af00b44b9232bee48167eb7c74762a3402def67d1e5faf2f983b",prior_memory_only_not_durable:true};
}
