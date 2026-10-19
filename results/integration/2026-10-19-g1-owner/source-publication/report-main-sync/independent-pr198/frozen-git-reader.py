#!/usr/bin/env python3
"""Review fixed Git delivery bytes only; do not execute archived code or tests."""
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit
import argparse
import collections
import datetime
import hashlib
import io
import json
import posixpath
import re
import stat
import subprocess
import tarfile
import traceback
import zipfile

PREFIX = 'results/integration/2026-10-19-g1-owner/'
QUALIFIED_TREE = '2b873aa43445c8a02351f5900074a38c6fa4820d'
QUALIFIED_COMMIT = '1ca738c6310c50565804c2ea2a5d413a74bbe80a'
HISTORY_BASE = 'e15ae6a63edb5d4e7c475a001be82111d451b653'
R9_BASE = '0c2bf0fc1ba473325a0266c7bd476b1ddbf66383'
R9_PREFIXES = ('results/integration/2026-10-18-objective-history/',
               'results/integration/2026-10-18-objective-history-ci/')
ALLOWED = {'docs/INDEX.md', 'docs/STATUS.md'}
FROZEN_CI = {
    'g1-remote-ci-f744': ('f744-frozen-files.json', 'fd7272ea240c83d695e6e11c2d2561ebcddf3dd6183535b6381085d806654cd8'),
    'g1-remote-ci-463f': ('463f-frozen-files.json', '8c76942b1be82321eb5cb3098b2139c83da48d2d9b32e57ad1cb42f30f15db3d'),
    'g1-remote-ci-107afb': ('107afb-frozen-files.json', '79bfaf1b4844242cc1f8becf0770ceed9d517650481dd8f23d6f85de0a3c7731'),
    'g1-remote-ci-1c054': ('1c054-frozen-files.json', '21b8d2f289502883cba16148d6876a74cf5d235428baa7a19e90e3963875bdc7'),
}
ORIGINAL_ARCHIVES = {
    'g1-evidence/raw-evidence.tar.xz': (10602828, '6a20eefe453be83e04ad74ac99e79206d20034025c30a743f9a95ce2e6b370fd'),
    'hepta-security/raw-evidence.tar.xz': (2752828, '8f46f3080bd9645a57ed44c8910c616b9035d4ddaf84e6cd6fb3d4bd7e1311ac'),
    'hepta-bazel-followup/raw-evidence.tar.xz': (969644, 'd53aaa52bbf7a905ecfc83caa81a1a623bdfaccbed3fa3b7c2fa077588e96cdb'),
    'g1-ci-host-correction/raw-evidence.tar.xz': (74564, 'e5ba4f7543934283b7e649c48bef0f08de073aa311f9030ffa07ef12bb5f13e2'),
}

checks = []
def need(value, label):
    if not value:
        raise ValueError(label)
    checks.append(label)

def sha(data):
    return hashlib.sha256(data).hexdigest()

def safe(name):
    p = PurePosixPath(name)
    need(bool(name) and not p.is_absolute() and '..' not in p.parts and
         '\\' not in name and '\0' not in name and str(p) == name,
         'safe relative path: ' + name)
    return name

def relative(parent, name):
    return posixpath.join(parent, safe(name))

