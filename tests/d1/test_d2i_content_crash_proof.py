import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "packaging/debian/image/d2i-overlay/usr/local/libexec/trillionnium-d2i-content-crash-proof"
SERVICE = ROOT / "packaging/debian/image/d2i-overlay/etc/systemd/system/trillionnium-d2i-content-crash-proof.service"
DROP_IN = ROOT / "packaging/debian/image/d2i-overlay/etc/systemd/system/trillionnium-d2i-acceptance.service.d/20-content-crash-proof.conf"


class D2IContentCrashProofTest(unittest.TestCase):
    def test_script_proves_process_identity_kill_survival_and_replacement(self) -> None:
        text = SCRIPT.read_text()
        required = [
            "systemctl show --property MainPID",
            "/proc/$content_pid/stat",
            "kill -KILL \"$content_pid\"",
            "killed_content_start_time_ticks",
            "runtime_main_survived",
            "killed_pid_disappeared",
            "replacement_content_pid",
            "replacement_pid_distinct",
            "crash_callback_observed",
            "trusted_chrome_visible_after_crash",
            "PASS_ACTUAL_CONTENT_PROCESS_CRASH_AND_RECOVERY",
        ]
        for item in required:
            self.assertIn(item, text)
        self.assertNotIn("kill -KILL \"$main_pid\"", text)
        self.assertNotIn("actual_content_process_crash_proven\": false", text)

    def test_service_orders_proof_between_runtime_and_acceptance(self) -> None:
        service = SERVICE.read_text()
        self.assertIn("Requires=trillionnium-d2i-runtime.service", service)
        self.assertIn("After=trillionnium-d2i-runtime.service", service)
        self.assertIn("Before=trillionnium-d2i-acceptance.service", service)
        self.assertIn("TimeoutStartSec=8min", service)
        drop_in = DROP_IN.read_text()
        self.assertIn("Requires=trillionnium-d2i-content-crash-proof.service", drop_in)
        self.assertIn("After=trillionnium-d2i-content-crash-proof.service", drop_in)

    def test_contract_fixture_is_valid_json_when_substituted(self) -> None:
        template = SCRIPT.read_text()
        start = template.index("cat > \"$proof.tmp\" <<EOF")
        end = template.index("\nEOF", start)
        body = template[start:end].splitlines()[1:]
        rendered = "\n".join(body)
        replacements = {
            "$unit": "trillionnium-d2i-runtime.service",
            "$main_pid": "100",
            "$content_pid": "101",
            "$content_start_time": "200",
            "$content_cmdline_sha256": "a" * 64,
            "$replacement_pid": "102",
            "$replacement_start_time": "300",
            "$replacement_cmdline_sha256": "b" * 64,
            "$generation": "2",
            "$crash_callback": "true",
            "$trusted_chrome": "true",
            "$before_descendants": "101",
            "$after_descendants": "102",
        }
        for key in sorted(replacements, key=len, reverse=True):
            rendered = rendered.replace(key, replacements[key])
        parsed = json.loads(rendered)
        self.assertEqual(parsed["status"], "PASS_ACTUAL_CONTENT_PROCESS_CRASH_AND_RECOVERY")
        self.assertNotEqual(parsed["killed_content_pid"], parsed["replacement_content_pid"])


if __name__ == "__main__":
    unittest.main()
