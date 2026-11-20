# Calendar reminder native resource binding

The selected Calendar reminder controller reads `cpu.max` and `memory.max`
from its immediate cgroup and requires CPU quota at most 50% and exactly
512 MiB memory. The original native leaf runner creates a nested child without
local controller limits. A source-only bootstrap therefore cannot establish
that the real execution path will pass the original resource admission.

This successor preserves the complete original Calendar case and binds its
resource observation to a live native parent lease. The native parent and
child stay within the original cancellation scope. The dedicated validator
checks the actual native parent executable, pidfd, process identity, held
cgroup controls, complete adopted release and canonical CURRENT owner chain.
It accepts only source catalog index 1 and the Calendar-specific owned child
prefix. The original CPU and memory budgets are unchanged.

## Exact change boundary

Of the 33 selected source modules, 31 remain byte-for-byte identical, including
`system_case.py`, the complete planner, proof gates, business flow, UI helpers
and cleanup. The two changed modules are:

- `system_entry.py`: after the original source-packet validation and task-module
  loading, open the adopted native lease, bind the exact validator-created
  resource object, execute the original case, complete its original result
  publication, recheck the request and release, and print the original output
  within the same live lease context.
- `calendar_resources.py`: an explicitly bound live object supplies the nine
  actual held ancestor metrics. The result distinguishes the actual child
  membership from the limiting ancestor directory. The original
  `resource_limits` and `memory_events` functions are unchanged, and the old
  local collector remains the unbound path.

The preparation includes a 34th module, the dedicated
`native_calendar_release.py`. There is no added request field: the original
request remains exactly `{ "base_plan": FilePin }`. Reading CURRENT to discover
the release reference grants no authority; the actual lease independently
reopens and validates the entire relation under the original two lock OFDs.
Saved JSON resource reports, arbitrary cgroup paths and caller-provided PIDs
are not accepted as resource admission.

The native execution wrapper retains its original 690-second outer budget.
The effective ancestor additionally has zero swap, 64 PIDs and no OOM events;
the actual native process and its pinned control values are checked repeatedly.
The original Calendar result, success predicate, cancellation handling,
unknown-effect behavior and no-retry rule remain unchanged.

## Verification

The actual Pocket4 source bootstrap passed with 34 source files. An actual
wrong-external-hash invocation was rejected. All 44 preparation, source and
original proof references retained their exact hashes and F9 bookends. No
native lease or Main was opened during these source-only checks.

Four focused unit controls verify the 31 unchanged files and original resource
predicates, actual report shape and numeric limits, the 50% CPU boundary, and
the lease lifetime through original execution, cleanup, result publication and
failure. Offline fixtures grant no runtime authority. A separate reviewer
confirmed that the bound resource module is the same task module used before
and after the original business case; no reload discards the binding.

```sh
python3 adapt_sources.py
python3 -m unittest discover -s tests -v
python3 prepare_selection.py
```

The source reproduction reads the exact captured originals in `originals/`
and their `SOURCE-ORIGINS.json` pins. The selector reproduction also reads the
published sibling `gallery-image-consumer-20261120` packet from PR #320.

## Joint source selector

The new complete selector changes indices `1, 8, 9, 10, 11, 12`. Indices
`0, 2, 3, 4, 5, 6, 7` are unchanged. The full 42-app route map changes only the
Calendar and Gallery rows, preserves all original common/business gates, and
retains zero accepted gates. The five Gallery preparations themselves are
unchanged from their already verified source packet.

The source preparation and selector do not write CURRENT, install or enable a
native release, execute Android, or close a runtime gate. A matching native
driver/catalog build, final executable, canonical owner adoption, actual
current Main and every original identity/custody/business/cleanup gate remain
required. Runtime, business, data continuity and production acceptance remain
pending.
