# Existing acoustic supervisor controls

These two files are exact copies of the qualified controller and worker. The
original seven cases were rerun against the current complete 29-module source
set in job `1a1bb474558-13c47-1a3`. The pre-fix source used by the negative
regression cases is retained only as `../fixtures/supervisor-before-fix.py`,
SHA `afecd93caa3c3d5c47f77ad6e4e1e286ce8631014fc457409df7feaa7388f875`.
It is never in the runtime source packet.

For a repeat, create fresh input metadata with schema
`pocket4-camera-video-supervisor-host-input-v1`. `packet` names the current
`source` directory. `controller`, `worker`, `old_supervisor`, and `source_map`
are exact `{path,bytes,sha256}` references. `sources` lists all 29 exact source
references. The source map maps each source basename to `{bytes,sha256}`.
The case list, in order, is:

1. `queued-go-old`
2. `queued-go-new`
3. `adoptee-old`
4. `adoptee-new`
5. `three-leader-channel`
6. `pipe-register-failure`
7. `missing-worker-terminal`

The controller takes `--inputs`, `--expect-inputs-sha256`, and a fresh `--output`
whose parent is the input file's parent. It requires its own H job cgroup:
512 MiB, 50% CPU quota, zero swap, 64 PIDs, CPU 19, nice 10. Its original pinned
`business_commands.py` and `capture_lifecycle.py` remain the host dependencies.
Main/plan qualification, the acoustic protocol backend and PCM correlation are
explicit fixtures. No Pulse socket, audio device, Android process, service
operation or Main command is used.
