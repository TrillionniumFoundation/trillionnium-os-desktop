"""Build the translator's platform-private view of the selected GSI lib64 tree."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid

MOUNT = "/system/system_ext/lib64"
VENDOR_LIB = "/lib64/droidloom/nativebridge"
ENGINE = "libberberis_arm64.so"
ORIGINAL = "hw/android.hidl.memory@1.0-impl.so"
ORIGINAL_SHA = "16d2b993998d519f533a7d95655dbcaaf37465c9cbbac8d5560c17f28f2817ec"
LIB_LABEL = "u:object_r:system_lib_file:s0"
FILE_TIME = "1230768000"
IMAGE = Path("system_ext_lib64.img")


def verify(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def run(arguments):
    result = subprocess.run(arguments, check=True, capture_output=True, text=True,
                            env=dict(os.environ, LC_ALL="C", E2FSPROGS_FAKE_TIME=FILE_TIME))
    return result.stdout, result.stderr


class FileSystem:
    def __init__(self, path, debugfs):
        self.path = path
        self.debugfs = debugfs

    def inspect(self, command, write=False):
        arguments = [self.debugfs]
        if write:
            arguments.append("-w")
        output, errors = run([*arguments, "-R", command, self.path])
        diagnostics = [line for line in errors.splitlines() if line and not line.startswith("debugfs ")]
        verify(not diagnostics, str(diagnostics))
        return output

    def members(self, path):
        members = {}
        for line in self.inspect("ls -lp " + path).splitlines():
            if not line:
                continue
            columns = line.split("/")
            name = columns[5]
            if name in (".", "..", ""):
                continue
            verify(re.fullmatch(r"[A-Za-z0-9_@.+-]+", name) and name not in members,
                   "unexpected or duplicate ext4 entry " + repr(name))
            members[name] = (int(columns[2], 8), int(columns[3]), int(columns[4]), int(columns[6] or 0))
        return members

    def extract(self, member, destination):
        # All debugfs arguments are fixed paths or names checked by members().
        verify(not destination.exists(), "extraction would overwrite a file")
        destination.parent.mkdir(parents=True, exist_ok=True)
        self.inspect("dump " + member + " " + str(destination))
        verify(destination.is_file() and not destination.is_symlink(), "missing extracted file")
        return sha256(destination)


def build(system, vendor, tools, native_hashes, existing_image=None):
    image = Path(existing_image) if existing_image is not None else IMAGE
    system_fs = FileSystem(system, tools["debugfs"])
    vendor_fs = FileSystem(vendor, tools["debugfs"])
    output_fs = FileSystem(image, tools["debugfs"])
    src = Path("src")
    src.mkdir()
    verify(system_fs.members(MOUNT) == {"hw": (0o40755, 0, 0, 0)}
           and system_fs.members(MOUNT + "/hw") == {Path(ORIGINAL).name: (0o100644, 0, 0, 37344)},
           "the original system extension lib64 directory layout changed")
    original_attributes = system_fs.inspect("ea_list " + MOUNT)
    expected_attributes = f'  security.selinux ({len(LIB_LABEL) + 1}) = "{LIB_LABEL}\\000"'
    verify(original_attributes.splitlines() == ["Extended attributes:", expected_attributes]
           and all(system_fs.inspect("ea_list " + MOUNT + "/" + name) == original_attributes
                   for name in ["hw", ORIGINAL]), "unexpected original platform inode attributes")
    hashes = {ORIGINAL: system_fs.extract(MOUNT + "/" + ORIGINAL, src / ORIGINAL)}
    verify(hashes[ORIGINAL] == ORIGINAL_SHA, "the selected platform hardware library changed")

    physical = vendor_fs.members(VENDOR_LIB)
    verify(set(physical) == set(native_hashes) and ENGINE in native_hashes,
           "installed vendor differs from built host module roster")
    for name, expected in sorted(native_hashes.items()):
        mode, uid, gid, size = physical[name]
        verify((mode, uid, gid) == (0o100644, 0, 0) and size > 0,
               "unexpected vendor mode or owner for " + name)
        relative = name if name == ENGINE else "droidloom/nativebridge/" + name
        hashes[relative] = vendor_fs.extract(VENDOR_LIB + "/" + name, src / relative)
        verify(hashes[relative] == expected, "vendor image differs from the normal native build: " + name)

    directories = ["droidloom", "droidloom/nativebridge", "hw"]
    config = ["/ 0 0 0755", MOUNT.lstrip("/") + " 0 0 0755"]
    config += [MOUNT.lstrip("/") + "/" + entry + " 0 0 0755" for entry in directories]
    config += [MOUNT.lstrip("/") + "/" + entry + " 0 0 0644" for entry in sorted(hashes)]
    Path("fs_config").write_text("\n".join(config) + "\n")
    contexts = Path("plat_file_contexts")
    system_fs.extract("/system/etc/selinux/plat_file_contexts", contexts)
    system_fs.extract("/system/etc/mke2fs.conf", Path("mke2fs.conf"))
    if existing_image is None:
        env_config = os.environ.get("MKE2FS_CONFIG")
        os.environ["MKE2FS_CONFIG"] = str(Path("mke2fs.conf").resolve())
        try:
            with image.open("xb") as stream:
                stream.truncate(24 * 1024 * 1024)
            identifier = str(uuid.uuid5(uuid.NAMESPACE_DNS, "pocket4.cp3a.r15.nativebridge.fixed-systemext-lib64"))
            run([tools["mke2fs"], "-q", "-t", "ext4", "-b", "4096", "-I", "256", "-m", "0",
                 "-U", identifier, "-L", "p4_system_ext", "-E",
                 "lazy_itable_init=0,lazy_journal_init=0,hash_seed=" + identifier, "-F", image])
        finally:
            if env_config is None:
                del os.environ["MKE2FS_CONFIG"]
            else:
                os.environ["MKE2FS_CONFIG"] = env_config
        verify(set(output_fs.members("/")) == {"lost+found"}, "unexpected empty filesystem")
        output_fs.inspect("rmdir /lost+found", write=True)
        run([tools["e2fsdroid"], "-e", "-T", FILE_TIME, "-C", "fs_config", "-S", contexts,
             "-a", MOUNT, "-f", src, image])
    run([tools["e2fsck"], "-fn", image])

    wanted = set(directories) | set(hashes)
    visited = set()
    def walk(parent):
        for name, (mode, uid, gid, size) in output_fs.members("/" + parent).items():
            member = parent + "/" + name if parent else name
            verify(member in wanted and member not in visited, "unexpected extension member: " + member)
            visited.add(member)
            verify(uid == 0 and gid == 0 and output_fs.inspect("ea_list /" + member) == original_attributes,
                   "extension ownership or platform attributes differ: " + member)
            if member in directories:
                verify(mode == 0o40755, "wrong extension directory mode: " + member)
                walk(member)
            else:
                temp = Path("reread")
                actual_sha = output_fs.extract("/" + member, temp)
                verify(mode == 0o100644 and temp.stat().st_size == size and actual_sha == hashes[member],
                       "extension library readback mismatch: " + member)
                temp.unlink()
    walk("")
    verify(visited == wanted and output_fs.inspect("ea_list /") == original_attributes,
           "extension root or member roster differs")
    root_stat = output_fs.inspect("stat /")
    verify(re.search(r"Type: directory\s+Mode:\s+0755", root_stat)
           and re.search(r"User:\s+0\s+Group:\s+0\s", root_stat), "incorrect root mode or owner")
    return {"file": IMAGE.name, "bytes": image.stat().st_size, "sha256": sha256(image),
            "target": MOUNT, "member_sha256": hashes, "platform_contexts_sha256": sha256(contexts)}


if __name__ == "__main__":
    data = json.loads(Path(sys.argv[1]).read_text())
    receipt = build(Path(data["system"]), Path(data["vendor"]), data["tools"], data["native_hashes"], data.get("existing_image"))
    Path("receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
