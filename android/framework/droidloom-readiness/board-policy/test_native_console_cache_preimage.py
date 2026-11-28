"""Fixed cache-loader preimages: raw grants cannot be invented or broadened."""
import unittest

import derive_native_console_policy as console

CACHE = "p4_linux_console_ld_cache_native_config_t"
CONFIG = "p4_linux_native_config_t"
INTERPRETER = "p4_linux_elf_interpreter_t"
BIRTH = "p4_linux_working_payload_birth_t"
COMMIT = "p4_linux_production_commit_t"
VERIFY = "p4_linux_production_verify_t"
OUTSIDER = "p4_linux_unreviewed_fixture_t"
SELECTED = (BIRTH, COMMIT, VERIFY)
CACHE_BITS = ("getattr", "open", "read", "map")
ELF_BITS = (*CACHE_BITS, "execute")
CLASSES = {"file": ["getattr", "open", "read", "map", "execute",
                    "write", "append", "create", "setattr", "relabelto"],
           "dir": ["getattr", "search"]}


def allow(actor, target, permissions):
    return "(allow " + actor + " " + target + " (file (" + " ".join(permissions) + ")))"


def fixture():
    actors = (*SELECTED, OUTSIDER, console.ROLE, "p4_linux_ldconfig_t")
    lines = ["(type " + name + ")" for name in (*actors, CONFIG, CACHE, INTERPRETER)]
    lines += ["(roletype system_r " + name + ")" for name in actors]
    lines += ["(roletype object_r " + name + ")" for name in (CONFIG, CACHE, INTERPRETER)]
    lines += ["(typeattribute p4_production_commit_actors)",
              "(typeattributeset p4_production_commit_actors (" + COMMIT + " " + VERIFY + "))"]
    lines += [allow(BIRTH, CACHE, CACHE_BITS),
              allow("p4_production_commit_actors", CACHE, CACHE_BITS)]
    lines += [allow(actor, INTERPRETER, ELF_BITS) for actor in SELECTED]
    return lines


class FixedEffectivePolicy:
    """Independent expected effective vectors; raw mutations cannot teach them."""
    def __init__(self, changed=None):
        self.changed = changed or {}

    def permissions(self, cls, names):
        return 1, {name: 1 << i for i, name in enumerate(CLASSES[cls])}

    def context_av(self, source, target, cls, names):
        actor = source.split(":", 3)[2]
        obj = target.split(":", 3)[2]
        level = source.split(":", 3)[3]
        wanted = set()
        if actor in SELECTED:
            wanted = {CONFIG: set(), CACHE: set(CACHE_BITS),
                      INTERPRETER: set(ELF_BITS)}[obj]
        wanted = self.changed.get((actor, obj, level), wanted)
        _, bits = self.permissions(cls, names)
        return sum(bits[p] for p in wanted)


