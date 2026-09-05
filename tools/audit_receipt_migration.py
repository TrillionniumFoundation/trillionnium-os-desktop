"""Source-local regression guard for offline legacy copy, not deployment proof."""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path
import re
import tomllib

INPUTS = {
    'source': 'crates/hepta-session-core/src/receipt_journal/migration.rs',
    'managed': 'crates/hepta-session-core/src/receipt_journal/managed.rs',
    'chain': 'crates/hepta-session-core/src/receipt_journal/chain.rs',
    'journal': 'crates/hepta-session-core/src/receipt_journal.rs',
    'api': 'crates/hepta-session-core/src/lib.rs',
    'tests': 'crates/hepta-session-core/src/receipt_journal/migration_tests.rs',
    'process': 'crates/hepta-session-core/tests/journal_migration_process.rs',
    'cargo': 'crates/hepta-session-core/Cargo.toml',
}
CONTRACT = 'contracts/legacy-receipt-migration.v1.json'
DOCUMENT = 'docs/architecture/LEGACY_RECEIPT_MIGRATION.md'
CUTS = [
    'migration.before_directory_create', 'migration.after_directory_create',
    'migration_marker.before_write', 'migration_marker.partial_write',
    'migration.after_marker_sync',
    'migration_segment_0.before_write', 'migration_segment_0.partial_write',
    'migration_segment_0.before_sync', 'migration_segment_0.after_sync',
    'migration_segment_1.before_write', 'migration_segment_1.partial_write',
    'migration_segment_1.before_sync', 'migration_segment_1.after_sync',
    'migration.before_publish', 'migration.after_publish', 'migration.after_directory_sync',
]
EXPECTED = {
    'schema': 'trillionnium.desktop.legacy-receipt-migration.v1',
    'status': 'SOURCE_CANDIDATE', 'work_package': 'D0C-06',
    'api': 'ReceiptJournal::copy_legacy_chain_to_managed',
    'source_selection': 'caller_authoritative_complete_ordered_chain',
    'source_access': 'read_only_descriptors_all_inode_locks',
    'source_repair': False, 'source_lease_mutation': False, 'source_deletion': False,
    'maximum_segments': 64, 'maximum_segment_bytes': 67108864,
    'maximum_total_bytes': 134217728, 'maximum_records': 131072,
    'destination': 'new_private_directory_only', 'staging_marker': 'migration.pending',
    'commit_marker': 'store.v1', 'record_encoding': 'byte_identical_v1_no_reencoding',
    'commit_order': ['validate_sources', 'reserve_new_directory', 'sync_staged_marker',
                     'copy_and_sync_segments', 'revalidate_sources_and_copies',
                     'sync_staging_directory', 'rename_marker', 'sync_committed_directory',
                     'postverify_then_report'],
    'partial_destination': 'reject_preserve_no_resume',
    'post_commit_error': 'may_have_complete_copy_never_infer_absence',
    'report_authority': 'copy_facts_only_not_writer_or_cutover',
    'automatic_service_cutover': False, 'automatic_replay': False,
    'authenticated_rollback_protection': False, 'physical_power_loss_qualified': False,
    'promotion_authoritative': False, 'installed_cli': False,
    'process_cut_cases': 16, 'injected_io_combinations': 32,
    'cutpoints': CUTS, 'required_sources': list(INPUTS.values()), 'document': DOCUMENT,
}
_SPEC = importlib.util.spec_from_file_location('_receipt_migration_helpers', Path(__file__).with_name('verify_receipt_journal.py'))
assert _SPEC and _SPEC.loader
_HELPERS = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_HELPERS)

