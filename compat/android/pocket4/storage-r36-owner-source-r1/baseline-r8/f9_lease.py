"""Pure gates for a separately admitted final-F9 role; no host action on import."""
import datetime
import math

from recovery_core import require, sha

ROLE = 'final_f9'
OWNER = 'foreground-root-e6ac9e05361c'
OLD_B_NONCE = '50e61f3b9db070a26e5841a273cf9bcf340a2a6617f35b0d1499645b8f0a7c22'
OLD_A_NONCE = 'd3d42145c55ccd5e99aa0172eb1647370d2f9a3570a8cfec9c264799760490d7'
WORK_SECONDS = 10800
NATIVE_SECONDS = 12000
STOP_SECONDS = 1200
INDEPENDENT_NATIVE_SECONDS = 4800
INDEPENDENT_STOP_SECONDS = 300
CLOSE_NATIVE_SECONDS = 90
CLOSE_STOP_SECONDS = 15
DISPATCH_ALLOWANCE_SECONDS = 600
ADDITIONAL_MARGIN_SECONDS = 1200
FULL_ENVELOPE_SECONDS = (DISPATCH_ALLOWANCE_SECONDS + NATIVE_SECONDS + STOP_SECONDS +
                         INDEPENDENT_NATIVE_SECONDS + INDEPENDENT_STOP_SECONDS +
                         CLOSE_NATIVE_SECONDS + CLOSE_STOP_SECONDS + ADDITIONAL_MARGIN_SECONDS)
MINIMUM_REMAINING_SECONDS = 21600


def owner_lease(owner, generation, nonce, expected_nonce, stage, now):
    # This is the accepted B lease pattern with a new explicit phase/nonce and
    # the separately reviewed whole final-F9 envelope. It never renews a lease.
    sha(nonce)
    require(nonce == expected_nonce and nonce not in (OLD_B_NONCE, OLD_A_NONCE) and
            stage in ('admit', 'dispatch', 'entry'), 'only the new final-F9 admission generation')
    require(type(now) is datetime.datetime and now.tzinfo is not None and now.utcoffset() is not None,
            'actual aware current time supplied by caller')
    require(owner['name'] == OWNER and owner['generation'] == generation,
            'same actually selected foreground owner')
    expires = datetime.datetime.fromisoformat(owner['active_until_utc'])
    require(expires.tzinfo is not None and expires.utcoffset() is not None,
            'explicit aware owner expiry')
    seconds = (expires - now).total_seconds()
    require(math.isfinite(seconds) and seconds >= MINIMUM_REMAINING_SECONDS and
            FULL_ENVELOPE_SECONDS == 20205 < MINIMUM_REMAINING_SECONDS,
            'actual CURRENT lease covers the new complete finite envelope')
    return {'phase': ROLE, 'phase_nonce': nonce, 'stage': stage,
            'owner_generation': generation, 'owner_active_until_utc': owner['active_until_utc'],
            'required_seconds': MINIMUM_REMAINING_SECONDS,
            'actual_remaining_seconds': seconds, 'whole_envelope_seconds': FULL_ENVELOPE_SECONDS,
            'cleanup_independent_of_expired_lease': True}


def storage_envelope(ready, measured, pocket4_boot, now_monotonic_ns, now_unix_ns):
    require(type(now_monotonic_ns) is int and now_monotonic_ns > 0 and
            type(now_unix_ns) is int and now_unix_ns > 0 and
            type(ready['deadline_monotonic_ns']) is int and
            type(measured['observed_unix_ns']) is int,
            'actual integer clocks and original storage deadline')
    require(measured['boot'] == pocket4_boot, 'same separately observed P4 storage boot')
    remaining = measured['remaining_seconds']
    require(type(remaining) in (int, float) and math.isfinite(remaining),
            'finite original measured P4 remaining duration')
    elapsed = (now_unix_ns - measured['observed_unix_ns']) / 10**9
    require(0 <= elapsed <= 600, 'unchanged bounded P4 observation age')
    desktop = (ready['deadline_monotonic_ns'] - now_monotonic_ns) / 10**9
    pocket4 = remaining - elapsed
    require(min(desktop, pocket4) >= MINIMUM_REMAINING_SECONDS,
            'both original new-owner deadlines cover the complete final-F9 envelope')
    return {'desktop_remaining_seconds': desktop, 'pocket4_remaining_seconds': pocket4,
            'measured_elapsed_seconds': elapsed, 'required_seconds': MINIMUM_REMAINING_SECONDS,
            'whole_envelope_seconds': FULL_ENVELOPE_SECONDS,
            'deadline_was_extended': False}
