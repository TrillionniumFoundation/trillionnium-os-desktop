# Camera r4: actual host decoder qualification

This package is one executable control runner and an externally pinned source
packet. It does not change production sources. It is prepared for a single
fresh, resource-limited root systemd service on Pocket4; no H request or device
operation was issued by its author.

## What a pass would qualify

All eight controls must execute, return their exact expected results, and pass
the final idle/resource checks. Missing prerequisites fail; there is no skip,
PID-namespace fallback, receipt reuse or automatic retry.

| Control | Actual boundary |
| --- | --- |
| Normal decoder and nonce | Unchanged `Decoder.run`, real fixed capture/lifecycle, actual ffprobe/full-frame/PCM commands and a freshly generated synthetic acoustic nonce |
| UID 1000 and two FDs | A fixed Python child directly reports its four UID/GID fields, empty supplementary groups, no-new-privileges, core limit, exactly two additional descriptors, inaccessible root input, immutable sealed bytes and a read-only view |
| Seal negatives | Real UID-1000 write/resize attempts must fail; bytes/size/seals/original file stay fixed; actual metadata drift must cause the original decoder's exact rejection without rebasing identity |
| Malformed MOV | Original decoder executes ffprobe, rejects the input, and proves retirement as a known failure |
| Timeout | Real sleeping child is killed and reaped by the original owned lifecycle |
| Output bound | A real writer exceeds the 1024-byte bound by one observed byte and is retired; no extra reads or success promotion |
| Descendant | A real escaped-session descendant is adopted and reaped; descendant cleanup must not turn the command into a success |
| UNKNOWN | After actual child/FD retirement and ECHILD, the runner changes only its own subreaper flag; original `finish()` really fails, Decoder latches UNKNOWN and refuses replay; separate finite local recovery does not rewrite the UNKNOWN receipt |

The UID/FD sample comes from the fixed Python child using the same Popen
credential/descriptor arguments. It is not falsely described as a sample from
inside each ffmpeg process. The three normal decodes use the unchanged
production class and capture source. Its inherited memfd is sealed and has an
`O_RDWR` file description; the child explicitly opens and checks an `O_RDONLY`
view. All four seals enforce byte/size immutability, and denied writes can still
change inode timestamps, which the control handles without weakening identity.

The temporary Session deliberately provides host-only scope/phase markers and
local source/file guards. It never creates a BusinessBaseline or Main. Synthetic
nonce correlation proves the host decoder component only. A pass cannot qualify
live Session admission, physical microphone/output, current CAMCORDER/HAL,
same-URI Android playback, recovery or whole-app business acceptance.

## Exact source packet

`source-packet.json` pins this runner, three production component files and the
unchanged fixed host dependencies. Production components are loaded from the
explicit reviewed `--source-dir`; their bytes must match:

- `camera_decode.py`: `7a42785a9d5d16fbc4644d0db961acd965b42f79dc9a75b2f101d88ab51574a4`
- `camera_video_media.py`: `58c5b6508fe23532fe4282c38446e75dfc25800ed6b063691da80bd431f74190`
- `camera_audio_challenge.py`: `30b8560cf4f43e77e051e4915492ed18fe3c78e8b2a67527f4e14c02643dcd4c`

Actual qualification requires the literal production paths for
`bounded_host_capture.py`, its transitive `capture_lifecycle.py`, and the current
host `business_commands.py`. Relocation overrides exist only for source
inspection and are refused in `qualify-host`. All sources and actual runner
tool files are checked again throughout the run. This does not freeze or
qualify the remaining 26 files of the combined Camera controller.

## Required outer execution boundary

The operator must create a new, otherwise empty unit and output directory. The
unit name and packet SHA are part of the concrete reviewed H request. Recover
that same durable H job after an uncertain response; never launch a second unit
or reuse output under a new key.

These outer properties are mandatory, not suggestions:

```text
CPUQuota=100%
CPUAffinity=2
MemoryMax=512M
MemorySwapMax=0
TasksMax=128
RuntimeMaxSec=90
TimeoutStopSec=10
KillMode=control-group
NoNewPrivileges=yes
UMask=0077
```

The runner independently verifies the actual self PID/single-thread `/proc`,
root UID, dedicated cgroup, CPU quota/affinity, memory/swap/tasks limits and
no-new-privileges. Before work and before its final receipt it reads the same
cgroup directory's real memory peak/events, swap current/events/available peak,
and PID events/available peak. Any max, OOM, OOM-kill, swap or PID-limit event
fails qualification. The final observed peak is retained before systemd can
collect the unit. These are bounded observations, not continuous sampling.

The operator must also verify and retain the unit's hard `RuntimeMaxSec`,
`TimeoutStopSec` and `KillMode`; the runner's 65-second checks alone are not a
substitute for the manager's hard deadline and group cleanup. Only the test
controller's kernel-proven children may be signalled by the capture lifecycle.
No system-wide process search, Main PID, shared lock or external process is
used. The supplied protected PID set consists only of PID 1 and the controller's
parent; it is not represented as a current Main baseline.

After substituting the reviewed isolated package/source paths and literal
packet SHA, the single H shell command can use this form:

```sh
sudo -n systemd-run --unit=p4-camera-r4-decoder-host-20261108-r1 \
  --collect --wait --pipe \
  -p CPUQuota=100% -p CPUAffinity=2 \
  -p MemoryMax=512M -p MemorySwapMax=0 -p TasksMax=128 \
  -p RuntimeMaxSec=90 -p TimeoutStopSec=10 -p KillMode=control-group \
  -p NoNewPrivileges=yes -p UMask=0077 \
  /usr/bin/python3 -I -B /ABSOLUTE/ISOLATED/CONTROLS/qualify_decoder_host.py qualify-host \
  --packet /ABSOLUTE/ISOLATED/CONTROLS/source-packet.json \
  --expect-packet-sha256 REVIEWED_LITERAL_PACKET_SHA256 \
  --source-dir /ABSOLUTE/ISOLATED/COMBINED_CAMERA/source \
  --output-root /home/alex/work/camera-r4-decoder-host-qualification-20261108-r1 \
  --expected-cgroup /system.slice/p4-camera-r4-decoder-host-20261108-r1.service
```

The controls normally need a few seconds; 12-second synthetic Session budgets,
short negative deadlines, the 65-second controller budget and the 90-second hard
unit cap are finite. No bound is extended after a failure. The output root is
create-only, root-private, and must have the required name prefix. Synthetic
clips are removed after owned descriptors close, including constructor/close
failure paths when their exact identity can be verified. A failed exact cleanup
is preserved as a failure, not silently counted as removed. PCM stays in memfd
or memory. Text receipts remain in this one new root for operator review.

## Current validation status

`local-inspection.json` records source inspection and four narrowly scoped
runner cleanup regressions. Those regressions use inert kernel state fixtures
and do not count toward the eight actual host controls. The local cloud
environment fails the exact self-PID `/proc` admission before child creation.
There is no fallback or claimed host qualification from that environment.

The package currently authorizes no execution by itself. The root agent reviews
and executes the concrete bounded H request. Retain the original systemd-run
exit/log, complete durable H terminal receipt and `qualification.json`. A result
is accepted only with eight successful controls, zero `not_run`, true final
idle/resource gates and the independently verified outer unit constraints.
`runtime_qualified` and `whole_app_business_accepted` remain false in every
result, including a successful host qualification.
