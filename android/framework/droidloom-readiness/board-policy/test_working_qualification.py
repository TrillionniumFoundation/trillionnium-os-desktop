"""Focused rejection tests for the complete working authority projection."""
import copy
from pathlib import Path
import tempfile
import unittest
import verify_working_qualification as v

P=v.PARENT
D="p4_linux_working_watchdog_t"
L=v.LABELER
B=v.BIRTH

def index(extra=""):
    types=set(v.OWNED)|{"old_reader_t","other_t","device","kernel","init","system_server","droidloom_broker","init_t","rootfs","system_file","system_data_root_file","system_data_file",*v.UNIT_READER_PAIR,
        "droidloom_apk_payload","tmpfs","proc","p4_kernel_pid_handle_t","p4_kernel_ns_handle_t",
        "droidloom_public_control_client_exec","p4_linux_runtime_lib_t","p4_linux_elf_interpreter_t",
        "p4_linux_console_ld_cache_native_config_t","p4_linux_rootdir_t","p4_linux_etc_dir_t",
        "p4_linux_usrmerge_link_t", "droidloom_working_apk_payload_creator",
        "droidloom_native_leaf_apk_reader", "droidloom_native_leaf_apk_copy",
        "droidloom_native_helper_source", "droidloom_container_entry_exec_t",
        "droidloom_metadata_observer", "apex_mnt_dir", "apk_data_file", "labeledfs",
        "p4_linux_service_executor_t", "p4_linux_observed_client_exec_t"}
    rows=["(type "+n+")"for n in sorted(types)]
    rows+=["(class file (getattr open read write create setattr append execute execute_no_trans entrypoint map ioctl))",
           "(class memfd_file (getattr open read write create setattr append execute execute_no_trans entrypoint map ioctl))",
           "(class dir (getattr search open read write add_name remove_name))",
           "(class lnk_file (getattr read))",
           "(class filesystem (getattr associate))",
           "(class fd (use))",
           "(class fifo_file (getattr read write))",
           "(class unix_stream_socket (getattr getopt read write create bind listen accept connect connectto))",
           "(class capability (sys_ptrace))",
           "(class capability2 (bpf))",
           "(class service (start stop status reload kill load enable disable))",
           "(class chr_file (getattr open read write ioctl relabelfrom relabelto))",
           "(class process (transition dyntransition getattr ptrace sigkill siginh rlimitinh sigchld getcap setexec setfscreate fork))",
           "(class process2 (nnp_transition nosuid_transition))"]
    for n in sorted(v.OWNED):
        role="r"if n==L else"system_r"if n in v.SUBJECTS else"object_r"
        rows.append(f"(roletype object_r {n})")
        if role != "object_r":
            rows.append(f"(roletype {role} {n})")
    groups={**v.GROUPS,"p4_linux_procs":v.HOSTS,"p4_linux_data":v.DATA,
            "p4_handle_owner":v.HOSTS,"p4_all_board_owned":v.HOSTS|v.DATA|v.EMPTY_DATA|{B}}
    groups.update({g:()for g in("domain","coredomain","mlstrustedsubject","mlstrustedobject","netdomain","p4_linux_native_processes","p4_linux_mac_roles")})
    rows.extend("(typeattributeset "+name+" ("+" ".join(sorted(members))+"))"for name,members in groups.items())
    forms=v._forms("\n".join(rows)+"\n"+extra)
    return v._Index(forms),forms

