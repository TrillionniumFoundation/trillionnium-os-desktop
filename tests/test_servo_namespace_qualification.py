"""Source decoder/contract regressions, never native or installed evidence.

Actual no-skip systemd/Rust entry cases run through the separate explicit
kernel-fixture CLI. The permanent native CI runs the real pinned Servo binary.
"""
from __future__ import annotations

import copy
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
        "renderer_uid": 1000, "renderer_gid": 1000, "read_write_paths": "/source-fixture/kernel-fixture/renderer",
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
            "renderer_uid": 1000, "renderer_gid": 1000, "renderer_path": host["read_write_paths"],
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
                content_argument_observed=role == "content", read_write_paths="/source-fixture/" + case + "/renderer")
            host["identity"].update(pid=pid, pgid=pid, session=pid, start_time=started)
            host["descriptor_inventory"][0].update(kind="socket", socket_domain=10 if case.endswith("ipv6") else 2)
            entry = {key: value for key, value in self.fixture.entry.items() if key in gate.REFUSAL_KEYS}
            entry.update(schema="trillionnium.desktop.netns-refusal.v1", role=role, pid=pid, start_time=started,
                reason="entry_descriptor_inventory_refused", engine_started=False)
            entry_name = f"namespace-refusal-{pid}-{started}.json"; host_name = "host-" + entry_name
            self.fixture.put(renderer / entry_name, entry); self.fixture.put(directory / host_name, host)
            (renderer / "runtime.log").write_text("SOURCE_ONLY_MOCKED_REFUSAL_NO_KERNEL_EXECUTION\n")
            launch = copy.deepcopy(self.fixture.launch)
            launch.update(case=case, unit=unit, main_pid=pid, exit_code=1, renderer_path=host["read_write_paths"],
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


if __name__ == "__main__":
    unittest.main()
