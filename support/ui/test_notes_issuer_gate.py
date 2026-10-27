"""Pure shape/receipt fixtures only: no cryptographic or product qualification."""
import copy
import json
import unittest
from notes_fault_contract import Refused, digest
from notes_issuer_gate_contract import IssuerTransaction, raw_member, OPERATION
import notes_issuer_gate_receipts as receipts


def encode(value):
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode()


def original():
    bound = dict(subject_id="original:agentd", destination_id="trill.notes:abc:3:def",
                 request_sha256=[1]*32, scope_sha256=[2]*32, payload_sha256=[3]*32)
    select = {key:bound[key] for key in ("subject_id", "destination_id", "scope_sha256")}
    select["exact_binding"] = None
    request = dict(schema_version=1, operation=OPERATION, binding=bound)
    grant = dict(schema_version=1, signer_id="root:original", authority_epoch=3, grant_id="original:grant:1",
                 nonce=[4]*32, binding=bound, not_before_unix_ms=1000, expires_at_unix_ms=2000)
    signed = dict(grant=grant, signature=[7]*64)  # shape fixture, NOT a signature
    head = dict(authority_epoch=3, revision=8, revoked_grant_ids=["older:grant"])
    return select, request, dict(schema_version=1, revocations=head, grant=signed, denial_reason=None)


def capture_pair():
    select, request, response = original(); tx = IssuerTransaction(select)
    raw=encode(request); frame=len(raw).to_bytes(4,"big")+raw
    tx.received(frame[:1],50.0); tx.received(frame[1:3],50.01); tx.received(frame[3:],50.02)
    body=encode(response); prefix=len(body).to_bytes(4,"big")
    tx.write_entry(prefix[:1],1); tx.write_exit(1); tx.write_entry(prefix[1:],3); tx.write_exit(3)
    return tx, body


def all_receipts(capture):
    grant=capture["signed"]["grant"]; bound=capture["binding"]
    instance=dict(boot_id="original-boot",root_pid=1234,process_start_ticks=77,episode_nonce=[4]*32)
    mirror=dict(status="issued_notes_grant_observed",instance=instance,observation=dict(status="captured",
        selection_scope="volatile_original_notes_issue_artifact",signed_grant_json=capture["signed_raw"].decode(),
        signed_grant_sha256=capture["signed_grant_sha256"],observation_attempt=1,delivery_observed=False,effect_observed=False))
    lease=dict(schema_version=1,lease_id="original:effect",authority_epoch=3,revision=1,
        binding=dict(principal_id=bound["subject_id"],operation_class=OPERATION,destination_id=bound["destination_id"],
                     scope_sha256=bound["scope_sha256"],payload_sha256=bound["payload_sha256"]),
        issued_at_unix_ms=900,expires_at_unix_ms=2200)
    def sync(rev):
        return dict(state="confirmed",device_frontier=dict(authority_epoch=3,revocation_revision=rev,state_sha256=[8]*32),
                    notes_frontier=dict(authority_epoch=3,revocation_revision=rev,state_sha256=[9]*32))
    before=dict(status="original_notes_grant_observed",instance=instance,original_grant_id=grant["grant_id"],
        effect_lease=dict(lease=lease,store_revision=10),effect_revocation=None,
        lease_frontier=dict(authority_epoch=3,store_revision=10,state_sha256=[5]*32),
        final_use_head=capture["head"],grant_expired=False,synchronization=sync(8))
    receipt=dict(lease_id=lease["lease_id"],authority_epoch=3,previous_lease_revision=1,lease_revision=2,
                 store_revision=11,reason_sha256=[6]*32,revoked_at_unix_ms=1500)
    next_head=dict(authority_epoch=3,revision=9,revoked_grant_ids=sorted(["older:grant",grant["grant_id"]]))
    mutation=dict(status="original_notes_grant_revocation",instance=instance,original_grant_id=grant["grant_id"],
                  effect_lease_receipt=receipt,final_use_head=next_head,synchronization=sync(9))
    after=copy.deepcopy(before); after.update(final_use_head=next_head,synchronization=sync(9))
    after["effect_lease"]["lease"]["revision"]=2
    after["effect_lease"]["store_revision"]=after["lease_frontier"]["store_revision"]=11
    rev=dict(receipt); del rev["previous_lease_revision"]
    after["effect_revocation"]=dict(revocation=dict(schema_version=1,**rev))
    return instance,mirror,before,mutation,after


