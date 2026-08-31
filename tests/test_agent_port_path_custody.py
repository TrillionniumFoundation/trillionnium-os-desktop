from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "validate_agent_port_path_custody_under_test",
    ROOT / "tools/validate_agent_port_path_custody.py",
)
assert SPEC is not None and SPEC.loader is not None
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


class SystemdMergeSemanticsTests(unittest.TestCase):
    def test_empty_assignment_resets_inherited_list(self) -> None:
        assignments = VALIDATOR.merge_units(
            [
                ("base", "[Service]\nReadWritePaths=/run/hepta/browserd /state\n"),
                ("drop-in", "[Service]\nReadWritePaths=\nReadWritePaths=/state\n"),
            ]
        )
        self.assertEqual(VALIDATOR.list_value(assignments, "Service", "ReadWritePaths"), ["/state"])

    def test_last_singleton_assignment_wins(self) -> None:
        assignments = VALIDATOR.merge_units(
            [
                ("base", "[Socket]\nSocketUser=root\n"),
                ("drop-in", "[Socket]\nSocketUser=hepta-browserd\n"),
            ]
        )
        self.assertEqual(VALIDATOR.last_value(assignments, "Socket", "SocketUser"), "hepta-browserd")

    def test_parser_rejects_directive_outside_section(self) -> None:
        with self.assertRaises(VALIDATOR.PolicyError):
            VALIDATOR.parse_unit("SocketUser=root\n", label="bad")


class RepositoryPolicyTests(unittest.TestCase):
    def test_repository_has_root_owned_parent_path_custody(self) -> None:
        result = VALIDATOR.validate(ROOT)
        self.assertEqual(result["status"], "PASS_SOURCE_POLICY")
        self.assertEqual(result["socket_inode_owner"], "hepta-browserd")
        self.assertEqual(result["socket_inode_group"], "hepta-agent")
        self.assertEqual(result["directory_owner"], "root")
        self.assertEqual(result["directory_group"], "hepta-agent-socket")
        self.assertFalse(result["browser_service_in_directory_group"])
        self.assertFalse(result["product_service_socket_path_mutation_authority"])
        self.assertFalse(result["development_service_socket_path_mutation_authority"])
        self.assertFalse(result["development_dropins_in_production_install_map"])
        self.assertFalse(result["promotion_authoritative"])


if __name__ == "__main__":
    unittest.main()
