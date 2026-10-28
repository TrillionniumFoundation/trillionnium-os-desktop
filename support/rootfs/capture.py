#!/usr/bin/env python3
"""Capture an auditable *candidate* readonly Linux ELF rootfs without chroot/mount.

The generated tar is deterministic for identical input bytes. This stages the
ELF loader/DT_NEEDED closure, glibc NSS modules and public CA trust. Runtime
dlopen, files, services and syscalls are NOT inferred from this static closure:
only a real strace can qualify them, especially for the pinned Hepta profile.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tarfile


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def run(argv):
    p = subprocess.run([str(x) for x in argv], capture_output=True, text=True)
    if p.returncode:
        raise RuntimeError(f"{' '.join(map(str, argv))}: {p.stderr.strip()}")
    return p.stdout


def elf_closure(elf):
    headers = run(["readelf", "-l", elf])
    needed = re.search(r"Requesting program interpreter: ([^]]+)", headers)
    loader = needed.group(1) if needed else None
    data = run(["readelf", "-d", elf])
    dynamic_names = re.findall(r"Shared library: \[([^]]+)\]", data)
    paths = set()
    if loader:
        paths.add(loader)
        listing = run(["ldd", elf])  # Input MUST be a trusted, pinned ELF.
        if "not found" in listing:
            raise RuntimeError(f"unresolved DT_NEEDED for {elf}: {listing}")
        paths.update(re.findall(r"(?:=>\s*)?(/[^\s(]+)\s*\(", listing))
    return loader, dynamic_names, sorted(paths)


def package(path):
    candidates = [path]
    if path.startswith("/lib/"):
        candidates.append("/usr" + path)
    if path.startswith("/lib64/"):
        candidates.append("/usr" + path)
    for candidate in candidates[::-1]:
        p = subprocess.run(["dpkg-query", "-S", candidate], capture_output=True, text=True)
        if p.returncode:
            continue
        first = next((x for x in p.stdout.splitlines() if ": " in x and not x.startswith("diversion ")), "")
        if not first:
            continue
        owner = first.rsplit(": ", 1)[0].split(", ")[0]
        v = subprocess.run(["dpkg-query", "-W", "-f=${Version}", owner], capture_output=True, text=True)
        if v.returncode == 0:
            return {"name": owner, "version": v.stdout.strip()}
    return None


def host_packages():
    names = ("gcc", "libc6", "libc6-dev", "libsqlite3-0", "libsqlite3-dev",
             "ca-certificates", "tzdata", "python3-minimal", "openssl")
    installed = {}
    for name in names:
        p = subprocess.run(["dpkg-query", "-W", "-f=${Version}", name], capture_output=True, text=True)
        if p.returncode == 0 and p.stdout.strip():
            installed[name] = p.stdout.strip()
    return installed


def add_file(root, record, dest, source=None, data=None, executable=False):
    if not dest.startswith("/") or ".." in Path(dest).parts or dest == "/":
        raise ValueError("unsafe rootfs destination")
    target = root / dest.lstrip("/")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise ValueError(f"duplicate path: {dest}")
    if source is not None:
        if not Path(source).is_file():
            raise FileNotFoundError(source)
        target.write_bytes(Path(source).read_bytes())
        origin = ({"build_source": "tests/workloads/linux/", "source_sha256": sha(source)}
                  if dest.startswith("/usr/local/bin/a04/") else
                  {"host_path": str(source), "source_sha256": sha(source), "package": package(str(source))})
    else:
        target.write_bytes(data)
        origin = {"generated": True}
    os.chmod(target, 0o555 if executable else 0o444)
    record.append({"path": dest, "sha256": sha(target), "bytes": target.stat().st_size,
                   "mode": "0555" if executable else "0444", "origin": origin})


def create_tar(root, out):
    """Deterministic USTAR with real DIRTYPE, never file-typed `etc/` entries.

    tarfile.TarInfo(name + "/") does NOT set type=DIRTYPE automatically.
    The old A04 archive therefore failed ordinary tarfile.extractall() at /etc.
    Reject symlinks/special files so a staged rootfs cannot import host bytes.
    """
    root = Path(root)
    with tarfile.open(out, "w", format=tarfile.USTAR_FORMAT) as tar:
        files = sorted(root.rglob("*"), key=lambda x: x.relative_to(root).as_posix())
        for file in files:
            if file.is_symlink() or not (file.is_dir() or file.is_file()):
                raise ValueError("unsupported staged rootfs entry: " + file.relative_to(root).as_posix())
            is_dir = file.is_dir()
            rel = file.relative_to(root).as_posix()
            info = tarfile.TarInfo(rel + ("/" if is_dir else ""))
            info.type = tarfile.DIRTYPE if is_dir else tarfile.REGTYPE
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            info.mtime = 0
            info.mode = 0o755 if is_dir else file.stat().st_mode & 0o777
            if is_dir:
                info.size = 0
                tar.addfile(info)
            else:
                content = file.read_bytes()
                info.size = len(content)
                tar.addfile(info, io.BytesIO(content))



def extract_verified_tar(archive_path, manifest_path, destination):
    """Materialize ONLY the manifest-pinned regular files in a fresh directory.

    Refuse the old A04 archive with regular-file-typed directory entries,
    links, path traversal, missing files or changed byte hashes. Never write
    outside the new destination or silently relax pinned read-only modes.
    This is host staging only, not a guest mounted-rootfs qualification.
    """
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise ValueError("destination already exists; refusing extraction")
    manifest = json.loads(Path(manifest_path).read_text())
    expected = {}
    for entry in manifest["files"]:
        path = entry["path"]
        if (not isinstance(path, str) or not path.startswith("/") or path.startswith("//") or
                path == "/" or PurePosixPath(path).as_posix() != path or
                ".." in PurePosixPath(path).parts or path[1:] in expected):
            raise ValueError("invalid or duplicate pinned manifest path")
        expected[path[1:]] = entry
    required_dirs = set()
    for name in expected:
        parent = PurePosixPath(name).parent
        while str(parent) != ".":
            required_dirs.add(str(parent))
            parent = parent.parent
    members = {}
    with tarfile.open(archive_path, "r:") as tar:
        for member in tar.getmembers():
            name = member.name
            path = PurePosixPath(name)
            if (not name or path.is_absolute() or ".." in path.parts or
                    path.as_posix() != name or name in members):
                raise ValueError("unsafe or duplicate rootfs tar entry")
            if member.isdir():
                if name not in required_dirs or member.size != 0 or member.mode != 0o755:
                    raise ValueError("unexpected rootfs directory or permissions")
            elif member.isfile():
                entry = expected.get(name)
                if (entry is None or member.size != entry["bytes"] or
                        member.mode != int(entry["mode"], 8)):
                    raise ValueError("unexpected rootfs file, size or permissions")
                handle = tar.extractfile(member)
                if handle is None:
                    raise ValueError("missing rootfs file data")
                digest = hashlib.sha256()
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
                if digest.hexdigest() != entry["sha256"]:
                    raise ValueError("rootfs tar content SHA-256 mismatch")
            else:
                raise ValueError("rootfs tar contains link or special file")
            members[name] = member
        if (set(name for name, member in members.items() if member.isfile()) != set(expected)
                or set(name for name, member in members.items() if member.isdir()) != required_dirs):
            raise ValueError("rootfs tar file/directory closure differs from manifest")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.mkdir(mode=0o700)
        for name in sorted(required_dirs, key=lambda x: (x.count("/"), x)):
            (destination / name).mkdir(mode=0o755)
        for name in sorted(expected):
            target = destination / name
            handle = tar.extractfile(members[name])
            if handle is None:
                raise ValueError("unexpected missing rootfs tar payload")
            with target.open("xb") as dst:
                shutil.copyfileobj(handle, dst, 1024 * 1024)
            target.chmod(int(expected[name]["mode"], 8))
    verify(destination, manifest_path)
    return len(expected)


def verify(root, manifest):
    """Require an exact manifest of regular files; exclude symlink escape paths."""
    root = Path(root)
    obj = json.loads(Path(manifest).read_text())
    records = obj["files"]
    expected = {}
    for record in records:
        name = record["path"]
        if (not isinstance(name, str) or not name.startswith("/")
                or name == "/" or ".." in Path(name).parts or name in expected):
            raise ValueError("invalid or duplicate rootfs manifest path")
        expected[name] = (record["sha256"], record["mode"])
    actual = {}
    for entry in root.rglob("*"):
        if entry.is_symlink() or not (entry.is_dir() or entry.is_file()):
            raise ValueError("unsafe rootfs staging entry: " + entry.relative_to(root).as_posix())
        if entry.is_file():
            actual["/" + entry.relative_to(root).as_posix()] = (
                sha(entry), f"{entry.stat().st_mode & 0o777:04o}")
    if expected != actual:
        missing = sorted(set(expected) - set(actual))
        extra = sorted(set(actual) - set(expected))
        mismatched = sorted(k for k in set(actual) & set(expected) if actual[k] != expected[k])
        raise RuntimeError(f"rootfs changed: missing={missing}, extra={extra}, mismatch={mismatched}")
    return len(actual)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, required=True, help="new rootfs directory")
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--tar", type=Path, help="optional deterministic uncompressed tar")
    ap.add_argument("--binary", type=Path, action="append", help="trusted ELF to capture; repeat")
    ap.add_argument("--verify", action="store_true", help="only check existing directory against manifest")
    ap.add_argument("--extract-verified", action="store_true",
                    help="extract an existing pinned --tar to NEW --root after strict verification")
    args = ap.parse_args()
    root = args.root.resolve()
    if args.extract_verified:
        if not args.tar or args.verify or args.binary:
            ap.error("--extract-verified requires --tar and excludes --verify/--binary")
        count = extract_verified_tar(args.tar, args.manifest, root)
        print(json.dumps({"verified_extracted_files": count, "host_only": True}))
        return
    if args.verify:
        print(json.dumps({"verified_files": verify(root, args.manifest)}))
        return
    if not args.binary:
        ap.error("at least one --binary is required")
    if root.exists():
        ap.error("root already exists; refusing to overwrite")
    root.mkdir(parents=True)
    manifest = {"schema": 1, "kind": "candidate_elf_rootfs", "qualified_hepta": False,
                "readonly_mount_verified": False,
                "policy": {"rootfs": "read-only when mounted by guest; staging directory not a mounted filesystem",
                           "writable_workspace": "/work (guest must mount separately)",
                           "external_dns": "unconfigured", "timezone": "UTC", "locale": "C",
                           "system_services": ["guest init", "procfs", "devtmpfs or /dev/null", "clock", "entropy"]},
                "elf": [], "files": [], "host_packages": host_packages()}
    files = manifest["files"]
    libs = set()
    for elf in args.binary:
        path = elf.resolve()
        loader, needed, paths = elf_closure(path)
        dest = f"/usr/local/bin/a04/{path.name}"
        add_file(root, files, dest, path, executable=True)
        manifest["elf"].append({"name": path.name, "sha256": sha(path),
                                "interpreter": loader, "needed": needed, "path": dest})
        libs.update(paths)
    # Glibc may dlopen these via NSS; ldd of the ELF alone cannot show them.
    for nss in ("libnss_files.so.2", "libnss_dns.so.2"):
        for base in ("/lib/x86_64-linux-gnu", "/usr/lib/x86_64-linux-gnu"):
            candidate = Path(base) / nss
            if candidate.exists():
                libs.add(str(candidate))
                break
    for lib in sorted(libs):
        add_file(root, files, lib, lib, executable=True)
    add_file(root, files, "/etc/nsswitch.conf",
             data=b"passwd: files\ngroup: files\nhosts: files dns\n")
    add_file(root, files, "/etc/hosts", data=b"127.0.0.1 localhost\n::1 localhost\n")
    add_file(root, files, "/etc/passwd", data=b"root:x:0:0:root:/root:/bin/sh\nnobody:x:65534:65534:nobody:/:/usr/sbin/nologin\n")
    add_file(root, files, "/etc/group", data=b"root:x:0:\nnogroup:x:65534:\n")
    # No inherited host DNS settings, tokens, state, machine ID or SSH keys.
    add_file(root, files, "/etc/resolv.conf", data=b"# no external DNS resolver pinned\n")
    cert = Path("/etc/ssl/certs/ca-certificates.crt")
    if cert.is_file():
        add_file(root, files, str(cert), cert)
    zoneinfo = Path("/usr/share/zoneinfo/UTC")
    if zoneinfo.is_file():
        add_file(root, files, str(zoneinfo), zoneinfo)
    files.sort(key=lambda item: item["path"])
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    verified = verify(root, args.manifest)
    tar_sha = None
    if args.tar:
        args.tar.parent.mkdir(parents=True, exist_ok=True)
        create_tar(root, args.tar)
        tar_sha = sha(args.tar)
    print(json.dumps({"verified_files": verified, "elf_count": len(manifest["elf"]),
                      "tar_sha256": tar_sha, "hepta_qualified": False}))


if __name__ == "__main__":
    main()
