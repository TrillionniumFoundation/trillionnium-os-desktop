"""Actual original-Linux shebang/procfs ELF identity regression; NOT Asterinas QEMU."""
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import tempfile
import unittest

HERE=Path(__file__).resolve().parent


class ShebangProcExe(unittest.TestCase):
    def test_interpreter_identity_real_linux_elf(self):
        if platform.system()!='Linux' or platform.machine()!='x86_64':
            self.skipTest('x86_64 host Linux required for this ABI reference')
        with tempfile.TemporaryDirectory(prefix='a04-proc-exe-') as td:
            root=Path(td)
            binary=root/'probe'
            compiler=subprocess.run(['gcc','-std=c11','-O2','-Wall','-Wextra','-Werror',
                                     str(HERE/'proc_self_exe.c'),'-o',str(binary)],
                                    capture_output=True,text=True,timeout=30)
            self.assertEqual(compiler.returncode,0,compiler.stderr)
            self.assertEqual(binary.read_bytes()[:4],b'\x7fELF')
            exe_hash=hashlib.sha256(binary.read_bytes()).hexdigest()
            result=subprocess.run([str(binary),td],capture_output=True,text=True,timeout=20)
            self.assertEqual(result.returncode,0,result.stderr)
            facts=json.loads(result.stdout.strip())
            self.assertEqual(facts,{'ok':True,'shebang_interpreter_elf':True,
                                    'proc_self_exe_is_interpreter':True,
                                    'child_reaped':True,'script_unlinked':True})
            self.assertFalse((root/'a04-interpreter.sh').exists())
            self.assertEqual(len(exe_hash),64)


if __name__=='__main__':
    unittest.main()
