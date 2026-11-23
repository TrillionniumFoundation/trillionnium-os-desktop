# SPDX-License-Identifier: GPL-3.0-or-later
"""Build the two immutable system_ext subtrees used by the readiness service."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import uuid


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def check(value, detail):
    if not value:
        raise ValueError(detail)


CONTEXT_MEMBER = "etc/selinux/system_ext_property_contexts"
CONTEXT_FACTORY = "fae8632a118192c5dbb59c3a1096f575f410ae9eee80854355861e96a79eb0fd"
CONTEXT_AUGMENTED = "ca32c601b2debee94be7a5088f7050864e13e85e06e34598aef0b5925e154098"
CONTEXT_ADDITION = b"sys.droidloom.shutdown_request u:object_r:droidloom_shutdown_request_prop:s0 exact enum shutdown\n"
SHUTDOWN_LABEL = b"u:object_r:droidloom_shutdown_exec:s0\0"


def shutdown_context(system, expected):
    original = inspect(system, "cat /system/system_ext/" + CONTEXT_MEMBER)
    check(len(original) == 181 and hashlib.sha256(original).hexdigest() == CONTEXT_FACTORY,
          "different factory system_ext property declarations")
    augmented = original + CONTEXT_ADDITION
    check(hashlib.sha256(augmented).hexdigest() == expected == CONTEXT_AUGMENTED,
          "different single-value shutdown property declaration")
    return augmented


TOOLS = {name: name for name in ("debugfs", "mke2fs", "e2fsck")}


def run(args, **kw):
    program, *arguments = args
    kw.setdefault("env", dict(os.environ, E2FSPROGS_FAKE_TIME="1230768000", LC_ALL="C"))
    return subprocess.run([TOOLS[program], *arguments], check=True, capture_output=True, **kw)


def inspect(image, cmd, *, write=False):
    proc = run(["debugfs", *(["-w"] if write else []), "-R", cmd, image])
    messages = proc.stderr.decode().splitlines()
    check(all(line.startswith("debugfs ") for line in messages), (cmd, messages))
    return proc.stdout


def names(image, node):
    lines = inspect(image, "ls -lp " + node).decode().splitlines()
    values = {}
    for line in filter(None, lines):
        _, _, mode, uid, gid, name, size, _ = line.split("/")
        if name in (".", "..", ""):
            continue
        check(re.fullmatch(r"[A-Za-z0-9_@.+-]+", name) and name not in values, name)
        values[name] = (int(mode, 8), int(uid), int(gid), int(size or 0))
    return values


def attrs(image, name, temp):
    listing = inspect(image, "ea_list " + name).decode().splitlines()
    check(listing and listing[0] == "Extended attributes:", (name, listing))
    result = {}
    for line in listing[1:]:
        match = re.fullmatch(r"  ([a-zA-Z0-9_.]+) \(([0-9]+)\).*", line)
        check(match is not None, line)
        attribute, size = match.groups()
        if temp.exists():
            temp.unlink()
        inspect(image, f"ea_get -f {temp} {name} {attribute}")
        result[attribute] = temp.read_bytes()
        check(len(result[attribute]) == int(size), (name, attribute))
    return result


def verify(system, image, expected, work):
    """Compare both mounted subtrees against CP3A and the two normal installed files."""
    check(digest(system) == expected["system"], "original system digest changed")
    run(["e2fsck", "-fn", image])
    check(set(names(image, "/")) == {"bin", "etc"}, "unexpected readiness filesystem root")
    shutdown = expected.get("shutdown_property_contexts")
    check(set(names(image, "/etc")) == ({"init", "selinux"} if shutdown else {"init"}),
          "unexpected readiness carrier etc")
    check(names(image, "/")["etc"][:3] == (0o40755, 0, 0), "wrong private carrier parent")
    new_files = {
        "bin/droidloom-readiness": (0o100755, 0, 2000, b"u:object_r:droidloom_readiness_exec:s0\0", expected["elf"]),
        "etc/init/droidloom-readiness.rc": (0o100644, 0, 0, b"u:object_r:system_file:s0\0", expected["rc"]),
    }
    if shutdown:
        new_files["bin/droidloom-shutdown"] = (0o100755, 0, 2000, SHUTDOWN_LABEL, expected["elf"])
    result = {}
    attr_tmp = work / "verify-attr"
    def visit(relative, original, actual):
        mode, uid, gid, size = actual
        path = "/" + relative
        wanted = None
        if relative in new_files:
            want_mode, want_uid, want_gid, label, wanted = new_files[relative]
            check(original is None, "normal addition hides an original file: " + relative)
            check((mode, uid, gid) == (want_mode, want_uid, want_gid), "wrong added inode: " + relative)
            attributes = {"security.selinux": label}
        else:
            check(original is not None and actual[:3] == original[:3], "original inode changed: " + relative)
            original_path = "/system/system_ext/" + relative
            attributes = attrs(system, original_path, attr_tmp)
            if stat.S_ISDIR(mode):
                old = names(system, original_path)
                current = names(image, path)
                additions = {os.path.basename(item) for item in new_files if os.path.dirname(item) == relative}
                check(not old.keys() & additions and set(current) == set(old) | additions,
                      "subtree differs from original plus selected additions: " + relative)
                for name, entry in sorted(current.items()):
                    visit(relative + "/" + name, old.get(name), entry)
            else:
                check(stat.S_ISREG(mode) and size == original[3], "unsupported type or different size: " + relative)
                wanted = hashlib.sha256(inspect(system, "cat " + original_path)).hexdigest()
        check(attrs(image, path, attr_tmp) == attributes, "wrong xattrs: " + relative)
        if wanted is not None:
            contents = inspect(image, "cat " + path)
            check(len(contents) == size and hashlib.sha256(contents).hexdigest() == wanted,
                  "file bytes differ: " + relative)
            if relative == "bin/droidloom-readiness":
                check(contents[:7] == b"\x7fELF\x02\x01\x01" and contents[16:20] == b"\x03\x00\x3e\x00",
                      "expected a little-endian x86_64 PIE")
        result[relative] = {"mode": oct(mode), "uid": uid, "gid": gid, "sha256": wanted,
                            "xattrs_hex": {key: v.hex() for key, v in attributes.items()}}
    for relative in ("bin", "etc/init"):
        parent, leaf = os.path.split(relative)
        visit(relative, names(system, "/system/system_ext/" + parent)[leaf], names(image, "/" + parent)[leaf])
    if shutdown:
        selected = names(image, "/etc/selinux")
        factory = names(system, "/system/system_ext/etc/selinux")
        leaf = "system_ext_property_contexts"
        check(set(selected) == {leaf} and selected[leaf][:3] == factory[leaf][:3] == (0o100644, 0, 0),
              "incorrect original property file metadata or extra carrier files")
        check(names(image, "/etc")["selinux"][:3] == (0o40755, 0, 0), "invalid property carrier directory")
        actual = inspect(image, "cat /" + CONTEXT_MEMBER)
        check(actual == shutdown_context(system, shutdown), "unexpected change to the factory property declarations")
        metadata = attrs(system, "/system/system_ext/" + CONTEXT_MEMBER, attr_tmp)
        check(metadata.get("security.selinux") == b"u:object_r:property_contexts_file:s0\0" and
              attrs(image, "/" + CONTEXT_MEMBER, attr_tmp) == metadata, "changed original property file attributes")
        result[CONTEXT_MEMBER] = {"mode": oct(0o100644), "uid": 0, "gid": 0, "sha256": shutdown,
                                  "xattrs_hex": {key: value.hex() for key, value in metadata.items()}}
        inodes = []
        for path in ("/bin/droidloom-readiness", "/bin/droidloom-shutdown"):
            info = inspect(image, "stat " + path).decode()
            inode = re.search(r"^Inode: (\d+)\s+Type: regular", info)
            check(inode and re.search(r"^Links: 1\b", info, re.MULTILINE), "shutdown executables need independent inodes")
            inodes.append(inode[1])
        check(inodes[0] != inodes[1], "differently labeled executables share an inode")
    check(new_files.keys() <= result.keys(), "missing selected observer or init script")
    return result


def build(system, service, rc, out, expected):
    for name, path in (("system", system), ("elf", service), ("rc", rc)):
        check(digest(path) == expected[name], name + " input changed")
    check(service.read_bytes()[:7] == b"\x7fELF\x02\x01\x01", "wrong selected ELF")
    check(not out.exists(), "output already exists")
    roots = ("bin", "etc/init")
    new_files = {"bin/droidloom-readiness": (service, 0o100755, 0, 2000, b"u:object_r:droidloom_readiness_exec:s0\0"),
                 "etc/init/droidloom-readiness.rc": (rc, 0o100644, 0, 0, b"u:object_r:system_file:s0\0")}
    shutdown = expected.get("shutdown_property_contexts")
    if shutdown:
        new_files["bin/droidloom-shutdown"] = (service, 0o100755, 0, 2000, SHUTDOWN_LABEL)
    with tempfile.TemporaryDirectory(dir=out.parent) as directory:
        tmp = Path(directory).resolve()
        check(re.fullmatch(r"[/A-Za-z0-9_.-]+", str(tmp)), "unsafe private build path")
        material = tmp / "original"
        material.mkdir()
        rows = {}
        attr_tmp = tmp / "xattr"
        def read(name, metadata):
            mode, uid, gid, size = metadata
            source = "/system/system_ext/" + name
            check(name not in new_files and name not in rows, "input would be hidden: " + name)
            entry = (mode, uid, gid, attrs(system, source, attr_tmp), None)
            dest = material/name
            if stat.S_ISDIR(mode):
                rows[name] = entry
                dest.mkdir(parents=True)
                for child, child_data in sorted(names(system, source).items()):
                    read(name + "/" + child, child_data)
            else:
                check(stat.S_ISREG(mode), "unsupported original inode " + name)
                inspect(system, f"dump {source} {dest}")
                check(dest.stat().st_size == size, source)
                rows[name] = (*entry[:4], digest(dest))
        for name in roots:
            parent, component = os.path.split(name)
            read(name, names(system, "/system/system_ext/" + parent)[component])
        for name, (path, mode, uid, gid, label) in new_files.items():
            shutil.copyfile(path, material/name)
            rows[name] = (mode, uid, gid, {"security.selinux": label}, digest(path))
        if shutdown:
            parent = material / "etc/selinux"
            parent.mkdir()
            rows["etc/selinux"] = (0o40755, 0, 0, {}, None)
            file = material / CONTEXT_MEMBER
            file.write_bytes(shutdown_context(system, shutdown))
            original = "/system/system_ext/" + CONTEXT_MEMBER
            metadata = attrs(system, original, attr_tmp)
            rows[CONTEXT_MEMBER] = (0o100644, 0, 0, metadata, digest(file))
        # /etc remains private. The shutdown variant projects one verified property file.
        (material/"etc").mkdir(exist_ok=True)
        image = tmp/"carrier.img"
        with image.open("xb") as stream:
            stream.truncate(8 * 1024 * 1024)
        identifier = str(uuid.uuid5(uuid.NAMESPACE_DNS, "pocket4.trusted.system-ext-readiness.v1"))
        fs_config = tmp/"mke2fs.conf"
        inspect(system, f"dump /system/etc/mke2fs.conf {fs_config}")
        env = dict(os.environ, E2FSPROGS_FAKE_TIME="1230768000", LC_ALL="C", MKE2FS_CONFIG=str(fs_config))
        run(["mke2fs", "-q", "-t", "ext4", "-b", "4096", "-I", "256", "-m", "0",
             "-U", identifier, "-L", "p4_readiness", "-E",
             "lazy_itable_init=0,lazy_journal_init=0,hash_seed="+identifier, "-F", image], env=env)
        inspect(image, "rmdir /lost+found", write=True)
        for name in sorted({"etc", *rows}, key=lambda s: (s.count("/"), s)):
            mode, uid, gid, attributes, hash_value = rows.get(name, (0o40755, 0, 0, {}, None))
            if stat.S_ISDIR(mode):
                inspect(image, "mkdir /"+name, write=True)
            else:
                inspect(image, f"write {material/name} /{name}", write=True)
            for field, value in (("mode", oct(mode)), ("uid", uid), ("gid", gid),
                                 ("atime", "0x495c0780"), ("mtime", "0x495c0780"),
                                 ("ctime", "0x495c0780"), ("crtime", "0x495c0780")):
                # debugfs accepts the C octal form, not Python's 0o prefix.
                v = str(value).replace("0o", "0")
                inspect(image, f"set_inode_field /{name} {field} {v}", write=True)
            for key, value in attributes.items():
                attr_tmp.write_bytes(value)
                inspect(image, f"ea_set -f {attr_tmp} /{name} {key}", write=True)
        readback = verify(system, image, expected, tmp)
        result = {"file": out.name, "sha256": digest(image), "bytes": image.stat().st_size,
                  "parents": expected, "mount_subtrees": list(roots), "members": readback}
        os.link(image, out)
        return result


if __name__ == "__main__":
    config = json.loads(Path(sys.argv[1]).read_text())
    if "tools" in config:
        required = {"debugfs", "e2fsck"} if "existing_image" in config else set(TOOLS)
        if set(config["tools"]) != required:
            raise ValueError("incomplete selected ext4 tool set")
        TOOLS.update(config["tools"])
    if "existing_image" in config:
        image = Path(config["existing_image"])
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp:
            checked = verify(Path(config["system"]), image, config["sha256"], Path(temp))
        result = {"members": checked, "bytes": image.stat().st_size, "sha256": digest(image)}
    else:
        result = build(*(Path(config[key]) for key in ("system", "elf", "rc", "output")), config["sha256"])
    print(json.dumps(result, sort_keys=True, indent=2))
