"""Independent new-Main component; no historical Session, Main or execute entry."""
from pathlib import Path
import argparse, hashlib, json, os, re, signal, sys, time, types
PROFILE_TX_SHA = 'b2274355ea9acc9d3f82f4e245dceef01aae86e689221744f0fb2afaff679470'
PROFILE_ACTIVATION_SHA = '7e490c14586d891f6b121341f879f41c955414c9122e3a68053f04665c12e615'
NEW_SHA = '726241395b485794badd1a1fdcef4298ebb284f67826d73a7e2648f2b7a5382e'
PROVIDER_SHA = 'eebf12f81981f7d8c59a9b9ed465945818d2ab0208c121d858cbc4e6426f5fff'
READER_SHA = '08400fd889d2373bcefafe60630d0e619dddcb72cb913db4617acb885f2d9705'
ADAPTER_SHA = '21e368ea3369a12339f288eb9f53b1475e555b055289aca782ba5267677e8aca'
ATOMIC_SHA = '1d66de839c05c11983196764d44c518175bc10481cff754b850d6034c8533796'
LEASE_SECONDS = 480
CLEANUP_SECONDS = 90
DRIVER_SHA = '0089da73755fec25fafbb26356a495f0253acb5d2d785e0c05c19a5e37af2bbb'
SEMANTIC_BUTTON_SHA = '7eb435ec8bc555b72f2f82591ea01a580265500e8e18f671140d0a424fecfdc4'
POLICY_SHA = '39ba779c4b81b8fc22487957e3cb501af9a1f5f6dd935e76f83d176828d56e15'
PICKER_SHA = 'c1ac3f5cb26cda0d04f2b2b16ebed06f744b01ce9a29df69aa4a34d77f53902e'
SEGMENTS_SHA = 'a7823b62913c8e187538f543026cd00b52e22044cfc1a0ed27879d0f9b5d9de4'
FIRST_OPEN_SHA = '52a036d242b890905896e9c63ca65acd69e1f09842f0d83ed5fb161ca49a17c9'
NATIVE_PACKAGE = 'local.pocket4.actions.v2'
NATIVE_APK_SHA = 'a5368465d5f6faef3299bf1ba6d6bde268cc8b37c72401c6e668872b24725058'
REQUIRED = {'explicit_first_use_local_calendar', 'cancel_unsaved_without_event_write', 'created_in_calendar_ui', 'edited_same_event', 'normal_close_reopen_detail', 'deleted_in_calendar_ui', 'edited_dates_timezone_recurrence', 'later_occurrence_detail_does_not_change_series', 'series_editor_uses_original_start'}

def need(value, reason):
    if not value:
        raise RuntimeError(reason)

def make_flow(m, model, base, probe, policy, picker, segments, prerequisites, emit):

    class CoreFlow(m.Flow):

        def __init__(self, s, tx, base, doc, diag):
            super().__init__(s, tx, base, doc, diag)
            self.model = model.Model(s, self.record)
            self.business_pending = None
            self.policy = policy
            self.picker = picker
            self.diag_chain = segments.Segments(self.diagnostics, diag, self.record)
            self.cleanup_pending = False
            self.cleanup_calls = 0
            self.roles = {}
            self.role_tokens = {}
            self.scrolls = 0
            self.result = {'schema': 'calendar-owned-natural-reminder22-current-v1', 'state': 'FAILED', 'started_utc': m.stamp(), 'run_id': model.RUN, 'candidate_apk_sha256': NEW_SHA, 'gates': {}, 'ui_roles': [], 'historical_transport_sha256': PROFILE_TX_SHA, 'historical_activation_sha256': PROFILE_ACTIVATION_SHA, 'automatic_retry': False, 'whole_app_production_ready': False, 'package_mutations': 0, 'permission_changes': 0, 'account_operations': 0, 'helper_event_writes': 0, 'provider_write_commands_excluding_empty_calendar_cleanup': 0, 'historical_reader_sha256': READER_SHA, 'original_private_adapter_sha256': ADAPTER_SHA, 'atomic_empty_delete_review_sha256': ATOMIC_SHA, 'lease_seconds': LEASE_SECONDS, 'cleanup_seconds': CLEANUP_SECONDS}

        def shell_grants(self):
            raw = self.s.android(['/system/bin/pm', 'list', 'packages', '-U', '--user', '0', 'com.android.shell'], 12).decode()
            need([line for line in raw.splitlines() if line.startswith('package:com.android.shell ')] == ['package:com.android.shell uid:2000'], 'ACTUAL_SHELL_UID_REQUIRED')
            rows = probe.shared_shell_permission_rows(self.s.android(['/system/bin/dumpsys', 'package', 'com.android.shell'], 15).decode())
            need(all((m.permission_granted(rows, name) for name in m.GRANTS)), 'EXISTING_SHELL_CALENDAR_GRANTS_REQUIRED')
            return [row for row in rows if any((row.startswith(name + ':') for name in m.GRANTS))]

        def snapshot(self, label):
            value = self.model.read(label)
            emit({'type': 'owned-provider-observation', 'phase': self.phase, 'value': value, 'business_pending': self.business_pending, 'ui_pending': self.ui.pending})
            return value

        def finish_business(self, role, proof):
            need(self.business_pending is not None and self.business_pending['role'] == role, 'EXACT_PENDING_BUSINESS_ROLE_REQUIRED')
            token = self.business_pending['token']
            if token in self.ui.pending:
                old = self.ui.pending[token]
                need(old.get('kind') == 'tap', 'UNKNOWN_NONBUSINESS_INPUT_RETAINED')
                self.record('business-input-readback-reconciled', {'token': token, 'original_pending': old, 'proof': proof, 'action_replayed': False, 'original_ack_rewritten': False})
                del self.ui.pending[token]
            need(not self.ui.pending, 'ANOTHER_INPUT_STILL_PENDING')
            self.business_pending = None
    return CoreFlow