class ConsoleCachePreimages(unittest.TestCase):
    def check(self, lines=None, changed=None):
        return console._cache_loader_preimages(
            FixedEffectivePolicy(changed), fixture() if lines is None else lines, CLASSES)

    def test_exact_three_existing_preimages_are_required_at_every_level(self):
        result = self.check()
        self.assertEqual(result["fixed_isolated_loaders"], sorted(SELECTED))
        self.assertEqual(result["raw_and_constrained_vectors"], 3 * 3 * len(console.LEVELS))
        self.assertEqual(result["all_concrete_cache_actor_preimages_checked"], 4)
        self.assertEqual(len(result["vector_sha256"]), 64)

    def test_every_missing_cache_bit_is_rejected_before_derivation(self):
        for actor in (BIRTH, "p4_production_commit_actors"):
            for bit in CACHE_BITS:
                with self.subTest(actor=actor, bit=bit):
                    lines = fixture()
                    lines[lines.index(allow(actor, CACHE, CACHE_BITS))] = allow(
                        actor, CACHE, [p for p in CACHE_BITS if p != bit])
                    with self.assertRaises(ValueError):
                        self.check(lines)

    def test_each_isolated_actor_cannot_gain_raw_cache_write_or_execute(self):
        for actor in SELECTED:
            for bit in ("write", "append", "create", "execute", "setattr", "relabelto"):
                with self.subTest(actor=actor, bit=bit):
                    with self.assertRaises(ValueError):
                        self.check(fixture() + [allow(actor, CACHE, [bit])])

    def test_no_declared_cache_grant_cannot_be_manufactured_by_extra(self):
        for actor in (BIRTH, "p4_production_commit_actors"):
            with self.subTest(actor=actor):
                lines = fixture()
                lines.remove(allow(actor, CACHE, CACHE_BITS))
                with self.assertRaises(ValueError):
                    self.check(lines)

    def test_foreign_actor_does_not_gain_the_loader_exception(self):
        for bit in (*CACHE_BITS, "write", "execute"):
            with self.subTest(bit=bit):
                with self.assertRaisesRegex(ValueError, "exact explicit preimage"):
                    self.check(fixture() + [allow(OUTSIDER, CACHE, [bit])])
        self.assertEqual(console._extra(OUTSIDER, CACHE), set())

    def test_production_attribute_is_exactly_the_two_reviewed_actors(self):
        lines = fixture()
        definition = "(typeattributeset p4_production_commit_actors (" + COMMIT + " " + VERIFY + "))"
        for members in ((COMMIT,), (VERIFY,), (COMMIT, VERIFY, BIRTH)):
            with self.subTest(members=members):
                changed = list(lines)
                changed[changed.index(definition)] = (
                    "(typeattributeset p4_production_commit_actors (" + " ".join(members) + "))")
                with self.assertRaises(ValueError):
                    self.check(changed)

    def test_generic_native_configuration_authority_stays_zero(self):
        for actor in SELECTED:
            with self.subTest(actor=actor):
                with self.assertRaisesRegex(ValueError, "raw preimage"):
                    self.check(fixture() + [allow(actor, CONFIG, ["getattr"])])

    def test_interpreter_preimage_keeps_exact_five_bits(self):
        for actor in SELECTED:
            for bit in ELF_BITS:
                with self.subTest(actor=actor, missing=bit):
                    lines = fixture()
                    lines[lines.index(allow(actor, INTERPRETER, ELF_BITS))] = allow(
                        actor, INTERPRETER, [p for p in ELF_BITS if p != bit])
                    with self.assertRaisesRegex(ValueError, "raw preimage"):
                        self.check(lines)
            with self.assertRaisesRegex(ValueError, "raw preimage"):
                self.check(fixture() + [allow(actor, INTERPRETER, ["write"])])

    def test_exact_system_role_is_required(self):
        for actor in SELECTED:
            for wrong in ("r", None, "both"):
                with self.subTest(actor=actor, wrong=wrong):
                    lines = fixture()
                    role = "(roletype system_r " + actor + ")"
                    if wrong != "both":
                        lines.remove(role)
                    if wrong is not None:
                        lines.append("(roletype r " + actor + ")")
                    with self.assertRaisesRegex(ValueError, "role differs"):
                        self.check(lines)

    def test_effective_mcs_changes_do_not_hide_behind_correct_raw_grants(self):
        for actor in SELECTED:
            for level in console.LEVELS:
                with self.subTest(actor=actor, level=level):
                    for target, permissions in (
                        (CONFIG, {"getattr"}),
                        (CACHE, set(CACHE_BITS) - {"read"}),
                        (CACHE, set(CACHE_BITS) | {"write"}),
                        (INTERPRETER, set(ELF_BITS) - {"execute"})):
                        with self.assertRaisesRegex(ValueError, "constrained preimage"):
                            self.check(changed={(actor, target, level): permissions})

    def test_conditional_and_unconsumed_raw_authority_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "unconditional"):
            self.check(fixture() + ["(booleanif enabled (true))"])
        with self.assertRaisesRegex(ValueError, "incomplete"):
            self.check(fixture() + ["  " + allow(OUTSIDER, CACHE, ["read"])])

    def test_other_alias_targets_do_not_gain_the_cache_exception(self):
        for actor in SELECTED:
            for target in (CONFIG, INTERPRETER, "p4_linux_console_cache_native_config_t"):
                with self.subTest(actor=actor, target=target):
                    self.assertEqual(console._extra(actor, target), set())


if __name__ == "__main__":
    unittest.main()
