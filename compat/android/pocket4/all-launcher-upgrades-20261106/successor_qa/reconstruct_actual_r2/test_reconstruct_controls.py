#!/usr/bin/env python3
"""Precision and fail-closed controls only; no substitute for the actual binding."""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("reconstructor_controls",HERE/"reconstruct_generated_source.py")
reconstructor=importlib.util.module_from_spec(spec);spec.loader.exec_module(reconstructor)

class Controls(unittest.TestCase):
    def test_large_integers_and_dict_order_without_source_execution(self):
        raw=b"BINDING = {'z': 1793980000000000001, 'a': {'ns': 9223372036854775807}}\nraise RuntimeError('must not execute')\n"
        b=reconstructor.extract_binding(raw)
        self.assertEqual(b["z"],1793980000000000001)
        self.assertEqual(b["a"]["ns"],9223372036854775807)
        self.assertEqual(list(b),["z","a"])
        self.assertIn(b"1793980000000000001",reconstructor.canonical(b))
        self.assertIs(type(b["z"]),int)

    def test_binding_call_and_duplicate_rejected(self):
        with tempfile.TemporaryDirectory(prefix="qa-ast-control-") as temp:
            sentinel=Path(temp)/"must-not-exist"
            raw=("BINDING = __import__('pathlib').Path("+repr(str(sentinel))+").write_text('bad')\n").encode()
            with self.assertRaisesRegex(reconstructor.Rejection,"BINDING_IS_NOT_A_LITERAL"):
                reconstructor.extract_binding(raw)
            self.assertFalse(sentinel.exists())
        with self.assertRaisesRegex(reconstructor.Rejection,"EXACTLY_ONE_TOP_LEVEL_BINDING_LITERAL_REQUIRED"):
            reconstructor.extract_binding(b"BINDING={}\nBINDING={}\n")

    def test_missing_extra_changed_output_cannot_match_manifest(self):
        source={"one.py":"pass\n","two.py":"x=1\n"}
        pins={k:{"bytes":len(v.encode()),"sha256":hashlib.sha256(v.encode()).hexdigest()}
              for k,v in source.items()}
        manifest=json.dumps({"files":pins}).encode()
        self.assertEqual(len(reconstructor.verify_rendered_set(source,manifest)),2)
        with self.assertRaisesRegex(reconstructor.Rejection,"RENDERED_FILE_SET_MISMATCH"):
            reconstructor.verify_rendered_set({"one.py":"pass\n"},manifest)
        with self.assertRaisesRegex(reconstructor.Rejection,"RENDERED_FILE_SET_MISMATCH"):
            reconstructor.verify_rendered_set(dict(source,extra="x"),manifest)
        with self.assertRaisesRegex(reconstructor.Rejection,"RENDERED_FILE_PIN_MISMATCH"):
            reconstructor.verify_rendered_set(dict(source,**{"two.py":"x=2\n"}),manifest)

    def test_missing_actual_input_is_rejection_without_publishing(self):
        with tempfile.TemporaryDirectory(prefix="qa-missing-input-control-") as temp:
            missing=Path(temp)/"missing-recorded-contract.py"
            output=io.StringIO()
            with mock.patch.object(sys,"argv",["reconstruct","--source-contract",str(missing)]), \
                 mock.patch.object(reconstructor,"publish_once",side_effect=AssertionError("must not publish")), \
                 contextlib.redirect_stdout(output):
                rc=reconstructor.main()
            row=json.loads(output.getvalue())
            self.assertEqual(rc,1)
            self.assertEqual(row["status"],"RECONSTRUCTION_REJECTED_OR_INPUT_MISSING")
            self.assertEqual(row["error_type"],"FileNotFoundError")
            self.assertFalse(row["runtime_QA_claimed"])

if __name__=="__main__":
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Controls))
    report={"schema":"pocket4-actual-source-reconstructor-local-controls-v1",
            "success":result.wasSuccessful(),"tests_run":result.testsRun,"failures":len(result.failures),
            "errors":len(result.errors),"skips":len(result.skipped),"synthetic_binding_used_only_in_unit_controls":True,
            "actual_reconstruction_performed":False,"Main_actions":0,"source_sha256":
             hashlib.sha256((HERE/"reconstruct_generated_source.py").read_bytes()).hexdigest()}
    print(json.dumps(report,sort_keys=True,indent=2))
    raise SystemExit(0 if report["success"] else 1)

