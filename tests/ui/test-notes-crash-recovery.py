#!/usr/bin/env python3
"""Real private Session/Notes transport, SIGKILL and separate recovery process.

This is application durability qualification. Its parent is an isolated
transport fixture, not a production Hepta authority or durable writer.
"""

import contextlib
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import socket
import struct
import subprocess
import sys
import tempfile
import time

spec = importlib.util.spec_from_file_location(
    "notes_bootstrap_probe", Path(__file__).with_name("test-notes-bootstrap-ipc.py")
)
bootstrap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bootstrap)
require = bootstrap.require
encode = bootstrap.encode


@contextlib.contextmanager
def recovery_process(binary, state, target):
    parent, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_DGRAM)
    parent.settimeout(4)
    proc = subprocess.Popen(
        [str(binary), "--state-dir", str(state), "--notes-session", target["session_instance"],
         "--task-id", str(target["task_id"]), "--notes-incarnation", target["incarnation"]],
        stdin=child, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )
    child.close()
    try:
        yield parent, proc
    finally:
        parent.close()
        if proc.poll() is None:
            proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=3)
        proc.stderr.close()


def exchange(channel, request):
    channel.send(encode(request))
    raw = channel.recv(2049)
    require(0 < len(raw) <= 2048, "recovery response bound")
    return json.loads(raw), raw


def check(binary_dir):
    require(os.environ.get("TRILL_NOTES_PROBE_ISOLATED") == "1"
            and (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")),
            "use an owned isolated compositor")
    binary_dir = Path(binary_dir).resolve()
    helper = binary_dir / "trill-notes-recovery"
    require(os.access(helper, os.X_OK), "missing recovery executable")
    with tempfile.TemporaryDirectory(prefix="trill-notes-crash-") as folder:
        state = Path(folder)
        with bootstrap.launched(binary_dir, state) as (session, parent, path, app):
            offer, effect, live_recovery = bootstrap.receive_offer(parent)
            target = offer["target"]
            bootstrap.acknowledge(parent, offer, "attached")
            deadline = time.monotonic() + 12
            while True:
                snapshot = bootstrap.roundtrip(path, {"type": "snapshot"})
                if snapshot["tasks"][0]["ui_first_frame_unix_ms"] is not None:
                    break
                require(time.monotonic() < deadline, "Notes layout deadline")
                time.sleep(0.025)
            children = bootstrap.owned_children(session, app)
            require(len(children) == 1, "expected one owned Notes application")
            pid, identity = next(iter(children.items()))
            request = {"schema_version": 1, "action": "replace_note", "target": target,
                       "destination_id": offer["destination_id"],
                       "operation_id": "isolated-app-crash-original-operation",
                       "expected_revision": 0, "text": "实际窗口 · 丢回复 · 进程崩溃后的独立回读"}
            raw = encode(request)
            digest = hashlib.sha256(raw).hexdigest()
            effect.sendall(struct.pack(">I", len(raw)) + raw)
            # Do not read any effect response. Close this lane immediately;
            # the independent recovery path is the only later observation.
            effect.close()
            live_recovery.close()
            document = state / (
                f"{target['session_instance']}-{target['task_id']}-{target['incarnation']}"
            ) / "document.json"
            deadline = time.monotonic() + 6
            while True:
                try:
                    saved = json.loads(document.read_bytes())
                    if saved["revision"] == 1 and saved["pending_receipt"] is not None:
                        break
                except (FileNotFoundError, json.JSONDecodeError):
                    pass
                require(time.monotonic() < deadline, "actual application did not persist effect")
                time.sleep(0.01)
            require(bootstrap.child_identity(pid) == identity, "owned child identity changed")
            os.kill(pid, signal.SIGKILL)
            deadline = time.monotonic() + 5
            while True:
                require(time.monotonic() < deadline, "killed app was not reaped")
                ended = bootstrap.roundtrip(path, {"type": "snapshot"})
                if ended["tasks"][0]["state"] in ("failed", "completed", "cancelled"):
                    require(bootstrap.child_identity(pid) != identity, "terminal task still has its live child")
                    break
                time.sleep(0.025)

            query = {"schema_version": 1, "action": "observe", "target": target,
                     "operation_id": request["operation_id"], "payload_sha256": digest}
            with recovery_process(helper, state, target) as (channel, proc):
                try:
                    receipt, receipt_raw = exchange(channel, query)
                except TimeoutError as error:
                    if proc.poll() is not None:
                        diagnostic = proc.stderr.read(4096).decode(errors="replace")
                        raise RuntimeError(f"recovery helper exited {proc.returncode}: {diagnostic}") from error
                    raise RuntimeError("live recovery helper did not answer the original query") from error
                require(receipt == saved["pending_receipt"], "recovered exact receipt differs")
                require(receipt["result"] == {
                    "status": "applied", "previous_revision": 0, "revision": 1,
                    "text_sha256": hashlib.sha256(request["text"].encode()).hexdigest(),
                }, "wrong effect receipt")
                channel.settimeout(0.2)
                channel.send(raw)
                try:
                    channel.recv(2049)
                except socket.timeout:
                    pass
                else:
                    raise RuntimeError("recovery process accepted a mutation")
                channel.settimeout(4)
                again, _ = exchange(channel, query)
                require(again == receipt, "forbidden replay changed the receipt")
                acknowledgement = {
                    "schema_version": 1, "action": "acknowledge_terminal", "target": target,
                    "operation_id": request["operation_id"], "payload_sha256": digest,
                    "receipt_sha256": hashlib.sha256(receipt_raw).hexdigest(),
                }
                retired, _ = exchange(channel, acknowledgement)
                require(retired["status"] == "released", "exact retirement failed")
            with recovery_process(helper, state, target) as (channel, proc):
                retired, _ = exchange(channel, acknowledgement)
                require(retired["status"] == "already_released", "retirement was not durable")
                old, _ = exchange(channel, query)
                require(old["result"] == {"status": "unknown", "current_revision": 1},
                        "retired receipt was incorrectly recreated")
            persisted = json.loads(document.read_bytes())
            require(persisted["text"] == request["text"] and persisted["revision"] == 1,
                    "recovery changed document content or revision")
            require(persisted["pending_receipt"] is None, "retired receipt is still pending")
            result = {"passed": True, "app_sigkill": True, "effect_response_read": False,
                      "effect_dispatches": 1, "document_revision": 1,
                      "independent_recovery_processes": 2, "exact_retirement_durable": True,
                      "recovery_effect_replay": False, "production_authority": False,
                      "original_writer_terminal": False, "compositor_pixels": False,
                      "binary_sha256": {name: hashlib.sha256((binary_dir / name).read_bytes()).hexdigest()
                                        for name in ("trill-session", "trill-app-window", "trill-notes-recovery")}}
            print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    check(sys.argv[1])
