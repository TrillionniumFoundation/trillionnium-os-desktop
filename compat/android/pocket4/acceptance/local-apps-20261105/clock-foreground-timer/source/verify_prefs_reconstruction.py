#!/usr/bin/python3 -I
"""Recompute the exact historical preference hash from the captured post XML.

This is local, read-only verification. It never opens an Android file or changes
the real counter; no retained historical XML is claimed.
"""
from pathlib import Path
import hashlib, json, re

HERE = Path(__file__).resolve().parent
raw = (HERE/'preferences-after-private.xml').read_bytes()
assert len(raw) == 231
assert hashlib.sha256(raw).hexdigest() == '2eb569d90fed2625825354851e9597905e191b5670e837a980a2b9d25e6c1745'
pattern = rb'(<int name="intent\.extra\.alarm\.global\.id" value=")([0-9]+)(" />)'
matches = list(re.finditer(pattern,raw)); assert len(matches) == 1
match = matches[0]; value = int(match[2]); assert value == 120
preimage = raw[:match.start(2)] + b'119' + raw[match.end(2):]
assert hashlib.sha256(preimage).hexdigest() == 'dba5288e001fa6d4e9705f3032b0024f3486688a6829e971cb9781c90e3c1e35'
assert (HERE/'preferences-preimage-reconstructed-private.xml').read_bytes() == preimage
print(json.dumps({'captured_post_sha256':hashlib.sha256(raw).hexdigest(),
    'reconstructed_preimage_sha256':hashlib.sha256(preimage).hexdigest(),
    'matches_previously_captured_preinstall_hash':True,
    'only_byte_change':'intent.extra.alarm.global.id: 119 -> 120',
    'device_reads':0,'device_writes':0,'original_install_outcome_rewritten':False}))
