#!/usr/bin/env python3
"""Stage one actual-host-bound Android input in the existing private input directory."""
import hashlib
import json
import os
import stat
import sys

PARENT = '/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01'
NAME = 'qualification-inputs-9b4f271386ac6d2dfbe18594c5b92380'
FILENAME = 'android-inputs.json'
HOST_FILENAME = 'host-candidate-inputs.json'
NONCE = '9b4f271386ac6d2dfbe18594c5b92380'
DATA = b'{\n  "attempt": {\n    "data": "/var/lib/p4-signal-combined07-9b4f271386ac6d2d",\n    "evidence": "/home/alex/work/pocket4-signal-canary-combined07-9b4f271386ac6d2d",\n    "host_uid": 2407,\n    "name": "p4-signal-combined07-9b4f271386ac6d2d",\n    "runtime": "/run/p4-signal-combined07-9b4f271386ac6d2d",\n    "stage": "/opt/p4-signal-combined07-9b4f271386ac6d2d",\n    "subid_start": 14600000,\n    "user_runtime": "/run/user/1000/p4-signal-combined07-9b4f271386ac6d2d"\n  },\n  "base": {\n    "manifest": {\n      "path": "/opt/p4-media-composer-diagnostic-20261102-chat2-r5/media-canary-manifest.json",\n      "sha256": "31885dffa33fe30b0249d37acf437c00b348a0ac1020f8c56b427a8dac743183"\n    },\n    "root": "/opt/p4-media-composer-diagnostic-20261102-chat2-r5",\n    "spec": {\n      "path": "/opt/p4-media-composer-diagnostic-20261102-chat2-r5/cell.json",\n      "sha256": "944110b00770d948de050b92efe46d510f7afc142cf2c5742d4d2a898fad00ce"\n    }\n  },\n  "candidate_build_inputs": {\n    "path": "/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01/full-build-combined07-go5-streaming-01/android-out/target/product/droidloom_x86_64/droidloom-native-engine-inputs.json",\n    "sha256": "97c3b9e686ee2c1d2ac2a5f996cc2cee0a7f54dcb939f09bb44c3f5278f9a5b5"\n  },\n  "candidate_build_receipt": {\n    "path": "/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01/full-build-combined07-go5-streaming-01/android-out/target/product/droidloom_x86_64/droidloom-native-engine-source.json",\n    "sha256": "648cc61ba4652df24061b45cf7875f7c880d1793e8c217bc519e21e2f3677b90"\n  },\n  "cpu_inventory": {\n    "path": "/home/alex/work/pocket4-native-private-canary-20261104-r1/cpu-inventory-v2.json",\n    "sha256": "590d32e10c5a86934afbd18eebd620d5a07f0e13a4c4af2e4094fac801dc5c62"\n  },\n  "engine": {\n    "path": "/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01/full-build-combined07-go5-streaming-01/android-out/target/product/droidloom_x86_64/system/lib64/libberberis_arm64.so",\n    "sha256": "3aa9b479a9b66f56ae827477cf9f957fdeb6dcb21f1f8f981e34a1089f80048a"\n  },\n  "framework_guard": {\n    "path": "/home/alex/work/pocket4-framework-epoch-20261104-r10/framework_epoch.py",\n    "sha256": "f43f766f19a151d7d33ecd0c99c2e81f832fce7dcb1804e5c774e833066a6288"\n  },\n  "main_activation": {\n    "path": "/home/alex/work/pocket4-app-production-20261104-r10/deployment-preparation/activation-after-01.json",\n    "sha256": "7e490c14586d891f6b121341f879f41c955414c9122e3a68053f04665c12e615"\n  },\n  "main_resource_baseline": {\n    "cpu.max": "200000 100000",\n    "memory.high": "5368709120",\n    "memory.max": "6442450944",\n    "memory.swap.max": "max",\n    "pids.max": "12288"\n  },\n  "note": "Fresh candidate07 combined-engine qualification using unchanged frozen R5 runtime. All 3793 host registrations and the four original ARM64 cases are required. The inherited signal-mask-r1 preparation arm is a historical schema label. Metadata generation remains disabled; this does not qualify enabled metadata, ART, factory or whole apps. Main activation/epoch/resource and whole owned hierarchy retirement checks remain unchanged.",\n  "original_runner_manifest": {\n    "path": "/home/alex/work/pocket4-native-private-canary-20261104-r1/runner-v5-once-manifest.json",\n    "sha256": "72d3151d28485f536b9f28b9575b248da92c6b289998e28066a82a8a2f776f67"\n  },\n  "presenter": {\n    "path": "/opt/pocket4-presenter-timing-20261104-r10/payload/droidloom-wayland",\n    "sha256": "47f34d5f68783a372283cb63a42034d5899e270524cca40122bf28fd5e903f24"\n  },\n  "probes": {\n    "r2": {\n      "apk": {\n        "path": "/home/alex/work/pocket4-owned-signal-apk-r11-source-02/signal-probe/build-attempt-1/owned_signal_probe.apk",\n        "sha256": "7982ebd6e951a6c2159755afa79d1d7bafe43b6b6aa8c29f43a7d0c1496e3f59"\n      },\n      "build_receipt": {\n        "path": "/home/alex/work/pocket4-owned-signal-apk-r11-source-02/signal-probe/build-attempt-1/build-result.json",\n        "sha256": "9bf1e090f79583e496cfea6d2d0eee6afbbea16eb6db970752df80b470bbee20"\n      },\n      "source_pins": {\n        "path": "/home/alex/work/pocket4-owned-signal-apk-r11-source-02/signal-probe/SOURCE_PINS.json",\n        "sha256": "b5d03eb02ad073180fd3a680518bfac3be42b7df292caa3ba74b4139581d458f"\n      }\n    },\n    "r3": {\n      "apk": {\n        "path": "/home/alex/work/pocket4-owned-signal-r3-apk-r11-source-01/signal-probe-r3/build-attempt-1/owned_signal_probe.apk",\n        "sha256": "6ec31387ce9b648bc841b1aa6c4ca6bf67b2544fee804a320f2df100831ef0d9"\n      },\n      "build_receipt": {\n        "path": "/home/alex/work/pocket4-owned-signal-r3-apk-r11-source-01/signal-probe-r3/build-attempt-1/build-result.json",\n        "sha256": "55b2a7da86bbf7ddde0532f292b909a887625823fc89de82a1272ac99df33384"\n      },\n      "source_pins": {\n        "path": "/home/alex/work/pocket4-owned-signal-r3-apk-r11-source-01/signal-probe-r3/SOURCE_PINS.json",\n        "sha256": "1a17f89bf0ab6d03cc6d592528735c23012c3af38bc3b57cae008659631fc456"\n      }\n    }\n  },\n  "runner_manifest": {\n    "path": "/home/alex/work/pocket4-owned-signal-host-r11-source-01/isolated-signal-canary-r1/source-manifest.json",\n    "sha256": "3f12e8bcde951712a20208aaeed04f1125bac58993ce1a3f5a93e4f950a9b103"\n  },\n  "schema": 1,\n  "signal_fix_pins": {\n    "path": "/home/alex/work/pocket4-owned-signal-host-r11-source-01/candidate-attempt-01/signal-mask-r1-pins.json",\n    "sha256": "6a24ef53595e9d8da458a626effbfca4280a5de18c90ad1d5dd036ad3e936bf2"\n  },\n  "tools": {\n    "/usr/bin/cp": "8fcdb2485ebc68f00392d647b3d3d9130f0d4bb9f72c69ee258086dd63e1c122",\n    "/usr/bin/dbus-daemon": "bd0a019f1c4ed911eeb974f6e396d1eae9777ebac19a773361c1291a90addc5c",\n    "/usr/bin/env": "f84e76ea4da1e0c4e92254bd0d7dccdabe2c8b3098e734f27997dae3ee5d8e02",\n    "/usr/bin/journalctl": "d91b5f8629d41d7503fa00d8f4d58b6d0b72b5f0ca7b46667c8b5b1c59d460a2",\n    "/usr/bin/nsenter": "763259c01dca596ed903f1dc430599a938396294723165d0b0fdfdcc15d92aea",\n    "/usr/bin/sway": "5a4c54c1bfbb2fb6fc190e817222c2b10bbec71e030c717f22608a2fae91bdd4",\n    "/usr/bin/systemctl": "639bce3ce5c06b605079ea56f74e3f08216ddffcfa76e11f62073aa775180082",\n    "/usr/bin/systemd-run": "6eaf6650fc3bc07ba2fb51242d9d286e56770a2abd7306678aa22050ddf9f935",\n    "/usr/bin/timeout": "f84e76ea4da1e0c4e92254bd0d7dccdabe2c8b3098e734f27997dae3ee5d8e02",\n    "/usr/sbin/mkfs.ext4": "e42e49656dfc308efeed86f9bfad7746fc22ad1d4a3b0d508b5dba7a4b9a904f"\n  }\n}\n'
SHA256 = '25f8e4cf8aedce8f42ae251cd7404c8d684e0db6a0566f07a075890cb3f34d7b'
HOST_DATA = b'{\n  "arm": "candidate",\n  "baseline_result": {\n    "path": "/home/alex/work/pocket4-signal-host-baseline-r11-01-ff3127ab/result.json",\n    "sha256": "d99ee51205eeab9b6d33a2fcd6b4fa3d51304b06bc2fc638a470677a8f3a5a2e"\n  },\n  "binding": {\n    "candidate_build_inputs": {\n      "path": "/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01/full-build-combined07-go5-streaming-01/android-out/target/product/droidloom_x86_64/droidloom-native-engine-inputs.json",\n      "sha256": "97c3b9e686ee2c1d2ac2a5f996cc2cee0a7f54dcb939f09bb44c3f5278f9a5b5"\n    },\n    "candidate_build_receipt": {\n      "path": "/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01/full-build-combined07-go5-streaming-01/android-out/target/product/droidloom_x86_64/droidloom-native-engine-source.json",\n      "sha256": "648cc61ba4652df24061b45cf7875f7c880d1793e8c217bc519e21e2f3677b90"\n    },\n    "engine": {\n      "path": "/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01/full-build-combined07-go5-streaming-01/android-out/target/product/droidloom_x86_64/system/lib64/libberberis_arm64.so",\n      "sha256": "3aa9b479a9b66f56ae827477cf9f957fdeb6dcb21f1f8f981e34a1089f80048a"\n    },\n    "signal_fix_pins": {\n      "path": "/home/alex/work/pocket4-owned-signal-host-r11-source-01/candidate-attempt-01/signal-mask-r1-pins.json",\n      "sha256": "6a24ef53595e9d8da458a626effbfca4280a5de18c90ad1d5dd036ad3e936bf2"\n    }\n  },\n  "cpu": 6,\n  "evidence": "/home/alex/work/pocket4-signal-host-candidate-combined07-9b4f271386ac",\n  "kind": "owned-full-host-suite-r1",\n  "main": {\n    "framework_guard": {\n      "path": "/home/alex/work/pocket4-framework-epoch-20261104-r10/framework_epoch.py",\n      "sha256": "f43f766f19a151d7d33ecd0c99c2e81f832fce7dcb1804e5c774e833066a6288"\n    },\n    "main_activation": {\n      "path": "/home/alex/work/pocket4-app-production-20261104-r10/deployment-preparation/activation-after-01.json",\n      "sha256": "7e490c14586d891f6b121341f879f41c955414c9122e3a68053f04665c12e615"\n    },\n    "main_resource_baseline": {\n      "cpu.max": "200000 100000",\n      "memory.high": "5368709120",\n      "memory.max": "6442450944",\n      "memory.swap.max": "max",\n      "pids.max": "12288"\n    }\n  },\n  "nonce": "9b4f271386ac6d2dfbe18594c5b92380",\n  "preparation_source": "/home/alex/work/pocket4-owned-signal-host-r11-source-01/isolated-signal-canary-r1",\n  "schema": 1,\n  "tools": {\n    "/usr/bin/python3": "52e0a13e60a981d8c4b6478be2ba5176f69da07948a056bf49cf6f077e30cb41",\n    "/usr/bin/systemctl": "639bce3ce5c06b605079ea56f74e3f08216ddffcfa76e11f62073aa775180082"\n  },\n  "unit": "p4-signal-host-candidate-9b4f271386ac.service"\n}\n'
HOST_SHA256 = '22ef628bc6dfde895925db5a2b37f3e2b8a90d9133eb7b11be5d25a14532d601'


