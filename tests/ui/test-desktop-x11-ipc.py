#!/usr/bin/env python3
"""Real private Xvfb + stock X11 applications, never the user's display.

This harness is a transport fixture, not a Hepta issuer or durable writer.
Original-owner authorization is separately verified in the Hepta repository.
"""
import array
import ctypes
import hashlib
import json
import os
from pathlib import Path
import select
import signal
import socket
import struct
import subprocess
import sys
import tempfile
import time


def check(value, message):
    if not value:
        raise AssertionError(message)


def raw(value):
    return json.dumps(value, separators=(",", ":")).encode()


def digest(value):
    return hashlib.sha256(value).hexdigest()


def exact(channel, count):
    value = bytearray()
    while len(value) < count:
        part = channel.recv(count-len(value))
        check(part, "private channel EOF")
        value.extend(part)
    return bytes(value)


def exchange(channel, payload, limit=2048):
    channel.sendall(struct.pack("!I", len(payload))+payload)
    size = struct.unpack("!I", exact(channel, 4))[0]
    check(0 < size <= limit, "response byte bound")
    return exact(channel, size)


def wait_until(predicate, message, seconds=5):
    deadline = time.monotonic()+seconds
    while time.monotonic() < deadline:
        found = predicate()
        if found:
            return found
        time.sleep(0.025)
    raise AssertionError(message)


