"""Check the explicit TCP adapter profile without starting a guest."""
import importlib.util
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


adapter = module("a01_osdk_adapter", HERE / "osdk.py")
runner = module("a01_osdk_runner", HERE / "run.py")


class ProfileTests(unittest.TestCase):
    def command(self, args, local=False):
        env = {"A01_REAL_OSDK": "/actual/cargo-osdk", "A01_OSDK_LOCAL_TCP": "1" if local else "0"}
        return adapter.adapt_command(args, env, HERE)

    def test_default_coverage_keeps_original_monitor_transport(self):
        self.assertNotIn("--qemu-monitor-transport=tcp", self.command(["osdk", "run", "--coverage"]))

    def test_explicit_tcp_coverage_selects_production_transport(self):
        command = self.command(["osdk", "run", "--coverage"], local=True)
        self.assertEqual(command.count("--qemu-monitor-transport=tcp"), 1)
        self.assertIn("--boot-method=vmm-direct", command)

    def test_tcp_plain_run_does_not_add_a_coverage_monitor(self):
        self.assertNotIn("--qemu-monitor-transport=tcp", self.command(["osdk", "run"], local=True))

    def test_explicit_v2_only_adds_capture_gdb_to_coverage(self):
        env = {"A01_REAL_OSDK": "/actual/cargo-osdk", "A01_OSDK_LOCAL_TCP": "1",
               "A01_OSDK_PROFILE": runner.CAPTURE_PROFILE}
        capture = adapter.adapt_command(["osdk", "run", "--coverage"], env, HERE)
        self.assertIn("--gdb-server=wait-client,addr=127.0.0.1:0", capture)
        plain = adapter.adapt_command(["osdk", "run"], env, HERE)
        self.assertFalse(any(argument.startswith("--gdb-server") for argument in plain))

    def test_help_remains_unadapted(self):
        self.assertEqual(self.command(["osdk", "run", "--help"], local=True),
                         ["/actual/cargo-osdk", "osdk", "run", "--help"])

    def test_tcp_debug_patch_retains_guest_and_debugger_assertions(self):
        original = (HERE.parents[2] / "kernel/asterinas/osdk/tests/commands/run.rs").read_text()
        adapted = runner.adapt_basic_debug_to_local_tcp(original)
        basic = adapted[adapted.index('    fn basic_debug() {'):adapted.index('    fn owned_gdb_endpoint()')]
        self.assertIn('let gdb_address = "127.0.0.1:0".to_string();', basic)
        self.assertNotIn('TcpListener::bind', basic)
        self.assertNotIn('drop(listener)', basic)
        self.assertIn('wait_for(&debugger_cancelled, owned_gdb_endpoint)', basic)
        self.assertIn('gdb_continue_via(&address, None)', basic)
        vsc = adapted[adapted.index('    mod vsc {'):]
        self.assertIn('let addr = "127.0.0.1:0".to_string();', vsc)
        self.assertNotIn('TcpListener::bind', vsc)
        self.assertNotIn('drop(listener)', vsc)
        self.assertIn('let symbols = wait_for(&debugger_cancelled, || launch_symbol_file(&dir))?;', vsc)
        self.assertIn('let address = wait_for(&debugger_cancelled, owned_gdb_endpoint)?;', vsc)
        self.assertIn('gdb_continue_via(&address, Some(&symbols))', vsc)
        self.assertIn('std::env::var("A01_OSDK_GDB_READY")', adapted)
        for line in original.splitlines():
            if "assert!" in line or "gdb.join()" in line or 'expect("GDB session failed")' in line:
                self.assertIn(line, adapted)
        self.assertNotEqual(original, adapted)

    def test_changed_vsc_address_setup_is_rejected(self):
        original = (HERE.parents[2] / "kernel/asterinas/osdk/tests/commands/run.rs").read_text()
        with self.assertRaises(SystemExit):
            runner.adapt_basic_debug_to_local_tcp(original.replace(
                'let addr = listener.local_addr().unwrap().to_string();', 'let addr = different_setup();'))

    def test_changed_debug_setup_is_rejected(self):
        original = (HERE.parents[2] / "kernel/asterinas/osdk/tests/commands/run.rs").read_text()
        with self.assertRaises(SystemExit):
            runner.adapt_basic_debug_to_local_tcp(original.replace("qemu-gdb-sock", "different-setup"))


if __name__ == "__main__":
    unittest.main()
