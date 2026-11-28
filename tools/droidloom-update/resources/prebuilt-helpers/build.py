#!/usr/bin/env python3
"""Normal fixed-source helper producer. No Android, Main, install or UI action.

The release producer owns its finite resource envelope and all source/tool FDs.
This module executes the original eleven compiler/signature commands per helper.
Its products are immutable package material; they grant no runtime authority.
"""
import hashlib, io, json, os, re, secrets, struct, sys, time, types, zipfile
from pathlib import Path

KINDS = ("saf", "features", "ihg")
DOC_COMMANDS = ("aapt-package", "javac", "d8", "align", "create-owned-key", "sign",
                "signature", "alignment", "badging", "permissions", "manifest")
IHG_COMMANDS = ("javac", "d8", "aapt-package", "align", "create-owned-signing-key", "sign",
                "signature", "alignment", "badging", "permissions", "manifest")
LIMITS = {"saf": 240, "features": 240, "ihg": 230}
MAX_APK = 2 * 1024 * 1024

def need(value, reason):
    if not value:
        raise ValueError(reason)

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode()

def pin(raw):
    return {"bytes": len(raw), "sha256": sha(raw)}

def regular(path, maximum=MAX_APK):
    p = Path(path)
    fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(fd)
        need(before.st_nlink == 1 and 0 < before.st_size <= maximum, "BOUNDED_SINGLE_REGULAR_OUTPUT")
        need((before.st_mode & 0o170000) == 0o100000, "REGULAR_OUTPUT")
        raw = b""
        while len(raw) <= maximum:
            part = os.read(fd, min(65536, maximum + 1 - len(raw)))
            if not part:
                break
            raw += part
        need(len(raw) == before.st_size and metadata(before) == metadata(os.fstat(fd))
             == metadata(p.lstat()), "OUTPUT_BOOKENDS")
        return raw, {"path": str(p), **pin(raw)}
    finally:
        os.close(fd)

def metadata(s):
    return (s.st_dev, s.st_ino, s.st_mode, s.st_uid, s.st_gid, s.st_nlink,
            s.st_size, s.st_mtime_ns, s.st_ctime_ns)

def new_file(path, raw, mode=0o600):
    p = Path(path)
    p.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, mode)
    try:
        view = memoryview(raw)
        while view:
            count = os.write(fd, view)
            need(count > 0, "OUTPUT_SHORT_WRITE")
            view = view[count:]
        os.fsync(fd)
    finally:
        os.close(fd)
    need(regular(p, max(1, len(raw)))[0] == raw, "OUTPUT_FULL_READBACK")
    return {"path": str(p), **pin(raw)}

def module(read, relative):
    raw = read(relative)
    name = "_normal_prebuilt_" + relative.replace("/", "_").replace(".", "_")
    result = types.ModuleType(name)
    result.__file__ = relative
    sys.modules[name] = result
    exec(compile(raw, relative, "exec"), result.__dict__)
    return result

def one_lp(raw, at, width=4):
    need(at >= 0 and at + width <= len(raw), "SIGNING_BLOCK_LENGTH_FIELD")
    size = int.from_bytes(raw[at:at+width], "little")
    start = at + width
    need(size > 0 and size <= len(raw) - start, "SIGNING_BLOCK_LENGTH_BOUND")
    return raw[start:start+size], start+size

def public_certificate(apk):
    """Extract exactly one v3 DER certificate after normal apksigner verified it."""
    need(22 <= len(apk) <= MAX_APK, "APK_BOUND")
    pos = apk.rfind(b"PK\x05\x06", max(0, len(apk) - 65557))
    need(pos >= 0 and pos + 22 <= len(apk), "CLASSIC_ZIP_EOCD")
    eocd = apk[pos:]
    need(len(eocd) == 22 + int.from_bytes(eocd[20:22], "little"), "EXACT_ZIP_EOCD")
    disk, central_disk, entries_disk, entries = struct.unpack_from("<HHHH", eocd, 4)
    size, offset = struct.unpack_from("<II", eocd, 12)
    need(disk == central_disk == 0 and entries_disk == entries and entries < 65535
         and offset + size == pos and offset >= 32, "SINGLE_CLASSIC_ZIP_DIRECTORY")
    footer = apk[offset-24:offset]
    need(footer[8:] == b"APK Sig Block 42", "APK_SIGNING_BLOCK_MAGIC")
    block_size = int.from_bytes(footer[:8], "little")
    start = offset - block_size - 8
    need(block_size >= 24 and start >= 0
         and int.from_bytes(apk[start:start+8], "little") == block_size, "APK_SIGNING_BLOCK_BOOKENDS")
    pairs = apk[start+8:offset-24]
    at = 0
    v3 = []
    identifiers = set()
    while at < len(pairs):
        entry, at = one_lp(pairs, at, 8)
        need(len(entry) >= 4, "APK_SIGNING_PAIR_ID")
        identity = int.from_bytes(entry[:4], "little")
        need(identity not in identifiers, "DUPLICATE_APK_SIGNING_PAIR")
        identifiers.add(identity)
        if identity == 0xf05368c0:
            v3.append(entry[4:])
    need(at == len(pairs) and len(v3) == 1, "ONE_V3_SIGNING_BLOCK")
    signers, end = one_lp(v3[0], 0)
    need(end == len(v3[0]), "EXACT_V3_SIGNERS")
    signer, end = one_lp(signers, 0)
    need(end == len(signers), "ONE_V3_SIGNER")
    signed, _ = one_lp(signer, 0)
    _, at = one_lp(signed, 0)
    certificates, _ = one_lp(signed, at)
    cert, end = one_lp(certificates, 0)
    need(end == len(certificates) and 128 <= len(cert) <= 16384 and cert[0] == 0x30,
         "ONE_DER_PUBLIC_CERTIFICATE")
    return cert

