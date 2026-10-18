#!/usr/bin/env python3
"""Seed a new private UI target from unchanged, known task dependency files."""
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import tempfile

base = Path('/workspace/scratch/98f315e377b2')
old = base / 'r2-host-target/debug'
root = Path(tempfile.mkdtemp(prefix='trill-ui-r5-', dir='/dev/shm'))
target = root / 'target/debug'
target.mkdir(parents=True, mode=0o700)
record = {'started_at_utc': datetime.now(timezone.utc).isoformat(),
          'root': str(root), 'target': str(root / 'target'),
          'purpose': 'isolated native UI owner/IME build for current desktop task',
          'source_cache': str(old), 'source_cache_mutated': False,
          'files_copied': 0, 'bytes_copied': 0,
          'minimum_free_bytes': 100 * 1024 * 1024}
(root / 'ownership.json').write_text(json.dumps(record, indent=2) + '\n')
try:
    files = []
    for folder in ['.fingerprint', 'build']:
        files.extend(p for p in (old / folder).rglob('*') if p.is_file())
    files.extend(p for p in (old / 'deps').iterdir()
                 if p.is_file() and p.suffix in {'.rlib', '.rmeta', '.so', '.d', '.o'})
    for source in files:
        if source.is_symlink():
            raise RuntimeError('unexpected dependency cache symlink: ' + str(source))
        size = source.stat().st_size
        if shutil.disk_usage(root).free - size < record['minimum_free_bytes']:
            raise RuntimeError('temporary UI target reserve reached')
        destination = target / source.relative_to(old)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        record['files_copied'] += 1
        record['bytes_copied'] += size
    record['status'] = 'seeded_dependency_cache_only'
except Exception as error:
    record['status'] = 'failed'
    record['error'] = {'type': type(error).__name__, 'detail': str(error)}
    raise
finally:
    record['ended_at_utc'] = datetime.now(timezone.utc).isoformat()
    record['free_bytes_after'] = shutil.disk_usage(root).free
    (root / 'ownership.json').write_text(json.dumps(record, indent=2) + '\n')
    out = base / 'next-tools/ui-r5-target.json'
    with out.open('x') as stream:
        json.dump(record, stream, indent=2)
        stream.write('\n')
    print(json.dumps(record), flush=True)
