"""A05 fail-closed source contract for the native effect seam.

This checks source boundaries, not Rust compilation or a successful guest.
Ordinary builds remain QueryAbi-only. G1-c adds the trusted initial image's
ReadUsage. G1-d separately connects all five opcodes to the original Process,
CPU owner and delivery core; this experimental slice does not certify Hepta
disk durability. Keep the default and G1-c disabled-operation gates intact.
"""
from pathlib import Path
import tomllib
import unittest

from rust_source_contract import block_after, positions, replace_once, require_sequence, rust_tokens


ROOT = Path(__file__).resolve().parents[2]
DEVICE = ROOT / "kernel/asterinas/kernel/core/src/device/misc/hepta_control.rs"
ABI = ROOT / "libs/os-abi/src/lib.rs"
ARCHITECTURE = ROOT / "docs/ARCHITECTURE.md"
INDEX = ROOT / "docs/INDEX.md"
KERNEL = ROOT / "kernel/asterinas/kernel/Cargo.toml"
CORE = KERNEL.parent / "core/Cargo.toml"
OPERATIONS = ("QueryAbi", "ReadUsage", "InstallBudget", "QueryDelivery", "RetireThrough")
MANAGEMENT = ("RequestPayload::InstallBudget(_) | RequestPayload::QueryDelivery(_) "
              "| RequestPayload::RetireThrough(_) =>")


def check_capabilities(source):
    query = block_after(rust_tokens(source), "RequestPayload::QueryAbi =>")
    checks = (
        ('''#[cfg(not(feature = "g1c-trusted-observe"))]
            let (supported_ops, max_response_payload) = (1u64 << Opcode::QueryAbi.as_u16(), 48);''',
         "ordinary QueryAbi-only capabilities"),
        ('''#[cfg(all(feature = "g1c-trusted-observe", not(feature = "g1d-trusted-control")))]
            let (supported_ops, max_response_payload) = (
                (1u64 << Opcode::QueryAbi.as_u16()) | (1u64 << Opcode::ReadUsage.as_u16()), 64,
            );''', "G1-c declares exactly its two reads"),
        ('''#[cfg(feature = "g1d-trusted-control")]
            let (supported_ops, max_response_payload) = ('''
         + " | ".join(f"(1u64 << Opcode::{name}.as_u16())" for name in OPERATIONS)
         + ", 64,);", "G1-d declares exactly its five operations"),
        ('''#[cfg(not(feature = "g1d-trusted-control"))]
            let max_request_payload = 0;''', "non-management request bound"),
        ('''#[cfg(feature = "g1d-trusted-control")]
            let max_request_payload = 40;''', "bounded management request"),
        ("features: 0", "no implicit feature or authority bits"),
    )
    for fragment, label in checks:
        require_sequence(query, fragment, label)
    if len(positions(query, "let (supported_ops, max_response_payload)")) != 3:
        raise AssertionError("capabilities require exactly ordinary, G1-c and G1-d declarations")


def check_operation_routes(source):
    ioctl = block_after(rust_tokens(source), "fn ioctl(")
    require_sequence(ioctl, '''#[cfg(feature = "g1c-trusted-observe")]
                                RequestPayload::ReadUsage =>''',
                     "ordinary builds must not compile ReadUsage")
    usage = block_after(ioctl, "RequestPayload::ReadUsage =>")
    require_sequence(usage, '''#[cfg(not(feature = "g1d-trusted-control"))]
                               let result = match process.read_hepta_initial_usage(''',
                     "independently qualified G1-c observe path")
    require_sequence(usage, '''#[cfg(feature = "g1d-trusted-control")]
        let result = match process.dispatch_hepta_control(self.image_key, &request)''',
        "G1-c cannot dispatch through the management owner")
    require_sequence(ioctl, '#[cfg(feature = "g1d-trusted-control")] ' + MANAGEMENT,
                     "management and history require the separate G1-d profile")
    manage = block_after(ioctl, MANAGEMENT)
    for body in (usage, manage):
        require_sequence(body, "self.check_session()?;", "recheck final Process image")
        require_sequence(body, "self.process.upgrade()", "retain original Process owner")
        require_sequence(body, "process.dispatch_hepta_control(self.image_key, &request)",
                         "original Process/CPU/D execution path")
        if positions(body, "self.check_session()?")[0] > positions(body, "process.dispatch_hepta_control(")[0]:
            raise AssertionError("check the caller image before any control dispatch")
    if len(positions(ioctl, "process.dispatch_hepta_control(self.image_key, &request)")) != 2:
        raise AssertionError("usage and management must be the only original control dispatches")
    require_sequence(ioctl, '''#[cfg(not(feature = "g1d-trusted-control"))]
        _ => return_errno_with_message!(Errno::EOPNOTSUPP,
            "recognized HOS2 resource operation not implemented"),''',
        "all disabled operations fail closed with EOPNOTSUPP")