def main():
    binary = Path(sys.argv[1]).resolve()
    output = Path(sys.argv[2]).resolve()
    output.mkdir(parents=True, exist_ok=False)
    owned = []
    channels = []
    files = []
    steps = []
    result = {"scope": "private Xvfb real third-party applications; transport fixture, no Hepta authority", "production_authority_qualified": False,
              "binary_sha256": digest(binary.read_bytes()), "steps": steps}
    xlib = ctypes.CDLL("libX11.so.6")
    xlib.XOpenDisplay.argtypes = [ctypes.c_char_p]
    xlib.XOpenDisplay.restype = ctypes.c_void_p
    xlib.XSetInputFocus.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
    xlib.XFlush.argtypes = [ctypes.c_void_p]
    xlib.XSync.argtypes = [ctypes.c_void_p, ctypes.c_int]
    xlib.XKeysymToKeycode.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    xlib.XKeysymToKeycode.restype = ctypes.c_ubyte
    xlib.XUnmapWindow.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    xlib.XMapWindow.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    xlib.XMoveWindow.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_int]
    xlib.XCloseDisplay.argtypes = [ctypes.c_void_p]
    display = None
    def spawn(args, name, **kwargs):
        log = (output/name).open("wb")
        files.append(log)
        child = subprocess.Popen(args, stdout=log, stderr=subprocess.STDOUT, start_new_session=True, **kwargs)
        owned.append(child)
        return child
    try:
        with tempfile.TemporaryDirectory(prefix="dx-") as temp:
            fixture = Path(temp)
            result["temporary_storage"] = {"path": temp, "device": fixture.stat().st_dev}
            cookie = os.urandom(16)
            cookie_path = fixture/"cookie"
            cookie_path.write_bytes(cookie)
            cookie_path.chmod(0o600)
            auth_path = fixture/"Xauthority"
            def authority(display_number):
                # Standard Xauthority record with FamilyWild. The server uses
                # the cookie; clients receive the actual selected display id.
                fields = [b"", str(display_number).encode() if display_number is not None else b"", b"MIT-MAGIC-COOKIE-1", cookie]
                auth_path.write_bytes(struct.pack("!H", 65535)+b"".join(struct.pack("!H", len(field))+field for field in fields))
                auth_path.chmod(0o600)
            authority(None)
            rfd, wfd = os.pipe()
            server = spawn(["Xvfb", "-displayfd", str(wfd), "-screen", "0", "1280x900x24", "-nolisten", "tcp", "-auth", str(auth_path)], "xvfb.log", pass_fds=(wfd,))
            os.close(wfd)
            check(select.select([rfd], [], [], 5)[0], "Xvfb display readiness")
            number = int(os.read(rfd, 64).strip())
            os.close(rfd)
            authority(number)
            display_name = f":{number}"
            env = dict(os.environ, DISPLAY=display_name, XAUTHORITY=str(auth_path))
            env.pop("WAYLAND_DISPLAY", None)
            os.environ["XAUTHORITY"] = str(auth_path)
            display = xlib.XOpenDisplay(display_name.encode())
            check(display, "open owned Xvfb")
            result["x11_authentication"] = "MIT-MAGIC-COOKIE-1; private fixture cookie, exact server PID/UID"
            def focus(window):
                xlib.XSetInputFocus(display, window, 1, 0)
                xlib.XSync(display, 0)
            def find_window(name):
                def search():
                    p = subprocess.run(["xdotool", "search", "--onlyvisible", "--name", name], env=env, capture_output=True, timeout=2)
                    values = p.stdout.splitlines()
                    return int(values[0]) if values else None
                return wait_until(search, f"window {name}")
            def attach(window, tag):
                runtime = fixture/tag
                runtime.mkdir(mode=0o700)
                local_env = dict(env, XDG_RUNTIME_DIR=str(runtime))
                parent, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_DGRAM)
                x11 = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                x11.connect(f"/tmp/.X11-unix/X{number}")
                with cookie_path.open("rb") as cookie_file:
                    proc = spawn([str(binary), "--desktop-bootstrap-stdin", "--desktop-x11-fd", str(x11.fileno()), "--desktop-x11-cookie-fd", str(cookie_file.fileno()), "--desktop-x11-server-pid", str(server.pid), "--desktop-window", str(window)], f"{tag}.log", stdin=child, pass_fds=(x11.fileno(), cookie_file.fileno()), env=local_env)
                child.close()
                x11.close()
                parent.settimeout(4)
                offer_raw, control, flags, _ = parent.recvmsg(1025, socket.CMSG_SPACE(8), socket.MSG_CMSG_CLOEXEC)
                check(not flags & (socket.MSG_TRUNC | socket.MSG_CTRUNC), "bootstrap truncation")
                fds = []
                for level, kind, data in control:
                    check(level == socket.SOL_SOCKET and kind == socket.SCM_RIGHTS, "bootstrap rights only")
                    values = array.array("i")
                    values.frombytes(data)
                    fds.extend(values)
                check(len(fds) == 2, "exact effect,observe descriptors")
                endpoints = [socket.socket(fileno=fd) for fd in fds]
                channels.extend(endpoints)
                for endpoint in endpoints:
                    endpoint.settimeout(3)
                    check(endpoint.type == socket.SOCK_STREAM and endpoint.getsockname() == "" and endpoint.getpeername() == "", "private STREAM capability")
                offer = json.loads(offer_raw)
                check(offer["profile"] == "trill.desktop.x11.v1" and offer["expected_window"] == window, "bootstrap profile")
                parent.send(raw({"schema_version": 1, "profile": offer["profile"], "target": offer["target"], "status": "attached"}))
                parent.close()
                (output/f"{tag}-offer.json").write_bytes(offer_raw)
                return proc, endpoints[0], endpoints[1], offer, runtime
            def request(offer, name, sequence, events, window=None):
                return raw({"schema_version": 1, "action": "input", "operation_id": name, "destination_id": offer["destination_id"], "target": offer["target"], "expected_sequence": sequence, "expected_window": offer["expected_window"] if window is None else window, "events": events})
            def keys(code):
                return [{"kind": "key", "keycode": code, "pressed": True}, {"kind": "key", "keycode": code, "pressed": False}]
            def observe(endpoint, offer, name, payload):
                return exchange(endpoint, raw({"schema_version": 1, "action": "observe", "target": offer["target"], "operation_id": name, "payload_sha256": digest(payload)}))
            def capture(endpoint, offer, name):
                value = json.loads(exchange(endpoint, raw({"schema_version": 1, "action": "capture", "target": offer["target"], "request_id": "4"*32}), 8*1024*1024))
                check(value["target"] == offer["target"] and value["window_id"] == offer["expected_window"] and value["pixel_format"] == "rgb8", "capture identity")
                pixels = bytes.fromhex(value.pop("pixels_hex"))
                check(0 < value["width"] <= 1024 and 0 < value["height"] <= 768 and len(pixels) == value["width"]*value["height"]*3, "capture dimensions")
                check(digest(pixels) == value["sha256"], "capture exact pixel digest")
                from PIL import Image
                Image.frombytes("RGB", (value["width"], value["height"]), pixels).save(output/f"{name}.png")
                (output/f"{name}.json").write_text(json.dumps(value, indent=2)+"\n")
                return value
            app = spawn(["xev", "-name", "OrganInputProbe", "-geometry", "300x200+10+10", "-event", "keyboard", "-event", "button"], "xev.log", env=env)
            window = find_window("^OrganInputProbe$")
            focus(window)
            session, effect, observation, offer, runtime = attach(window, "session-input")
            capture(observation, offer, "xev-before")
            steps.append("real bounded XGetImage capture with independent SHA256")
            code = int(xlib.XKeysymToKeycode(display, ord("a")))
            bad = request(offer, "wrong-window", 0, keys(code), window+1)
            check(json.loads(exchange(effect, bad))["result"]["reason"] == "target_mismatch", "wrong window refusal")
            focus(1)  # PointerRoot, not the selected application.
            bad = request(offer, "wrong-focus", 0, keys(code))
            check(json.loads(exchange(effect, bad))["result"]["reason"] == "focus_mismatch", "changed focus refusal")
            focus(window)
            xlib.XUnmapWindow(display, window)
            xlib.XSync(display, 0)
            bad = request(offer, "unmapped-window", 0, keys(code))
            check(json.loads(exchange(effect, bad))["result"]["reason"] == "window_unavailable", "unmapped target refusal")
            xlib.XMapWindow(display, window)
            focus(window)
            steps.append("wrong window, changed focus, unmapped target refuse before injection")
            first = request(offer, "key-a", 0, keys(code))
            receipt = exchange(effect, first)
            check(json.loads(receipt)["result"] == {"status": "injected", "effect_semantics": "x11_server_injected", "previous_sequence": 0, "sequence": 1}, "input server receipt")
            wait_until(lambda: "KeyPress event" in (output/"xev.log").read_text(), "third-party key event")
            before = (output/"xev.log").read_text().count("KeyPress event")
            check(exchange(effect, first) == receipt, "exact duplicate receipt")
            time.sleep(0.15)
            check((output/"xev.log").read_text().count("KeyPress event") == before, "duplicate must not inject")
            check(observe(observation, offer, "key-a", first) == receipt, "independent exact receipt")
            steps.append("real third-party key event, exact deduplication, independent receipt")
            conflict = request(offer, "key-a", 1, keys(code))
            check(json.loads(exchange(effect, conflict))["result"]["reason"] == "operation_conflict", "operation identity reuse refusal")
            conflict = request(offer, "stale-sequence", 0, keys(code))
            check(json.loads(exchange(effect, conflict))["result"]["reason"] == "sequence_conflict", "sequence CAS refusal")
            pointer = request(offer, "pointer-click", 1, [{"kind": "pointer_move", "x": 60, "y": 60}, {"kind": "pointer_button", "button": 1, "pressed": True}, {"kind": "pointer_button", "button": 1, "pressed": False}])
            check(json.loads(exchange(effect, pointer))["result"]["sequence"] == 2, "pointer injection")
            wait_until(lambda: "ButtonPress event" in (output/"xev.log").read_text(), "third-party pointer event")
            steps.append("operation/sequence fences and real third-party pointer event")
            unknown = request(offer, "never-seen", 2, keys(code))
            check(json.loads(observe(observation, offer, "never-seen", unknown))["result"]["status"] == "unknown", "cache absence stays unknown")
            lost = request(offer, "lost-ack", 2, keys(code))
            effect.sendall(struct.pack("!I", len(lost))+lost)
            effect.close()
            recovered = wait_until(lambda: (lambda r: r if json.loads(r)["result"]["status"] == "injected" else None)(observe(observation, offer, "lost-ack", lost)), "lost reply independent recovery")
            check(json.loads(recovered)["result"]["sequence"] == 3, "lost reply original sequence")
            check(capture(observation, offer, "xev-after")["input_sequence"] == 3, "independent sequence observation")
            steps.append("lost ACK reconciles original receipt without effect replay")
            # Fill the public Session request slots with slow frames. Its own
            # main loop must expire the complete frames and answer a valid peer.
            slow = []
            sockpath = runtime/"trillionnium-ui/session.sock"
            for _ in range(32):
                peer = socket.socket(socket.AF_UNIX)
                peer.settimeout(2)
                peer.connect(str(sockpath))
                peer.sendall(b'{')
                slow.append(peer)
            started = time.monotonic()
            peer = socket.socket(socket.AF_UNIX)
            peer.settimeout(2)
            peer.connect(str(sockpath))
            peer.sendall(b'{"type":"snapshot"}\n')
            snapshot = bytearray()
            while not snapshot.endswith(b'\n'):
                part = peer.recv(65536)
                check(part, "Session snapshot EOF")
                snapshot.extend(part)
            check(json.loads(snapshot)["session_instance"] == offer["target"]["session_instance"] and time.monotonic()-started < 1.5, "Session fair slow-peer progress")
            peer.close()
            for peer in slow:
                peer.close()
            steps.append("Session remains responsive under 32 slow public peers")
            # A stock application handles Return and reports its own selected
            # button exit code. This is separate app evidence, not a meaning
            # inferred from the adapter's server-injection receipt.
            message = spawn(["xmessage", "-name", "OrganMessage", "-buttons", "Done:7", "-default", "Done", "-geometry", "320x120+400+40", "Original third-party application"], "xmessage.log", env=env)
            message_window = find_window("^OrganMessage$")
            focus(message_window)
            _, message_effect, message_observe, message_offer, _ = attach(message_window, "session-message")
            capture(message_observe, message_offer, "xmessage-before")
            enter = int(xlib.XKeysymToKeycode(display, 0xff0d))
            message_raw = request(message_offer, "third-party-return", 0, keys(enter))
            message_receipt = exchange(message_effect, message_raw)
            check(json.loads(message_receipt)["result"]["status"] == "injected", "third-party submission")
            check(message.wait(timeout=3) == 7, "stock application independently processed Return")
            destroyed = request(message_offer, "destroyed-window", 1, keys(enter))
            check(json.loads(exchange(message_effect, destroyed))["result"]["reason"] == "window_unavailable", "destroyed window cannot be reused")
            steps.append("stock xmessage processes input; destroyed window permanently fenced")
            # Reattachment has a fresh identity and cannot manufacture the old
            # process's receipt from pixels or current sequence.
            focus(window)
            _, reopened_effect, reopened_observe, reopened_offer, _ = attach(window, "session-reopened")
            check(reopened_offer["target"] != offer["target"], "fresh attachment identity")
            old_query = raw({"schema_version": 1, "action": "observe", "target": offer["target"], "operation_id": "lost-ack", "payload_sha256": digest(lost)})
            check(json.loads(exchange(reopened_observe, old_query))["result"]["status"] == "unknown", "new adapter cannot know old receipt")
            steps.append("fresh identity cannot convert missing old history to success or absence")
            focus(1)
            for i in range(128):
                refused = request(reopened_offer, f"bounded-cache-{i}", 0, keys(code))
                check(json.loads(exchange(reopened_effect, refused))["result"]["reason"] == "focus_mismatch", "preflight cache fixture")
            focus(window)
            refused = request(reopened_offer, "bounded-cache-full", 0, keys(code))
            check(json.loads(exchange(reopened_effect, refused))["result"]["reason"] == "receipt_capacity", "bounded receipt cache never evicts into redispatch")
            steps.append("128-receipt capacity refuses new input without evicting prior evidence")
            large = spawn(["xev", "-name", "OrganLargeProbe", "-geometry", "1030x770+0+0", "-event", "keyboard"], "xev-large.log", env=env)
            large_window = find_window("^OrganLargeProbe$")
            focus(large_window)
            _, _, large_observe, large_offer, _ = attach(large_window, "session-large")
            try:
                capture(large_observe, large_offer, "oversized-must-not-exist")
            except AssertionError as error:
                check(str(error) == "private channel EOF", "oversized capture must fail closed")
            else:
                raise AssertionError("oversized capture accepted")
            steps.append("oversized native capture closes lane before returning unbounded pixels")
            large.terminate()
            large.wait(timeout=2)
            focus(window)
            _, flood_effect, _, flood_offer, _ = attach(window, "session-event-flood")
            for i in range(300):
                xlib.XMoveWindow(display, window, 10+i % 2, 10)
            xlib.XSync(display, 0)
            for i in range(2):
                flooded_raw = request(flood_offer, f"event-flood-{i}", 0, keys(code))
                check(json.loads(exchange(flood_effect, flooded_raw))["result"]["reason"] == "window_unavailable", "event backlog cannot hide destroyed/reused identity")
            steps.append("structure-event overflow permanently refuses input instead of skipping lifecycle evidence")
            _, stalled_effect, stalled_observe, stalled_offer, _ = attach(window, "session-stalled")
            stalled_raw = request(stalled_offer, "stalled-server", 0, keys(code))
            started = time.monotonic()
            os.kill(server.pid, signal.SIGSTOP)
            try:
                stalled_receipt = exchange(stalled_effect, stalled_raw)
                check(json.loads(stalled_receipt)["result"]["status"] == "unknown" and time.monotonic()-started < 1.5, "native total deadline and unknown")
            finally:
                os.kill(server.pid, signal.SIGCONT)
            check(observe(stalled_observe, stalled_offer, "stalled-server", stalled_raw) == stalled_receipt, "unknown retained without reconnect or replay")
            next_raw = request(stalled_offer, "after-stalled-server", 0, keys(code))
            check(json.loads(exchange(stalled_effect, next_raw))["result"]["status"] == "unknown", "native uncertainty permanently disables further input")
            steps.append("frozen X server bounded by native deadline; unknown never reconnects or retries")
            result["status"] = "passed"
            result["first_target"] = offer["target"]
            result["reopened_target"] = reopened_offer["target"]
            result["third_party_exit_code"] = 7
            result["exact_receipt_sha256"] = digest(receipt)
    except BaseException as error:
        result["status"] = "failed"
        result["error"] = repr(error)
        raise
    finally:
        result["binary_sha256_after"] = digest(binary.read_bytes())
        (output/"result.json").write_text(json.dumps(result, indent=2)+"\n")
        if display:
            xlib.XCloseDisplay(display)
        for channel in channels:
            channel.close()
        for child in reversed(owned):
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGTERM)
            try:
                child.wait(timeout=2)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait(timeout=2)
        for file in files:
            file.close()
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
