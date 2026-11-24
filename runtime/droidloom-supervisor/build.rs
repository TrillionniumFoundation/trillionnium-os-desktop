use std::{env, ffi::OsString, path::PathBuf, process::Command};

fn selected_tool(name: &str, default: &str) -> OsString {
    let target = env::var("TARGET").expect("cargo target");
    let host = env::var("HOST").expect("cargo build host");
    for key in [
        format!("{name}_{target}"),
        format!("{name}_{}", target.replace('-', "_")),
        format!("TARGET_{name}"),
        name.to_owned(),
    ] {
        println!("cargo:rerun-if-env-changed={key}");
        if let Some(value) = env::var_os(key) {
            return value;
        }
    }
    if host == target {
        default.into()
    } else {
        format!("{target}-{default}").into()
    }
}
fn execute(command: &mut Command) {
    let status = command.status().expect("launch the board C toolchain");
    assert!(status.success(), "board toolchain failed with {status}");
}
fn main() {
    let out = PathBuf::from(env::var_os("OUT_DIR").expect("Cargo build output"));
    let cc = selected_tool("CC", "cc");
    let ar = selected_tool("AR", "ar");
    let mut archive = Command::new(ar);
    archive.arg("rcs").arg(out.join("libdroidloom_board.a"));
    for stem in [
        "board_resources",
        "board_retirement",
        "board_assembly",
        "firststage",
        "custody",
        "selected",
        "device_source",
        "device_template",
        "instance_context",
        "instance_query",
    ] {
        let source = format!("../droidloom-early-boot/{stem}.c");
        let object = out.join(format!("{stem}.o"));
        println!("cargo:rerun-if-changed={source}");
        execute(
            Command::new(&cc)
                .args([
                    "-std=c11",
                    "-O2",
                    "-fPIC",
                    "-Wall",
                    "-Wextra",
                    "-Werror",
                    "-DDROIDLOOM_INSTANCE_LIBRARY",
                    "-c",
                ])
                .arg(source)
                .arg("-o")
                .arg(&object),
        );
        archive.arg(object);
    }
    execute(&mut archive);
    for header in [
        "board.h",
        "custody.h",
        "device_source.h",
        "device_template.h",
    ] {
        println!("cargo:rerun-if-changed=../droidloom-early-boot/{header}");
    }
    println!("cargo:rerun-if-changed=../droidloom-early-boot/instance_query.h");
    println!("cargo:rerun-if-changed=../droidloom-early-boot/board_cgroup.h");
    println!("cargo:rerun-if-changed=../droidloom-early-boot/board_resources.h");
    println!("cargo:rerun-if-changed=../droidloom-early-boot/board_binder.h");
    println!("cargo:rustc-link-search=native={}", out.display());
    println!("cargo:rustc-link-lib=static=droidloom_board");
    println!("cargo:rustc-link-lib=crypto");
}
