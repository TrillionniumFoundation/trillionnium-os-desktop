"""Actual host custody/process tests plus explicitly synthetic parser policy tests.

The short parser fixture below is NOT a signed DSSE attestation. Its certificate
DER is the observed public certificate. Parser tests never claim crypto success.
Real official-tool signature negatives are separately recorded author facts.
"""
from __future__ import annotations

import base64
import copy
import fcntl
import gc
import hashlib
import inspect
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from tools import mozjs_authenticated_input as m
from tools import build_mozjs_authenticated_native as b

DER_BASE64 = "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"


def descriptors():
    return set(os.listdir("/proc/self/fd"))


def parser_fixture():
    statement = {"_type": "https://in-toto.io/Statement/v1", "predicateType": m.PREDICATE,
                 "subject": [{"name": m.POLICY["archive"]["name"], "digest": {"sha256": m.POLICY["archive"]["sha256"]}}],
                 "predicate": {"syntheticParserOnly": True}}
    bundle = {"mediaType": m.POLICY["bundle"]["media_type"],
              "verificationMaterial": {"certificate": {"rawBytes": DER_BASE64}},
              "dsseEnvelope": {"payload": base64.b64encode(json.dumps(statement).encode()).decode()}}
    output = [{"attestation": {"bundle": copy.deepcopy(bundle), "bundle_url": "", "initiator": ""},
               "verificationResult": {"mediaType": "application/vnd.dev.sigstore.verificationresult+json;version=0.1",
                                      "signature": {"certificate": copy.deepcopy(m.CERTIFICATE_FIELDS)},
                                      "verifiedTimestamps": [{"type": "Tlog", "uri": "https://rekor.sigstore.dev", "timestamp": "2026-08-24T09:46:29Z"}],
                                      "verifiedIdentity": {"subjectAlternativeName": {"subjectAlternativeName": m.IDENTITY},
                                                           "issuer": {"issuer": "", "regexp": ".*"}, "runnerEnvironment": "github-hosted"},
                                      "statement": statement}}]
    return output, bundle


def parse(output, bundle):
    return m._parse_verified(json.dumps(output).encode(), json.dumps(bundle).encode())