class WorkingAuthorityTests(unittest.TestCase):
    def test_inbound_attribute_and_complement_are_observed(self):
        idx,_=index(f"(typeattributeset callers (old_reader_t other_t))\n(typeattributeset objects (not (other_t)))")
        observed=v._project(v._forms(f"(allow callers {D} (chr_file (write)))"),idx)
        self.assertEqual(set(observed[0]),{("allow",n,D,"chr_file")for n in("old_reader_t","other_t")})
        with self.assertRaises(ValueError):v._compare(observed,({},set(),set()))
        outgoing=v._project(v._forms(f"(allow {P} objects (file (read)))"),idx)[0]
        self.assertIn(("allow",P,D,"file"),outgoing)
        self.assertNotIn(("allow",P,"other_t","file"),outgoing)

    def test_dontaudit_and_auditallow_cannot_hide_extra_authority(self):
        idx,_=index()
        for kind in("dontaudit","auditallow"):
            observed=v._project(v._forms(f"({kind} {P} device (chr_file (write)))"),idx)
            with self.assertRaises(ValueError):v._compare(observed,({},set(),set()))
        for target in (P,"p4_working_actors"):
            for wrapper in (
                    f"(booleanif optional_gate (true (allow {target} device (chr_file (write)))))",
                    f"(optional extra_authority (allow {target} device (chr_file (write))))"):
                with self.assertRaises(ValueError):v._project(v._forms(wrapper),idx)

    def test_ioctl_full_u16_extra_bit_is_rejected(self):
        idx,_=index()
        good=v._project(v._forms(f"(allowx {P} {D} (ioctl chr_file (0x5705)))"),idx)
        bad=v._project(v._forms(f"(allowx {P} {D} (ioctl chr_file ((range 0x5705 0x5706))))"),idx)
        with self.assertRaises(ValueError):v._compare(bad,good)
        self.assertEqual(v._xvalues(["range","0","65535"]),set(range(65536)))
        for expr in("65536","-1",["range","8","7"]):
            with self.assertRaises(ValueError):v._xvalues(expr)

    def test_output_type_transition_and_unreviewed_change_are_rejected(self):
        idx,_=index()
        actual=v._project(v._forms(f"(typetransition old_reader_t device chr_file {D})"),idx)
        with self.assertRaises(ValueError):v._compare(actual,({},set(),set()))
        for kind in("typechange","typemember"):
            with self.assertRaises(ValueError):v._project(v._forms(f"({kind} {P} device chr_file {D})"),idx)

    def test_new_context_permissive_and_bounds_cannot_escape_projection(self):
        idx,_=index()
        for rule in(f"(typepermissive {P})",f"(typebounds old_reader_t {P})"):
            with self.assertRaises(ValueError):v._project(v._forms(rule),idx)
        actual=v._project(v._forms(f"(genfscon devtmpfs /watchdog0 (u object_r {D} ((s0) (s0))))"),idx)
        with self.assertRaises(ValueError):v._compare(actual,({},set(),set()))

    def test_closed_membership_rejects_widened_role_or_domain(self):
        idx,forms=index()
        v._validate_membership(idx)
        for extra in(f"(typeattributeset domain ({P}))",f"(roletype r {P})",
                     f"(typeattributeset p4_working_children ({L}))"):
            with self.assertRaises(ValueError):v._validate_membership(v._Index(forms+v._forms(extra)))

    def test_compiled_derivation_aliases_keep_strict_concrete_membership(self):
        _, forms = index()
        aliases = {"p4_working_data", "p4_working_main_proc_peers"}
        omitted = [f for f in forms if not (
            f[0] == "typeattributeset" and f[1] in aliases)]
        v._validate_membership(v._Index(omitted))
        for extra in (
                f"(typeattributeset p4_working_data ({P}))",
                "(typeattribute p4_working_data)",
                "(type p4_working_data)",
                f"(typeattributeset p4_linux_data ({P}))",
                "(typeattributeset p4_working_proc_peers (other_t))"):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                v._validate_membership(v._Index(omitted + v._forms(extra)))
        missing_concrete = [f for f in omitted if not (
            f[0] == "typeattributeset" and f[1] == "p4_working_children")]
        with self.assertRaises(ValueError):
            v._validate_membership(v._Index(missing_concrete))

    def test_linked_roles_keep_only_fixed_process_role_plus_object_role(self):
        _, forms = index()
        v._validate_membership(v._Index(forms))
        for extra in (
                f"(roletype r {P})",
                f"(roletype system_r {L})",
                f"(roletype r {D})"):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                v._validate_membership(v._Index(forms + v._forms(extra)))
        for role in ("object_r", "system_r"):
            missing = [f for f in forms if f != ["roletype", role, P]]
            with self.subTest(missing=role), self.assertRaises(ValueError):
                v._validate_membership(v._Index(missing))

    def test_unknown_or_recursive_attribute_fails_closed(self):
        idx,_=index("(typeattributeset first (second))\n(typeattributeset second (first))")
        for name in("missing","first"):
            with self.assertRaises(ValueError):idx.members(name)


    def test_fixed_unit_reader_rejects_extra_body_or_service_authority(self):
        idx, _ = index()
        expected = v._unit_reader_projection(v._forms(v.UNIT_READER_ACL), idx)
        self.assertEqual(expected, {("allow", *v.UNIT_READER_PAIR, "file"): frozenset(("getattr", "open", "read"))})
        s, t = v.UNIT_READER_PAIR
        for tag in ("allow", "auditallow", "dontaudit"):
            extra = v._unit_reader_projection(v._forms(v.UNIT_READER_ACL + "\n" + f"({tag} {s} {t} (file (write)))"), idx)
            self.assertNotEqual(extra, expected)
        changed = v._unit_reader_projection(v._forms(v.UNIT_READER_ACL + "\n" + f"(allow {s} {t} (service (status)))"), idx)
        self.assertNotEqual(changed, expected)
        for extra in (
                f"(booleanif conditional (true (allow {s} {t} (file (read)))))",
                f"(optional conditional (allow {s} {t} (file (read))))",
                f"(typetransition {s} {t} file other_t)"):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                v._unit_reader_projection(v._forms(extra), idx)
        expanded, _ = index(f"(typeattributeset readers ({s}))\n(typeattributeset units ({t}))")
        self.assertEqual(v._unit_reader_projection(v._forms("(allow readers units (file (getattr open read)))"), expanded), expected)

    def test_fixed_desktop_unit_label_rejects_wildcard_neighbor_or_duplicate(self):
        good = "\n".join(v.UNIT_FILE_CONTEXTS) + "\n"
        self.assertEqual(v._unit_file_contexts(good), list(v.UNIT_FILE_CONTEXTS))
        for bad in (
                good.replace(r"droidloom-production-desktop\.service", r".*\.service"),
                good.replace("droidloom-production-desktop", "droidloom-production-desktop-extra"),
                good + v.UNIT_FILE_CONTEXTS[1] + "\n",
                v.UNIT_FILE_CONTEXTS[0] + "\n"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                v._unit_file_contexts(bad)

    def test_actual_source_contract_and_alias_roster_remain_complete(self):
        here=Path(v.__file__).resolve().parent
        self.assertEqual(len(v.verify_sources(here)),70)
        self.assertEqual(len(v._fixed_aliases(here)),66)
        self.assertEqual(len(v._apk_paths(here)),67)

    def test_original_apk_bodies_cannot_leak_to_another_working_actor(self):
        target="p4_linux_working_apk_input_t"
        idx,_=index()
        expected=v._project(v._forms(f"(allow {v.PREP} {target} (file (getattr open read)))"),idx)
        for source in [P,v.PHYSICAL,v.RETURN,"old_reader_t","p4_working_actors"]:
            observed=v._project(v._forms(f"(allow {source} {target} (file (read)))"),idx)
            with self.subTest(source=source),self.assertRaises(ValueError):
                v._compare(observed,expected)
        for permission in ["write","execute","map"]:
            changed=v._project(v._forms(f"(allow {v.PREP} {target} (file (getattr open read {permission})))"),idx)
            with self.subTest(permission=permission),self.assertRaises(ValueError):
                v._compare(changed,expected)

    def test_original_apk_apparmor_rejects_wildcards_extra_paths_and_other_roles(self):
        here=Path(v.__file__).resolve().parent
        names=("droidloom-working-qualification","droidloom-working-privateprep",
               "droidloom-working-application","droidloom-working-qualification-return")
        profiles={name:(here/"apparmor"/name).read_text()for name in names}
        v._apk_apparmor(here,profiles)
        path=v._apk_paths(here)[0]
        mutations=[(names[1],profiles[names[1]].replace(path,v.APK_ROOT+"/*.apk")),
                   (names[1],profiles[names[1]].replace(path+" r,",path+" rw,")),
                   (names[1],profiles[names[1]]+"\n"+path+" r,\n"),
                   (names[1],profiles[names[1]].replace("  "+path+" r,\n",""))]
        mutations.extend((name,profiles[name]+"\n"+path+" r,\n")for name in(names[0],names[2],names[3]))
        for name,changed in mutations:
            with self.subTest(name=name,changed=changed[-100:]),self.assertRaises(ValueError):
                v._apk_apparmor(here,{**profiles,name:changed})

    def test_changed_c_source_is_rejected_before_linked_policy_read(self):
        real=Path(v.__file__).resolve().parent
        with tempfile.TemporaryDirectory()as tmp:
            here=Path(tmp)/"android/framework/droidloom-readiness/board-policy"
            for name in[*v.SOURCE_PINS,"ubuntu-native-file_contexts","ubuntu-real-root-file_contexts"]:
                dest=here/name;dest.parent.mkdir(parents=True,exist_ok=True)
                dest.write_bytes((real/name).read_bytes())
            target=here/"../../../../runtime/droidloom-early-boot/board_policy.c"
            body=bytearray(target.read_bytes());body[0]^=1;target.write_bytes(body)
            with self.assertRaisesRegex(ValueError,"Changed working authority source"):
                v.verify_sources(here)

    def test_empty_payload_role_is_not_a_host_client_or_namespace_owner(self):
        idx, forms = index()
        v._validate_membership(idx)
        self.assertNotIn(B, v.HOSTS)
        self.assertNotIn(B, v.CLIENTS)
        self.assertEqual(idx.roles[B], {"object_r", "system_r"})
        for group in ("p4_linux_procs", "p4_linux_native_processes", "p4_handle_owner",
                      "p4_working_actors", "p4_working_clients", "p4_working_children",
                      "domain", "mlstrustedsubject"):
            with self.subTest(group=group), self.assertRaises(ValueError):
                v._validate_membership(v._Index(forms + v._forms(
                    f"(typeattributeset {group} ({B}))")))
        with self.assertRaises(ValueError):
            v._validate_membership(v._Index(forms + v._forms(f"(roletype r {B})")))
        with self.assertRaises(ValueError):
            v._validate_membership(v._Index(forms + v._forms(
                f"(typeattributeset p4_all_board_owned ({L}))")))
        omitted = [f for f in forms if not (
            f[0] == "typeattributeset" and f[1] == "p4_all_board_owned")]
        v._validate_membership(v._Index(omitted))
        with self.assertRaises(ValueError):
            v._validate_membership(v._Index(omitted + v._forms(
                "(typeattributeset p4_all_board_owned (p4_working_actors p4_working_data))")))

    def test_empty_birth_cannot_read_or_modify_payload_and_parent_cannot_create_it(self):
        idx, _ = index()
        baseline = v._forms(v.PAYLOAD_BIRTH_ACL)
        expected = v._project(baseline, idx, expected=True)
        for kind in ("file", "memfd_file"):
            self.assertEqual(expected[0][("allow", B, "droidloom_apk_payload", kind)],
                             {"getattr"})
            self.assertEqual(expected[0][("allow", v.PREP, "droidloom_apk_payload", kind)],
                             {"getattr", "open", "read", "write"})
            for permission in ("create", "open", "read", "write", "setattr", "map", "execute"):
                changed = baseline + v._forms(
                    f"(allow {B} droidloom_apk_payload ({kind} ({permission})))")
                with self.subTest(kind=kind, permission=permission), self.assertRaises(ValueError):
                    v._compare(v._project(changed, idx), expected)
            for permission in ("create", "setattr", "map", "execute"):
                with self.subTest(parent=permission, kind=kind), self.assertRaises(ValueError):
                    v._compare(v._project(baseline + v._forms(
                        f"(allow {v.PREP} droidloom_apk_payload ({kind} ({permission})))"), idx), expected)

    def test_birth_transition_keeps_preparation_comparison_default(self):
        idx, _ = index()
        comparison = "\n".join(
            f"(typetransition p4_working_clients tmpfs {kind} p4_linux_working_comparison_t)"
            for kind in ("file", "memfd_file"))
        baseline = v._forms(v.PAYLOAD_BIRTH_ACL + comparison)
        expected = v._project(baseline, idx, expected=True)
        for kind in ("file", "memfd_file"):
            self.assertIn(("typetransition", B, "tmpfs", kind, "", "droidloom_apk_payload"), expected[1])
            self.assertIn(("typetransition", v.PREP, "tmpfs", kind, "", "p4_linux_working_comparison_t"), expected[1])
            for extra in (
                    f"(typetransition {v.PREP} tmpfs {kind} droidloom_apk_payload)",
                    f'(typetransition {B} tmpfs {kind} "droidloom-apk-payload" droidloom_apk_payload)',
                    f"(allow {B} self (process (setfscreate)))"):
                with self.subTest(extra=extra), self.assertRaises(ValueError):
                    v._compare(v._project(baseline + v._forms(extra), idx), expected)

    def test_birth_onexec_is_only_the_original_preparation_and_same_elf(self):
        idx, _ = index()
        baseline = v._forms(v.PAYLOAD_BIRTH_ACL)
        expected = v._project(baseline, idx, expected=True)
        for extra in (
                f"(allow {v.PHYSICAL} {B} (process (transition)))",
                f"(allow old_reader_t {B} (process (transition)))",
                f"(allow {v.PREP} {B} (process (dyntransition)))",
                f"(allow {B} self (process (fork setexec)))",
                f"(allow {v.PREP} {B} (process2 (nosuid_transition)))",
                f"(typetransition {v.PREP} droidloom_public_control_client_exec process {B})"):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                v._compare(v._project(baseline + v._forms(extra), idx), expected)
        missing = [f for f in baseline if f != ["allow", v.PREP, B,
                                               ["process2", ["nnp_transition"]]]]
        with self.assertRaises(ValueError):
            v._compare(v._project(missing, idx), expected)

    def test_birth_fd_and_anonymous_socket_cannot_accept_other_peers(self):
        idx, _ = index()
        baseline = v._forms(v.PAYLOAD_BIRTH_ACL)
        expected = v._project(baseline, idx, expected=True)
        for extra in (
                f"(allow {B} kernel (fd (use)))",
                f"(allow {B} droidloom_broker (fd (use)))",
                f"(allow p4_working_clients {B} (fd (use)))",
                f"(allow {B} self (unix_stream_socket (create)))",
                f"(allow {B} {v.PREP} (unix_stream_socket (connect connectto)))",
                f"(allow {B} {v.PREP} (fifo_file (write)))",
                f"(allow {B} self (capability (sys_ptrace)))"):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                v._compare(v._project(baseline + v._forms(extra), idx), expected)

    def test_birth_pidfd_info_has_no_other_ioctl_or_namespace_handle(self):
        idx, _ = index()
        baseline = v._forms(v.PAYLOAD_BIRTH_ACL)
        expected = v._project(baseline, idx, expected=True)
        for actor in (B, v.PREP):
            self.assertEqual(expected[0][("allowx", actor, "p4_kernel_pid_handle_t", "file")], {0xff0b})
            for extra in (
                    f"(allowx {actor} p4_kernel_pid_handle_t (ioctl file ((range 0xff0b 0xff0c))))",
                    f"(allow {actor} p4_kernel_pid_handle_t (file (read)))"):
                with self.subTest(extra=extra), self.assertRaises(ValueError):
                    v._compare(v._project(baseline + v._forms(extra), idx), expected)
        with self.assertRaises(ValueError):
            v._compare(v._project(baseline + v._forms(
                f"(allow {B} p4_kernel_ns_handle_t (file (getattr ioctl)))"), idx), expected)

    def test_birth_cannot_access_originals_comparisons_or_broker(self):
        idx, _ = index()
        baseline = v._forms(v.PAYLOAD_BIRTH_ACL)
        expected = v._project(baseline, idx, expected=True)
        for target in ("p4_linux_working_apk_input_t", "p4_linux_working_comparison_t",
                       "p4_linux_native_leaf_source_t", "p4_linux_working_evidence_t"):
            for permission in ("getattr", "open", "read", "write"):
                with self.subTest(target=target, permission=permission), self.assertRaises(ValueError):
                    v._compare(v._project(baseline + v._forms(
                        f"(allow {B} {target} (file ({permission})))"), idx), expected)
        for extra in (
                "(allow droidloom_broker p4_linux_working_comparison_t (file (read)))",
                f"(allow {B} droidloom_broker (unix_stream_socket (connectto)))"):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                v._compare(v._project(baseline + v._forms(extra), idx), expected)

    def test_maintained_birth_cil_matches_the_independent_authority_table(self):
        here = Path(v.__file__).resolve().parent
        source = (here / "ubuntu-working-qualification.cil").read_text()
        body = source.split("(type " + B + ")", 1)[1].split("(macro p4_working_base", 1)[0]
        forms = v.parse_expression("(" + "\n".join(
            line.split(";", 1)[0] for line in body.splitlines()) + ")")
        authority = [f for f in forms if f[0] in v.FLOW_TAGS | v.TRANSITION_TAGS]
        idx, _ = index()
        v._compare(v._project(authority, idx), v._project(v._forms(v.PAYLOAD_BIRTH_ACL), idx, expected=True))
        memberships = [f for f in forms if f[0] == "typeattributeset" and B in f[2]]
        self.assertEqual(memberships, [["typeattributeset", "p4_all_board_owned", [B]]])

    def test_native_apk_component_matches_independent_working_cross_edges(self):
        here = Path(v.__file__).resolve().parent
        source = v._forms((here / "linux-native-apk.cil").read_text())
        _, declarations = index()
        idx = v._Index(declarations + source)
        actual = v._project([f for f in source if f[0] in v.FLOW_TAGS | v.TRANSITION_TAGS], idx)
        expected = v._project(v._forms(v.NATIVE_APK_CLIENT_ACL), idx, expected=True)
        v._compare(actual, expected)
        self.assertEqual(len(expected[0]), 11)
        self.assertEqual(expected[1:], (set(), set()))

    def test_native_helper_roles_and_attribute_expansion_cannot_widen_clients(self):
        idx, _ = index()
        baseline = v._forms(v.NATIVE_APK_CLIENT_ACL)
        expected = v._project(baseline, idx, expected=True)
        for actor in (P, v.RETURN, L, B, "p4_working_clients"):
            for target, kind, permissions in (
                    ("droidloom_native_helper_source", "dir", "getattr read"),
                    ("droidloom_native_helper_source", "file", "getattr read"),
                    ("droidloom_native_leaf_apk_reader", "fd", "use"),
                    ("droidloom_native_leaf_apk_copy", "file", "getattr read"),
                    ("droidloom_native_leaf_apk_copy", "memfd_file", "getattr read")):
                extra = f"(allow {actor} {target} ({kind} ({permissions})))"
                with self.subTest(actor=actor, target=target, kind=kind), self.assertRaises(ValueError):
                    v._compare(v._project(baseline + v._forms(extra), idx), expected)

    def test_native_apk_copy_cannot_be_reopened_modified_or_executed(self):
        idx, _ = index()
        baseline = v._forms(v.NATIVE_APK_CLIENT_ACL)
        expected = v._project(baseline, idx, expected=True)
        for actor in (v.PREP, v.PHYSICAL):
            for kind in ("file", "memfd_file"):
                self.assertEqual(expected[0][("allow", actor, "droidloom_native_leaf_apk_copy", kind)],
                                 {"getattr", "read"})
                for permission in ("open", "write", "create", "setattr", "map", "execute", "ioctl"):
                    extra = f"(allow {actor} droidloom_native_leaf_apk_copy ({kind} ({permission})))"
                    with self.subTest(actor=actor, kind=kind, permission=permission), self.assertRaises(ValueError):
                        v._compare(v._project(baseline + v._forms(extra), idx), expected)

    def test_reader_descriptor_use_does_not_add_process_or_reverse_fd_authority(self):
        idx, _ = index()
        baseline = v._forms(v.NATIVE_APK_CLIENT_ACL)
        expected = v._project(baseline, idx, expected=True)
        for actor in (v.PREP, v.PHYSICAL):
            for extra in (
                    f"(allow droidloom_native_leaf_apk_reader {actor} (fd (use)))",
                    f"(allow {actor} droidloom_native_leaf_apk_reader (process (getattr)))",
                    f"(allow {actor} droidloom_native_leaf_apk_reader (process (transition)))",
                    f"(allow {actor} droidloom_native_leaf_apk_reader (process (ptrace)))"):
                with self.subTest(extra=extra), self.assertRaises(ValueError):
                    v._compare(v._project(baseline + v._forms(extra), idx), expected)

    def test_native_source_ancestors_and_audit_rows_remain_closed(self):
        idx, _ = index()
        baseline = v._forms(v.NATIVE_APK_CLIENT_ACL)
        expected = v._project(baseline, idx, expected=True)
        for extra in (
                "(allow droidloom_broker p4_linux_native_leaf_source_t (dir (open read)))",
                "(allow droidloom_broker p4_linux_native_leaf_source_t (file (read)))",
                f"(allow {v.PREP} droidloom_native_helper_source (file (write)))",
                f"(auditallow {v.PREP} droidloom_native_helper_source (file (read)))",
                f"(dontaudit {v.PHYSICAL} droidloom_native_leaf_apk_copy (file (read)))"):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                v._compare(v._project(baseline + v._forms(extra), idx), expected)


    def test_current_cas_directory_matches_only_the_parent_body_access(self):
        here = Path(v.__file__).resolve().parent
        target = "p4_linux_working_current_dir_t"
        def rows(text):
            forms = v.parse_expression("(" + "\n".join(
                line.split(";", 1)[0] for line in text.splitlines()) + ")")
            return [f for f in forms if f[0] in v.FLOW_TAGS
                    and f[2] == target and f[3][0] == "dir"]
        idx, _ = index()
        expected = v._project(rows(v.FIXED_ACL), idx, expected=True)
        actual = v._project(rows((here / "ubuntu-working-qualification.cil").read_text()), idx)
        v._compare(actual, expected)
        self.assertEqual(expected[0], {
            ("allow", P, target, "dir"): frozenset((
                "getattr", "search", "open", "read", "write", "add_name", "remove_name")),
            ("allow", v.PREP, target, "dir"): frozenset(("getattr", "search")),
            ("allow", v.PHYSICAL, target, "dir"): frozenset(("getattr", "search")),
        })
        for permission in ("open", "read"):
            missing = copy.deepcopy(actual)
            key = ("allow", P, target, "dir")
            missing[0][key] = missing[0][key] - {permission}
            with self.subTest(missing=permission), self.assertRaises(ValueError):
                v._compare(missing, expected)
        baseline = rows(v.FIXED_ACL)
        for actor in (v.PREP, v.PHYSICAL, v.RETURN, B, L,
                      "old_reader_t", "p4_working_clients", "p4_working_actors"):
            extra = f"(allow {actor} {target} (dir (open read)))"
            with self.subTest(actor=actor), self.assertRaises(ValueError):
                v._compare(v._project(baseline + v._forms(extra), idx), expected)
        for extra in (
                f"(allow {P} other_t (dir (open read)))",
                f"(auditallow {P} {target} (dir (read)))",
                f"(dontaudit {P} {target} (dir (read)))",
                f"(allow {P} {target} (file (read)))"):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                v._compare(v._project(baseline + v._forms(extra), idx), expected)

    def test_current_cas_apparmor_rejects_other_directories_roles_and_modes(self):
        here = Path(v.__file__).resolve().parent
        names = ("droidloom-working-qualification", "droidloom-working-privateprep",
                 "droidloom-working-application", "droidloom-working-qualification-return")
        profiles = {name: (here / "apparmor" / name).read_text() for name in names}
        v._current_apparmor(profiles)
        exact = "/home/alex/work/pocket4-android-final/ rw,"
        mutations = [
            (names[0], profiles[names[0]].replace(exact, exact.replace("rw,", "w,"))),
            (names[0], profiles[names[0]].replace(exact, exact.replace("rw,", "rwk,"))),
            (names[0], profiles[names[0]].replace(exact, exact.replace("final/", "final-other/"))),
            (names[0], profiles[names[0]].replace(exact, exact.replace("final/", "final*/"))),
            (names[0], profiles[names[0]].replace("  " + exact + "\n", "")),
            (names[0], profiles[names[0]] + "\n" + exact + "\n"),
        ]
        mutations.extend((name, profiles[name] + "\n" + exact + "\n") for name in names[1:])
        for name, body in mutations:
            with self.subTest(name=name, tail=body[-120:]), self.assertRaises(ValueError):
                v._current_apparmor({**profiles, name: body})
        with self.assertRaises(ValueError):
            v._current_apparmor({**profiles, "unreviewed-profile": ""})


if __name__=="__main__":unittest.main()
