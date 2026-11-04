"""Bounded diagnostics for a failed, once-only owned instrumentation command.

This module never reruns a test. It reads only the held fresh cell. Diagnostic
failure cannot replace the original command error or turn a failed run into PASS.
"""
import hashlib
import os
import re
import selectors
import stat
import subprocess
import time

LOG_LIMIT = 512 * 1024
ERROR_LIMIT = 64 * 1024
TOMBSTONE_LIMIT = 2 * 1024 * 1024
TOMBSTONE_TOTAL = 8 * 1024 * 1024
TOMBSTONE_COUNT = 4

def bounded_command(target, command, env, timeout=12):
    out = {"stdout": bytearray(), "stderr": bytearray()}
    limits = {"stdout": LOG_LIMIT, "stderr": ERROR_LIMIT}
    stopped = None
    cleanup_errors = []
    deadline = time.monotonic() + timeout
    with target.entry(command) as (argv, authorities):
        # A selector allocation failure occurs before any child is launched.
        selector = selectors.DefaultSelector()
        process = None
        try:
            process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE, env=env, close_fds=True,
                                       pass_fds=authorities)
            for name, stream in (("stdout", process.stdout), ("stderr", process.stderr)):
                os.set_blocking(stream.fileno(), False)
                selector.register(stream, selectors.EVENT_READ, name)
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    stopped = "diagnostic-timeout"
                    break
                for key, _ in selector.select(min(.1, remaining)):
                    name = key.data
                    try:
                        block = os.read(key.fd, min(65536, limits[name] + 1 - len(out[name])))
                    except BlockingIOError:
                        continue
                    if not block:
                        selector.unregister(key.fileobj)
                        key.fileobj.close()
                        continue
                    out[name].extend(block)
                    if len(out[name]) > limits[name]:
                        del out[name][limits[name]:]
                        stopped = "diagnostic-output-limit"
                        break
                if stopped:
                    break
        finally:
            try:
                selector.close()
            except BaseException as error:
                cleanup_errors.append("selector-close: " + repr(error))
            if process is not None:
                try:
                    if stopped is None and process.poll() is None:
                        process.wait(timeout=max(.001, deadline - time.monotonic()))
                except subprocess.TimeoutExpired:
                    stopped = "diagnostic-timeout"
                except BaseException as error:
                    cleanup_errors.append("initial-wait: " + repr(error))
                try:
                    if process.poll() is None:
                        process.kill()  # Only this exact Popen child.
                except BaseException as error:
                    cleanup_errors.append("own-child-kill: " + repr(error))
                for stream in (process.stdout, process.stderr):
                    try:
                        if stream is not None:
                            stream.close()
                    except BaseException as error:
                        cleanup_errors.append("stream-close: " + repr(error))
                try:
                    process.wait(timeout=5)
                except BaseException as error:
                    stopped = "diagnostic-child-not-reaped"
                    cleanup_errors.append("final-wait: " + repr(error))
                if process.returncode is None:
                    # A lease ending does not prove its process was reaped.
                    # Permanently forbid entry and FD release; the controller
                    # exit closes these FDs after exact cell/systemd cleanup.
                    target.poison_unjoined_command()
        return {"returncode": process.returncode, "stopped": stopped,
                "cleanup_errors": cleanup_errors,
                "stdout": bytes(out["stdout"]), "stderr": bytes(out["stderr"]),
                "stdout_limit": LOG_LIMIT, "stderr_limit": ERROR_LIMIT,
                "deadline_seconds": timeout, "child_reaped": process.returncode is not None}

def inspect_tombstones(target, label, package, uid, nonce, save):
    deadline = time.monotonic() + 10
    directory = target.open_root("/data/tombstones", os.O_RDONLY | os.O_DIRECTORY)
    rows = []
    total = 0
    try:
        names = []
        with os.scandir(directory) as entries:
            for entry in entries:
                names.append(entry.name)
                if len(names) > 256:
                    raise RuntimeError("owned tombstone directory bound exceeded")
        for name in sorted(names):
            if not re.fullmatch(r"tombstone_[0-9]{2,3}", name):
                continue
            if time.monotonic() > deadline:
                raise RuntimeError("owned tombstone deadline exceeded")
            fd = os.open(name, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=directory)
            try:
                before = os.fstat(fd)
                if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > TOMBSTONE_LIMIT:
                    continue
                head = os.read(fd, 4096)
                text = head.decode("utf-8", "replace")
                cmdline = next((line.removeprefix("Cmdline: ") for line in text.splitlines()
                                if line.startswith("Cmdline: ")), "")
                uid_match = re.search(r"^uid: ([0-9]+)$", text, re.M)
                owned = ((" nonce " + nonce + " ") in (" " + cmdline + " ") or
                         cmdline.split(" ", 1)[0] == package)
                if not owned or uid_match is None or int(uid_match[1]) not in (2000, uid):
                    continue
                if len(rows) >= TOMBSTONE_COUNT or total + before.st_size > TOMBSTONE_TOTAL:
                    raise RuntimeError("owned tombstone total bound exceeded")
                data = bytearray(head)
                while len(data) <= before.st_size:
                    if time.monotonic() > deadline:
                        raise RuntimeError("owned tombstone deadline exceeded")
                    block = os.read(fd, min(65536, before.st_size + 1 - len(data)))
                    if not block:
                        break
                    data.extend(block)
                after = os.fstat(fd)
                if ((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) !=
                    (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
                    or len(data) != before.st_size):
                    raise RuntimeError("owned tombstone changed while reading")
                raw = bytes(data)
                output = label + "-failure-" + name + ".txt"
                save(output, raw)
                total += len(raw)
                rows.append({"name": name, "output": output, "bytes": len(raw),
                             "sha256": hashlib.sha256(raw).hexdigest(),
                             "device": before.st_dev, "inode": before.st_ino,
                             "cmdline": cmdline, "uid": int(uid_match[1])})
            finally:
                os.close(fd)
    finally:
        os.close(directory)
    return {"files": rows, "bytes": total, "file_limit": TOMBSTONE_LIMIT,
            "total_limit": TOMBSTONE_TOTAL, "count_limit": TOMBSTONE_COUNT,
            "deadline_seconds": 10}

def capture(flow, label, row, binding, nonce, first_error):
    report = {"schema": 1, "scope": "held fresh private cell only",
              "first_error": str(first_error), "automatic_retry": False,
              "errors": [], "native_verdict_inferred": False}
    try:
        flow.guard(True)
        command = flow.guest_command(["/system/bin/logcat", "-b", "all", "-d", "-t", "128"], 0, 12)
        result = bounded_command(flow.target, command, flow.s["ENV"], timeout=12)
        flow.s["save"](label + "-failure-logcat.stdout", result.pop("stdout"))
        flow.s["save"](label + "-failure-logcat.stderr", result.pop("stderr"))
        report["logcat"] = result
        flow.guard(True)
    except BaseException as error:
        report["errors"].append("logcat: " + repr(error))
    try:
        flow.guard(True)
        report["tombstones"] = inspect_tombstones(flow.target, label, row["package"],
                                                 binding["uid"], nonce, flow.s["save"])
        flow.guard(True)
    except BaseException as error:
        report["errors"].append("tombstones: " + repr(error))
    flow.s["save"](label + "-failure-evidence.json", report)
    return report