class GateContractTests(unittest.TestCase):
    def test_original_bytes_and_four_sent_header_zero_body(self):
        tx,body=capture_pair(); c=tx.write_entry(body,len(body))
        self.assertEqual(c["response_raw"],body); self.assertEqual(c["signed_raw"],encode(json.loads(body)["grant"]))
        self.assertEqual(c["request_sha256"],digest(c["request_raw"]))
        self.assertFalse(c["fresh_or_unspent_proven_by_parser"]); self.assertEqual(tx.body_sent,0)
        self.assertEqual(len(tx.header),4)

    def test_raw_nested_member_keeps_whitespace_and_unicode(self):
        raw=b' \n {"first":1,"grant" : { "x":"\\u4e2d", "n" : [1,2] },"tail":2}'
        self.assertEqual(raw_member(raw,"grant"),b'{ "x":"\\u4e2d", "n" : [1,2] }')

    def test_partial_start_and_partial_body_refused(self):
        select,request,_=original()
        with self.assertRaisesRegex(Refused,"not_original_first_byte"): IssuerTransaction(select).received(encode(request),0)
        tx,body=capture_pair()
        with self.assertRaisesRegex(Refused,"not_complete_first_grant_body"): tx.write_entry(body[:1],1)

    def test_exact_binding_mismatch_refused(self):
        select,request,_=original(); select["exact_binding"]=copy.deepcopy(request["binding"])
        request["binding"]["request_sha256"][0]=4; raw=encode(request); frame=len(raw).to_bytes(4,"big")+raw
        tx=IssuerTransaction(select); tx.received(frame[:1],0)
        with self.assertRaisesRegex(Refused,"exact_mismatch"): tx.received(frame[1:],0)

    def test_other_policy_passes_without_capture(self):
        select,request,response=original(); select["subject_id"]="another:agentd"
        tx=IssuerTransaction(select); raw=encode(request); frame=len(raw).to_bytes(4,"big")+raw
        tx.received(frame[:1],0); tx.received(frame[1:],0); body=encode(response)
        tx.write_entry(len(body).to_bytes(4,"big"),4); tx.write_exit(4)
        self.assertIsNone(tx.write_entry(None,len(body))); tx.write_exit(len(body))
        self.assertEqual(tx.completed_other_frames,1)

    def test_duplicate_unknown_denial_and_pre_revoked_refused(self):
        _,_,response=original(); revoked=copy.deepcopy(response)
        revoked["revocations"]["revoked_grant_ids"]=[revoked["grant"]["grant"]["grant_id"]]
        variants=[encode(response).replace(b'"schema_version":1',b'"schema_version":1,"schema_version":1',1),
                  encode(dict(response,unknown=True)),encode(dict(response,grant=None,denial_reason="refused")),encode(revoked)]
        for raw in variants:
            with self.subTest(sha=digest(raw)):
                tx,_=capture_pair(); tx.response_length=len(raw)
                with self.assertRaises(Refused): tx.write_entry(raw,len(raw))

    def test_grant_epoch_nonce_time_binding_and_signature_shape_rejected(self):
        mutators=[lambda g:g["grant"].update(authority_epoch=4),lambda g:g["grant"].update(nonce=[0]*32),
                  lambda g:g["grant"].update(expires_at_unix_ms=1000),lambda g:g.update(signature=[1]*63),
                  lambda g:g["grant"]["binding"].update(payload_sha256=[9]*32)]
        for mutate in mutators:
            tx,body=capture_pair(); response=json.loads(body); mutate(response["grant"]); raw=encode(response)
            tx.response_length=len(raw)
            with self.assertRaises(Refused): tx.write_entry(raw,len(raw))

    def test_same_root_full_chain_and_distinct_valid_consumer_nonce_histories(self):
        tx,body=capture_pair(); c=tx.write_entry(body,len(body)); i,m,b,r,a=all_receipts(c)
        receipts.mirror(m,c,i); receipts.before_revoke(b,c,i)
        receipts.revoked(r,c,i,b,"06"*32); receipts.after_revoke(a,c,i,b,r)

    def test_mirror_requires_actual_bytes_not_reserialization(self):
        tx,body=capture_pair(); c=tx.write_entry(body,len(body)); i,m,*_=all_receipts(c)
        m["observation"]["signed_grant_json"]=json.dumps(c["signed"])
        with self.assertRaisesRegex(Refused,"mirror_bytes"): receipts.mirror(m,c,i)

    def test_unknown_pending_expired_wrong_root_binding_and_cas_refused(self):
        tx,body=capture_pair(); c=tx.write_entry(body,len(body)); i,_,b,r,a=all_receipts(c)
        checks=[(b,lambda v:v.update(grant_expired=True),lambda v:receipts.before_revoke(v,c,i)),
            (b,lambda v:v["instance"]["episode_nonce"].__setitem__(0,2),lambda v:receipts.before_revoke(v,c,i)),
            (b,lambda v:v["effect_lease"]["lease"]["binding"].update(payload_sha256=[1]*32),lambda v:receipts.before_revoke(v,c,i)),
            (r,lambda v:v.update(final_use_head=None),lambda v:receipts.revoked(v,c,i,b,"06"*32)),
            (r,lambda v:v.update(synchronization={"state":"pending","reason":"not synced"}),lambda v:receipts.revoked(v,c,i,b,"06"*32)),
            (r,lambda v:v["effect_lease_receipt"].update(revoked_at_unix_ms=2000),lambda v:receipts.revoked(v,c,i,b,"06"*32)),
            (r,lambda v:v["effect_lease_receipt"].update(previous_lease_revision=2),lambda v:receipts.revoked(v,c,i,b,"06"*32)),
            (a,lambda v:v["synchronization"]["notes_frontier"].update(revocation_revision=8),lambda v:receipts.after_revoke(v,c,i,b,r)),
            (a,lambda v:v["effect_revocation"]["revocation"].update(reason_sha256=[7]*32),lambda v:receipts.after_revoke(v,c,i,b,r))]
        for initial,mutate,check in checks:
            value=copy.deepcopy(initial); mutate(value)
            with self.subTest(change=mutate):
                with self.assertRaises(Refused): check(value)

