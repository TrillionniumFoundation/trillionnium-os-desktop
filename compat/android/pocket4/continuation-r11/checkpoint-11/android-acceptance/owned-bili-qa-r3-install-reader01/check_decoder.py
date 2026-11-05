"""Only owned synthetic bytes through the actual fixed reader decoder."""
import base64
import gzip
import json
from pathlib import Path
import types

HERE = Path(__file__).resolve().parent


def main():
    reader = types.ModuleType('actual_state_reader')
    reader.__file__ = str(HERE/'read_install.py')
    exec(compile((HERE/'read_install.py').read_bytes(),reader.__file__,'exec'),reader.__dict__)
    raw = b'{"owned":true}'
    compressed = gzip.compress(raw,mtime=0)
    assert reader.decode_state_wire(base64.b64encode(compressed)) == raw
    assert reader.decode_state_wire(base64.b64encode(gzip.compress(b'x'*65536,mtime=0))) == b'x'*65536
    rejected = []
    bad_crc = bytearray(compressed)
    bad_crc[-8] ^= 1
    cases = {'over_decompressed_bound':gzip.compress(b'x'*65537,mtime=0),
             'bad_crc':bytes(bad_crc),'incomplete':compressed[:-1],
             'second_member':compressed+compressed,'trailing_bytes':compressed+b'junk'}
    for name,value in cases.items():
        try:
            reader.decode_state_wire(base64.b64encode(value))
        except (RuntimeError,reader.zlib.error):
            rejected.append(name)
        else:
            raise AssertionError('invalid state gzip accepted: '+name)
    print(json.dumps({'schema':1,'state':'ACTUAL_DECODER_SYNTHETIC_CONTROLS_PASS',
        'valid_cases':2,'rejected':rejected,'collect_called':False,
        'remote_or_Android_calls':0,'fixture_contains_commercial_data':False},indent=2,sort_keys=True))


if __name__ == '__main__':
    main()
