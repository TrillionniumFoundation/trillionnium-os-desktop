"""Construct only newly published components with explicit fresh dependencies."""
import os
from pathlib import Path
import re


class CalendarPrerequisites:
    def __init__(self, c, components):
        self.c, self.components = c, components
    def verify(self, s, guard):
        c = self.c; p = self.components['system_profiles.py']
        historical = c.parse(c.read_ref(p.CALENDAR_INSTALL)); atomic = c.parse(c.read_ref(p.ATOMIC_REVIEW))
        c.read_ref(p.TASK_PROOF)
        c.need(historical['state'] == 'INSTALLED_VERIFIED_NOT_BUSINESS_QUALIFIED'
            and historical['install_calls'] == 1 and historical['install_pending'] is False
            and historical['new_sha256'] == p.CALENDAR['apks'][0]['sha256']
            and historical['data_identity_preserved'] is True
            and atomic['provider_apk_sha256'] == p.CALENDAR_PROVIDER['apks'][0]['sha256'],
            'ORIGINAL_REPAIRED_APK_AND_PROVIDER_CONTRACT')
        target = s.identities[0]; artifact = target['artifacts'][0]
        c.need(artifact['bytes'] == historical['after']['apk_bytes']
            and artifact['sha256'] == historical['after']['apk_sha256']
            and target['metadata']['uid'] == historical['after']['uid'] == 10061,
            'ACTUAL_NEW_MAIN_HAS_ORIGINAL_REPAIRED_CALENDAR')
        # Old st_dev belonged to a different runtime namespace. It is never
        # substituted for the actual live loop device. The new baseline binds
        # this live inode/UID to the stopped predeployment image and UUID.
        linked = {}
        namespace = s.baseline.docs['final_baseline']['main_user_namespace']
        mapping = s.baseline.data.userns_module()
        for old_key, prefix in [('ce', 'user'), ('de', 'user_de')]:
            current = s.baseline.value['data_continuity']['directories'][prefix + '/0/com.android.calendar']
            original = historical['after']['directories'][old_key]
            c.need((current['inode'], current['uid'], current['gid']) ==
                (original['st_ino'], mapping.mapped_id(namespace['uid_map'], original['st_uid']),
                 mapping.mapped_id(namespace['gid_map'], original['st_gid'])), 'ORIGINAL_CALENDAR_DATA_IDENTITY_CONTINUITY')
            linked[old_key] = {'historical': original, 'actual_new_Main': current,
                'stopped_predeployment_receipt': s.baseline.value['data_continuity']['preimage']}
        dump = s.android(['/system/bin/dumpsys', 'package', 'com.android.calendar'], 20).decode('utf-8', 'strict')
        blocks = re.findall(r'^Packages:\n(.*?)(?=^\S|\Z)', dump, re.M | re.S)
        c.need(len(blocks) == 1 and re.findall(r'^  Package \[([^]]+)\]', blocks[0], re.M) == ['com.android.calendar']
            and re.findall(r'^    firstInstallTime=(.*)$', blocks[0], re.M) == [historical['after']['first_install_time']],
            'ORIGINAL_CALENDAR_FIRST_INSTALL_IDENTITY')
        c.need(s.guard() == guard, 'FRESH_MAIN_CHANGED_DURING_PREREQUISITE_BINDING')
        return {'historical_installer': p.CALENDAR_INSTALL, 'actual_identity': s.active['target_identity'],
            'actual_provider_identity': s.active['provider_identity'], 'actual_new_Main': s.active['baseline'],
            'actual_qualification': s.active['qualification'], 'data_identity_links': linked,
            'task_option_source_proof': p.TASK_PROOF, 'atomic_delete_review': p.ATOMIC_REVIEW,
            'old_activation_or_nonce_transferred': False, 'business_accepted': False}


def construct(s, result, emit):
    m = s.components; root = s.evidence_root
    if s.kind == 'contacts_search':
        base, adapter, loop, verifier, mouse, menu = [m[name] for name in (
            'contacts_base.py', 'contacts_trial.py', 'contacts_continuation.py', 'contacts_model.py',
            'contacts_mouse.py', 'contacts_menu.py')]
        base.Flow = base.make_flow(root)
        adapter.Trial = adapter.make_trial(root)
        loop.Continuation = loop.make_continuation(emit)
        trial = menu.trial_class(adapter, verifier, result)(s, s.tx)
        case = m['contacts_search.py'].make_flow(base, mouse, root)(trial, loop, verifier, result)
        s.trial, s.case = trial, case
        case.deadline = s.deadline
        return case
    base, adapter, model, diag = [m[name] for name in (
        'calendar_base.py', 'calendar_adapter.py', 'calendar_model.py', 'calendar_diagnostics.py')]
    adapter.Adapter = m['calendar_first_open.py'].extend(adapter, m['calendar_semantic.py'])
    ui = base.ui_class(adapter)
    base.Flow = base.make_flow(root, ui, diag.Trial, emit)
    core = m['calendar_core.py'].make_flow(base, model, adapter, m['calendar_shell_permissions.py'],
        m['calendar_picker_policy.py'], m['calendar_picker_mouse.py'], m['calendar_segments.py'],
        CalendarPrerequisites(s.c, m), emit)
    case = core(s, s.tx, adapter, m['calendar_identity.py'], diag)
    s.case = case; s.trial = case.ui
    return case
