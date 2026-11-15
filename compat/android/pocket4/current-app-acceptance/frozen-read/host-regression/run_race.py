"""Run an actual read_frozen source against a pathname-to-FIFO open race.

This is a host-only blocking-I/O regression. It grants no Android evidence.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import select
import subprocess
import tempfile


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def race(binary, preload, replace="fifo"):
    with tempfile.TemporaryDirectory(prefix="p4-frozen-open-") as directory:
        root = Path(directory)
        target = root / "evidence.json"
        target.write_bytes(b"owned host test evidence\n")
        before = target.stat()
        notify_r, notify_w = os.pipe()
        release_r, release_w = os.pipe()
        env = dict(os.environ, LD_PRELOAD=str(preload), P4_FROZEN_RACE_PATH=str(target),
                   P4_FROZEN_NOTIFY_FD=str(notify_w), P4_FROZEN_RELEASE_FD=str(release_r))
        child = None
        pidfd = None
        timed_out = False
        message = b""
        try:
            child = subprocess.Popen([str(binary), str(target)], env=env, stdin=subprocess.DEVNULL,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                     pass_fds=(notify_w, release_r), start_new_session=True)
            pidfd = os.pidfd_open(child.pid)
            os.close(notify_w); notify_w = None
            os.close(release_r); release_r = None
            ready, _, _ = select.select([notify_r], [], [], 5)
            if not ready:
                raise RuntimeError("reader did not reach the actual target open")
            message = os.read(notify_r, 256)
            if not message.startswith(b"open_flags="):
                raise RuntimeError("bad interposition rendezvous")
            target.rename(root / "original-owned-evidence.json")
            if replace == "fifo":
                os.mkfifo(target, 0o600)
            elif replace == "symlink":
                target.symlink_to(root / "original-owned-evidence.json")
            else:
                raise ValueError(replace)
            os.write(release_w, b"G")
            try:
                stdout, stderr = child.communicate(timeout=2)
            except subprocess.TimeoutExpired:
                timed_out = True
                child.kill()
                stdout, stderr = child.communicate(timeout=5)
            retired, _, _ = select.select([pidfd], [], [], 0)
            if not retired:
                raise RuntimeError("own reader pidfd not retired")
            return {"source_action": "rename original then create " + replace,
                    "before": {"dev": before.st_dev, "ino": before.st_ino, "bytes": before.st_size},
                    "interposer_observation": message.decode("ascii").strip(),
                    "timed_out_blocked_in_real_open": timed_out,
                    "exit_code": child.returncode,
                    "stdout": stdout.decode("utf-8", "strict"),
                    "stderr": stderr.decode("utf-8", "strict"),
                    "original_child_reaped": True, "original_pidfd_readable": True,
                    "Android_actions": 0}
        finally:
            if child is not None and child.poll() is None:
                child.kill(); child.wait(timeout=5)
            for fd in (notify_r, notify_w, release_r, release_w, pidfd):
                if fd is not None:
                    os.close(fd)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("binary", type=Path)
    p.add_argument("preload", type=Path)
    p.add_argument("--replacement", choices=("fifo", "symlink"), default="fifo")
    p.add_argument("--expect", choices=("blocks", "rejects"), required=True)
    args = p.parse_args()
    result = race(args.binary.resolve(), args.preload.resolve(), args.replacement)
    result.update(binary_sha256=sha(args.binary), preload_sha256=sha(args.preload),
                  expected=args.expect, replacement=args.replacement)
    result["expectation_met"] = (result["timed_out_blocked_in_real_open"]
                                  if args.expect == "blocks" else
                                  not result["timed_out_blocked_in_real_open"] and result["exit_code"] == 2)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["expectation_met"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
