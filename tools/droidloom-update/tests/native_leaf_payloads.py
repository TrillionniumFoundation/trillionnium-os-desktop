"""Pure tests for the source-owned Settings transaction and real argv shape.

No Android command, namespace entry, helper binary or native leaf is executed.
Only local temporary fixtures and the current process's read-only ns FDs are used.
"""
import argparse
import ast
import contextlib
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import struct
import tempfile
import textwrap
import time
import types
import unittest

ARGS = argparse.ArgumentParser()
ARGS.add_argument("--cohort", required=True, type=Path)
OPTIONS, REMAINING = ARGS.parse_known_args()
ROOT = OPTIONS.cohort

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

ROUNDTRIP = load("source_owned_font_scale", ROOT / "source/settings/settings_roundtrip.py")
POLICY = load("source_owned_settings_policy", ROOT / "source/settings/settings_policy.py")

def varint(value):
    out = bytearray()
    while value >= 128:
        out.append((value & 127) | 128); value >>= 7
    out.append(value); return bytes(out)

def blob(number, value):
    return varint((number << 3) | 2) + varint(len(value)) + value

def proto(scale=1.0, other=b"\x10\x01"):
    config = b"\x0d" + struct.pack("<f", scale) + other
    return blob(1, blob(1, config) + b"\x10\xa0\x01")

