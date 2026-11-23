"""Build and inspect the private, per-cell source for four standard Android devices."""
import ctypes
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path


IMAGE_BYTES = 8 * 1024 * 1024
CONTEXTS_SHA = "85175ed802b5661b44ba7ffff5e820e34dcbcbf9d8cbec799a5a1853499941bb"
UEVENTD_SHA = "7a26df7521ecba3b3fd66df438b4e5d1b5e8fa6fc5ea1a73c2c93eed803f985e"
# fuse uses DeviceHandler's fallback mode in the selected factory ueventd configuration.
DEVICES = (
    ("zero", 1, 5, 0o666, "zero_device"),
    ("full", 1, 7, 0o666, "device"),
    ("tty", 5, 0, 0o666, "owntty_device"),
    ("fuse", 10, 229, 0o600, "fuse_device"),
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main(inputs):
    tools = inputs["tools"]
    env = dict(os.environ, LC_ALL="C", E2FSPROGS_FAKE_TIME="1704067200")
    def run(name, *args):
        return subprocess.run([tools[name], *args], env=env, check=True,
                              stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE).stdout

    for name, guest, expected in (
        ("contexts", "/system/etc/selinux/plat_file_contexts", CONTEXTS_SHA),
        ("ueventd.rc", "/system/etc/ueventd.rc", UEVENTD_SHA),
    ):
        run("debugfs", "-R", "dump " + guest + " " + name, inputs["system"])
        require(digest(Path(name)) == expected, "wrong selected factory input " + guest)

    class Option(ctypes.Structure):
        _fields_ = [("kind", ctypes.c_int), ("value", ctypes.c_char_p)]

    selinux = ctypes.CDLL("libselinux.so.1", use_errno=True)
    selinux.selabel_open.argtypes = [ctypes.c_uint, ctypes.POINTER(Option), ctypes.c_uint]
    selinux.selabel_open.restype = ctypes.c_void_p
    selinux.selabel_lookup_raw.argtypes = [
        ctypes.c_void_p, ctypes.POINTER(ctypes.c_char_p), ctypes.c_char_p, ctypes.c_int,
    ]
    selinux.selabel_close.argtypes = [ctypes.c_void_p]
    selinux.freecon.argtypes = [ctypes.c_char_p]
    option = Option(3, b"contexts")
    handle = selinux.selabel_open(0, ctypes.byref(option), 1)
    require(handle, "cannot open the selected Android file-context database")
    commands = ["rmdir lost+found"]
    try:
        rules = [line.split() for line in Path("ueventd.rc").read_text().splitlines()]
        for name, major, minor, mode, kind in DEVICES:
            guest = "/dev/" + name
            explicit = [r[1:] for r in rules if r and r[0] == guest]
            want = [] if name == "fuse" else [[format(mode, "04o"), "root", "root"]]
            require(explicit == want, "unexpected ueventd rule for " + guest)
            context = ctypes.c_char_p()
            require(selinux.selabel_lookup_raw(handle, ctypes.byref(context), guest.encode(),
                                              stat.S_IFCHR) == 0, "unknown label for " + guest)
            try:
                native = ("u:object_r:" + kind + ":s0").encode()
                require(context.value == native, "wrong character device label for " + guest)
                Path(name + ".label").write_bytes(native + b"\0")
            finally:
                selinux.freecon(context)
            commands.extend([
                f"mknod {name} c {major} {minor}",
                f"set_inode_field {name} mode 0{stat.S_IFCHR | mode:o}",
                f"ea_set -f {name}.label {name} security.selinux",
            ])
    finally:
        selinux.selabel_close(handle)

    image = Path("android-device-source.img")
    with image.open("xb") as target:
        target.truncate(IMAGE_BYTES)
    run("mke2fs", "-q", "-F", "-t", "ext4", "-b", "4096", "-I", "256", "-N", "128",
        "-m", "0", "-L", "P4_SAFE_DEV", "-U", "ca89400f-44e7-5a57-bd42-f3dd706241cb",
        "-O", "^has_journal", "-E", "lazy_itable_init=0,hash_seed=ca89400f-44e7-5a57-bd42-f3dd706241cb", image)
    Path("edits").write_text("\n".join(commands) + "\n")
    run("debugfs", "-w", "-f", "edits", image)
    run("e2fsck", "-fn", image)
    entries = run("debugfs", "-R", "ls -p /", image).decode().splitlines()
    names = [line.split("/")[5] for line in entries if line]
    require(sorted(names) == sorted([".", "..", *(d[0] for d in DEVICES)]),
            "unexpected member in the private device image")
    result = {}
    for name, major, minor, mode, kind in DEVICES:
        info = run("debugfs", "-R", "stat /" + name, image).decode()
        number = re.search(r"Device major/minor number:\s*\d+:\d+\s+\(hex ([a-fA-F0-9]+):([a-fA-F0-9]+)\)", info)
        require("Type: character special" in info and
                re.search(r"Mode:\s+0*" + format(mode, "o") + r"\b", info) and
                re.search(r"User:\s+0\s+Group:\s+0\b", info) and
                re.search(r"Links:\s+1\b", info) and number and
                tuple(int(n, 16) for n in number.groups()) == (major, minor),
                "wrong private inode for /dev/" + name)
        run("debugfs", "-R", f"ea_get -f {name}.readback /{name} security.selinux", image)
        require(Path(name + ".readback").read_bytes() == Path(name + ".label").read_bytes(),
                "wrong device image xattr for " + name)
        result[name] = {"rdev": [major, minor], "mode": mode, "uid": 0, "gid": 0,
                        "selinux": "u:object_r:" + kind + ":s0"}
    return {"sha256": digest(image), "bytes": image.stat().st_size, "devices": result,
            "platform_file_contexts_sha256": CONTEXTS_SHA, "ueventd_rc_sha256": UEVENTD_SHA}


if __name__ == "__main__":
    print(json.dumps(main(json.loads(Path(sys.argv[1]).read_text())), sort_keys=True))
