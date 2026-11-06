#!/usr/bin/env python3
"""Claim only the requested next original-ledger batch and emit its exact packet.

No remote call is made here. The coordinator must retain the returned durable
job identity before advancing; an unsettled claim stops all later claims.
"""
from pathlib import Path
import hashlib
import json
import subprocess
import sys

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[2]
PLAN_SHA = 'e26ff7e5c1739d2e30eab340df9072ab34a433362b9e8c869b905e25c1af18b3'
GATE_SHA = '0befe9f69aa46608a6cec8505c1fed41cd8fca1f9045693c43a83dbb4fa00d8e'


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    assert len(sys.argv) == 2
    number = int(sys.argv[1]); assert 7 <= number <= 13
    assert digest((HERE / 'linked_audit_gate.py').read_bytes()) == GATE_SHA
    plan_raw = (HERE / 'CONTINUATION_PLAN.json').read_bytes(); assert digest(plan_raw) == PLAN_SHA
    plan = json.loads(plan_raw)
    row = next(r for r in plan['batches'] if r['batch'] == number)
    packet_raw = (HERE / row['process_request']['file']).read_bytes()
    assert len(packet_raw) == row['process_request']['bytes'] and digest(packet_raw) == row['process_request']['sha256']
    folder = PROJECT / plan['original_state_dir'] / f'batch-{number:02}'
    assert not folder.exists(), 'Existing claim must be reconciled, never replaced.'
    result = subprocess.run([sys.executable, str(HERE / 'linked_audit_gate.py'), 'claim-next',
                             '--plan', str(HERE / 'CONTINUATION_PLAN.json'), '--plan-sha256', PLAN_SHA],
                            capture_output=True, check=False)
    # A rejected claim is preserved outside the ledger as well; it is never retried.
    for name, raw in [(f'root-claim-b{number:02}.stdout.original.json', result.stdout),
                      (f'root-claim-b{number:02}.stderr.original.txt', result.stderr)]:
        with (HERE / name).open('xb') as handle:
            handle.write(raw)
    decision = json.loads(result.stdout)
    assert result.returncode == 0 and not result.stderr, decision
    assert decision['state'] == 'CLAIMED_ONE_LINKED_ORIGINAL_BATCH_FOR_COORDINATOR'
    assert decision['next'] == row and Path(decision['intent_path']).parent == folder
    print(packet_raw.decode(), end='')


if __name__ == '__main__':
    main()
