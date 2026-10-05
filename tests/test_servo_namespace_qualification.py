"""Source decoder/contract regressions, never native or installed evidence.

Actual no-skip systemd/Rust entry cases run through the separate explicit
kernel-fixture CLI. The permanent native CI runs the real pinned Servo binary.
"""
from __future__ import annotations

import copy
import fcntl
import gc
import hashlib
import json
import os
from pathlib import Path
import select
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

from tools import servo_namespace_qualification as gate
from tools import check_servo_resource_gate as resource
from test_servo_resource_gate import source_only_fixture


def source_binding_fixture():
    """Invented verifier inputs. No Linux process was observed by this helper."""
    binary = {"device": 7, "inode": 77}
    unit = "hepta-netns-" + "a" * 32 + ".service"
    fds = [{"fd": fd, "device": 7, "inode": 100 + fd, "kind": "pipe", "socket_domain": None} for fd in range(3)]
    host = {"schema": "trillionnium.desktop.netns-host-observation.v1", "unit": unit,
        "control_group": "/system.slice/" + unit, "main_pid": 4242, "role": "embedder",
        "identity": {"pid": 4242, "ppid": 1, "pgid": 4242, "session": 4242, "start_time": 12345, "state": "T"},
        "executable_identity": binary, "network_namespace_inode": 222, "outside_network_namespace_inode": 111,
        "caps": {"CapEff": "0000000000000000", "CapBnd": "0000000000000000", "CapAmb": "0000000000000000"},
        "no_new_privileges": 1, "seccomp": 2, "unit_properties": dict(gate.PROPERTIES), "descriptor_inventory": fds,
        "renderer_uid": 1000, "renderer_gid": 1000, "read_write_paths": "/source-fixture/kernel-fixture/renderer /tmp/hn-" + "a" * 24,
        "temporary_directory": {"path": "/tmp/hn-" + "a" * 24, "device": 7, "inode": 88, "uid": 1000, "mode": 0o700},
        "pidfd_retained": True, "entry_stopped": True, "content_argument_observed": False,
        "source_qualification_only": True, "installed_qualified": False, "production_ready": False}
    entry = {"schema": "trillionnium.desktop.netns-entry.v1", "profile": gate.PROFILE, "role": "embedder",
        "pid": 4242, "start_time": 12345, "network_namespace_inode": 222, "cap_effective": 0, "cap_bounding": 0,
        "cap_ambient": 0, "no_new_privileges": True, "seccomp_filter_observed": True,
        "tcp_ipv4_errno": 97, "udp_ipv4_errno": 97, "tcp_ipv6_errno": 97, "udp_ipv6_errno": 97,
        "unix_payload_roundtrip": True, "descriptor_inventory": [{key: value for key, value in item.items()
            if key != "socket_domain"} for item in fds], "entry_stop_requested": True,
        "source_qualification_only": True, "installed_qualified": False, "production_ready": False}
    return entry, host, binary


