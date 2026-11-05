#!/usr/bin/env python3
# The external prepared digest is filled only after the unique preparation succeeds.
import hashlib, os, stat, sys
PREPARED_SHA256 = '__ACTUAL_PREPARED_SHA256__'
SOURCE = '/opt/p4-owner07-normal-20261105-01/source/coordinator.py'
SOURCE_SHA256 = 'c45cda4ed2adbc9bd5a91ca428b2bd8806e5cf6473633bfda9e6df414ce1a39a'
SOURCE_BYTES = 14396
if len(PREPARED_SHA256) != 64 or any(c not in '0123456789abcdef' for c in PREPARED_SHA256):
    raise RuntimeError('actual external prepared SHA-256 is required')
fd = os.open(SOURCE, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
try:
    st = os.fstat(fd); body = os.read(fd, SOURCE_BYTES + 1)
    if not stat.S_ISREG(st.st_mode) or st.st_uid != 0 or st.st_nlink != 1 or st.st_mode & 0o6022 or len(body) != SOURCE_BYTES or hashlib.sha256(body).hexdigest() != SOURCE_SHA256:
        raise RuntimeError('sealed actual NORMAL coordinator differs')
finally:
    os.close(fd)
sys.argv = [SOURCE, '--prepared', '/opt/p4-owner07-normal-20261105-01-state/prepared.json', '--prepared-sha256', PREPARED_SHA256]
exec(compile(body, SOURCE, 'exec'), {'__name__':'__main__','__file__':SOURCE})
