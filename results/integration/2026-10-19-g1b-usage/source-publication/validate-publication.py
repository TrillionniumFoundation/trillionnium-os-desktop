#!/usr/bin/env python3
"""Bounded, read-only R11 publication checks. Never executes published code.

Generate the report before the outer files-manifest; then run a second check to
an external output path after that outer manifest is frozen. No producer
manifest is changed, and later subpackages are outside an older producer scope.
"""
from pathlib import Path, PurePosixPath
from datetime import datetime, timezone
from urllib.parse import urlsplit, parse_qsl, unquote
import argparse
import hashlib
import html
import io
import json
import lzma
import os
import re
import stat
import subprocess
import zipfile

PREFIX = 'results/integration/2026-10-19-g1b-usage'
DOCS = ['docs/ASTERINAS_CPU_USAGE_G1B.md', 'docs/INDEX.md', 'docs/STATUS.md']
BASE = 'b8d5af3f82aa8c262560fd52a79408a18e18bde1'
MAX_UNIT = 32 * 1024 * 1024
MAX_DECODED = 256 * 1024 * 1024
HEX_SHA = re.compile(r'^[0-9a-f]{64}$')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()


def safe_relative(name):
    path = PurePosixPath(name)
    return bool(name) and not path.is_absolute() and '..' not in path.parts and '\\' not in name


def link_destinations(markdown):
    """Inline, image and reference destinations; code blocks/spans excluded."""
    lines, fence = [], None
    for line in markdown.splitlines():
        opening = re.match(r'^\s{0,3}(`{3,}|~{3,})', line)
        if opening:
            mark = opening[1]
            if fence is None:
                fence = mark
            elif mark[0] == fence[0] and len(mark) >= len(fence):
                fence = None
            lines.append('')
        else:
            lines.append('' if fence else line)
    text = '\n'.join(lines)
    text = re.sub(r'(`+)([^\n]*?)\1', '', text)
    references = {}
    for match in re.finditer(r'^\s{0,3}\[([^\]\n]+)\]:\s*(?:<([^>\n]+)>|(\S+))', text, re.M):
        references[' '.join(match[1].lower().split())] = match[2] or match[3]
    found = []
    inline = re.compile(r'!?\[([^\]\n]*)\]\(\s*(<[^>\n]+>|(?:\\.|[^\s)\\]|\([^\n)]*\))+)(?:\s+[\"\'][^\n]*?[\"\'])?\s*\)')
    for match in inline.finditer(text):
        found.append(match[2].strip('<>'))
    for match in re.finditer(r'!?\[([^\]\n]+)\]\[([^\]\n]*)\]', text):
        key = ' '.join((match[2] or match[1]).lower().split())
        if key in references:
            found.append(references[key])
    return found


