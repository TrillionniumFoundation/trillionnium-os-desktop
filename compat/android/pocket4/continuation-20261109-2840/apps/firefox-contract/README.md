# Firefox business acceptance contract

The selected 42-app matrix's Firefox projection contains a purpose and primary flow but leaves its profile, business gate definitions, prerequisites, and common gate IDs null. This proposal fills those six existing contract fields. It does not change the frozen application checker or any runtime state.

## Integration boundary

**This contract is not integrated. All eleven required gates are pending, with zero tests executed and zero acceptance credit.** The original matrix identity is pinned in `source-binding.json` to SHA-256 `9b812661db9171bd3d12bd4068a5d3d54c52ea6a7557bc02798693657a61f21c`. The complete matrix bytes and root schema are not held offline, so this directory intentionally contains no patch that guesses a matrix JSON pointer. `observed-business-contract.json` preserves the previously read projection; it is not represented as a newly rehashed matrix subtree.

`firefox-business-contract.json` is the proposed contract, retaining the existing six field names and data types. The runtime owner must first verify the matrix preimage, locate the unique Firefox row using its real schema, confirm the browser profile is accepted by the existing harness, and integrate only that missing contract. If the matrix has advanced, reconcile it explicitly. The current planning status `pending` is recorded separately; no application-checker result rows have been fabricated.

## Five business gates

| Gate | Required observed behavior |
| --- | --- |
| `browser.external_https` | Actual implicit external HTTPS invocation, default BROWSER resolution to the selected Firefox, expected rendered document, and return to the caller. |
| `browser.document` | Correct visible text, exact editable Unicode input, and correctly decoded and rendered reference image. |
| `browser.media` | Actual reference video and audio, play/pause/seek/resume behavior, and normal shutdown without leaked output or a self-exit. |
| `browser.return` | Correct owned-tab Back/Forward state and normal reopen behavior under the recorded browser settings, preserving unrelated user data. |
| `browser.recovery` | Scoped request failure followed by recovery, plus one denied site permission honored without making the page unusable. |

These are required alongside the six common gates: identity, lifecycle, stability, data permissions, release scope, and UI observation. Each business gate's complete executable criteria and allowed inputs are in the contract JSON. Reference text, image and media identities, the owned origin, and the expected browser-setting behavior must be declared before runtime execution. No particular test endpoint is assumed to exist.

Only owned fixtures or public HTTPS resources and owned input strings are allowed. No login, SMS, message recipient, purchase, reservation, or ride request is part of this contract. Existing tabs, history, permission state, and preferences must remain intact; cleanup is restricted to the newly owned fixtures.

## Validation performed here

The structural receipt verifies field names and types against the observed projection, uniqueness of the five business and six common gates, preservation of the original purpose and primary flow, and that all eleven execution states are pending with no evidence. It does not prove compatibility with the missing root matrix schema, execution by an Android runner, official package installation, current Main/boot identity, or production readiness.
