# D0A-02 headed Servo runtime evidence

> **HISTORICAL SNAPSHOT / STALE_EVIDENCE:** This artifact is bound to source
> head `fe0ea6169127ce1f7950618b55374d83834a462c`. The active PR #60 candidate
> supersedes that snapshot; rerun `servo-headed-runtime` on the exact
> candidate head before promotion or an exact-main claim.

**Evidence date:** 2026-08-30  
**Gate:** `D0A-02`  
**Evidence tier:** `headed_host`  
**Status:** `PASS_HEADED_LOCAL_FIXTURE_ONLY`  
**Evidence lifecycle:** `STALE_EVIDENCE_REQUIRES_EXACT_HEAD_RERUN`
**Evidence freshness:** `STALE_EVIDENCE`
**Merge readiness:** `merge_ready: false` (historical evidence only)
**Candidate source head:** `fe0ea6169127ce1f7950618b55374d83834a462c`  
**Base main:** `bf6bba2ea1c49b36e11754bf27dc0c56e3da3bd1`  
**Tested merge SHA:** `0df9b9c15f51d12f34ef1af288dfae5a009f073f`  
**Git tree:** `37dc62883d12f3e8917f21545e8223ff809c452d`  
**Servo commit:** `670ae8a70801b162e186f81cbb5bdd2d59c39108`

## Permanent workflow identity

- Workflow: `.github/workflows/servo-headed-runtime.yml`
- Run: `33289966647`
- Job: `99199795258`
- Artifact: `9725709890`
- Artifact digest: `sha256:50ce0bc82723d6c64c8d2ca2ac900651273ef65e85e9f7b7c233e60f8e628978`
- Artifact size: `66302` bytes
- Workflow digest: `b82f725eb857bfa364ec763714967e67ad41ede931040d6a4ad7f0b1d5440dc3`
- Servo lock digest: `a64fc7f64926d0a3726ce50551aa879065bcfac285caa553494c7be59ad953f4`
- Formatted product overlay digest: `1631a61125b85430f2a2ebd9640c444fc7b89db987afab2d46fbbf76ec1007ce`

## Demonstrated facts

The exact source head compiled against a clean zero-patch checkout of the pinned
Servo commit and ran on an Ubuntu 24.04 GitHub-hosted X11/Xvfb environment. The
machine result records:

- one native trusted window;
- trusted chrome separate from untrusted content;
- a peak of one logical Servo content WebView;
- deterministic loopback-fixture generation 1;
- 5 native pointer, 6 button, 2 wheel, and 2 keyboard events;
- 19 Servo input-handled callbacks;
- three submitted IME composition events and three DOM composition observations;
- 2 popup requests and 2 external-navigation requests refused;
- exact content-process SIGKILL observation for PID 9038 at the recorded process
  start time;
- trusted-window survival during the content failure;
- replacement content generation 2;
- screenshot and process-topology digests bound in the machine evidence.

The identical generation screenshots are expected for the deterministic fixture;
the independent generation counter, process identity transition, crash
placeholder, and process-topology evidence distinguish recovery from a static
image assertion.

## Claim ceiling

This evidence proves only the headed local-fixture behavior on the exact tested
host environment. It does not prove:

- Debian image or QEMU integration;
- Wayland compositor integration;
- AgentPort, BrowserActor, or TaskFlow principal activation;
- external browsing, credentials, or effects;
- Secure Boot, hardware qualification, update safety, or release readiness.

The runtime log contains two post-success teardown warnings: an attempted wake
after the event loop closed and a background-hang-monitor disconnect during
shutdown. They did not invalidate the enforced evidence corpus, but remain
observable teardown debt.

## Promotion rule

This historical snapshot is not merge-ready. The active PR #60 candidate must
rerun the same source and headed-runtime corpus on its exact head, then pass
all exact-head gates. After merge, the corpus must pass again on exact main
before `D0A-02` becomes integrated truth.