class Objects:
    def __init__(self, repo):
        self.repo = repo
        self.process = subprocess.Popen(
            ['git', '--no-optional-locks', '-C', str(repo), 'cat-file', '--batch'],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        self.small = {}
        self.digests = {}

    def git(self, *args):
        return subprocess.check_output(['git', '--no-optional-locks', '-C', str(self.repo), *args])

    def tree(self, revision):
        result = {}
        for row in self.git('ls-tree', '-rz', revision).split(b'\0'):
            if not row:
                continue
            fields, name = row.split(b'\t', 1)
            mode, kind, oid = fields.decode().split()
            name = name.decode()
            need(kind == 'blob' and name not in result, 'regular Git blob item: ' + name)
            result[name] = {'mode': mode, 'git_blob': oid}
        return result

    def blob(self, oid):
        if oid in self.small:
            return self.small[oid]
        self.process.stdin.write((oid + '\n').encode())
        self.process.stdin.flush()
        fields = self.process.stdout.readline().decode().split()
        need(len(fields) == 3 and fields[:2] == [oid, 'blob'], 'Git batch object header')
        length = int(fields[2])
        data = self.process.stdout.read(length)
        need(len(data) == length and self.process.stdout.read(1) == b'\n', 'complete Git batch object')
        need(hashlib.sha1(b'blob ' + str(length).encode() + b'\0' + data).hexdigest() == oid,
             'Git blob object bytes: ' + oid)
        self.digests[oid] = {'bytes': length, 'sha256': sha(data)}
        if length <= 262144:
            self.small[oid] = data
        return data

    def data(self, tree, path):
        need(path in tree, 'path exists in fixed Git: ' + path)
        return self.blob(tree[path]['git_blob'])

    def identity(self, tree, path):
        row = tree[path]
        if row['git_blob'] not in self.digests:
            self.blob(row['git_blob'])
        return {**row, **self.digests[row['git_blob']]}

    def close(self):
        self.process.stdin.close()
        self.process.wait(timeout=5)

def match_record(data, record, label):
    need(len(data) == record['bytes'] and sha(data) == record['sha256'], label)

def review(args):
    need(re.fullmatch('[0-9a-f]{40}', args.commit) is not None, 'full fixed commit supplied')
    obj = Objects(args.repo)
    try:
        final = obj.tree(args.commit)
        qualified = obj.tree(QUALIFIED_COMMIT)
        history = obj.tree(HISTORY_BASE)
        old_r9 = obj.tree(R9_BASE)
        need(obj.git('rev-parse', QUALIFIED_COMMIT + '^{tree}').decode().strip() == QUALIFIED_TREE,
             'qualified source tree fixed')
        final_tree = obj.git('rev-parse', args.commit + '^{tree}').decode().strip()
        differences = sorted(p for p in set(final) | set(qualified) if final.get(p) != qualified.get(p))
        need(all(p in ALLOWED or p.startswith(PREFIX) for p in differences), 'all changes within two docs and R10 results')
        for p in ['README.md']:
            need(obj.data(final, p) == obj.data(qualified, p) == b'', 'root README remains empty')

        retained = {p: v for p, v in old_r9.items() if p.startswith(R9_PREFIXES)}
        current_retained = {p: v for p, v in final.items() if p.startswith(R9_PREFIXES)}
        need(len(retained) == 74 and retained == current_retained, 'both R9 directories retain exactly all 74 Git blobs and modes')
        r9_inventory = sha(json.dumps(retained, sort_keys=True, separators=(',', ':')).encode())
        old_status = obj.data(history, 'docs/STATUS.md')
        title = '# 当前状态\n\n'.encode()
        need(old_status.startswith(title), 'e15 STATUS header')
        old_body = old_status[len(title):]
        new_status = obj.data(final, 'docs/STATUS.md')
        need(new_status.startswith(title) and new_status.endswith(old_body), 'complete e15 STATUS body preserved as exact suffix')
        link_pattern = re.compile(r'\[([^\]]+)\]\(([^\s)]+)\)')
        old_links = link_pattern.findall(obj.data(history, 'docs/INDEX.md').decode())
        new_index = obj.data(final, 'docs/INDEX.md').decode()
        old_hrefs = {href for _, href in old_links}
        new_hrefs = {href for _, href in link_pattern.findall(new_index)}
        need(len(old_links) == 105 and len(old_hrefs) == 81 and old_hrefs <= new_hrefs,
             'all 81 unique e15 INDEX hrefs retained (105 original occurrences)')

        manifest_path = PREFIX + 'delivery-manifest.json'
        manifest = json.loads(obj.data(final, manifest_path))
        rows = manifest['entries']
        listed = {safe(r['path']): r for r in rows}
        need(len(listed) == len(rows), 'delivery manifest has unique paths')
        terminal = {manifest_path, PREFIX + 'review/final-delivery-review.json'}
        actual_scope = {p for p in final if p in ALLOWED or p.startswith(PREFIX)}
        need(set(listed) | terminal == actual_scope, 'manifest plus terminal files exactly covers fixed Git delivery')
        need(set(manifest['self_reference_rule']['excluded']) == terminal, 'explicit two-file self-reference exception')
        need(manifest['fixed_local_product_tree'] == QUALIFIED_TREE, 'delivery manifest identifies qualified product tree')
        need(manifest['scope']['files_in_manifest'] == len(rows) and
             manifest['scope']['total_bytes_in_manifest'] == sum(r['bytes'] for r in rows),
             'manifest headline counts match exact entries')
        need(set(manifest['scope']['edited_tracked_documents']) == ALLOWED and
             manifest['scope']['new_results_prefix'] == PREFIX,
             'manifest declared edit scope matches enforced scope')
        need(obj.git('rev-parse', manifest['base_commit'] + '^{tree}').decode().strip() == QUALIFIED_TREE,
             'manifest base resolves to qualified source tree')
        for p, row in listed.items():
            got = obj.identity(final, p)
            need(got['mode'] == row['mode'] and got['bytes'] == row['bytes'] and got['sha256'] == row['sha256'],
                 'manifest byte and mode identity: ' + p)
        omitted = {relative(PREFIX.rstrip('/'), p) for p in manifest['parts_only_archive_publication']['body_omitted_from_Git']}
        need(not (omitted & set(final)), 'all explicitly omitted archive bodies absent from Git')
        producer_review = json.loads(obj.data(final, PREFIX + 'review/final-delivery-review.json'))
        match_record(obj.data(final, manifest_path), producer_review['delivery_manifest'],
                     'terminal producer review binds exact delivery manifest')
        need(producer_review['manifest_file_count'] == len(rows) and
             producer_review['fixed_local_product_tree'] == QUALIFIED_TREE,
             'terminal producer review has matching source and file count')

        reconstructed = {}
        archive_parts = []
        for path in sorted(p for p in final if p.startswith(PREFIX) and p.endswith('/archive-parts.json')):
            parts = json.loads(obj.data(final, path))
            need(parts['schema'] == 'r10.archive-parts.v1', 'known archive parts schema: ' + path)
            parent = posixpath.dirname(path)
            for arc in parts['archives']:
                destination = relative(parent, arc['path'])
                need(destination not in reconstructed, 'one part manifest per archive: ' + destination)
                pieces = arc['parts']
                need([x['index'] for x in pieces] == list(range(len(pieces))), 'contiguous part indices: ' + destination)
                need(len({x['path'] for x in pieces}) == len(pieces), 'unique part names: ' + destination)
                joined = io.BytesIO()
                for piece in pieces:
                    pp = relative(parent, piece['path'])
                    need(final[pp]['mode'] == '100644', 'regular part Git mode: ' + pp)
                    data = obj.data(final, pp)
                    match_record(data, piece, 'individual part identity: ' + pp)
                    need(0 < len(data) <= parts['part_bytes'], 'bounded part length: ' + pp)
                    joined.write(data)
                raw = joined.getvalue()
                match_record(raw, arc, 'reconstructed original archive identity: ' + destination)
                if destination in final:
                    need(raw == obj.data(final, destination), 'retained direct archive equals reconstructed bytes: ' + destination)
                reconstructed[destination] = raw
                archive_parts.append({'manifest': path, 'manifest_sha256': sha(obj.data(final, path)),
                                      'archive': destination, 'bytes': len(raw), 'sha256': sha(raw),
                                      'parts': len(pieces), 'direct_body_in_Git': destination in final})
        need(omitted <= set(reconstructed), 'every omitted body fully reconstructed from fixed Git parts')

        def delivered(path):
            return reconstructed[path] if path in reconstructed else obj.data(final, path)

        frozen = []
        for package, (name, digest) in FROZEN_CI.items():
            parent = PREFIX + package
            raw = obj.data(final, parent + '/' + name)
            need(sha(raw) == digest, 'original independent CI manifest unchanged: ' + package)
            f = json.loads(raw)
            for row in f['files']:
                p = relative(parent, row['path'])
                match_record(delivered(p), row, 'frozen CI material retained: ' + p)
            frozen.append({'package': package, 'manifest_sha256': digest, 'original_files_including_manifest': len(f['files']) + 1})

        # Read archive content in memory. Never extract paths or execute members.
        virtual_targets = {}
        archive_reviews = []
        all_archives = sorted(set(reconstructed) | {p for p in final if p.startswith(PREFIX) and (p.endswith('.tar.xz') or p.endswith('.zip'))})
        for path in all_archives:
            raw = delivered(path)
            parent = posixpath.dirname(path)
            relative_name = path.removeprefix(PREFIX)
            if relative_name in ORIGINAL_ARCHIVES:
                need((len(raw), sha(raw)) == ORIGINAL_ARCHIVES[relative_name], 'original recorded tar identity: ' + path)
            members = {}
            mf_path = None
            if path.endswith('.tar.xz'):
                with tarfile.open(fileobj=io.BytesIO(raw), mode='r:xz') as tf:
                    order = []
                    embedded_manifest = None
                    for member in tf:
                        name = safe(member.name)
                        need(member.isfile() and name not in members, 'unique regular tar member: ' + name)
                        data = tf.extractfile(member).read()
                        need(len(data) == member.size, 'complete tar member: ' + name)
                        members[name] = {'bytes': len(data), 'sha256': sha(data)}
                        order.append(name)
                        if name == 'files-manifest.json':
                            embedded_manifest = data
                need(embedded_manifest is not None, 'archive has its original files manifest: ' + path)
                mf_path = parent + '/files-manifest.json'
                need(embedded_manifest == obj.data(final, mf_path), 'embedded and delivered original manifest identical: ' + path)
                fm = json.loads(embedded_manifest)
                expected = {r['path']: {'bytes': r['bytes'], 'sha256': r['sha256']} for r in fm['files']}
                need(len(expected) == len(fm['files']), 'unique tar manifest records: ' + path)
                expected['files-manifest.json'] = {'bytes': len(embedded_manifest), 'sha256': sha(embedded_manifest)}
                need(expected == members, 'all tar members exactly equal original manifest: ' + path)
                if 'archive_order' in fm:
                    need(order == fm['archive_order'], 'original tar member order: ' + path)
                ap = parent + '/artifact-manifest.json'
                if ap in final:
                    artifact = json.loads(obj.data(final, ap))
                    if 'archive' in artifact:
                        match_record(raw, artifact['archive'], 'artifact manifest original archive identity: ' + path)
                        if 'files_manifest' in artifact:
                            match_record(embedded_manifest, artifact['files_manifest'], 'artifact files-manifest identity: ' + path)
                        for row in artifact.get('primary_copies', []):
                            pp = relative(parent, row['path'])
                            match_record(obj.data(final, pp), row, 'primary copy identity: ' + pp)
                            member = row.get('archive_entry', row['path'])
                            need(members[member] == {'bytes': row['bytes'], 'sha256': row['sha256']}, 'primary equals original archive member: ' + pp)
                    else:
                        # The two later Fleet packages use their frozen schema-1
                        # file inventory, not the earlier primary_copies shape.
                        need(artifact.get('schema') == 1 and isinstance(artifact.get('files'), list),
                             'known later artifact inventory schema: ' + ap)
                        inventory = {safe(r['path']): r for r in artifact['files']}
                        need(len(inventory) == len(artifact['files']), 'unique later artifact inventory: ' + ap)
                        match_record(raw, inventory[posixpath.basename(path)], 'later artifact original archive identity: ' + path)
                        match_record(embedded_manifest, artifact['raw_manifest'], 'later artifact files-manifest identity: ' + path)
                        need(artifact['raw_member_count'] == len(members), 'later artifact actual member count: ' + path)
                        for name, row in inventory.items():
                            match_record(delivered(relative(parent, name)), row, 'later artifact delivered inventory identity: ' + name)
                        for name in artifact['primary_files']:
                            row = inventory[name]
                            need(members[name] == {'bytes': row['bytes'], 'sha256': row['sha256']},
                                 'later primary equals original archive member: ' + name)
                kind = 'tar.xz'
            elif path.endswith('.zip'):
                with zipfile.ZipFile(io.BytesIO(raw)) as z:
                    for member in z.infolist():
                        name = safe(member.filename)
                        need(name not in members and not member.is_dir() and not(member.flag_bits & 1) and not stat.S_ISLNK(member.external_attr >> 16), 'safe regular ZIP member: ' + name)
                        data = z.read(member)
                        need(len(data) == member.file_size, 'complete ZIP member: ' + name)
                        members[name] = {'bytes': len(data), 'sha256': sha(data), 'crc32': format(member.CRC, '08x')}
                    need(z.testzip() is None, 'all actual ZIP CRC values: ' + path)
                candidates = [p for p in final if posixpath.dirname(p) == parent and ('member' in posixpath.basename(p)) and p.endswith('.json')]
                matching = []
                for candidate in candidates:
                    m = json.loads(obj.data(final, candidate))
                    archive_name = m.get('archive', m.get('zip_name'))
                    expected_digest = m.get('archive_sha256', m.get('zip_sha256', m.get('sha256')))
                    # The later Fleet member receipt binds by actual archive
                    # digest/size and artifact ID, with no redundant basename.
                    if archive_name != posixpath.basename(path) and not (archive_name is None and expected_digest == sha(raw)):
                        continue
                    rows = m.get('members', m.get('files'))
                    need(isinstance(rows, list), 'known ZIP members list schema: ' + candidate)
                    expected = {safe(r['path']): r for r in rows}
                    need(len(expected) == len(rows) and set(expected) == set(members), 'exact unique ZIP manifest member set: ' + candidate)
                    for name, row in expected.items():
                        need(all(row[k] == members[name][k] for k in ('bytes', 'sha256')) and
                             ('crc32' not in row or row['crc32'] == members[name]['crc32']),
                             'ZIP member bytes/digest and every recorded CRC: ' + name)
                    need(expected_digest == sha(raw), 'ZIP member manifest archive binding: ' + candidate)
                    if 'archive_bytes' in m:
                        need(m['archive_bytes'] == len(raw), 'ZIP member manifest archive size: ' + candidate)
                    matching.append(candidate)
                need(len(matching) == 1, 'one original member manifest for each delivered ZIP: ' + path)
                mf_path = matching[0]
                kind = 'zip'
            else:
                raise ValueError('Unknown reconstructed archive format: ' + path)
            for name, metadata in members.items():
                virtual_targets[relative(parent, name)] = {'archive': path, **metadata}
            archive_reviews.append({'archive': path, 'kind': kind, 'bytes': len(raw), 'sha256': sha(raw),
                                    'members': len(members), 'uncompressed_bytes': sum(v['bytes'] for v in members.values()),
                                    'original_member_manifest': mf_path, 'member_manifest_sha256': sha(obj.data(final, mf_path))})

        # Independently resolve local Markdown file targets from the Git tree or
        # verified archive members, distinguishing archived paths from Git files.
        documents = [(p, obj.data(final, p)) for p in sorted(final) if p.startswith(PREFIX) and p.endswith('.md')]
        documents += [('docs/INDEX.md', new_index.encode()), ('docs/STATUS.md', new_status[:-len(old_body)])]
        link_counts = collections.Counter()
        missing = []
        for document, raw in documents:
            for _, href in link_pattern.findall(raw.decode()):
                u = urlsplit(href)
                if u.scheme or u.netloc:
                    link_counts['external_not_refetched'] += 1
                    continue
                p = posixpath.normpath(posixpath.join(posixpath.dirname(document), unquote(u.path))) if u.path else document
                if p.startswith('/') or p.startswith('../'):
                    missing.append({'from': document, 'href': href, 'target': p, 'reason': 'outside repository'})
                elif p in final:
                    link_counts['fixed_git_file'] += 1
                elif any(x.startswith(p.rstrip('/') + '/') for x in final):
                    link_counts['fixed_git_directory'] += 1
                elif p in reconstructed:
                    link_counts['archive_body_restored_from_parts'] += 1
                elif p in virtual_targets:
                    link_counts['archive_member_extract_first'] += 1
                elif any(x.startswith(p.rstrip('/') + '/') for x in virtual_targets):
                    link_counts['archive_directory_extract_first'] += 1
                else:
                    missing.append({'from': document, 'href': href, 'target': p, 'reason': 'missing from Git and verified archives'})
        need(not missing, 'all local primary Markdown targets resolve: ' + json.dumps(missing, ensure_ascii=False))

        return {
            'source': {'commit': args.commit, 'tree': final_tree, 'qualified_commit': QUALIFIED_COMMIT,
                       'qualified_tree': QUALIFIED_TREE, 'source_paths_unchanged_outside_delivery': True,
                       'allowed_edited_documents': sorted(ALLOWED), 'new_results_prefix': PREFIX,
                       'changed_paths': len(differences), 'tracked_files': len(final)},
            'delivery': {'manifest': manifest_path, 'manifest_sha256': sha(obj.data(final, manifest_path)),
                         'entries': len(listed), 'entry_bytes': sum(r['bytes'] for r in listed.values()),
                         'two_self_reference_terminals': sorted(terminal), 'git_delivery_file_count': len(actual_scope),
                         'omitted_bodies_absent_from_Git': sorted(omitted), 'root_README_bytes': 0},
            'history': {'R9_base': R9_BASE, 'R9_prefixes': R9_PREFIXES, 'R9_files': len(retained),
                        'R9_original_blob_mode_map_sha256': r9_inventory, 'all_74_original_blobs_modes_retained': True,
                        'e15_base': HISTORY_BASE, 'STATUS_suffix_bytes': len(old_body), 'STATUS_suffix_sha256': sha(old_body),
                        'STATUS_suffix_preserved': True, 'INDEX_old_link_occurrences': len(old_links),
                        'INDEX_old_unique_hrefs': len(old_hrefs), 'all_81_hrefs_preserved': True},
            'archive_parts': archive_parts, 'archive_parts_count': sum(x['parts'] for x in archive_parts),
            'archive_reviews': archive_reviews, 'frozen_original_CI_groups': frozen,
            'markdown': {'documents': len(documents), 'target_counts': dict(link_counts), 'missing': missing,
                         'fragments_checked': False, 'external_sites_refetched': False},
            'limits': ['Only immutable Git objects were used for delivery validation; no physical worktree copy was treated as a tracked file.',
                       'Original archives were reconstructed in memory from actual tracked part bytes and independently parsed; no archive command or downloaded executable was run.',
                       'The 74 historical R9 files were compared by original Git blob and mode. Their old runtime evidence was not reexecuted.',
                       'The full incoming e15 STATUS body and 81 unique INDEX references were preserved. External URLs and Markdown anchors were not newly validated.',
                       'This is a delivery/source-integrity review, not new Cargo, QEMU, native-device, Hepta or post-merge CI qualification.'],
        }
    finally:
        obj.close()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    args = parser.parse_args()
    args.repo = args.repo.resolve()
    args.receipt = args.receipt.resolve()
    need(not args.receipt.is_relative_to(args.repo), 'review receipt remains outside product checkout')
    need(not args.receipt.exists(), 'new receipt path, no overwrite')
    started = datetime.datetime.now(datetime.timezone.utc).isoformat()
    script = Path(__file__).read_bytes()
    result = {'schema': 'r10.frozen-git-delivery-independent-review.v1', 'reviewer': '/root/r9_g1_contract',
              'started_at_utc': started, 'commit': args.commit, 'review_script_sha256': sha(script)}
    exit_code = 0
    try:
        result.update(review(args))
        result.update({'status': 'passed', 'blocking_findings': []})
    except Exception as exc:
        result.update({'status': 'failed', 'blocking_findings': [str(exc)], 'traceback': traceback.format_exc()})
        exit_code = 1
    result['completed_at_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    result['checks_completed'] = len(checks)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    with args.receipt.open('x') as stream:
        stream.write(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    with args.receipt.with_name(args.receipt.stem + '-reviewer.py').open('xb') as stream:
        stream.write(script)
    print(json.dumps({'status': result['status'], 'blocking_findings': result['blocking_findings'],
                      'checks_completed': len(checks), 'receipt': str(args.receipt)}, ensure_ascii=False))
    raise SystemExit(exit_code)

if __name__ == '__main__':
    main()
