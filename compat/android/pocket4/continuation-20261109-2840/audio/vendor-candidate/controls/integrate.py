from pathlib import Path
import hashlib
import json
import subprocess

ROOT = Path('/data/pocket4-audio-qpr1-vendor-candidate-20261109-2840-r1')
SOURCE = ROOT / 'source'
PARENT = '4caa694f25b3da022651a1078600a0eb1a5334fc'
assert subprocess.check_output(['/usr/bin/git', '-C', str(SOURCE), 'rev-parse', 'HEAD']).decode().strip() == PARENT

def replace(path, before, after):
    text = path.read_text()
    assert text.count(before) == 1, (str(path), text.count(before))
    path.write_text(text.replace(before, after))

main = SOURCE / 'tools/droidloom-update/src/main.rs'
replace(main, 'mod assemble;\n', 'mod assemble;\nmod audio_vendor_candidate;\nmod audio_vendor_zip;\n')
replace(main, '    /// Restore an interrupted source projection under the normal two workspace locks.\n', '''    /// Stage one unqualified vendor Audio APEX from a frozen successful full-build terminal.
    /// Does not assemble system partitions, install artifacts, or start services.
    AudioApexStageCandidate {
        #[arg(long)]
        terminal: PathBuf,
        #[arg(long)]
        terminal_sha256: String,
        #[arg(long)]
        destination: PathBuf,
    },
    /// Restore an interrupted source projection under the normal two workspace locks.
''')
replace(main, '    match &args.command {\n        Some(Action::RecoverSource { work }) => {\n', '''    match &args.command {
        Some(Action::AudioApexStageCandidate {
            terminal,
            terminal_sha256,
            destination,
        }) => {
            if args.source.is_some() || args.clean || args.build_only || args.bootstrapped || args.jobs.is_some() {
                return fail("audio-apex-stage-candidate does not accept source, build, bootstrap or cleanup options");
            }
            let report = audio_vendor_candidate::stage(terminal, terminal_sha256, destination)?;
            println!("{}", serde_json::to_string_pretty(&report)?);
            return Ok(());
        }
        Some(Action::RecoverSource { work }) => {
''')
replace(SOURCE / 'tools/droidloom-update/Cargo.toml', 'hex.workspace = true\n', 'hex.workspace = true\nflate2.workspace = true\n')
lock = SOURCE / 'Cargo.lock'
text = lock.read_text()
start = text.index('name = "droidloom-update"\n')
end = text.index('\n[[package]]', start)
before = text[start:end]
assert before.count(' "hex",\n') == 1 and ' "flate2",\n' not in before
replace(lock, before, before.replace(' "hex",\n', ' "flate2",\n "hex",\n'))

readme = SOURCE / 'tools/droidloom-update/README.md'
with readme.open('a') as output:
    output.write('''
## Stage a vendor Audio APEX candidate

The scoped staging command consumes a SHA256-pinned successful normal Audio
full-build terminal. It copies only the exact complete
`com.android.hardware.audio.droidloom.apex` under
`payload/vendor/apex/` in a new caller-owned staging directory. It emits
`CANDIDATE.json` with state `UNQUALIFIED_VENDOR_AUDIO_CANDIDATE`; it never
calls the system image assembler or updates a running installation.

```console
droidloom-update audio-apex-stage-candidate \\
  --terminal /absolute/full-build/RESULT.json \\
  --terminal-sha256 <exact-terminal-sha256> \\
  --destination /absolute/trusted-parent/new-candidate
```

The destination parent must be a real caller-owned directory without group or
other write access. Every ancestor is opened without following symlinks;
retained directory descriptors anchor exclusive creation and are checked again
before and after publication. An existing destination is never reused. Failed
staging can leave a partial private directory without a successful receipt;
inspect that attempt before choosing another new destination.

Inputs require the complete 430-project normal full-build terminal, exact
success and retirement fields, the recorded normal command, and the output
artifact's original path, file identity, byte length and SHA256. Source-only
reconcile receipts cannot stand in for a full build. The file is copied and
read back through the same held descriptor. The terminal's recorded input
references remain attached to the candidate; this command does not contact the
durable job service to independently authenticate its terminal.

ZIP metadata inspection is bounded: a container is at most 256 MiB with 4–256
members and a central directory at most 256 KiB; only stored and DEFLATE entries
are accepted. Required metadata is at most 64 KiB per member. Duplicate or
noncanonical names, inconsistent headers, overlapping members, incomplete or
oversized DEFLATE streams and an unexpected package identity reject staging.
The APEX payload must be stored, and compressed APEX containers are out of scope.
The existing workspace `flate2` dependency and lock are reused.

The declared target is the selected official QPR1 CP3A.260905.010 / 16176746
system image. It is not copied or reverified by this command. No CP2A
`system`, `system_ext`, `product`, ART, bionic, framework or Connectivity
overrides are projected. A successful candidate does **not** qualify APEX
container signing, payload AVB, the payload filesystem, compiled ELF imports,
linker namespaces, VINTF matching, Audio HAL behavior, runtime audio or
production readiness. All qualification and readiness fields remain false,
even when a supplied terminal claims otherwise. These gates must run against
the actual full artifact and the selected official base before activation.

Focused staging controls can be run without Android compilation:

```console
cargo test --locked -j2 -p droidloom-update audio_vendor -- --test-threads=2
```
''')
subprocess.run(['/usr/bin/git', '-C', str(SOURCE), 'diff', '--check'], check=True)
print(json.dumps({'state': 'RUST_CANDIDATE_INTEGRATED_NOT_YET_COMPILED', 'parent': PARENT,
                  'files': subprocess.check_output(['/usr/bin/git', '-C', str(SOURCE), 'status', '--porcelain']).decode()}))
