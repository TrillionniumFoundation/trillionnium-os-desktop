"""Guard the two fixed production entry units against silent or cyclic failures."""
import configparser
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[4]
UNITS = ROOT / "packaging/systemd/system"
RUNTIME = ROOT / "runtime/droidloom-supervisor/src"
VERIFY = "droidloom-production-verify.service"
RETURN = "droidloom-production-verify-return.service"


def unit(path):
    value = configparser.ConfigParser(interpolation=None, strict=True)
    value.optionxform = str
    value.read_string(path.read_text())
    return value


def seconds(value):
    text = value.removesuffix("s")
    if not text.isdigit() or not 1 <= int(text) <= 1800:
        raise ValueError("unit must have a single finite seconds value")
    return int(text)


class ProductionUnitContract(unittest.TestCase):
    def test_ready_window_uses_normal_notify_deadlines_not_broker_exec(self):
        startup = []
        for name in ("manager-label", "instance-factory", "instance-launcher", "early-observer"):
            startup.append(seconds(unit(RUNTIME / f"droidloom-{name}.service")["Service"]["TimeoutStartSec"]))
        self.assertEqual(startup, [30, 60, 240, 255])
        self.assertEqual(120 + sum(startup), 705)
        broker = unit(RUNTIME / "droidloom-production.service")["Service"]
        self.assertEqual(broker["Type"], "exec")
        self.assertNotIn("TimeoutStartSec", broker)
        self.assertEqual(705 + 180 + 180 + 30,
                         seconds(unit(UNITS / VERIFY)["Service"]["RuntimeMaxSec"]))
        self.assertEqual(180 + 30,
                         seconds(unit(UNITS / RETURN)["Service"]["RuntimeMaxSec"]))

    def test_main_start_failure_does_not_cancel_the_verifier(self):
        value = unit(UNITS / VERIFY)["Unit"]
        self.assertEqual(set(value["Wants"].split()),
                         {"droidloom-production.service", "droidloom-early-observer.service"})
        self.assertEqual(set(value["After"].split()), {
            "local-fs.target", "systemd-journald.service",
            "droidloom-production.service", "droidloom-early-observer.service"})
        self.assertFalse({"Requires", "Requisite", "BindsTo", "PartOf"} & set(value))
        self.assertEqual(value["OnFailure"], RETURN)
        self.assertEqual(value["OnFailureJobMode"], "replace")
        self.assertNotIn("OnSuccess", value)

    def test_fallback_does_not_depend_on_a_working_main(self):
        value = unit(UNITS / RETURN)["Unit"]
        self.assertEqual(value["DefaultDependencies"], "no")
        self.assertEqual(value["After"], VERIFY)
        self.assertFalse({"Wants", "Requires", "Requisite", "BindsTo", "PartOf",
                          "OnFailure", "OnSuccess"} & set(value))
        self.assertEqual(value["Conflicts"], "shutdown.target")
        self.assertEqual(value["Before"], "shutdown.target")

    def test_fixed_actor_and_sealing_entry_are_preserved(self):
        modes = {VERIFY: "--production-observe-normal-boot",
                 RETURN: "--production-return-original"}
        for name, mode in modes.items():
            with self.subTest(unit=name):
                value = unit(UNITS / name)
                service = value["Service"]
                self.assertEqual(service["Type"], "exec")
                self.assertEqual(service["ExecStart"], "/usr/bin/droidloom-applications " + mode)
                self.assertEqual(service["SELinuxContext"], "u:system_r:p4_linux_production_verify_t:s0")
                self.assertEqual(service["AppArmorProfile"], "droidloom-production-verify")
                self.assertEqual(service["User"], "root")
                self.assertEqual(service["Group"], "root")
                self.assertEqual(service["CapabilityBoundingSet"], "CAP_SYS_PTRACE")
                self.assertEqual(service["AmbientCapabilities"], "")
                self.assertEqual(service["NoNewPrivileges"], "no")
                self.assertEqual(service["PrivateMounts"], "no")
                self.assertEqual(service["LimitNOFILE"], "32768")
                self.assertEqual(service["UMask"], "0077")
                self.assertNotIn("ExecStartPre", service)
                self.assertNotIn("ExecStartPost", service)

    def test_failure_is_terminal_and_cannot_be_silently_skipped(self):
        for name in (VERIFY, RETURN):
            with self.subTest(unit=name):
                value = unit(UNITS / name)
                service = value["Service"]
                self.assertEqual(service["Restart"], "no")
                self.assertEqual(service["KillMode"], "control-group")
                self.assertEqual(service["SendSIGKILL"], "yes")
                self.assertEqual(seconds(service["TimeoutStartSec"]), 30)
                self.assertEqual(seconds(service["TimeoutStopSec"]), 30)
                self.assertEqual(service["MemoryMax"], "2147483648")
                self.assertEqual(service["MemorySwapMax"], "0")
                self.assertEqual(service["CPUQuota"], "100%")
                self.assertNotIn("Install", value)
                self.assertFalse(any(key.startswith(("Condition", "Assert"))
                                     for key in value["Unit"]))
                self.assertNotIn("ExecCondition", service)
                self.assertNotIn("SuccessExitStatus", service)


if __name__ == "__main__":
    unittest.main()