class ParserPolicyOnlyTests(unittest.TestCase):
    def test_synthetic_parser_shape_is_not_a_signature_receipt(self):
        output, bundle = parser_fixture(); result = parse(output, bundle)
        self.assertEqual(result["authenticated_token_subject"], m.TOKEN_SUBJECT)
        self.assertEqual(len(result["authenticated_certificate_fields"]), 22)
        self.assertNotIn("actual_supplier_signature_verified", result)

    def test_every_authenticated_certificate_field_and_unknown_field_refused(self):
        for field in m.CERTIFICATE_FIELDS:
            output, bundle = parser_fixture(); output[0]["verificationResult"]["signature"]["certificate"][field] = "synthetic wrong authority"
            with self.subTest(field=field), self.assertRaises(ValueError): parse(output, bundle)
        output, bundle = parser_fixture(); output[0]["verificationResult"]["signature"]["certificate"]["extra"] = True
        with self.assertRaises(ValueError): parse(output, bundle)

    def test_verified_statement_cannot_differ_from_same_bundle_payload(self):
        output, bundle = parser_fixture(); output[0]["verificationResult"]["statement"]["subject"][0]["digest"]["sha256"] = "0" * 64
        with self.assertRaises(ValueError): parse(output, bundle)

    def test_duplicate_archive_subject_and_changed_subject_refused(self):
        for mode in ["duplicate", "changed"]:
            output, bundle = parser_fixture(); statement = output[0]["verificationResult"]["statement"]
            if mode == "duplicate": statement["subject"].append(copy.deepcopy(statement["subject"][0]))
            else: statement["subject"][0]["name"] = "other.tar.gz"
            bundle["dsseEnvelope"]["payload"] = base64.b64encode(json.dumps(statement).encode()).decode()
            output[0]["attestation"]["bundle"] = copy.deepcopy(bundle)
            with self.assertRaises(ValueError): parse(output, bundle)

    def test_release_predicate_and_other_bundle_cannot_substitute_slsa(self):
        output, bundle = parser_fixture(); output[0]["attestation"]["bundle"]["mediaType"] = "other"
        with self.assertRaises(ValueError): parse(output, bundle)
        output, bundle = parser_fixture(); statement = output[0]["verificationResult"]["statement"]
        statement["predicateType"] = "https://github.com/attestation/release/v0.2"
        bundle["dsseEnvelope"]["payload"] = base64.b64encode(json.dumps(statement).encode()).decode()
        output[0]["attestation"]["bundle"] = copy.deepcopy(bundle)
        with self.assertRaises(ValueError): parse(output, bundle)

    def test_historical_verified_time_authority_and_timezone_refused(self):
        for field, value in [("timestamp", "2026-08-24T09:46:29"), ("timestamp", "2026-08-24T09:57:00Z"),
                             ("timestamp", "2026-10-03T09:46:29Z"), ("uri", "https://example.invalid"), ("type", "caller")]:
            output, bundle = parser_fixture(); output[0]["verificationResult"]["verifiedTimestamps"][0][field] = value
            with self.assertRaises(ValueError): parse(output, bundle)

    def test_empty_or_multiple_results_timestamps_and_unknown_keys_refused(self):
        for mutation in [lambda x: x.clear(), lambda x: x.append(copy.deepcopy(x[0])),
                         lambda x: x[0].update(extra=True),
                         lambda x: x[0]["verificationResult"]["verifiedTimestamps"].clear(),
                         lambda x: x[0]["verificationResult"].update(caller_passed=True)]:
            output, bundle = parser_fixture(); mutation(output)
            with self.assertRaises(ValueError): parse(output, bundle)

    def test_actual_cert_der_token_subject_and_canonical_der_refusals(self):
        der = base64.b64decode(DER_BASE64)
        token, before, after = m._der_certificate(der)
        self.assertEqual(token, m.TOKEN_SUBJECT); self.assertLessEqual(before, after)
        for raw in [der[:-1], der + b"x", der[:50] + bytes([der[50] ^ 1]) + der[51:]]:
            with self.assertRaises(ValueError): m._der_certificate(raw)
        for raw in [b"\x0c\x80", b"\x0c\x81\x01x", b"\x0c\x82\x00\x80", b"\x0c\x02x"]:
            with self.assertRaises(ValueError): m._der_items(raw)

    def test_duplicate_nonfinite_deep_and_oversize_json_refused(self):
        for raw in [b'{"a":1,"a":2}', b'{"a":NaN}', b"[" * 25 + b"0" + b"]" * 25,
                    b" " * (m.MAX_OUTPUT_BYTES + 1)]:
            with self.assertRaises(ValueError): m._bounded_json(raw, m.MAX_OUTPUT_BYTES)

    def test_display_wildcard_never_replaces_exact_certificate_issuer(self):
        output, bundle = parser_fixture()
        self.assertTrue(parse(output, bundle)["display_issuer_is_wildcard"])
        output[0]["verificationResult"]["signature"]["certificate"]["issuer"] = ".*"
        with self.assertRaises(ValueError): parse(output, bundle)


class StopHere(BaseException): pass


