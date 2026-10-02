# Session state machine

The executable reference is `crates/hepta-session-core`. Adapters supply events
and monotonic time; the core owns no Servo object, socket, thread, or OS clock.

## Control state

| State | Meaning | Agent mutation |
| --- | --- | --- |
| `Idle` | no input owner | may begin when phase is Ready |
| `AgentObserving` | one Agent observation is active | no second operation |
| `AgentMutating` | one Agent mutation is active | no second operation |
| `HumanActive` | human focus lease owns interaction | refused |
| `HumanImeComposing` | human IME composition owns text input | refused |

## Session phase

| Phase | Meaning | Compatible mutation |
| --- | --- | --- |
| `Ready` | normal operation | subject to control state |
| `NavigationPending` | top-level document transition | none |
| `ModalBlocked` | browser/system modal unresolved | none |
| `CapabilityPending` | typed capability unresolved | none |
| `Cancelling` | cancellation reconciliation | none |
| `Recovering` | browser/session recovery | none |
| `Closed` | terminal | none |

## Key transitions

| Event | Preconditions | Result/effect |
| --- | --- | --- |
| begin Agent mutation | Ready + Idle | `AgentMutating` |
| human focus gained | Ready | interrupt Agent work, grant bounded lease, `HumanActive` |
| human input / IME transition | Ready + matching lease; IME also requires unexpired lease | extend lease or enter/leave `HumanImeComposing` |
| DOM committed | live content outside Recovering | increment `mutation_epoch` only |
| semantic snapshot published | live content outside Recovering | increment snapshot revision |
| Agent/system navigation started | Ready + Idle | enter NavigationPending |
| human navigation started | Ready + HumanActive + unexpired lease | enter NavigationPending; retain human custody |
| navigation committed | NavigationPending | increment document/snapshot/mutation; return Ready and preserve human custody |
| navigation failed / cancel completed | matching pending phase | return Ready; release Agent control and preserve human custody |
| browser crashed | session live | increment every identity layer, clear lease, Recovering |
| tick at lease expiry | matching active lease elapsed | clear human control, emit expiry |
| close | any non-terminal state | Closed; clear lease/control |

Focus cannot be granted while navigation, modal, capability, cancellation or
recovery blocks the content frame. Existing focus may be released in those
phases, and ticks may expire it. Phase completion does not clear a live human
lease or IME ownership: only release, expiry, crash and close revoke that
custody. Content callbacks from a crashed frame cannot publish document or
semantic revisions before an explicit `Recovered` event.

D4 may relax read-only observation during human activity only through a new ADR
and consistency/privacy evidence. It may not weaken mutation exclusion.
