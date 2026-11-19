"""Streaming recovery records and phase gates; no host action occurs on import."""
import hashlib
import json
import os
import pathlib
import sqlite3
import stat

GIB = 1024 ** 3
ROW_MAX = 65536


def require(ok, detail):
    if not ok:
        raise RuntimeError(detail)


def cpu_set(value):
    require(isinstance(value, str) and 0 < len(value) <= 4096, 'actual bounded CPU list')
    result = set()
    for part in value.replace(',', ' ').split():
        bounds = part.split('-')
        require(len(bounds) in (1, 2) and all(x.isdecimal() for x in bounds), 'CPU list syntax')
        low = int(bounds[0]); high = int(bounds[-1])
        require(0 <= low <= high < 4096, 'bounded CPU range')
        result.update(range(low, high + 1))
    require(result, 'nonempty effective CPU set')
    return result


def canonical_recovery_binding(contract, source_manifest_sha256):
    sha(source_manifest_sha256)
    require(set(contract['roles']) == {'audit', 'reuse', 'gap_export', 'gap_receive', 'verify'},
            'exact five canonical recovery phases')
    return {'schema': 'p4-production651-recovery-canonical-binding-v1',
            'source_manifest_sha256': source_manifest_sha256, 'nonce': contract['nonce'],
            'phases': contract['roles']}


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True) + '\n').encode()


def identity(value):
    return [value.st_dev, value.st_ino, value.st_mode, value.st_uid,
            value.st_gid, value.st_nlink, value.st_size, value.st_mtime_ns, value.st_ctime_ns]


def name(value):
    require(isinstance(value, str) and 0 < len(os.fsencode(value)) < 4096 and '\0' not in value,
            'bounded path data')
    path = pathlib.PurePosixPath(value)
    require(not path.is_absolute() and path.as_posix() == value and
            all(part not in ('', '.', '..') for part in value.split('/')), 'canonical relative path')
    return value


def sha(value):
    require(isinstance(value, str) and len(value) == 64 and
            all(c in '0123456789abcdef' for c in value), 'complete SHA256')
    return value


def mapped_source(contract, relative):
    relative = name(relative)
    matches = [row for row in contract['selected_roots']
               if relative == row['destination'] or relative.startswith(row['destination'] + '/')]
    require(len(matches) == 1, 'exactly one of the fixed selected roots')
    selected = matches[0]
    return selected['source'] + relative[len(selected['destination']):]


def validate_contract(contract, original):
    require(contract['schema'] == 'p4-production651-recovery-contract-v1' and
            contract['source_projects'] == original['source_projects'] == 651 and
            contract['source_lock_sha256'] == original['source_lock_sha256'] and
            contract['selected_roots'] == original['selected_roots'] and
            len(contract['selected_roots']) == 30 and
            contract['fixed_source_inputs'] == original['fixed_source_inputs'] and
            contract['original_locks'] == original['original_locks'], 'exact unchanged source epoch')
    require(set(contract['roles']) == {'audit', 'reuse', 'gap_export', 'gap_receive', 'verify'},
            'finite new recovery role whitelist')
    roots = [name(x['destination']) for x in contract['selected_roots']]
    for a in roots:
        require(sum(a == b or a.startswith(b + '/') for b in roots) == 1,
                'nonoverlapping selected roots')
    return contract


def validate_row(row, contract):
    require(isinstance(row, dict) and row.get('kind') == 'entry', 'source entry record')
    relative = name(row['name'])
    require(row['source_path'] == mapped_source(contract, relative), 'fixed original source path')
    value = row['identity']
    require(isinstance(value, list) and len(value) == 9 and all(type(x) is int for x in value),
            'complete original source F9')
    require(value[3:5] == [1000, 1000] and value[5] > 0 and value[0] > 0 and value[1] > 0,
            'original ordinary source owner and inode')
    require(type(row['bytes']) is int and 0 <= row['bytes'] <= contract['limits']['maximum_file_bytes'] and
            type(row['mode']) is int and row['mode'] == stat.S_IMODE(value[2]) and row['mode'] & 0o7000 == 0,
            'source size and ordinary permission bits')
    kind = row['type']
    allowed = {'kind', 'name', 'source_path', 'identity', 'type', 'mode', 'bytes'}
    if kind == 'file':
        require(stat.S_ISREG(value[2]) and row['bytes'] == value[6], 'regular source entry')
        sha(row['sha256']); allowed.add('sha256')
    elif kind == 'directory':
        require(stat.S_ISDIR(value[2]) and row['bytes'] == 0, 'directory source entry')
    elif kind == 'symlink':
        require(stat.S_ISLNK(value[2]) and row['bytes'] == 0 and
                isinstance(row['target'], str) and len(os.fsencode(row['target'])) < 4096 and
                '\0' not in row['target'], 'literal symlink data, never followed')
        allowed.add('target')
    else:
        raise RuntimeError('unsupported source node')
    require(set(row) == allowed, 'exact source record schema')
    return row