class AuthenticatedHostCustodyTests(unittest.TestCase):
    def setUp(self):
        if sys.platform != "linux" or not hasattr(os, "memfd_create"):
            raise RuntimeError("actual Linux memfd/procfs/fork required")
        self.temp = tempfile.TemporaryDirectory(prefix="mozjs-authenticated-host-"); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.path = self.root / "input"
        self.raw = b"real sealed host input\0" * 123; self.path.write_bytes(self.raw)
        self.digest = hashlib.sha256(self.raw).hexdigest()

    def lease(self):
        return m._seal_input(self.path, len(self.raw), self.digest, m.MAX_BUNDLE_BYTES)

    def held(self):
        held = m._InputSet()
        try:
            for name in ["archive", "bundle", "tool"]: held._leases[name] = self.lease()
            return held
        except BaseException: held.close(); raise

    def test_source_policy_closed_and_old_false_claims_preserved(self):
        self.assertEqual(m.load_manifest(), m.POLICY)
        self.assertFalse(m.archive.load_manifest()["correspondence"]["attestation_verified"])
        for mutation in [lambda x: x.update(caller_passed=True), lambda x: x["tool"].update(sha256="0" * 64),
                         lambda x: x["bundle"].update(index=0), lambda x: x["limits"].update(tool=True),
                         lambda x: x["claims"].update(production_ready=True)]:
            value = copy.deepcopy(m.POLICY); mutation(value)
            with self.assertRaises(ValueError): m.check_manifest(value)

    def test_public_api_has_no_verification_token_argv_root_or_bypass_argument(self):
        self.assertEqual(list(inspect.signature(b.build_authenticated_native).parameters),
                         ["upstream", "original_lock", "archive_path", "bundle_path", "tool_path", "target_parent", "profile"])
        for key in ["attestation_passed", "stdout", "proof", "argv", "roots", "ignore_expiry"]:
            with self.assertRaises(TypeError): b.build_authenticated_native(**{key: True})

    def test_real_seals_snapshot_original_path_replacement_and_close_inventory(self):
        before = descriptors(); value = self.lease()
        try:
            path = value.stable_path(); self.path.unlink(); self.path.write_bytes(b"replacement")
            self.assertEqual(Path(path).read_bytes(), self.raw)
            self.assertEqual(value.readback()["sha256"], self.digest)
            self.assertEqual(fcntl.fcntl(value._owner.fd, fcntl.F_GET_SEALS), m.archive.SEALS)
            for op in [lambda: os.pwrite(value._owner.fd, b"x", 0), lambda: os.ftruncate(value._owner.fd, 0)]:
                with self.assertRaises(OSError): op()
        finally: value.close()
        self.assertFalse(Path(path).exists()); self.assertEqual(descriptors(), before)

    def test_actual_sealed_executable_runs_after_mutable_selector_replaced(self):
        binary = Path("/usr/bin/true"); raw = binary.read_bytes(); selector = self.root / "tool"; selector.write_bytes(raw)
        lease = m._seal_input(selector, len(raw), hashlib.sha256(raw).hexdigest(), m.MAX_TOOL_BYTES, True)
        try:
            path = lease.stable_path(); selector.write_bytes(b"not an executable")
            completed = subprocess.run([path], executable=path, timeout=5, capture_output=True)
            self.assertEqual(completed.returncode, 0)
            self.assertEqual(lease.readback()["sha256"], hashlib.sha256(raw).hexdigest())
        finally: lease.close()

    def test_wrong_bytes_links_fifo_source_name_drift_rejected_without_fd_leak(self):
        before = descriptors()
        for size, digest in [(True, self.digest), (0, self.digest), (len(self.raw), "0" * 64), (len(self.raw) - 1, self.digest)]:
            with self.assertRaises(ValueError): m._seal_input(self.path, size, digest, m.MAX_BUNDLE_BYTES)
        symlink = self.root / "symlink"; symlink.symlink_to(self.path)
        fifo = self.root / "fifo"; os.mkfifo(fifo); hard = self.root / "hard"; os.link(self.path, hard)
        for path in [symlink, fifo, hard, self.path, self.root]:
            with self.assertRaises((ValueError, OSError)): m._seal_input(path, len(self.raw), self.digest, m.MAX_BUNDLE_BYTES)
        gc.collect(); self.assertEqual(descriptors(), before)

    def test_actual_source_read_replacement_and_interrupted_write_refused(self):
        from tools import browser_codec_reference_security as source
        actual = source.ManagedSourceReader.read_some; replaced = False; before = descriptors()
        def read(reader, size):
            nonlocal replaced
            raw = actual(reader, size)
            if not replaced: self.path.unlink(); self.path.write_bytes(self.raw); replaced = True
            return raw
        with patch.object(source.ManagedSourceReader, "read_some", read), self.assertRaises(ValueError): self.lease()
        write = m.os.write
        def interrupted(fd, raw): write(fd, raw[:3]); raise StopHere()
        with patch.object(m.os, "write", interrupted), self.assertRaises(StopHere): self.lease()
        gc.collect(); self.assertEqual(descriptors(), before)

    def test_undelivered_factory_return_closes_owned_descriptor(self):
        before = descriptors()
        def trace(frame, event, value):
            if frame.f_code is m._seal_input.__code__ and event == "return": raise StopHere()
            return trace
        try:
            sys.settrace(trace)
            with self.assertRaises(StopHere): self.lease()
        finally: sys.settrace(None)
        gc.collect(); self.assertEqual(descriptors(), before)

    def test_real_aggregate_thread_fork_and_path_callback_reentry_refused(self):
        held = self.held()
        try:
            results = []
            def use():
                for method in [held.readback, held.paths, held.close]:
                    try: method()
                    except ValueError: results.append(True)
                    else: results.append(False)
            thread = threading.Thread(target=use); thread.start(); thread.join(5)
            self.assertFalse(thread.is_alive()); self.assertEqual(results, [True] * 3)
            read, write = os.pipe(); pid = os.fork()
            if pid == 0:
                os.close(read)
                try:
                    refused = 0
                    for method in [held.readback, held.paths, held.close]:
                        try: method()
                        except ValueError: refused += 1
                    os.write(write, str(refused).encode())
                finally: os._exit(0)
            os.close(write)
            try:
                self.assertTrue(select.select([read], [], [], 5)[0]); self.assertEqual(os.read(read, 8), b"3")
            finally: os.close(read); os.waitpid(pid, 0)
            original = m.archive.os.pread; refused = []
            def callback(fd, size, offset):
                for method in [held.readback, held.paths, held.close]:
                    try: method()
                    except ValueError: refused.append(True)
                    else: refused.append(False)
                return original(fd, size, offset)
            with patch.object(m.archive.os, "pread", callback): held.paths()
            self.assertTrue(refused); self.assertTrue(all(refused)); self.assertEqual(len(held.readback()), 3)
        finally: held.close()

    def test_descriptor_reuse_refused_without_closing_foreign_replacement(self):
        value = self.lease(); fd = value._owner.fd; os.close(fd)
        foreign = os.open(self.path, os.O_RDONLY | os.O_CLOEXEC)
        if foreign != fd: os.dup2(foreign, fd)
        try:
            with self.assertRaises(ValueError): value.readback()
            value.close(); self.assertEqual(os.read(fd, len(self.raw)), self.raw)
        finally:
            os.close(fd)
            if foreign != fd: os.close(foreign)

    def test_actual_private_host_nonzero_and_output_overflow_keep_all_inputs_current(self):
        held = self.held()
        try:
            evidence = m._new_directory(self.root, "host-nonzero-")
            rc, stdout, stderr = m._run_verifier(held, [sys.executable, "-c", "print('ordinary host output');raise SystemExit(7)"], evidence, {}, 5, .1)
            self.assertEqual(rc, 7); self.assertIn(b"ordinary host output", stdout)
            self.assertEqual(len(held.readback()), 3); self.assertEqual((evidence / "stdout.raw").read_bytes(), stdout)
            evidence = m._new_directory(self.root, "host-overflow-")
            with self.assertRaises(ValueError):
                m._run_verifier(held, [sys.executable, "-c", "import os;os.write(1,b'x'*400000)"], evidence, {}, 5, .1)
            self.assertLessEqual((evidence / "stdout.raw").stat().st_size, m.MAX_OUTPUT_BYTES)
            self.assertEqual(len(held.readback()), 3)
        finally: held.close()

    def test_actual_private_host_timeout_and_cancel_reap_before_all_inputs_close(self):
        held = self.held(); pids = []
        try:
            start = m._VerifierProcess.start
            def observe(owner, *args): start(owner, *args); pids.append(owner.process.pid)
            with patch.object(m._VerifierProcess, "start", observe), self.assertRaises(subprocess.TimeoutExpired):
                m._run_verifier(held, [sys.executable, "-c", "import time;time.sleep(20)"], self.root, {}, 1, .1)
            def cancel(owner, *args): start(owner, *args); pids.append(owner.process.pid); raise StopHere()
            with patch.object(m._VerifierProcess, "start", cancel), self.assertRaises(StopHere):
                m._run_verifier(held, [sys.executable, "-c", "import time;time.sleep(20)"], self.root, {}, 5, .1)
            for pid in pids:
                with self.assertRaises(ProcessLookupError): os.kill(pid, 0)
                self.assertFalse(m.original._group_exists(pid))
            self.assertEqual(len(held.readback()), 3)
        finally: held.close()

    def test_original_cargo_group_helper_holds_aggregate_through_real_child(self):
        held = self.held()
        try:
            paths = held.paths()
            code = "import hashlib,pathlib,sys;assert all(hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()==sys.argv[4] for p in sys.argv[1:4]);raise SystemExit(9)"
            rc = m.original._run_with_lease(held, [sys.executable, "-c", code, *paths.values(), self.digest], self.root, {}, 5, .1)
            self.assertEqual(rc, 9); self.assertEqual(len(held.readback()), 3)
        finally: held.close()

    def test_inherited_overrides_refused_before_prepared_verification_or_input_io(self):
        for key in ["MOZJS_FROM_SOURCE", "MOZJS_CREATE_ARCHIVE", "MOZJS_ARCHIVE", "CARGO_TARGET_DIR", "RUSTC_WRAPPER", "RUSTFLAGS"]:
            with patch.dict(os.environ, {key: "secret-value"}, clear=True), patch.object(m.original, "verify_prepared") as prepared:
                with self.assertRaises(ValueError): b.build_authenticated_native(self.root, self.path, self.path, self.path, self.path, self.root, "native-owner")
                prepared.assert_not_called()

    def test_private_verifier_environment_is_fresh_without_inherited_auth_roots_or_debug(self):
        evidence = m._new_directory(self.root, "environment-")
        with patch.dict(os.environ, {"GH_TOKEN": "secret", "SIGSTORE_ROOT_FILE": "untrusted", "GH_DEBUG": "api", "HOME": "caller"}):
            env = m._verifier_environment(evidence)
        self.assertNotIn("GH_TOKEN", env); self.assertNotIn("SIGSTORE_ROOT_FILE", env); self.assertNotIn("GH_DEBUG", env)
        self.assertEqual(env["GH_CONFIG_DIR"], str(evidence / "gh-config"))

    def test_actual_build_cli_override_failure_has_fixed_stderr_without_secret_payload(self):
        canary = "credential-104299-path-秘密"
        argv = [sys.executable, str(m.ROOT / "tools/build_mozjs_authenticated_native.py"),
                "--profile", "native-owner", "--upstream", str(self.root / canary),
                "--original-lock", str(self.path), "--archive", str(self.path), "--bundle", str(self.path),
                "--tool", str(self.path), "--target-parent", str(self.root)]
        completed = subprocess.run(argv, env=dict(os.environ, MOZJS_FROM_SOURCE=canary),
                                   capture_output=True, timeout=5)
        self.assertEqual(completed.returncode, 1)
        self.assertEqual(completed.stderr, b"MOZJS_AUTHENTICATED_INPUT_REFUSED\n")
        self.assertNotIn(canary.encode(), completed.stdout + completed.stderr)

    def test_actual_both_cli_argument_failures_do_not_print_unknown_secret_selectors(self):
        canary = "credential-58302-秘密-path"
        for name in ["build_mozjs_authenticated_native.py", "verify_mozjs_authenticated_input.py"]:
            completed = subprocess.run([sys.executable, str(m.ROOT / "tools" / name), "--unreviewed", canary],
                                       capture_output=True, timeout=5)
            self.assertEqual(completed.returncode, 2)
            self.assertEqual(completed.stderr, b"MOZJS_AUTHENTICATED_INPUT_REFUSED\n")
            self.assertEqual(completed.stdout, b"")

    def test_fault_injected_unresolved_shutdown_retains_all_live_inputs(self):
        # This injects the unresolved owner status after a real child was
        # reaped. It tests retention semantics, not a real escaped daemon.
        held = self.held(); previous = len(m.original._PENDING_SHUTDOWNS)
        stop = m._VerifierProcess.stop
        def unresolved(owner, *args):
            stop(owner, *args); owner.stopped = False; raise RuntimeError("host fault injected unresolved")
        try:
            with patch.object(m._VerifierProcess, "stop", unresolved), self.assertRaises(RuntimeError):
                m._run_verifier(held, [sys.executable, "-c", "pass"], self.root, {}, 5, .1)
            self.assertEqual(len(m.original._PENDING_SHUTDOWNS), previous + 1)
            owner = m.original._PENDING_SHUTDOWNS[-1]
            self.assertIs(owner.lease, held); self.assertTrue(held._active)
            with self.assertRaises(ValueError): held.close()
            for lease in held._leases.values(): os.fstat(lease._owner.fd)
            self.assertFalse(m.original._group_exists(owner.process.pid))
        finally:
            del m.original._PENDING_SHUTDOWNS[previous:]
            held._active = False; held.close()

    def test_real_private_readonly_snapshot_distinct_inode_and_capability_drop_across_exec(self):
        # This is an ordinary kernel delivery fixture, not official gh or a
        # cryptographic receipt. The separate official actual cases use policy.
        code = r'''import json,os,pathlib,sys
sys.path.insert(0,sys.argv[1])
from tools import mozjs_authenticated_input as m
fd,evidence,size,digest=int(sys.argv[2]),pathlib.Path(sys.argv[3]),int(sys.argv[4]),sys.argv[5]
directory,fact=m._namespace_snapshot(fd,evidence,size,digest)
m._drop_namespace_privilege()
script="import json,os,pathlib,sys;status=dict(line.split(':',1) for line in pathlib.Path('/proc/self/status').read_text().splitlines() if ':' in line);raw=pathlib.Path(sys.argv[1]).read_bytes();print(json.dumps({'bytes':len(raw),'sha256':__import__('hashlib').sha256(raw).hexdigest(),'caps':{k:int(status[k].strip(),16) for k in ['CapEff','CapPrm','CapInh','CapAmb','CapBnd']},'nnp':status['NoNewPrivs'].strip()}))"
path=f'/proc/self/fd/{directory}/bundle.json'
pathlib.Path(evidence/'host-snapshot.json').write_text(json.dumps(fact))
os.execve(sys.executable,[sys.executable,'-c',script,path],dict(os.environ))
'''
        lease = self.lease()
        try:
            evidence = m._new_directory(self.root, "kernel-snapshot-")
            child = subprocess.run([sys.executable, "-c", code, str(m.ROOT), str(lease._owner.fd),
                                    str(evidence), str(len(self.raw)), self.digest],
                                   pass_fds=(lease._owner.fd,), capture_output=True, timeout=10)
            self.assertEqual(child.returncode, 0, child.stderr)
            result = json.loads(child.stdout); fact = json.loads((evidence / "host-snapshot.json").read_bytes())
            self.assertEqual(result["sha256"], self.digest); self.assertEqual(result["bytes"], len(self.raw))
            self.assertEqual(result["caps"], {name: 0 for name in ["CapEff", "CapPrm", "CapInh", "CapAmb", "CapBnd"]})
            self.assertEqual(result["nnp"], "1"); self.assertEqual(fact["snapshot"]["write_errno"], 30)
            self.assertFalse(fact["snapshot"]["same_original_memfd_inode"])
            self.assertFalse(fact["snapshot"]["four_seals_on_consuming_inode_claimed"])
            self.assertEqual(lease.readback()["sha256"], self.digest)
        finally: lease.close()

    def test_private_worker_unknown_invocation_refuses_without_payload(self):
        child = subprocess.run([sys.executable, str(Path(m.__file__)), "caller-proof-secret"],
                               capture_output=True, timeout=5)
        self.assertEqual(child.returncode, 1); self.assertEqual(child.stdout, b"")
        self.assertEqual(child.stderr, b"MOZJS_AUTHENTICATED_INPUT_REFUSED\n")


