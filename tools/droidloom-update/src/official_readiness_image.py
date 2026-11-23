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


def build(system, service, rc, out, expected):
    for name, path in (("system", system), ("elf", service), ("rc", rc)):
        check(digest(path) == expected[name], name + " input changed")
    check(service.read_bytes()[:7] == b"\x7fELF\x02\x01\x01", "wrong selected ELF")
    check(not out.exists(), "output already exists")
    roots = ("bin", "etc/init")
    new_files = {"bin/droidloom-readiness": (service, 0o100755, 0, 2000, b"u:object_r:droidloom_readiness_exec:s0\0"),
                 "etc/init/droidloom-readiness.rc": (rc, 0o100644, 0, 0, b"u:object_r:system_file:s0\0")}
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
        # /etc is a private carrier parent. Only /bin and /etc/init are mounted.
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
        run(["e2fsck", "-fn", image])
        readback = {}
        for name, (mode, uid, gid, attributes, hash_value) in rows.items():
            parent, component = os.path.split("/" + name)
            metadata = names(image, parent)[component]
            check(metadata[:3] == (mode, uid, gid), "wrong inode mode or owner: "+name)
            check(attrs(image, "/"+name, attr_tmp) == attributes, "wrong xattr: "+name)
            if hash_value:
                check(hashlib.sha256(inspect(image, "cat /" + name)).hexdigest() == hash_value, name)
            else:
                wanted = {os.path.basename(x) for x in rows if os.path.dirname(x) == name}
                check(set(names(image, "/"+name)) == wanted, "unexpected directory contents: "+name)
            readback[name] = {"mode": oct(mode), "uid": uid, "gid": gid, "sha256": hash_value,
                              "xattrs_hex": {key: v.hex() for key, v in attributes.items()}}
        result = {"file": out.name, "sha256": digest(image), "bytes": image.stat().st_size,
                  "parents": expected, "mount_subtrees": list(roots), "members": readback}
        os.link(image, out)
        return result


if __name__ == "__main__":
    config = json.loads(Path(sys.argv[1]).read_text())
    if "tools" in config:
        if set(config["tools"]) != set(TOOLS):
            raise ValueError("incomplete selected ext4 tool set")
        TOOLS.update(config["tools"])
    result = build(*(Path(config[key]) for key in ("system", "elf", "rc", "output")), config["sha256"])
    print(json.dumps(result, sort_keys=True, indent=2))