def audit(inputs: dict[str, str], contract_text: str) -> list[str]:
    if set(inputs) != set(INPUTS):
        return ['receipt migration source inventory mismatch']
    try:
        contract = _HELPERS.strict_json(contract_text)
        if type(contract) is not dict: raise ValueError('not object')
    except (ValueError, TypeError):
        return ['receipt migration contract is not strict JSON']
    errors = []
    if json.dumps(contract, sort_keys=True, separators=(',', ':'), allow_nan=False) != json.dumps(EXPECTED, sort_keys=True, separators=(',', ':'), allow_nan=False):
        errors.append('receipt migration contract fields/types or non-claims changed')
    code = {k: _HELPERS.mask_rust_non_code(v) for k, v in inputs.items() if k != 'cargo'}
    def body(key, name):
        found = _HELPERS.rust_function_body(code[key], name)
        if not found: errors.append('missing receipt migration function ' + key + '.' + name)
        return found
    def require(text, pattern, label):
        if not re.search(pattern, text, re.S): errors.append('receipt migration lost ' + label)
    def order(text, patterns, label):
        start = 0
        for pattern in patterns:
            found = re.search(pattern, text[start:], re.S)
            if not found:
                errors.append('receipt migration ordering lost ' + label)
                return
            start += found.end()
    source = code['source']
    order(body('source','acquire'), [r'chain::bounded_paths\(paths\)\?', r'reject_unmanaged_access\(&path\)\?', r'open_existing_file_checked\(&path, false, identity\)\?', r'lock_file\(&file\)\?', r'recover_bytes\(&bytes\)\?', r'chain::validate_reports\(&inspected, false\)\?'], 'strict locked read-only source admission')
    require(body('source','acquire'), r'!identities.insert\(identity\)', 'duplicate inode refusal')
    require(body('source','acquire'), r'bytes > MAX_SEGMENT_BYTES \|\| total_bytes > MAX_CHAIN_BYTES', 'source byte bounds')
    require(body('source','acquire'), r'report.header.journal_id != id', 'journal identity')
    order(body('source','read_unchanged'), [r'item.verify_current\(\)\?', r'read_segment_bytes\(&mut item.file\)\?', r'sha256\(&bytes\) != self.digests\[index\]', r'item.verify_current\(\)\?'], 'source digest and identity resampling')
    staged = body('source','verify_staging')
    for pattern in [r'count > MAX_CHAIN_SEGMENTS', r'actual != expected', r'bytes != marker_bytes\(id\)', r'validate_existing_path_identity\(&entry.path\(\)\)\?', r'sha256\(&read_segment_bytes\(&mut segment.file\)\?\) != \*expected']:
        require(staged, pattern, 'closed staging inventory and digest')
    migrate = body('source','copy_legacy_chain_to_managed')
    order(migrate, [r'validate_new_path\(root\)\?', r'LegacySource::acquire\(paths, expected_journal_id\)\?', r'fs::DirBuilder::new\(\)', r'\.create\(root\)', r'lock_directory\(root\)\?', r'create_private_file\(&marker_path, true\)\?', r'marker_file.sync_all\(\).map_err\(map_io_error\)\?', r'source.read_unchanged\(index\)\?', r'create_private_file\(&path, true\)\?', r'file.sync_all\(\).map_err\(map_io_error\)\?', r'source.verify_all\(\)\?', r'verify_staging\(', r'directory.sync_all\(\).map_err\(map_io_error\)\?', r'fs::rename\(&marker.path, root.join\(MARKER\)\).map_err\(map_io_error\)\?', r'directory.sync_all\(\).map_err\(map_io_error\)\?', r'guard.verify_current\(\)\?', r'source.verify_all\(\)\?', r'Ok\(ReceiptMigrationReport'], 'copy commit and postvalidation')
    require(migrate, r'sha256\(&read_segment_bytes\(&mut copy.file\)\?\) != \*expected', 'post-publication copied digest')
    require(body('managed','reject_unmanaged_access'), r'for name in \[MARKER, migration::MIGRATION_PENDING\]', 'staging blocks legacy write APIs')
    require(code['journal'], r'mod managed;', 'canonical journal module')
    require(code['managed'], r'mod migration;', 'migration source compiled')
    require(code['api'], r'ReceiptMigrationReport', 'public report export')
    if re.search(r'unsafe|std::(?:net|process)|Command::|WriterLease|\.set_len\(|fs::(?:remove|write|hard_link|copy)|\.append\(|\.rotate\(', source):
        errors.append('receipt migration acquired forbidden source mutation or execution authority')
    # Every user-space fault call is cfg(test)-guarded at its statement, not just
    # hidden by a test-only callee. This does not replace compiler/runtime tests.
    for match in re.finditer(r'persistence_tests::(?:point|before_write)\(', source):
        if not re.search(r'#\[cfg\(test\)\]\s*$', source[:match.start()]):
            errors.append('receipt migration test hook escaped cfg(test)')
    for key, constant in [('tests','CUTS'), ('process','CASES')]:
        text = re.sub(r'(?m)^\s*//[^\n]*', '', inputs[key])
        found = re.search(rf'const\s+{constant}\s*:[^=]+?=\s*&\[(.*?)\];', text, re.S)
        actual = re.findall(r'"([^"\n]+)"', found.group(1)) if found else []
        if actual != CUTS: errors.append('receipt migration fault inventory changed ' + key)
    for name in ['copy_preserves_every_byte_and_source_sidecar', 'source_descriptors_are_read_only_and_create_no_lease', 'rejects_active_source_writer_before_creating_destination', 'torn_and_corrupt_source_is_rejected_without_repair', 'injected_io_faults_preserve_sources_and_never_admit_partial_copy']:
        require(code['tests'], rf'#\[test\]\s*fn {name}\(', 'runtime regression '+name)
    require(code['process'], r'child.0.kill\(\).unwrap\(\)', 'actual child termination')
    require(code['process'], r'child.0.wait\(\).unwrap\(\).signal\(\), Some\(9\)', 'SIGKILL confirmation')
    if '#[path = "../src/receipt_journal.rs"]' not in inputs['process']:
        errors.append('migration process must compile the actual journal source')
    try:
        targets = tomllib.loads(inputs['cargo']).get('test', [])
        selected = [item for item in targets if item.get('name') == 'journal_migration_process']
        if selected != [{'name':'journal_migration_process', 'path':'tests/journal_migration_process.rs', 'harness':False}]:
            errors.append('migration custom process target missing or gated')
    except (ValueError, TypeError): errors.append('migration Cargo target cannot be parsed')
    return errors