class BuildDirectoryHostCallchainTests(unittest.TestCase):
    """Explicit private preparation/crypto/compile substitutions, no authority.

    Real ordinary children run through the complete build entry. These tests
    establish cwd and diagnostic routing, never official verification or Cargo
    archive consumption. All earlier test bodies remain unchanged.
    """

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="mozjs-build-cwd-host-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.upstream = self.root / "checked-upstream"; self.upstream.mkdir()
        self.parent = self.root / "private-target-parent"; self.parent.mkdir()
        self.marker = b"ordinary host cwd marker; not a Cargo manifest"
        (self.upstream / "Cargo.toml").write_bytes(self.marker)
        self.input = self.root / "input"; self.raw = b"ordinary sealed host callchain fixture"
        self.input.write_bytes(self.raw); self.digest = hashlib.sha256(self.raw).hexdigest()

    def held(self):
        value = m._InputSet()
        try:
            for name in ("archive", "bundle", "tool"):
                value._leases[name] = m._seal_input(self.input, len(self.raw), self.digest, m.MAX_BUNDLE_BYTES)
            return value
        except BaseException: value.close(); raise

    def test_complete_build_callchain_real_child_uses_checked_upstream_separate_from_evidence(self):
        before = descriptors(); held = self.held(); observed = []; phases = []
        helper = m._run_verifier
        code = ("import hashlib,json,os,pathlib;"
                "print(json.dumps({'cwd':os.getcwd(),"
                "'source_marker_sha256':hashlib.sha256(pathlib.Path('Cargo.toml').read_bytes()).hexdigest(),"
                "'held_archive_sha256':hashlib.sha256(pathlib.Path(os.environ['MOZJS_ARCHIVE']).read_bytes()).hexdigest(),"
                "'target_initially_empty':not list(pathlib.Path(os.environ['CARGO_TARGET_DIR']).iterdir())}));"
                "raise SystemExit(7)")
        def private_stage(held_inputs, argv, evidence, environment, *limits, **kwargs):
            if len(argv) > 2 and "b.verify_prepared(" in argv[2]:
                # This actual child substitutes only the source-validation
                # stage. It is deliberately not an exact-PIN verification.
                self.assertEqual(argv[4], str(self.upstream))
                phases.append("synthetic-preparation-with-real-child")
                return helper(held_inputs, [sys.executable, "-c", "print('ordinary preparation stage')"],
                              evidence, environment, *limits, **kwargs)
            phases.append("real-final-host-child")
            self.assertEqual(limits, (10800, 5))
            self.assertEqual(kwargs["cwd"], self.upstream)
            rc, stdout, stderr = helper(held_inputs, argv, evidence, environment, *limits, **kwargs)
            observed.append((evidence, json.loads(stdout), rc, stderr))
            return rc, stdout, stderr
        def synthetic_crypto(*args):
            phases.append("synthetic-crypto-only")
            return {"private_fault_fixture_only": True}
        with patch.dict(os.environ, {}, clear=True), \
             patch.object(m, "_admit_inputs", return_value=held), \
             patch.object(m, "_authenticate", synthetic_crypto), \
             patch.object(m.original, "compile_argv", return_value=[sys.executable, "-c", code]), \
             patch.object(m, "_run_verifier", private_stage):
            result = b.build_authenticated_native(self.upstream, self.input, self.input, self.input,
                                                  self.input, self.parent, "native-owner")
        self.assertEqual(phases, ["synthetic-preparation-with-real-child", "synthetic-crypto-only", "real-final-host-child"])
        self.assertEqual(result["cargo_returncode"], 7)
        self.assertFalse(result["actual_cargo_archive_consumption_proven"])
        evidence, actual, rc, stderr = observed[0]
        self.assertEqual((rc, stderr), (7, b""))
        self.assertEqual(actual["cwd"], str(self.upstream))
        self.assertEqual(actual["source_marker_sha256"], hashlib.sha256(self.marker).hexdigest())
        self.assertEqual(actual["held_archive_sha256"], self.digest)
        self.assertTrue(actual["target_initially_empty"])
        self.assertNotEqual(evidence, self.upstream)
        self.assertEqual((evidence / "stdout.raw").read_bytes(), json.dumps(actual).encode() + b"\n")
        process = json.loads((evidence / "actual-process.json").read_bytes())
        self.assertEqual(process["working_directory"], str(self.upstream))
        self.assertTrue(process["ordinary_group_ended"])
        self.assertFalse(m.original._group_exists(process["pid"]))
        self.assertEqual(descriptors(), before)
        for lease in held._leases.values(): self.assertIsNone(lease._owner.fd)

    def test_real_nonzero_preparation_child_stops_before_crypto_and_final_target(self):
        held = self.held(); helper = m._run_verifier; phases = []
        def private_preparation(held_inputs, argv, evidence, environment, *limits, **kwargs):
            self.assertIn("b.verify_prepared(", argv[2]); phases.append("preparation-only")
            return helper(held_inputs, [sys.executable, "-c", "raise SystemExit(17)"],
                          evidence, environment, *limits, **kwargs)
        with patch.dict(os.environ, {}, clear=True), \
             patch.object(m, "_admit_inputs", return_value=held), \
             patch.object(m, "_authenticate") as crypto, \
             patch.object(m, "_run_verifier", private_preparation), self.assertRaises(ValueError):
            b.build_authenticated_native(self.upstream, self.input, self.input, self.input,
                                         self.input, self.parent, "native-owner")
        self.assertEqual(phases, ["preparation-only"]); crypto.assert_not_called()
        self.assertEqual(list(self.parent.glob("mozjs-authenticated-empty-*")), [])
        for lease in held._leases.values(): self.assertIsNone(lease._owner.fd)

    def test_default_verifier_cwd_stays_private_evidence_and_relative_cwd_refused(self):
        held = self.held()
        try:
            evidence = m._new_directory(self.parent, "default-evidence-")
            rc, stdout, _ = m._run_verifier(held, [sys.executable, "-c", "import os;print(os.getcwd())"],
                                          evidence, {}, 5, .1)
            self.assertEqual(rc, 0); self.assertEqual(stdout.decode().strip(), str(evidence))
            self.assertEqual(json.loads((evidence / "actual-process.json").read_bytes())["working_directory"], str(evidence))
            with self.assertRaises(ValueError):
                m._run_verifier(held, [sys.executable, "-c", "pass"], evidence, {}, 5, .1, cwd=Path("relative"))
            self.assertEqual(len(held.readback()), 3)
        finally: held.close()

    def test_public_build_cannot_select_execution_cwd(self):
        with self.assertRaises(TypeError):
            b.build_authenticated_native(self.upstream, self.input, self.input, self.input,
                                         self.input, self.parent, "native-owner", cwd=self.parent)