class PrivateTemporaryDirectoryTests(unittest.TestCase):
    """Actual private files/Unix sockets; these tests do not execute Servo."""
    def test_real_short_directory_tempfile_and_unix_socket_cleanup(self):
        previous = os.umask(0o077)
        owner = gate._PrivateTemporaryDirectory()
        path = owner.path
        try:
            self.assertEqual(len(str(path).encode()), 32)
            self.assertEqual(owner.verify()["mode"], 0o700)
            with tempfile.TemporaryDirectory(dir=path) as nested:
                socket_path = str(Path(nested) / "socket")
                self.assertLess(len(socket_path.encode()), 108)
                listener = socket.socket(socket.AF_UNIX); client = socket.socket(socket.AF_UNIX)
                try:
                    listener.bind(socket_path); listener.listen(1)
                    client.connect(socket_path); accepted, _ = listener.accept()
                    with accepted:
                        client.sendall(b"actual-private-ipc"); self.assertEqual(accepted.recv(32), b"actual-private-ipc")
                finally:
                    listener.close(); client.close()
            (path / "cache.sqlite3").write_bytes(b"owned cache bytes")
            owner.close(remove=True)
            self.assertFalse(path.exists())
        finally:
            if owner.root is not None: owner.close(remove=True)
            os.umask(previous)

    def test_replaced_named_directory_preserves_foreign_inode_and_bytes(self):
        owner = gate._PrivateTemporaryDirectory(); path = owner.path
        saved = path.with_name(path.name + "-saved")
        try:
            path.rename(saved); path.mkdir(mode=0o700); foreign = path / "foreign"; foreign.write_bytes(b"foreign")
            inode = foreign.stat().st_ino
            with self.assertRaisesRegex(ValueError, "pathname changed"): owner.close(remove=True)
            self.assertEqual((foreign.stat().st_ino, foreign.read_bytes()), (inode, b"foreign"))
        finally:
            (path / "foreign").unlink(); path.rmdir(); saved.rmdir()

    def test_actual_abandoned_nested_cache_and_unix_socket_are_retired(self):
        previous = os.umask(0o077); owner = gate._PrivateTemporaryDirectory(); path = owner.path
        try:
            nested = path / ".tmpActual"; nested.mkdir(mode=0o700)
            (nested / "cache.sqlite3").write_bytes(b"abandoned private cache")
            endpoint = socket.socket(socket.AF_UNIX)
            try: endpoint.bind(str(nested / "socket"))
            finally: endpoint.close()
            self.assertTrue((nested / "socket").is_socket())
            owner.close(remove=True)
            self.assertFalse(path.exists())
        finally:
            if owner.root is not None: owner.close(remove=True)
            os.umask(previous)

    def test_foreign_symlink_child_refuses_cleanup_without_deleting_target(self):
        owner = gate._PrivateTemporaryDirectory(); path = owner.path
        with tempfile.TemporaryDirectory() as external:
            target = Path(external) / "target"; target.write_bytes(b"outside")
            inode = target.stat().st_ino; (path / "foreign-link").symlink_to(target)
            with self.assertRaisesRegex(ValueError, "foreign or unsafe"): owner.close(remove=True)
            self.assertTrue((path / "foreign-link").is_symlink())
            self.assertEqual((target.stat().st_ino, target.read_bytes()), (inode, b"outside"))
            (path / "foreign-link").unlink(); path.rmdir()

    def test_hardlinked_child_is_preserved_and_never_repaired(self):
        previous = os.umask(0o077); owner = gate._PrivateTemporaryDirectory(); path = owner.path
        try:
            leaf = path / "first"; leaf.write_bytes(b"aliased"); os.link(leaf, path / "second")
            with self.assertRaisesRegex(ValueError, "aliased"): owner.close(remove=True)
            self.assertEqual(leaf.stat().st_nlink, 2)
        finally:
            (path / "second").unlink(); (path / "first").unlink(); path.rmdir(); os.umask(previous)

    def test_changed_directory_permissions_refuse_without_repair(self):
        owner = gate._PrivateTemporaryDirectory(); path = owner.path
        try:
            path.chmod(0o775)
            with self.assertRaises(ValueError): owner.close(remove=True)
            self.assertEqual(path.stat().st_mode & 0o777, 0o775)
        finally:
            path.chmod(0o700); path.rmdir()

    def test_actual_fork_refuses_before_unlink_and_parent_retains_descriptor(self):
        owner = gate._PrivateTemporaryDirectory(); path = owner.path
        (path / "owned").write_bytes(b"parent")
        read, write = os.pipe(); child = os.fork()
        if child == 0:
            os.close(read)
            try: owner.close(remove=True)
            except ValueError:
                os.write(write, b"refused"); os._exit(0)
            os._exit(2)
        os.close(write)
        try:
            self.assertTrue(select.select([read], [], [], 3)[0])
            self.assertEqual(os.read(read, 32), b"refused"); self.assertEqual(os.waitpid(child, 0)[1], 0)
            self.assertEqual((path / "owned").read_bytes(), b"parent"); owner.verify()
        finally:
            os.close(read); (path / "owned").unlink(); owner.close(remove=True)

    def test_actual_leaf_substitution_during_complete_scan_preserves_foreign_file(self):
        previous = os.umask(0o077); owner = gate._PrivateTemporaryDirectory(); path = owner.path
        leaf = path / "cache.sqlite3"; leaf.write_bytes(b"original")
        real_stat = os.stat; replaced = False
        def substitute(name, *args, **kwargs):
            nonlocal replaced
            if name == "cache.sqlite3" and not replaced:
                replaced = True; leaf.unlink(); leaf.write_bytes(b"foreign")
            return real_stat(name, *args, **kwargs)
        try:
            with mock.patch.object(gate.os, "stat", side_effect=substitute):
                with self.assertRaisesRegex(ValueError, "name changed"): owner.close(remove=True)
            self.assertTrue(replaced); self.assertEqual(leaf.read_bytes(), b"foreign")
        finally:
            leaf.unlink(); path.rmdir(); os.umask(previous)

    def test_gc_retires_descriptors_without_removing_path(self):
        owner = gate._PrivateTemporaryDirectory(); path = owner.path; descriptor = owner.root.fd
        del owner; gc.collect()
        try:
            with self.assertRaises(OSError): os.fstat(descriptor)
            self.assertTrue(path.is_dir())
        finally: path.rmdir()

    def test_closed_temporary_metadata_alias_or_extra_writable_path_fails(self):
        for field, value in (("mode", 448.0), ("inode", True), ("uid", 1000.0), ("path", "/tmp"), ("path", "/tmp/hn-" + "a" * 100)):
            entry, host, binary = source_binding_fixture(); host["temporary_directory"][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                gate.validate_binding(entry, host, binary, 111, 4242, renderer_path="/source-fixture/kernel-fixture/renderer")
        entry, host, binary = source_binding_fixture(); host["read_write_paths"] += " /tmp"
        with self.assertRaises(ValueError): gate.validate_binding(entry, host, binary, 111, 4242)

    def test_actual_entry_size_and_depth_bounds_refuse_before_deleting_contents(self):
        for limit in ("entries", "bytes", "depth"):
            previous = os.umask(0o077); owner = gate._PrivateTemporaryDirectory(); path = owner.path
            try:
                if limit == "entries":
                    for index in range(owner.MAX_ENTRIES + 1): (path / str(index)).touch(mode=0o600)
                elif limit == "bytes":
                    with (path / "sparse-cache").open("xb") as stream: stream.truncate(owner.MAX_BYTES + 1)
                else:
                    parent = path
                    for index in range(owner.MAX_DEPTH): parent = parent / str(index); parent.mkdir(mode=0o700)
                    (parent / "cache").write_bytes(b"retained")
                before = sorted(str(item.relative_to(path)) for item in path.rglob("*"))
                with self.subTest(limit=limit), self.assertRaisesRegex(ValueError, "bound exceeded|depth exceeded"):
                    owner.close(remove=True)
                self.assertEqual(before, sorted(str(item.relative_to(path)) for item in path.rglob("*")))
            finally:
                for item in sorted(path.rglob("*"), key=lambda item: len(item.parts), reverse=True):
                    if item.is_dir(): item.rmdir()
                    else: item.unlink()
                path.rmdir(); os.umask(previous)


class LazyTemporaryEnumerationTests(unittest.TestCase):
    """Real private names and iterator FDs; injected cuts are host source tests."""
    def test_actual_4096_names_stop_at_257_before_unlink_without_fd_leak(self):
        real_scandir = os.scandir
        def inventory():
            values = {}
            for name in os.listdir("/proc/self/fd"):
                try:
                    metadata = os.fstat(int(name)); values[name] = (metadata.st_dev, metadata.st_ino)
                except OSError: pass
            return values
        previous = os.umask(0o077); before = inventory()
        owner = gate._PrivateTemporaryDirectory(); path = owner.path
        for index in range(4096): (path / str(index)).touch(mode=0o600)
        observers = []
        class ObservedIterator:
            def __init__(self, descriptor):
                self.native = real_scandir(descriptor); self.names = 0; self.closed = False; observers.append(self)
            def __enter__(self): return self
            def __exit__(self, *args): self.native.close(); self.closed = True
            def __next__(self):
                value = next(self.native); self.names += 1; return value
        try:
            with mock.patch.object(gate.os, "scandir", side_effect=ObservedIterator):
                with self.assertRaisesRegex(ValueError, "entry bound exceeded"): owner.close(remove=True)
            self.assertEqual(sum(item.names for item in observers), 257)
            self.assertTrue(all(item.closed for item in observers))
            self.assertEqual(len(os.listdir(path)), 4096)
            self.assertEqual(inventory(), before)
        finally:
            for name in os.listdir(path): (path / name).unlink()
            path.rmdir(); os.umask(previous)

    def test_actual_nested_count_is_global_and_rejects_before_any_deletion(self):
        previous = os.umask(0o077); owner = gate._PrivateTemporaryDirectory(); path = owner.path
        for directory in (path / "first", path / "second"):
            directory.mkdir(mode=0o700)
            for index in range(128): (directory / str(index)).touch(mode=0o600)
        before = sorted(str(item.relative_to(path)) for item in path.rglob("*"))
        try:
            with self.assertRaisesRegex(ValueError, "entry bound exceeded"): owner.close(remove=True)
            self.assertEqual(before, sorted(str(item.relative_to(path)) for item in path.rglob("*")))
        finally:
            for directory in (path / "first", path / "second"):
                for child in directory.iterdir(): child.unlink()
                directory.rmdir()
            path.rmdir(); os.umask(previous)

    def test_real_late_empty_iterator_and_interrupt_close_fds_and_preserve_names(self):
        real_scandir = os.scandir
        for cut in ("late-eof", "interrupted-next", "late-foreign"):
            previous = os.umask(0o077); owner = gate._PrivateTemporaryDirectory(); path = owner.path
            if cut == "interrupted-next": (path / "owned").write_bytes(b"not deleted")
            descriptors = set(os.listdir("/proc/self/fd")); elapsed = [0.0]; calls = [0]; iterators = []
            class CutIterator:
                def __init__(self, descriptor):
                    calls[0] += 1
                    if cut == "late-foreign" and calls[0] == 2: (path / "foreign").write_bytes(b"preserved")
                    self.native = real_scandir(descriptor); self.closed = False; self.names = 0; iterators.append(self)
                def __enter__(self): return self
                def __exit__(self, *args): self.native.close(); self.closed = True
                def __next__(self):
                    if cut == "interrupted-next": raise KeyboardInterrupt("actual iterator owns an FD")
                    try:
                        item = next(self.native); self.names += 1; return item
                    except StopIteration:
                        if cut == "late-eof": elapsed[0] = 6.0
                        raise
            try:
                with mock.patch.object(gate.os, "scandir", side_effect=CutIterator), \
                        mock.patch.object(gate.time, "monotonic", side_effect=lambda: elapsed[0]):
                    with self.assertRaises(KeyboardInterrupt if cut == "interrupted-next" else ValueError):
                        owner.close(remove=True)
                self.assertTrue(all(item.closed for item in iterators))
                self.assertEqual(sum(item.names for item in iterators), 1 if cut == "late-foreign" else 0)
                self.assertTrue(path.is_dir())
                if cut == "late-foreign": self.assertEqual((path / "foreign").read_bytes(), b"preserved")
                if cut == "interrupted-next": self.assertEqual((path / "owned").read_bytes(), b"not deleted")
                # The temporary owner's descriptors retired as well as the iterators.
                self.assertLess(len(set(os.listdir("/proc/self/fd"))), len(descriptors))
            finally:
                for name in os.listdir(path): (path / name).unlink()
                path.rmdir(); os.umask(previous)


    def test_actual_final_rmdir_effect_after_deadline_refuses_success_without_rollback(self):
        owner = gate._PrivateTemporaryDirectory(); path = owner.path
        real_rmdir = os.rmdir; elapsed = [0.0]; removed = []
        def after_real_effect(*args, **kwargs):
            result = real_rmdir(*args, **kwargs); elapsed[0] = 6.0; removed.append(True); return result
        with mock.patch.object(gate.os, "rmdir", side_effect=after_real_effect), \
                mock.patch.object(gate.time, "monotonic", side_effect=lambda: elapsed[0]):
            with self.assertRaisesRegex(ValueError, "expired after final removal"): owner.close(remove=True)
        self.assertEqual(removed, [True])
        self.assertFalse(path.exists())
        self.assertIsNone(owner.root)
        self.assertIsNone(owner.parent)


class OwnedCleanupTests(unittest.TestCase):
    """Real descriptor/canary cleanup; mocked unit commands are not systemd proof."""
    def test_join_interruption_still_closes_retired_real_pidfd_and_log(self):
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(.05)"])
        descriptor = os.pidfd_open(child.pid)
        child.wait(timeout=5)
        item = gate.Unit.__new__(gate.Unit)
        item.owner_pid = os.getpid()
        item._continuation_lock = threading.Lock()
        item.stop = threading.Event()
        item.unit = "hepta-netns-" + "b" * 32 + ".service"
        item.forwarder = None
        item.handles = {child.pid: descriptor}
        item.log = tempfile.TemporaryFile()
        item.thread = mock.Mock()
        item.thread.join.side_effect = KeyboardInterrupt("after observer retirement")
        item.thread.is_alive.return_value = False
        with mock.patch.object(gate, "command", return_value=""), mock.patch.object(gate.subprocess, "run",
                return_value=subprocess.CompletedProcess([], 3, "inactive\n", "")):
            with self.assertRaisesRegex(ValueError, "namespace cleanup"):
                item.close()
        self.assertTrue(item.log.closed)
        self.assertEqual(item.handles, {})
        with self.assertRaises(OSError): os.fstat(descriptor)

    def test_inherited_owner_is_rejected_before_lock_or_unit_command(self):
        item = gate.Unit.__new__(gate.Unit)
        item.owner_pid = os.getpid() + 1
        item._continuation_lock = mock.MagicMock()
        with mock.patch.object(gate, "command") as command:
            with self.assertRaisesRegex(ValueError, "inherited child"):
                item.close()
        item._continuation_lock.__enter__.assert_not_called()
        command.assert_not_called()

    def test_actual_fork_child_refuses_inherited_unit_before_held_parent_lock(self):
        item = gate.Unit.__new__(gate.Unit)
        item.owner_pid = os.getpid()
        item._continuation_lock = threading.Lock()
        item._continuation_lock.acquire()
        read_fd, write_fd = os.pipe()
        child = os.fork()
        if child == 0:
            os.close(read_fd)
            try:
                item.close()
            except ValueError:
                os.write(write_fd, b"refused")
                os._exit(0)
            except BaseException:
                os._exit(2)
            os._exit(3)
        descriptor = os.pidfd_open(child)
        os.close(write_fd)
        try:
            self.assertTrue(select.select([read_fd], [], [], 3)[0], "inherited owner reached parent's held lock")
            self.assertEqual(os.read(read_fd, 32), b"refused")
            self.assertTrue(select.select([descriptor], [], [], 3)[0])
            self.assertEqual(os.waitpid(child, 0)[1], 0)
        finally:
            if not select.select([descriptor], [], [], 0)[0]:
                signal.pidfd_send_signal(descriptor, signal.SIGKILL)
            try: os.waitpid(child, 0)
            except ChildProcessError: pass
            os.close(descriptor)
            os.close(read_fd)
            item._continuation_lock.release()

    def test_case_retirement_attempts_all_owners_after_first_exception(self):
        calls = []
        unit = mock.Mock(); unit.close.side_effect = KeyboardInterrupt("unit cleanup")
        inherited = mock.Mock(); inherited.close.side_effect = lambda: calls.append("socket")
        canary = mock.Mock(); canary.finish.side_effect = lambda: calls.append("canary") or {"source_fixture_only": True}
        def cleanup(child):
            calls.append(child)
            if child == "helper": raise OSError("helper cleanup")
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "case cleanup"):
                gate._retire_case(unit, "helper", "xvfb", {"cleanup": cleanup}, inherited, canary, Path(directory))
            self.assertTrue((Path(directory) / "outside-canary.json").is_file())
        self.assertEqual(calls, ["helper", "xvfb", "socket", "canary"])

    def test_real_canary_listeners_close_when_final_control_fails(self):
        canary = gate.Canary()
        listeners, threads = list(canary.sockets), list(canary.threads)
        with mock.patch.object(canary, "positive", side_effect=OSError("final positive control failed")):
            with self.assertRaisesRegex(OSError, "final positive"):
                canary.finish()
        self.assertTrue(all(listener.fileno() == -1 for listener in listeners))
        self.assertTrue(all(not thread.is_alive() for thread in threads))


