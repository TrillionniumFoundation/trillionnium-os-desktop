#!/usr/bin/env python3
"""Build only the diskless peer-LSM mechanism initrd; never install or boot it."""
import argparse, gzip, hashlib, json, os, pathlib, re, stat, subprocess

ap = argparse.ArgumentParser()
ap.add_argument("--program", type=pathlib.Path, required=True)
ap.add_argument("--profile", type=pathlib.Path, required=True)
ap.add_argument("--candidate-library", type=pathlib.Path, required=True)
ap.add_argument("--output", type=pathlib.Path, required=True)
args = ap.parse_args()
output = args.output
output.mkdir(mode=0o700, parents=False, exist_ok=False)

def held_bytes(path):
    with path.open("rb") as handle:
        before = os.fstat(handle.fileno())
        assert stat.S_ISREG(before.st_mode) and before.st_nlink == 1
        body = handle.read()
        after = os.fstat(handle.fileno())
        assert (before.st_dev, before.st_ino, before.st_size, before.st_mode, before.st_nlink, before.st_mtime_ns, before.st_ctime_ns) == (after.st_dev, after.st_ino, after.st_size, after.st_mode, after.st_nlink, after.st_mtime_ns, after.st_ctime_ns)
    return body, {"path": str(path), "bytes": len(body),
                  "sha256": hashlib.sha256(body).hexdigest(),
                  "mode": stat.S_IMODE(after.st_mode)}

def readelf(path, option):
    proc = subprocess.run(["/usr/bin/readelf", option, "--wide", str(path)],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          check=True, text=True)
    return proc.stdout

def needed(path):
    names = re.findall(r"\(NEEDED\).*?\[([^]]+)\]", readelf(path, "--dynamic"))
    assert len(names) == len(set(names))
    assert set(names) <= {"libc.so.6", "libpcre2-8.so.0", "ld-linux-x86-64.so.2"}
    return names

entries = {}
sources = []
def add(path, mode, body=b"", major=0, minor=0):
    assert not path.startswith("/") and path and all(x not in ("", ".", "..") for x in path.split("/"))
    assert path not in entries
    entries[path] = (mode, body, major, minor)
    parts = path.split("/")[:-1]
    for i in range(1, len(parts) + 1):
        parent = "/".join(parts[:i])
        entries.setdefault(parent, (stat.S_IFDIR | 0o755, b"", 0, 0))

def regular(path, source, mode, preserve_source_mode=False):
    body, pin = held_bytes(source)
    if preserve_source_mode:
        assert pin["mode"] == mode, "interpreter source mode changed"
    add(path, stat.S_IFREG | mode, body)
    sources.append({"guest_path": "/" + path, "source": pin})
    return body

def link(path, target):
    assert target and "\x00" not in target
    add(path, stat.S_IFLNK | 0o777, target.encode())

program = regular("peer-runtime", args.program, 0o755)
assert program[:6] == b"\x7fELF\x02\x01"
profile = regular("peer-deny.bin", args.profile, 0o644)
# .load consumes the original kernel serialization, not the parser's optional
# eight-byte user compression header. Compile for the locked target features.
assert 16 <= len(profile) <= 65536
assert profile.startswith(b"\x04\x08\x00version\x00\x02"), "raw kernel AppArmor stream required"
profile_version = int.from_bytes(profile[12:16], "little")
assert 5 <= (profile_version & 0x3ff) <= 9, "target kernel ABI version required"
assert not profile_version & 0x800, "forced complain profile is not a denial test"
assert profile.count(b"p4-peer-deny\x00") == 1, "the one fixed denial profile is required"
interpreter = re.findall(r"\[Requesting program interpreter: ([^]]+)\]",
                        readelf(args.program, "--program-headers"))
assert interpreter == ["/lib64/ld-linux-x86-64.so.2"]