class BuildDirectoryContainmentTests(unittest.TestCase):
    """Real path aliases must refuse before input admission or allocation."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="mozjs-build-containment-host-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.upstream = self.root / "upstream"; self.upstream.mkdir()
        self.descendant = self.upstream / "nested"; self.descendant.mkdir()
        self.parent = self.root / "external"; self.parent.mkdir()
        self.bridge = self.root / "bridge"; self.bridge.mkdir()

    def refused_without_allocation(self, upstream, parent):
        before = {str(path.relative_to(self.root)) for path in self.root.rglob("*")}
        with patch.dict(os.environ, {}, clear=True), \
             patch.object(m, "_admit_inputs") as admit, \
             patch.object(m, "_new_directory") as allocate, self.assertRaises(ValueError):
            b.build_authenticated_native(upstream, self.root / "not-read", self.root / "not-read",
                                         self.root / "not-read", self.root / "not-read", parent, "native-owner")
        admit.assert_not_called(); allocate.assert_not_called()
        self.assertEqual({str(path.relative_to(self.root)) for path in self.root.rglob("*")}, before)

    def test_target_parent_dotdot_same_source_and_descendant_refuse_before_allocation(self):
        for parent in (self.bridge / ".." / "upstream", self.bridge / ".." / "upstream" / "nested"):
            with self.subTest(parent=parent): self.refused_without_allocation(self.upstream, parent)

    def test_upstream_dotdot_alias_cannot_hide_containment(self):
        self.refused_without_allocation(self.bridge / ".." / "upstream", self.descendant)

    def test_external_dotdot_selector_is_explicitly_noncanonical_and_refuses(self):
        self.refused_without_allocation(self.upstream, self.bridge / ".." / "external")

    def test_symlink_directory_aliases_refuse_before_allocation(self):
        source_alias = self.root / "source-alias"; source_alias.symlink_to(self.upstream, target_is_directory=True)
        target_alias = self.root / "target-alias"; target_alias.symlink_to(self.parent, target_is_directory=True)
        self.refused_without_allocation(source_alias, self.descendant)
        self.refused_without_allocation(self.upstream, target_alias)

    def test_canonical_source_and_descendant_target_remain_refused(self):
        for parent in (self.upstream, self.descendant):
            with self.subTest(parent=parent): self.refused_without_allocation(self.upstream, parent)


if __name__ == "__main__": unittest.main()
