import unittest

from recipe_epoch_bindings import recipe_bindings, require_recipe_bindings

RECIPE = "recipe-pasit-original-r1"
TOOLS = "tools/pasit-original-r1"
LAUNCHER = """
from pathlib import Path
ROOT = Path("/build/workspace")
working = "WorkingDirectory=" + str(ROOT / "recipe-pasit-original-r1")
def recover(commands, environment):
    return commands.run(
        "normal-recovery-after-retired-unit",
        [str(ROOT / "tools/pasit-original-r1/droidloom-update"),
         "--source", str(ROOT / "recipe-pasit-original-r1"),
         "recover-source", "--work", str(ROOT / "work")],
        300, cwd=ROOT / "recipe-pasit-original-r1", env=environment)
"""
CONTROLLER = """
RECIPE = ROOT / "recipe-pasit-original-r1"
TOOLS = ROOT / "tools/pasit-original-r1"
"""


class RecipeEpochBindingsTests(unittest.TestCase):
    def assert_one_stale_role(self, good, stale):
        self.assertEqual(LAUNCHER.count(good), 1)
        bad = LAUNCHER.replace(good, stale)
        observed = recipe_bindings(bad, RECIPE, TOOLS)
        self.assertEqual(len(observed["invalid"]), 1)
        with self.assertRaises(ValueError):
            require_recipe_bindings(bad, RECIPE, TOOLS)

    def test_actual_old_shape_reproduces_all_four_stale_bindings(self):
        old = LAUNCHER.replace("pasit-original-r1", "connectivity-projection-r1")
        result = recipe_bindings(old, RECIPE, TOOLS)
        self.assertEqual(len(result["observed"]), 4)
        self.assertEqual(len(result["invalid"]), 4)
        with self.assertRaises(ValueError):
            require_recipe_bindings(old, RECIPE, TOOLS)

    def test_current_launcher_binds_all_four_roles(self):
        result = require_recipe_bindings(LAUNCHER, RECIPE, TOOLS)
        self.assertEqual(len(result["observed"]), 4)
        self.assertEqual(result["invalid"], [])

    def test_current_controller_uses_the_same_recipe_and_tools(self):
        result = require_recipe_bindings(CONTROLLER, RECIPE, TOOLS)
        self.assertEqual(len(result["observed"]), 2)
        self.assertEqual({r["path"] for r in result["observed"]}, {RECIPE, TOOLS})

    def test_old_outer_working_directory_is_rejected(self):
        self.assert_one_stale_role(
            'working = "WorkingDirectory=" + str(ROOT / "recipe-pasit-original-r1")',
            'working = "WorkingDirectory=" + str(ROOT / "recipe-connectivity-projection-r1")')

    def test_old_fallback_executable_is_rejected(self):
        self.assert_one_stale_role(
            'ROOT / "tools/pasit-original-r1/droidloom-update"',
            'ROOT / "tools/connectivity-projection-r1/droidloom-update"')

    def test_old_fallback_source_argument_is_rejected(self):
        self.assert_one_stale_role(
            '"--source", str(ROOT / "recipe-pasit-original-r1")',
            '"--source", str(ROOT / "recipe-connectivity-projection-r1")')

    def test_old_fallback_working_directory_is_rejected(self):
        self.assert_one_stale_role(
            'cwd=ROOT / "recipe-pasit-original-r1"',
            'cwd=ROOT / "recipe-connectivity-projection-r1"')


if __name__ == "__main__":
    unittest.main()