class NamespaceBindingTests(unittest.TestCase):
    def check(self, entry, host, binary):
        gate.validate_binding(entry, host, binary, 111, 4242, renderer_identity=(1000, 1000),
                              renderer_path="/source-fixture/kernel-fixture/renderer")

    def test_closed_source_fixture_binds_exact_observations_without_production_claim(self):
        self.check(*source_binding_fixture())

    def test_source_and_host_process_namespace_binary_or_fd_substitution_is_refused(self):
        for field in ("pid", "start_time", "network_namespace_inode"):
            entry, host, binary = source_binding_fixture()
            entry[field] += 1
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.check(entry, host, binary)
        for field in ("device", "inode"):
            entry, host, binary = source_binding_fixture()
            host["executable_identity"] = {**binary, field: binary[field] + 1}
            with self.subTest(binary=field), self.assertRaises(ValueError):
                self.check(entry, host, binary)
            entry, host, binary = source_binding_fixture()
            entry["descriptor_inventory"][0][field] += 1
            with self.subTest(fd=field), self.assertRaises(ValueError):
                self.check(entry, host, binary)

    def test_boolean_float_and_zero_authority_fields_are_refused(self):
        for field in ("pid", "start_time", "network_namespace_inode", "tcp_ipv4_errno", "udp_ipv4_errno", "tcp_ipv6_errno", "udp_ipv6_errno"):
            for value in (True, 0, 1.0):
                entry, host, binary = source_binding_fixture()
                entry[field] = value
                with self.subTest(entry=field, value=value), self.assertRaises(ValueError):
                    self.check(entry, host, binary)
        for field in ("pid", "ppid", "pgid", "session", "start_time"):
            for value in (True, 1.0):
                entry, host, binary = source_binding_fixture()
                host["identity"][field] = value
                with self.subTest(identity=field, value=value), self.assertRaises(ValueError):
                    self.check(entry, host, binary)
        for field in ("renderer_uid", "renderer_gid", "no_new_privileges", "seccomp", "main_pid"):
            entry, host, binary = source_binding_fixture()
            host[field] = True
            with self.subTest(host=field), self.assertRaises(ValueError):
                self.check(entry, host, binary)
        for who in ("entry", "host"):
            for field in ("fd", "device", "inode"):
                for value in (True, 1.0):
                    entry, host, binary = source_binding_fixture()
                    target = entry if who == "entry" else host
                    target["descriptor_inventory"][0][field] = value
                    with self.subTest(who=who, field=field, value=value), self.assertRaises(ValueError):
                        self.check(entry, host, binary)

    def test_routing_refusal_or_missing_family_cannot_replace_kernel_policy(self):
        for field in ("tcp_ipv4_errno", "udp_ipv4_errno", "tcp_ipv6_errno", "udp_ipv6_errno"):
            for value in (0, 101, 110, 111):
                entry, host, binary = source_binding_fixture()
                entry[field] = value
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    self.check(entry, host, binary)

    def test_caps_nnp_seccomp_stop_or_unit_weakenings_are_refused(self):
        for field, value in (("no_new_privileges", 0), ("seccomp", 0), ("entry_stopped", False),
            ("pidfd_retained", False), ("content_argument_observed", True), ("read_write_paths", "/")):
            entry, host, binary = source_binding_fixture()
            host[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.check(entry, host, binary)
        for field in gate.PROPERTIES:
            entry, host, binary = source_binding_fixture()
            host["unit_properties"][field] = "unsupported"
            with self.subTest(property=field), self.assertRaises(ValueError):
                self.check(entry, host, binary)
        entry, host, binary = source_binding_fixture()
        host["caps"]["CapBnd"] = "0000000000000001"
        with self.assertRaises(ValueError): self.check(entry, host, binary)
        entry, host, binary = source_binding_fixture()
        host["identity"]["state"] = "R"
        with self.assertRaises(ValueError): self.check(entry, host, binary)

    def test_all_actual_host_socket_domains_must_be_unix(self):
        for family in (socket.AF_INET, socket.AF_INET6, socket.AF_NETLINK):
            entry, host, binary = source_binding_fixture()
            host["descriptor_inventory"].append({"fd": 3, "device": 10, "inode": 1003,
                "kind": "socket", "socket_domain": int(family)})
            with self.subTest(domain=family), self.assertRaises(ValueError):
                self.check(entry, host, binary)

    def test_unix_domain_is_not_an_approved_peer_or_proxy_claim(self):
        entry, host, binary = source_binding_fixture()
        host["descriptor_inventory"].append({"fd": 3, "device": 10, "inode": 1003,
            "kind": "socket", "socket_domain": 1})
        self.check(entry, host, binary)
        host["approved_unix_peer"] = True
        with self.assertRaises(ValueError): self.check(entry, host, binary)

    def test_unknown_nested_fields_or_claim_promotions_are_refused(self):
        for who, path in (("entry", ()), ("host", ()), ("host", ("identity",)),
            ("host", ("executable_identity",)), ("host", ("unit_properties",))):
            entry, host, binary = source_binding_fixture()
            target = entry if who == "entry" else host
            for field in path: target = target[field]
            target["invented"] = True
            with self.subTest(who=who, path=path), self.assertRaises(ValueError): self.check(entry, host, binary)
        for who in ("entry", "host"):
            for field in ("source_qualification_only", "installed_qualified", "production_ready"):
                entry, host, binary = source_binding_fixture()
                target = entry if who == "entry" else host
                target[field] = not target[field]
                with self.subTest(who=who, claim=field), self.assertRaises(ValueError): self.check(entry, host, binary)

    def test_content_requires_exact_native_parent_and_content_argument(self):
        entry, host, binary = source_binding_fixture()
        entry.update(role="content", pid=4243)
        host.update(role="content", content_argument_observed=True)
        host["identity"].update(pid=4243, ppid=4242)
        self.check(entry, host, binary)
        for field, value in (("ppid", 1), ("pid", 4242)):
            hostile = copy.deepcopy(host); hostile["identity"][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError): self.check(entry, hostile, binary)

    def test_inherited_negative_requires_exact_independently_duplicated_fd0(self):
        for family in (2, 10):
            entry, host, binary = source_binding_fixture()
            refusal = {key: value for key, value in entry.items() if key in gate.REFUSAL_KEYS}
            refusal.update(schema="trillionnium.desktop.netns-refusal.v1", reason="entry_descriptor_inventory_refused", engine_started=False)
            host["descriptor_inventory"][0].update(kind="socket", socket_domain=family)
            gate.validate_binding(refusal, host, binary, 111, 4242, inherited_family=family)
            for value in (True, float(family), 1, 16):
                hostile = copy.deepcopy(host); hostile["descriptor_inventory"][0]["socket_domain"] = value
                with self.subTest(domain=value), self.assertRaises(ValueError):
                    gate.validate_binding(refusal, hostile, binary, 111, 4242, inherited_family=family)

    def test_fd_duplicates_or_inventory_bounds_fail(self):
        for who in ("entry", "host"):
            for mutation in ("duplicate", "empty", "too_many"):
                entry, host, binary = source_binding_fixture(); target = entry if who == "entry" else host
                fds = target["descriptor_inventory"]
                target["descriptor_inventory"] = fds + [fds[0]] if mutation == "duplicate" else [] if mutation == "empty" else fds * 100
                with self.subTest(who=who, mutation=mutation), self.assertRaises(ValueError): self.check(entry, host, binary)


class PacketCustodyTests(unittest.TestCase):
    def setUp(self):
        previous = os.umask(0o077)
        self.addCleanup(os.umask, previous)
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.path = self.directory / "fact.json"
        self.path.write_text('{"value":1}')
        self.packet = gate.Packet(self.directory)

    def test_actual_file_rewrite_after_first_read_is_refused(self):
        self.assertEqual(self.packet.json("fact.json"), {"value": 1})
        self.path.write_text('{"value":2}')
        with self.assertRaises(ValueError): self.packet.finish()

    def test_hardlink_symlink_fifo_and_alias_ancestors_are_refused(self):
        alias = self.directory / "alias.json"; os.link(self.path, alias)
        with self.assertRaises(ValueError): self.packet.read("fact.json")
        alias.unlink(); self.path.unlink(); self.path.symlink_to("outside.json")
        with self.assertRaises((ValueError, OSError)): self.packet.read("fact.json")
        self.path.unlink(); os.mkfifo(self.path)
        with self.assertRaises((ValueError, OSError)): self.packet.read("fact.json")
        self.path.unlink(); self.path.write_text('{}')
        child = self.directory / "child"; child.mkdir(); (child / "fact.json").write_text('{}')
        link = self.directory / "linked"; link.symlink_to(child, target_is_directory=True)
        with self.assertRaises((ValueError, OSError)): gate.Packet(link).read("fact.json")

    def test_json_duplicate_nan_infinite_and_oversize_are_refused(self):
        for value in ('{"x":1,"x":2}', '{"x":NaN}', '{"x":1e999}', 'x' * 129):
            self.path.write_text(value)
            with self.subTest(value=value[:30]), self.assertRaises(ValueError):
                if len(value) == 129: self.packet.read("fact.json", 128)
                else: self.packet.json("fact.json")

    def test_actual_symlink_above_packet_root_is_refused_on_read_and_finish(self):
        actual = self.directory / "actual"
        actual.mkdir(mode=0o700)
        case = actual / "case"
        case.mkdir(mode=0o700)
        (case / "fact.json").write_text('{"value":1}')
        alias = self.directory / "alias"
        alias.symlink_to(actual, target_is_directory=True)
        with self.assertRaises((ValueError, OSError)):
            gate.Packet(alias / "case").json("fact.json")
        retained = gate.Packet(case)
        self.assertEqual(retained.json("fact.json"), {"value": 1})
        original = self.directory / "original"
        actual.rename(original)
        actual.symlink_to(original, target_is_directory=True)
        with self.assertRaises((ValueError, OSError)):
            retained.finish()

    def test_foreign_or_mutable_modes_and_bad_relative_names_fail(self):
        self.path.chmod(0o666)
        with self.assertRaises(ValueError): self.packet.read("fact.json")
        for name in ("../fact.json", "/fact.json", "x/fact.json", "fact.json\n"):
            with self.subTest(name=name), self.assertRaises(ValueError): self.packet.read(name)

    def test_recursive_receipt_match_rejects_bool_and_float_identity_aliases(self):
        for value in (True, 1.0):
            with self.assertRaises(ValueError): gate.exact_tree({"facts": [{"generation": value}]}, {"facts": [{"generation": 1}]}, "typed receipt")


class CanaryAndResourceTests(unittest.TestCase):
    def test_actual_outside_dualstack_payload_controls_are_read_back(self):
        canary = gate.Canary()
        record = canary.finish()
        gate.validate_canary(record, gate.ns_inode(os.getpid()))
        self.assertEqual(len(record["actual_connections"]), 4)

    def test_missing_ipv6_extra_connection_nonce_or_claim_is_refused(self):
        canary = gate.Canary(); source = canary.finish(); outside = source["outside_network_namespace_inode"]
        for mutation in ("ipv6", "extra", "nonce", "claim", "boolfamily", "floatfamily"):
            item = copy.deepcopy(source)
            if mutation == "ipv6": item["actual_connections"].pop()
            elif mutation == "extra": item["actual_connections"].append(item["actual_connections"][0])
            elif mutation == "nonce": item["nonce"] = "0" * 32
            elif mutation == "claim": item["production_ready"] = True
            else: item["actual_connections"][0]["family"] = True if mutation == "boolfamily" else 2.0
            with self.subTest(mutation=mutation), self.assertRaises(ValueError): gate.validate_canary(item, outside)

    def test_immutable_origin_requires_explicit_profile_and_preserves_false_ceiling(self):
        report, runtime, _ = source_only_fixture()
        report["fixture_origin"] = gate.ORIGIN
        with self.assertRaises(ValueError): resource.validate(report, runtime, gate.ORIGIN)
        resource.validate(report, runtime, gate.ORIGIN, namespace_immutable_qualification=True)
        for value in (1, "true", None):
            with self.subTest(selector=value), self.assertRaises(ValueError): resource.validate(report, runtime, gate.ORIGIN, namespace_immutable_qualification=value)
        for value in (gate.ORIGIN + ":443", gate.ORIGIN.replace("https", "http"), "https://evil.invalid", "https://fixture.netns-qualification.invalid.evil"):
            with self.subTest(origin=value), self.assertRaises(ValueError): resource.validate(report, runtime, value, namespace_immutable_qualification=True)
        report["claim_ceiling"]["network_namespace_confinement"] = True
        with self.assertRaises(ValueError): resource.validate(report, runtime, gate.ORIGIN, namespace_immutable_qualification=True)


class CompletePacketTests(unittest.TestCase):
    """A private source-input packet exercises bindings, not actual process IO."""
    def setUp(self):
        previous = os.umask(0o077); self.addCleanup(os.umask, previous)
        self.temporary = tempfile.TemporaryDirectory(); self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "kernel-fixture"; self.root.mkdir()
        self.renderer = self.root / "renderer"; self.renderer.mkdir()
        entry, host, binary = source_binding_fixture()
        self.entry, self.host = entry, host
        self.entry_name = "namespace-entry-4242-12345.json"
        self.host_name = "host-" + self.entry_name
        self.put(self.renderer / self.entry_name, entry)
        self.put(self.root / self.host_name, host)
        (self.renderer / "runtime.log").write_text("SOURCE_ONLY_DECODER_FIXTURE_NO_KERNEL_EXECUTION\n")
        nonce = "b" * 32
        controls = [{"family": family, "payload_hex": (nonce + ":" + phase).encode().hex()} for phase in ("before", "after") for family in (2, 10)]
        self.canary = {"schema": "trillionnium.desktop.netns-canary.v1", "nonce": nonce,
            "outside_network_namespace_inode": 111, "positive_controls": controls, "actual_connections": controls,
            "unexpected_connections": 0, "source_qualification_only": True, "installed_qualified": False, "production_ready": False}
        self.put(self.root / "outside-canary.json", self.canary)
        self.launch = {"schema": "trillionnium.desktop.netns-launch.v1", "case": "kernel-fixture", "unit": host["unit"],
            "main_pid": 4242, "binary_identity": binary, "binary_sha256": "c" * 64, "outside_namespace": 111,
            "renderer_uid": 1000, "renderer_gid": 1000, "renderer_path": host["read_write_paths"].split()[0],
            "temporary_directory": copy.deepcopy(host["temporary_directory"]), "temporary_directory_removed": True,
            "entries": [{"entry": self.entry_name, "host": self.host_name, "pid": 4242, "start_time": 12345, "role": "embedder"}],
            "exit_code": 0, "owned_unit_stopped": True, "exact_processes_exited": True, "qualification_nonce_enabled": False,
            "per_pair_ack_pacing": False, "source_qualification_only": True, "installed_qualified": False, "production_ready": False}
        self.put(self.root / "namespace-launch.json", self.launch)

    def put(self, path, value):
        path.write_text(json.dumps(value, allow_nan=False))

    def check(self):
        return gate.verify_packet(self.root, "kernel-fixture")

    def test_complete_private_source_fixture_returns_no_actual_servo_claim(self):
        result = self.check()
        self.assertEqual(result["detail"], {"actual_servo_executed": False})
        self.assertFalse(result["production_ready"])
        self.assertIn("renderer/" + self.entry_name, result["raw_sha256"])

    def test_missing_extra_or_wrong_generation_entry_is_refused(self):
        baseline = copy.deepcopy(self.launch)
        for value in ([], baseline["entries"] * 2, [{**baseline["entries"][0], "start_time": 99}]):
            self.put(self.root / "namespace-launch.json", {**baseline, "entries": value})
            with self.subTest(value=value), self.assertRaises(ValueError): self.check()
        self.put(self.root / "namespace-launch.json", baseline)
        self.put(self.renderer / "namespace-entry-999-777.json", self.entry)
        with self.assertRaises(ValueError): self.check()

    def test_launch_and_independent_observation_must_bind_same_unit_and_original_binary(self):
        for key, value in (("unit", "hepta-netns-" + "e" * 32 + ".service"), ("main_pid", True),
            ("exit_code", 0.0), ("renderer_uid", 0), ("binary_identity", {"device": 7, "inode": 78}),
            ("renderer_path", "/different/kernel-fixture/renderer")):
            self.put(self.root / "namespace-launch.json", {**self.launch, key: value})
            with self.subTest(key=key), self.assertRaises(ValueError): self.check()

    def test_cleanup_profile_and_claim_drift_is_refused(self):
        for key, value in (("owned_unit_stopped", False), ("exact_processes_exited", False), ("qualification_nonce_enabled", True),
            ("per_pair_ack_pacing", True), ("installed_qualified", True), ("production_ready", True)):
            self.put(self.root / "namespace-launch.json", {**self.launch, key: value})
            with self.subTest(key=key), self.assertRaises(ValueError): self.check()

    def test_host_or_canary_raw_substitution_is_refused(self):
        hostile = copy.deepcopy(self.host); hostile["network_namespace_inode"] = 111
        self.put(self.root / self.host_name, hostile)
        with self.assertRaises(ValueError): self.check()
        self.put(self.root / self.host_name, self.host)
        hostile = copy.deepcopy(self.canary); hostile["actual_connections"][0]["family"] = 2.0
        self.put(self.root / "outside-canary.json", hostile)
        with self.assertRaises(ValueError): self.check()

    def test_private_temp_launch_alias_missing_cleanup_and_actual_host_drift_are_refused(self):
        for mutation in ("float", "bool", "foreign", "extra", "not_removed", "numeric_removed"):
            hostile = copy.deepcopy(self.launch)
            if mutation == "float": hostile["temporary_directory"]["device"] = 7.0
            elif mutation == "bool": hostile["temporary_directory"]["inode"] = True
            elif mutation == "foreign": hostile["temporary_directory"]["inode"] += 1
            elif mutation == "extra": hostile["temporary_directory"]["approved"] = True
            elif mutation == "not_removed": hostile["temporary_directory_removed"] = False
            else: hostile["temporary_directory_removed"] = 1
            self.put(self.root / "namespace-launch.json", hostile)
            with self.subTest(mutation=mutation), self.assertRaises(ValueError): self.check()
        self.put(self.root / "namespace-launch.json", self.launch)
        hostile = copy.deepcopy(self.host); hostile["read_write_paths"] += " /tmp"
        self.put(self.root / self.host_name, hostile)
        with self.assertRaises(ValueError): self.check()


class RuntimePredicateTests(unittest.TestCase):
    def setUp(self):
        from test_native_runtime_identities import NativeBurstVerifierTests
        NativeBurstVerifierTests.setUpClass()
        self.source_fixture = NativeBurstVerifierTests()
        self.source_fixture.setUp()
        self.addCleanup(self.source_fixture.doCleanups)
        self.directory = self.source_fixture.directory
        self.report = self.source_fixture.report_fixture()
        self.report["authority"]["fixture_listener_loopback_only"] = False
        resource_report, resource_runtime, _ = source_only_fixture()
        resource_report["fixture_origin"] = gate.ORIGIN
        for key in ("initial_page_evidence", "recovery_page_evidence"):
            self.report[key].update(resource_runtime[key])
        self.resource = resource_report
        self.queue = self.source_fixture.queue
        self.put("resource-gate-result.json", self.resource)
        self.put("native-input-queue.json", self.queue)
        self.put("content-process-identity.json", {"generation": 1, "pid": 321, "start_time": 543})
        self.put("content-sigkill-sent.json", {"generation": 1, "pid": 321, "start_time": 543, "signal": "SIGKILL"})
        (self.directory / "fixture-origin.txt").write_text(gate.ORIGIN + "\n")
        for name in ("content-generation-1.png", "content-generation-2.png", "workspace-generation-1.png",
            "workspace-crash-placeholder.png", "workspace-generation-2.png"):
            (self.directory / name).write_bytes(b'\x89PNG\r\n\x1a\nSOURCE_FIXTURE_ONLY')

    def put(self, name, value):
        (self.directory / name).write_text(json.dumps(value))

    def check(self, report=None):
        self.put("runtime-result.json", report or self.report)
        return gate.validate_runtime(gate.Packet(self.directory), self.source_fixture.native)

    def test_decoder_fixture_preserves_original_down_click_order_ack_and_resource_predicates(self):
        self.assertEqual(self.check()["actual_dom_document_click_events"], 3)

    def test_actual_dom_count_type_order_and_ack_drift_fail(self):
        for mutation in ("two_down", "two_click", "no_fixture_click", "bad_order", "bool_coordinate", "float_count", "ack_total"):
            hostile = copy.deepcopy(self.report); page = hostile["initial_page_evidence"]
            if mutation == "two_down": page["pointerDowns"] = 2
            elif mutation == "two_click": page["documentClickEvents"] = 2
            elif mutation == "no_fixture_click": page["clicks"] = 0
            elif mutation == "bad_order": page["inputEventOrder"][1]["type"] = "pointerdown"
            elif mutation == "bool_coordinate": page["inputEventOrder"][0]["x"] = True
            elif mutation == "float_count": hostile["input_handled_callbacks"] = 15.0
            else: hostile["input_handled_callbacks"] += 1
            with self.subTest(mutation=mutation), self.assertRaises(ValueError): self.check(hostile)

    def test_fault_receipt_bool_float_on_every_numeric_identity_fails(self):
        for name in ("content-process-identity.json", "content-sigkill-sent.json"):
            baseline = {"generation": 1, "pid": 321, "start_time": 543}
            if "sigkill" in name: baseline["signal"] = "SIGKILL"
            for field in ("generation", "pid", "start_time"):
                for value in (True, float(baseline[field])):
                    self.put(name, {**baseline, field: value})
                    with self.subTest(name=name, field=field, value=value), self.assertRaises(ValueError): self.check()
            self.put(name, baseline)


class CompleteCorpusTests(unittest.TestCase):
    """Complete mocked byte packets; no systemd/kernel/native execution claim."""
    def setUp(self):
        self.fixture = CompletePacketTests(); self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root.parent
        self.cases = ["kernel-fixture"] + [f"inherited-{role}-ipv{version}" for role in ("embedder", "content") for version in (4, 6)]
        for index, case in enumerate(self.cases[1:], start=1):
            directory = self.root / case; directory.mkdir(); renderer = directory / "renderer"; renderer.mkdir()
            host = copy.deepcopy(self.fixture.host); pid, started = 4242 + index, 12345 + index
            unit = "hepta-netns-" + f"{index:032x}" + ".service"
            role = "content" if "content" in case else "embedder"
            host.update(unit=unit, control_group="/system.slice/" + unit, main_pid=pid, role=role,
                content_argument_observed=role == "content", read_write_paths="/source-fixture/" + case + "/renderer /tmp/hn-" + f"{index:024x}")
            host["temporary_directory"].update(path="/tmp/hn-" + f"{index:024x}", inode=88 + index)
            host["identity"].update(pid=pid, pgid=pid, session=pid, start_time=started)
            host["descriptor_inventory"][0].update(kind="socket", socket_domain=10 if case.endswith("ipv6") else 2)
            entry = {key: value for key, value in self.fixture.entry.items() if key in gate.REFUSAL_KEYS}
            entry.update(schema="trillionnium.desktop.netns-refusal.v1", role=role, pid=pid, start_time=started,
                reason="entry_descriptor_inventory_refused", engine_started=False)
            entry_name = f"namespace-refusal-{pid}-{started}.json"; host_name = "host-" + entry_name
            self.fixture.put(renderer / entry_name, entry); self.fixture.put(directory / host_name, host)
            (renderer / "runtime.log").write_text("SOURCE_ONLY_MOCKED_REFUSAL_NO_KERNEL_EXECUTION\n")
            launch = copy.deepcopy(self.fixture.launch)
            launch.update(case=case, unit=unit, main_pid=pid, exit_code=1, renderer_path=host["read_write_paths"].split()[0], temporary_directory=copy.deepcopy(host["temporary_directory"]),
                entries=[{"entry": entry_name, "host": host_name, "pid": pid, "start_time": started, "role": role}])
            self.fixture.put(directory / "namespace-launch.json", launch)
            self.fixture.put(directory / "outside-canary.json", self.fixture.canary)
        self.corpus = {"schema": "trillionnium.desktop.netns-corpus.v1", "status": "PASS_HOST_KERNEL_FIXTURE_ONLY",
            "actual_servo_executed": False, "cases": [gate.verify_packet(self.root / case, case) for case in self.cases],
            "source_binding": None, "source_qualification_only": True, "host_unix_proxy_confinement": False,
            "approved_unix_peer_policy": False, "installed_all_protocol_confinement": False,
            "late_scm_rights_authority_qualified": False, "lifetime_socket_authority_qualified": False,
            "installed_qualified": False, "production_ready": False}
        self.write(self.corpus)

    def write(self, value):
        self.fixture.put(self.root / "namespace-corpus.json", value)

    def test_complete_closed_mocked_kernel_packet_stays_kernel_scope(self):
        result = gate.verify_corpus(self.root)
        self.assertEqual(result["status"], "PASS_HOST_KERNEL_FIXTURE_ONLY")
        self.assertFalse(result["production_ready"])

    def test_lifetime_late_scm_proxy_all_protocol_and_install_promotions_fail_even_after_rehash(self):
        for field in ("host_unix_proxy_confinement", "approved_unix_peer_policy", "installed_all_protocol_confinement",
            "late_scm_rights_authority_qualified", "lifetime_socket_authority_qualified", "installed_qualified", "production_ready"):
            hostile = copy.deepcopy(self.corpus); hostile[field] = True
            self.write(hostile)
            with self.subTest(field=field), self.assertRaises(ValueError): gate.verify_corpus(self.root)

    def test_nested_case_numeric_alias_or_raw_hash_rewrite_is_refused(self):
        for mutation in ("bool", "float", "digest", "extra", "native", "cases"):
            hostile = copy.deepcopy(self.corpus)
            if mutation in {"bool", "float"}: hostile["cases"][1]["detail"]["inherited_socket_domain"] = True if mutation == "bool" else 2.0
            elif mutation == "digest": hostile["cases"][0]["raw_sha256"]["namespace-launch.json"] = "0" * 64
            elif mutation == "extra": hostile["cases"][0]["invented"] = True
            elif mutation == "native": hostile.update(actual_servo_executed=True, status="PASS_EXPLICIT_NATIVE_DIRECT_INET_QUALIFICATION_ONLY")
            else: hostile["cases"] = hostile["cases"][:-1]
            self.write(hostile)
            with self.subTest(mutation=mutation), self.assertRaises(ValueError): gate.verify_corpus(self.root)

    def test_reused_unit_is_refused_after_consistent_case_rehash(self):
        case = self.cases[1]; directory = self.root / case
        launch = json.loads((directory / "namespace-launch.json").read_text())
        launch["unit"] = self.fixture.launch["unit"]
        host_name = launch["entries"][0]["host"]
        host = json.loads((directory / host_name).read_text())
        host.update(unit=launch["unit"], control_group="/system.slice/" + launch["unit"])
        self.fixture.put(directory / host_name, host); self.fixture.put(directory / "namespace-launch.json", launch)
        self.corpus["cases"][1] = gate.verify_packet(directory, case)
        self.write(self.corpus)
        with self.assertRaisesRegex(ValueError, "reused"): gate.verify_corpus(self.root)

    def test_reused_private_temp_is_refused_after_complete_case_rehash(self):
        case = self.cases[1]; directory = self.root / case
        launch = json.loads((directory / "namespace-launch.json").read_text())
        temporary = copy.deepcopy(self.fixture.launch["temporary_directory"])
        launch["temporary_directory"] = temporary
        host_name = launch["entries"][0]["host"]
        host = json.loads((directory / host_name).read_text())
        host["temporary_directory"] = temporary
        host["read_write_paths"] = launch["renderer_path"] + " " + temporary["path"]
        self.fixture.put(directory / host_name, host); self.fixture.put(directory / "namespace-launch.json", launch)
        self.corpus["cases"][1] = gate.verify_packet(directory, case); self.write(self.corpus)
        with self.assertRaisesRegex(ValueError, "reused a private temporary"): gate.verify_corpus(self.root)


class ContractWiringTests(unittest.TestCase):
    def test_fixed_contract_matches_all_closed_nested_profiles(self):
        gate.validate_contract()
        source = json.loads((gate.ROOT / "contracts/native-direct-inet-qualification.v1.json").read_text())
        for key in source:
            hostile = copy.deepcopy(source); hostile[key] = None
            with self.subTest(field=key), self.assertRaises(ValueError): gate.validate_contract(hostile)
        for field in ("activation", "fixture", "limits", "authority", "claim_ceiling", "qualification", "record_fields", "systemd_properties"):
            hostile = copy.deepcopy(source); hostile[field]["extra"] = True
            with self.subTest(nested=field), self.assertRaises(ValueError): gate.validate_contract(hostile)

    def test_default_disabled_and_false_claims_cannot_be_refreshed_or_promoted(self):
        source = json.loads((gate.ROOT / "contracts/native-direct-inet-qualification.v1.json").read_text())
        for path in (("activation", "default_enabled"), ("activation", "product_activation_allowed"),
            ("fixture", "holds_inet_listener"), ("authority", "socket_domain_alone_is_peer_approval")):
            hostile = copy.deepcopy(source); hostile[path[0]][path[1]] = True
            with self.subTest(path=path), self.assertRaises(ValueError): gate.validate_contract(hostile)
        for claim in source["claim_ceiling"]:
            hostile = copy.deepcopy(source); hostile["claim_ceiling"][claim] = True
            with self.subTest(claim=claim), self.assertRaises(ValueError): gate.validate_contract(hostile)
        hostile = copy.deepcopy(source); hostile["limits"]["entry_absolute_budget_seconds"] = 10.0
        with self.assertRaises(ValueError): gate.validate_contract(hostile)

    def test_content_entry_precedes_actual_engine_start_and_no_token_is_recorded(self):
        main = (gate.ROOT / "experiments/servo-headed-runtime/src/main.rs").read_text()
        body = main.split("fn main() {", 1)[1].split("fn content_process_token", 1)[0]
        self.assertLess(body.index("Role::Content"), body.index("run_content_process(token)"))
        source = (gate.ROOT / "experiments/servo-headed-runtime/src/network_confinement.rs").read_text()
        self.assertIn("Duration::from_secs(10)", source)
        self.assertIn("const MAX_FDS: usize = 256", source)
        self.assertIn("const MAX_PROC_BYTES: u64 = 8192", source)
        self.assertNotIn("cmdline", source)


class ExecutableStagingTests(unittest.TestCase):
    """Actual files, descriptors, exec and fork; no Servo qualification."""
    def source(self, parent, body=b"#!/bin/sh\nprintf staging-fixture"):
        path = Path(parent) / "source-runtime"
        path.write_bytes(body)
        path.chmod(0o700)
        return path

    def fds(self, value):
        result = [value.copy.fd]
        for item in (value.source, value.parent, value.root):
            result.extend(owner.fd for owner in item.owners)
        return result

    def test_actual_two_link_executable_copied_and_executes_readonly_single_link(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.dict(os.environ, {"RUNNER_TEMP": directory}):
            source = self.source(directory)
            alias = Path(directory) / "cargo-hash-alias"
            os.link(source, alias)
            self.assertEqual(source.stat().st_nlink, 2)
            with self.assertRaisesRegex(ValueError, "exactly one hard link"):
                gate.hash_regular(source)
            with gate._StagedExecutable(source) as value:
                retained = self.fds(value)
                path = value.path
                self.assertEqual(path.stat().st_nlink, 1)
                self.assertEqual(path.stat().st_mode & 0o777, 0o500)
                self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)
                self.assertEqual(fcntl.fcntl(value.copy.fd, fcntl.F_GETFL) & os.O_ACCMODE, os.O_RDONLY)
                self.assertTrue(fcntl.fcntl(value.copy.fd, fcntl.F_GETFD) & fcntl.FD_CLOEXEC)
                self.assertEqual(value.digest, hashlib.sha256(source.read_bytes()).hexdigest())
                self.assertEqual(gate.hash_regular(path), value.verify())
                actual = subprocess.run([str(path)], capture_output=True, timeout=3, check=True)
                self.assertEqual(actual.stdout, b"staging-fixture")
            self.assertFalse(path.parent.exists())
            self.assertTrue(alias.exists())
            for descriptor in retained:
                with self.assertRaises(OSError): os.fstat(descriptor)

    def test_unsafe_group_write_source_is_not_repaired_or_admitted(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.dict(os.environ, {"RUNNER_TEMP": directory}):
            source = self.source(directory)
            source.chmod(0o775)
            with self.assertRaisesRegex(ValueError, "source unsafe"):
                gate._StagedExecutable(source)
            self.assertEqual(source.stat().st_mode & 0o777, 0o775)
            self.assertFalse(list(Path(directory).glob(".hepta-netns-exec-*")))

    def test_explicit_staging_parent_inside_uploaded_output_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            source = self.source(directory)
            artifacts = Path(directory) / "artifacts"
            artifacts.mkdir(mode=0o700)
            with mock.patch.dict(os.environ, {"RUNNER_TEMP": str(artifacts)}):
                with self.assertRaisesRegex(ValueError, "outside artifact output"):
                    gate._StagedExecutable(source, artifact_root=artifacts)
            self.assertFalse(list(artifacts.iterdir()))

    def test_source_leaf_and_ancestor_symlinks_and_fifo_are_refused(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.dict(os.environ, {"RUNNER_TEMP": directory}):
            root = Path(directory)
            real = root / "real"
            real.mkdir(mode=0o700)
            source = self.source(real)
            alias = root / "alias"
            alias.symlink_to(real, target_is_directory=True)
            leaf = root / "leaf"
            leaf.symlink_to(source)
            fifo = root / "fifo"
            os.mkfifo(fifo, 0o700)
            for path in (alias / source.name, leaf, fifo):
                with self.subTest(path=path), self.assertRaises((ValueError, OSError)):
                    gate._StagedExecutable(path)
            self.assertFalse(list(root.glob(".hepta-netns-exec-*")))

    def test_real_source_name_substitution_during_copy_refuses_and_removes_owned_copy(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.dict(os.environ, {"RUNNER_TEMP": directory}):
            source = self.source(directory)
            original = os.read
            changed = False
            def read(descriptor, size):
                nonlocal changed
                block = original(descriptor, size)
                if block and not changed:
                    changed = True
                    source.rename(source.with_name("old-runtime"))
                    self.source(directory)
                return block
            with mock.patch.object(gate.os, "read", side_effect=read):
                with self.assertRaisesRegex(ValueError, "source.*changed"):
                    gate._StagedExecutable(source)
            self.assertTrue(changed)
            self.assertFalse(list(Path(directory).glob(".hepta-netns-exec-*")))

    def test_source_and_staged_bytes_rechecked_after_actual_creation(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.dict(os.environ, {"RUNNER_TEMP": directory}):
            source = self.source(directory)
            value = gate._StagedExecutable(source)
            source.write_bytes(b"changed-source")
            with self.assertRaisesRegex(ValueError, "source changed"):
                value.verify()
            value.close(remove=True)
            source = self.source(directory)
            value = gate._StagedExecutable(source)
            value.path.chmod(0o700)
            value.path.write_bytes(b"changed-copy")
            with self.assertRaisesRegex(ValueError, "metadata changed"):
                value.verify()
            value.close(remove=True)

    def test_source_parent_replacement_is_refused_with_retained_original_fd(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.dict(os.environ, {"RUNNER_TEMP": directory}):
            root = Path(directory)
            parent = root / "input"
            parent.mkdir(mode=0o700)
            source = self.source(parent)
            value = gate._StagedExecutable(source)
            parent.rename(root / "old-input")
            parent.mkdir(mode=0o700)
            self.source(parent)
            self.assertEqual(gate.snapshot(os.fstat(value.source.fd)), value.source_snapshot)
            with self.assertRaisesRegex(ValueError, "source name changed"):
                value.verify()
            value.close(remove=True)

    def test_foreign_leaf_substitution_is_preserved_when_cleanup_refuses(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.dict(os.environ, {"RUNNER_TEMP": directory}):
            value = gate._StagedExecutable(self.source(directory))
            retained = self.fds(value)
            value.path.rename(value.path.with_name("retained-old"))
            value.path.write_bytes(b"foreign-do-not-delete")
            foreign = value.path
            with self.assertRaisesRegex(ValueError, "cleanup name changed"):
                value.close(remove=True)
            self.assertEqual(foreign.read_bytes(), b"foreign-do-not-delete")
            for descriptor in retained:
                with self.assertRaises(OSError): os.fstat(descriptor)

    def test_foreign_directory_substitution_is_preserved_when_cleanup_refuses(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.dict(os.environ, {"RUNNER_TEMP": directory}):
            value = gate._StagedExecutable(self.source(directory))
            path = value.path.parent
            path.rename(path.with_name(path.name + "-old"))
            path.mkdir(mode=0o700)
            foreign = path / "runtime"
            foreign.write_bytes(b"foreign-directory")
            with self.assertRaisesRegex(ValueError, "directory path changed"):
                value.close(remove=True)
            self.assertEqual(foreign.read_bytes(), b"foreign-directory")

    def test_partial_real_write_failure_retires_descriptors_and_owned_names(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.dict(os.environ, {"RUNNER_TEMP": directory}):
            source = self.source(directory)
            original = os.write
            def write(descriptor, block):
                original(descriptor, block[:3])
                raise OSError("actual partial staged write")
            with mock.patch.object(gate.os, "write", side_effect=write):
                with self.assertRaisesRegex(OSError, "partial staged write"):
                    gate._StagedExecutable(source)
            self.assertFalse(list(Path(directory).glob(".hepta-netns-exec-*")))

    def test_real_fsync_interruption_and_expired_copy_budget_leave_no_executable(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.dict(os.environ, {"RUNNER_TEMP": directory}):
            source = self.source(directory)
            original = os.fsync
            def fsync(descriptor):
                original(descriptor)
                raise KeyboardInterrupt("after actual staged fsync")
            with mock.patch.object(gate.os, "fsync", side_effect=fsync):
                with self.assertRaisesRegex(KeyboardInterrupt, "actual staged fsync"):
                    gate._StagedExecutable(source)
            self.assertFalse(list(Path(directory).glob(".hepta-netns-exec-*")))
            with mock.patch.object(gate._StagedExecutable, "BUDGET", 0):
                with self.assertRaisesRegex(ValueError, "staging deadline expired"):
                    gate._StagedExecutable(source)
            self.assertFalse(list(Path(directory).glob(".hepta-netns-exec-*")))

    def test_actual_late_eof_cannot_renew_the_original_copy_budget(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.dict(os.environ, {"RUNNER_TEMP": directory}):
            source = self.source(directory)
            original = os.read
            delayed = False
            def read(descriptor, size):
                nonlocal delayed
                block = original(descriptor, size)
                if not block and not delayed:
                    delayed = True
                    time.sleep(0.03)
                return block
            with mock.patch.object(gate._StagedExecutable, "BUDGET", 0.02), mock.patch.object(gate.os, "read", side_effect=read):
                with self.assertRaisesRegex(ValueError, "staging deadline expired"):
                    gate._StagedExecutable(source)
            self.assertTrue(delayed)
            self.assertFalse(list(Path(directory).glob(".hepta-netns-exec-*")))

    def test_actual_fork_refuses_before_cleanup_and_preserves_parent_file_and_fds(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.dict(os.environ, {"RUNNER_TEMP": directory}):
            value = gate._StagedExecutable(self.source(directory))
            retained = self.fds(value)
            child = os.fork()
            if child == 0:
                try:
                    for operation in (value.verify, lambda: value.close(remove=True)):
                        try: operation()
                        except ValueError: pass
                        else: os._exit(2)
                    value.__del__()
                    os._exit(0 if value.path.is_file() else 3)
                except BaseException:
                    os._exit(4)
            descriptor = os.pidfd_open(child)
            try:
                self.assertTrue(select.select([descriptor], [], [], 3)[0])
                self.assertEqual(os.waitpid(child, 0)[1], 0)
                for owned in retained: os.fstat(owned)
                value.verify()
            finally:
                if not select.select([descriptor], [], [], 0)[0]:
                    signal.pidfd_send_signal(descriptor, signal.SIGKILL)
                try: os.waitpid(child, 0)
                except ChildProcessError: pass
                os.close(descriptor)
                value.close(remove=True)

    def test_real_close_then_reuse_interrupt_gc_never_closes_foreign_fd(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.dict(os.environ, {"RUNNER_TEMP": directory}):
            value = gate._StagedExecutable(self.source(directory))
            retained = self.fds(value)
            target = value.copy.fd
            original = os.close
            interrupted = False
            def close(descriptor):
                nonlocal interrupted
                original(descriptor)
                if descriptor == target and not interrupted:
                    interrupted = True
                    foreign = os.open("/dev/null", os.O_RDONLY | os.O_CLOEXEC)
                    if foreign != target:
                        os.dup2(foreign, target)
                        original(foreign)
                    raise KeyboardInterrupt("after real close and descriptor reuse")
            with mock.patch.object(gate.os, "close", side_effect=close):
                with self.assertRaisesRegex(KeyboardInterrupt, "descriptor reuse"):
                    value.close()
            del value
            gc.collect()
            try:
                os.fstat(target)
                self.assertTrue(interrupted)
                for descriptor in retained:
                    if descriptor != target:
                        with self.assertRaises(OSError): os.fstat(descriptor)
            finally:
                original(target)

    def test_actual_helper_return_interruption_gc_closes_unreceived_path_descriptors(self):
        with tempfile.TemporaryDirectory() as directory:
            source = self.source(directory)
            captured = []
            previous = sys.gettrace()
            def trace(frame, event, arg):
                if event == "return" and frame.f_code is gate._StagingPath.open.__func__.__code__:
                    captured.extend(owner.fd for owner in arg.owners)
                    raise KeyboardInterrupt("actual path-owner return")
                return trace
            try:
                sys.settrace(trace)
                with self.assertRaisesRegex(KeyboardInterrupt, "path-owner return"):
                    gate._StagingPath.open(source)
            finally:
                sys.settrace(previous)
            gc.collect()
            self.assertTrue(captured)
            for descriptor in captured:
                with self.assertRaises(OSError): os.fstat(descriptor)

    def test_actual_constructor_return_interruption_gc_retires_fds_without_unlinking(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.dict(os.environ, {"RUNNER_TEMP": directory}):
            source = self.source(directory)
            before = set(os.listdir("/proc/self/fd"))
            paths = []
            previous = sys.gettrace()
            def trace(frame, event, arg):
                if event == "return" and frame.f_code is gate._StagedExecutable.__init__.__code__:
                    paths.append(frame.f_locals["self"].path)
                    raise KeyboardInterrupt("actual staged constructor return")
                return trace
            try:
                sys.settrace(trace)
                with self.assertRaisesRegex(KeyboardInterrupt, "staged constructor return"):
                    gate._StagedExecutable(source)
            finally:
                sys.settrace(previous)
            gc.collect()
            self.assertEqual(set(os.listdir("/proc/self/fd")), before)
            self.assertEqual(len(paths), 1)
            self.assertTrue(paths[0].is_file(), "GC must not turn an undelivered owner into pathname cleanup")

    def test_actual_detached_and_native_call_line_interruptions_retire_all_owned_fds(self):
        import inspect
        lines, first = inspect.getsourcelines(gate._StagingDescriptor.close)
        native_line = next(first + index for index, line in enumerate(lines)
                           if "os.close(descriptor)" in line)
        for boundary in ("after_detach", "native_call_line"):
            for target_kind in ("copy", "source"):
                with self.subTest(boundary=boundary, target=target_kind):
                    with tempfile.TemporaryDirectory() as directory, mock.patch.dict(os.environ, {"RUNNER_TEMP": directory}):
                        value = gate._StagedExecutable(self.source(directory))
                        retained = self.fds(value)
                        target = value.copy.fd if target_kind == "copy" else value.source.fd
                        previous = sys.gettrace()
                        fired = False
                        def trace(frame, event, arg):
                            nonlocal fired
                            if (not fired and event == "line"
                                and frame.f_code is gate._StagingDescriptor.close.__code__
                                and frame.f_locals.get("descriptor") == target
                                and frame.f_locals["self"].fd is None
                                and (boundary == "after_detach" or frame.f_lineno == native_line)):
                                fired = True
                                sys.settrace(None)
                                raise KeyboardInterrupt("actual detached native-close line")
                            return trace
                        try:
                            sys.settrace(trace)
                            with self.assertRaisesRegex(KeyboardInterrupt, "detached native-close"):
                                value.close()
                        finally:
                            sys.settrace(previous)
                        self.assertTrue(fired)
                        del value
                        gc.collect()
                        for descriptor in retained:
                            with self.assertRaises(OSError):
                                os.fstat(descriptor)


if __name__ == "__main__":
    unittest.main()
