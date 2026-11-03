#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Run timestamp permission controls on Linux in an isolated, networkless container."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--image', default='ubuntu:24.04', help='already installed image; never pulled')
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    source = Path(__file__).with_name('utimens_probe.c')
    binary = out / 'probe.elf'
    compile_argv = ['cc', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-static', str(source), '-o', str(binary)]
    cp = subprocess.run(compile_argv, capture_output=True, timeout=90)
    (out / 'compile.log').write_bytes(cp.stdout + cp.stderr)
    if cp.returncode:
        raise RuntimeError('probe compilation failed')
    image = json.loads(subprocess.check_output(['docker', 'image', 'inspect', args.image], text=True))[0]
    argv = ['docker', 'run', '--rm', '--network', 'none', '--read-only', '--pids-limit', '32',
            '--tmpfs', '/case:rw,nosuid,nodev,mode=1777,size=16m', '--mount',
            'type=bind,src=' + str(binary) + ',dst=/probe,readonly', image['Id'],
            '/probe', '--linux-reference', '/case']
    cp = subprocess.run(argv, capture_output=True, timeout=60)
    raw = (cp.stdout + cp.stderr).decode(errors='replace')
    (out / 'probe.log').write_text(raw)
    cases = re.findall(r'^UT_CASE name=(\S+) pass=([01]) actual=(-?\d+) errno=(\d+) unchanged=([01]) omit=([01])$', raw, re.M)
    passed = (cp.returncode == 0 and len(cases) == 38 and len({c[0] for c in cases}) == 38
              and all(c[1] == '1' for c in cases) and raw.count('UT_COMPLETE cases=38 failures=0\n') == 1)
    report = dict(passed=passed, exit_code=cp.returncode, cases=cases, compile_argv=compile_argv,
                  command=argv, image_id=image['Id'], image_digests=image.get('RepoDigests', []),
                  kernel=subprocess.check_output(['uname', '-a'], text=True).strip(),
                  source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                  probe_sha256=hashlib.sha256(binary.read_bytes()).hexdigest())
    (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(passed=passed, cases=len(cases), exit_code=cp.returncode)))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