class GateUnwindTests(unittest.TestCase):
    """Dependency controls only; no actual Root, pidfd or ptrace is selected."""

    def run_selected_control(self, failure=None, *, real_wait_timeout=False,
                             verify_failure=None, shutdown_failure=None, selector_failure=False):
        import os
        from pathlib import Path
        import socket
        import subprocess
        import sys
        import tempfile
        import time
        import types
        from unittest.mock import patch
        import notes_issuer_gate_admin as admin_module
        import notes_issuer_gate_controller as controller

        events, children, actual_errors = [], [], []
        capture_tx, body = capture_pair()
        capture = capture_tx.write_entry(body, len(body))

        class Held:
            identity = {}
            def __init__(self, _): pass
            def verify(self, **_): pass
            def close(self): pass

        class Channel:
            fd = 44
            identity = types.SimpleNamespace(st_ino=6)
            def __init__(self): self.socket = self
            def shutdown(self, how):
                events.append(("shutdown", how))
                if shutdown_failure is not None: raise shutdown_failure
            def verify(self):
                if verify_failure is not None: raise verify_failure
            def close(self): pass

        class Trace:
            def __init__(self, *_):
                self.attached = self.stopped = self.issuer_body_held = True
                self.cleanup_failed = False
                self.events = []
                self.stops = 1
                self.total_pause = self.max_pause = self.omitted_events = 0
            def verify(self): pass
            def close(self):
                if self.attached:
                    events.append(("detach",))
                    self.events.append({"detached_monotonic": time.monotonic()})
                self.attached = self.stopped = False

        def scan(trace, *_):
            trace.selected_capture = capture
            return capture, time.monotonic() + .4

        with tempfile.TemporaryDirectory(prefix="trill-issuer-unwind-control-") as temporary:
            directory = Path(temporary)
            with open(sys.executable, "rb") as executable:
                admin = admin_module.OriginalRootAdmin.__new__(admin_module.OriginalRootAdmin)
                admin.instance, admin.steps, admin.mutation_attempted = {}, [], False
                admin.output = directory / "run"
                admin.cli = types.SimpleNamespace(fd=executable.fileno())
                admin.descriptor = types.SimpleNamespace(path=directory / "fixture-unused-instance")
                admin.verify = lambda: None
                admin.close = lambda: None
                original_popen = subprocess.Popen

                def start_owned_child(*_, **__):
                    # Only this current-UID Python child runs. It closes its own
                    # output pipes, then remains alive to exercise Popen.wait's
                    # real TimeoutExpired (not a fake CLI/Root response).
                    child = original_popen([sys.executable, "-I", "-B", "-c",
                        "import os,time;os.close(1);os.close(2);time.sleep(2)"],
                        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE, close_fds=True)
                    children.append(child)
                    return child

                def revoke(_, __, end, cancelled):
                    admin.mutation_attempted = True
                    if real_wait_timeout or selector_failure:
                        try:
                            return admin.call("owned-child-timeout", [], end, cancelled)
                        except BaseException as error:
                            actual_errors.append(type(error))
                            raise
                    raise failure

                admin.revoke_held_original = revoke
                bound = dict(root={}, agentd={}, desktop_commit="a"*40, hepta_commit="b"*40,
                             issuer_path="fixture-unused", request_timeout_ms=500,
                             selector=original()[0], reason_sha256="06"*32)
                patches = [patch.object(controller.os, "getuid", return_value=0),
                    patch.object(controller.os, "geteuid", return_value=0),
                    patch.object(controller, "private_parent"),
                    # These are dependency controls for unwind ordering. Avoid
                    # unrelated fixture fsync latency consuming the fake scan's
                    # finite budget before the real child wait is reached.
                    # Production writes and its original deadline are unchanged.
                    patch.object(controller, "write_new", side_effect=lambda path, raw: path.write_bytes(raw)),
                    patch.object(controller, "HeldProcess", Held),
                    patch.object(controller, "OriginalRootAdmin", return_value=admin),
                    patch.object(controller, "select_issuer", return_value=(1, (271, []), Channel(), 1)),
                    patch.object(controller, "IssuerTrace", Trace),
                    patch.object(controller, "scan_to_grant", scan)]
                if real_wait_timeout or selector_failure:
                    patches.append(patch.object(admin_module.subprocess, "Popen", side_effect=start_owned_child))
                if selector_failure:
                    patches.append(patch.object(admin_module.selectors, "DefaultSelector",
                                                side_effect=RuntimeError("fixture selector setup")))
                for selected in patches: selected.start()
                try:
                    result = controller.run(bound, directory / "run", 1, lambda: False)
                finally:
                    for selected in reversed(patches): selected.stop()
            self.assertEqual(result["status"], "outcome_unknown")
            self.assertTrue(result["mutation_attempted"])
            self.assertEqual(result["body_shutdown"], verify_failure is None and shutdown_failure is None)
            self.assertTrue(result["selected_body_resumed_on_cleanup"])
            if verify_failure is not None or shutdown_failure is not None:
                self.assertIn("shutdown_reason", result)
            self.assertFalse(result["body_released"])
            self.assertFalse(result["product_qualified"])
            self.assertFalse(result["consumer_first_use_revoked_proven"])
            expected_events = ([] if verify_failure is not None else [("shutdown", socket.SHUT_WR)]) + [("detach",)]
            self.assertEqual(events, expected_events)
            self.assertTrue(result["tool_source_unchanged"])
            for child in children:
                self.assertIsNotNone(child.returncode)
                with self.assertRaises(ChildProcessError): os.waitpid(child.pid, os.WNOHANG)
            return actual_errors

    def test_all_catchable_unwinds_shutdown_the_selected_body_before_detach(self):
        import subprocess
        for failure in (subprocess.TimeoutExpired("fixture", 0), RuntimeError("fixture"),
                        KeyError("fixture"), KeyboardInterrupt(), SystemExit(7)):
            with self.subTest(exception=type(failure).__name__):
                self.run_selected_control(failure)

    def test_shutdown_or_verification_failure_cannot_claim_zero_body_or_success(self):
        self.run_selected_control(RuntimeError("fixture abort"), verify_failure=RuntimeError("fixture verify"))
        self.run_selected_control(RuntimeError("fixture abort"), shutdown_failure=RuntimeError("fixture shutdown"))

    def test_real_owned_child_is_reaped_if_selector_setup_raises(self):
        self.assertEqual(self.run_selected_control(selector_failure=True), [RuntimeError])

    def test_real_owned_child_wait_timeout_is_unknown_and_reaped(self):
        import subprocess
        self.assertEqual(self.run_selected_control(real_wait_timeout=True), [subprocess.TimeoutExpired])

