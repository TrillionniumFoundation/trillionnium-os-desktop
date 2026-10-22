# Original Agentd: ordinary-kernel config-boundary evidence

This directory retains the actual 2026-10-22 isolated QEMU execution of the original frozen Hepta Agentd ELF and an independent local replay of the same oracle. The outcome is **loader → Rust main → exact missing `HEPTA_FLEET_ROOT` rejection**, with child exit 1 and actual QEMU exit 33. It does not qualify a running daemon, production authority, G2, or F completion.

## Evidence files

| File | Origin and scope |
| --- | --- |
| `agentd-abi-result.json` | Unmodified actual remote execution receipt, including source/binary/kernel identities, observed child result and false completion flags |
| `agentd-abi-invocation.json` | Unmodified actual QEMU, compiler and formatter arguments, empty child environment and payload identity |
| `agentd-abi-runtime-inputs.json` | Unmodified original ELF headers and resolved dynamic-library closure with hashes |
| `agentd-abi-serial.log.gz` | Complete raw serial compressed without omitting warnings or errors |
| `independent-replay.json` | Locally recomputed gzip/raw hashes, exact-oracle replay, decoded child output and explicit warning/error observations |
| `host-tests.log`, `host-tests-tool-result.json` | Actual local repository-relocation validation: all 11 control tests passed, no skips; no guest execution |
| `host-workflow-local-validation.json` | Actual execution of the new workflow's shell blocks in a separate clean local Git fixture: 11 tests, strict static compilation and unchanged-checkout checks; no GitHub checkout action or native run |
| `host-identity-controls.json` | Post-review checks for the updated workflow identity blocks: valid empty README passes; failed Git status, missing/nonempty README and symlink README all fail as required |

The original workflow validation keeps its original workflow SHA256. Review
subsequently hardened the two identity blocks so a failed `git status` cannot
be mistaken for a clean checkout, and each README condition is independently
checked. `host-identity-controls.json` binds the updated workflow SHA256
`a6d2aae5356742ee72c2ba2679d28b15c9ca8a8cbafc54af4bb97cf8cf5da998`:
five temporary-Git cases across both blocks produced all ten expected outcomes.
The 11-test suite and static compiler block did not change. This extra local
control verification is not a GitHub CI run or a second native execution.

The original binary, payload disk and original frozen manifest are retained by the execution producer. Their exact identities are in the actual receipt; those large/private inputs are not replicated in this directory. The local replay verifies the raw serial and copied receipt relationships. It does not independently rehash an absent payload or binary, or constitute a second native run.

## Identities

- Agentd build and published head: `6d6097da843f5831dfaf9cee3530da512d072a15`; tree `f722fbe5f24275c324089be720559a40901105f3`.
- Agentd ELF: 484,463,504 bytes; SHA256 `228d2e07583d0d27cf5750a6ba169254380fb4d49f1fdc21adcc04001fc3252f`.
- Frozen input manifest SHA256: `999e632d8e82cc71b58436a5c0a63b50312cf83ccfcfdb35b28b947b0eb12728`.
- Ordinary OS head: `85d394f99c73ad3194d57c876712ac01b59d90ca`; tree `7389c0a3f982983087953f75de7042fc058be088`; kernel ELF SHA256 `8170402aaa7408eb2c4ab1ade2cd1d9641ef03ccbd37631aaec775528df2ede7`.
- Executed runner SHA256: `0994e2452596ca8a4c3b59f6a6234d070c4ba5cb2edde4232271a7eefb1f535c`.
- Complete compressed serial: 253,084 bytes; SHA256 `e1b7987c58185142480184e9947b502618c58984832d77d3be186ccc9c78f585`.
- Complete uncompressed serial: 7,287,706 bytes, 21,537 lines; SHA256 `0567b1b7a03ca4d9f5c09d5113970bb3512fc976457d68e492cab2c7463dcd74`.

## Observed limitations

The exact child result passed, but shutdown emitted **three write I/O error diagnostics**: one failed block Write and two failed writeback messages after `SYS_SYNC`, before `SYS_REBOOT`. They occur on raw lines 21,534–21,536. The read-only payload's digest remained unchanged according to the actual execution receipt. Correct read-only filesystem semantics and error-free I/O are **not qualified** by this pass. The current ext2 read/atime and sync behavior, together with absent virtio RO negotiation, require a separate kernel repair and regression gate.

The raw serial also contains **25 unimplemented syscall 334 warnings** (`rseq` on x86_64). This startup continued successfully through its fallback. This does not qualify `rseq` support.

Most serial volume comes from repeated virtio/block read diagnostics while loading the large dev-profile original ELF. The complete log is retained rather than replacing it with the five acceptance markers.

## Reproduce the independent replay

From repository root:

```sh
python3 -I -B - <<'PY'
from pathlib import Path
import gzip, hashlib, importlib.util, json
base = Path('results/integration/2026-10-22-agentd-ordinary-abi')
path = Path('tests/workloads/hepta_agentd_abi/run_agentd_abi.py')
spec = importlib.util.spec_from_file_location('agentd_abi_replay', path)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
result = json.loads((base / 'agentd-abi-result.json').read_text())
raw = gzip.decompress((base / 'agentd-abi-serial.log.gz').read_bytes())
if hashlib.sha256(path.read_bytes()).hexdigest() != result['runner_sha256']:
    raise SystemExit('executed runner differs')
if hashlib.sha256(raw).hexdigest() != result['serial_sha256']:
    raise SystemExit('raw serial differs')
if not runner.oracle(raw, result['qemu_exit'], result['timed_out'], result['nonce']):
    raise SystemExit('raw oracle failed')
print('raw replay passed; scope=loader/main/config refusal; daemon=false; F=false')
PY
```

The [runner documentation](../../../tests/workloads/hepta_agentd_abi/README.md) describes the disabled-default native invocation and the separate original FleetRegistry/Supervisor stage required next.