class Journal:
    """Create-only canonical NDJSON with bounded records and durable completion."""
    def __init__(self, path, limit):
        self.path = pathlib.Path(path)
        self.fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
        self.limit = limit; self.bytes = 0; self.count = 0; self.digest = hashlib.sha256()

    def add(self, row):
        data = encoded(row)
        require(len(data) <= ROW_MAX and self.bytes + len(data) <= self.limit, 'bounded complete journal')
        view = memoryview(data)
        while view:
            written = os.write(self.fd, view); require(written > 0, 'journal write'); view = view[written:]
        self.bytes += len(data); self.count += 1; self.digest.update(data)
        if self.count % 2048 == 0:
            os.fsync(self.fd)

    def close(self):
        if self.fd is not None:
            os.fsync(self.fd); os.close(self.fd); self.fd = None
            fd = os.open(self.path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
            try: os.fsync(fd)
            finally: os.close(fd)
        return {'path': str(self.path), 'bytes': self.bytes, 'sha256': self.digest.hexdigest(), 'records': self.count}

    def __enter__(self): return self
    def __exit__(self, *_): self.close()


def records(path, maximum, checkpoint=lambda: None, allow_incomplete_tail=False):
    """Read bounded lines. A preserved truncated old tail is never a valid row."""
    total = 0
    with open(path, 'rb', buffering=65536) as stream:
        while True:
            checkpoint(); raw = stream.readline(ROW_MAX + 1)
            if not raw:
                return
            total += len(raw)
            require(total <= maximum and len(raw) <= ROW_MAX, 'bounded NDJSON input')
            if not raw.endswith(b'\n'):
                require(allow_incomplete_tail and stream.read(1) == b'', 'complete NDJSON row')
                return
            value = json.loads(raw)
            require(encoded(value) == raw, 'canonical NDJSON bytes')
            yield value


class ManifestIndex:
    """Finite disk index, 8 MiB SQLite cache; never loads a whole manifest in RAM."""
    def __init__(self, path, contract, checkpoint=lambda: None):
        self.path = pathlib.Path(path); self.contract = contract; self.checkpoint = checkpoint
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
        os.close(fd)
        self.connection = sqlite3.connect(self.path)
        self.connection.execute('PRAGMA cache_size=-8192')
        self.connection.execute('PRAGMA temp_store=FILE')
        self.connection.execute('PRAGMA mmap_size=0')
        self.connection.execute('PRAGMA journal_mode=DELETE')
        self.connection.execute('PRAGMA synchronous=FULL')
        self.connection.execute('CREATE TABLE nodes (name TEXT PRIMARY KEY, ordinal INTEGER UNIQUE, source BLOB NOT NULL, observed BLOB) WITHOUT ROWID')
        self.count = 0; self.payload = 0

    def bounded(self):
        self.checkpoint()
        size = self.path.stat().st_size
        for suffix in ('-journal', '-wal', '-shm'):
            p = pathlib.Path(str(self.path) + suffix)
            if p.exists(): size += p.stat().st_size
        require(size <= self.contract['index_bytes_max'], 'bounded on-disk recovery index')

    def add(self, row):
        validate_row(row, self.contract)
        self.count += 1; self.payload += row['bytes']
        require(self.count <= self.contract['limits']['maximum_members'] and
                self.payload <= self.contract['limits']['maximum_payload_bytes'], 'bounded source closure')
        self.connection.execute('INSERT INTO nodes(name,ordinal,source) VALUES(?,?,?)',
                                (row['name'], self.count, encoded(row)))
        if self.count % 2048 == 0:
            self.connection.commit(); self.bounded()

    def load(self, manifest):
        for row in records(manifest, self.contract['limits']['maximum_manifest_bytes'], self.checkpoint):
            self.add(row)
        self.connection.commit(); self.bounded()
        require(all(self.get(row['destination']) is not None for row in self.contract['selected_roots']),
                'all 30 authenticated roots present')
        # Every nonsynthetic parent within a selected root must be an authenticated directory.
        for row in self.rows():
            if row['name'] in {x['destination'] for x in self.contract['selected_roots']}:
                continue
            parent = self.get(row['name'].rsplit('/', 1)[0])
            require(parent is not None and parent['type'] == 'directory', 'complete source parent membership')
        return {'members': self.count, 'payload_bytes': self.payload}

    def get(self, key):
        found = self.connection.execute('SELECT source FROM nodes WHERE name=?', (name(key),)).fetchone()
        return json.loads(found[0]) if found else None

    def rows(self):
        cursor = self.connection.execute('SELECT source FROM nodes ORDER BY ordinal')
        for (raw,) in cursor:
            self.checkpoint(); yield json.loads(raw)

    def observe(self, key, actual):
        count = self.connection.execute('UPDATE nodes SET observed=? WHERE name=? AND observed IS NULL',
                                        (encoded(actual), name(key))).rowcount
        require(count == 1, 'no unknown or duplicate destination member')

    def observations(self):
        cursor = self.connection.execute('SELECT source,observed FROM nodes ORDER BY ordinal')
        for original, actual in cursor:
            self.checkpoint(); yield json.loads(original), None if actual is None else json.loads(actual)

    def close(self):
        if self.connection is not None:
            self.connection.commit(); self.connection.close(); self.connection = None
            fd = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
            try: os.fsync(fd)
            finally: os.close(fd)

    def __enter__(self): return self
    def __exit__(self, *_): self.close()


def classify(source, observed):
    if observed is None:
        return 'missing'
    if observed['type'] != source['type']:
        return 'conflict'
    if source['type'] == 'file':
        if (observed['bytes'], observed['sha256']) != (source['bytes'], source['sha256']):
            return 'partial_file'
    elif source['type'] == 'symlink' and observed['target'] != source['target']:
        return 'conflict'
    if source['type'] != 'symlink' and (observed['mode'], observed['identity'][7]) != (source['mode'], source['identity'][7]):
        return 'metadata'
    if source['type'] == 'symlink' and observed['identity'][7] != source['identity'][7]:
        return 'metadata'
    return 'reuse'


def transfer_end(nonce, plan_sha, manifest_sha, members, payload, transcript_sha):
    return {'schema': 'p4-production651-gap-transfer-end-v1', 'nonce': nonce,
            'plan_sha256': sha(plan_sha), 'source_manifest_sha256': sha(manifest_sha),
            'transcript_sha256': sha(transcript_sha), 'members': members, 'payload_bytes': payload,
            'source_full_F9_recheck': True, 'source_writes': 0}


def commit_ack(end):
    require(end['schema'] == 'p4-production651-gap-transfer-end-v1' and
            end['source_full_F9_recheck'] is True and end['source_writes'] == 0,
            'sender authenticated completion before ACK')
    return {'schema': 'p4-production651-gap-fsynced-ack-v1', 'nonce': end['nonce'],
            'plan_sha256': end['plan_sha256'], 'source_manifest_sha256': end['source_manifest_sha256'],
            'transcript_sha256': end['transcript_sha256'], 'members': end['members'],
            'payload_bytes': end['payload_bytes'], 'per_file_fsync_complete': True,
            'gap_transfer_complete': True, 'full_source_readback_complete': False,
            'original_import_passed': False}


def accept_ack(end, actual):
    require(actual == commit_ack(end), 'exact new transfer ACK; never an old importer ACK')
    return True


def schedule(remaining_seconds_by_host, stage_work_and_stop_seconds, full_stages=2,
             storage_cleanup_seconds=1200):
    require(set(remaining_seconds_by_host) == {'desktop', 'pocket4'} and
            all(type(v) in (int, float) and v >= 0 for v in remaining_seconds_by_host.values()),
            'fresh host-local remaining durations, not cross-host monotonic timestamps')
    require(type(full_stages) is int and 0 <= full_stages <= 2 and
            all(type(v) is int and v >= 0 for v in stage_work_and_stop_seconds), 'finite stage schedule')
    remaining = min(remaining_seconds_by_host.values())
    needed = sum(stage_work_and_stop_seconds) + full_stages * 28800 + storage_cleanup_seconds
    return {'minimum_actual_remaining_seconds': remaining, 'required_upper_seconds': needed,
            'fits_original_storage': needed < remaining,
            'requires_normal_storage_retirement_offline_verification_new_owner': needed >= remaining,
            'hot_extension_permitted': False, 'new_allocation_permitted': False}