def need(value, message):
    if not value:
        raise RuntimeError(message)


def identity(value):
    return [value.st_dev, value.st_ino, value.st_mode, value.st_uid,
            value.st_gid, value.st_size, value.st_mtime_ns, value.st_ctime_ns]


def directory_identity(value):
    return [value.st_dev, value.st_ino, value.st_mode, value.st_uid, value.st_gid]


def read_frozen(fd, directory, name, expected, sha):
    before = os.fstat(fd)
    need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and
         before.st_uid == 1000 and before.st_gid == 1000 and
         stat.S_IMODE(before.st_mode) == 0o400 and before.st_size == len(expected),
         'frozen file type/owner/mode/size differs: ' + name)
    data = os.pread(fd, len(expected) + 1, 0)
    after = os.fstat(fd)
    named = os.stat(name, dir_fd=directory, follow_symlinks=False)
    need(identity(before) == identity(after) == identity(named) and
         data == expected and hashlib.sha256(data).hexdigest() == sha,
         'held/named frozen file or bytes changed: ' + name)
    return identity(after)


def main():
    need(hashlib.sha256(DATA).hexdigest() == SHA256 and
         hashlib.sha256(HOST_DATA).hexdigest() == HOST_SHA256, 'embedded input changed')
    need(json.loads(HOST_DATA)['nonce'] == NONCE and
         json.loads(DATA)['attempt']['name'] == 'p4-signal-combined07-' + NONCE[:16] and
         len(NONCE) == 32 and all(c in '0123456789abcdef' for c in NONCE) and
         NAME == 'qualification-inputs-' + NONCE, 'fixed nonce/directory differs')
    plan = {'schema': 1, 'state': 'PLAN_ONLY', 'directory': PARENT + '/' + NAME,
            'file': FILENAME, 'bytes': len(DATA), 'sha256': SHA256,
            'existing_host_input_sha256': HOST_SHA256, 'tests_executed': False,
            'Android_executed': False, 'Main_actions': 0}
    if sys.argv == [sys.argv[0]]:
        print(json.dumps(plan, sort_keys=True))
        return
    need(sys.argv[1:] == ['--execute-once'], 'explicit fixed execution mode required')
    need(os.getuid() == os.geteuid() == 1000 and os.getgid() == os.getegid() == 1000,
         'operator uid/gid must remain 1000')
    need(os.path.realpath(PARENT) == PARENT and
         os.path.realpath(PARENT + '/' + NAME) == PARENT + '/' + NAME,
         'fixed parent or input directory is an alias')
    parent = os.open(PARENT, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
    directory = host = target = None
    try:
        ps = os.fstat(parent)
        need(stat.S_ISDIR(ps.st_mode) and ps.st_uid == ps.st_gid == 1000 and
             stat.S_IMODE(ps.st_mode) == 0o700 and ps.st_dev == 66306 and
             ps.st_ino == 34351895, 'actual private parent identity or permissions differ')
        need(identity(ps) == identity(os.stat(PARENT, follow_symlinks=False)),
             'private parent held/named identity differs')
        directory = os.open(NAME, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC |
                            os.O_NOFOLLOW, dir_fd=parent)
        ds = os.fstat(directory)
        need(stat.S_ISDIR(ds.st_mode) and ds.st_uid == ds.st_gid == 1000 and
             stat.S_IMODE(ds.st_mode) == 0o700 and
             identity(ds) == identity(os.stat(NAME, dir_fd=parent, follow_symlinks=False)),
             'existing input directory held/named owner or mode differs')
        need(os.listdir(directory) == [HOST_FILENAME],
             'existing private directory is not the single host input')
        host = os.open(HOST_FILENAME, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW,
                       dir_fd=directory)
        host_before = read_frozen(host, directory, HOST_FILENAME, HOST_DATA, HOST_SHA256)
        # This O_EXCL open is the sole mutation/claim. No directory is created and no old file is modified.
        target = os.open(FILENAME, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW |
                         os.O_CLOEXEC, 0o600, dir_fd=directory)
        offset = 0
        while offset < len(DATA):
            written = os.write(target, DATA[offset:])
            need(written > 0, 'short input write')
            offset += written
        os.fchmod(target, 0o400)
        os.fsync(target)
        written_identity = identity(os.fstat(target))
        os.close(target)
        target = None
        target = os.open(FILENAME, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW,
                         dir_fd=directory)
        staged_identity = read_frozen(target, directory, FILENAME, DATA, SHA256)
        need(written_identity == staged_identity, 'written input was replaced')
        need(host_before == read_frozen(host, directory, HOST_FILENAME, HOST_DATA, HOST_SHA256),
             'original host input changed')
        after = os.fstat(directory)
        need(directory_identity(after) == directory_identity(ds) and
             identity(after) == identity(os.stat(NAME, dir_fd=parent, follow_symlinks=False)),
             'input directory replaced or permissions changed')
        need(sorted(os.listdir(directory)) == sorted([HOST_FILENAME, FILENAME]),
             'unexpected private input directory entries')
        need(directory_identity(os.fstat(parent)) == directory_identity(ps) and
             directory_identity(os.stat(PARENT, follow_symlinks=False)) == directory_identity(ps),
             'private parent replaced or permissions changed')
        os.fsync(directory)
        plan.update(state='FROZEN_ANDROID_INPUT_STAGED_NOT_EXECUTED', input_writes=1,
                    directories_created=0, children_created=0,
                    held_file_identity=staged_identity, host_input_identity=host_before,
                    held_directory_identity=identity(after))
        print(json.dumps(plan, sort_keys=True))
    finally:
        for fd in (target, host, directory, parent):
            if fd is not None:
                os.close(fd)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(json.dumps({'schema': 1, 'state': 'FAILED', 'error': repr(error),
                          'errno': getattr(error, 'errno', None),
                          'filename': getattr(error, 'filename', None),
                          'tests_executed': False, 'Android_executed': False,
                          'Main_actions': 0}, sort_keys=True))
        raise SystemExit(1)