class GateSourceCacheTests(unittest.TestCase):
    """CLI source-cache controls in disposable copies, without Root operations."""

    def cache_case(self, entry_name, module_name, mode):
        import importlib.util
        from pathlib import Path
        import py_compile
        import shutil
        import subprocess
        import sys
        import tempfile
        source = Path(__file__).resolve().parent
        modules = ("notes_fault_contract.py", "notes_fault_linux.py",
                   "notes_issuer_gate_contract.py", "notes_issuer_gate_receipts.py",
                   "notes_issuer_gate_linux.py", "notes_issuer_gate_admin.py",
                   "notes_issuer_gate_controller.py", "test_notes_issuer_gate.py")
        fixtures = ("notes_issuer_gate_kernel_fixture.py", "notes_issuer_gate_cleanup_fixture.py")
        with tempfile.TemporaryDirectory(prefix="trill-issuer-cache-control-") as temporary:
            root = Path(temporary)
            copied = root / "support/ui"
            (copied / "qualification").mkdir(parents=True)
            for member in modules: shutil.copyfile(source / member, copied / member)
            for member in fixtures:
                shutil.copyfile(source / "qualification" / member, copied / "qualification" / member)
            poison = root / "untrusted.py"
            poison.write_text('raise RuntimeError("ignored-issuer-cache-must-not-execute")\n')
            actual_source = copied / module_name
            cached = Path(importlib.util.cache_from_source(str(actual_source)))
            cached.parent.mkdir(exist_ok=True)
            py_compile.compile(str(poison), cfile=str(cached), doraise=True,
                               invalidation_mode=mode)
            if mode == py_compile.PycInvalidationMode.TIMESTAMP:
                raw = bytearray(cached.read_bytes())
                info = actual_source.stat()
                raw[8:12] = int(info.st_mtime).to_bytes(4, "little")
                raw[12:16] = info.st_size.to_bytes(4, "little")
                cached.write_bytes(raw)
            entry = copied / entry_name
            command = [sys.executable, "-I", "-B", *(["-O"] * sys.flags.optimize), str(entry), "--help"]
            protected = subprocess.run(command, capture_output=True)
            self.assertEqual(protected.returncode, 0, protected.stderr)
            text = entry.read_text()
            weakened = text.replace("sys.pycache_prefix = _source_cache", "sys.pycache_prefix = _old_cache")
            self.assertNotEqual(text, weakened)
            # Only the disposable negative copy: remove all entry guards so
            # an inner controller guard cannot mask an outer fixture failure.
            # This establishes that -B alone still reads the poisoned cache.
            for relative in ("notes_issuer_gate_controller.py", *("qualification/" + name for name in fixtures)):
                local = copied / relative
                local.write_text(local.read_text().replace("sys.pycache_prefix = _source_cache",
                                                         "sys.pycache_prefix = _old_cache"))
            if mode == py_compile.PycInvalidationMode.TIMESTAMP:
                # If the poisoned module itself is an entry, guard removal
                # changed its size. Keep the negative cache timestamp-valid.
                raw = bytearray(cached.read_bytes())
                info = actual_source.stat()
                raw[8:12] = int(info.st_mtime).to_bytes(4, "little")
                raw[12:16] = info.st_size.to_bytes(4, "little")
                cached.write_bytes(raw)
            negative = subprocess.run(command, capture_output=True)
            self.assertNotEqual(negative.returncode, 0)
            self.assertIn(b"ignored-issuer-cache-must-not-execute", negative.stderr)

    def test_controller_complete_import_closure_ignores_valid_cache(self):
        import py_compile
        for module in ("notes_fault_contract.py", "notes_fault_linux.py", "notes_issuer_gate_contract.py",
                       "notes_issuer_gate_receipts.py", "notes_issuer_gate_linux.py", "notes_issuer_gate_admin.py"):
            for mode in (py_compile.PycInvalidationMode.TIMESTAMP, py_compile.PycInvalidationMode.UNCHECKED_HASH):
                with self.subTest(module=module, mode=mode.name):
                    self.cache_case("notes_issuer_gate_controller.py", module, mode)

    def test_fixture_complete_import_closures_ignore_valid_cache(self):
        import py_compile
        entries = {
            "qualification/notes_issuer_gate_kernel_fixture.py": ("notes_fault_contract.py", "notes_fault_linux.py",
                "notes_issuer_gate_contract.py", "notes_issuer_gate_receipts.py", "notes_issuer_gate_linux.py",
                "notes_issuer_gate_admin.py", "notes_issuer_gate_controller.py", "test_notes_issuer_gate.py"),
            "qualification/notes_issuer_gate_cleanup_fixture.py": ("notes_fault_contract.py", "notes_fault_linux.py",
                "notes_issuer_gate_linux.py"),
        }
        for entry, modules in entries.items():
            for module in modules:
                for mode in (py_compile.PycInvalidationMode.TIMESTAMP, py_compile.PycInvalidationMode.UNCHECKED_HASH):
                    with self.subTest(entry=entry, module=module, mode=mode.name):
                        self.cache_case(entry, module, mode)