class Review:
    def __init__(self, args):
        self.args = args
        self.repo = args.repo.resolve()
        self.report = self.repo / PREFIX
        self.errors, self.notes = [], []
        self.aliases, self.physical = {}, {}
        self.raw_units, self.text_count, self.decoded_bytes = 0, 0, 0
        self.archives, self.sensitive = [], []
        self.hit_keys = set()
        self.manifests = []

    def error(self, kind, **detail):
        self.errors.append({'kind': kind, **detail})

    def git(self, *argv):
        env = dict(os.environ, GIT_NO_LAZY_FETCH='1', GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL='/dev/null')
        result = subprocess.run(['git', '-c', 'core.fsmonitor=false', *argv], cwd=self.repo,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
        if result.returncode:
            raise ValueError('Read-only Git command failed: ' + ' '.join(argv[:3]) + '; exit ' + str(result.returncode))
        return result.stdout

    def identity(self, data):
        return {'bytes': len(data), 'sha256': digest(data)}

    def add_alias(self, virtual_path, data, origin):
        identity = self.identity(data)
        self.aliases.setdefault(virtual_path, [])
        if not any(row['origin'] == origin for row in self.aliases[virtual_path]):
            self.aliases[virtual_path].append({**identity, 'origin': origin, 'data': data})

    def hit(self, kind, origin, value):
        # Do not reveal the candidate credential or signed URL in output.
        fingerprint = digest(value.encode())
        key = (kind, origin, fingerprint)
        if key not in self.hit_keys:
            self.hit_keys.add(key)
            self.sensitive.append({'kind': kind, 'origin': origin, 'candidate_sha256': fingerprint})

    def scan_text(self, text, origin):
        self.text_count += 1
        patterns = {
            'private_key_pem_header': r'-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----',
            'github_token': r'\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{40,})\b',
            'aws_access_key_id': r'\b(?:AKIA|ASIA)[0-9A-Z]{16}\b',
            'openai_project_secret': r'\bsk-proj-[A-Za-z0-9_-]{24,}\b',
            'unredacted_authorization_header': r'(?i)authorization[\"\']?\s*[:=]\s*[\"\']?(?:bearer|basic)\s+([A-Za-z0-9+/=_.-]{16,})',
        }
        for name, pattern in patterns.items():
            for match in re.finditer(pattern, text):
                self.hit(name, origin, match[0])
        url_pattern = r'https?://[^\s<>\"\'`\\]+'

        def inspect_string(value):
            normalized = html.unescape(value)
            for _ in range(2):
                decoded = unquote(normalized)
                if decoded == normalized:
                    break
                normalized = decoded
            for match in re.finditer(url_pattern, normalized):
                candidate = match[0].rstrip('),.;]')
                parsed = urlsplit(candidate)
                keys = {key.lower(): val for key, val in parse_qsl(parsed.query, keep_blank_values=True)}
                signed = {'sig', 'signature', 'x-amz-signature', 'x-amz-credential', 'x-amz-security-token',
                          'x-goog-signature', 'x-goog-credential', 'access_token', 'refresh_token'}
                active = {key: val for key, val in keys.items() if key in signed and val
                          and not re.fullmatch(r'\*+|<[^>]+>|\{[^}]+\}|\[?REDACTED\]?', val, re.I)}
                if active:
                    self.hit('temporary_signed_or_token_url', origin, candidate)
                if parsed.username is not None and parsed.password is not None:
                    self.hit('credential_in_url_authority', origin, candidate)
            if re.search(r'(?:file-service|openai-file|attachment)://[^\s\"\']+', normalized):
                self.hit('temporary_file_reference', origin, normalized)

        inspect_string(text)
        try:
            parsed = json.loads(text)
        except (ValueError, RecursionError):
            return
        stack = [parsed]
        while stack:
            value = stack.pop()
            if isinstance(value, dict):
                for key, item in value.items():
                    if key == 'file_uri' and isinstance(item, str) and item.strip():
                        self.hit('nonempty_file_uri', origin, item)
                    stack.append(item)
            elif isinstance(value, list):
                stack.extend(value)
            elif isinstance(value, str):
                inspect_string(value)

    def decode(self, data, virtual_path, origin, depth=0):
        self.raw_units += 1
        if len(data) > MAX_UNIT or depth > 4:
            self.error('bounded_decode_limit', origin=origin, bytes=len(data), depth=depth)
            return
        self.add_alias(virtual_path, data, origin)
        if data.startswith(b'\xfd7zXZ\x00'):
            try:
                stream = lzma.LZMADecompressor()
                decoded = stream.decompress(data, max_length=MAX_UNIT + 1)
                if not stream.eof or stream.unused_data or len(decoded) > MAX_UNIT:
                    raise ValueError('XZ did not complete within bounds or has trailing stream')
                self.decoded_bytes += len(decoded)
                if self.decoded_bytes > MAX_DECODED:
                    raise ValueError('Total decode bound exceeded')
                target = virtual_path[:-3] if virtual_path.endswith('.xz') else virtual_path + '!decoded'
                self.decode(decoded, target, origin + '!xz', depth + 1)
            except (ValueError, lzma.LZMAError) as error:
                self.error('xz_decode_failed', origin=origin, error_type=type(error).__name__)
            return
        if zipfile.is_zipfile(io.BytesIO(data)):
            try:
                with zipfile.ZipFile(io.BytesIO(data)) as archive:
                    infos = archive.infolist()
                    names = [info.filename for info in infos]
                    if len(names) != len(set(names)) or sum(info.file_size for info in infos) > MAX_DECODED:
                        raise ValueError('ZIP duplicate names or decode size limit')
                    for info in infos:
                        if not safe_relative(info.filename) or info.flag_bits & 1 or stat.S_IFMT(info.external_attr >> 16) == stat.S_IFLNK:
                            raise ValueError('ZIP unsafe path, encrypted entry or symlink')
                        if info.is_dir():
                            continue
                        if info.file_size > MAX_UNIT:
                            raise ValueError('ZIP member too large')
                        member = archive.read(info)
                        self.decoded_bytes += len(member)
                        if self.decoded_bytes > MAX_DECODED:
                            raise ValueError('Total decode bound exceeded')
                        target = str(PurePosixPath(virtual_path).parent / info.filename)
                        self.decode(member, target, origin + '!zip:' + info.filename, depth + 1)
                    self.archives.append({'path': origin, 'members': len(infos), 'uncompressed_bytes': sum(i.file_size for i in infos), 'all_read_crc_ok': True})
            except (ValueError, zipfile.BadZipFile, RuntimeError) as error:
                self.error('zip_decode_failed', origin=origin, error_type=type(error).__name__)
            return
        try:
            text = data.decode('utf-8-sig')
        except UnicodeDecodeError:
            self.error('opaque_unscanned_selected_file', origin=origin, bytes=len(data))
            return
        self.scan_text(text, origin)

    def scope(self):
        base = self.git('rev-parse', self.args.base + '^{commit}').decode().strip()
        current = self.git('rev-parse', 'HEAD').decode().strip()
        current_tree = self.git('rev-parse', 'HEAD^{tree}').decode().strip()
        changes = set(filter(None, self.git('diff', '--name-only', '-z', '--no-ext-diff', '--no-renames', base, '--').decode().split('\0')))
        changes.update(filter(None, self.git('ls-files', '-z', '--others', '--exclude-standard').decode().split('\0')))
        unexpected = sorted(p for p in changes if p not in DOCS and not p.startswith(PREFIX + '/'))
        if unexpected:
            self.error('unexpected_changed_paths', paths=unexpected)
        changed_docs = sorted(p for p in changes if p in DOCS)
        if set(changed_docs) != set(DOCS):
            self.error('required_three_document_changes_not_present', actual=changed_docs)
        prior_prefix = self.git('ls-tree', '-r', '--name-only', base, '--', PREFIX).decode().splitlines()
        if prior_prefix:
            self.error('report_prefix_was_not_new_at_requested_base', paths=prior_prefix)
        readme = self.repo / 'README.md'
        readme_data = readme.read_bytes()
        base_readme = self.git('show', base + ':README.md')
        if readme_data or base_readme:
            self.error('root_README_not_zero_bytes', worktree_bytes=len(readme_data), base_bytes=len(base_readme))
        return {'base': base, 'head': current, 'head_tree': current_tree, 'documentation_changed_paths': changed_docs,
                'new_report_prefix': PREFIX, 'changed_path_count': len(changes), 'unexpected_changed_paths': unexpected,
                'root_README_bytes': len(readme_data), 'base_root_README_bytes': len(base_readme)}

    def snapshot(self):
        data = {}
        roots = [self.repo / p for p in DOCS] + [self.repo / 'README.md']
        if self.report.exists():
            roots.extend(p for p in self.report.rglob('*') if p.is_file() or p.is_symlink())
        for path in sorted(roots):
            if path.is_symlink():
                self.error('publication_symlink', path=str(path.relative_to(self.repo)))
                continue
            rel = str(path.relative_to(self.repo))
            raw = path.read_bytes()
            data[rel] = {'bytes': len(raw), 'sha256': digest(raw)}
        return data

    def manifests_check(self):
        physical_manifests = [p for p in sorted(self.report.rglob('*.json'))
                              if 'manifest' in p.name or p.name == 'publication-selection.json']
        parsed = []
        for path in physical_manifests:
            try:
                data = json.loads(path.read_text())
            except ValueError:
                self.error('invalid_json_manifest', path=str(path.relative_to(self.repo)))
                continue
            parsed.append((path, data))
        # Exact producer-declared lossless mappings make original uncompressed
        # manifest rows verifiable without requiring excluded duplicate files.
        for path, data in parsed:
            for binding in data.get('lossless_original_bindings', []):
                parent = path.parent
                old, published = binding['original_path'], binding['published_path']
                if not safe_relative(old) or not safe_relative(published):
                    self.error('unsafe_lossless_binding', manifest=str(path.relative_to(self.repo)))
                    continue
                carrier = parent / published
                if not carrier.exists():
                    self.error('missing_lossless_carrier', path=str(carrier.relative_to(self.repo)))
                    continue
                candidates = self.aliases.get(str(carrier.relative_to(self.repo)).removesuffix('.xz'), [])
                matches = [r for r in candidates if r['bytes'] == binding['original_bytes'] and r['sha256'] == binding['original_sha256']]
                if len(matches) != 1:
                    self.error('lossless_binding_identity_mismatch', original=old, carrier=str(carrier.relative_to(self.repo)))
                    continue
                self.add_alias(str((parent / old).relative_to(self.repo)), matches[0]['data'], matches[0]['origin'])

        for path, data in parsed:
            rel = str(path.relative_to(self.repo))
            required, optional = [], []
            if 'publication_selection_excluding_this_manifest' in data:
                required.extend(data['publication_selection_excluding_this_manifest'])
                optional.extend(data.get('files', []))
            elif isinstance(data.get('files'), list):
                required.extend(data['files'])
            if isinstance(data.get('selection'), list):
                required.extend(data['selection'])
            if isinstance(data.get('selected'), list):
                required.extend(data['selected'])
            for key in ['review', 'report', 'index']:
                row = data.get(key)
                if isinstance(row, dict) and all(k in row for k in ['path', 'bytes', 'sha256']):
                    required.append(row)
            if not required:
                self.notes.append({'kind': 'manifest_schema_has_no_supported_member_rows', 'path': rel})
                continue
            # Validate declared denominators, not current descendant directory
            # size: older producer manifests intentionally exclude added packs.
            count_pairs = [('file_count', 'files'), ('file_count_excluding_manifest', 'files'),
                           ('file_count_excluding_this_manifest', 'files'), ('selected_count', 'selected'), ('selected_count', 'selection')]
            byte_pairs = [('total_bytes', 'files'), ('total_bytes_excluding_manifest', 'files'),
                          ('bytes_excluding_this_manifest', 'files'), ('selected_bytes', 'selected'), ('selected_bytes', 'selection')]
            for count_key, rows_key in count_pairs:
                if count_key in data and isinstance(data.get(rows_key), list) and data[count_key] != len(data[rows_key]):
                    self.error('manifest_declared_count_mismatch', path=rel, field=count_key)
            for byte_key, rows_key in byte_pairs:
                if byte_key in data and isinstance(data.get(rows_key), list) and data[byte_key] != sum(r['bytes'] for r in data[rows_key]):
                    self.error('manifest_declared_bytes_mismatch', path=rel, field=byte_key)
            checked, unseen_optional, seen = [], [], set()
            for required_row, rows in [(True, required), (False, optional)]:
                for row in rows:
                    name = row.get('path')
                    if name in seen:
                        continue
                    seen.add(name)
                    if not isinstance(name, str) or not safe_relative(name) or not HEX_SHA.fullmatch(row.get('sha256', '')) or not isinstance(row.get('bytes'), int):
                        self.error('invalid_manifest_member', manifest=rel, path=name)
                        continue
                    virtual = str((path.parent / name).relative_to(self.repo))
                    candidates = self.aliases.get(virtual, [])
                    matches = [r for r in candidates if (r['bytes'], r['sha256']) == (row['bytes'], row['sha256'])]
                    if not matches:
                        if not candidates and not required_row:
                            unseen_optional.append(name)
                        else:
                            self.error('manifest_member_missing_or_changed', manifest=rel, path=name, candidates=len(candidates), required=required_row)
                        continue
                    checked.append({'path': name, 'verified_via': matches[0]['origin']})
                    original = row.get('original')
                    if isinstance(original, dict) and name.endswith('.xz') and {'bytes', 'sha256'} <= original.keys():
                        originals = self.aliases.get(virtual[:-3], [])
                        if not any((r['bytes'], r['sha256']) == (original['bytes'], original['sha256']) for r in originals):
                            self.error('selected_original_identity_mismatch', manifest=rel, path=name)
            self.manifests.append({'manifest': rel, 'sha256': digest(path.read_bytes()), 'verified_members': len(checked),
                                   'verified_via_physical_file': sum('!' not in r['verified_via'] for r in checked),
                                   'verified_via_lossless_decoding': sum('!' in r['verified_via'] for r in checked),
                                   'unselected_original_rows_not_present': unseen_optional,
                                   'additional_descendant_files_not_claimed_by_this_manifest': 'Not treated as an error; no producer scope is expanded.'})

    def links_check(self):
        files = [self.repo / p for p in DOCS] + [self.report / 'README.md', self.report / 'RECOVERY.md']
        local, remote, pending, missing = [], 0, [], []
        for path in files:
            text = path.read_text()
            for raw in link_destinations(text):
                destination = html.unescape(re.sub(r'\\([() ])', r'\1', raw))
                parsed = urlsplit(destination)
                if parsed.scheme or parsed.netloc:
                    remote += 1
                    continue
                if not parsed.path:
                    continue
                relative = unquote(parsed.path)
                target = (self.repo / relative.lstrip('/') if relative.startswith('/') else path.parent / relative).resolve()
                try:
                    target_name = str(target.relative_to(self.repo))
                except ValueError:
                    self.error('local_link_escapes_repository', source=str(path.relative_to(self.repo)))
                    continue
                row = {'source': str(path.relative_to(self.repo)), 'target': target_name, 'fragment_present': bool(parsed.fragment)}
                local.append(row)
                if not target.exists():
                    if self.args.allow_pending_outer_manifest and target == self.report / 'files-manifest.json':
                        pending.append(row)
                    else:
                        missing.append(row)
        for row in missing:
            self.error('missing_local_link', **row)
        return {'primary_markdown_files': len(files), 'local_link_occurrences': len(local),
                'distinct_local_targets': len({r['target'] for r in local}), 'remote_links_not_fetched': remote,
                'missing_links': missing, 'allowed_pending_outer_manifest_links': pending,
                'local_target_existence_validated': True, 'heading_fragments_not_validated': True}

    def run(self):
        started = datetime.now(timezone.utc).isoformat()
        scope = self.scope()
        before = self.snapshot()
        for rel in sorted(before):
            raw = (self.repo / rel).read_bytes()
            self.physical[rel] = raw
            self.decode(raw, rel, rel)
        self.manifests_check()
        links = self.links_check()
        if self.sensitive:
            self.error('sensitive_or_temporary_reference_candidates', count=len(self.sensitive))
        after = self.snapshot()
        if before != after:
            self.error('publication_inputs_changed_during_read', changed=sorted(p for p in set(before) | set(after) if before.get(p) != after.get(p)))
        return {'schema': 2, 'started_at_utc': started, 'checked_at_utc': datetime.now(timezone.utc).isoformat(),
                'kind': 'Read-only documentation/publication scope, member identity, links and bounded recursive secret-pattern scan; no product tests.',
                'validator_sha256': digest(Path(__file__).read_bytes()), 'scope': scope,
                'physical_input_files': len(before), 'physical_input_bytes': sum(row['bytes'] for row in before.values()),
                'input_identity_map_sha256': digest(json_bytes(before)), 'inputs_stable_during_check': before == after,
                'manifest_checks': self.manifests, 'links': links,
                'recursive_content_scan': {'raw_or_decoded_units': self.raw_units, 'utf8_text_units': self.text_count,
                                           'expanded_bytes': self.decoded_bytes, 'zip_archives': self.archives,
                                           'sensitive_candidates': self.sensitive,
                                           'rules': ['PEM private-key headers, GitHub/AWS/OpenAI token signatures, unredacted Authorization headers.',
                                                     'Signed/token query URLs after JSON/string/HTML/percent decoding; URL user+password; temporary file references and nonempty file_uri.',
                                                     'Bounded XZ/ZIP recursive decoding and CRC validation. No archive extraction, helper import or ELF execution.'],
                                           'limitation': 'A bounded pattern scan does not prove absence of every conceivable secret or encoded credential.'},
                'pending_outer_files_manifest_allowed': self.args.allow_pending_outer_manifest,
                'notes': self.notes, 'blocking': self.errors, 'passed': not self.errors,
                'producer_manifests_or_report_not_modified_by_checks': True, 'new_product_executions': 0,
                'generation_note': 'This result may be generated into the report once before its outer files-manifest is frozen. Subsequent rechecks must write outside that frozen tree.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--base', default=BASE)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--allow-pending-outer-manifest', action='store_true')
    parser.add_argument('--replace-output', action='store_true')
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists() and not args.replace_output:
        parser.error('Output exists; choose a new path or explicitly use --replace-output.')
    report_root = args.repo.resolve() / PREFIX
    if output.is_relative_to(args.repo.resolve()) and output != report_root / 'publication-validation.json':
        parser.error('Only the requested publication-validation.json may be generated inside the repository.')
    if output == report_root / 'publication-validation.json' and (report_root / 'files-manifest.json').exists():
        parser.error('Outer manifest is already frozen; write the recheck outside the repository.')
    review = Review(args)
    result = review.run()
    output.parent.mkdir(parents=True, exist_ok=True)
    raw = json_bytes(result)
    temporary = output.with_name(output.name + '.pending')
    if temporary.exists():
        parser.error('Output temporary path exists; choose a new output path.')
    temporary.write_bytes(raw)
    temporary.replace(output)
    print(json.dumps({'output': str(output), 'bytes': len(raw), 'sha256': digest(raw), 'passed': result['passed'],
                      'blocking_count': len(result['blocking']), 'blocking': result['blocking'],
                      'physical_input_files': result['physical_input_files'], 'manifest_count': len(result['manifest_checks']),
                      'text_units': result['recursive_content_scan']['utf8_text_units'], 'local_links': result['links']['local_link_occurrences']}))
    raise SystemExit(0 if result['passed'] else 1)


if __name__ == '__main__':
    main()