def rendered_documents(read, kind):
    names_module = module(read, kind + "/documents_names.py")
    renderer = module(read, kind + "/documents_helper_source.py")
    origins = {name: read(kind + "/template_" + name) for name in renderer.TEMPLATES}
    commitment = encoded({name: pin(value) for name, value in sorted(origins.items())})
    run = sha(b"droidloom-normal-prebuilt-documents-v2\0" + kind.encode() + b"\0" + commitment)[:16]
    prefix = "business-documents-saf-case-" if kind == "saf" else "business-documents-case-"
    namespace = Path("/var/lib/droidloom/qualification/pocket4") / (prefix + sha(commitment)[:32])
    constructor = names_module.SAFNames if kind == "saf" else names_module.FeaturesNames
    names = constructor(run, namespace)
    files, source = renderer.render(names, origins)
    build = module(read, kind + "/documents_build.py")
    need(tuple(build.COMMAND_NAMES) == DOC_COMMANDS, "ORIGINAL_DOCUMENTS_COMMAND_ROSTER")
    return names, files, source, build

def docs(read, root, kind, tools, run_command, guard, whole_end):
    root.mkdir(mode=0o700)
    names, files, source, build = rendered_documents(read, kind)
    for name in ("source", "generated", "classes", "dex", "private-signing"):
        (root / name).mkdir(mode=0o700)
    for name, raw in sorted(files.items()):
        new_file(root / "source" / name, raw)
    tools = {name: {"resolved_path": value} for name, value in tools.items()}
    commands = build.command_plan(root, names, tools)
    need(len(commands) == 11, "ELEVEN_DOCUMENTS_COMMANDS")
    end = min(whole_end, time.monotonic() + LIMITS[kind])
    records = []
    def execute(index):
        guard()
        need(index == len(records) and time.monotonic() < end, "ORIGINAL_COMMAND_ORDER_DEADLINE")
        record, stdout, stderr = run_command(kind, DOC_COMMANDS[index], commands[index], min(end, time.monotonic()+90))
        records.append(record)
        need(record["returncode"] == 0 and record["host_retirement_proved"] is True
             and record["timed_out"] is False, "NORMAL_DOCUMENTS_COMMAND_FAILED:" + DOC_COMMANDS[index])
        return stdout
    execute(0)
    need(sorted((root / "generated").rglob("R.java")) ==
         [root / "generated" / names.PACKAGE.replace(".", "/") / "R.java"], "ONE_ORIGINAL_GENERATED_R")
    execute(1)
    classes = sorted((root / "classes").rglob("*.class"))
    need(classes == build.class_paths(root, names.PACKAGE), "ORIGINAL_COMPILED_CLASS_ROSTER")
    execute(2)
    need(sorted(p.name for p in (root / "dex").iterdir()) == ["classes.dex"], "ONE_DEX")
    dex = regular(root / "dex/classes.dex", 1048576)[0]
    with zipfile.ZipFile(root / "unsigned.apk", "a", compression=zipfile.ZIP_DEFLATED) as archive:
        need("classes.dex" not in archive.namelist(), "NO_PREEXISTING_DEX")
        archive.writestr("classes.dex", dex)
    execute(3)
    new_file(root / "private-signing/password.txt", (secrets.token_hex(32)+"\n").encode())
    execute(4)
    execute(5)
    outputs = {DOC_COMMANDS[index]: execute(index) for index in range(6, 11)}
    common = types.SimpleNamespace(need=need, regular=regular)
    cert_digest = build.validate_artifact_outputs(common, names, root, outputs)
    apk_name = "owned-saf.apk" if kind == "saf" else "owned-features.apk"
    apk = regular(root / apk_name, 1048576)[0]
    cert = public_certificate(apk)
    need(sha(cert) == cert_digest, "PUBLIC_CERTIFICATE_MATCHES_ACTUAL_VERIFIER")
    for name, raw in files.items():
        need(regular(root / "source" / name)[0] == raw, "RENDERED_SOURCE_CHANGED")
    guard()
    need(time.monotonic() < end, "ORIGINAL_DOCUMENTS_240_SECOND_BOUND")
    contract = {"kind": kind, "package": names.PACKAGE, "run_id": names.RUN, "version_code": 1,
                "compile_sdk": 31, "min_sdk": 31, "target_sdk": 33,
                "permissions": [], "launcher": False, "test_only": True, "debuggable": False,
                "activity": names.CLIENT_ACTIVITY}
    return publish(root, kind, apk, cert, files, contract, source, records, end)

