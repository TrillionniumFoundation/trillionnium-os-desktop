# AppArmor: preserve the credentials retained by Binder

A normal Binder transaction succeeded on the original Ubuntu kernel, while a
transaction requesting a security context failed with `BR_FAILED_REPLY` and
`-EINVAL`. Binder retains the credentials that opened its file descriptor. The
AppArmor LSM lacked the credential-to-security-ID hook required by that path.

## Change and source boundary

`apparmor-credential-secid.patch` adds `apparmor_cred_getsecid` and registers the
normal `cred_getsecid` LSM hook. It reads the label on the supplied retained
credential. It returns zero for an absent label, matching the invalid-security-ID
case. It does not substitute the active task's credentials, change Binder,
bypass a security-context request, or turn off AppArmor.

The patch applies to the official Ubuntu source tag `Ubuntu-7.0.0-43.43`, commit
`f53b359683af7918c5436499948763cb726d5082`, from the
[Ubuntu resolute kernel repository](https://git.launchpad.net/~ubuntu-kernel/ubuntu/+source/linux/+git/resolute).
The completed kernel release is `7.0.14-p4cred1`. The original kernel features
remain enabled; local release, compiler location and signing configuration are
bound in the actual configuration receipt.

## Actual validation

The normal full build and module installation completed all five commands and
retired their children. All 6,901 core modules were signed using the kernel's
normal compiled `sign-file` program and its existing signing key. Every module's
CMS signature was independently checked against the compiled public certificate,
and every unsigned payload was compared with its original bytes. Modified
payload and modified-signature controls were rejected. The private signing key
was neither copied nor read into this capsule.

The original baseline and the patched kernel were booted separately in isolated,
diskless KVM guests with no network interface. These controls used actual Binder
IPC, actual AppArmor profile transitions, an actual drop to UID 10001, and an
actual permission denial. The results were:

| Real transaction | Original baseline | Patched kernel |
| --- | --- | --- |
| Plain Binder IPC | Passed | Passed |
| Unconfined transaction requesting security context | Failed | Passed |
| Descriptor opened under A/root, task changed to B/UID 10001 | Failed | Received retained A label |
| Fresh descriptor opened under B/UID 10001 | Failed | Received B label |

Both test profiles enforced policy; the intentionally forbidden open returned
`EACCES`. All four patched transactions received valid replies. The guest,
owned QEMU process, unit and cgroup retired. The host kernel, host LSM state and
original Android user images remained unchanged.

`validation.json` contains compact results and full receipt hashes. These are
observations of the completed isolated test, not a request to load test policy
or modules on a host. Failed earlier build/signing attempts remain recorded in
the operational evidence and are not relabelled as successes.

## Guest control sources

The C source, its header and the AppArmor profiles are the exact sources used by
the successful VM. The C executable refuses execution before mounting anything
unless it runs as root PID 1 with the explicit disposable guest marker. The
normal compilation used:

```sh
gcc -std=c11 -Wall -Wextra -Werror -O2 -static \
  binder_saved_cred_probe.c -o binder_saved_cred_probe
```

The profiles were compiled through the normal AppArmor parser with kernel
loading and cache updates disabled. They belong only in the controlled guest.
The capsule deliberately contains no host installer, reboot action, raw private
initramfs, signing key or user data.

## Remaining release gates

The kernel and these four isolated credential controls are qualified. Host boot,
hardware operation, production Android UID mapping and seccomp, coherent
QPR1 Native/Audio payloads, Android startup and all selected application flows
remain separate gates. This capsule grants no Android or application runtime
acceptance and makes no production-ready claim.
