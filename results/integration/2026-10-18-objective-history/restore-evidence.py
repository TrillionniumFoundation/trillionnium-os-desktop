#!/usr/bin/env python3
"""Reconstruct the exact R9 tar.xz from repository parts, checking every hash."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    here = Path(__file__).resolve().parent
    manifest = json.loads((here / 'archive-parts.json').read_text())
    output = args.output.absolute()
    if output.exists() or output.is_symlink():
        raise SystemExit('output already exists; choose a new path')
    output.parent.mkdir(parents=True, exist_ok=True)
    whole = hashlib.sha256()
    total = 0
    with tempfile.TemporaryDirectory(prefix='r9-restore-', dir=output.parent) as temp:
        staging = Path(temp) / 'archive'
        with staging.open('xb') as target:
            for record in manifest['parts']:
                relative = Path(record['path'])
                if relative.is_absolute() or '..' in relative.parts:
                    raise SystemExit('invalid part path')
                path = here / relative
                if path.is_symlink() or not path.is_file():
                    raise SystemExit('part is not a regular file: ' + str(relative))
                raw = path.read_bytes()
                if len(raw) != record['bytes'] or hashlib.sha256(raw).hexdigest() != record['sha256']:
                    raise SystemExit('part identity mismatch: ' + str(relative))
                target.write(raw)
                whole.update(raw)
                total += len(raw)
        archive = manifest['archive']
        if total != archive['bytes'] or whole.hexdigest() != archive['sha256']:
            raise SystemExit('combined archive identity mismatch')
        # Same-directory staging makes this an atomic, exclusive publication.
        # A concurrently created output is never overwritten.
        os.link(staging, output)
    print(json.dumps({'output': str(output), 'bytes': total, 'sha256': whole.hexdigest(),
                      'parts': len(manifest['parts']), 'status': 'reconstructed_and_verified'}))


if __name__ == '__main__':
    main()
