use super::*;

fn command(command: &mut Command) -> std::process::Output {
    let result = command.output().unwrap();
    assert!(result.status.success(), "{command:?}: {}", String::from_utf8_lossy(&result.stderr));
    result
}

fn debug(image: &Path, operation: &str, writable: bool) -> Vec<u8> {
    let tool = reader_tool("debugfs").unwrap();
    let mut cmd = Command::new(&tool.path);
    if writable {
        cmd.arg("-w");
    }
    let result = command(cmd.args(["-R", operation]).arg(image).env("LC_ALL", "C"));
    assert!(String::from_utf8_lossy(&result.stderr).lines().all(|line| line.starts_with("debugfs ")),
        "{operation}: {}", String::from_utf8_lossy(&result.stderr));
    result.stdout
}

fn attributes(image: &Path, name: &str, mode: &str, gid: u32, label: &str, work: &Path) {
    for (field, value) in [("mode", mode.to_owned()), ("uid", "0".into()), ("gid", gid.to_string())] {
        debug(image, &format!("set_inode_field {name} {field} {value}"), true);
    }
    let value = work.join("attribute");
    fs::write(&value, format!("{label}\0")).unwrap();
    debug(image, &format!("ea_set -f {} {name} security.selinux", value.display()), true);
}

fn original_file(image: &Path, name: &str, body: &[u8], mode: &str, gid: u32, label: &str, work: &Path) {
    let value = work.join("original-body");
    fs::write(&value, body).unwrap();
    debug(image, &format!("write {} {name}", value.display()), true);
    attributes(image, name, mode, gid, label, work);
}

fn synthetic_system(work: &Path) -> PathBuf {
    let image = work.join("synthetic-system.img");
    File::create(&image).unwrap().set_len(16 * 1024 * 1024).unwrap();
    let mke2fs = reader_tool("mke2fs").unwrap();
    command(Command::new(&mke2fs.path).args(["-q", "-F", "-t", "ext4", "-b", "4096"]).arg(&image));
    for name in ["/system", "/system/etc", "/system/system_ext", "/system/system_ext/bin",
        "/system/system_ext/etc", "/system/system_ext/etc/init", "/system/system_ext/etc/selinux",
        "/system/system_ext/framework", "/system/system_ext/framework/oat",
        "/system/system_ext/framework/oat/x86_64"] {
        debug(&image, &format!("mkdir {name}"), true);
        attributes(&image, name, "040755", 0, "u:object_r:system_file:s0", work);
    }
    original_file(&image, "/system/etc/mke2fs.conf", &fs::read("/etc/mke2fs.conf").unwrap(),
        "0100644", 0, "u:object_r:system_file:s0", work);
    original_file(&image, "/system/system_ext/bin/hwservicemanager", b"factory-service",
        "0100755", 2000, "u:object_r:hwservicemanager_exec:s0", work);
    original_file(&image, "/system/system_ext/etc/init/wificond.rc", b"# factory init\n",
        "0100644", 0, "u:object_r:system_file:s0", work);
    original_file(&image, "/system/system_ext/framework/factory.jar", b"factory-framework",
        "0100644", 0, "u:object_r:system_file:s0", work);
    original_file(&image, "/system/system_ext/framework/oat/x86_64/factory.odex", b"factory-oat",
        "0100644", 0, "u:object_r:system_file:s0", work);
    // Public bytes from the already pinned CP3A property file. No host identity or state.
    let contexts = b"#line 50 \"system/sepolicy/flagging/flagging_macros\"\n\n#line 1 \"out/soong/.intermediates/system/sepolicy/contexts/system_ext_property_contexts/android_common/generic_x86_64/newline\"\n\n";
    assert_eq!(hex::encode(Sha256::digest(contexts)), contract::FACTORY_PROPERTY_CONTEXTS_SHA256);
    original_file(&image, "/system/system_ext/etc/selinux/system_ext_property_contexts", contexts,
        "0100644", 0, "u:object_r:property_contexts_file:s0", work);
    image
}

fn jar(path: &Path, dex: bool) {
    // This is deliberately synthetic archive data, never Android execution evidence.
    let python = reader_tool("python3").unwrap();
    command(Command::new(&python.path).args(["-I", "-c",
        "import sys,zipfile\nwith zipfile.ZipFile(sys.argv[1], 'x', compression=zipfile.ZIP_STORED) as z:\n z.writestr('classes.dex' if sys.argv[2]=='dex' else 'README', b'dex\\n039\\x00synthetic-carrier-test')\n"])
        .arg(path).arg(if dex { "dex" } else { "stripped" }));
}