class GateCliImageTests(unittest.TestCase):
    def test_only_the_held_live_process_image_is_the_original_cli(self):
        # A real current-UID process/image control, never a product Root. Only
        # the descriptor verifier is a shim; both ELF files and pidfd are real.
        import hashlib
        import os
        from pathlib import Path
        import platform
        import types
        import notes_issuer_gate_admin as admin_module
        from notes_fault_linux import HeldProcess, proc_identity
        if platform.system() != "Linux" or platform.machine() != "x86_64":
            self.skipTest("Linux x86_64 original gate image contract")
        process = proc_identity(os.getpid())
        executable = Path("/proc/self/exe").resolve(strict=True)
        other = Path("/usr/bin/true").resolve(strict=True)
        original_sha = hashlib.sha256(executable.read_bytes()).hexdigest()
        held = HeldProcess(dict(pid=os.getpid(), start_ticks=process["start_ticks"],
            uid=os.getuid(), gid=os.getgid(), executable=str(executable), sha256=original_sha))
        try:
            same = admin_module.RootFile(executable, 128*1024*1024, expected_sha=original_sha)
            different = admin_module.RootFile(other, 128*1024*1024,
                expected_sha=hashlib.sha256(other.read_bytes()).hexdigest())
            try:
                actual = admin_module.OriginalRootAdmin.__new__(admin_module.OriginalRootAdmin)
                actual.root = held
                actual.descriptor = types.SimpleNamespace(verify=lambda: None)
                actual.cli = same
                actual.verify()
                actual.cli = different
                with self.assertRaisesRegex(Refused, "admin_cli_not_held_root_image"):
                    actual.verify()
                actual.cli = same
                actual.verify()  # Failed selection cannot replace either held image.
            finally:
                different.close(); same.close()
        finally:
            held.close()


if __name__=="__main__": unittest.main()