library_directory = pathlib.Path("/usr/lib/x86_64-linux-gnu")
interpreter_source = pathlib.Path(interpreter[0]).resolve(strict=True)
assert interpreter_source == library_directory / "ld-linux-x86-64.so.2"
aa = args.candidate_library
assert aa.name == "libapparmor.so.1.30.7"
assert "Library soname: [libapparmor.so.1]" in readelf(aa, "--dynamic")
assert needed(aa) == ["libc.so.6"]
regular("usr/lib/x86_64-linux-gnu/" + aa.name, aa, 0o644)
link("usr/lib/x86_64-linux-gnu/libapparmor.so.1", aa.name)
queue = ["libselinux.so.1", *needed(args.program), *needed(aa)]
seen = set()
while queue:
    soname = queue.pop(0)
    if soname in seen:
        continue
    assert soname in {"libselinux.so.1", "libc.so.6", "libpcre2-8.so.0",
                      "ld-linux-x86-64.so.2"}
    seen.add(soname)
    source = (library_directory / soname).resolve(strict=True)
    assert source.parent == library_directory
    guest_leaf = "usr/lib/x86_64-linux-gnu/" + source.name
    if guest_leaf not in entries:
        is_interpreter = source == interpreter_source
        regular(guest_leaf, source, 0o755 if is_interpreter else 0o644,
                preserve_source_mode=is_interpreter)
    guest_alias = "usr/lib/x86_64-linux-gnu/" + soname
    if guest_alias != guest_leaf:
        link(guest_alias, source.name)
    queue += needed(source)
assert "ld-linux-x86-64.so.2" in seen and "libselinux.so.1" in seen
link("lib64/ld-linux-x86-64.so.2",
     "/usr/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2")
for directory in ["proc", "sys", "dev"]:
    entries.setdefault(directory, (stat.S_IFDIR | 0o755, b"", 0, 0))
add("dev/console", stat.S_IFCHR | 0o600, major=5, minor=1)
add("dev/null", stat.S_IFCHR | 0o666, major=1, minor=3)

cpio = bytearray()
def member(name, mode, body, major, minor, ino):
    encoded = name.encode() + b"\0"
    values = [ino, mode, 0, 0, 2 if stat.S_ISDIR(mode) else 1, 0,
              len(body), 0, 0, major, minor, len(encoded), 0]
    cpio.extend(b"070701" + "".join(f"{x:08x}" for x in values).encode())
    cpio.extend(encoded)
    cpio.extend(b"\0" * ((-len(cpio)) % 4))
    cpio.extend(body)
    cpio.extend(b"\0" * ((-len(cpio)) % 4))
for ino, name in enumerate(sorted(entries, key=lambda n: (n.count("/"), n)), 1):
    member(name, *entries[name], ino)
member("TRAILER!!!", 0, b"", 0, 0, len(entries) + 1)
cpio.extend(b"\0" * ((-len(cpio)) % 512))
archive = output / "peer-mechanism.cpio.gz"
archive.write_bytes(gzip.compress(cpio, compresslevel=6, mtime=0))
record = {
    "schema": "p4-peer-lsm-kernel-mechanism-material-v1",
    "required_kernel_release": "6.18.64-p4ctx6181-fusectl-aafs-peer-r1",
    "sources": sources,
    "initrd": held_bytes(archive)[1],
    "entry_count": len(entries),
    "denial_profile_kernel_abi": profile_version & 0x3ff,
    "denial_profile_raw_stream": True,
    "interpreter": {"requested_path": interpreter[0],
                    "guest_leaf": "/usr/lib/x86_64-linux-gnu/" + interpreter_source.name,
                    "source_mode": 0o755},
    "entries": [{"path": "/" + name, "mode": mode,
                 "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest(),
                 "device_major": major, "device_minor": minor}
                for name, (mode, body, major, minor) in sorted(entries.items())],
    "command_line": "console=ttyS0 rdinit=/peer-runtime loglevel=5 panic=-1 selinux=1 enforcing=1 apparmor=1 lsm=lockdown,capability,landlock,yama,selinux,apparmor,bpf,ima,evm p4_peer_mechanism=1",
    "guest_started": False, "production_policy_loaded": False,
    "production_qualified": False,
}
(output / "MATERIALS.json").write_text(json.dumps(record, indent=2) + "\n")
print(json.dumps({"initrd": record["initrd"], "entry_count": len(entries)}))