def ihg(read, root, tools, run_command, guard, whole_end):
    root.mkdir(mode=0o700)
    factory = module(read, "ihg/ihg_helper_factory.py")
    original = {name: read("ihg/" + name) for name in factory.ORIGINALS}
    files = factory.render_prebuilt(original)
    original_build = module(read, "ihg/ihg_helper_build.py")
    need(tuple(original_build.BUILD_COMMANDS) == IHG_COMMANDS, "ORIGINAL_IHG_COMMAND_ROSTER")
    common = types.SimpleNamespace(need=need)
    contract = original_build.manifest_contract(common, files["AndroidManifest.xml"])
    for name in ("source", "classes", "dex", "res", "private-signing"):
        (root / name).mkdir(mode=0o700)
    for name, raw in files.items():
        new_file(root / "source" / name, raw)
    end = min(whole_end, time.monotonic() + LIMITS["ihg"])
    records = []
    java = [tools["java"], "-XX:ActiveProcessorCount=1", "-XX:+UseSerialGC", "-Xmx256m"]
    signer = java + ["-jar", tools["apksigner_jar"]]
    def execute(name, argv):
        guard()
        need(name == IHG_COMMANDS[len(records)] and time.monotonic() < end, "ORIGINAL_IHG_COMMAND_ORDER")
        record, stdout, stderr = run_command("ihg", name, argv, min(end, time.monotonic()+60))
        records.append(record)
        need(record["returncode"] == 0 and record["host_retirement_proved"] is True
             and record["timed_out"] is False, "NORMAL_IHG_COMMAND_FAILED:" + name)
        return stdout
    execute("javac", [tools["javac"], "-J-XX:ActiveProcessorCount=1", "-J-XX:+UseSerialGC", "-J-Xmx256m",
        "-proc:none", "-Xmaxerrs", "20", "-Xmaxwarns", "20", "-source", "8", "-target", "8",
        "-bootclasspath", tools["android_jar"], "-d", str(root/"classes"), str(root/"source/ActionRunner.java")])
    classes = sorted((root/"classes").rglob("*.class"))
    need(1 <= len(classes) <= 32 and all(p.is_file() and p.stat().st_size <= 262144 for p in classes),
         "ORIGINAL_IHG_CLASS_BOUND")
    execute("d8", java + ["-cp", tools["r8"], "com.android.tools.r8.D8", "--lib", tools["android_jar"],
        "--min-api", "31", "--output", str(root/"dex"), *[str(p) for p in classes]])
    need(sorted(p.name for p in (root/"dex").iterdir()) == ["classes.dex"], "ONE_IHG_DEX")
    dex = regular(root/"dex/classes.dex", 1048576)[0]
    execute("aapt-package", [tools["aapt"], "package", "-f", "-M", str(root/"source/AndroidManifest.xml"),
        "-S", str(root/"res"), "-I", tools["android_jar"], "-F", str(root/"unsigned.apk")])
    with zipfile.ZipFile(root/"unsigned.apk", "a", compression=zipfile.ZIP_DEFLATED) as archive:
        need("classes.dex" not in archive.namelist(), "NO_PREEXISTING_IHG_DEX")
        archive.writestr("classes.dex", dex)
    execute("align", [tools["zipalign"], "-f", "4", str(root/"unsigned.apk"), str(root/"aligned.apk")])
    password = root/"private-signing/password.txt"
    key = root/"private-signing/owned.p12"
    new_file(password, (secrets.token_hex(32)+"\n").encode())
    execute("create-owned-signing-key", java + ["-m", "java.base/sun.security.tools.keytool.Main", "-genkeypair", "-noprompt",
        "-storetype", "PKCS12", "-keystore", str(key), "-storepass:file", str(password), "-alias", "owned-ihg-final-main",
        "-keyalg", "RSA", "-keysize", "3072", "-validity", "3650", "-dname", "CN=Pocket4 Owned IHG Final Main,O=Owned Test,C=US"])
    apk_path = root/"owned-ihg-qa.apk"
    execute("sign", signer + ["sign", "--ks", str(key), "--ks-pass", "file:"+str(password), "--ks-key-alias",
        "owned-ihg-final-main", "--min-sdk-version", "31", "--v1-signing-enabled", "false",
        "--v2-signing-enabled", "true", "--v3-signing-enabled", "true", "--out", str(apk_path), str(root/"aligned.apk")])
    signature = execute("signature", signer + ["verify", "--verbose", "--print-certs", "--min-sdk-version", "31", str(apk_path)])
    certificates = re.findall(rb"^Signer #1 certificate SHA-256 digest: ([0-9a-f]{64})\r?$", signature, re.M)
    need(len(certificates) == 1 and b"Number of signers: 1" in signature
         and b"Verified using v3 scheme (APK Signature Scheme v3): true" in signature, "ONE_NORMAL_V3_IHG_SIGNER")
    execute("alignment", [tools["zipalign"], "-c", "4", str(apk_path)])
    badging = execute("badging", [tools["aapt"], "dump", "badging", str(apk_path)])
    permissions = execute("permissions", [tools["aapt"], "dump", "permissions", str(apk_path)])
    xml = execute("manifest", [tools["aapt"], "dump", "xmltree", str(apk_path), "AndroidManifest.xml"])
    package = factory.SELF
    need(("package: name='"+package+"' versionCode='1'").encode() in badging
         and b"sdkVersion:'31'" in badging and b"targetSdkVersion:'33'" in badging, "ACTUAL_IHG_APK_IDENTITY")
    need(b"uses-permission" not in permissions and b"uses-permission" not in xml
         and b"application-debuggable" not in badging and b"launchable-activity" not in badging,
         "ORIGINAL_IHG_PRIVILEGE_CONTRACT")
    need(all(x not in xml for x in (b"E: activity ", b"E: activity-alias ", b"E: service ", b"E: receiver ", b"E: provider ")),
         "ORIGINAL_IHG_COMPONENT_SET")
    need(re.search(rb'A: android:targetPackage\([^\n]*="' + re.escape(package.encode()) + rb'"', xml) is not None
         and len(re.findall(rb"E: instrumentation(?:\s|$)", xml)) == 1
         and len(re.findall(rb'A: android:name\([^\n]*="' + re.escape(package.encode()) + rb'\.ActionRunner"', xml)) == 1,
         "ONE_SELF_INSTRUMENTATION")
    need(re.search(rb"A: android:testOnly\([^\n]*=\(type 0x12\)0xffffffff", xml) is not None
         and re.search(rb"A: android:debuggable\([^\n]*=\(type 0x12\)0x0\b", xml) is not None,
         "ORIGINAL_IHG_TEST_ONLY_NONDEBUG")
    apk = regular(apk_path)[0]
    with zipfile.ZipFile(io.BytesIO(apk)) as archive:
        names = archive.namelist()
        need(len(names) == len(set(names)) and set(names) <= {"AndroidManifest.xml", "classes.dex", "resources.arsc"}
             and archive.read("classes.dex") == dex, "ACTUAL_IHG_DEX_APK_MEMBERS")
    cert = public_certificate(apk)
    need(sha(cert) == certificates[0].decode(), "ACTUAL_IHG_PUBLIC_CERTIFICATE")
    for name, raw in files.items():
        need(regular(root/"source"/name)[0] == raw, "FIXED_IHG_SOURCE_CHANGED")
    guard()
    need(time.monotonic() < end, "ORIGINAL_IHG_230_SECOND_BOUND")
    source = {"schema": "droidloom.ihg-fixed-apk-source.v2", "package": package, "protocol": factory.PROTOCOL,
              "actual_main_embedded_in_apk": False, "runtime_binding_required": True,
              "original_templates": {name: pin(raw) for name, raw in sorted(original.items())},
              "declared_java_transformations": len(factory.JAVA_EDITS)}
    return publish(root, "ihg", apk, cert, files, {"kind": "ihg", "version_code": 1, **contract}, source, records, end)