class Files:
    STACKS = ["/system/bin/cmd", "activity", "stacks", "list"]
    @staticmethod
    def need(ok, code):
        if not ok: raise RuntimeError(code)
    @staticmethod
    def regular(path, contents=False):
        raw = Path(path).read_bytes()
        return {"path": str(path), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    @staticmethod
    def read_ref(pin):
        raw = Path(pin["path"]).read_bytes()
        assert len(raw) == pin["bytes"] and hashlib.sha256(raw).hexdigest() == pin["sha256"]
        return raw
    @staticmethod
    def parse(raw): return json.loads(raw)
    @staticmethod
    @contextlib.contextmanager
    def locked(path):
        assert path == "/run/lock/android-digitalis-actions.lock"
        yield

class Session:
    def __init__(self, root, value):
        self.root = root
        self.original_value = value
        self.profile = types.SimpleNamespace(PACKAGE="com.android.settings")
        self.value = value
        self.scale = ROUNDTRIP.provider_value(self.raw_value())["effective"]
        self.closed_claims = []
        self.roundtrip = ROUNDTRIP.Roundtrip(self)
        self.effect_enabled = True
        self.fail_after_admit = False
        self.unexpected_put = False
        self.dispatches = []
        self.guards = 0
    def raw_value(self):
        return b"null\n" if self.value is None else self.value.encode("ascii") + b"\n"
    def guard(self, flow):
        assert flow.session is self and time.monotonic() < flow.deadline
        self.guards += 1
    def require_owned_task(self, flow):
        self.guard(flow)
        return {"test_fixture": True}, flow.claim

class Flow:
    def __init__(self, session, name):
        self.session = session
        self.c = Files
        self.phase = "inspect"
        self.deadline = time.monotonic() + 30
        self.step = session.root / (name + "-initial")
        self.step.mkdir()
        self.bridge = None
        self.command_index = 0
        self.scope_ref = {"fixture": name}
        self.claim = {"fixture_claim": name}
        self.policy = POLICY.Policy(self)
    def _new_step(self, name, reason, detail, mutation):
        assert reason == "fixed-font-scale"
        self.step = self.session.root / name
        self.step.mkdir()
        self.command_index = 0
    def _bridge(self): self.bridge = object()
    def guard(self): self.session.guard(self)
    def android(self, argv, timeout, mutation=False):
        self.policy.admit(argv, timeout, mutation, False)
        self.session.dispatches.append((list(argv), mutation))
        if mutation and self.session.fail_after_admit:
            raise RuntimeError("fixture unknown dispatched write")
        if tuple(argv) == ROUNDTRIP.READ_VALUE:
            raw = self.session.raw_value()
        elif tuple(argv) == ROUNDTRIP.READ_CONFIG:
            raw = proto(self.session.scale)
        elif argv == list(ROUNDTRIP.PREFIX + ("put", "system", "font_scale", self.session.roundtrip.selected)):
            self.session.value = argv[-1]
            if self.session.effect_enabled: self.session.scale = float(argv[-1])
            raw = b"unexpected\n" if self.session.unexpected_put else b""
        elif argv[3:] == ["delete", "system", "font_scale"]:
            self.session.value = None
            if self.session.effect_enabled: self.session.scale = 1.0
            raw = b"Deleted 1 rows\n"
        elif argv[:6] == list(ROUNDTRIP.PREFIX + ("put", "system", "font_scale")):
            self.session.value = argv[-1]
            if self.session.effect_enabled: self.session.scale = float(argv[-1])
            raw = b""
        else:
            raise AssertionError("fixture received a nonfixed command")
        out = self.step / "stdout"; err = self.step / "stderr"
        out.write_bytes(raw); err.write_bytes(b"")
        result = {"host_retirement_proved": True, "evidence_complete": True,
                  "returncode": 0, "timed_out": False, "errors": [], "first_error": None,
                  "argv": list(argv), "stdout": self.c.regular(out), "stderr": self.c.regular(err)}
        (self.step / "command-001.result.json").write_text(json.dumps(result))
        return raw

class SourcePayloadTests(unittest.TestCase):
    def test_exact_provider_and_absence_reject_noncanonical_or_unknown_values(self):
        self.assertEqual(ROUNDTRIP.provider_value(b"null\n"), {"present":False,"text":None,"effective":1.0})
        self.assertEqual(ROUNDTRIP.provider_value(b"1.000\n")["text"], "1.000")
        for raw in (b"", b"NaN\n", b"1e0\n", b"01\n", b"1\n2\n", b"2.1\n", b"0.4\n", b" 1\n", b"1"):
            with self.subTest(raw=raw), self.assertRaises((RuntimeError, UnicodeError)):
                ROUNDTRIP.provider_value(raw)

    def test_actual_selected_proto_shape_and_complement(self):
        original = ROUNDTRIP.configuration(proto())
        changed = ROUNDTRIP.configuration(proto(1.15))
        ROUNDTRIP.same_other_configuration(original, changed)
        self.assertAlmostEqual(changed["font_scale"], 1.15, places=5)
        with self.assertRaises(RuntimeError):
            ROUNDTRIP.same_other_configuration(original, ROUNDTRIP.configuration(proto(1.15, b"\x10\x02")))
        for raw in (b"", proto()[:-1], blob(1,blob(1,b"\x0d"+struct.pack("<f",float("nan")))),
                    blob(1,blob(1,b"\x0d"+struct.pack("<f",1.0)+b"\x0d"+struct.pack("<f",1.0))),
                    b"\x0b\x01", b"\x80"*11):
            with self.subTest(raw=raw), self.assertRaises(RuntimeError):
                ROUNDTRIP.configuration(raw)

    def test_transaction_restores_original_string_and_absence_after_distinct_reopen(self):
        for initial in ("1.000", None, "1.15"):
            with tempfile.TemporaryDirectory() as root, self.subTest(initial=initial):
                session = Session(Path(root), initial)
                first = Flow(session, "first"); transaction = session.roundtrip
                transaction.apply(first)
                self.assertTrue(transaction.applied)
                session.closed_claims.append(first.claim)
                second = Flow(session, "reopen")
                transaction.verify_reopened(second)
                transaction.restore(second)
                self.assertTrue(transaction.restored)
                self.assertEqual(session.value, initial)
                self.assertEqual(transaction.write_count, 2)
                self.assertEqual(transaction.state, "restored_verified")
                self.assertFalse(transaction.report()["whole_app_business_accepted"])

    def test_external_change_and_unknown_dispatch_are_never_replayed(self):
        with tempfile.TemporaryDirectory() as root:
            session=Session(Path(root),"1.0");flow=Flow(session,"first");t=session.roundtrip
            t.apply(flow);session.value="1.2";session.scale=1.2
            count=len([r for r in session.dispatches if r[1]])
            with self.assertRaisesRegex(RuntimeError,"THIRD_PARTY"):
                t.restore(flow,failure_cleanup=True)
            self.assertEqual(len([r for r in session.dispatches if r[1]]),count)
        with tempfile.TemporaryDirectory() as root:
            session=Session(Path(root),"1.0");flow=Flow(session,"first");t=session.roundtrip
            session.fail_after_admit=True
            with self.assertRaisesRegex(RuntimeError,"unknown dispatched"):
                t.apply(flow)
            self.assertEqual(t.state,"dispatch_or_postguard_unknown")
            self.assertFalse(t.may_restore())
            self.assertEqual(t.write_count,1)
            with self.assertRaises(RuntimeError): t.restore(flow,failure_cleanup=True)
            self.assertEqual(len([r for r in session.dispatches if r[1]]),1)

    def test_known_retired_apply_with_bad_stdout_can_restore_but_no_credit(self):
        with tempfile.TemporaryDirectory() as root:
            session=Session(Path(root),"1.0");flow=Flow(session,"first");t=session.roundtrip
            session.unexpected_put=True
            with self.assertRaisesRegex(RuntimeError,"UNEXPECTED_SETTING_PUT_OUTPUT"):
                t.apply(flow)
            self.assertTrue(t.may_restore())
            session.unexpected_put=False
            t.restore(flow,failure_cleanup=True)
            self.assertEqual(session.value,"1.0")
            self.assertFalse(t.applied)
            self.assertFalse(t.reopened)
            self.assertFalse(t.report()["whole_app_business_accepted"])

    def test_policy_cannot_be_used_for_an_arbitrary_key_or_third_write(self):
        with tempfile.TemporaryDirectory() as root:
            session=Session(Path(root),"1.0");flow=Flow(session,"first");t=session.roundtrip
            for command in (["/system/bin/settings","--user","0","put","system","brightness","1"],
                            ["/system/bin/settings","--user","1","put","system","font_scale","1.15"],
                            ["/system/bin/am","get-config","--device","--proto"]):
                with self.assertRaises(RuntimeError): flow.policy.admit(command,20,True,False)
            t.apply(flow)
            with self.assertRaises(RuntimeError): t.apply(flow)
            session.closed_claims.append(flow.claim);again=Flow(session,"second")
            t.verify_reopened(again);t.restore(again)
            with self.assertRaises(RuntimeError): t.restore(again)
            self.assertEqual(t.write_count,2)

    def test_real_held_caller_and_callee_have_the_same_userns_and_start_prefix(self):
        held_source=(ROOT/"source/main/held_runtime.py").read_text()
        tree=ast.parse(held_source)
        methods=[n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=="entry"]
        self.assertEqual(len(methods),1)
        method=methods[0]
        env={"contextmanager":contextlib.contextmanager,"os":os}
        # The original method uses its actual contextmanager decorator spelling.
        for decorator in method.decorator_list:
            if isinstance(decorator,ast.Attribute):env[decorator.value.id]=contextlib
        def require(value,*rest):
            if not value:raise RuntimeError(rest)
        env["require"]=require
        exec(compile(ast.fix_missing_locations(ast.Module(body=[method],type_ignores=[])),"held-entry-method","exec"),env)
        entry=env["entry"]
        opened=[]
        try:
            root_fd=os.open("/",os.O_RDONLY|os.O_DIRECTORY);opened.append(root_fd)
            namespaces={}
            for name in ("mnt","pid","uts","ipc","net","cgroup"):
                fd=os.open("/proc/self/ns/"+name,os.O_RDONLY);opened.append(fd);namespaces[name]=fd
            user=os.open("/proc/self/ns/user",os.O_RDONLY);opened.append(user)
            start=Path("/proc/self/stat").read_text().rsplit(")",1)[1].split()[19]
            class Target:
                helper_path=str(ROOT/"bin/held-namespace-entry")
                def __init__(self):
                    self.root_fd=root_fd;self.namespaces=namespaces;self.user_namespace_fd=user
                    self.expected={"start":start}
                    self._mapping_module=types.SimpleNamespace(namespace_fact=lambda fd:{"device":os.fstat(fd).st_dev,"inode":os.fstat(fd).st_ino})
                @contextlib.contextmanager
                def lease(self):yield
                def _verify_user_namespace(self):
                    self.asserted_user=(os.fstat(user).st_dev,os.fstat(user).st_ino)
            target=Target()
            for source in ("source/support/business_scope.py","source/clock-support/business_scope.py"):
                text=(ROOT/source).read_text()
                begin=text.index("                expected_prefix = ")
                end=text.index('\n',text.index("                require(prefix == expected_prefix",begin))
                block=textwrap.dedent(text[begin:end])
                with entry(target,["/system/bin/true"]) as (argv,authority):
                    cut=argv.index("--");prefix=argv[:cut]
                    scope={"self":types.SimpleNamespace(target=target),"os":os,"descriptors":authority,"prefix":prefix,"require":require}
                    exec(compile(block,"actual-source-callee-prefix","exec"),scope)
                    for index in (-1,-2,-3):
                        bad=prefix.copy();bad[index]=bad[index].split("=")[0]+"=0"
                        with self.assertRaises(RuntimeError):
                            exec(compile(block,"actual-source-callee-prefix","exec"),{**scope,"prefix":bad})
                    self.assertEqual(len(authority),7)
        finally:
            for fd in reversed(opened):os.close(fd)

if __name__=="__main__":
    unittest.main(argv=["native_leaf_payloads",*REMAINING],verbosity=2)
