# Independent disposable-VM context controls; no host attachment.
profile p4-context-peer-a {
  file,
  network,
  capability setuid,
  capability setgid,
  capability setpcap,
  signal,
  ptrace,
  change_profile -> p4-context-peer-a,
  change_profile -> p4-context-peer-b,
  audit deny /p4-context-work/aa-denied r,
}
profile p4-context-peer-b {
  file,
  network,
  capability setuid,
  capability setgid,
  capability setpcap,
  signal,
  ptrace,
  change_profile -> p4-context-peer-a,
  change_profile -> p4-context-peer-b,
  audit deny /p4-context-work/aa-denied r,
}