def publish(root, kind, apk, cert, files, contract, source, records, end):
    need(len(records) == 11 and time.monotonic() < end, "EXACT_ELEVEN_COMPLETED_COMMANDS")
    public = root/"public"
    public.mkdir(mode=0o700)
    members = {"helper.apk": apk, "signer.der": cert, "SOURCE.json": encoded(source)}
    for name, raw in files.items():
        members["source/"+name] = raw
    for name, raw in sorted(members.items()):
        new_file(public/name, raw, 0o400)
    manifest = {"schema": "droidloom.prebuilt-helper-bundle.v2", "kind": kind,
                "contract": contract, "members": {name: pin(raw) for name, raw in sorted(members.items())},
                "apk": pin(apk), "certificate_sha256": sha(cert),
                "commands": [{"name": r["name"], "returncode": r["returncode"],
                              "stdout": {"bytes": r["stdout"]["bytes"], "sha256": r["stdout"]["sha256"]},
                              "stderr": {"bytes": r["stderr"]["bytes"], "sha256": r["stderr"]["sha256"]}}
                             for r in records],
                "normal_static_build_verified": True, "runtime_authority_created": False,
                "actual_main_embedded_in_apk": False, "installed": False, "Android_actions": 0,
                "whole_app_business_accepted": False, "private_signing_key_published": False}
    manifest_pin = new_file(public/"MANIFEST.json", encoded(manifest), 0o400)
    return {"kind": kind, "contract": contract, "manifest": manifest_pin, "members": manifest["members"],
            "commands": records, "static_build_verified": True, "runtime_qualified": False}

def build_all(read, output, tools, run_command, guard, original_end):
    need(os.getuid() == os.geteuid() == os.getgid() == os.getegid() == 1000, "NORMAL_UID1000_COMPILER")
    need(set(tools) == {"java", "javac", "android_jar", "r8", "aapt", "zipalign", "apksigner_jar"},
         "FIXED_NORMAL_TOOL_ROSTER")
    results = []
    for kind in KINDS:
        guard()
        need(time.monotonic() < original_end, "ORIGINAL_WHOLE_BUILD_END")
        root = Path(output)/kind
        result = ihg(read, root, tools, run_command, guard, original_end) if kind == "ihg" else docs(
            read, root, kind, tools, run_command, guard, original_end)
        results.append(result)
    guard()
    need(sum(len(x["commands"]) for x in results) == 33 and time.monotonic() < original_end,
         "EXACT_THREE_NORMAL_HELPERS_33_COMMANDS")
    return results