fn frontend(install: &Path) -> InstalledFrontend {
    for name in ["bin", "etc/init", "framework"] {
        fs::create_dir_all(install.join(name)).unwrap();
    }
    fs::write(install.join("bin/droidloom-input-bridge"), INPUT_WRAPPER).unwrap();
    fs::write(install.join("etc/init/droidloom-input-bridge.rc"), INPUT_RC).unwrap();
    fs::copy("/usr/bin/true", install.join("bin/droidloom-task-launcher")).unwrap();
    jar(&install.join("framework/droidloom-input-bridge.jar"), true);
    jar(&install.join("framework/droidloom-camera-producer.jar"), true);
    fs::write(install.join("etc/init/droidloom-camera-producer.rc"), CAMERA_RC).unwrap();
    fs::write(install.join("etc/init/droidloom-virtual-camera.rc"), CAMERA_PROVIDER_RC).unwrap();
    let product = install.parent().unwrap();
    fs::create_dir_all(product.join("system/bin")).unwrap();
    fs::copy("/usr/bin/true", product.join("system/bin/virtual_camera")).unwrap();
    InstalledFrontend::read(install, product).unwrap()
}

fn builder(work: &Path, config: &Value) -> std::process::Output {
    let input = work.join("builder-config.json");
    fs::write(&input, serde_json::to_vec(config).unwrap()).unwrap();
    let python = reader_tool("python3").unwrap();
    Command::new(&python.path).args(["-I", "-c", BUILDER]).arg(input).current_dir(work).output().unwrap()
}

#[test]
fn normal_frontend_requires_exact_sources_and_eight_bounded_pins() {
    let temp = tempfile::tempdir().unwrap();
    let install = temp.path().join("system_ext");
    let selected = frontend(&install);
    assert!(selected.digests().unwrap().valid());
    assert_eq!(selected.paths().len(), 8);
    for role in ["input_bridge_wrapper", "input_bridge_jar", "input_bridge_init_rc", "task_launcher"] {
        let mut missing = serde_json::to_value(&selected).unwrap();
        missing.as_object_mut().unwrap().remove(role);
        assert!(serde_json::from_value::<InstalledFrontend>(missing).is_err());
        let mut empty = serde_json::to_value(&selected).unwrap();
        empty[role]["bytes"] = json!(0);
        assert!(serde_json::from_value::<InstalledFrontend>(empty).unwrap().digests().is_err());
        let mut wrong_hash = serde_json::to_value(&selected).unwrap();
        wrong_hash[role]["sha256"] = json!("z".repeat(64));
        assert!(serde_json::from_value::<InstalledFrontend>(wrong_hash).unwrap().digests().is_err());
    }
    for role in ["jar", "init_rc", "provider", "provider_init_rc"] {
        let mut missing = serde_json::to_value(&selected).unwrap();
        missing["camera"].as_object_mut().unwrap().remove(role);
        assert!(serde_json::from_value::<InstalledFrontend>(missing).is_err());
        let mut empty = serde_json::to_value(&selected).unwrap();
        empty["camera"][role]["bytes"] = json!(0);
        assert!(serde_json::from_value::<InstalledFrontend>(empty).unwrap().digests().is_err());
    }
    fs::write(install.join("etc/init/droidloom-input-bridge.rc"), b"# different source\n").unwrap();
    assert!(InstalledFrontend::read(&install, temp.path()).is_err());
    assert!(selected.recheck().is_err());
}

