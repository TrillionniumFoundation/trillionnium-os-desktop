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

    def test_help_remains_unadapted(self):
        self.assertEqual(self.command(["osdk", "run", "--help"], local=True),
                         ["/actual/cargo-osdk", "osdk", "run", "--help"])

    def test_tcp_debug_patch_retains_guest_and_debugger_assertions(self):
        original = (HERE.parents[2] / "kernel/asterinas/osdk/tests/commands/run.rs").read_text()
        adapted = runner.adapt_basic_debug_to_local_tcp(original)
        self.assertIn('TcpListener::bind("127.0.0.1:0")', adapted)
        self.assertIn('std::env::var("A01_OSDK_GDB_READY")', adapted)
        for line in original.splitlines():
            if "assert!" in line or "gdb.join()" in line or 'expect("GDB session failed")' in line:
                self.assertIn(line, adapted)
        self.assertNotEqual(original, adapted)

    def test_changed_debug_setup_is_rejected(self):
        original = (HERE.parents[2] / "kernel/asterinas/osdk/tests/commands/run.rs").read_text()
        with self.assertRaises(SystemExit):
            runner.adapt_basic_debug_to_local_tcp(original.replace("qemu-gdb-sock", "different-setup"))


if __name__ == "__main__":
    unittest.main()
