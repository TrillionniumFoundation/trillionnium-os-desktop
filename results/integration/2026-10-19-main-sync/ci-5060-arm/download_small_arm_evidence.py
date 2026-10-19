#!/usr/bin/env python3
"""Download only the requested small CI evidence ZIP; never an ELF bundle."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import os
import sys
import urllib.request
import zipfile


def main():
    config = json.loads(Path(sys.argv[1]).read_text())
    artifact = config['artifact']
    expected_head = '5060ac6976b56b32647c728991e489cdee1cce9d'
    if (artifact['name'] != 'hepta-original-agentd-evidence-39182491155-1'
            or artifact['workflow_run']['head_sha'] != expected_head
            or not 0 < artifact['size_in_bytes'] < 8 * 1024 * 1024):
        raise SystemExit('Refusing an artifact outside the exact small R9 evidence scope')
    url = config['download_url']
    if not url.startswith('https://'):
        raise SystemExit('HTTPS download required')
    root = Path(__file__).resolve().parent
    path = root / 'arm-evidence.zip'
    os.umask(0o077)
    digest = hashlib.sha256()
    received = 0
    with urllib.request.urlopen(url, timeout=30) as response, path.open('xb') as output:
        while chunk := response.read(1024 * 1024):
            received += len(chunk)
            if received > artifact['size_in_bytes']:
                raise SystemExit('Download exceeds the GitHub artifact size')
            output.write(chunk)
            digest.update(chunk)
    if (received != artifact['size_in_bytes']
            or 'sha256:' + digest.hexdigest() != artifact['digest']):
        raise SystemExit('Downloaded evidence size or SHA differs from GitHub metadata')
    with zipfile.ZipFile(path) as archive:
        if archive.testzip() is not None:
            raise SystemExit('ZIP member CRC failed')
        files = [{'path': x.filename, 'bytes': x.file_size,
                  'compressed_bytes': x.compress_size, 'crc32': format(x.CRC, '08x')}
                 for x in archive.infolist()]
        if len({x['path'] for x in files}) != len(files):
            raise SystemExit('Duplicate evidence ZIP member names')
    receipt = {
        'recorded_at_utc': datetime.now(timezone.utc).isoformat(),
        'artifact_id': artifact['id'], 'expected_head': expected_head,
        'bytes': received, 'sha256': digest.hexdigest(),
        'github_digest_matches': True, 'zip_crc_verified': True,
        'members': len(files), 'uncompressed_total_bytes': sum(x['bytes'] for x in files),
        'large_elf_archives_downloaded': False, 'files': files,
        'note': 'Only the exact small logs/locks/reports/source-identity artifact was downloaded. Signed temporary URLs are not retained in the public receipt.',
    }
    out = root / 'arm-download-verification.json'
    out.write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps({k: v for k, v in receipt.items() if k not in ('files', 'note')}))


if __name__ == '__main__':
    main()