# A separate generation for the four owned Documents/Gallery fixtures. The
# original signed APK is a build input: its business DEX/resources/assets are
# preserved byte for byte. Only a new, source-built read-only provider DEX and
# provider manifest node are added. This is not a claim to have rebuilt the
# original Activity sources, and it never applies to a commercial application.
STATE_ORIGINS = {
    "saf": (16588, "5a7ec386816ffe0cc273c2c17cf80dd428914aa277bc4622b624b1805a0520ad",
        "42fba91c100527b8f7e5782b87987e4d57965e06ae1634e95e799982b8cab5e9", "org.droidloom.qa.saf.r12.na7f1de49e707c7a9", "a7f1de49e707c7a9"),
    "features": (20684, "8b2ff340fe56a54925c6e44d1345f995f89215188100cbc72ec2b70c2879bab5",
        "8dcbf6c012158e9fbbc620f8b332713647035b64558ca5faee5a814a547a7912", "org.droidloom.qa.documents.r12.n98116f3fbefcfc95", "98116f3fbefcfc95"),
    "rotation": (24780, "d68bbcc45df268ab97866a9477d86e69cf01aa3efb5be6666c8fa607daeb5b6a",
        "78cab56e8c667fc1a1252a161d1dbd2a51b5dacb3bf97240b15b3b7d46ec218e", "org.droidloom.qa.galleryrotation.r12.nd24b61ed8f7c9a03", "d24b61ed8f7c9a03"),
    "video": (139532, "7fc4dadcc33c94cd41d0425473622df38138d60801c2e5585c4d28cf7db68933",
        "b152def48096bab1000175a762244910f2c4aa9b5b6b080813515a1a38a0b403", "org.droidloom.qa.media.r12.nc92c3d79180955ef", "c92c3d79180955ef"),
}
STATE_DOC_SOURCES = {'saf': {'SOURCE.json': {'bytes': 2281, 'sha256': 'a6ac2ec4a91930e573bca80b712738a7db647036a9ba86b3d2f169cd55b7123a'}, 'source/AndroidManifest.xml': {'bytes': 1137, 'sha256': 'a3adcf3764edcda1fb89526ea93669637e3513342788d4d681581695b77451b9'}, 'source/SOURCE_PINS.json': {'bytes': 2281, 'sha256': 'a6ac2ec4a91930e573bca80b712738a7db647036a9ba86b3d2f169cd55b7123a'}, 'source/contract.json': {'bytes': 1105, 'sha256': '146bba638a8875dd7b3eedc0d1fbbcd28e636975afd4a65cb145927abc7ac6cf'}, 'source/res/values/ids.xml': {'bytes': 273, 'sha256': '96b43d2d226700a9d1b99a9575b6ab73f5ca245776165d1a05ef783579e9c1f7'}, 'source/src/org/droidloom/qa/saf/r12/na7f1de49e707c7a9/SafActivity.java': {'bytes': 16590, 'sha256': 'b0e977a68c02d1e2d9be5509d2e705f4068480ab85bd7409e3fe9a625f0dd7fd'}}, 'features': {'SOURCE.json': {'bytes': 2389, 'sha256': 'f6c5426f1363bd16d259a14676696e9353efd630d52b562481975e1d2a7782c8'}, 'source/AndroidManifest.xml': {'bytes': 721, 'sha256': 'bf3848131b913324665cf85ce1648b388d1ba2deda6386487703a0b7ea3a3ebf'}, 'source/SOURCE_PINS.json': {'bytes': 2389, 'sha256': 'f6c5426f1363bd16d259a14676696e9353efd630d52b562481975e1d2a7782c8'}, 'source/contract.json': {'bytes': 3302, 'sha256': '68f18ac35676090c1a05fb7709bf90de475bc4c31cf0642ac6fe92aad4343828'}, 'source/res/values/ids.xml': {'bytes': 451, 'sha256': '2cb07cba41fa376ebc3d8f72f7e9491a8dc88ae87672d75ab1fcba1f0fb82083'}, 'source/src/org/droidloom/qa/documents/r12/n98116f3fbefcfc95/FeaturesActivity.java': {'bytes': 19190, 'sha256': 'a3339fc610064e5b91a91e138cbb7707b04e4aa9fc62f5f4b7571f5ede22cfe9'}}}
STATE_CLASS = "org.droidloom.qa.state.FixedStateProvider"

def _xml_chunks(raw):
    need(len(raw) >= 8 and struct.unpack_from("<HHI", raw) == (3, 8, len(raw)), "BINARY_MANIFEST_ROOT")
    out = []; at = 8
    while at < len(raw):
        need(at + 8 <= len(raw), "MANIFEST_CHUNK_HEADER")
        kind, header, size = struct.unpack_from("<HHI", raw, at)
        need(8 <= header <= size and size % 4 == 0 and at + size <= len(raw), "MANIFEST_CHUNK_BOUND")
        out.append((kind, raw[at:at+size])); at += size
    need(at == len(raw), "MANIFEST_COMPLETE_CHUNKS")
    return out