def feature_closure(features, selected):
    reached = set()
    pending = list(selected)
    while pending:
        feature = pending.pop()
        if feature in reached:
            continue
        reached.add(feature)
        pending.extend(features.get(feature, ()))
    return reached


def check_profile_features(kernel, core):
    profiles = {"g1c-trusted-observe", "g1d-trusted-control", "g2-trusted-daemon"}
    kernel_defaults = feature_closure(kernel, ["default"])
    core_defaults = feature_closure(core, ["default", *[
        value.split("/", 1)[1] for value in kernel_defaults if value.startswith("aster-core/")
    ]])
    if not profiles.isdisjoint(kernel_defaults | core_defaults):
        raise AssertionError("ordinary defaults must not activate a trusted profile, including aliases")
    for profile in profiles:
        selected = feature_closure(kernel, [profile])
        if "aster-core/" + profile not in selected:
            raise AssertionError("kernel must forward the selected profile to its original core")
        forwarded = feature_closure(core, [value.split("/", 1)[1] for value in selected
                                          if value.startswith("aster-core/")])
        forbidden = ({"g1d-trusted-control", "g2-trusted-daemon"}
                     if profile == "g1c-trusted-observe" else
                     {"g2-trusted-daemon"} if profile == "g1d-trusted-control" else set())
        if forbidden & (selected | forwarded):
            raise AssertionError("kernel forwarding cannot activate a more privileged profile")
    observer = feature_closure(core, ["g1c-trusted-observe"])
    control = feature_closure(core, ["g1d-trusted-control"])
    daemon = feature_closure(core, ["g2-trusted-daemon"])
    if {"g1d-trusted-control", "g2-trusted-daemon"} & observer:
        raise AssertionError("the observer profile cannot activate management or the launcher")
    if "g2-trusted-daemon" in control:
        raise AssertionError("G1-d must not activate the private G2 launcher")
    if not {"g1c-trusted-observe", "osdk-frame-allocator/physical-reserve"} <= control:
        raise AssertionError("G1-d must retain image sealing and physical-reserve prerequisites")
    if "g1d-trusted-control" not in daemon:
        raise AssertionError("G2 must retain the original control prerequisites")


