#!/usr/bin/env python3
"""Read-only verification of Root's immutable CP14 payload/batches."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path('/workspace/scratch/94990735b266/root-recovery-20261104-02/checkpoint14-publication')
BATCH_PIN = (3809, 'ff2ba2156ca67748b1423e29da7153e954e3c8896fa6f51d86c62a64e8fb4717')
INDEX_PIN = (496723, '5f233370555e150065bad0273906ea20be17a3fbac6d653a39e0682c6db2d9d7')
BASE = '264b856843a4afd7237022ae93dd461c42e2bc7f'

def check(condition, message):
    if not condition:
        raise ValueError(message)

def read_pinned(path, size, digest):
    data = path.read_bytes()
    check(len(data) == size and hashlib.sha256(data).hexdigest() == digest, 'file pin mismatch: ' + str(path))
    return data

def object_sha(kind, data):
    return hashlib.sha1(kind.encode() + b' ' + str(len(data)).encode() + b'\0' + data).hexdigest()

def git_tree(leaves):
    root = {}
    for path, row in leaves.items():
        parts = path.split('/')
        check(all(p and p not in ('.', '..') for p in parts), 'bad path')
        current = root
        for part in parts[:-1]:
            current = current.setdefault(part, {})
            check(isinstance(current, dict), 'tree/blob conflict')
        check(parts[-1] not in current, 'duplicate path')
        current[parts[-1]] = (row['mode'], row['git_blob_sha1'])
    def finish(node):
        entries = []
        for name, value in node.items():
            encoded = name.encode('utf-8')
            if isinstance(value, dict):
                entries.append((encoded + b'/', b'40000 ' + encoded + b'\0' + bytes.fromhex(finish(value))))
            else:
                entries.append((encoded, value[0].encode() + b' ' + encoded + b'\0' + bytes.fromhex(value[1])))
        return object_sha('tree', b''.join(v for _, v in sorted(entries)))
    return finish(root)

def verify(batch_index=None):
    batches = json.loads(read_pinned(ROOT / 'git-batches.json', *BATCH_PIN))
    index = json.loads(read_pinned(ROOT / 'payload-base-index.json', *INDEX_PIN))
    check(index['count'] == len(index['files']) == 756, 'wrong payload count')
    rows = {r['path']: r for r in index['files']}
    check(len(rows) == 756, 'duplicate index path')
    check(sum(r['bytes'] for r in rows.values()) == index['bytes'], 'wrong total bytes')
    seen = {}
    states = []
    selected = None
    for expected_i, batch in enumerate(batches):
        check(batch['index'] == expected_i, 'batch order mismatch')
        entries = json.loads(read_pinned(Path(batch['path']), batch['bytes'], batch['sha256']))
        check(len(entries) == batch['entries'], 'wrong batch entry count')
        before = git_tree(seen)
        for entry in entries:
            path = entry['path']
            check(path in rows and path not in seen, 'unknown or duplicate payload path')
            row = rows[path]
            check(entry['mode'] == row['mode'] == '100644' and entry['type'] == 'blob', 'mode/type mismatch')
            raw = read_pinned(Path(row['local_path']), row['bytes'], row['sha256'])
            raw.decode('utf-8', 'strict')
            check(b'\0' not in raw, 'NUL in text payload')
            check(object_sha('blob', raw) == row['git_blob_sha1'], 'blob hash mismatch')
            if 'content' in entry:
                check('sha' not in entry and entry['content'].encode('utf-8') == raw, 'inline content mismatch')
            else:
                check(entry['sha'] == row['git_blob_sha1'], 'referenced blob mismatch')
            seen[path] = row
        after = git_tree(seen)
        states.append({'index': expected_i, 'entries': len(entries), 'cumulative_count': len(seen), 'batch_sha256': batch['sha256'], 'previous_tree': before, 'tree': after})
        if batch_index == expected_i:
            selected = entries
        if expected_i == 2:
            check(len(seen) == 569 and after == BASE, 'Root base tree mismatch')
    check(len(seen) == 756 and set(seen) == set(rows), 'incomplete coverage')
    result = {'schema': 1, 'source_index_sha256': INDEX_PIN[1], 'batch_index_sha256': BATCH_PIN[1], 'files': len(seen), 'bytes': index['bytes'], 'all_local_utf8_and_sha_and_git_blob_verified': True, 'base_tree': BASE, 'final_tree': states[-1]['tree'], 'states': states}
    if batch_index is not None:
        check(3 <= batch_index <= 12 and selected is not None, 'invalid pending batch')
        result['selected_index'] = batch_index
        result['tree_elements'] = selected
    return result

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--batch', type=int)
    args = parser.parse_args()
    print(json.dumps(verify(args.batch), ensure_ascii=False))