def _xml_strings(raw):
    kind, header, size, count, styles, flags, start, style_start = struct.unpack_from("<HHIIIIII", raw)
    need(kind == 1 and header == 28 and size == len(raw) and styles == style_start == 0
         and count <= 1024 and start == 28 + count*4, "FIXED_UNSTYLED_MANIFEST_POOL")
    result = []
    def length(at, width):
        if width == 1:
            first = raw[at]; at += 1
            return (((first & 127) << 8) | raw[at], at+1) if first & 128 else (first, at)
        first = struct.unpack_from("<H", raw, at)[0]; at += 2
        return (((first & 32767) << 16) | struct.unpack_from("<H", raw, at)[0], at+2) if first & 32768 else (first, at)
    for n in range(count):
        at = start + struct.unpack_from("<I", raw, 28+4*n)[0]
        units, at = length(at, 1 if flags & 0x100 else 2)
        if flags & 0x100:
            size, at = length(at, 1); text = raw[at:at+size].decode("utf-8")
            need(raw[at+size:at+size+1] == b"\0", "MANIFEST_UTF8_TERMINATOR")
        else:
            text = raw[at:at+units*2].decode("utf-16-le")
            need(raw[at+units*2:at+units*2+2] == b"\0\0", "MANIFEST_UTF16_TERMINATOR")
        need(len(text.encode("utf-16-le"))//2 == units, "MANIFEST_STRING_LENGTH")
        result.append(text)
    return result, flags

def _xml_pool(strings, flags):
    data = bytearray(); offsets = []
    def length(n, width):
        need(0 <= n < 32768, "MANIFEST_FIXED_STRING_LENGTH")
        if width == 1: return bytes((n,)) if n < 128 else bytes((0x80 | (n >> 8), n & 255))
        return struct.pack("<H", n)
    for text in strings:
        offsets.append(len(data)); units = len(text.encode("utf-16-le"))//2
        if flags & 0x100:
            raw = text.encode(); data += length(units, 1) + length(len(raw), 1) + raw + b"\0"
        else: data += length(units, 2) + text.encode("utf-16-le") + b"\0\0"
    data += b"\0" * ((-len(data)) % 4)
    start = 28 + len(strings)*4
    return struct.pack("<HHIIIIII", 1, 28, start+len(data), len(strings), 0, flags & ~1, start, 0) + struct.pack("<"+"I"*len(offsets), *offsets) + data

def append_state_provider(original, package):
    """Append one fixed node; all original XML event chunks remain identical.

    String indices of existing events are retained. The only rewritten common
    chunks are the expanded string pool, attribute resource map and root size.
    The official aapt decoder independently compares semantics after signing.
    """
    need(package in [v[3] for v in STATE_ORIGINS.values()], "FOUR_OWNED_FIXTURE_PACKAGES_ONLY")
    chunks = _xml_chunks(original)
    need(sum(k == 1 for k, _ in chunks) == sum(k == 0x180 for k, _ in chunks) == 1,
         "ONE_MANIFEST_POOL_AND_RESOURCE_MAP")
    strings, flags = _xml_strings(next(b for k,b in chunks if k == 1))
    old_strings = list(strings)
    raw = next(b for k,b in chunks if k == 0x180)
    ids = list(struct.unpack_from("<"+"I"*((len(raw)-8)//4), raw, 8))
    need(len(ids) <= len(strings) and STATE_CLASS not in strings and "provider" not in strings,
         "ORIGINAL_HAS_NO_STATE_PROVIDER")
    def add(text, rid=0):
        matches = [i for i,s in enumerate(strings) if s == text and (rid == 0 or (i < len(ids) and ids[i] == rid))]
        if matches: return matches[0]
        i = len(strings); strings.append(text)
        if rid:
            ids.extend([0] * (i+1-len(ids))); ids[i] = rid
        return i
    ns = add("http://schemas.android.com/apk/res/android")
    name = add("provider"); classname = add(STATE_CLASS); authority = add(package+".state")
    attrs = []
    for label,rid,kind,value in [("name",0x01010003,3,classname),
        ("permission",0x01010006,3,add("android.permission.DUMP")),
        ("exported",0x01010010,0x12,0xffffffff),
        ("authorities",0x01010018,3,authority), ("grantUriPermissions",0x0101001b,0x12,0)]:
        index = add(label, rid)
        attrs.append((rid, struct.pack("<IIIHBBI", ns, index, value if kind == 3 else 0xffffffff, 8, 0, kind, value)))
    attrs.sort()
    begin = struct.pack("<HHIII", 0x102, 16, 36+20*len(attrs), 1, 0xffffffff) + struct.pack("<IIHHHHHH", 0xffffffff, name, 20, 20, len(attrs), 0, 0, 0) + b"".join(a for _,a in attrs)
    end = struct.pack("<HHIIIII", 0x103, 16, 24, 1, 0xffffffff, 0xffffffff, name)
    out = []; inserted = 0
    for k, raw in chunks:
        if k == 1: out.append(_xml_pool(strings, flags)); continue
        if k == 0x180: out.append(struct.pack("<HHI", k, 8, 8+len(ids)*4)+struct.pack("<"+"I"*len(ids), *ids)); continue
        if k == 0x103 and old_strings[struct.unpack_from("<I", raw, 20)[0]] == "application":
            out.extend([begin, end]); inserted += 1
        out.append(raw)
    need(inserted == 1, "ONE_ORIGINAL_APPLICATION_END")
    body = b"".join(out); result = struct.pack("<HHI", 3, 8, 8+len(body))+body
    revised = _xml_chunks(result)
    need([b for k,b in revised if k not in (1,0x180) and b not in (begin,end)] == [b for k,b in chunks if k not in (1,0x180)]
         and _xml_strings(next(b for k,b in revised if k == 1))[0][:len(old_strings)] == old_strings,
         "ORIGINAL_MANIFEST_EVENTS_AND_STRINGS_PRESERVED")
    return result

def state_manifest_semantics(raw, remove_provider=False):
    text = raw.decode("utf-8"); result = []; dropping = None; count = 0
    for line in text.splitlines():
        indent = len(line)-len(line.lstrip())
        if dropping is not None and line.strip() and indent <= dropping: dropping = None
        if remove_provider and re.match(r"\s*E: provider \(line=", line):
            need(dropping is None, "ONE_STATE_PROVIDER"); dropping = indent; count += 1
        if dropping is None: result.append(re.sub(r" \(line=\d+\)", "", line))
    need(count == (1 if remove_provider else 0), "EXACT_ADDED_PROVIDER_COUNT")
    return result

def build_state_helpers(read, output, tools, originals, run_command, guard, original_end):
    need(os.getuid() == os.geteuid() == os.getgid() == os.getegid() == 1000, "NORMAL_UID1000_COMPILER")
    need(set(originals) == set(STATE_ORIGINS) and set(tools) == {"java","javac","android_jar","r8","aapt2","zipalign","apksigner_jar"},
         "FIXED_STATE_BUILD_INPUT_ROSTER")
    output = Path(output); output.mkdir(mode=0o700)
    provider = read("state/FixedStateProvider.java")
    shared = output/"provider"; shared.mkdir(mode=0o700)
    new_file(shared/"FixedStateProvider.java", provider)
    for name in ("classes","dex"): (shared/name).mkdir(mode=0o700)
    records = []
    def execute(kind, name, argv, limit=90):
        guard(); need(time.monotonic() < original_end, "FIXED_STATE_BUILD_END")
        record, stdout, stderr = run_command(kind, name, argv, min(original_end,time.monotonic()+limit))
        records.append(record)
        need(record["returncode"] == 0 and record["host_retirement_proved"] is True
             and record["timed_out"] is False, "FIXED_STATE_COMMAND_FAILED:"+name)
        guard(); return stdout
    java = [tools["java"],"-XX:ActiveProcessorCount=1","-XX:+UseSerialGC","-Xmx256m"]
    signer = java+["-jar",tools["apksigner_jar"]]
    execute("provider","javac",[tools["javac"],"-J-XX:ActiveProcessorCount=1","-J-XX:+UseSerialGC","-J-Xmx256m",
        "-proc:none","-encoding","UTF-8","-source","8","-target","8","-bootclasspath",tools["android_jar"],
        "-d",str(shared/"classes"),str(shared/"FixedStateProvider.java")])
    classes = sorted((shared/"classes").rglob("*.class"))
    need([p.relative_to(shared/"classes").as_posix() for p in classes] == [STATE_CLASS.replace(".","/")+".class"], "ONE_SOURCE_STATE_CLASS")
    execute("provider","d8",java+["-cp",tools["r8"],"com.android.tools.r8.D8","--lib",tools["android_jar"],"--min-api","31",
        "--output",str(shared/"dex"),str(classes[0])])
    need(sorted(p.name for p in (shared/"dex").iterdir()) == ["classes.dex"], "ONE_STATE_DEX")
    dex = regular(shared/"dex/classes.dex",262144)[0]; results = []
    for kind,(size,digest,old_cert,package,run_id) in STATE_ORIGINS.items():
        root = output/kind; root.mkdir(mode=0o700); (root/"private-signing").mkdir(mode=0o700)
        raw = read(originals[kind]); need(pin(raw) == {"bytes":size,"sha256":digest}, "EXACT_ORIGINAL_OWNED_APK")
        original = root/"original.apk"; new_file(original, raw)
        before = execute(kind,"original-signature",signer+["verify","--verbose","--print-certs",str(original)])
        need(re.findall(rb"^V3\.0 Signer: certificate SHA-256 digest: ([0-9a-f]{64})\r?$",before,re.M)==[old_cert.encode()]
             and b"Number of signers: 1" in before and sha(public_certificate(raw))==old_cert,
             "ORIGINAL_HELPER_SIGNATURE")
        old_xml = execute(kind,"original-manifest",[tools["aapt2"],"dump","xmltree",str(original),"--file","AndroidManifest.xml"])
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            names = z.namelist(); need(len(names) == len(set(names)) and "classes.dex" in names
                and all(n in ("classes.dex","AndroidManifest.xml","resources.arsc","assets/pattern.mp4") for n in names), "ORIGINAL_HELPER_ZIP_ROSTER")
            members = {n:z.read(n) for n in names}; original_members = {n:pin(b) for n,b in members.items()}
        members["AndroidManifest.xml"] = append_state_provider(members["AndroidManifest.xml"],package)
        members["classes2.dex"] = dex
        with zipfile.ZipFile(root/"unsigned.apk","x",compression=zipfile.ZIP_DEFLATED) as z:
            for name,body in members.items(): z.writestr(name,body)
        execute(kind,"align",[tools["zipalign"],"-f","4",str(root/"unsigned.apk"),str(root/"aligned.apk")])
        password=root/"private-signing/password.txt"; key=root/"private-signing/owned.p12"
        new_file(password,(secrets.token_hex(32)+"\n").encode())
        execute(kind,"create-owned-key",java+["-m","java.base/sun.security.tools.keytool.Main","-genkeypair","-noprompt",
            "-storetype","PKCS12","-keystore",str(key),"-storepass:file",str(password),"-alias","fixed-state-fixture",
            "-keyalg","RSA","-keysize","3072","-validity","3650","-dname","CN=Droidloom Owned State Fixture,O=Owned Test,C=US"])
        apk=root/"helper.apk"
        execute(kind,"sign",signer+["sign","--ks",str(key),"--ks-pass","file:"+str(password),"--ks-key-alias","fixed-state-fixture",
            "--min-sdk-version","31","--v1-signing-enabled","false","--v2-signing-enabled","true","--v3-signing-enabled","true","--out",str(apk),str(root/"aligned.apk")])
        signed=execute(kind,"signature",signer+["verify","--verbose","--print-certs",str(apk)])
        certificate=re.findall(rb"^V3\.0 Signer: certificate SHA-256 digest: ([0-9a-f]{64})\r?$",signed,re.M)
        need(len(certificate)==1 and b"Number of signers: 1" in signed
            and b"Verified using v3 scheme (APK Signature Scheme v3): true" in signed,"ONE_ACTUAL_NEW_V3_SIGNER")
        execute(kind,"alignment",[tools["zipalign"],"-c","4",str(apk)])
        badge=execute(kind,"badging",[tools["aapt2"],"dump","badging",str(apk)])
        perms=execute(kind,"permissions",[tools["aapt2"],"dump","permissions",str(apk)])
        xml=execute(kind,"manifest",[tools["aapt2"],"dump","xmltree",str(apk),"--file","AndroidManifest.xml"])
        need(state_manifest_semantics(old_xml)==state_manifest_semantics(xml,True), "ALL_ORIGINAL_MANIFEST_SEMANTICS_PRESERVED")
        need(("package: name='"+package+"' versionCode='1'").encode() in badge
            and b"minSdkVersion:'31'" in badge and b"targetSdkVersion:'33'" in badge
            and b"uses-permission" not in perms and b"application-debuggable" not in badge
            and b"launchable-activity" not in badge, "ORIGINAL_HELPER_PRIVILEGE_CONTRACT")
        apk_raw=regular(apk)[0]; cert=public_certificate(apk_raw)
        need(sha(cert)==certificate[0].decode(),"ACTUAL_NEW_PUBLIC_CERTIFICATE")
        with zipfile.ZipFile(io.BytesIO(apk_raw)) as z:
            need(set(z.namelist())==set(members) and len(z.namelist())==len(members)
                and all(z.read(n)==body for n,body in members.items()),"EVERY_SIGNED_ZIP_MEMBER_EQUALS_BUILD_INPUT")
        guard(); need(read(originals[kind])==raw and read("state/FixedStateProvider.java")==provider,"SOURCE_BUILD_BOOKENDS")
        result={"kind":kind,"package":package,"run_id":run_id,"original_apk":pin(raw),"original_certificate_sha256":old_cert,
            "original_members":original_members,"new_members":{n:pin(b) for n,b in members.items()},
            "apk":pin(apk_raw),"certificate_sha256":sha(cert),"provider_source":pin(provider),
            "provider_dex":pin(dex),"original_manifest_semantics_preserved":True,
            "original_business_dex_resources_assets_preserved":True,"original_sources_recompiled":False,
            "normal_static_build_verified":True,"installed":False,"whole_app_business_accepted":False,
            "commands":[r for r in records if r["kind"] in ("provider",kind)]}
        public=root/"public"; public.mkdir(mode=0o700)
        published={"helper.apk":apk_raw,"signer.der":cert,"STATE-SOURCE.json":encoded(result),"state/FixedStateProvider.java":provider}
        # The recovered Documents source remains an unchanged base-Activity
        # comparison, never a claim that it compiled the added provider.
        if kind in STATE_DOC_SOURCES:
            for name,wanted in STATE_DOC_SOURCES[kind].items():
                body=read("original-source/"+kind+"/"+name)
                need(pin(body)==wanted,"UNCHANGED_ORIGINAL_DOCUMENTS_SOURCE")
                published[name]=body
        else:
            published["SOURCE.json"]=encoded({"schema":"droidloom.preserved-owned-apk-source.v1",
                "kind":kind,"package":package,"run_id":run_id,"original_apk":pin(raw),
                "original_certificate_sha256":old_cert,"original_members":original_members,
                "original_sources_available":False,"original_sources_recompiled":False})
        manifest={"schema":"droidloom.prebuilt-state-helper-bundle.v1","kind":kind,
            "contract":{"kind":kind,"package":package,"run_id":run_id,"version_code":1,
                "compile_sdk":31,"min_sdk":31,"target_sdk":33,"permissions":[],
                "launcher":False,"test_only":True,"debuggable":False,
                "state_provider":STATE_CLASS,"state_authority":package+".state",
                "state_method":"state","state_caller_uid":2000,"state_arg":None,
                "state_extras":"null-or-empty","call_uri_path_received_by_provider":False},
            "apk":pin(apk_raw),"certificate_sha256":sha(cert),
            "original_apk":pin(raw),"original_certificate_sha256":old_cert,
            "members":{n:pin(b) for n,b in sorted(published.items())},"commands":result["commands"],
            "normal_static_build_verified":True,"installed":False,"private_signing_key_published":False,
            "actual_main_embedded_in_apk":False,"runtime_authority_created":False,
            "whole_app_business_accepted":False,"original_sources_recompiled":False,
            "original_manifest_semantics_preserved":True,"original_business_dex_resources_assets_preserved":True}
        published["MANIFEST.json"]=encoded(manifest)
        for name,body in published.items(): new_file(public/name,body,0o400)
        result["published_members"]={n:pin(b)for n,b in sorted(published.items())}
        results.append(result)
    guard(); need(time.monotonic()<original_end,"WHOLE_STATE_BUILD_END")
    return results
