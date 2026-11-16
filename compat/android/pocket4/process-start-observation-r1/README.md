# Initial process exit observation

A real short Git command exited successfully while `/proc/PID/exe` had already
disappeared and WNOWAIT had not yet exposed the waitable exit. The old immediate
failure could reject a correctly owned child before its actual terminal status
was available.

This change waits at most 0.5 seconds using the same held PIDFD and unreaped
child. It accepts either the actual process snapshot or the actual kernel exit
observation. It never substitutes a different PID, reaps the child early, treats
permission errors as successful exit, or qualifies an empty argv as the executed
normal command. The separate post-exec command witness remains mandatory.

Only this observation gap changes. The public lifecycle module retains its
original resource profile and retirement rules. Four focused controls cover a
late waitable exit, identity reappearance, finite deadline and permission errors.

```sh
python3 -B -m unittest -v test_start_observation.py
```
