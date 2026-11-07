#!/usr/bin/python3 -I
"""Fail closed before using the inherited Droidloom platform compatibility patch."""
import hashlib, os
from pathlib import Path
config=Path('<CONFIG_PREFIX>'+os.uname().release)
if not config.is_file() or 'CONFIG_VMAP_STACK=y' not in config.read_text().splitlines():
    raise SystemExit('Digitalis trial blocked: running kernel VMAP_STACK configuration is unverified')
library=Path('<COMPAT_LIBRARY_PATH>')
expected='a2b1445b68a9bff4ab23687c66668579b57fbc5122df055d212a51a60049a64c'
if hashlib.sha256(library.read_bytes()).hexdigest()!=expected:
    raise SystemExit('Digitalis trial blocked: platform compatibility library changed')
print('Kernel VMAP_STACK and recorded trial library verified')