class A05EffectPathFailClosedContract(unittest.TestCase):
    def test_default_device_advertises_only_queryabi(self):
        check_capabilities(DEVICE.read_text())

    def test_all_disabled_opcodes_share_eopnotsupp_gate(self):
        abi = block_after(rust_tokens(ABI.read_text()), "enum Opcode")
        for number, opcode in enumerate(OPERATIONS, 1):
            require_sequence(abi, f"{opcode} = {number},", "unchanged exact HOS2 opcode")
        check_operation_routes(DEVICE.read_text())

    def test_source_guards_accept_layout_but_reject_capability_and_dispatch_mutations(self):
        source = DEVICE.read_text()
        tokens = rust_tokens(source)
        formatted = " /* layout only */\n".join(tokens)
        check_capabilities(formatted)
        check_operation_routes(formatted)
        changes = (
            ("(1u64 << Opcode::QueryAbi.as_u16(), 48)",
             "(1u64 << Opcode::QueryAbi.as_u16() | 1u64 << Opcode::InstallBudget.as_u16(), 48)",
             check_capabilities),
            ("let max_request_payload = 0;", "let max_request_payload = 40;", check_capabilities),
            ("features: 0", "features: 1", check_capabilities),
            ('#[cfg(feature = "g1c-trusted-observe")] RequestPayload::ReadUsage',
             "RequestPayload::ReadUsage", check_operation_routes),
            ('#[cfg(feature = "g1d-trusted-control")] RequestPayload::InstallBudget',
             "RequestPayload::InstallBudget", check_operation_routes),
            ('Errno::EOPNOTSUPP, "recognized HOS2 resource operation not implemented"',
             'Errno::ENOTTY, "recognized HOS2 resource operation not implemented"', check_operation_routes),
            ("match process.dispatch_hepta_control(self.image_key, &request)",
             "match process.dispatch_hepta_control(other_image_key, &request)", check_operation_routes),
        )
        for before, after, checker in changes:
            with self.subTest(boundary=before):
                mutant = " ".join(replace_once(tokens, before, after))
                # A comment containing the old safe code must not restore acceptance.
                with self.assertRaises(AssertionError):
                    checker(mutant + "\n/* " + before + " */\n")

    def test_profiles_are_opt_in_and_preserve_their_prerequisites(self):
        kernel = tomllib.loads(KERNEL.read_text())["features"]
        core = tomllib.loads(CORE.read_text())["features"]
        check_profile_features(kernel, core)
        bad_kernel = dict(kernel, default=[*kernel["default"], "aster-core/hidden-management"])
        bad_core = dict(core, **{"hidden-management": ["g1d-trusted-control"]})
        with self.assertRaisesRegex(AssertionError, "ordinary defaults"):
            check_profile_features(bad_kernel, bad_core)
        for profile, dependency in (("g1c-trusted-observe", "g1d-trusted-control"),
                                    ("g1d-trusted-control", "g2-trusted-daemon")):
            with self.subTest(profile=profile):
                with self.assertRaises(AssertionError):
                    check_profile_features(kernel, dict(core, **{profile: [*core[profile], dependency]}))
                with self.assertRaisesRegex(AssertionError, "kernel forwarding"):
                    check_profile_features(
                        dict(kernel, **{profile: [*kernel[profile], "aster-core/hidden-escalation"]}),
                        dict(core, **{"hidden-escalation": [dependency]}),
                    )

    def test_private_launcher_requires_its_own_profile_and_exact_session(self):
        tokens = rust_tokens(DEVICE.read_text())
        require_sequence(tokens, '''#[cfg(feature = "g2-trusted-daemon")]
            const EXPERIMENTAL_NATIVE_LAUNCH_IOCTL: u32 = 0xC080_4803;''', "private G2 endpoint")
        ioctl = block_after(tokens, "fn ioctl(")
        require_sequence(ioctl, '''#[cfg(feature = "g2-trusted-daemon")]
            if raw_ioctl.cmd() == EXPERIMENTAL_NATIVE_LAUNCH_IOCTL { self.check_session()?;''',
            "no ordinary or G1 launcher authority")
        launcher = block_after(ioctl, "if raw_ioctl.cmd() == EXPERIMENTAL_NATIVE_LAUNCH_IOCTL")
        require_sequence(launcher, "process.dispatch_hepta_launcher(self.image_key, &input)?",
                         "original Process launcher owner")

    def test_control_device_does_not_import_ui_or_host_authority(self):
        source = DEVICE.read_text()
        forbidden = (
            "os-control",
            "os_control",
            "TrustedReadOnlyOrgan",
            "Agentd",
            "WebSocket",
            "websocket",
            "FinalUse",
            "Final-use",
        )
        for token in forbidden:
            self.assertNotIn(token, source)

        architecture = ARCHITECTURE.read_text()
        index = INDEX.read_text()
        self.assertIn("不冒充内核", architecture)
        self.assertIn("仍返回 `EOPNOTSUPP`", architecture)
        self.assertIn("libs/os-control/API_CONTRACT.md", index)
        self.assertIn("宿主模型", index)
        self.assertIn("内核 IRQ/SMP 接合仍需验证", index)

    def test_readonly_bootstrap_has_no_effectful_authority_signal(self):
        source = DEVICE.read_text()
        self.assertIn("//! Read-only HOS2 bootstrap", source)
        self.assertIn("Management and\n//! history operations remain disabled", source)
        self.assertIn("Open, dup, fork and descriptor transfer grant no authority", source)
        self.assertNotIn("execute_reserved", source)
        self.assertNotIn("install_budget", source)
        self.assertNotIn("retire_through", source)


if __name__ == "__main__":
    unittest.main()