#[test]
fn real_ext4_three_tree_roundtrip_rejects_lost_modified_or_mislabelled_members() {
    let temp = tempfile::tempdir().unwrap();
    let work = temp.path();
    let system_path = synthetic_system(work);
    let system = pin(&system_path, MAX_IMAGE).unwrap();
    let installed = frontend(&work.join("installed-system_ext"));
    let observer = work.join("observer");
    fs::copy("/usr/bin/true", &observer).unwrap();
    let observer = pin(&observer, 8 * 1024 * 1024).unwrap();
    let rc = work.join("readiness.rc");
    fs::write(&rc, RC).unwrap();
    let rc = pin(&rc, 4096).unwrap();
    let expected = receipt_parents(&system.sha256, &observer.sha256, &rc.sha256,
        &installed.digests().unwrap()).unwrap();
    let image = work.join("complete-carrier.img");
    let config = json!({"system":system.path,"elf":observer.path,"rc":rc.path,
        "output":image,"frontend":installed.paths(),"sha256":expected,
        "tools":{"debugfs":reader_tool("debugfs").unwrap().path,
            "e2fsck":reader_tool("e2fsck").unwrap().path,
            "mke2fs":reader_tool("mke2fs").unwrap().path}});
    let result = builder(work, &config);
    assert!(result.status.success(), "{}", String::from_utf8_lossy(&result.stderr));
    let record: Value = serde_json::from_slice(&result.stdout).unwrap();
    assert_eq!(record["mount_subtrees"], json!(["bin", "etc/init", "framework"]));
    assert_eq!(record["parents"], expected);
    for (path, bytes) in [("framework/factory.jar", b"factory-framework".as_slice()),
        ("framework/oat/x86_64/factory.odex", b"factory-oat".as_slice())] {
        assert_eq!(record["members"][path]["sha256"], hex::encode(Sha256::digest(bytes)));
    }
    for path in ["bin/droidloom-input-bridge", "bin/droidloom-task-launcher",
        "framework/droidloom-input-bridge.jar", "etc/init/droidloom-input-bridge.rc",
        "framework/droidloom-camera-producer.jar", "etc/init/droidloom-camera-producer.rc",
        "bin/droidloom-virtual-camera", "etc/init/droidloom-virtual-camera.rc"] {
        assert_eq!(record["members"][path]["uid"], 0);
        assert_eq!(record["members"][path]["gid"], 0);
    }
    let verify = |path: &Path, expected: &Value| builder(work, &json!({
        "system":system.path,"existing_image":path,"sha256":expected,
        "tools":{"debugfs":reader_tool("debugfs").unwrap().path,
            "e2fsck":reader_tool("e2fsck").unwrap().path}}));
    assert!(verify(&image, &expected).status.success());
    // Historical R10 remains readable with its exact old member inventory.
    // Removing the declaration cannot hide camera files in a current image.
    let mut historical = config.clone();
    historical["sha256"]["frontend"].as_object_mut().unwrap().remove("camera");
    for role in ["camera_jar", "camera_init_rc", "camera_provider", "camera_provider_init_rc"] {
        historical["frontend"].as_object_mut().unwrap().remove(role);
    }
    historical["output"] = json!(work.join("historical-carrier.img"));
    let older = builder(work, &historical);
    assert!(older.status.success(), "{}", String::from_utf8_lossy(&older.stderr));
    assert!(verify(&work.join("historical-carrier.img"), &historical["sha256"]).status.success());
    assert!(!verify(&image, &historical["sha256"]).status.success());
    assert!(!verify(&work.join("historical-carrier.img"), &expected).status.success());

    for scenario in ["missing-jar", "changed-factory", "wrong-label", "wrong-owner", "extra-framework", "missing-camera", "camera-label", "provider-owner"] {
        let altered = work.join(format!("{scenario}.img"));
        fs::copy(&image, &altered).unwrap();
        match scenario {
            "missing-jar" => { debug(&altered, "rm /framework/droidloom-input-bridge.jar", true); }
            "changed-factory" => {
                debug(&altered, "rm /framework/oat/x86_64/factory.odex", true);
                original_file(&altered, "/framework/oat/x86_64/factory.odex", b"changed-oat",
                    "0100644", 0, "u:object_r:system_file:s0", work);
            }
            "wrong-label" => attributes(&altered, "/framework/droidloom-input-bridge.jar", "0100644", 0,
                "u:object_r:vendor_file:s0", work),
            "wrong-owner" => { debug(&altered, "set_inode_field /bin/droidloom-task-launcher uid 1", true); }
            "extra-framework" => original_file(&altered, "/framework/unselected.jar", b"unselected",
                "0100644", 0, "u:object_r:system_file:s0", work),
            "missing-camera" => { debug(&altered, "rm /framework/droidloom-camera-producer.jar", true); }
            "camera-label" => attributes(&altered, "/framework/droidloom-camera-producer.jar",
                "0100644", 0, "u:object_r:system_file:s0", work),
            "provider-owner" => { debug(&altered, "set_inode_field /bin/droidloom-virtual-camera uid 1000", true); }
            _ => unreachable!(),
        }
        assert!(!verify(&altered, &expected).status.success(), "accepted {scenario}");
    }
    let mut wrong = expected.clone();
    wrong["frontend"]["input_bridge_jar_sha256"] = json!("f".repeat(64));
    assert!(!verify(&image, &wrong).status.success());
    let stripped = work.join("stripped.jar");
    jar(&stripped, false);
    let stripped = pin(&stripped, 8 * 1024 * 1024).unwrap();
    let mut no_dex = config.clone();
    no_dex["output"] = json!(work.join("must-not-publish.img"));
    no_dex["frontend"]["input_bridge_jar"] = json!(stripped.path);
    no_dex["sha256"]["frontend"]["input_bridge_jar_sha256"] = json!(stripped.sha256);
    assert!(!builder(work, &no_dex).status.success());
    assert!(!work.join("must-not-publish.img").exists());
    recheck(&system, MAX_IMAGE).unwrap();
    installed.recheck().unwrap();
}
